#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask the same questions of the same table through each host and server.

Two axes, so a difference can be attributed to one thing:

    axis A   host fixed, servers vary              -> isolates the server surface
    axis B   server fixed, hosts vary               -> host AND model together
    axis C   server fixed, hosts vary, model pinned -> isolates the host

    python3 run_matrix.py --axis A --host claude
    python3 run_matrix.py --axis B --server bigquery
    python3 run_matrix.py --axis C --server bigquery --model MODEL

Axis B cannot attribute its own result and says so: each host defaults to its
vendor's model, so a difference there is host and model at once. Axis C pins one
model across the hosts and is the cell that separates them -- the same move
paper 3 made by running Strands on Gemini beside ADK on Gemini. A host that
rejects the pinned model is recorded as a refusal, never silently run on its
default, because that would restore the confound without saying so.

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
import random
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
AXIS_B_SERVER = "ours-engine"


def ground_truth(catalog, table="probe_table"):
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
    stem = "ground-truth-%s" % catalog
    if table != "probe_table":
        stem += "-%s" % table
    path = os.path.join(EVIDENCE, stem + ".txt")
    if not os.path.exists(path):
        raise SystemExit(
            "no ground truth for %s.\n  expected %s\n"
            "  run: python3 ground_truth.py --catalog %s --table %s"
            % (catalog, path, catalog, table))
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


def questions(table="probe_ns.probe_table"):
    out = []
    with open(os.path.join(HERE, "questions.txt")) as h:
        for line in h:
            line = line.strip()
            if line and not line.startswith("#"):
                qid, text = line.split(None, 1)
                out.append((qid, text.strip().replace("{table}", table)))
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
SCORER_VERSION = 11


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
    out = re.sub(r"[`*_]", "", out)
    # Thousands separators, or the scale arm scores itself wrong. MEASURED
    # 2026-09-16, before the run rather than after it: the true count is 99,999
    # and "The table has 99,999 rows." returned False, because the pattern looks
    # for the bare digits. English prose groups digits; the catalog does not.
    # Only a separator sitting between a digit and exactly three more is
    # removed, so a snapshot id or a decimal is untouched.
    return re.sub(r"(?<=\d)[,\u00a0\u202f ](?=\d{3}(?!\d))", "", out)


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


def states_number(n, noun, text):
    """`n` next to `noun`, the states_count pattern for any countable thing.

    Same lookarounds and the same reason: a bare \\b4\\b matches a date, a
    version and half a snapshot id. The number has to sit beside the word it is
    a count of, on one line, in either order.
    """
    # MEASURED 2026-09-16: three of twelve Q1 answers wrote "One namespace:
    # probe_ns" -- the word, not the digit -- and a digit-only check scored a
    # correct answer wrong. Small counts get spelled out in prose, which is
    # ordinary English rather than a wrong answer, so the spelling counts too.
    # A fixed table of number words is comparison, not judgement.
    WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve"]
    forms = [re.escape(str(n))]
    if str(n).isdigit() and int(n) < len(WORDS):
        forms.append(WORDS[int(n)])
    alt = "(?:%s)" % "|".join(forms)
    return bool(re.search(
        r"(?<![\w.-])%s(?![\w-]|\.\d)[^\n]{0,90}?\b%s" % (alt, noun) + r"s?\b|"
        r"\b%s" % noun + r"s?\b[^\n]{0,90}?(?<![\w.-])%s(?![\w-]|\.\d)" % alt,
        for_pairing(text), re.I))


ABSENT = re.compile(
    r"\b(does not exist|doesn't exist|no such namespace|not found|does not "
    r"appear|no namespace|not present|there is no|nosuchnamespace)\b", re.I)


REFUSAL = re.compile(
    r"\b(no tool|not available|cannot|can't|unable to|does not (?:support|expose)|"
    r"no such tool|not supported|lacks?)\b", re.I)


def loose(stamp):
    """A timestamp as a pattern tolerant of the ways an answer may write it.

    The catalog gives `2026-09-01 00:00:00+00:00`. An answer may write it with a
    T, with a Z, without the offset, or without the seconds, and all four are
    the same instant correctly reported. Matching the literal string would score
    a right answer wrong, which is the failure mode this whole file is built to
    avoid -- so the date and the hour and minute are required, and everything
    after them is optional.
    """
    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})", str(stamp))
    if not m:
        return None
    date, hh, mm = m.groups()
    return re.compile(r"%s[ T]%s:%s" % (re.escape(date), hh, mm))


