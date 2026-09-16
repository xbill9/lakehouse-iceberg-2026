#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn raw paper 3 evidence into the published copy: re-score, summarise, anonymise.

No run writes to ``papers/iceberg-agent-three-clouds/evidence/``. Runs write to
the gitignored raw directory, which holds real account identifiers, and this is
the only path from there into the repo. It

  1. re-scores every matrix capture from its own body against ground truth, and
     refuses if that disagrees with what the runner stored, or if any run has no
     stamped header -- a leg that died before answering is not a result;
  2. writes matrix-summary.txt and derived-figures.txt from the re-scored rows,
     so no figure in the article is typed by hand;
  3. publishes a superseded run, when one is archived, rather than letting it
     disappear;
  4. maps account identifiers to stable pseudonyms with the conformance
     anonymiser's patterns plus every literal in .known-identifiers, and refuses
     if the residual scan or a literal grep finds anything.

MEASURED 2026-09-14: the first matrix wrote captures as leg__catalog__run, so
Axis B's gcp-on-Polaris runs overwrote Axis A's and three published Axis A rows
had no capture behind them. Step 1 would have refused that evidence.

    python3 publish_evidence.py
"""
import json
import os
import re
import shutil
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))

import anonymize_evidence as anon  # noqa: E402
from run_matrix import (AXIS_A_CATALOG, AXIS_B_LEG, FRAMEWORK, LEGS, RAW,  # noqa: E402
                        SCAN_QUESTION, SCORER_VERSION, answer_of, ground_truth, score, score_scan,
                        token_fields)

#: Fields whose score moved because a run was recorded under an older scorer.
#: Disclosed in matrix-summary.txt rather than refused: the capture is the
#: evidence, and re-scoring it with a stricter check is the point.
SCORER_CHANGES = []

DEST = os.path.join(ROOT, "papers", "iceberg-agent-three-clouds", "evidence")
#: Archived complete runs, oldest first. Each is published under
#: superseded-runs/<name>/ and re-scored by the same checks; none was replaced
#: to change a result. `timed` says whether its answers carry the timing line.
SUPERSEDED = [
    ("run1-uninstrumented", False, [
        "# a complete matrix run captured earlier on 2026-09-14, SUPERSEDED and kept.",
        "# It was run before the tools recorded where an answer's time went. Two of its",
        "# Axis B runs were far slower than the rest (google-lakehouse run 3, onelake",
        "# run 2) with nothing in their captures to attribute the time to, so both axes",
        "# were re-run, instrumented. It was not re-run to change a result."]),
    ("run2-instrumented", True, [
        "# a complete instrumented matrix run captured earlier on 2026-09-14, SUPERSEDED",
        "# and kept. The article originally reported it. The whole pipeline was then run",
        "# again from ground truth onwards, to check that the result replicates rather",
        "# than to change one; the replication is in derived-figures.txt."]),
    ("run3-three-repeats", True, [
        "# a complete run at three repeats per cell, captured 2026-09-15, SUPERSEDED and",
        "# kept. It timed sign-in inside each answer and ran cells in blocks; the",
        "# published run warms each process first and runs cells in shuffled rounds,",
        "# ten repeats per cell."]),
    ("run4-ten-repeats", True, [
        "# a complete run at ten repeats per cell, captured 2026-09-15, SUPERSEDED and",
        "# kept. It did not record tokens or model calls, and had no Axis E; the",
        "# published run records both and runs Axis E alongside."]),
    ("run6-sample-note-no-filter", True, [
        "# a complete run at ten repeats per cell, Axes A to E, captured 2026-09-15,",
        "# SUPERSEDED and kept. Its scan tool added a SAMPLE note whenever a model asked",
        "# for more than 100 rows, beside the COMPLETE line of an 11-row table, and had",
        "# no filter, so a filtered count was arithmetic the model did in its head.",
        "# Nova Micro, given the agent's instruction and every row, gave the count right",
        "# in 1 of 20 direct calls.",
        "# The Strands runner also scored only the last assistant message, where ADK's",
        "# and Agent Framework's runners took every message of the turn; Nova named the",
        "# columns in an earlier message. The scan now filters in the engine and returns",
        "# an exact COUNT, MIN and MAX, the Strands runner takes the whole turn, Nova runs",
        "# with Amazon's documented tool-use decoding, and every axis was re-run.",
        "# nova-diagnosis.txt has the measurements. Re-scored below, not changed."]),
]
#: Archived single-axis runs, published under superseded-runs/<name>/ with their
#: re-scored rows. Kept for the same reason as the complete runs above.
SUPERSEDED_D = [
    ("run10-thinking-in-answers", [
        "# Axes A, C, D, E and F, captured 2026-09-15, SUPERSEDED and kept. Their answers",
        "# carry Nova Micro's <thinking> text, because the runner returned model output as",
        "# it arrived: 130 of them, 9 stating a count or largest id the visible answer never",
        "# showed, 113 echoing the agent's own call budget back to the caller. run_once.py",
        "# now strips <thinking> on every leg, so a published capture is the text a caller",
        "# receives, and every axis was re-run. Scores are unchanged -- the scorer always",
        "# read the answer with those blocks removed. nova-diagnosis.txt counts them here."]),
    ("run9-rows-only-keep-limit-small", [
        "# Axis E at ten repeats per cell, captured 2026-09-15, SUPERSEDED and kept. Its",
        "# rows-only cells used the v1 scan with its own docstring, which tells the model",
        "# to keep the limit small, so a rows-only run could fail by reading part of the",
        "# table rather than by miscounting: over 30 Nova Micro runs in that configuration",
        "# 8 never saw every row. rows-only now carries the neutral limit wording, so the",
        "# only difference from the published scan is who counts. Re-scored below."]),
    ("run8-greedy-single-sample", [
        "# Axis E at ten repeats per cell, captured 2026-09-15, SUPERSEDED and kept. Nova",
        "# Micro's greedy cells returned one identical answer in all ten runs, so each was",
        "# a single sample repeated, and the only rows-only Nova cell was greedy. Axis E",
        "# was re-run with a rows-only Nova cell at Bedrock's default decoding, and the",
        "# distinct answers per cell are now published. Re-scored below, not changed."]),
    ("run7-untraced-no-variants", [
        "# Axes D and E at ten repeats per cell, captured 2026-09-15, SUPERSEDED and kept.",
        "# Same harness as the published run, but the captures did not record tool calls,",
        "# so which filter each agent used was on record only for ADK, and Axis E had no",
        "# rows-only or Nova default-decoding cells. Both axes were re-run with tool traces",
        "# and those cells, and scored with scorer v7. Re-scored below, not changed."]),
    ("run6-sample-note-no-filter", [
        "# Axes D and E at ten repeats per cell, captured 2026-09-15, SUPERSEDED and kept",
        "# beside the same run's Axes A to C; why is under that run above."]),
    ("run5-strands-str-join", [
        "# Axes C and E, captured 2026-09-15, SUPERSEDED and kept. The harness read",
        "# Strands answers with str(AgentResult), which puts a line break after every",
        "# text block; Strands' Gemini provider returns some answers as several blocks,",
        "# so a line break could land inside a word or number -- one of them inside the",
        "# largest id. The count below is generated from the captures. The harness now",
        "# joins the text blocks directly and both axes were re-run. Re-scored below,",
        "# not changed."]),
    ("run4-ten-repeats", [
        "# Axis D at ten repeats per cell, captured 2026-09-15, SUPERSEDED and kept",
        "# beside the ten-repeat run of Axes A to C."]),
    ("run3-three-repeats", [
        "# Axis D at three repeats per cell, captured 2026-09-15, SUPERSEDED and kept",
        "# beside the three-repeat run of Axes A and B."]),
    ("axis-d-run1-instruction-v2", [
        "# Axis D's first run, captured 2026-09-15, SUPERSEDED and kept.",
        "# Instruction v2 told every agent that iceberg_scan_table returns a sample and",
        "# must never be counted, and the scan tool never said when it had returned the",
        "# whole table. Two of three ADK runs declined to scan at all, and every answer",
        "# that did scan hedged 'based on a sample', although each scan had returned",
        "# every row. That is this harness's wording, not a framework's behaviour, so",
        "# the instruction (v3) and the scan tool's output were changed and the axis was",
        "# re-run. Re-scored below under the current scorer, not changed."]),
]
COPIED = ["ground-truth.txt", "environment.txt", "failure-modes.txt", "verification.txt",
          "run-gcp.txt", "run-aws.txt", "run-azure.txt", "import-times.txt",
          "credential-times.txt", "related-work.txt", "nova-diagnosis.txt"]
TIMING = re.compile(r"agent seconds: ([\d.]+) \| tool seconds: ([\d.]+)")
#: Hostnames that are the evidence rather than an account. The blob host is the
#: one PyArrow builds for OneLake and which does not exist -- masking it would
#: remove the finding.
anon.KEEP_HOSTS |= {"onelake.blob.core.windows.net", "onelake.dfs.fabric.microsoft.com"}
#: Public documentation and research hosts cited in related-work.txt. They carry
#: no account, and masking them turns the source list into catalog-host-NNNN.
anon.KEEP_HOSTS |= {"launchdarkly.com", "arxiv.org", "github.com", "iceberglakehouse.com",
                    "aws.amazon.com", "iceberg.apache.org", "py.iceberg.apache.org",
                    "polaris.apache.org", "docs.aws.amazon.com"}


def rescore(base: str, axis: str, truth: dict, timed: bool) -> tuple:
    with open(os.path.join(base, "matrix-axis-%s.json" % axis)) as handle:
        data = json.load(handle)
    rows, problems, bodies = [], [], {}
    for stored in data["results"]:
        with open(os.path.join(base, "matrix", stored["capture"])) as handle:
            body = handle.read()
        bodies[stored["capture"]] = body
        fresh = (score_scan if axis in "DE" else score)(body, truth[stored["catalog"]])
        answered = fresh["catalog_calls"] is not None
        older = stored.get("scorer", 1) != SCORER_VERSION
        for key, value in fresh.items():
            if stored.get(key) != value:
                line = ("%s: %s stored %r, re-scored %r"
                        % (stored["capture"], key, stored.get(key), value))
                (SCORER_CHANGES if older and key != "catalog_calls" else problems).append(
                    "%s (%s)" % (line, os.path.basename(base)))
        elapsed = float(re.search(r"elapsed_s=([\d.]+)", body).group(1))
        if elapsed != stored["elapsed_s"]:
            problems.append("%s: elapsed stored %s, capture says %s"
                            % (stored["capture"], stored["elapsed_s"], elapsed))
        timing = TIMING.search(body)
        agent_s, tool_s = (float(timing.group(1)), float(timing.group(2))) if timing else (None, None)
        if timed and answered and (agent_s is None or agent_s != stored.get("agent_s")
                                   or tool_s != stored.get("tool_s")):
            problems.append("%s: timing line missing or disagrees with the runner"
                            % stored["capture"])
        model = re.search(r"<!-- cloud=\S+ model=(\S+)", body)
        model = model.group(1) if model else "?"
        if stored.get("model") and stored["model"] != model:
            problems.append("%s: runner asked for %s, answer header says %s"
                            % (stored["capture"], stored["model"], model))
        rows.append(dict(stored, **fresh, agent_s=agent_s, tool_s=tool_s, model=model,
                         answered=answered, **token_fields(body),
                         cell="%s / %s%s%s" % (FRAMEWORK[stored["leg"]], model,
                                                " on %s" % stored["catalog"] if axis in "DE" else "",
                                                " [%s]" % stored["variant"] if stored.get("variant") else "")))
    return data, rows, problems, bodies


def secs(row: dict) -> float:
    """Answer seconds: question in, answer out, after imports and agent
    construction. MEASURED 2026-09-15: importing the frameworks alone takes 0.78s
    for ADK, 0.45s for Strands and 0.24s for Agent Framework, and process time
    carried that into every published latency. A run recorded before answers were
    timed (the first superseded run) falls back to process time, and every figure
    that includes one says so."""
    return row["agent_s"] if row.get("agent_s") is not None else row["elapsed_s"]


def timed_label(rows: list) -> str:
    return "" if all(r.get("agent_s") is not None for r in rows) else "  [PROCESS time: no answer time recorded]"


def answered(rows: list) -> list:
    """Runs that produced an answer. Timing is taken over these only; runs that
    did not answer are counted and shown, never dropped silently or retried."""
    return [r for r in rows if r.get("answered", True)]


def quartiles(values) -> tuple:
    """(p25, p75). With ten runs a single outlier makes min/max overlap, so
    separation between cells is judged on the middle half of the runs."""
    values = list(values)
    if len(values) < 2:
        return values[0], values[0]
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def cells(rows: list, key: str) -> dict:
    out = {}
    for row in rows:
        out.setdefault(row[key], []).append(row)
    return out


def med(values) -> float:
    return statistics.median(values)


def cell_line(name: str, runs: list, width: int = 20) -> str:
    ok = answered(runs)
    t = [secs(r) for r in ok]
    n = len(runs)
    frac = lambda f: "%d/%d" % (sum(bool(r[f]) for r in runs), n)  # noqa: E731
    p25, p75 = quartiles(t)
    line = ("  %-*s %-5d %-6d %-8s %-8s %-8s %-8s %5.2f / %5.2f / %5.2f  iqr %5.2f-%5.2f"
            % (width, name, n, n - len(ok), frac("correct_row_count"), frac("cites_snapshot"),
               frac("cites_metadata"), frac("names_all_columns"), min(t), med(t), max(t), p25, p75))
    if all(r["tool_s"] is not None for r in ok):
        line += "   %5.1f       %5.2f" % (med(r["elapsed_s"] for r in ok), med(r["tool_s"] for r in ok))
    return line


def summary(a_rows: list, b_rows: list, repeat: int, c_rows: list = (), d_rows: list = (),
            truth: dict = None, e_rows: list = (), f_rows: list = ()) -> str:
    head = ("  cell                 runs  failed correct  snapshot metadata columns  "
            "answer s (min/med/max)  iqr (p25-p75)  process-med tool-med")
    tail = lambda rs: ("  catalog_calls across all runs: %s | invented columns: %d"  # noqa: E731
                       % (sorted({r["catalog_calls"] for r in rs}),
                          sum(bool(r["invented_column"]) for r in rs)))
    b_model = b_rows[0]["model"] if b_rows else "?"
    lines = ["# matrix summary, derived from matrix-axis-A.json and matrix-axis-B.json",
             "# every cell is %d runs of one question; correctness is checked against" % repeat,
             "# ground-truth.txt read directly from each catalog. Re-scored from each",
             "# capture's body by publish_evidence.py, not copied from the runner.",
             "# answer s is the answer alone: question in, answer out, after imports and",
             "# agent construction. process-med is the whole process, imports included.",
             "# tool is the part of the answer spent inside the Iceberg tools.", "",
             "AXIS A -- catalog fixed (%s), framework and model vary" % AXIS_A_CATALOG, head]
    lines += [cell_line(k, v) for k, v in cells(a_rows, "leg").items()]
    lines += [tail(a_rows), "",
              "AXIS B -- leg fixed (%s / ADK / %s), catalog varies" % (AXIS_B_LEG, b_model), head]
    lines += [cell_line(k, v) for k, v in cells(b_rows, "catalog").items()]
    lines.append(tail(b_rows))
    if c_rows:
        lines += ["", "AXIS C -- catalog fixed (%s), model fixed while framework varies" % AXIS_A_CATALOG,
                  head.replace("cell                ", "framework / model".ljust(36))]
        lines += [cell_line(k, v, 36) for k, v in cells(c_rows, "cell").items()]
        lines.append(tail(c_rows))
    if d_rows:
        lines += ["", "AXIS D -- each leg on its own cloud's catalog, a question only a data scan answers",
                  "  question: %s" % SCAN_QUESTION,
                  "  %-58s %-5s %-8s %-9s %-8s %-23s %-8s %s"
                  % ("framework / model on catalog", "runs", "max id", "count>=10", "snapshot",
                     "answer s (min/med/max)", "tool-med", "calls")]
        for key, runs in cells(d_rows, "cell").items():
            n = len(runs)
            frac = lambda f: "%d/%d" % (sum(bool(r[f]) for r in runs), n)  # noqa: E731
            ok = answered(runs)
            t = [secs(r) for r in ok]
            p25, p75 = quartiles(t)
            lines.append("  %-58s %-5d %-8s %-9s %-8s %5.2f / %5.2f / %5.2f  iqr %5.2f-%5.2f  %5.2f    %s  failed %d"
                         % (key, n, frac("correct_max_id"), frac("correct_count"),
                            frac("cites_snapshot"), min(t), med(t), max(t), p25, p75,
                            med(r["tool_s"] for r in ok),
                            sorted({r["catalog_calls"] for r in ok}), n - len(ok)))
        if truth:
            lines.append("  expected: " + "; ".join(
                "%s max_id=%s count>=10=%s" % (c, truth[c]["max_id"], truth[c]["ids_at_least_10"])
                for c in sorted({r["catalog"] for r in d_rows})))
    if e_rows:
        lines += ["", "AXIS E -- every framework and model on %s, the same data question" % AXIS_A_CATALOG,
                  "  question: %s" % SCAN_QUESTION,
                  "  %-58s %-5s %-8s %-9s %-8s %-23s %-8s %s"
                  % ("framework / model on catalog", "runs", "max id", "count>=10", "snapshot",
                     "answer s (min/med/max)", "tool-med", "calls")]
        for key, runs in cells(e_rows, "cell").items():
            n = len(runs)
            frac = lambda f: "%d/%d" % (sum(bool(r[f]) for r in runs), n)  # noqa: E731
            ok = answered(runs)
            t = [secs(r) for r in ok]
            p25, p75 = quartiles(t)
            lines.append("  %-58s %-5d %-8s %-9s %-8s %5.2f / %5.2f / %5.2f  iqr %5.2f-%5.2f  %5.2f    %s  failed %d"
                         % (key, n, frac("correct_max_id"), frac("correct_count"),
                            frac("cites_snapshot"), min(t), med(t), max(t), p25, p75,
                            med(r["tool_s"] for r in ok),
                            sorted({r["catalog_calls"] for r in ok}), n - len(ok)))
        lines.append("  [rows-only]: the v1 scan, rows and no computed count, so the model counts."
                     " [provider-decoding]: Nova Micro with no decoding fields sent.")
    if f_rows:
        lines += ["", "AXIS F -- Nova Micro on %s, Axis A's question, with and without its tool-use decoding"
                  % AXIS_A_CATALOG, head.replace("cell                ", "framework / model".ljust(58))]
        lines += [cell_line(k, v, 58) for k, v in cells(f_rows, "cell").items()]
        lines.append(tail(f_rows))
    if truth:
        lines += ["", "ground truth: snapshot total-records against a full scan of the data files"]
        lines += ["  %-20s total-records=%s scanned=%s agree=%s"
                  % (c, t["rows"], t.get("rows_scanned", "?"), t.get("rows_agree", "not checked"))
                  for c, t in truth.items()]
    everything = a_rows + b_rows
    lines += ["", "total runs, axes A and B: %d" % len(everything)]
    for f in ("correct_row_count", "cites_snapshot", "cites_metadata",
              "names_all_columns", "invented_column"):
        lines.append("  %-20s %d/%d" % (f, sum(bool(r[f]) for r in everything), len(everything)))
    if c_rows:
        lines.append("  axis C runs: %d (reported separately; it measures a different question)"
                     % len(c_rows))
    lines += ["", "# scored with scorer v%d (answer text only, count beside 'rows', whole-word"
              % SCORER_VERSION, "# columns). Runs recorded under an older scorer and re-scored:"]
    lines += ["#   " + c for c in SCORER_CHANGES] or ["#   no field changed"]
    return "\n".join(lines) + "\n"


def derived(a_rows: list, b_rows: list) -> str:
    legs = cells(a_rows, "leg")
    mid = {k: med(secs(r) for r in v) for k, v in legs.items()}
    lo = {k: quartiles(secs(r) for r in v)[0] for k, v in legs.items()}
    hi = {k: quartiles(secs(r) for r in v)[1] for k, v in legs.items()}
    order = sorted(mid, key=mid.get)
    fast, slow = order[0], order[-1]
    b_times = [secs(r) for r in b_rows]
    lines = ["# Figures in the article that are arithmetic on measured values rather than",
             "# measurements themselves. Written by publish_evidence.py from the re-scored",
             "# rows in matrix-summary.txt; nothing here is typed by hand.", "",
             "latency spread, fastest framework median to slowest, in answer seconds",
             "  source    matrix-summary.txt, AXIS A (catalog fixed at %s)" % AXIS_A_CATALOG,
             "  operands  %s median %.2fs / %s median %.2fs" % (slow, mid[slow], fast, mid[fast]),
             "  result    %.4f -> quoted as %.2fx" % (mid[slow] / mid[fast], mid[slow] / mid[fast]),
             "  note      medians, not extremes.", "",
             "separation between Axis A legs, ordered by median, on the middle half of runs"]
    for a, b in zip(order, order[1:]):
        lines.append("  %-5s p75 %.2fs vs %-5s p25 %.2fs -> %s"
                     % (a, hi[a], b, lo[b], "no overlap" if hi[a] < lo[b] else "OVERLAP"))
    lines += ["", "gap between adjacent Axis A legs",
              "  %-14s %-10s %s" % ("pair", "medians", "p25 of slower - p75 of faster")]
    for a, b in zip(order, order[1:]):
        lines.append("  %-14s %-10s %.2fs" % ("%s-%s" % (a, b), "%.2fs" % (mid[b] - mid[a]),
                                             lo[b] - hi[a]))
    lines += ["", "Axis B range, every run through one leg",
              "  %.2fs to %.2fs, width %.2fs" % (min(b_times), max(b_times),
                                                max(b_times) - min(b_times))]
    if all(r["tool_s"] is not None for r in a_rows + b_rows):
        lines += ["", "where the answer's time went (medians over each axis's runs)"]
        for label, rows in (("axis A", a_rows), ("axis B", b_rows)):
            share = med(r["tool_s"] / r["agent_s"] for r in rows if r["agent_s"])
            lines.append("  %s  agent %.2fs, tool %.2fs, tool share of the answer %.0f%%"
                         % (label, med(r["agent_s"] for r in rows),
                            med(r["tool_s"] for r in rows), 100 * share))
        slowest = sorted(a_rows + b_rows, key=lambda r: secs(r))[-3:]
        lines += ["", "the three slowest runs overall, split"]
        for r in reversed(slowest):
            lines.append("  %-45s total %.1fs  agent %.2fs  tool %.2fs  other %.2fs"
                         % (r["capture"], r["elapsed_s"], r["agent_s"], r["tool_s"],
                            r["agent_s"] - r["tool_s"]))
    return "\n".join(lines) + "\n"


def superseded(truth: dict) -> tuple:
    """Every archived run, re-scored and listed run by run, so none is lost.

    Returns the texts to publish and each run's (name, axis A rows, axis B rows)
    for the replication figures.
    """
    texts, history = {}, []
    for name, timed, header in SUPERSEDED:
        base = os.path.join(RAW, name)
        if not os.path.isdir(base):
            continue
        lines, by_axis = header + [""], {}
        for axis in [x for x in "ABC" if x in "AB"
                     or os.path.exists(os.path.join(base, "matrix-axis-%s.json" % x))]:
            _, rows, problems, bodies = rescore(base, axis, truth, timed=timed)
            if problems:
                sys.exit("%s re-scoring disagrees:\n%s" % (name, "\n".join(problems)))
            by_axis[axis] = rows
            lines.append("AXIS %s" % axis)
            for r in rows:
                ok = all(r[k] for k in ("correct_row_count", "cites_snapshot",
                                        "cites_metadata", "names_all_columns"))
                lines.append("  %-45s %5.1fs  %s  calls=%s"
                             % (r["capture"], secs(r), "correct" if ok else "WRONG",
                                r["catalog_calls"]))
            lines.append("")
            for capture, body in bodies.items():
                texts["superseded-runs/%s/matrix/%s" % (name, capture)] = body
        texts["superseded-runs/%s/README.txt" % name] = "\n".join(lines)
        history.append((name, by_axis["A"], by_axis["B"]))
    return texts, history


def self_test(truth: dict) -> None:
    """Plant an answer that must fail and one that must pass. A check that
    cannot fail reads exactly like a check that passes."""
    t = truth[AXIS_A_CATALOG]
    wrap = "<!-- cloud=x model=y catalog=z instruction=v2 catalog_calls=3 -->\n%s\n\ncatalog calls: 3 of 8"
    vacuous = score(wrap % "snapshot-id exists; payload region. %s" % t["rows"], t)
    good = score(wrap % ("%s rows. Columns: id, ts, payload, region. snapshot-id %s, %s"
                         % (t["rows"], t["snapshot_id"], t["metadata_location"])), t)
    outside = score("question: %s rows? id ts payload region %s %s\n" % (
        t["rows"], t["snapshot_id"], t["metadata_location"]) + wrap % "I could not read it.", t)
    # A real phrasing from the ten-repeat run, which v4 scored wrong.
    long_gap = score(wrap % ("The exact number of rows in this table, as of snapshot-id %s, is %s."
                             % (t["snapshot_id"], t["rows"])), t)
    failures = [k for k in ("correct_row_count", "names_all_columns") if vacuous[k]]
    failures += ["long-gap row count" for _ in [0] if not long_gap["correct_row_count"]]
    failures += ["good answer: " + k for k in ("correct_row_count", "cites_snapshot",
                 "cites_metadata", "names_all_columns") if not good[k]]
    failures += ["text outside the answer: " + k for k, v in outside.items()
                 if k != "catalog_calls" and v]
    if "max_id" in t:
        mx, n = t["max_id"], t["ids_at_least_10"]
        # The long gap is a real answer from Axis D's first run, which v2 scored wrong.
        right = score_scan(wrap % ('The largest id in the "probe_ns.probe_table" is %s. %s rows '
                                   "have an id of 10 or more. snapshot-id %s"
                                   % (mx, n, t["snapshot_id"])), t)
        swapped = score_scan(wrap % ("The largest id is %s, and %s rows have an id of 10 or more."
                                     % (n, mx)), t)
        failures += ["scan scorer, right answer: " + k for k in
                     ("correct_max_id", "correct_count", "cites_snapshot") if not right[k]]
        failures += ["scan scorer, swapped answer: " + k for k in
                     ("correct_max_id", "correct_count") if swapped[k]]
        # Scorer v7: the last stated value decides. A right value on the way to a
        # different final one must fail; a table total beside a right count must not.
        wrong_last = score_scan(wrap % ("The largest id is %s and %s rows have an id of 10 or more. "
                                        "Checking again: the largest id is %d, and %d rows have an "
                                        "id of 10 or more." % (mx, n, int(mx) - 2, int(n) + 3)), t)
        with_total = score_scan(wrap % ("Of the %s rows, those with an id of 10 or more number %s, "
                                        "and the largest id is %s." % (t["rows"], n, mx)), t)
        failures += ["scan scorer, right value then a different final one: " + k for k in
                     ("correct_max_id", "correct_count") if wrong_last[k]]
        failures += ["scan scorer, table total beside the count: " + k for k in
                     ("correct_max_id", "correct_count") if not with_total[k]]
        # Real phrasings from the published captures that a first v7 draft scored
        # wrong: the largest id on the line above the count, and the ids listed after it.
        for label, text in (
                ("max above count", "- Largest id in the table: %s.\n- Number of rows with id >= 10: %s."
                 % (mx, n)),
                ("ids listed after count", "The largest `id` in the table is %s.\nThere are %s rows "
                 "with an `id` of 10 or more (20, 21, 22, 23, 10, 11, 12, 13)." % (mx, n)),
                ("long gap before 10 or more", "The largest `id` is %s.\nThere are %s rows in the "
                 "`probe_ns.probe_table` that have an `id` of 10 or more." % (mx, n)),
                ("parenthetical before the count", "- Largest id in the table (snapshot shown "
                 "above): %s.\n- Number of rows with id >= 10 (same snapshot and metadata): %s."
                 % (mx, n)),
                ("ids listed after a colon", "The largest `id` is %s.\n\nThere are %s rows with an "
                 "`id` of 10 or more: 20, 21, 22, 23, 10, 11, 12, 13." % (mx, n)),
                # Verbatim shape from an Agent Framework capture: bullets, each with a
                # source line under it, and the scan's own COUNT and MIN/MAX quoted last.
                ("value stated as a bullet", "Results from reading that table (iceberg_scan_table "
                 "outputs):\n- Largest id in the table: %s.\n- Source version: snapshot-id %s.\n"
                 "- Number of rows with id >= 10: exactly %s rows.\n- Source version: snapshot-id "
                 "%s.\n(Scans also reported the full-table COUNT = %s and id MIN/MAX = 0 / %s.)"
                 % (mx, t["snapshot_id"], n, t["snapshot_id"], t["rows"], mx)),
                # Answers quote the scan's own summary under their claim; the MIN in
                # that line is not the answer's last word on the largest id.
                ("tool MIN and MAX quoted after the claim", "Largest id: %s.\nRows with id >= 10: %s.\n"
                 "From the scan: COUNT: exactly %s row(s) match `id >= 10`. MIN and MAX of id over "
                 "those %s row(s): 10 and %s." % (mx, n, n, n, mx)),
                # Verbatim third spelling of the same echo, from an Agent Framework
                # capture: the claim in a bullet, the scan's summary quoted below it.
                ("tool MIN and MAX quoted as 'over those rows'", "Answers (read from the snapshot "
                 "cited above)\n- Largest id in the table: %s.\n- Number of rows with id >= 10: %s.\n"
                 "- A filtered scan for id >= 10 reported COUNT: exactly %s row(s) matching "
                 "`id >= 10` in snapshot-id %s (MIN and MAX over those rows: 10 and %s)."
                 % (mx, n, n, t["snapshot_id"], mx))):
            real = score_scan(wrap % text, t)
            failures += ["scan scorer, real phrasing (%s): %s" % (label, k) for k in
                         ("correct_max_id", "correct_count") if not real[k]]
    if failures:
        sys.exit("scorer self-test failed, evidence NOT published: %s" % failures)


def verify_single_legs(truth: dict) -> list:
    """Re-check the quoted single-leg captures under the current scorer."""
    problems = []
    for leg in LEGS:
        with open(os.path.join(RAW, "run-%s.txt" % leg)) as handle:
            body = handle.read()
        catalog = re.search(r"catalog=(\S+)", body).group(1)
        result = score(body, truth[catalog])
        bad = [k for k, v in result.items()
               if (k == "invented_column" and v) or (k not in ("invented_column", "catalog_calls") and not v)]
        if bad:
            problems.append("run-%s.txt fails under scorer v%d: %s" % (leg, SCORER_VERSION, bad))
    return problems


def answer_style(bodies: dict) -> str:
    """How each framework-and-model pair answers, read from the published captures.

    Not scored: nothing here is right or wrong. It is what a developer sees, and
    Axis C separates the framework's part from the model's -- Strands appears
    with two models, Gemini with two frameworks.
    """
    cells_ = {}
    for name, body in bodies.items():
        leg = os.path.basename(name).split("__")[1]
        model = re.search(r"model=(\S+)", body).group(1)
        m = re.search(r"<!-- cloud=.*?-->\n(.*?)\ncatalog calls:", body, re.S)
        answer = m.group(1).strip() if m else ""
        before = body.split("<!-- cloud=")[0]
        first = answer.splitlines()[0][:60] if answer else ""
        c = cells_.setdefault("%s / %s" % (FRAMEWORK[leg], model),
                              {"n": 0, "chars": [], "lines": [], "thinking": 0,
                               "tool_log": 0, "twice": 0, "agent": []})
        c["n"] += 1
        c["chars"].append(len(answer))
        c["lines"].append(answer.count("\n") + 1)
        c["thinking"] += "<thinking>" in body
        c["tool_log"] += bool(re.search(r"-> tool:|Tool #\d", body))
        c["twice"] += bool(first) and first in before
        timing = TIMING.search(body)
        if timing:
            c["agent"].append(float(timing.group(1)))
    lines = ["", "answer style: every published matrix capture, by framework and model",
             "  %-36s %-5s %-12s %-11s %-9s %-9s %-7s %s"
             % ("framework / model", "runs", "answer chars", "answer lines", "thinking",
                "tool log", "printed", "agent-med")]
    for key in sorted(cells_):
        c = cells_[key]
        lines.append("  %-36s %-5d %-12d %-12d %-9s %-9s %-7s %.2fs"
                     % (key, c["n"], med(c["chars"]), med(c["lines"]),
                        "%d/%d" % (c["thinking"], c["n"]), "%d/%d" % (c["tool_log"], c["n"]),
                        "%d/%d" % (c["twice"], c["n"]), med(c["agent"]) if c["agent"] else 0))
    lines += ["  answer chars and lines are medians of the text after the stamped header.",
              "  thinking: <thinking> text reached stdout. tool log: the capture shows each",
              "  tool call as it happened. printed: the answer appears before the header as",
              "  well as after it, so it was printed twice."]
    return "\n".join(lines) + "\n"


def crossover(c_rows: list) -> str:
    """Axis C: each comparison moves exactly one of framework and model."""
    by = cells(c_rows, "cell")
    mid = {k: med(secs(r) for r in v) for k, v in by.items()}
    agent = {k: med(r["agent_s"] for r in v) for k, v in by.items()}
    lo = {k: quartiles(secs(r) for r in v)[0] for k, v in by.items()}
    hi = {k: quartiles(secs(r) for r in v)[1] for k, v in by.items()}
    adk_g, str_g, str_n = ("ADK / gemini-2.5-flash", "Strands / gemini-2.5-flash",
                           "Strands / us.amazon.nova-micro-v1:0")
    if not all(k in mid for k in (adk_g, str_g, str_n)):
        return ""

    def compare(label, a, b):
        slow, fast = (a, b) if mid[a] >= mid[b] else (b, a)
        return ["  %s" % label,
                "    %-36s answer median %.2fs  (iqr %.2f-%.2f)" % (a, mid[a], lo[a], hi[a]),
                "    %-36s answer median %.2fs  (iqr %.2f-%.2f)" % (b, mid[b], lo[b], hi[b]),
                "    ratio %.2fx, medians differ %.2fs, %s"
                % (mid[slow] / mid[fast], mid[slow] - mid[fast],
                   "no overlap" if hi[fast] < lo[slow] else "OVERLAP")]
    lines = ["", "crossover: Axis C, catalog fixed at %s" % AXIS_A_CATALOG]
    lines += compare("framework varies, model fixed (gemini-2.5-flash)", adk_g, str_g)
    lines += compare("model varies, framework fixed (Strands)", str_g, str_n)
    return "\n".join(lines) + "\n"


def token_breaks(body: str) -> list:
    """Line breaks inside a word or number that the model did not stream: the
    answer has "2\n3" where the streamed copy printed before the header has "23"."""
    answer = re.search(r"<!-- cloud=.*?-->\n(.*?)\ncatalog calls:", body, re.S)
    answer = answer.group(1) if answer else ""
    streamed = body.split("<!-- cloud=")[0]
    found = []
    for mt in re.finditer(r"(?<=\w)\n(?=\w)", answer):
        i = mt.start()
        joined = answer[max(0, i - 12):i] + answer[i + 1:i + 13]
        if "\n" not in joined and joined in streamed:
            found.append(answer[max(0, i - 15):i + 12])
    return found


def superseded_d(truth: dict) -> dict:
    texts = {}
    for name, header in SUPERSEDED_D:
        base = os.path.join(RAW, name)
        if not os.path.isdir(base):
            continue
        # Axis C of a complete archived run is already published by superseded().
        covered = "C" if name in {n for n, _, _ in SUPERSEDED} else ""
        # A and F too: an archive kept for what its ANSWER TEXT held, rather than for
        # a scan result, carries every axis it ran. Dropping them would publish 260 of
        # run10's 310 captures while nova-diagnosis.txt counts all 310.
        axes_here = [x for x in "ACDEF" if x not in covered
                     and os.path.exists(os.path.join(base, "matrix-axis-%s.json" % x))]
        rows, bodies = [], {}
        for axis in axes_here:
            _, axis_rows, problems, axis_bodies = rescore(base, axis, truth, timed=True)
            if problems:
                sys.exit("%s re-scoring disagrees:\n%s" % (name, "\n".join(problems)))
            rows += [dict(r, axis=axis) for r in axis_rows]
            bodies.update(axis_bodies)
        lines = header + ["", "  %-40s %-6s %-6s %-9s %-6s %s"
                          % ("capture", "max id", "count", "snapshot", "calls", "answer s")]
        for r in rows:
            # A, C and F ask the metadata question, so they are scored on the row
            # count and the column names, not on a scan result.
            if r["axis"] in "ACF":
                ok = all(r[k] for k in ("correct_row_count", "cites_snapshot",
                                        "cites_metadata", "names_all_columns"))
                lines.append("  %-40s %-22s %-6s %.2f"
                             % (r["capture"], "correct" if ok else "WRONG",
                                r["catalog_calls"], secs(r)))
                continue
            lines.append("  %-40s %-6s %-6s %-9s %-6s %.2f"
                         % (r["capture"], "ok" if r["correct_max_id"] else "WRONG",
                            "ok" if r["correct_count"] else "WRONG",
                            "ok" if r["cites_snapshot"] else "WRONG", r["catalog_calls"], secs(r)))
        broken = sorted((c, token_breaks(b)) for c, b in bodies.items() if "__aws__" in c)
        broken = [(c, b) for c, b in broken if b]
        strands = [c for c in bodies if "__aws__" in c]
        lines += ["", "Strands answers with a line break inside a word or number the model streamed"
                  " whole: %d of %d" % (len(broken), len(strands))]
        lines += ["  %-55s %r" % (c, b[0]) for c, b in broken]
        texts["superseded-runs/%s/README-axis-%s.txt" % (name, "".join(axes_here))] = "\n".join(lines) + "\n"
        for capture, body in bodies.items():
            texts["superseded-runs/%s/matrix/%s" % (name, capture)] = body
    return texts


def answer_diversity(named: list) -> str:
    """Distinct answer texts per cell. A cell whose ten runs return one identical
    answer is one sample repeated, not ten: its correct count is 0 or 10 by
    construction, and it cannot be read as a rate. MEASURED 2026-09-15: Nova Micro
    at temperature 0 and topK 1 gave one answer, word for word, in every run of a
    cell; every other model's cells gave ten different answers."""
    lines = ["", "answer diversity: distinct answer texts per cell (1 = one sample, repeated)",
             "  %-6s %-72s %s" % ("axis", "cell", "distinct answers / runs")]
    for axis, rows, bodies in named:
        for key, runs in cells(rows, "cell").items():
            texts = {answer_of(bodies[r["capture"]]).strip() for r in runs if r["capture"] in bodies}
            lines.append("  %-6s %-72s %d/%d" % (axis, key, len(texts), len(runs)))
    return "\n".join(lines) + "\n"


