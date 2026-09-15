#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce the configurations that reach the catalog and cannot read the data.

Each case changes ``iceberg_tool``'s storage wiring by intercepting the
properties the tool hands to ``RestCatalog`` -- so what runs is the tool's own
configuration with one thing taken away, not a second hand-built one. It then
calls ``iceberg_list_tables`` and ``iceberg_scan_table``, in that order: the
metadata call succeeding first is what shows the catalog was reachable.

Every case states its expected outcome, and one of them is expected to READ.
MEASURED 2026-09-14: removing only ``adls.credential`` while keeping fsspec and
the OneLake account name and host does not fail, because adlfs resolves
DefaultAzureCredential itself when handed none. The 2026-09-04 TypeError comes
from having no ``adls.*`` configuration at all under PyArrowFileIO -- the tool's
default before its Azure branch -- and that is what case A now reproduces. The
credential-only case is kept as a null result rather than dropped.

A control follows the cases: the same calls with the wiring intact. Without it
an error could be the catalog's, or the machine's, rather than the change's --
it is what caught adlfs missing from this machine on its first run.

    python3 failure_modes.py

Writes failure-modes.txt into the raw evidence directory only if every case
behaves as labelled and every control reads.
"""
import asyncio
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))
os.environ.setdefault("ICEBERG_CATALOGS_FILE",
                      os.path.join(ROOT, "iceberg-conformance", "catalogs.yaml"))

import pyiceberg.catalog.rest as rest  # noqa: E402

import iceberg_tool  # noqa: E402
from run_matrix import RAW  # noqa: E402

REAL = rest.RestCatalog
FSSPEC = "pyiceberg.io.fsspec.FsspecFileIO"
PYARROW = "pyiceberg.io.pyarrow.PyArrowFileIO"
S3_KEYS = ("s3.access-key-id", "s3.secret-access-key", "s3.session-token")


def no_adls_configuration(props: dict) -> bool:
    wired = props.get("py-io-impl") == FSSPEC and "adls.credential" in props
    for key in [k for k in props if k.startswith("adls.")]:
        props.pop(key)
    props["py-io-impl"] = PYARROW
    return wired


def drop_adls_credential_only(props: dict) -> bool:
    return props.pop("adls.credential", None) is not None


def pyarrow_io(props: dict) -> bool:
    wired = props.get("py-io-impl") == FSSPEC and "adls.credential" in props
    props["py-io-impl"] = PYARROW
    return wired


def drop_local_s3(props: dict) -> bool:
    found = [props.pop(k, None) for k in S3_KEYS]
    return found[0] is not None and found[1] is not None


#: (label, title, catalog, table, change, expected) -- expected is "error" or "reads".
CASES = [
    ("A", "OneLake, no ADLS configuration (PyArrowFileIO, no adls.* properties)",
     "microsoft-onelake", "dbo.probe_table", no_adls_configuration, "error"),
    ("B", "OneLake, ADLS credential set but PyArrowFileIO instead of fsspec",
     "microsoft-onelake", "dbo.probe_table", pyarrow_io, "error"),
    ("C", "Glue, SigV4 for the catalog but no local S3 credentials",
     "aws-glue", "probe_ns.probe_table", drop_local_s3, "error"),
    ("D", "OneLake, fsspec with account host but adls.credential removed "
          "(expected to read: adlfs falls back to DefaultAzureCredential)",
     "microsoft-onelake", "dbo.probe_table", drop_adls_credential_only, "reads"),
]


def run(catalog: str, table: str, change) -> tuple:
    """One list and one scan through the tool, with `change` applied to its props."""
    def patched(name, **props):
        if change and not change(props):
            raise SystemExit("precondition not met: the wiring this case changes "
                             "was not in the tool's props for %s" % catalog)
        return REAL(name, **props)

    rest.RestCatalog = patched
    try:
        os.environ["ICEBERG_CATALOG"] = catalog
        iceberg_tool._catalog = None
        iceberg_tool.reset_budget()
        listed = asyncio.run(iceberg_tool.iceberg_list_tables())
        scanned = asyncio.run(iceberg_tool.iceberg_scan_table(table, limit=3))
    finally:
        rest.RestCatalog = REAL
    return listed, scanned


def read_line(scanned: str) -> str:
    """The scan's summary line, not its rows."""
    hits = [l for l in scanned.splitlines() if "row(s), read from snapshot-id" in l]
    return hits[0] if hits else ""


def main() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rule = "=" * 78
    out = ["# failure modes reproduced deliberately, captured %s" % now,
           "# each changes one piece of the tool's storage wiring and calls",
           "# iceberg_scan_table, to show what that configuration actually produces.",
           "# Metadata calls are shown succeeding first, which is the point: the catalog",
           "# is reachable in every case below. Case D is expected to read, and is kept",
           "# as a null result. The control at the end runs the same calls unchanged.", ""]
    ok = True
    # Changed cases first: a filesystem cached by a working control could
    # otherwise be reused by a case that is meant to lack its configuration.
    for label, title, catalog, table, change, expected in CASES:
        listed, scanned = run(catalog, table, change)
        got = "error" if scanned.startswith("CATALOG ERROR") else "reads"
        out += [rule, "%s. %s" % (label, title), rule,
                "-- metadata call (iceberg_list_tables):", listed,
                "-- data call (iceberg_scan_table):",
                scanned if got == "error" else read_line(scanned), ""]
        if listed.startswith("CATALOG ERROR") or got != expected:
            ok = False
            print("UNEXPECTED in case %s: expected %s, got %s: %r"
                  % (label, expected, got, scanned[:160]))

    out += [rule, "control. The same calls with the tool's wiring unchanged", rule]
    for catalog, table in (("microsoft-onelake", "dbo.probe_table"),
                           ("aws-glue", "probe_ns.probe_table")):
        listed, scanned = run(catalog, table, None)
        line = read_line(scanned)
        out.append("%-18s list: %s | scan: %s"
                   % (catalog, listed.replace("\n", ", "), line or scanned[:300]))
        if not line:
            ok = False
            print("UNEXPECTED: control scan failed on %s" % catalog)

    text = "\n".join(out) + "\n"
    print(text)
    if not ok:
        sys.exit("failure-modes.txt NOT written: a case or control did not behave as labelled")
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "failure-modes.txt"), "w") as handle:
        handle.write(text)
    print("wrote %s/failure-modes.txt" % RAW)


if __name__ == "__main__":
    main()
