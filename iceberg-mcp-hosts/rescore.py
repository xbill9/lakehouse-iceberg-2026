#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-grade a finished matrix from its captures, without asking a host anything.

    python3 rescore.py --axis A --host claude --host agy

A scorer improves more often than a matrix is worth re-running: v4 added the
fields for Q1, Q2, Q5 and Q6, which had no truth to be graded against and so
scored 0 in every row of two matrices for want of a check rather than for want
of an answer. Re-running 72 cells to fix that would have cost an hour and a
model bill, and would have changed the answers being graded, which is the one
thing a scoring fix must not do.

So the answers are read back from `evidence/matrix/*.txt` exactly as the host
produced them, and the tool calls from `evidence/traces/*.jsonl`, and everything
is recomputed. The captures are the record; the JSON is a view of it.

**The guard that makes this safe.** A rescore is only trustworthy if it agrees
with the original run wherever the scorer did not change. Every field the old
JSON already carried is compared against the new one, and any disagreement
outside the fields this version is meant to change is reported as a FAILURE
rather than quietly written -- because a rescore that silently rewrites history
is indistinguishable from one that fixes it.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "servers"))

import run_matrix as R                       # noqa: E402
from servers import SERVERS                  # noqa: E402

#: Fields v4 is meant to change. Anything else that moves is a bug in the
#: rescore, not an improvement in the scorer.
EXPECTED_TO_CHANGE = {
    "names_namespaces", "names_table", "correct_ts_range", "cites_version",
    "answered_correctly", "engine_aggregate", "fetched_rows",
    "model_did_arithmetic",
    # v7: spelled-out counts ("One namespace") now count, which moves this
    # field on rows a digit-only check had scored wrong.
    "correct_namespace_count", "correct_snapshot_count",
    "reports_namespace_absent", "invented_a_table",
    # v9-v11: grouped digits now count, and the claims/decline fields are new.
    "correct_row_count", "declines_to_count", "row_count_claims",
}


def read_capture(path):
    """Header fields and the answer body, as written by run_matrix.one_cell."""
    with open(path) as handle:
        text = handle.read()
    head, _, body = text.partition("\n\n")
    meta = {}
    for line in head.splitlines():
        if line.startswith("# ") and "=" in line:
            for part in line[2:].split():
                if "=" in part:
                    key, value = part.split("=", 1)
                    meta[key] = value
    return meta, body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", default="A")
    ap.add_argument("--host", action="append", dest="hosts", required=True)
    ap.add_argument("--table", default="probe_table")
    ap.add_argument("--write", action="store_true",
                    help="write the new JSON; without it, report only")
    a = ap.parse_args()

    failures = []
    for host in a.hosts:
        old_path = os.path.join(R.EVIDENCE, "matrix-axis-%s-%s-%s.json"
                                % (a.axis, host, a.table))
        old = json.load(open(old_path))
        was = {(r["server"], r["question"], r["run"]): r for r in old["results"]}

        rows, changed = [], {}
        for key in sorted(was):
            server_key, qid, index = key
            server = SERVERS[server_key]
            truth = R.ground_truth(server["catalog"], a.table)
            label = "%s__%s__%s__%s__%d" % (host, server_key, a.table, qid, index)
            cap = os.path.join(R.EVIDENCE, "matrix", label + ".txt")
            if not os.path.exists(cap):
                failures.append("missing capture: %s" % label)
                continue
            meta, body = read_capture(cap)

            prior = was[key]
            row = {"host": host, "server": server_key, "question": qid, "run": index,
                   "table": a.table,
                   "model": prior.get("model"), "catalog": server["catalog"],
                   "graded_against": truth.get("snapshot_id"),
                   "elapsed_s": float(meta.get("elapsed_s", prior["elapsed_s"])),
                   "capture": os.path.basename(cap), "error": prior.get("error"),
                   "traced": prior.get("traced")}
            trace = R.read_trace(label) if server.get("traced") else None
            if trace:
                row.update(trace)
                row["answered_without_tools"] = (
                    not trace["tool_calls"] and len(body.strip()) > 80
                    and not R.REFUSAL.search(body))
                if qid in ("Q4", "Q5"):
                    row["model_did_arithmetic"] = (
                        trace["fetched_rows"] and not trace["engine_aggregate"]
                        and bool(R.re.search(r"\d", body)))
            row.update(R.score(qid, body, truth, server))
            rows.append(row)

            for field, before in prior.items():
                if field in EXPECTED_TO_CHANGE or field not in row:
                    continue
                if row[field] != before:
                    changed.setdefault(field, []).append(label)

        print("%-7s %d rows rescored at scorer v%d (was v%s)"
              % (host, len(rows), R.SCORER_VERSION, old.get("scorer")))
        if changed:
            for field, labels in sorted(changed.items()):
                failures.append("%s: %s changed in %d rows, e.g. %s"
                                % (host, field, len(labels), labels[0]))
        else:
            print("         every unchanged field agrees with the original run")

        if a.write and not failures:
            out = dict(old)
            out["scorer"] = R.SCORER_VERSION
            out["rescored_from"] = "evidence/matrix/*.txt"
            out["results"] = rows
            with open(old_path, "w") as handle:
                json.dump(out, handle, indent=2)
            print("         wrote %s" % old_path)

    if failures:
        raise SystemExit("\nRESCORE REFUSED -- fields moved that should not have:\n  "
                         + "\n  ".join(failures))


if __name__ == "__main__":
    main()