def token_section(named: list) -> str:
    """Tokens and model calls per answer. Output length drives answer time, so a
    speed difference between cells is read beside it. None where a framework does
    not report a figure (Agent Framework does not report model calls)."""
    lines = ["", "tokens and model calls per answer, medians over answered runs",
             "  frameworks report reasoning differently: ADK and Agent Framework separate it,",
             "  Strands' Gemini provider folds it into output. 'generated' is output plus",
             "  reasoning, the figure comparable across all four, and the per-100 column uses it.",
             "  %-6s %-58s %-7s %-7s %-9s %-9s %-11s %s"
             % ("axis", "cell", "input", "output", "reasoning", "generated", "model calls",
                "answer s per 100 generated tokens")]
    for axis, rows in named:
        for key, runs in cells(answered(rows), "cell").items():
            def m(field):
                vals = [r[field] for r in runs if r.get(field) is not None]
                return med(vals) if vals else None
            gen = [r["output_tokens"] + (r.get("reasoning_tokens") or 0)
                   for r in runs if r.get("output_tokens") is not None]
            per = [secs(r) / (r["output_tokens"] + (r.get("reasoning_tokens") or 0)) * 100
                   for r in runs if r.get("output_tokens")]
            fmt = lambda v: "n/a" if v is None else ("%d" % v if float(v).is_integer() else "%.1f" % v)  # noqa: E731
            lines.append("  %-6s %-58s %-7s %-7s %-9s %-9s %-11s %s"
                         % (axis, key, fmt(m("input_tokens")), fmt(m("output_tokens")),
                            fmt(m("reasoning_tokens")), fmt(med(gen) if gen else None),
                            fmt(m("model_calls")), "%.2f" % med(per) if per else "n/a"))
    return "\n".join(lines) + "\n"