def states_range(spec, body):
    """Both ends of a column's range, present and in the right order.

    One endpoint is not a range: an answer naming only the earliest timestamp
    has not answered "what is the range", and an earlier version of this check
    that used `or` would have passed it.
    """
    if not spec or "|" not in spec:
        return None
    low, high = spec.split("|", 1)
    lo_pat, hi_pat = loose(low), loose(high)
    if lo_pat and hi_pat:                      # a timestamp range
        return bool(lo_pat.search(body)) and bool(hi_pat.search(body))
    return word(low, body) and word(high, body)


#: Which field carries the verdict for each question. Without this the results
#: table read every field against every question, so Q1 and Q2 scored 0 for
#: `names_all_columns` -- a question that was never asked about columns marked
#: wrong for not answering it. Silence looked like failure across two matrices.
VERDICT = {
    "Q1": "correct_namespace_count",
    "Q2": "reports_namespace_absent",
    "Q3": "names_all_columns",
    "Q4": "correct_row_count",
    "Q5": "correct_ts_range",
    "Q6": "correct_snapshot_count",
}


#: Phrases a host uses when it has sampled and knows it cannot count. Separate
#: from REFUSAL, which is about a tool being missing: here the tool answered, and
#: the honest failure is about what the answer can support.
CANNOT_COUNT = re.compile(
    r"(could not|cannot|can't|unable to) count|not the whole table|only a sample|"
    r"\bsampled\b|is a sample|partial (?:view|scan|sample)|do(?:es)? not (?:give|"
    r"provide) (?:the |an )?(?:exact |total )?count", re.I)


def row_count_claims(text):
    """Every number this answer puts next to the word "rows", as written.

    Not a verdict. At scale, with the exact-count tool withheld, there is no
    correct number to give -- so the question is not whether a cell was right
    but what it said instead, and a boolean cannot carry that. The claims are
    recorded verbatim and read back in analysis; the scan itself reports "100
    row(s)", so a 100 here is a host describing its sample, not inventing a
    total, and only reading the capture can tell those apart. Recording the
    candidates and confirming by hand beats a regex that guesses intent.
    """
    out = []
    for m in re.finditer(r"(?<![\w.-])(\d+)(?![\w-]|\.\d)[^\n]{0,40}?\brows?\b|"
                         r"\brows?\b[^\n]{0,40}?(?<![\w.-])(\d+)(?![\w-]|\.\d)",
                         for_pairing(text), re.I):
        out.append(m.group(1) or m.group(2))
    return sorted(set(out), key=lambda v: (len(v), v))


def says_absent(name, text):
    """The namespace named as missing, not merely the word "no" somewhere.

    MEASURED 2026-09-16: a bare ABSENT search fired on 5 of 12 Q1 answers,
    because they explain that the server has "no namespace-listing tool" and
    that `iceberg_list_tables` "does not count them". That is a statement about
    a TOOL being absent, not about the namespace, and scoring it as an answer to
    Q2 would credit a host for a sentence about something else entirely. Same
    idiom as states_count: the claim has to sit beside the thing it is about.
    """
    if not name:
        return None
    near = r"[^\n]{0,80}"
    n = re.escape(name)
    return bool(re.search(r"%s%s%s|%s%s%s" % (ABSENT.pattern, near, n,
                                              n, near, ABSENT.pattern),
                          text, re.I))


