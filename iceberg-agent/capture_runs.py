#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask each leg the matrix question once, against its own cloud's catalog.

These are the single-leg captures the article quotes -- each leg reading the
catalog it would read in a real deployment, which the matrix does not do for the
AWS and Azure legs. Each is checked against ground truth by the same scorer the
matrix uses, plus the stamped header.

    python3 capture_runs.py

Writes run-<leg>.txt and verification.txt into the raw evidence directory.
"""
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
from run_matrix import LEGS, QUESTION, RAW, ground_truth, score  # noqa: E402


def main() -> None:
    truth = ground_truth()
    env = dict(os.environ)
    # run_once reads ICEBERG_CATALOG before its own default, so a value left in
    # the shell would silently point a leg at some other cloud's catalog.
    env.pop("ICEBERG_CATALOG", None)
    os.makedirs(RAW, exist_ok=True)

    report, all_ok = [], True
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for leg in LEGS:
        catalog = common.DEFAULT_CATALOG[leg]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        proc = subprocess.run([sys.executable, os.path.join(HERE, "run_once.py"), leg, QUESTION],
                              capture_output=True, text=True, cwd=HERE, env=env, timeout=900)
        body = proc.stdout + proc.stderr
        with open(os.path.join(RAW, "run-%s.txt" % leg), "w") as handle:
            handle.write("# captured %s by run_once.py on this machine\n"
                         "# command: python3 run_once.py %s \"%s\"\n\n" % (stamp, leg, QUESTION))
            handle.write(body)

        t = truth[catalog]
        s = score(body, t)
        head = re.search(r"<!-- cloud=(\S+) model=(\S+) catalog=(\S+) instruction=v(\d+) "
                         r"catalog_calls=(\d+) -->", body)
        checks = [
            ("row count %s present" % t["rows"], s["correct_row_count"]),
            ("snapshot id cited", s["cites_snapshot"]),
            ("metadata location cited", s["cites_metadata"]),
            ("all columns named", s["names_all_columns"]),
            ("no column invented", not s["invented_column"]),
            ("catalog in header matches", bool(head) and head.group(3) == catalog),
            ("instruction v2", bool(head) and head.group(4) == "2"),
            ("catalog_calls == 3", s["catalog_calls"] == 3),
        ]
        report.append("%-6s model=%s catalog=%s" % (leg, head.group(2) if head else "?", catalog))
        for name, passed in checks:
            report.append("   %-28s %s" % (name, "ok" if passed else "FAIL"))
            all_ok = all_ok and passed
        report.append("")
        print("\n".join(report[-10:]), flush=True)

    report.append("ALL CHECKS PASS" if all_ok else "CHECKS FAILED")
    with open(os.path.join(RAW, "verification.txt"), "w") as handle:
        handle.write("# verification captured %s, comparing each agent answer against "
                     "ground-truth.txt\n# every check is a string or integer comparison, "
                     "not a reading\n\n" % now)
        handle.write("\n".join(report) + "\n")
    print(report[-1])
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
