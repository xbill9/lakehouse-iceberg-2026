#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the answers straight from the catalog, so grading never goes through a host.

The same rule the agent matrix runs on: the thing being measured cannot also be
the thing that says whether the measurement was right. Every value here comes
from pyiceberg against the REST catalog directly -- no MCP server, no CLI host.

    python3 ground_truth.py --catalog apache-polaris --catalog google-lakehouse

Writes evidence/ground-truth-<catalog>.txt, one per catalog, because the servers
do not all read the same one. morristai and ahodroj talk to the local Polaris;
the BigQuery and Managed Spark MCP servers talk to Google. Those are different
physical tables holding the same seeded fixture, so they have different snapshot
ids and different metadata locations, and a single ground-truth file would score
every Google cell 0 on the citation checks for reasons that have nothing to do
with the server.

Shape matches the agent matrix's, so the grader is shared rather than rewritten.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# iceberg_tool already builds a RestCatalog for any of the seven, including the
# six credential flows. Reusing it rather than writing a seventh path here is
# the same reason it imports probe.auth instead of reimplementing them.
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))
sys.path.insert(0, os.path.join(ROOT, "iceberg-agent"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", action="append", dest="catalogs",
                    help="repeatable; defaults to apache-polaris")
    ap.add_argument("--namespace", default="probe_ns")
    ap.add_argument("--table", default="probe_table")
    a = ap.parse_args()

    for catalog in (a.catalogs or ["apache-polaris"]):
        os.environ["ICEBERG_CATALOG"] = catalog
        import importlib
        import iceberg_tool  # noqa: E402  -- needs the path inserts above
        # The module caches a catalog client, so a second catalog in the same
        # process would silently be read through the first one's connection.
        importlib.reload(iceberg_tool)

        tbl = iceberg_tool.catalog().load_table((a.namespace, a.table))
        snap = tbl.current_snapshot()

        cols = [f.name for f in tbl.schema().fields]
        types = {f.name: str(f.field_type) for f in tbl.schema().fields}
        rows = int(snap.summary.get("total-records", -1)) if snap else -1

        # Q1 asks what namespaces exist, and it had no truth to be graded
        # against, so it scored 0 in every run of the first two matrices for
        # want of a field rather than for want of an answer.
        spaces = sorted(".".join(n) for n in iceberg_tool.catalog().list_namespaces())

        # Q6 asks how many snapshots the table has. The current snapshot id is
        # compelled by the instruction -- every answer cites it -- so a question
        # whose answer IS that id cannot be graded. The count is not compelled,
        # so it can be.
        snapshots = len(tbl.metadata.snapshots or [])

        # Q2 asks about a namespace that is deliberately not there. Recorded so
        # the grader compares against a measured absence rather than a
        # remembered one -- if someone creates it, this file changes and the
        # question stops being a trap, loudly.
        absent = os.getenv("ICEBERG_ABSENT_NAMESPACE", "analytics")
        absent_really = absent not in [s.split(".")[0] for s in spaces]

        # Q5 asks for the range of the ts column. Same story: unmeasured, and
        # its column in the results table was really reporting whether the
        # answer happened to mention the row count in passing. The range is
        # computed here, in code, from the same snapshot the rest is read from
        # -- never asked of a model, and never derived from a host's answer.
        ranges = {}
        table = tbl.scan().to_arrow()
        for name in cols:
            column = table.column(name)
            try:
                import pyarrow.compute as pc
                low, high = pc.min(column).as_py(), pc.max(column).as_py()
            except Exception:      # noqa: BLE001 - a type with no ordering
                continue
            if low is None or high is None:
                continue
            ranges[name] = (low, high)

        out = [
            "catalog=%s table=%s.%s" % (catalog, a.namespace, a.table),
            "  table=%s.%s" % (a.namespace, a.table),
            "  rows=%d" % rows,
            "  namespaces=%s" % ",".join(spaces),
            "  namespace_count=%d" % len(spaces),
            "  snapshots=%d" % snapshots,
            "  absent_namespace=%s" % (absent if absent_really else ""),
            "  columns=%s" % ",".join(cols),
            "  types=%s" % ",".join("%s:%s" % (c, types[c]) for c in cols),
            "  snapshot_id=%s" % (snap.snapshot_id if snap else "none"),
            "  metadata_location=%s" % tbl.metadata_location,
        ] + [
            "  range_%s=%s|%s" % (c, ranges[c][0], ranges[c][1]) for c in cols if c in ranges
        ] + [
            "  read_at=%s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ]
        text = "\n".join(out) + "\n"
        # One file per TABLE, not per catalog. Two tables in one catalog is the
        # whole design of the scale arm, and a single filename would have had
        # the 99,999-row truth silently overwrite the 11-row one -- the same
        # clobber that lost a host's scored rows earlier in this work.
        stem = "ground-truth-%s" % catalog
        if a.table != "probe_table":
            stem += "-%s" % a.table
        path = os.path.join(HERE, "evidence", stem + ".txt")
        with open(path, "w") as h:
            h.write(text)
        print(text, end="")
        print("wrote %s\n" % path)


if __name__ == "__main__":
    main()