def noise_across_tests(a_rows: list, b_rows: list, c_rows: list) -> str:
    """The same cell measured in more than one test, in separate sittings. The
    spread of its medians is the run-to-run variation a comparison has to clear."""
    groups = [
        ("ADK / gemini-2.5-flash on %s" % AXIS_A_CATALOG, [
            ("Axis A", [r for r in a_rows if r["leg"] == "gcp"]),
            ("Axis B", [r for r in b_rows if r["catalog"] == AXIS_A_CATALOG]),
            ("Axis C", [r for r in c_rows if r["leg"] == "gcp"])]),
        ("Strands / us.amazon.nova-micro-v1:0 on %s" % AXIS_A_CATALOG, [
            ("Axis A", [r for r in a_rows if r["leg"] == "aws"]),
            ("Axis C", [r for r in c_rows if r["leg"] == "aws" and "nova" in r["model"]])]),
    ]
    lines = ["", "the same cell measured in more than one test (separate sittings), answer medians"]
    for label, parts in groups:
        mids = [(name, med(secs(r) for r in answered(rows))) for name, rows in parts if answered(rows)]
        if len(mids) < 2:
            continue
        values = [v for _, v in mids]
        lines.append("  %-45s %s   spread %.2fs"
                     % (label, "  ".join("%s %.2fs" % (n, v) for n, v in mids),
                        max(values) - min(values)))
    return "\n".join(lines) + "\n"


