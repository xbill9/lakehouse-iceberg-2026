#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the same question across a matrix of legs and catalogs, N times each.

A single run of each leg proves the wiring works and nothing else. It cannot
say whether a difference between two legs is a property of the framework, of
the model, or of the catalog, because a one-run-per-leg layout moves all three
at once -- and it cannot say whether a result is stable.

So this runs four axes separately:

  axis A   catalog fixed, legs vary      -> isolates framework and model
  axis B   leg fixed, catalogs vary      -> isolates the catalog
  axis C   model fixed, framework varies -> separates framework from model
  axis D   each leg on its own catalog, a question only a data scan answers
  axis E   axis D's question for every framework and model on one table, and each
           with the rows-only scan, so counting in the engine and in the model compare
  axis F   axis A's question for Nova Micro with and without its tool-use decoding

with repetition in both, and scores every answer against ground truth read from
the catalog itself rather than through any agent.

    python3 run_matrix.py --axis A --repeat 3
    python3 run_matrix.py --axis B --repeat 3 --leg gcp
"""
import argparse
import json
import random
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
#: Axis D: every leg on its own cloud's catalog, asked something only a data scan
#: can answer. Axes A to C ask a question answered from metadata alone, so no run
#: in them ever reads a data file -- which left the storage wiring, the part of
#: this agent that does not port, exercised only by failure_modes.py. A correct
#: answer here is evidence the agent read GCS, S3 or ADLS through that wiring,
#: including on the leg whose tool calls cannot be seen.
SCAN_QUESTION = ("What is the largest id in the probe table, and how many of its "
                 "rows have an id of 10 or more? Cite the exact table version you read.")
AXIS_D_CELLS = [("gcp", "google-lakehouse"), ("aws", "aws-glue"),
                ("azure", "microsoft-onelake")]
#: Axis E: Axis D's data question for every framework and model, on the same
#: local table. Axis D's legs read different catalogs, and OneLake's table is
#: smaller (4 of 6 ids to count, against 8 of 11), so its correctness column is
#: not like-for-like. Axis E is -- and with Strands on Gemini beside Strands on
#: Nova Micro, a miscount can be put on the framework or on the model.
#: A variant is one environment change on a cell, named in its capture and label.
#: rows-only restores the v1 scan -- rows and no computed count -- so the model has to
#: count them itself. provider-decoding sends Nova Micro no decoding fields at all.
#: rows-only carries ICEBERG_SCAN_DOC=read-all so the only difference from the
#: published scan is who counts. Without it the v1 scan's docstring says "keep the
#: limit small", and the model reads part of the table: MEASURED 2026-09-15 over 30
#: Nova Micro runs at Bedrock's defaults, 8 scanned with limit 0, 5 or 10 and never
#: saw every row, which is this harness talking, not the model's arithmetic.
VARIANTS = {"rows-only": {"ICEBERG_SCAN_FILTER": "0", "ICEBERG_SCAN_DOC": "read-all"},
            "provider-decoding": {"ICEBERG_DECODING": "provider"},
            "rows-only-provider-decoding": {"ICEBERG_SCAN_FILTER": "0",
                                            "ICEBERG_SCAN_DOC": "read-all",
                                            "ICEBERG_DECODING": "provider"}}
E_SETUPS = [("gcp", None), ("aws", "gemini-2.5-flash"), ("aws", None), ("azure", None)]
#: Nova Micro's greedy cells return one answer, word for word, in all ten runs, so
#: each is a single sample repeated; its two provider-decoding cells are the ones
#: whose ten runs are ten samples. MEASURED 2026-09-15 on the previous Axis E.
AXIS_E_CELLS = ([(leg, model, None) for leg, model in E_SETUPS]
                + [(leg, model, "rows-only") for leg, model in E_SETUPS]
                + [("aws", None, "provider-decoding"), ("aws", None, "rows-only-provider-decoding")])
#: Axis F: Axis A's question for Nova Micro as published (Amazon's tool-use decoding)
#: and at Bedrock's defaults, in one sitting, so the decoding's effect on the Axis A
#: and C timings is measured rather than assumed.
AXIS_F_CELLS = [("aws", None, None), ("aws", None, "provider-decoding")]
TOKENS = re.compile(r"tokens: input=(\S+) output=(\S+) reasoning=(\S+) model_calls=(\S+)")


def token_fields(body: str) -> dict:
    """Tokens and model calls from a capture's tokens line; None where absent."""
    m = TOKENS.search(body)
    as_int = lambda v: None if v in ("None", "n/a") else int(v)  # noqa: E731
    keys = ("input_tokens", "output_tokens", "reasoning_tokens", "model_calls")
    return dict(zip(keys, (as_int(v) for v in m.groups()))) if m else dict.fromkeys(keys)
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
#: v3 (2026-09-15) widens the Axis D max-id window from 25 to 60 characters.
#: MEASURED on Axis D's first run: 'The largest id in the "probe_ns.probe_table" is
#: 23.' put 36 characters between the word and the value, and v2 marked a correct
#: answer wrong. Axes A to C score identically under v2 and v3.
#: v4 (2026-09-15) scores the answer with any <thinking>...</thinking> blocks
#: removed. Strands prints Nova Micro's reasoning inside the final answer, so a
#: value that appeared only in the reasoning could pass a check. MEASURED on Axis
#: D: one Strands answer stated in its visible text that it "cannot confirm this
#: as the largest 'id' in the table", and passed the max-id check on its
#: <thinking> block alone.
#: v5 (2026-09-15) widens the row-count window from 40 to 90 characters.
#: MEASURED on the ten-repeat run: "The exact number of rows in this table, as of
#: snapshot-id 5653331815319537848, is 11." put the snapshot id between the word
#: and the count, and v4 marked a correct answer wrong. It also ended "is 11.",
#: and a full stop after the count was read as a decimal point.
#: v6 (2026-09-15) pairs values across blanked citations and markdown emphasis.
#: v7 (2026-09-15) scores the answer's LAST statement of a count or largest id, so a
#: right number mentioned on the way cannot pass a different final one. Answers now
#: span the whole turn, which makes that possible.
#: v8 (2026-09-15) allows 60 characters on one line between "10 or more" and the
#: count, not 30. MEASURED on Axis E: "Number of rows with id >= 10 (same snapshot
#: and metadata): 8." put 31 between them, and v7 marked a correct count wrong.
#: v9 (2026-09-15) does not take the first of a list of ids as the final count.
#: MEASURED on Axis E: "There are 8 rows with an id of 10 or more: 20, 21, 22, 23,
#: 10, 11, 12, 13." -- v8 read the 20 after the colon as the count and scored a
#: correct answer wrong.
#: v10 (2026-09-15) reads a value stated as a bullet -- "- Largest id in the table:
#: 23." -- as the answer's statement of it. MEASURED on Axis E: one Agent Framework
#: answer laid its results out that way and v9 scored a correct largest id wrong.
SCORER_VERSION = 10
#: Recorded in every matrix file, so an archived run says which harness produced it.
SCAN_TOOL = "v2: filters in the engine; exact COUNT, MIN and MAX over every matching row"
DECODING = "provider defaults; Nova greedy (temperature 0, topK 1) per Amazon's tool-use guidance"
ANSWER = re.compile(r"<!-- cloud=.*?-->\n(.*?)\ncatalog calls:", re.S)


