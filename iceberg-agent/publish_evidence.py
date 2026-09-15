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
                        SCORER_VERSION, ground_truth, score)

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
]
COPIED = ["ground-truth.txt", "environment.txt", "failure-modes.txt", "verification.txt",
          "run-gcp.txt", "run-aws.txt", "run-azure.txt"]
TIMING = re.compile(r"agent seconds: ([\d.]+) \| tool seconds: ([\d.]+)")
#: Hostnames that are the evidence rather than an account. The blob host is the
#: one PyArrow builds for OneLake and which does not exist -- masking it would
#: remove the finding.
anon.KEEP_HOSTS |= {"onelake.blob.core.windows.net", "onelake.dfs.fabric.microsoft.com"}


def rescore(base: str, axis: str, truth: dict, timed: bool) -> tuple:
    with open(os.path.join(base, "matrix-axis-%s.json" % axis)) as handle:
        data = json.load(handle)
    rows, problems, bodies = [], [], {}
    for stored in data["results"]:
        with open(os.path.join(base, "matrix", stored["capture"])) as handle:
            body = handle.read()
        bodies[stored["capture"]] = body
        fresh = score(body, truth[stored["catalog"]])
        if fresh["catalog_calls"] is None:
            problems.append("%s: no stamped header, the leg did not answer" % stored["capture"])
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
        if timed and (agent_s is None or agent_s != stored.get("agent_s")
                      or tool_s != stored.get("tool_s")):
            problems.append("%s: timing line missing or disagrees with the runner"
                            % stored["capture"])
        model = re.search(r"<!-- cloud=\S+ model=(\S+)", body)
        model = model.group(1) if model else "?"
        if stored.get("model") and stored["model"] != model:
            problems.append("%s: runner asked for %s, answer header says %s"
                            % (stored["capture"], stored["model"], model))
        rows.append(dict(stored, **fresh, agent_s=agent_s, tool_s=tool_s, model=model,
                         cell="%s / %s" % (FRAMEWORK[stored["leg"]], model)))
    return data, rows, problems, bodies


def cells(rows: list, key: str) -> dict:
    out = {}
    for row in rows:
        out.setdefault(row[key], []).append(row)
    return out


def med(values) -> float:
    return statistics.median(values)


def cell_line(name: str, runs: list, width: int = 20) -> str:
    t = [r["elapsed_s"] for r in runs]
    n = len(runs)
    frac = lambda f: "%d/%d" % (sum(bool(r[f]) for r in runs), n)  # noqa: E731
    line = ("  %-*s %-5d %-8s %-8s %-8s %-8s %5.1f / %5.1f / %5.1f"
            % (width, name, n, frac("correct_row_count"), frac("cites_snapshot"),
               frac("cites_metadata"), frac("names_all_columns"), min(t), med(t), max(t)))
    if all(r["tool_s"] is not None for r in runs):
        line += "   %5.2f   %5.2f" % (med(r["agent_s"] for r in runs), med(r["tool_s"] for r in runs))
    return line


