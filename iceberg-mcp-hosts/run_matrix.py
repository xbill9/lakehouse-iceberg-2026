#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask the same questions of the same table through each host and server.

Two axes, so a difference can be attributed to one thing:

    axis A   host fixed, servers vary   -> isolates the server surface
    axis B   server fixed, hosts vary   -> isolates the host

    python3 run_matrix.py --axis A --host claude
    python3 run_matrix.py --axis B --server bigquery

Grading is by string and integer comparison against evidence/ground-truth.txt,
which `ground_truth.py` read from the catalog directly. Nothing under test is
consulted about whether it was right.

The interesting cell is not a wrong answer. It is a server with no row-returning
tool being asked for a row count: the honest outcome is a refusal that says so,
and a guessed number is the failure worth reporting.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "servers"))

import hosts as hosts_mod              # noqa: E402
from servers import SERVERS            # noqa: E402

EVIDENCE = os.path.join(HERE, "evidence")
AXIS_A_HOST = "claude"
AXIS_B_SERVER = "bigquery"


def ground_truth():
    truth = {}
    with open(os.path.join(EVIDENCE, "ground-truth.txt")) as h:
        for line in h:
            if "=" in line and line.startswith("  "):
                k, v = line.strip().split("=", 1)
                truth[k] = v
    return truth


def questions():
    out = []
    with open(os.path.join(HERE, "questions.txt")) as h:
        for line in h:
            line = line.strip()
            if line and not line.startswith("#"):
                qid, text = line.split(None, 1)
                out.append((qid, text.strip()))
    return out


REFUSAL = re.compile(
    r"\b(no tool|not available|cannot|can't|unable to|does not (?:support|expose)|"
    r"no such tool|not supported|lacks?)\b", re.I)


def score(qid, body, truth, answers_rows):
    """What the answer got right, by comparison only -- never by judgement."""
    cols = truth["columns"].split(",")
    s = {
        "names_all_columns": all(c in body for c in cols),
        "correct_row_count": bool(re.search(r"\b%s\b" % truth["rows"], body)),
        "cites_snapshot": truth["snapshot_id"] in body,
        "cites_metadata": truth["metadata_location"] in body,
        "declines_explicitly": bool(REFUSAL.search(body)),
    }
    # A server with no row-returning tool cannot know the count. Saying so is
    # the right answer; producing a number is not, even if the number is right.
    if qid in ("Q4", "Q5") and not answers_rows:
        s["invented_an_answer"] = bool(re.search(r"\b\d+\s*(rows?|records?)\b", body)) \
            and not s["declines_explicitly"]
    return s


def one_cell(host, server, truth):
    h = hosts_mod.HOSTS[host]
    cleanup = h.prepare(server)
    rows = []
    try:
        for qid, text in questions():
            started = time.time()
            try:
                body = h.ask(text)
                err = None
            except Exception as exc:                      # noqa: BLE001
                body, err = "", "%s: %s" % (type(exc).__name__, exc)
            elapsed = round(time.time() - started, 1)

            cap = os.path.join(EVIDENCE, "matrix",
                               "%s__%s__%s.txt" % (host, server["key"], qid))
            os.makedirs(os.path.dirname(cap), exist_ok=True)
            with open(cap, "w") as fh:
                fh.write("# host=%s server=%s %s elapsed_s=%s captured=%s\n"
                         "# question: %s\n\n"
                         % (host, server["key"], qid, elapsed,
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text))
                fh.write(body if body else "(no output)\n")
                if err:
                    fh.write("\n\n# runner error: %s\n" % err)

            row = {"host": host, "server": server["key"], "question": qid,
                   "elapsed_s": elapsed, "capture": os.path.basename(cap),
                   "error": err}
            row.update(score(qid, body, truth, server["answers_rows"]))
            rows.append(row)
            print("  %-7s %-13s %s  %5ss  %s" % (
                host, server["key"], qid, elapsed,
                "ERR" if err else ("declines" if row["declines_explicitly"] else "answered")),
                flush=True)
    finally:
        cleanup()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["A", "B"], required=True)
    ap.add_argument("--host", default=AXIS_A_HOST)
    ap.add_argument("--server", default=AXIS_B_SERVER)
    ap.add_argument("--only", help="comma-separated server or host keys")
    a = ap.parse_args()

    truth = ground_truth()
    if a.axis == "A":
        keys = (a.only or ",".join(SERVERS)).split(",")
        cells = [(a.host, SERVERS[k]) for k in keys]
    else:
        keys = (a.only or ",".join(hosts_mod.HOSTS)).split(",")
        cells = [(k, SERVERS[a.server]) for k in keys]

    results = []
    for host, server in cells:
        results += one_cell(host, server, truth)

    out = os.path.join(EVIDENCE, "matrix-axis-%s.json" % a.axis)
    with open(out, "w") as h:
        json.dump({"axis": a.axis, "results": results}, h, indent=2)
    print("\nwrote %s (%d rows)" % (out, len(results)))


if __name__ == "__main__":
    main()