def replication(history: list) -> str:
    """Axis A's ordering, spread and overlap in every complete run, and the one
    cell both axes measure, so run-to-run noise is stated beside the result."""
    lines = ["", "replication: Axis A in every complete run, legs ordered by median"]
    for label, a_rows, _ in history:
        legs = cells(a_rows, "leg")
        mid = {k: med(secs(r) for r in v) for k, v in legs.items()}
        lo = {k: quartiles(secs(r) for r in v)[0] for k, v in legs.items()}
        hi = {k: quartiles(secs(r) for r in v)[1] for k, v in legs.items()}
        order = sorted(mid, key=mid.get)
        overlap = any(hi[a] >= lo[b] for a, b in zip(order, order[1:]))
        lines.append("  %-20s %s   spread %.2fx   %s%s"
                     % (label, " < ".join("%s %.2fs" % (k, mid[k]) for k in order),
                        mid[order[-1]] / mid[order[0]], "OVERLAP" if overlap else "no overlap",
                        timed_label(a_rows)))
    lines += ["", "the same cell measured by both axes (%s on %s), medians"
              % (AXIS_B_LEG, AXIS_A_CATALOG)]
    for label, a_rows, b_rows in history:
        a = med(secs(r) for r in a_rows if r["leg"] == AXIS_B_LEG)
        b = med(secs(r) for r in b_rows if r["catalog"] == AXIS_A_CATALOG)
        b_mids = [med(secs(r) for r in v) for v in cells(b_rows, "catalog").values()]
        lines.append("  %-20s axis A %.2fs  axis B %.2fs  differ %.2fs   "
                     "(Axis B cell-median range %.2fs)%s"
                     % (label, a, b, abs(a - b), max(b_mids) - min(b_mids),
                        timed_label(a_rows + b_rows)))
    return "\n".join(lines) + "\n"