def summary(a_rows: list, b_rows: list, repeat: int, c_rows: list = ()) -> str:
    head = ("  cell                 runs  correct  snapshot metadata columns  "
            "seconds (min/med/max)  agent-med tool-med")
    tail = lambda rs: ("  catalog_calls across all runs: %s | invented columns: %d"  # noqa: E731
                       % (sorted({r["catalog_calls"] for r in rs}),
                          sum(bool(r["invented_column"]) for r in rs)))
    b_model = b_rows[0]["model"] if b_rows else "?"
    lines = ["# matrix summary, derived from matrix-axis-A.json and matrix-axis-B.json",
             "# every cell is %d runs of one question; correctness is checked against" % repeat,
             "# ground-truth.txt read directly from each catalog. Re-scored from each",
             "# capture's body by publish_evidence.py, not copied from the runner.",
             "# seconds is the whole process, imports included. agent is the answer alone;",
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
    mid = {k: med(r["elapsed_s"] for r in v) for k, v in legs.items()}
    lo = {k: min(r["elapsed_s"] for r in v) for k, v in legs.items()}
    hi = {k: max(r["elapsed_s"] for r in v) for k, v in legs.items()}
    order = sorted(mid, key=mid.get)
    fast, slow = order[0], order[-1]
    b_times = [r["elapsed_s"] for r in b_rows]
    lines = ["# Figures in the article that are arithmetic on measured values rather than",
             "# measurements themselves. Written by publish_evidence.py from the re-scored",
             "# rows in matrix-summary.txt; nothing here is typed by hand.", "",
             "latency spread, fastest framework median to slowest",
             "  source    matrix-summary.txt, AXIS A (catalog fixed at %s)" % AXIS_A_CATALOG,
             "  operands  %s median %.1fs / %s median %.1fs" % (slow, mid[slow], fast, mid[fast]),
             "  result    %.4f -> quoted as %.2fx" % (mid[slow] / mid[fast], mid[slow] / mid[fast]),
             "  note      medians, not extremes. The max-to-min ratio over the same cells is",
             "            %.1f / %.1f = %.2fx, which is NOT the headline figure."
             % (max(hi.values()), min(lo.values()), max(hi.values()) / min(lo.values())), "",
             "overlap between Axis A legs, ordered by median"]
    for a, b in zip(order, order[1:]):
        lines.append("  %-5s slowest %.1fs vs %-5s fastest %.1fs -> %s"
                     % (a, hi[a], b, lo[b], "no overlap" if hi[a] < lo[b] else "OVERLAP"))
    lines += ["", "gap between adjacent Axis A legs",
              "  %-14s %-10s %s" % ("pair", "medians", "edges (fastest of slower - slowest of faster)")]
    for a, b in zip(order, order[1:]):
        lines.append("  %-14s %-10s %.1fs" % ("%s-%s" % (a, b), "%.1fs" % (mid[b] - mid[a]),
                                             lo[b] - hi[a]))
    lines += ["", "Axis B range, every run through one leg",
              "  %.1fs to %.1fs, width %.1fs" % (min(b_times), max(b_times),
                                                max(b_times) - min(b_times))]
    if all(r["tool_s"] is not None for r in a_rows + b_rows):
        lines += ["", "where the answer's time went (medians over each axis's runs)"]
        for label, rows in (("axis A", a_rows), ("axis B", b_rows)):
            share = med(r["tool_s"] / r["agent_s"] for r in rows if r["agent_s"])
            lines.append("  %s  agent %.2fs, tool %.2fs, tool share of the answer %.0f%%"
                         % (label, med(r["agent_s"] for r in rows),
                            med(r["tool_s"] for r in rows), 100 * share))
        slowest = sorted(a_rows + b_rows, key=lambda r: r["elapsed_s"])[-3:]
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
        for axis in "AB":
            _, rows, problems, bodies = rescore(base, axis, truth, timed=timed)
            if problems:
                sys.exit("%s re-scoring disagrees:\n%s" % (name, "\n".join(problems)))
            by_axis[axis] = rows
            lines.append("AXIS %s" % axis)
            for r in rows:
                ok = all(r[k] for k in ("correct_row_count", "cites_snapshot",
                                        "cites_metadata", "names_all_columns"))
                lines.append("  %-45s %5.1fs  %s  calls=%s"
                             % (r["capture"], r["elapsed_s"], "correct" if ok else "WRONG",
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
    failures = [k for k in ("correct_row_count", "names_all_columns") if vacuous[k]]
    failures += ["good answer: " + k for k in ("correct_row_count", "cites_snapshot",
                 "cites_metadata", "names_all_columns") if not good[k]]
    failures += ["text outside the answer: " + k for k, v in outside.items()
                 if k != "catalog_calls" and v]
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


def crossover(c_rows: list) -> str:
    """Axis C: each comparison moves exactly one of framework and model."""
    by = cells(c_rows, "cell")
    mid = {k: med(r["elapsed_s"] for r in v) for k, v in by.items()}
    agent = {k: med(r["agent_s"] for r in v) for k, v in by.items()}
    lo = {k: min(r["elapsed_s"] for r in v) for k, v in by.items()}
    hi = {k: max(r["elapsed_s"] for r in v) for k, v in by.items()}
    adk_g, str_g, str_n = ("ADK / gemini-2.5-flash", "Strands / gemini-2.5-flash",
                           "Strands / us.amazon.nova-micro-v1:0")
    if not all(k in mid for k in (adk_g, str_g, str_n)):
        return ""

    def compare(label, a, b):
        slow, fast = (a, b) if mid[a] >= mid[b] else (b, a)
        return ["  %s" % label,
                "    %-36s median %.1fs  (%.1f-%.1f)  agent-med %.2fs" % (a, mid[a], lo[a], hi[a], agent[a]),
                "    %-36s median %.1fs  (%.1f-%.1f)  agent-med %.2fs" % (b, mid[b], lo[b], hi[b], agent[b]),
                "    ratio %.2fx, medians differ %.1fs, %s"
                % (mid[slow] / mid[fast], mid[slow] - mid[fast],
                   "no overlap" if hi[fast] < lo[slow] else "OVERLAP")]
    lines = ["", "crossover: Axis C, catalog fixed at %s" % AXIS_A_CATALOG]
    lines += compare("framework varies, model fixed (gemini-2.5-flash)", adk_g, str_g)
    lines += compare("model varies, framework fixed (Strands)", str_g, str_n)
    return "\n".join(lines) + "\n"


def replication(history: list) -> str:
    """Axis A's ordering, spread and overlap in every complete run, and the one
    cell both axes measure, so run-to-run noise is stated beside the result."""
    lines = ["", "replication: Axis A in every complete run, legs ordered by median"]
    for label, a_rows, _ in history:
        legs = cells(a_rows, "leg")
        mid = {k: med(r["elapsed_s"] for r in v) for k, v in legs.items()}
        lo = {k: min(r["elapsed_s"] for r in v) for k, v in legs.items()}
        hi = {k: max(r["elapsed_s"] for r in v) for k, v in legs.items()}
        order = sorted(mid, key=mid.get)
        overlap = any(hi[a] >= lo[b] for a, b in zip(order, order[1:]))
        lines.append("  %-20s %s   spread %.2fx   %s"
                     % (label, " < ".join("%s %.1fs" % (k, mid[k]) for k in order),
                        mid[order[-1]] / mid[order[0]], "OVERLAP" if overlap else "no overlap"))
    lines += ["", "the same cell measured by both axes (%s on %s), medians"
              % (AXIS_B_LEG, AXIS_A_CATALOG)]
    for label, a_rows, b_rows in history:
        a = med(r["elapsed_s"] for r in a_rows if r["leg"] == AXIS_B_LEG)
        b = med(r["elapsed_s"] for r in b_rows if r["catalog"] == AXIS_A_CATALOG)
        b_mids = [med(r["elapsed_s"] for r in v) for v in cells(b_rows, "catalog").values()]
        lines.append("  %-20s axis A %.1fs  axis B %.1fs  differ %.1fs   "
                     "(Axis B cell-median range %.1fs)"
                     % (label, a, b, abs(a - b), max(b_mids) - min(b_mids)))
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
    c_rows, c_bad = [], []
    if os.path.exists(os.path.join(RAW, "matrix-axis-C.json")):
        c_data, c_rows, c_bad, c_bodies = rescore(RAW, "C", truth, timed=True)
        axes.append((c_data, c_bodies))
    bad = a_bad + b_bad + c_bad + verify_single_legs(truth)
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
    texts["derived-figures.txt"] += replication(history + [("published run", a_rows, b_rows)])
    texts["derived-figures.txt"] += crossover(c_rows)
    texts["matrix-summary.txt"] = summary(a_rows, b_rows, a_data["repeat"], c_rows)

    combined = "".join(texts.values())
    # BUCKET_RE reads abfss://<workspace-guid>@onelake.dfs... as one bucket name,
    # which would mask the OneLake host along with the GUID. The GUID pattern
    # already maps the workspace, so drop those entries and keep the host.
    mapping = {k: v for k, v in anon.build_map(combined).items() if "@" not in k}
    for value in known_values():
        if value.lower() in combined.lower() and value not in mapping:
            mapping[value] = "redacted-0000"
    mapping = renumber(mapping)

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