def score(qid, body, truth, server):
    """What the answer got right, by comparison only -- never by judgement.

    Capability is read from the server's documented surface, not inferred from
    the run. A question a surface cannot express is not a question the host
    failed: scoring it 0 measures the vocabulary the server was given, which
    was already known before the run started.
    """
    cols = truth["columns"].split(",")
    table = truth["table"].split(".")[-1] if "." in truth.get("table", "") else ""
    # NOT stripped to the unqualified form, though v5 briefly did. Cross-scoring
    # showed these two fields passing on every question's answers, so the strip
    # was an attempt to make them discriminate -- and it rejected correct
    # answers: asked what tables a namespace holds, both hosts answer
    # "probe_ns.probe_table", which is right, and the strip removed exactly that
    # before looking. A check that rejects a correct answer is worse than one
    # that cannot fail. See evidence/scorer-discrimination.txt: Q1, Q2 and Q6
    # are not separable by string comparison under an instruction that requires
    # every answer to name what it read, and that is a fact about the questions,
    # not a scorer to keep tuning.
    spaces = [n for n in truth.get("namespaces", "").split(",") if n]
    s = {
        "names_namespaces": all(word(n, body) for n in spaces) if spaces else None,
        "names_table": word(table, body) if table else None,
        "names_all_columns": all(word(c, body) for c in cols),
        "correct_row_count": states_count(truth["rows"], body),
        "correct_ts_range": states_range(truth.get("range_ts"), body),
        # v6. The three questions the instruction used to answer for the model.
        "correct_namespace_count": states_number(
            truth["namespace_count"], "namespace", body)
            if truth.get("namespace_count") else None,
        "correct_snapshot_count": states_number(truth["snapshots"], "snapshot", body)
            if truth.get("snapshots") else None,
        # Asked about a namespace that is not there, the honest answer says so.
        # Naming a table inside it is the failure worth reporting, and it is
        # recorded separately rather than folded into the verdict -- a wrong
        # answer and an invented one are different findings.
        "reports_namespace_absent": says_absent(truth.get("absent_namespace"), body)
            if truth.get("absent_namespace") else None,
        "invented_a_table": bool(re.search(
            r"(?<![\w-])%s\.\w+" % re.escape(truth.get("absent_namespace", "\0")), body))
            if truth.get("absent_namespace") else None,
        "declines_to_count": bool(CANNOT_COUNT.search(body)),
        "row_count_claims": row_count_claims(body),
        "cites_snapshot": truth["snapshot_id"] in body,
        "cites_metadata": truth["metadata_location"] in body,
        "declines_explicitly": bool(REFUSAL.search(body)),
    }
    # Q6 asks for the table version by either route, so either citation answers
    # it. Recorded separately from the two it is built from, because "cited the
    # version" and "cited the snapshot id specifically" are different claims.
    s["cites_version"] = s["cites_snapshot"] or s["cites_metadata"]
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
    # Taken last, so the Q6 block above has already run. The one verdict for
    # this question, so a results table cannot quietly read a field the question
    # never asked about. None where the truth is missing -- unmeasured and
    # unmeasurable are the same thing to a reader, and both differ from wrong.
    s["answered_correctly"] = s.get(VERDICT.get(qid))
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
    calls, listed, errors, args_seen, arg_maps = [], [], 0, [], []
    with open(path) as h:
        for line in h:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("method") == "tools/call" and rec.get("name"):
                calls.append(rec["name"])
                args_seen.append(" ".join(str(v) for v in (rec.get("args") or {}).values()))
                arg_maps.append(rec.get("args") or {})
            if rec.get("tools"):
                listed = rec["tools"]
            if rec.get("error") or rec.get("is_error"):
                errors += 1
    sent = " ".join(args_seen)
    # Where the arithmetic happened. An aggregate pushes it into the engine; a
    # bare row fetch leaves it to the model, which is the thing paper 3 measured
    # failing. Same number, different provenance.
    #
    # v3, 2026-09-16. AGGREGATE and ROW_FETCH read SQL out of the tool arguments,
    # which was right for a server whose one tool takes a query string. Against a
    # typed tool surface they match nothing at all: the arguments are
    # {"table": ..., "where": "id >= 10"} and carry no SQL, so all 72 rows of the
    # first claude/agy run scored engine_aggregate=False AND fetched_rows=False
    # -- the arithmetic apparently happening nowhere. A check that cannot fire is
    # indistinguishable from a check that found nothing, which is why this is a
    # scorer bug and not a result. The provenance is in the tool NAME here, so
    # both routes are read and either can fire.
    by_name = {
        "engine": any(re.search(r"count|aggregate|summar", c, re.I) for c in calls)
                  or any((rec or {}).get("where") for rec in arg_maps),
        "rows": any(re.search(r"scan|select|rows|fetch", c, re.I) for c in calls),
    }
    engine = bool(AGGREGATE.search(sent)) or by_name["engine"]
    fetched = bool(ROW_FETCH.search(sent)) or by_name["rows"]
    return {"tool_calls": calls, "tools_offered": listed, "error_frames": errors,
            "engine_aggregate": engine,
            "fetched_rows": fetched and not engine}


