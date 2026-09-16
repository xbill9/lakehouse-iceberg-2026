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


def ground_truth(catalog):
    """The truth for one catalog, or a refusal.

    Each server reads its own catalog, so each cell is graded against that
    catalog's snapshot id and metadata location. Grading a Google cell against
    Polaris's would score the citation checks 0 by construction, and a scoring
    artefact that looks like a finding is the failure this project exists to
    avoid.

    A missing file stops the run rather than defaulting to another catalog's:
    the whole point is that the grader cannot quietly compare against the wrong
    table.
    """
    path = os.path.join(EVIDENCE, "ground-truth-%s.txt" % catalog)
    if not os.path.exists(path):
        raise SystemExit(
            "no ground truth for %s.\n  expected %s\n"
            "  run: python3 ground_truth.py --catalog %s" % (catalog, path, catalog))
    truth = {}
    with open(path) as h:
        for line in h:
            if "=" in line and line.startswith("  "):
                k, v = line.strip().split("=", 1)
                truth[k] = v
    # A metadata_location pointing at a path that is gone means the file was
    # written on another machine or before a reseed. Paper 4's first
    # ground-truth.txt was exactly that, and every citation check would have
    # been graded against a file that does not exist.
    loc = truth.get("metadata_location", "")
    if loc.startswith("file:") and not os.path.exists(loc[len("file:"):]):
        raise SystemExit(
            "stale ground truth for %s: %s does not exist.\n"
            "  regenerate: python3 ground_truth.py --catalog %s" % (catalog, loc, catalog))
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


#: The arithmetic-provenance pair. `iceberg-agent`'s rule is that counting,
#: filtering and comparing belong in the engine and the model quotes the result;
#: a benchmark that lets the model do the sums measures the wrong thing. These
#: two say which happened, so the model-counts case can be reported as a
#: diagnostic rather than as the headline.
AGGREGATE = re.compile(r"\b(count|min|max|sum|avg|approx_count_distinct)\s*\(|"
                       r"\bgroup\s+by\b", re.I)
ROW_FETCH = re.compile(r"\bselect\b(?!\s*(count|min|max|sum|avg)\s*\()|\bscan\b|\blimit\b", re.I)

#: Bumped whenever a pattern changes, and recorded in the axis JSON so a stored
#: result says which scorer produced it. Paper 3 went through five versions on
#: exactly these two checks; the patterns below are its, not new ones.
SCORER_VERSION = 2


def word(name, text):
    """`name` as a whole identifier: not inside `identifier`, not inside `results`.

    The fixture's columns are id, ts, payload and region. Substring matching --
    which is what this check did at v1 -- makes "id" match *considered* and "ts"
    match *objects*, so it passed on prose that named no column at all.
    """
    return bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text))


def for_pairing(text):
    """Blank what breaks value-to-wording pairing, for pairing only.

    A metadata location and a snapshot id are long digit runs and URIs; their
    digits both stop a span and offer false matches. Markdown emphasis does the
    same by putting backticks between a number and its noun. The citation checks
    still read the answer as written -- only the pairing sees this.
    """
    out = re.sub(r"(?:file|s3a?|gs|abfss?)://?\S+|\b\d{12,}\b", " ", text)
    return re.sub(r"[`*_]", "", out)


def states_count(n, text):
    """The number next to its own noun, not merely present somewhere.

    `\b11\b` alone matches 2026-09-11 and 11.5 seconds. The lookarounds refuse
    a longer number and a decimal; the span requires the word "row" nearby, on
    the same line, in either order.
    """
    n = re.escape(n)
    return bool(re.search(
        r"(?<![\w.-])%s(?![\w-]|\.\d)[^\n]{0,90}?\brows?\b|"
        r"\brows?\b[^\n]{0,90}?(?<![\w.-])%s(?![\w-]|\.\d)" % (n, n),
        for_pairing(text), re.I))


REFUSAL = re.compile(
    r"\b(no tool|not available|cannot|can't|unable to|does not (?:support|expose)|"
    r"no such tool|not supported|lacks?)\b", re.I)