def answer_of(body: str) -> str:
    """The text after the stamped header -- not the question, the thinking or the tool log."""
    m = ANSWER.search(body)
    return re.sub(r"<thinking>.*?</thinking>", "", m.group(1), flags=re.S) if m else ""


def word(name: str, text: str) -> bool:
    """`name` as a whole identifier: not inside snapshot-id, not inside exists."""
    return bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text))


NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
AT_LEAST_10 = r"(?:10 or more|10 or greater|10 or higher|10 and above|at least 10|>= ?10|\u2265 ?10)"


def score_scan(body: str, truth: dict) -> dict:
    """Axis D: each value must sit next to its own wording, so a swapped answer
    ("the largest id is 8, and 23 rows...") fails both checks. \\D spans cannot
    cross another number, which is what keeps the pairing honest."""
    header = re.search(r"catalog_calls=(\d+)", body)
    answer = answer_of(body)
    # The citations the instruction asks for sit between a wording and its value
    # ("the largest id, read from metadata-location file:/.../00006-...json and
    # snapshot-id 5653..., is 23"), and their digits stopped the \D span. Blank
    # them for pairing only; cites_snapshot still reads the answer as written.
    paired = re.sub(r"(?:file|s3a?|gs|abfss?)://?\S+|\b\d{12,}\b", " ", answer)
    # Markdown emphasis too: "`id` is `10` or more is `8`" never matched "10 or more".
    paired = re.sub(r"[`*_]", "", paired)

    def token(value: str) -> str:
        alts = [re.escape(value)]
        if value.isdigit() and int(value) < len(NUMBER_WORDS):
            alts.append(NUMBER_WORDS[int(value)])
        # A full stop ends a sentence; only a stop followed by a digit is a decimal.
        # Caught by the scorer's own test: "Maximum id: 23." failed as (?![\w.-]).
        return r"(?<![\w.-])(?:%s)(?![\w-]|\.\d)" % "|".join(alts)

    mx, n = token(truth["max_id"]), token(truth["ids_at_least_10"])
    count_patterns = [
        r"%s\D{0,15}\brows?\b" % n,                  # 8 rows
        r"%s\s+of\s+(?:the\s+)?\d+\s+rows?\b" % n,   # 8 of the 11 rows
        r"%s\D{0,40}%s" % (n, AT_LEAST_10),            # 8 rows have an id of 10 or more
        # 60 on one line, not 30: "id >= 10 (same snapshot and metadata): 8" is 31.
        r"%s[^\d\n]{0,60}%s" % (AT_LEAST_10, n),       # 10 or more: 8
    ]
    # The last value the answer states, from phrasings that can only be the filtered
    # count: "8 of the 11 rows", "8 rows ... 10 or more" on one line, "10 or more: 8",
    # and "the largest id is 23". A right value that is not the last one fails.
    # Tight on purpose. A first draft took any number within 40 characters of "10 or
    # more" and, on the published captures, read the largest id on the line above
    # ("23.\n- Number of rows with id >= 10: 8") and a list of the ids ("10 or more
    # (20, 21, ...)") as final counts -- three correct answers scored wrong.
    num = r"(?<![\w.-])(\d+|%s)(?![\w-]|\.\d)" % "|".join(NUMBER_WORDS)
    as_digits = lambda s: s if s.isdigit() else str(NUMBER_WORDS.index(s.lower()))  # noqa: E731

    def last_stated(patterns, reject=None):
        found = [(m.end(), as_digits(m.group(1))) for p in patterns
                 for m in re.finditer(p, paired, re.I)
                 if not (reject and re.search(reject, m.group(0), re.I))]
        return max(found)[1] if found else None

    last_count = last_stated([r"%s\s+of\s+(?:the\s+)?\d+\s+rows?\b" % num,
                              r"%s\s+rows?\b[^\d\n]{0,60}%s" % (num, AT_LEAST_10),
                              # Not the first of a list: "8 rows with an id of 10 or
                              # more: 20, 21, 22, ..." names the ids after the count.
                              r"%s\)?\s*(?:\([^()\d\n]{0,40}\))?\s*"
                              r"(?::|=|is|was|are|equals|number|total|count)\s*%s(?!\s*,\s*\d)"
                              % (AT_LEAST_10, num)])
    # "the largest id is 23", "Largest id in the table: 23", "max id = 23" -- the
    # model's own claim. NOT the scan's "MIN and MAX of id over those 8 rows: 10 and
    # 23", which answers quote verbatim: matching that read the MIN as the last value
    # stated and scored 12 correct answers wrong (MEASURED across the stored runs).
    # Narrow on purpose: the wording, then at most a few plain words, then the value.
    # Every widening of this pattern has cost a correct answer somewhere, because
    # answers quote the scan's own summary ("MIN/MAX of id over those 8 rows: 10 and
    # 23") and refer back to the filter ("the maximum and the count of id >= 10 are
    # exact"). A match carrying >=, MIN or MAX-of is an echo, not a claim.
    # The lookbehind matters as much as the wording: answers quote the scan's summary
    # line, "id MIN/MAX = 0 / 23", whose tail reads as "MAX = 0" on its own. Matching
    # that took the MIN as the answer's last word on the largest id.
    claim = (r"(?<!min/)(?<!min / )\b(?:largest|maximum|highest|max|biggest|greatest)\b"
             r"(?!\s*/)(?!\s+of\b)[^\d\n:=]{0,32}[ \t]*(?:is|was|=|:|equals)[ \t]+%s" % num)
    # The echo always names itself: "MIN and MAX of id = 0 and 23", "MIN/MAX over
    # those rows: 10 and 23", "id >= 10". Reject on those words rather than widening
    # the claim shape -- three spellings of the same quoted line cost three correct
    # answers, one at a time, before this covered them all.
    last_max = last_stated([claim], reject=r">=|≥|\bmin\b|/max|max\s+(?:of|over)")
    return {
        "correct_max_id": bool(re.search(
            # 150, not 60: "The largest id found in the sample from the "probe_ns.probe_table"
            # is **23**" puts 62 characters between the two, and a blanked citation
            # adds more. The \D span, not the width, is what rejects a swapped answer.
            r"\b(?:largest|maximum|highest|max|biggest|greatest)\b\D{0,150}%s" % mx, paired, re.I))
            and last_max in (None, truth["max_id"]),
        # "- Largest id in the table: 23." is a statement of the value, so it counts
        # as the last one stated. Without this the bullet read as no statement at all
        # and a later mention decided the score.
        "correct_count": any(re.search(p, paired, re.I) for p in count_patterns)
            and last_count in (None, truth["ids_at_least_10"]),
        "cites_snapshot": truth["snapshot_id"] in answer,
        "catalog_calls": int(header.group(1)) if header else None,
    }


