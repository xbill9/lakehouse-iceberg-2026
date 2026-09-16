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

        out = [
            "catalog=%s table=%s.%s" % (catalog, a.namespace, a.table),
            "  rows=%d" % rows,
            "  columns=%s" % ",".join(cols),
            "  types=%s" % ",".join("%s:%s" % (c, types[c]) for c in cols),
            "  snapshot_id=%s" % (snap.snapshot_id if snap else "none"),
            "  metadata_location=%s" % tbl.metadata_location,
            "  read_at=%s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ]
        text = "\n".join(out) + "\n"
        path = os.path.join(HERE, "evidence", "ground-truth-%s.txt" % catalog)
        with open(path, "w") as h:
            h.write(text)
        print(text, end="")
        print("wrote %s\n" % path)


if __name__ == "__main__":
    main()
