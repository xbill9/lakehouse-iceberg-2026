#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry point for the Iceberg REST catalog conformance harness."""
import argparse
import os
import sys

import yaml

from probe.report import build_csv, build_markdown, load
from probe.runner import CatalogRun


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--config", default="catalogs.yaml")
    ap.add_argument("-e", "--evidence-dir", default="evidence")
    ap.add_argument("-o", "--out-dir", default="out")
    ap.add_argument("--only", help="comma-separated catalog names to run")
    ap.add_argument("--allow-writes", action="store_true",
                    help="run the mutating write tier against a scratch namespace")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild the matrix from existing evidence, no network")
    args = ap.parse_args()

    if not args.report_only:
        if not os.path.exists(args.config):
            sys.exit("no config at %s (copy catalogs.example.yaml and fill it in)" % args.config)
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
        catalogs = cfg.get("catalogs", [])
        # A catalog still holding placeholder config must not be probed: it
        # answers with real HTTP errors that look like conformance results but
        # only describe a wrong warehouse. Transport-level quarantine cannot
        # catch that, so unconfigured catalogs are opted out explicitly.
        skipped = [c["name"] for c in catalogs if c.get("enabled") is False]
        if skipped:
            print("skipping (enabled: false): %s\n" % ", ".join(skipped))
        catalogs = [c for c in catalogs if c.get("enabled") is not False]
        if args.only:
            want = {s.strip() for s in args.only.split(",")}
            catalogs = [c for c in catalogs if c["name"] in want]
        if not catalogs:
            sys.exit("no catalogs selected")
        if args.allow_writes:
            print("!! write tier enabled: this CREATES a scratch namespace and table")
            print("!! on every selected catalog and attempts to drop them afterwards.\n")
        os.makedirs(args.evidence_dir, exist_ok=True)
        for c in catalogs:
            try:
                CatalogRun(c, args.evidence_dir, allow_writes=args.allow_writes).run()
            except Exception as e:
                # One unreachable vendor must not sink the whole run.
                print("  !! %s failed: %s: %s" % (c.get("name"), type(e).__name__, e))

    runs = load(args.evidence_dir)
    if not runs:
        sys.exit("no evidence found in %s" % args.evidence_dir)
    os.makedirs(args.out_dir, exist_ok=True)
    md = os.path.join(args.out_dir, "conformance-matrix.md")
    csvp = os.path.join(args.out_dir, "conformance-matrix.csv")
    with open(md, "w") as f:
        f.write(build_markdown(runs))
    with open(csvp, "w") as f:
        f.write(build_csv(runs))
    print("\nmatrix -> %s\n          %s" % (md, csvp))


if __name__ == "__main__":
    main()