def score(qid, body, truth, server):
    """What the answer got right, by comparison only -- never by judgement.

    Capability is read from the server's documented surface, not inferred from
    the run. A question a surface cannot express is not a question the host
    failed: scoring it 0 measures the vocabulary the server was given, which
    was already known before the run started.
    """
    cols = truth["columns"].split(",")
    s = {
        "names_all_columns": all(word(c, body) for c in cols),
        "correct_row_count": states_count(truth["rows"], body),
        "cites_snapshot": truth["snapshot_id"] in body,
        "cites_metadata": truth["metadata_location"] in body,
        "declines_explicitly": bool(REFUSAL.search(body)),
    }
    # A server with no row-returning tool cannot know the count. Saying so is
    # the right answer; producing a number is not, even if the number is right.
    if qid in ("Q4", "Q5") and not server["answers_rows"]:
        s["invented_an_answer"] = bool(re.search(r"\b\d+\s*(rows?|records?)\b", body)) \
            and not s["declines_explicitly"]
    # Q6 on the same principle. bigquery-mcp's documented output carries no
    # snapshot id, metadata location or table version, so a refusal there is
    # the right answer -- and a citation would contradict
    # evidence/server-surfaces.txt, which is a finding, so it is recorded
    # rather than quietly scored as a pass.
    if qid == "Q6":
        can = server.get("cites_version")
        s["version_expressible"] = can
        if can is False:
            s["correctly_declined_version"] = s["declines_explicitly"]
            s["cited_despite_surface"] = s["cites_snapshot"] or s["cites_metadata"]
    return s


TRACES = os.path.join(EVIDENCE, "traces")


def read_trace(label):
    """What the host actually called, from the proxy's log.

    Absent is not empty. An HTTP server is dialled by the host directly, so
    those cells have no file at all and `traced` is False -- reporting them as
    "made no tool calls" would invent a finding out of a plumbing limit.
    """
    path = os.path.join(TRACES, label + ".jsonl")
    if not os.path.exists(path):
        return None
    calls, listed, errors, args_seen = [], [], 0, []
    with open(path) as h:
        for line in h:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("method") == "tools/call" and rec.get("name"):
                calls.append(rec["name"])
                args_seen.append(" ".join(str(v) for v in (rec.get("args") or {}).values()))
            if rec.get("tools"):
                listed = rec["tools"]
            if rec.get("error") or rec.get("is_error"):
                errors += 1
    sent = " ".join(args_seen)
    return {"tool_calls": calls, "tools_offered": listed, "error_frames": errors,
            # Where the arithmetic happened. An aggregate pushes it into the
            # engine; a bare row fetch leaves it to the model, which is the thing
            # paper 3 measured failing. Same number, different provenance.
            "engine_aggregate": bool(AGGREGATE.search(sent)),
            "fetched_rows": bool(ROW_FETCH.search(sent)) and not AGGREGATE.search(sent)}


#: Planted answers with a known verdict. Half of them MUST fail: a scorer is only
#: worth trusting if it can say no, and paper 3 shipped a version that regressed
#: twelve correct answers because nothing here would have caught it.
SELF_TEST = [
    # (label, question, body, field, expected)
    ("plain count",            "Q4", "The probe table has 11 rows.", "correct_row_count", True),
    ("count before noun",      "Q4", "Rows: 11", "correct_row_count", True),
    ("date, not a count",      "Q4", "Read on 2026-09-11 from the catalog.", "correct_row_count", False),
    ("decimal, not a count",   "Q4", "The query took 11.5 seconds over the rows.", "correct_row_count", False),
    ("different noun",         "Q4", "The table has 11 columns.", "correct_row_count", False),
    ("inside a longer number", "Q4", "Snapshot 6042367411917366632 rows were read.", "correct_row_count", False),
    ("all four columns",       "Q3", "Columns: id, ts, payload, region.", "names_all_columns", True),
    # Every column name present as a substring, none of them named: identifier,
    # timestamps, payloads, regions. v1 passed this, which is the bug.
    ("substrings, no columns",  "Q3",
     "The identifier list, timestamps, payloads and regions were all considered.",
     "names_all_columns", False),
    ("plural is not the name",  "Q3", "Columns: ids, ts, payloads, regions.",
     "names_all_columns", False),
    ("three of four",          "Q3", "Columns: id, ts, payload.", "names_all_columns", False),
]