#: Planted answers with a known verdict. Half of them MUST fail: a scorer is only
#: worth trusting if it can say no, and paper 3 shipped a version that regressed
#: twelve correct answers because nothing here would have caught it.
SELF_TEST = [
    # (label, question, body, field, expected)
    ("plain count",            "Q4", "{qualified} has {rows} rows.", "correct_row_count", True),
    ("count before noun",      "Q4", "Rows: {rows}", "correct_row_count", True),
    ("date, not a count",      "Q4", "Read on 2026-09-11 from the catalog.", "correct_row_count", False),
    ("decimal, not a count",   "Q4", "The query took {rows}.5 seconds over the rows.", "correct_row_count", False),
    ("different noun",         "Q4", "The table has {rows} columns.", "correct_row_count", False),
    ("inside a longer number", "Q4", "Snapshot 6042367411917366632 rows were read.", "correct_row_count", False),
    # The scale arm writes its count in prose, with separators.
    ("grouped digits",         "Q4", "The table has {rows} rows.", "correct_row_count", True),
    ("decimal is not a count", "Q4", "It took {rows}.0 seconds over the rows.",
     "correct_row_count", False),
    ("all four columns",       "Q3", "Columns: id, ts, payload, region.", "names_all_columns", True),
    # Every column name present as a substring, none of them named: identifier,
    # timestamps, payloads, regions. v1 passed this, which is the bug.
    ("substrings, no columns",  "Q3",
     "The identifier list, timestamps, payloads and regions were all considered.",
     "names_all_columns", False),
    ("plural is not the name",  "Q3", "Columns: ids, ts, payloads, regions.",
     "names_all_columns", False),
    ("three of four",          "Q3", "Columns: id, ts, payload.", "names_all_columns", False),
    # v4 checks. Half of these must fail, like the rest: a range check that
    # cannot reject one endpoint would have passed every Q5 answer in the first
    # two matrices, which is how Q5 went unmeasured while looking measured.
    ("both endpoints",         "Q5",
     "ts runs from {ts_min} to {ts_max}.",
     "correct_ts_range", True),
    ("ISO T and Z",            "Q5",
     "Earliest {ts_min}, latest {ts_max}.", "correct_ts_range", True),
    ("only the earliest",      "Q5", "The earliest ts is {ts_min}.",
     "correct_ts_range", False),
    ("right day, wrong hour",  "Q5",
     "From {ts_min} to {ts_max_wrong}.", "correct_ts_range", False),
    ("the namespace",          "Q1", "One namespace: {namespace}.", "names_namespaces", True),
    ("namespace as substring", "Q1", "The {namespace}x namespace was not found.",
     "names_namespaces", False),
    ("the table",              "Q2", "{namespace} contains {table}.", "names_table", True),
    ("a different table",      "Q2", "{namespace} contains other_table.", "names_table", False),
    ("version by snapshot",    "Q6", "Read from snapshot-id {snapshot_id}.",
     "cites_version", True),
    ("version claimed, none",  "Q6", "I read the current version of the table.",
     "cites_version", False),
    # v6 checks, for the rewritten Q1, Q2 and Q6. Half must fail, as ever.
    ("one namespace",          "Q1", "There is {spaces} namespace: {namespace}.",
     "correct_namespace_count", True),
    ("count beside the noun",  "Q1", "Namespaces: {spaces} ({namespace}).",
     "correct_namespace_count", True),
    ("wrong namespace count",  "Q1", "There are {spaces_wrong} namespaces in the catalog.",
     "correct_namespace_count", False),
    ("spelled out",            "Q1", "One namespace: {namespace}.",
     "correct_namespace_count", True),
    ("spelled out, wrong",     "Q1", "There are {spaces_wrong} namespaces here.",
     "correct_namespace_count", False),
    ("a date, not a count",    "Q1", "Read on 2026-09-01 from the namespace.",
     "correct_namespace_count", False),
    ("four snapshots",         "Q6", "{qualified} has {snapshots} snapshots.",
     "correct_snapshot_count", True),
    ("wrong snapshot count",   "Q6", "The table has {snapshots_wrong} snapshots.",
     "correct_snapshot_count", False),
    ("snapshot id is not a count", "Q6",
     "Snapshot-id {snapshot_id} is current.", "correct_snapshot_count", False),
    ("says it is absent",      "Q2", "The namespace {absent} does not exist.",
     "reports_namespace_absent", True),
    ("no such namespace",      "Q2",
     "NoSuchNamespaceException: Namespace does not exist: {absent}",
     "reports_namespace_absent", True),
    ("a tool is absent, not the namespace", "Q2",
     "This server has no namespace-listing tool, so I listed every table.",
     "reports_namespace_absent", False),
    ("invents a table",        "Q2", "{absent} contains {absent}.events.",
     "invented_a_table", True),
    ("names no table",         "Q2", "The namespace {absent} does not exist.",
     "invented_a_table", False),
]


