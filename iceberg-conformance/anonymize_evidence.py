#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rewrite stored evidence into a publishable form.

Evidence is the point of this harness -- a verdict should be re-derivable
without re-running against a vendor -- but the raw files carry identifiers from
the accounts they were gathered against: AWS account numbers, a GCP project and
its number, bucket names, a Databricks workspace host, a Snowflake account
locator, and Fabric workspace and lakehouse GUIDs. Several of those appear
inside error message bodies rather than in fields, which is why this rewrites
the file text rather than walking the JSON.

Two rules:

  Consistency. A given real value maps to one pseudonym everywhere, so
  cross-references survive: the table-uuid that createTable returned is still
  the table-uuid the later assert-table-uuid requirement carries, and a reader
  can still check that the suite did what it claims.

  Everything else is untouched. Status codes, verdicts, error text, field
  states, declared endpoint lists, timings and the harness fingerprint are the
  evidence, and none of them are rewritten.

GUIDs are masked wholesale rather than triaged. Most are harmless per-run table
UUIDs, but some encode a vendor's internal storage layout, and telling them
apart by eye across 280 values is exactly the kind of judgement that gets one
wrong. Masking all of them consistently costs a little readability and leaks
nothing.

Usage:  python3 anonymize_evidence.py [--in evidence] [--out evidence-public]
"""
import argparse
import json
import os
import re
import shutil
import sys

# Public API hostnames. These identify the vendor, not the account, and are the
# whole point of the evidence -- they stay.
KEEP_HOSTS = {
    "biglake.googleapis.com",
    "glue.us-east-1.amazonaws.com",
    "s3tables.us-east-1.amazonaws.com",
    "onelake.table.fabric.microsoft.com",
    "localhost:8181",
    "127.0.0.1:8181",
}

GUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                     re.I)
AWS_ACCT_RE = re.compile(r"\b\d{12}\b")
BUCKET_RE = re.compile(r"(?:gs|s3|s3a|abfss)://([A-Za-z0-9._@-]+)")
HOST_RE = re.compile(r"https?://([A-Za-z0-9.-]+(?::\d+)?)/")
# S3 Tables' managed buckets carry a long random component before "--table-s3".
S3TABLES_BUCKET_RE = re.compile(r"\b[0-9a-f-]{8,}[a-z0-9]{20,}--table-s3\b", re.I)


def build_map(text):
    """Deterministic real-value -> pseudonym map, ordered by first appearance."""
    m = {}

    def add(real, kind, counter=[0]):
        if real and real not in m:
            counter[0] += 1
            m[real] = "%s-%04d" % (kind, len([k for k, v in m.items()
                                              if v.startswith(kind)]) + 1)
        return m.get(real)

    for host in HOST_RE.findall(text):
        if host not in KEEP_HOSTS:
            add(host, "catalog-host")
    for b in S3TABLES_BUCKET_RE.findall(text):
        add(b, "managed-bucket")
    for b in BUCKET_RE.findall(text):
        if b not in m:
            add(b, "bucket")
    for a in AWS_ACCT_RE.findall(text):
        add(a, "aws-account")
    for g in GUID_RE.findall(text):
        add(g.lower(), "guid")
    return m


def apply_map(text, m):
    # Longest first: a bucket name can contain an account number, and replacing
    # the shorter token first would corrupt the longer one.
    for real in sorted(m, key=len, reverse=True):
        text = re.sub(re.escape(real), m[real], text, flags=re.I)
    return text


def residual_scan(text):
    """Report anything that still looks like an identifier. Fails loudly."""
    findings = []
    for label, pat in (("guid", GUID_RE),
                       ("12-digit account", AWS_ACCT_RE),
                       ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"))):
        hits = {h if isinstance(h, str) else h[0] for h in pat.findall(text)}
        hits = {h for h in hits if not h.startswith(("guid-", "aws-account-"))}
        if hits:
            findings.append((label, sorted(hits)[:5], len(hits)))
    for host in set(HOST_RE.findall(text)):
        if host not in KEEP_HOSTS and not host.startswith("catalog-host-"):
            findings.append(("host", [host], 1))
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", default="evidence")
    ap.add_argument("--out", dest="dst", default="evidence-public")
    args = ap.parse_args()

    files = sorted(f for f in
                   (os.path.join(args.src, d, "evidence.json")
                    for d in sorted(os.listdir(args.src)))
                   if os.path.exists(f))
    if not files:
        sys.exit("no evidence under %s" % args.src)

    combined = "".join(open(f).read() for f in files)
    m = build_map(combined)
    print("mapped %d distinct identifiers" % len(m))
    for kind in ("catalog-host", "bucket", "managed-bucket", "aws-account", "guid"):
        n = sum(1 for v in m.values() if v.startswith(kind))
        if n:
            print("   %-16s %d" % (kind, n))

    if os.path.isdir(args.dst):
        shutil.rmtree(args.dst)
    os.makedirs(args.dst)

    residual_total = 0
    for f in files:
        cat = os.path.basename(os.path.dirname(f))
        out = apply_map(open(f).read(), m)
        json.loads(out)          # must still parse
        r = residual_scan(out)
        residual_total += sum(x[2] for x in r)
        for label, sample, n in r:
            print("   !! %s: %d remaining, e.g. %s" % (label, n, sample))
        os.makedirs(os.path.join(args.dst, cat), exist_ok=True)
        with open(os.path.join(args.dst, cat, "evidence.json"), "w") as fh:
            fh.write(out)
        print("   %-19s -> %s" % (cat, os.path.join(args.dst, cat, "evidence.json")))

    with open(os.path.join(args.dst, "README.md"), "w") as fh:
        fh.write(
            "# Anonymized evidence\n\n"
            "Produced by `anonymize_evidence.py` from the raw run output. Every\n"
            "identifier tied to the accounts these runs were gathered against has\n"
            "been replaced with a stable pseudonym: AWS account numbers, bucket\n"
            "names, the Databricks workspace host, the Snowflake account locator,\n"
            "and all GUIDs.\n\n"
            "The mapping is consistent across every file, so cross-references still\n"
            "hold -- the `table-uuid` returned by `create_table` is the same value\n"
            "the later `assert-table-uuid` requirement carries.\n\n"
            "Nothing else is rewritten. Status codes, verdicts, error message text,\n"
            "field states, declared endpoint lists, timings and the harness\n"
            "fingerprint are the evidence and are reproduced as recorded.\n\n"
            "Public API hostnames are kept, because they identify the vendor rather\n"
            "than the account.\n")

    if residual_total:
        sys.exit("\n%d identifiers survived anonymization; not safe to publish"
                 % residual_total)
    print("\nresidual scan clean")


if __name__ == "__main__":
    main()
