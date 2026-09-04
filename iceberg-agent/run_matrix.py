#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the same question across a matrix of legs and catalogs, N times each.

A single run of each leg proves the wiring works and nothing else. It cannot
say whether a difference between two legs is a property of the framework, of
the model, or of the catalog, because a one-run-per-leg layout moves all three
at once -- and it cannot say whether a result is stable.

So this runs two axes separately:

  axis A   catalog fixed, legs vary      -> isolates framework and model
  axis B   leg fixed, catalogs vary      -> isolates the catalog

with repetition in both, and scores every answer against ground truth read from
the catalog itself rather than through any agent.

    python3 run_matrix.py --axis A --repeat 3
    python3 run_matrix.py --axis B --repeat 3 --leg gcp
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE = os.path.join(os.path.dirname(HERE),
                        "papers", "iceberg-agent-three-clouds", "evidence")
QUESTION = ("How many rows are in the probe table, and what columns does it "
            "have? Cite the exact table version you read.")

#: Axis A holds the catalog still. Polaris is the control: local, free, and
#: carrying the same fixture as the cloud catalogs, so nothing about it varies
#: between legs.
AXIS_A_CATALOG = "apache-polaris"
AXIS_B_LEG = "gcp"
CATALOGS = ["apache-polaris", "google-lakehouse", "aws-glue",
            "aws-s3tables", "microsoft-onelake"]
LEGS = ["gcp", "aws", "azure"]


def ground_truth() -> dict:
    """Per-catalog expected answers, parsed from the captured ground truth."""
    truth, cur = {}, None
    with open(os.path.join(EVIDENCE, "ground-truth.txt")) as handle:
        for line in handle:
            m = re.match(r"catalog=(\S+) table=(\S+)", line.strip())
            if m:
                cur = m.group(1)
                truth[cur] = {"table": m.group(2)}
            elif cur and "=" in line:
                k, v = line.strip().split("=", 1)
                truth[cur][k] = v
    return truth


def score(body: str, truth: dict) -> dict:
    """What the answer got right, by string and integer comparison only."""
    header = re.search(r"catalog_calls=(\d+)", body)
    cols = truth["columns"].split(",")
    return {
        "correct_row_count": bool(re.search(r"\b%s\b" % truth["rows"], body)),
        "cites_snapshot": truth["snapshot_id"] in body,
        "cites_metadata": truth["metadata_location"] in body,
        "names_all_columns": all(c in body for c in cols),
        # A column the fixture does not have. OneLake's table has no `region`,
        # so naming it there is an invention rather than a reading.
        "invented_column": ("region" in body) and ("region" not in cols),
        "catalog_calls": int(header.group(1)) if header else None,
    }


def one_run(leg: str, catalog: str, index: int) -> dict:
    env = dict(os.environ)
    env["ICEBERG_CATALOG"] = catalog
    started = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "run_once.py"), leg, QUESTION,
         "--catalog", catalog],
        capture_output=True, text=True, cwd=HERE, env=env, timeout=900)
    elapsed = round(time.time() - started, 1)
    body = proc.stdout + proc.stderr
    path = os.path.join(EVIDENCE, "matrix", "%s__%s__%d.txt" % (leg, catalog, index))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("# leg=%s catalog=%s run=%d elapsed_s=%s captured=%s\n\n"
                     % (leg, catalog, index, elapsed,
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        handle.write(body)
    return {"leg": leg, "catalog": catalog, "run": index,
            "elapsed_s": elapsed, "capture": os.path.basename(path), "body": body}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["A", "B"], required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--leg", default=AXIS_B_LEG)
    args = ap.parse_args()

    truth = ground_truth()
    cells = ([(leg, AXIS_A_CATALOG) for leg in LEGS] if args.axis == "A"
             else [(args.leg, cat) for cat in CATALOGS])

    results = []
    for leg, catalog in cells:
        for index in range(1, args.repeat + 1):
            row = one_run(leg, catalog, index)
            row.update(score(row.pop("body"), truth[catalog]))
            results.append(row)
            print("  %-6s %-19s run %d  %5ss  count=%s snap=%s meta=%s cols=%s calls=%s"
                  % (leg, catalog, index, row["elapsed_s"],
                     "ok" if row["correct_row_count"] else "NO",
                     "ok" if row["cites_snapshot"] else "NO",
                     "ok" if row["cites_metadata"] else "NO",
                     "ok" if row["names_all_columns"] else "NO",
                     row["catalog_calls"]), flush=True)

    out = os.path.join(EVIDENCE, "matrix-axis-%s.json" % args.axis)
    with open(out, "w") as handle:
        json.dump({"axis": args.axis, "question": QUESTION,
                   "repeat": args.repeat, "results": results}, handle, indent=2)
    print("\nwrote %s (%d runs)" % (out, len(results)))


if __name__ == "__main__":
    main()