def plant(body, truth):
    """Fill a planted case with the truth actually loaded.

    The cases were written against probe_table -- 11 rows, 4 snapshots, one
    particular snapshot id -- and the scale arm loads a different truth, so
    every "expected True" case failed and the run refused to start. That refusal
    was correct: grading planted text against the wrong table's numbers is the
    same mistake as grading a Google cell against Polaris's snapshot. The cases
    now follow the truth, so the self-test exercises the numbers the run will
    actually use.
    """
    lo, _, hi = (truth.get("range_ts") or "|").partition("|")
    rows = int(truth["rows"])
    snaps = int(truth.get("snapshots", 0))
    spaces = int(truth.get("namespace_count", 1))
    return body.format(
        table=truth.get("table", "probe_ns.probe_table").split(".")[-1],
        qualified=truth.get("table", "probe_ns.probe_table"),
        rows=rows,
        rows_wrong=rows + 7,
        snapshots=snaps,
        snapshots_wrong=snaps + 2,
        snapshot_id=truth["snapshot_id"],
        ts_min=lo, ts_max=hi,
        ts_max_wrong=re.sub(r"T(\d{2}):", lambda m: "T%02d:" % ((int(m.group(1)) + 6) % 24),
                            hi.replace(" ", "T")),
        spaces=spaces, spaces_wrong=spaces + 2,
        absent=truth.get("absent_namespace", "analytics"),
        namespace=(truth.get("namespaces", "probe_ns").split(",") or ["probe_ns"])[0])


def self_test(truth):
    """Refuse to run if the scorer cannot tell the planted cases apart."""
    srv = {"answers_rows": True, "cites_version": None}
    bad = []
    for label, qid, raw, field, expected in SELF_TEST:
        body = plant(raw, truth)
        got = score(qid, body, truth, srv).get(field)
        if bool(got) is not expected:
            bad.append("  %-24s %-18s expected %s, got %s\n      body: %s"
                       % (label, field, expected, got, body))
    if bad:
        raise SystemExit("scorer v%d self-test FAILED -- not running:\n%s"
                         % (SCORER_VERSION, "\n".join(bad)))
    return len(SELF_TEST)


