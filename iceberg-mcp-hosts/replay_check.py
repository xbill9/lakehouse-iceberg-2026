#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Did the figure in this answer ever come back from a tool?

    python3 replay_check.py --question Q4

The first version of this check asked whether the tools *could* have produced
the answer -- count_rows called, or a scan on a table small enough to be
COMPLETE. That is a statement about the tool list, not about the run, and in
three of the four configurations it was true in every single run, so those cells
could only ever report zero. A control that cannot produce a positive is not a
control.

This asks the question the other way round, from the record rather than from the
capability: replay the calls the run actually made, with the arguments the trace
recorded, against the same server variant, and look for the reported figure in
what came back. It can fire in any cell, including the ones where the tools were
perfectly capable of answering -- which is what makes a zero there worth
something.

Replay is sound here because every tool is a read and both tables are frozen:
the snapshot ids the runs cited are the snapshot ids still current, and that is
asserted rather than assumed before anything is compared.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "servers"))

import run_matrix as R                        # noqa: E402
from servers import SERVERS                   # noqa: E402

TRACES = os.path.join(R.EVIDENCE, "traces")


def calls_of(label):
    """The tools/call frames of one run, in order, with their arguments."""
    path = os.path.join(TRACES, label + ".jsonl")
    if not os.path.exists(path):
        return None
    out = []
    with open(path) as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("method") == "tools/call" and rec.get("name"):
                out.append((rec["name"], rec.get("args") or {}))
    return out


def replay(server, calls):
    """Run those calls against the server again; return everything it said."""
    if not calls:
        return ""
    env = dict(os.environ)
    env.update(server["spec"].get("env") or {})
    # The spec is wrapped in the trace proxy for the live run; replaying through
    # it would append to the trace being read. Talk to the server directly.
    cmd = [sys.executable, os.path.join(HERE, "servers", "iceberg_mcp.py")]
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "replay", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    for i, (name, args) in enumerate(calls):
        msgs.append({"jsonrpc": "2.0", "id": 10 + i, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    out, _ = proc.communicate("".join(json.dumps(m) + "\n" for m in msgs), timeout=600)
    said = []
    for line in out.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for part in (rec.get("result") or {}).get("content") or []:
            said.append(part.get("text", ""))
    return "\n".join(said)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", default="Q4")
    ap.add_argument("--axis", default="A")
    a = ap.parse_args()

    grid, detail = {}, []
    for host in ("claude", "agy"):
        for table in ("probe_table", "probe_large"):
            path = os.path.join(R.EVIDENCE, "matrix-axis-%s-%s-%s.json"
                                % (a.axis, host, table))
            results = json.load(open(path))["results"]
            truth = R.ground_truth("apache-polaris", table)
            for row in results:
                if row["question"] != a.question:
                    continue
                server = SERVERS[row["server"]]
                # The replay is only sound while the table has not moved.
                if truth["snapshot_id"] != str(row["graded_against"]):
                    sys.exit("snapshot moved since the run: %s vs %s"
                             % (truth["snapshot_id"], row["graded_against"]))
                label = "%s__%s__%s__%s__%d" % (host, row["server"], table,
                                                a.question, row["run"])
                calls = calls_of(label)
                if calls is None:
                    sys.exit("no trace for %s" % label)
                said = replay(server, calls)
                # Did the figure this answer reported ever come back from a tool?
                from_tools = R.states_count(truth["rows"], said) or \
                    R.for_pairing(said).find(str(truth["rows"])) >= 0
                stated = bool(row["correct_row_count"])
                outside = stated and not from_tools
                key = (table, row["server"])
                grid.setdefault(key, {"n": 0, "outside": 0, "stated": 0,
                                      "from_tools": 0})
                grid[key]["n"] += 1
                grid[key]["stated"] += stated
                grid[key]["from_tools"] += bool(from_tools)
                grid[key]["outside"] += outside
                detail.append((table, row["server"], host, row["run"], len(calls),
                               stated, bool(from_tools), outside))

    print("%s: did the reported count come back from a tool in that run?\n" % a.question)
    print("%-12s %-12s %-6s %-9s %-11s %s"
          % ("table", "variant", "runs", "stated it", "tool said it", "from outside"))
    print("-" * 70)
    for key in sorted(grid):
        g = grid[key]
        print("%-12s %-12s %-6d %-9d %-11d %d" % (key[0], key[1], g["n"],
                                                  g["stated"], g["from_tools"],
                                                  g["outside"]))
    print("\nper run")
    print("%-12s %-12s %-7s %-4s %-7s %-8s %-13s %s"
          % ("table", "variant", "host", "run", "calls", "stated", "tool said it",
             "outside"))
    print("-" * 82)
    for d in sorted(detail):
        print("%-12s %-12s %-7s %-4d %-7d %-8s %-13s %s" % d)


if __name__ == "__main__":
    main()
