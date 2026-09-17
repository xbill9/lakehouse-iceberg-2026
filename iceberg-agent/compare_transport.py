#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One leg, one question, both tool transports: imported, and over MCP.

    python3 compare_transport.py --leg aws --repeat 3

Everything is held still except how the agent reaches its tools. Same framework,
same model, same instruction, same four tools, same catalog, same question. The
tools are the same Python objects either way -- `agent.py` imports them,
`agent_mcp.py` reaches the module that holds them through a server process.

So a difference between the two columns is a difference the transport made, and
a null result is worth as much as any other: if the answers and the tool calls
match, then MCP costs the code around the agent (measured in
evidence/mcp-per-framework.txt) and costs the behaviour nothing.

Graded against the same ground truth paper 3 used, by the same comparison: the
row count beside its noun, every column named, and the version cited.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "iceberg-conformance"))

QUESTIONS = {
    "metadata": ("How many rows are in the probe table, and what columns does it "
                 "have? Cite the exact table version you read."),
    "scan": ("What is the largest id in the probe table, and how many of its "
             "rows have an id of 10 or more? Cite the exact table version you read."),
}

#: The probe table on the control catalog, read from the catalog by
#: iceberg-mcp-hosts/ground_truth.py rather than restated here.
TRUTH = os.path.join(os.path.dirname(HERE), "iceberg-mcp-hosts", "evidence",
                     "ground-truth-apache-polaris.txt")


def truth():
    out = {}
    with open(TRUTH) as handle:
        for line in handle:
            if line.startswith("  ") and "=" in line:
                k, v = line.strip().split("=", 1)
                out[k] = v
    return out


def states(number, noun, text):
    """The number beside its noun, the pairing paper 3 and paper 4 both use."""
    n = re.escape(str(number))
    flat = re.sub(r"(?:file|s3a?|gs|abfss?)://?\S+|\b\d{12,}\b", " ", text)
    flat = re.sub(r"[`*_]", "", flat)
    flat = re.sub(r"(?<=\d)[,   ](?=\d{3}(?!\d))", "", flat)
    return bool(re.search(
        r"(?<![\w.-])%s(?![\w-]|\.\d)[^\n]{0,90}?\b%ss?\b|"
        r"\b%ss?\b[^\n]{0,90}?(?<![\w.-])%s(?![\w-]|\.\d)" % (n, noun, noun, n),
        flat, re.I))


def score(kind, body, t):
    cols = t["columns"].split(",")
    s = {"cites_version": t["snapshot_id"] in body or t["metadata_location"] in body}
    if kind == "metadata":
        s["correct_row_count"] = states(t["rows"], "row", body)
        s["names_all_columns"] = all(
            re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(c), body) for c in cols)
    else:
        low, _, high = (t.get("range_id") or "|").partition("|")
        s["correct_largest_id"] = bool(re.search(
            r"(?<![\w.-])%s(?![\w-]|\.\d)" % re.escape(high), body)) if high else None
        # 8 of the 11 ids are 10 or more; the count is computed here, not recalled.
        s["correct_filtered_count"] = states(8, "row", body)
    return s


#: paper 3's legs import the conformance harness's auth module, and its README
#: sets these before running. Both transports get the identical environment, so
#: neither is advantaged by how it was launched.
CONFORMANCE = os.path.join(os.path.dirname(HERE), "iceberg-conformance")


def leg_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = CONFORMANCE + os.pathsep + env.get("PYTHONPATH", "")
    # Set, not setdefault. The default is the relative name "catalogs.yaml",
    # which resolves against the working directory, and an inherited relative
    # value made one run read a path that was not there while its neighbours
    # read the catalog. Absolute, and identical for both transports.
    env["ICEBERG_CATALOGS_FILE"] = os.path.join(CONFORMANCE, "catalogs.yaml")
    return env


def run_imported(leg, question, catalog):
    """paper 3's path: run_once.py, tools imported into the agent process."""
    started = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "run_once.py"), leg, question,
         "--catalog", catalog],
        capture_output=True, text=True, cwd=HERE, timeout=600, env=leg_env())
    return (proc.stdout or "") + (proc.stderr or ""), round(time.time() - started, 1)


def run_mcp(leg, question, catalog):
    """this paper's path: run_mcp.py, tools reached over stdio JSON-RPC."""
    started = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "run_mcp.py"), "--cloud", leg,
         "--question", question, "--catalog", catalog],
        capture_output=True, text=True, cwd=HERE, timeout=600, env=leg_env())
    return (proc.stdout or "") + (proc.stderr or ""), round(time.time() - started, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leg", default="aws")
    ap.add_argument("--catalog", default="apache-polaris")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--question", choices=sorted(QUESTIONS), action="append")
    a = ap.parse_args()
    kinds = a.question or sorted(QUESTIONS)
    t = truth()

    rows = []
    for kind in kinds:
        for transport, fn in (("imported", run_imported), ("mcp", run_mcp)):
            for index in range(1, a.repeat + 1):
                body, elapsed = fn(a.leg, QUESTIONS[kind], a.catalog)
                row = {"leg": a.leg, "question": kind, "transport": transport,
                       "run": index, "elapsed_s": elapsed}
                if elapsed < 1.0 or "Traceback" in body or "CATALOG ERROR" in body:
                    # A leg that died in under a second did not answer badly, it
                    # did not answer. Scoring it would put a launch failure in
                    # the results table as a property of the transport.
                    row["failed"] = body.strip().splitlines()[-1][:90] if body.strip() else "no output"
                else:
                    row.update(score(kind, body, t))
                row["chars"] = len(body)
                rows.append(row)
                fields = " ".join(
                    "%s=%s" % (k.replace("correct_", "").replace("names_", "")[:9], v)
                    for k, v in row.items()
                    if k not in ("leg", "question", "transport", "run", "elapsed_s", "chars"))
                print("%-6s %-9s %-9s r%d %6.1fs  %s"
                      % (a.leg, kind, transport, index, elapsed, fields), flush=True)

    out = os.path.join(HERE, "evidence", "transport-%s.json" % a.leg)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as handle:
        json.dump({"leg": a.leg, "catalog": a.catalog, "results": rows}, handle, indent=2)
    print("\nwrote %s (%d rows)" % (out, len(rows)))


if __name__ == "__main__":
    main()