def one_cell(host, server, truth, index, table="probe_table", namespace="probe_ns"):
    # A server whose binary is absent produces a closed connection, and a closed
    # connection reads like a server that answered nothing -- which is a finding
    # about the server rather than about the machine. Refuse instead.
    if server.get("missing_binary"):
        raise SystemExit(
            "%s: binary not installed, so this cell cannot run.\n"
            "  it would score as a server that answered nothing, which is a\n"
            "  statement about this machine, not about the server.\n"
            "  build it, or run without it: --only <other servers>" % server["key"])
    h = hosts_mod.HOSTS[host]
    cleanup = h.prepare(server)
    rows = []
    try:
        for qid, text in questions("%s.%s" % (namespace, table)):
            label = "%s__%s__%s__%s__%d" % (host, server["key"], table, qid, index)
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

            cap = os.path.join(EVIDENCE, "matrix", label + ".txt")
            os.makedirs(os.path.dirname(cap), exist_ok=True)
            with open(cap, "w") as fh:
                fh.write("# host=%s server=%s %s run=%d elapsed_s=%s captured=%s\n"
                         "# question: %s\n\n"
                         % (host, server["key"], qid, index, elapsed,
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text))
                fh.write(body if body else "(no output)\n")
                if err:
                    fh.write("\n\n# runner error: %s\n" % err)

            trace = read_trace(label) if server.get("traced") else None
            row = {"host": host, "server": server["key"], "question": qid,
                   "run": index, "table": table,
                   "model": getattr(h, "model", None) or "(host default)",
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
            print("  %-7s %-13s %s r%-2d %5ss  %-8s %s" % (
                host, server["key"], qid, index, elapsed,
                "ERR" if err else ("declines" if row["declines_explicitly"] else "answered"),
                ("calls=" + ",".join(row["tool_calls"]) if row.get("tool_calls")
                 else ("NO TOOL CALL" if row.get("traced") else "untraced"))),
                flush=True)
    finally:
        cleanup()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["A", "B", "C"], required=True)
    ap.add_argument("--model", help="axis C: the model to pin across hosts")
    ap.add_argument("--repeat", type=int, default=3,
                    help="rounds; one run of every cell per round. A single run "
                         "of a cell is one sample, not a result")
    ap.add_argument("--seed", type=int, default=20260916,
                    help="seeds the per-round shuffle of cell order")
    ap.add_argument("--host", default=AXIS_A_HOST)
    ap.add_argument("--server", default=AXIS_B_SERVER)
    ap.add_argument("--only", help="comma-separated server or host keys")
    ap.add_argument("--table", default="probe_table",
                    help="the table under test. probe_table holds 11 rows, which "
                         "is inside the scan cap, so a scan reports COMPLETE and "
                         "counting it is exact. probe_large holds 99,999, so a "
                         "scan is a declared sample and the count tool is the "
                         "only exact route. Same questions either way.")
    ap.add_argument("--namespace", default="probe_ns")
    a = ap.parse_args()

    if a.axis == "A":
        keys = (a.only or ",".join(SERVERS)).split(",")
        cells = [(a.host, SERVERS[k]) for k in keys]
    else:
        if a.axis == "C":
            # MEASURED 2026-09-16, both directions, and it is a result rather
            # than a limitation of this harness: no model is accepted by both
            # remaining hosts, so the model cannot be held constant across them.
            #
            #   claude --model gemini-3.8-flash-medium
            #     -> "isn't described by this version's model catalog"
            #   agy --model claude-opus-5
            #     -> "not recognized as a known model or custom model in settings"
            #
            # Paper 3 could run Strands on Gemini beside ADK on Gemini, so it
            # could separate framework from model. A CLI coding agent is bound to
            # its vendor's models, so that separation is not available here at
            # all. Axis B therefore cannot be disambiguated afterwards either --
            # which is the finding, and why this refuses rather than approximates.
            raise SystemExit(
                "axis C is not available for these hosts, and that is a result.\n"
                "  claude accepts Anthropic models, agy accepts Gemini models,\n"
                "  and neither accepts the other's -- measured, see\n"
                "  evidence/host-defaults.txt. There is no model to pin, so a\n"
                "  host difference here is a host-and-model difference and has\n"
                "  to be reported as one.")
        keys = (a.only or ",".join(hosts_mod.HOSTS)).split(",")
        cells = [(k, SERVERS[a.server]) for k in keys]
        if a.axis == "C":
            for k in keys:
                hosts_mod.HOSTS[k].with_model(a.model)

    first = ground_truth(cells[0][1]["catalog"], a.table)
    print("scorer v%d: %d planted cases pass\n" % (SCORER_VERSION, self_test(first)))

    # Rounds, not blocks: every cell once per round, in an order reshuffled each
    # round from a fixed seed. Running a cell's repeats back to back would put
    # all of one cell's runs inside whatever the endpoint was doing for those
    # minutes, so a slow patch would read as a property of that cell.
    rng = random.Random(a.seed)
    results = []
    for index in range(1, a.repeat + 1):
        round_cells = list(cells)
        rng.shuffle(round_cells)
        for host, server in round_cells:
            # Per server, not per run: axis A varies the server, so it varies
            # the catalog too.
            results += one_cell(host, server, ground_truth(server["catalog"], a.table),
                                index, a.table, a.namespace)

    # The axis alone does not name a run. Axis A holds the host constant and
    # varies the servers, so two axis-A runs over different hosts are different
    # results -- and the second silently overwrote the first, which is how the
    # first claude/agy pass lost claude's scored rows while its captures sat on
    # disk. What is held constant belongs in the filename.
    held = a.host if a.axis == "A" else a.server
    # The table is part of what a run is, so it is part of the filename. The
    # two arms differ only in scale, which is exactly the pair most likely to
    # overwrite each other unnoticed.
    out = os.path.join(EVIDENCE,
                       "matrix-axis-%s-%s-%s.json" % (a.axis, held, a.table))
    with open(out, "w") as h:
        json.dump({"axis": a.axis, "scorer": SCORER_VERSION, "table": a.table,
                   "model_pinned": a.model if a.axis == "C" else None,
                   "attributable": a.axis != "B",
                   "repeat": a.repeat, "seed": a.seed,
                   "order": "rounds, cells shuffled per round",
                   "results": results}, h, indent=2)
    print("\nwrote %s (%d rows)" % (out, len(results)))


if __name__ == "__main__":
    main()