def renumber(mapping: dict) -> dict:
    """Pseudonyms numbered by kind in first-appearance order, with no gaps."""
    counts, out = {}, {}
    for real, pseudo in mapping.items():
        kind = pseudo.rsplit("-", 1)[0]
        counts[kind] = counts.get(kind, 0) + 1
        out[real] = "%s-%04d" % (kind, counts[kind])
    return out


def known_values() -> list:
    path = os.path.join(ROOT, ".known-identifiers")
    if not os.path.exists(path):
        sys.exit("FAIL  .known-identifiers is missing; cannot anonymise safely")
    with open(path) as handle:
        return [l.split("|", 1)[0].strip() for l in handle
                if l.strip() and not l.startswith("#")]


def main() -> None:
    truth = ground_truth()
    self_test(truth)
    a_data, a_rows, a_bad, a_bodies = rescore(RAW, "A", truth, timed=True)
    b_data, b_rows, b_bad, b_bodies = rescore(RAW, "B", truth, timed=True)
    axes = [(a_data, a_bodies), (b_data, b_bodies)]
    c_rows, c_bad, d_rows, d_bad, e_rows, e_bad, f_rows, f_bad = [], [], [], [], [], [], [], []
    if os.path.exists(os.path.join(RAW, "matrix-axis-C.json")):
        c_data, c_rows, c_bad, c_bodies = rescore(RAW, "C", truth, timed=True)
        axes.append((c_data, c_bodies))
    if os.path.exists(os.path.join(RAW, "matrix-axis-D.json")):
        d_data, d_rows, d_bad, d_bodies = rescore(RAW, "D", truth, timed=True)
        axes.append((d_data, d_bodies))
    if os.path.exists(os.path.join(RAW, "matrix-axis-E.json")):
        e_data, e_rows, e_bad, e_bodies = rescore(RAW, "E", truth, timed=True)
        axes.append((e_data, e_bodies))
    if os.path.exists(os.path.join(RAW, "matrix-axis-F.json")):
        f_data, f_rows, f_bad, f_bodies = rescore(RAW, "F", truth, timed=True)
        axes.append((f_data, f_bodies))
    bad = a_bad + b_bad + c_bad + d_bad + e_bad + f_bad + verify_single_legs(truth)
    if bad:
        print("\n".join("   !! " + p for p in bad))
        sys.exit("\nevidence NOT published: re-scoring disagrees with the runner")

    texts = {}
    for name in COPIED:
        with open(os.path.join(RAW, name)) as handle:
            texts[name] = handle.read()
    for data, bodies in axes:
        texts["matrix-axis-%s.json" % data["axis"]] = json.dumps(data, indent=2) + "\n"
        for name, body in bodies.items():
            texts["matrix/" + name] = body
    texts["derived-figures.txt"] = derived(a_rows, b_rows)
    old_texts, history = superseded(truth)
    texts.update(old_texts)
    texts.update(superseded_d(truth))
    texts["derived-figures.txt"] += replication(history + [("published run", a_rows, b_rows)])
    texts["derived-figures.txt"] += crossover(answered(c_rows))
    texts["derived-figures.txt"] += noise_across_tests(a_rows, b_rows, c_rows)
    texts["derived-figures.txt"] += answer_diversity(
        [("A", a_rows, a_bodies if a_rows else {}), ("C", c_rows, c_bodies if c_rows else {}),
         ("D", d_rows, d_bodies if d_rows else {}), ("E", e_rows, e_bodies if e_rows else {}),
         ("F", f_rows, f_bodies if f_rows else {})])
    texts["derived-figures.txt"] += token_section(
        [("A", a_rows), ("B", b_rows), ("C", c_rows), ("D", d_rows), ("E", e_rows), ("F", f_rows)])
    texts["matrix-summary.txt"] = summary(a_rows, b_rows, a_data["repeat"], c_rows, d_rows, truth,
                                          e_rows, f_rows)

    combined = "".join(texts.values())
    # BUCKET_RE reads abfss://<workspace-guid>@onelake.dfs... as one bucket name,
    # which would mask the OneLake host along with the GUID. The GUID pattern
    # already maps the workspace, so drop those entries and keep the host.
    mapping = {k: v for k, v in anon.build_map(combined).items() if "@" not in k}
    for value in known_values():
        if value.lower() in combined.lower() and value not in mapping:
            mapping[value] = "redacted-0000"
    mapping = renumber(mapping)
    # Measured on the anonymised captures, so the figures re-derive from the repo.
    texts["derived-figures.txt"] += answer_style(
        {n: anon.apply_map(t, mapping) for n, t in texts.items() if n.startswith("matrix/")})

    out, problems = {}, []
    for name, text in texts.items():
        clean = anon.apply_map(text, mapping)
        if name.endswith(".json"):
            json.loads(clean)
        for label, sample, n in anon.residual_scan(clean):
            problems.append("%s: %s x%d, e.g. %s" % (name, label, n, sample))
        for value in known_values():
            if value.lower() in clean.lower():
                problems.append("%s: a literal from .known-identifiers survived" % name)
        out[name] = clean
    if problems:
        print("\n".join("   !! " + p for p in problems))
        sys.exit("\nevidence NOT published: identifiers survived anonymisation")

    for sub in ("matrix", "superseded-run", "superseded-runs"):
        if os.path.isdir(os.path.join(DEST, sub)):
            shutil.rmtree(os.path.join(DEST, sub))
    for name, text in out.items():
        path = os.path.join(DEST, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)
    print(out["matrix-summary.txt"])
    print(out["derived-figures.txt"])
    print("mapped %d identifiers; published %d files to %s" % (len(mapping), len(out), DEST))


if __name__ == "__main__":
    main()