def score(body: str, truth: dict) -> dict:
    """What the answer got right, by string and integer comparison only."""
    header = re.search(r"catalog_calls=(\d+)", body)
    answer = answer_of(body)
    cols = truth["columns"].split(",")
    n = re.escape(truth["rows"])
    return {
        "correct_row_count": bool(re.search(
            r"(?<![\w.-])%s(?![\w-]|\.\d)[^\n]{0,90}?\brows?\b|\brows?\b[^\n]{0,90}?(?<![\w.-])%s(?![\w-]|\.\d)"
            % (n, n), answer, re.I)),
        "cites_snapshot": truth["snapshot_id"] in answer,
        "cites_metadata": truth["metadata_location"] in answer,
        "names_all_columns": all(word(c, answer) for c in cols),
        # A column the fixture does not have. OneLake's table has no `region`,
        # so naming it there is an invention rather than a reading.
        "invented_column": word("region", answer) and ("region" not in cols),
        "catalog_calls": int(header.group(1)) if header else None,
    }


def one_run(axis: str, leg: str, catalog: str, index: int, model: str = None,
            question: str = QUESTION, warm: bool = True, variant: str = None) -> dict:
    # Nothing diagnostic leaks in from the shell: a cell's settings are its model and
    # its variant, and nothing else.
    env = {k: v for k, v in os.environ.items() if not k.startswith((
        "ICEBERG_MODEL", "ICEBERG_SCAN_FILTER", "ICEBERG_DECODING", "ICEBERG_TEMPERATURE",
        "ICEBERG_TOP_K", "ICEBERG_SCAN_DOC", "ICEBERG_TOOL_TRACE"))}
    env["ICEBERG_CATALOG"] = catalog
    if model:
        env["ICEBERG_MODEL_" + leg.upper()] = model
    env.update(VARIANTS.get(variant) or {})
    if axis in "DE":
        # Every tool call and its result go into the capture, so the filter an agent
        # used is on record for every framework -- Agent Framework logs no tool calls.
        env["ICEBERG_TOOL_TRACE"] = "1"
    started = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "run_once.py"), leg, question,
         "--catalog", catalog] + (["--warm"] if warm else []),
        capture_output=True, text=True, cwd=HERE, env=env, timeout=900)
    elapsed = round(time.time() - started, 1)
    body = proc.stdout + proc.stderr
    # The axis is in the name because both axes run gcp on the control. Without
    # it Axis B's captures overwrote Axis A's, and three published rows were left
    # with no capture behind them (found 2026-09-14).
    cell = "__".join([leg] + ([re.sub(r"[^\w.-]", "-", model)] if model else [])
                     + ([variant] if variant else []))
    path = os.path.join(RAW, "matrix", "%s__%s__%s__%d.txt" % (axis, cell, catalog, index))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("# axis=%s leg=%s catalog=%s run=%d elapsed_s=%s captured=%s\n\n"
                     % (axis, leg, catalog, index, elapsed,
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        handle.write(body)
    timing = re.search(r"agent seconds: ([\d.]+) \| tool seconds: ([\d.]+)", body)
    return {"leg": leg, "catalog": catalog, "run": index, "scorer": SCORER_VERSION,
            **({"model": model} if model else {}), **({"variant": variant} if variant else {}),
            "elapsed_s": elapsed, "capture": os.path.basename(path), "body": body,
            "agent_s": float(timing.group(1)) if timing else None,
            "tool_s": float(timing.group(2)) if timing else None, **token_fields(body)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis", choices=["A", "B", "C", "D", "E", "F"], required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--leg", default=AXIS_B_LEG)
    ap.add_argument("--no-warm", action="store_true", help="time sign-in inside the answer")
    ap.add_argument("--seed", type=int, default=20260915,
                    help="seeds the per-round shuffle of cell order")
    args = ap.parse_args()

    truth = ground_truth()
    if args.axis == "A":
        cells = [(leg, AXIS_A_CATALOG, None, None) for leg in LEGS]
    elif args.axis == "B":
        cells = [(args.leg, cat, None, None) for cat in CATALOGS]
    elif args.axis == "C":
        cells = [(leg, AXIS_A_CATALOG, model, None) for leg, model in AXIS_C_CELLS]
    elif args.axis == "D":
        cells = [(leg, cat, None, None) for leg, cat in AXIS_D_CELLS]
    elif args.axis == "E":
        cells = [(leg, AXIS_A_CATALOG, model, v) for leg, model, v in AXIS_E_CELLS]
    else:
        cells = [(leg, AXIS_A_CATALOG, model, v) for leg, model, v in AXIS_F_CELLS]
    question, scorer = (SCAN_QUESTION, score_scan) if args.axis in "DE" else (QUESTION, score)

    # Rounds, not blocks: one run of every cell per round, in a shuffled order, so
    # drift in endpoint load across a long sitting spreads over every cell instead
    # of landing on whichever cell happened to run while it was high.
    rng = random.Random(args.seed)
    results = []
    for index in range(1, args.repeat + 1):
        round_cells = list(cells)
        rng.shuffle(round_cells)
        for leg, catalog, model, variant in round_cells:
            row = one_run(args.axis, leg, catalog, index, model, question, not args.no_warm, variant)
            row.update(scorer(row.pop("body"), truth[catalog]))
            row["answered"] = row["catalog_calls"] is not None
            results.append(row)
            checks = " ".join("%s=%s" % (k, "ok" if v else "NO") for k, v in row.items()
                              if k.startswith(("correct_", "cites_", "names_")))
            print("  %-6s %-26s %-19s run %d  %5ss  agent=%ss tool=%ss  %s calls=%s"
                  % (leg, " ".join(x for x in (model, variant) if x), catalog, index,
                     row["elapsed_s"], row["agent_s"],
                     row["tool_s"], checks, row["catalog_calls"]), flush=True)

    out = os.path.join(RAW, "matrix-axis-%s.json" % args.axis)
    with open(out, "w") as handle:
        json.dump({"axis": args.axis, "question": question, "repeat": args.repeat,
                   "warm": not args.no_warm, "seed": args.seed,
                   "scan_tool": SCAN_TOOL, "decoding": DECODING,
                   "order": "rounds, cells shuffled per round", "results": results},
                  handle, indent=2)
    print("\nwrote %s (%d runs)" % (out, len(results)))


if __name__ == "__main__":
    main()
