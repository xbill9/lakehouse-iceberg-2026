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
#: Runs write here, never to the paper's evidence directory. It is gitignored
#: and holds real account identifiers; publish_evidence.py is the only way out,
#: and it re-scores and anonymises on the way.
RAW = os.path.join(os.path.dirname(HERE), "iceberg-conformance", "evidence", "paper3-raw")
QUESTION = ("How many rows are in the probe table, and what columns does it "
            "have? Cite the exact table version you read.")

#: Axis A holds the catalog still. Polaris is the control: local, free, and
#: carrying the same fixture as the cloud catalogs, so nothing about it varies
#: between legs.
AXIS_A_CATALOG = "apache-polaris"
AXIS_B_LEG = "gcp"
#: Axis C holds the model still and varies the framework, on the Axis A catalog.
#: Axis A cannot do this: each leg pairs one framework with one model. Strands on
#: Gemini is the crossover -- it shares a model with the ADK cell and a framework
#: with the Nova cell, so each comparison moves exactly one thing. All three cells
#: run in one sitting so they are comparable with each other.
AXIS_C_CELLS = [("gcp", "gemini-2.5-flash"), ("aws", "gemini-2.5-flash"),
                ("aws", "us.amazon.nova-micro-v1:0")]
FRAMEWORK = {"gcp": "ADK", "aws": "Strands", "azure": "Agent Framework"}
CATALOGS = ["apache-polaris", "google-lakehouse", "aws-glue",
            "aws-s3tables", "microsoft-onelake"]
LEGS = ["gcp", "aws", "azure"]


def ground_truth() -> dict:
    """Per-catalog expected answers, parsed from the captured ground truth."""
    truth, cur = {}, None
    with open(os.path.join(RAW, "ground-truth.txt")) as handle:
        for line in handle:
            m = re.match(r"catalog=(\S+) table=(\S+)", line.strip())
            if m:
                cur = m.group(1)
                truth[cur] = {"table": m.group(2)}
            elif cur and "=" in line:
                k, v = line.strip().split("=", 1)
                truth[cur][k] = v
    return truth


#: v1 matched against the whole capture: any standalone number counted as the row
#: count, and `id` and `ts` matched inside "snapshot-id" and "exists", so an
#: answer naming no columns could pass. MEASURED 2026-09-15 by planting
#: "snapshot-id exists; payload region. 11", which v1 scored as a correct count
#: with every column named. v2 reads only the answer, needs the count beside
#: "row"/"rows", and matches column names as whole words.
SCORER_VERSION = 2
ANSWER = re.compile(r"<!-- cloud=.*?-->\n(.*?)\ncatalog calls:", re.S)


def answer_of(body: str) -> str:
    """The text after the stamped header -- not the question, the thinking or the tool log."""
    m = ANSWER.search(body)
    return m.group(1) if m else ""


def word(name: str, text: str) -> bool:
    """`name` as a whole identifier: not inside snapshot-id, not inside exists."""
    return bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text))


def score(body: str, truth: dict) -> dict:
    """What the answer got right, by string and integer comparison only."""
    header = re.search(r"catalog_calls=(\d+)", body)
    answer = answer_of(body)
    cols = truth["columns"].split(",")
    n = re.escape(truth["rows"])
    return {
        "correct_row_count": bool(re.search(
            r"(?<![\w.-])%s(?![\w.-])[^\n]{0,40}?\brows?\b|\brows?\b[^\n]{0,40}?(?<![\w.-])%s(?![\w.-])"
            % (n, n), answer, re.I)),
        "cites_snapshot": truth["snapshot_id"] in answer,
        "cites_metadata": truth["metadata_location"] in answer,
        "names_all_columns": all(word(c, answer) for c in cols),
        # A column the fixture does not have. OneLake's table has no `region`,
        # so naming it there is an invention rather than a reading.
        "invented_column": word("region", answer) and ("region" not in cols),
        "catalog_calls": int(header.group(1)) if header else None,
    }


def one_run(axis: str, leg: str, catalog: str, index: int, model: str = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ICEBERG_MODEL")}
    env["ICEBERG_CATALOG"] = catalog
    if model:
        env["ICEBERG_MODEL_" + leg.upper()] = model
    started = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "run_once.py"), leg, QUESTION,
         "--catalog", catalog],
        capture_output=True, text=True, cwd=HERE, env=env, timeout=900)
    elapsed = round(time.time() - started, 1)
    body = proc.stdout + proc.stderr
    # The axis is in the name because both axes run gcp on the control. Without
    # it Axis B's captures overwrote Axis A's, and three published rows were left
    # with no capture behind them (found 2026-09-14).
    cell = leg if not model else "%s__%s" % (leg, re.sub(r"[^\w.-]", "-", model))
    path = os.path.join(RAW, "matrix", "%s__%s__%s__%d.txt" % (axis, cell, catalog, index))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("# axis=%s leg=%s catalog=%s run=%d elapsed_s=%s captured=%s\n\n"
                     % (axis, leg, catalog, index, elapsed,
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        handle.write(body)
    timing = re.search(r"agent seconds: ([\d.]+) \| tool seconds: ([\d.]+)", body)
    return {"leg": leg, "catalog": catalog, "run": index, "scorer": SCORER_VERSION,
            **({"model": model} if model else {}),
            "elapsed_s": elapsed, "capture": os.path.basename(path), "body": body,
            "agent_s": float(timing.group(1)) if timing else None,
            "tool_s": float(timing.group(2)) if timing else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["A", "B", "C"], required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--leg", default=AXIS_B_LEG)
    args = ap.parse_args()

    truth = ground_truth()
    if args.axis == "A":
        cells = [(leg, AXIS_A_CATALOG, None) for leg in LEGS]
    elif args.axis == "B":
        cells = [(args.leg, cat, None) for cat in CATALOGS]
    else:
        cells = [(leg, AXIS_A_CATALOG, model) for leg, model in AXIS_C_CELLS]

    results = []
    for leg, catalog, model in cells:
        for index in range(1, args.repeat + 1):
            row = one_run(args.axis, leg, catalog, index, model)
            row.update(score(row.pop("body"), truth[catalog]))
            results.append(row)
            print("  %-6s %-26s %-19s run %d  %5ss  agent=%ss tool=%ss  count=%s snap=%s meta=%s cols=%s calls=%s"
                  % (leg, model or "", catalog, index, row["elapsed_s"], row["agent_s"], row["tool_s"],
                     "ok" if row["correct_row_count"] else "NO",
                     "ok" if row["cites_snapshot"] else "NO",
                     "ok" if row["cites_metadata"] else "NO",
                     "ok" if row["names_all_columns"] else "NO",
                     row["catalog_calls"]), flush=True)

    out = os.path.join(RAW, "matrix-axis-%s.json" % args.axis)
    with open(out, "w") as handle:
        json.dump({"axis": args.axis, "question": QUESTION,
                   "repeat": args.repeat, "results": results}, handle, indent=2)
    print("\nwrote %s (%d runs)" % (out, len(results)))


if __name__ == "__main__":
    main()
