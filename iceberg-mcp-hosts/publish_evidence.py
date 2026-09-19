#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anonymise this paper's evidence and publish it, or refuse.

    python3 publish_evidence.py

Nothing else writes into the published directory. Raw evidence stays here and
carries real account state: the Google ground truth names a GCS bucket after the
project, and a frame trace records the arguments a host actually sent, which for
a SQL surface is a query naming real objects.

The rule is the one `iceberg-conformance/anonymize_evidence.py` already enforces
and that `check-no-identifiers.sh` exists to double-check, because the anonymiser
missed a project id once by having no pattern for it:

  * one mapping is built over every file at once, so the same identifier masks to
    the same token everywhere and two files can still be read against each other;
  * every published file is scanned afterwards, and a single residual hit aborts
    the whole publish rather than writing a partial set;
  * a `--full` trace is refused outright. It keeps result bodies, and a result
    body from a catalog can carry vended credentials.

Refusing is the designed outcome. A publish that half-worked is worse than none,
because the half that worked looks finished.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))

import anonymize_evidence as anon  # noqa: E402

EVIDENCE = os.path.join(HERE, "evidence")
#: Hosts that are the finding rather than an account. The MCP endpoints are the
#: subject of the paper; masking them would turn the server list into noise.
anon.KEEP_HOSTS |= {"bigquery.googleapis.com", "dataproc-us-central1.googleapis.com",
                    "localhost:8181", "github.com", "docs.cloud.google.com",
                    "storage.azure.com"}


def collect():
    """Every raw artefact, keyed by the path it will be published at."""
    out = {}
    for path in sorted(glob.glob(os.path.join(EVIDENCE, "*.txt"))):
        out[os.path.basename(path)] = open(path).read()
    for path in sorted(glob.glob(os.path.join(EVIDENCE, "matrix-axis-*.json"))):
        out[os.path.basename(path)] = open(path).read()
    for sub in ("matrix", "traces"):
        for path in sorted(glob.glob(os.path.join(EVIDENCE, sub, "*"))):
            out["%s/%s" % (sub, os.path.basename(path))] = open(path).read()
    return out


def collect_sweep():
    """The catalog sweep only: one MCP server, one catalog per process."""
    out = {}
    for path in sorted(glob.glob(os.path.join(EVIDENCE, "catalog-sweep-*"))):
        if ".failed." not in path:
            out[os.path.basename(path)] = open(path).read()
    return out


def refuse_full_traces(texts):
    """A --full trace keeps result bodies. Those are never published."""
    bad = []
    for name, text in texts.items():
        if not name.startswith("traces/"):
            continue
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("full") is True:
                bad.append(name)
                break
    if bad:
        raise SystemExit(
            "refusing to publish: %d trace(s) were recorded with --full, which "
            "keeps result bodies:\n  %s\n  re-run those cells without --full."
            % (len(bad), "\n  ".join(bad)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "papers", "iceberg-mcp-hosts", "evidence"),
                    help="published directory; provisional until the article has a slug")
    ap.add_argument("--sweep", action="store_true",
                    help="publish the catalog sweep to papers/iceberg-mcp-seven-catalogs/evidence")
    a = ap.parse_args()
    if a.sweep and a.out == ap.get_default("out"):
        a.out = os.path.join(ROOT, "papers", "iceberg-mcp-seven-catalogs", "evidence")

    texts = collect_sweep() if a.sweep else collect()
    if not texts:
        raise SystemExit("nothing to publish: %s is empty. Run the matrix first." % EVIDENCE)
    refuse_full_traces(texts)

    # One mapping over everything, so an id masks identically in every file.
    combined = "\n".join(texts.values())
    mapping = {k: v for k, v in anon.build_map(combined).items() if "@" not in k}

    clean, residual = {}, []
    for name, text in texts.items():
        c = anon.apply_map(text, mapping)
        clean[name] = c
        for label, sample, n in anon.residual_scan(c):
            residual.append("  %-38s %-22s %s (x%d)" % (name, label, sample, n))
    if residual:
        raise SystemExit("refusing to publish, %d residual identifier(s):\n%s"
                         % (len(residual), "\n".join(residual)))

    for name, text in clean.items():
        dest = os.path.join(a.out, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as h:
            h.write(text)
    print("mapped %d identifier(s); published %d file(s) to %s"
          % (len(mapping), len(clean), a.out))


if __name__ == "__main__":
    main()