def self_test(truth):
    """Refuse to run if the scorer cannot tell the planted cases apart."""
    srv = {"answers_rows": True, "cites_version": None}
    bad = []
    for label, qid, body, field, expected in SELF_TEST:
        got = score(qid, body, truth, srv).get(field)
        if bool(got) is not expected:
            bad.append("  %-24s %-18s expected %s, got %s\n      body: %s"
                       % (label, field, expected, got, body))
    if bad:
        raise SystemExit("scorer v%d self-test FAILED -- not running:\n%s"
                         % (SCORER_VERSION, "\n".join(bad)))
    return len(SELF_TEST)


def one_cell(host, server, truth):
    h = hosts_mod.HOSTS[host]
    cleanup = h.prepare(server)
    rows = []
    try:
        for qid, text in questions():
            label = "%s__%s__%s" % (host, server["key"], qid)
            # The proxy appends, so a re-run would otherwise stack on the last one.
            stale = os.path.join(TRACES, label + ".jsonl")
            if os.path.exists(stale):
                os.remove(stale)
            os.environ["MCP_TRACE_LABEL"] = label
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

            trace = read_trace(label) if server.get("traced") else None
            row = {"host": host, "server": server["key"], "question": qid,
                   "catalog": server["catalog"], "graded_against": truth.get("snapshot_id"),
                   "elapsed_s": elapsed, "capture": os.path.basename(cap),
                   "error": err, "traced": bool(trace)}
            if trace:
                row.update(trace)
                # The check prose cannot make: a substantive answer with no tool
                # call behind it. Paper 3 could only separate a fetched figure
                # from an invented one because the calls were on record.
                row["answered_without_tools"] = (
                    not trace["tool_calls"] and len(body.strip()) > 80
                    and not REFUSAL.search(body))
                # A number in the answer, rows pulled back, and no aggregate sent:
                # the model did the sum. Record it; do not headline it.
                if qid in ("Q4", "Q5"):
                    row["model_did_arithmetic"] = (
                        trace["fetched_rows"] and not trace["engine_aggregate"]
                        and bool(re.search(r"\d", body)))
            row.update(score(qid, body, truth, server))
            rows.append(row)
            print("  %-7s %-13s %s  %5ss  %-8s %s" % (
                host, server["key"], qid, elapsed,
                "ERR" if err else ("declines" if row["declines_explicitly"] else "answered"),
                ("calls=" + ",".join(row["tool_calls"]) if row.get("tool_calls")
                 else ("NO TOOL CALL" if row.get("traced") else "untraced"))),
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

    if a.axis == "A":
        keys = (a.only or ",".join(SERVERS)).split(",")
        cells = [(a.host, SERVERS[k]) for k in keys]
    else:
        keys = (a.only or ",".join(hosts_mod.HOSTS)).split(",")
        cells = [(k, SERVERS[a.server]) for k in keys]

    first = ground_truth(cells[0][1]["catalog"])
    print("scorer v%d: %d planted cases pass\n" % (SCORER_VERSION, self_test(first)))

    results = []
    for host, server in cells:
        # Per server, not per run: axis A varies the server, so it varies the
        # catalog too.
        results += one_cell(host, server, ground_truth(server["catalog"]))

    out = os.path.join(EVIDENCE, "matrix-axis-%s.json" % a.axis)
    with open(out, "w") as h:
        json.dump({"axis": a.axis, "scorer": SCORER_VERSION,
                   "results": results}, h, indent=2)
    print("\nwrote %s (%d rows)" % (out, len(results)))


if __name__ == "__main__":
    main()
