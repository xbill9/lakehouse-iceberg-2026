# -*- coding: utf-8 -*-
"""Why Strands on Nova Micro missed the Test 5 count, from the captures.

Writes ``nova-diagnosis.txt`` into the raw evidence directory, scored with the
matrix scorer, from the diagnostic captures under ``nova-diagnosis-captures/``.
``--direct`` first re-runs the direct Bedrock calls (section 1) into that
directory; the agent runs (section 2) come from ``run_once.py`` with
``ICEBERG_TOOL_TRACE=1`` and the settings named beside each set.

Every number in that file is produced here. None is typed in.
"""
import argparse
import glob
import json
import os
import re
import time

import run_matrix as rm

CAPTURES = os.path.join(rm.RAW, "nova-diagnosis-captures")
OUT = os.path.join(rm.RAW, "nova-diagnosis.txt")
MODEL = "us.amazon.nova-micro-v1:0"

#: The probe table on the control, as the scan returned it.
ROWS = [(0, 1, 0, 0), (2, 1, 2, 0), (3, 1, 3, 0), (20, 1, 0, 2), (21, 1, 1, 2), (22, 1, 2, 2),
        (23, 1, 3, 2), (10, 2, 0, 1), (11, 2, 1, 1), (12, 2, 2, 1), (13, 2, 3, 1)]
TAIL = ("\n11 row(s), read from snapshot-id 5653331815319537848\nCOMPLETE: these are all 11 rows "
        "in this snapshot (total-records 11), so values, maxima and counts read from them are "
        "exact for snapshot-id 5653331815319537848.")
FALSE_NOTE = ("\nNOTE: you asked for 10000 rows and this tool returns at most 100, so the rows "
              "above are a SAMPLE, not the whole table.")
QUESTION = ("\n\nUsing only the scan result above: what is the largest id, and how many rows "
            "have an id of 10 or more?")
GREEDY = {"inferenceConfig": {"temperature": 0},
          "additionalModelRequestFields": {"inferenceConfig": {"topK": 1}}}


def table(rows):
    return "id | ts | payload | region\n" + "\n".join(
        "%d | 2026-09-0%d 0%d:00:00+00:00 | row-%d-%d | None" % (i, d, h, b, h)
        for i, d, h, b in rows) + "\n"


def id_column(rows):
    return "id\n" + "\n".join(str(r[0]) for r in rows) + "\n"


def direct_variants(instruction):
    """(file, variant, label, system prompt, user text, extra request fields, repeats)"""
    ids = ", ".join(str(r[0]) for r in ROWS)
    inline = "Here are 11 id values: %s. " % ids
    sents = [s.strip() for s in re.split(r"(?<=\.) (?=[A-Z])", instruction)]

    def drop(*keys):
        return " ".join(s for s in sents if not any(k in s for k in keys))

    full = table(ROWS) + TAIL + QUESTION
    return [
        ("results", "plain", "ids inline, no system prompt", None,
         inline + "How many of them are 10 or more? Answer with the number.", {}, 10),
        ("results", "list-first", "ids inline, list them first", None,
         inline + "List every value that is 10 or more, then say how many you listed.", {}, 10),
        ("results", "each", "ids inline, yes or no per id", None,
         inline + "For each value, write the value and yes or no for whether it is 10 or more. "
                  "Then count the yes answers.", {}, 10),
        ("bisect", "as-is", "scan text as the agent saw it, false SAMPLE note included", None,
         table(ROWS) + TAIL + FALSE_NOTE + QUESTION, {}, 10),
        ("bisect", "no-false-note", "scan text, SAMPLE note removed", None, full, {}, 10),
        ("bisect", "ids-only-no-note", "scan text, id column only", None,
         id_column(ROWS) + TAIL + QUESTION, {}, 10),
        ("bisect", "as-is+instruction", "scan text with note, agent instruction as system prompt",
         instruction, table(ROWS) + TAIL + FALSE_NOTE + QUESTION, {}, 10),
        ("bisect", "no-note+instruction", "scan text, agent instruction as system prompt",
         instruction, full, {}, 10),
        ("ablate", "instr-full", "agent instruction, whole", instruction, full, {}, 10),
        ("ablate", "no-four-tools", "agent instruction without 'four'",
         instruction.replace("with four tools", "with tools"), full, {}, 10),
        ("ablate", "no-budget", "agent instruction without the budget sentence",
         drop("budget of eight"), full, {}, 10),
        ("ablate", "no-count-rule", "agent instruction without the count and scan sentences",
         drop("To answer how many rows", "To answer a question about the values", "Its result says"),
         full, {}, 10),
        ("ablate", "no-cite", "agent instruction without the citation sentences",
         drop("Cite every figure", "Those name an exact"), full, {}, 10),
        ("ablate", "only-first-two", "first two sentences of the agent instruction only",
         " ".join(sents[:2]), full, {}, 10),
        ("order", "stored-order", "instruction, table in stored row order", instruction, full, {}, 20),
        ("order", "sorted-by-id", "instruction, table sorted by id", instruction,
         table(sorted(ROWS)) + TAIL + QUESTION, {}, 20),
        ("order", "10-13-first", "instruction, table with ids 10 to 13 first", instruction,
         table([r for r in ROWS if 10 <= r[0] < 20] + [r for r in ROWS if not 10 <= r[0] < 20])
         + TAIL + QUESTION, {}, 20),
        ("format", "table", "instruction, full table", instruction, full, {}, 20),
        ("format", "id-column", "instruction, id column only", instruction,
         id_column(ROWS) + TAIL + QUESTION, {}, 20),
        ("format", "comma-list", "instruction, ids as a comma list", instruction,
         "id values: %s\n" % ids + TAIL + QUESTION, {}, 20),
        ("format", "table+greedy", "instruction, full table, temperature 0 topK 1", instruction,
         full, GREEDY, 20),
        ("format", "id-column+greedy", "instruction, id column, temperature 0 topK 1", instruction,
         id_column(ROWS) + TAIL + QUESTION, GREEDY, 20),
    ]


AGENT_SETS = [
    ("nova-trace", "Nova, v1 scan (rows only, SAMPLE note bug), default decoding"),
    ("nova-trace-t0", "Nova, v1 scan, temperature 0"),
    ("nova-trace-readall", "Nova, v1 scan, neutral limit wording"),
    ("fixed-default", "Nova, v1 scan with the SAMPLE note fixed"),
    ("fixed-readall", "Nova, v1 scan fixed, neutral limit wording"),
    ("fixed-nova-greedy", "Nova, v1 scan fixed, temperature 0 topK 1"),
    ("filter2-nova", "Nova, v2 scan (engine filter, exact COUNT/MIN/MAX), default decoding"),
    ("filter2-nova-greedy", "Nova, v2 scan, temperature 0 topK 1 -- the published setup"),
    ("readall-adk", "ADK on Gemini, v1 scan, neutral limit wording"),
    ("readall-strands-gemini", "Strands on Gemini, v1 scan, neutral limit wording"),
    ("filter2-adk", "ADK on Gemini, v2 scan"),
    ("filter2-strands-gemini", "Strands on Gemini, v2 scan"),
    ("filter2-af", "Agent Framework on gpt-5-mini, v2 scan"),
]


def run_direct() -> None:
    import concurrent.futures
    import boto3
    from iceberg_tool import INSTRUCTION

    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    os.makedirs(os.path.join(CAPTURES, "nova-count"), exist_ok=True)
    jobs = [(v, i) for v in direct_variants(INSTRUCTION) for i in range(v[6])]

    def call(job):
        (_, _, _, system, text, extra, _), _ = job
        kwargs = dict(extra, **({"system": [{"text": system}]} if system else {}))
        for _attempt in range(6):
            try:
                reply = client.converse(modelId=MODEL, messages=[
                    {"role": "user", "content": [{"text": text}]}], **kwargs)
                return reply["output"]["message"]["content"][0]["text"]
            except Exception as exc:  # noqa: BLE001 -- Bedrock throttles; retry, then record
                error = exc
                time.sleep(4)
        return "FAILED %s" % error

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(call, jobs))
    files = {}
    for ((fn, variant, _, system, text, extra, _), _), answer in zip(jobs, answers):
        files.setdefault(fn, []).append(json.dumps(
            {"variant": variant, "system": system, "prompt": text, "extra": extra, "answer": answer}))
    for fn, lines in files.items():
        with open(os.path.join(CAPTURES, "nova-count", fn + ".jsonl"), "w") as handle:
            handle.write("\n".join(lines) + "\n")


BARE = ("Here are 11 id values: %s. How many of them are 10 or more? Answer with just "
        "the number." % ", ".join(str(r[0]) for r in ROWS))


def run_bare(repeats: int = 20) -> None:
    """The counting question with no agent, no tools and no instruction: the model,
    the eleven ids, one API call. It is the answer to "is this the harness?" -- a
    reader can paste the prompt into a console and see the same thing."""
    import concurrent.futures
    import boto3
    from google import genai

    bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    vertex = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                          location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))

    def ask(job):
        model, _ = job
        for _attempt in range(6):
            try:
                if model.startswith("gemini"):
                    return model, (vertex.models.generate_content(model=model, contents=BARE).text or "").strip()
                reply = bedrock.converse(modelId=model, messages=[
                    {"role": "user", "content": [{"text": BARE}]}])
                return model, reply["output"]["message"]["content"][0]["text"].strip()
            except Exception as exc:  # noqa: BLE001 -- throttling; retry, then record
                error = exc
                time.sleep(4)
        return model, "FAILED %s" % error

    jobs = [(m, i) for m in (MODEL, "gemini-2.5-flash") for i in range(repeats)]
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        answers = list(pool.map(ask, jobs))
    os.makedirs(os.path.join(CAPTURES, "bare-count"), exist_ok=True)
    with open(os.path.join(CAPTURES, "bare-count", "answers.jsonl"), "w") as handle:
        for model, answer in answers:
            handle.write(json.dumps({"model": model, "prompt": BARE, "answer": answer}) + "\n")


def bare_section(truth: dict) -> list:
    path = os.path.join(CAPTURES, "bare-count", "answers.jsonl")
    if not os.path.exists(path):
        return []
    by_model, stated = {}, {}
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            digits = re.findall(r"\d+", row["answer"])
            value = digits[-1] if digits else "no number"
            by_model.setdefault(row["model"], []).append(value == truth["ids_at_least_10"])
            stated.setdefault(row["model"], {}).setdefault(value, 0)
            stated[row["model"]][value] += 1
    out = ["", "## 4. The same question with no agent, no tools and no instruction",
           "#  One API call per run: the eleven ids in the prompt, "
           "\"how many of them are 10 or more?\"",
           "#  " + BARE]
    for model, results in by_model.items():
        counts = ", ".join("%s x%d" % kv for kv in sorted(stated[model].items(),
                                                          key=lambda kv: -kv[1]))
        out.append("  %2d of %2d right   %-28s answers: %s" % (sum(results), len(results), model, counts))
    return out


def thinking_section() -> list:
    """What reaches a caller in the answer text. Nova Micro writes its reasoning as
    ordinary <thinking> text and Strands passes text through, so the blocks arrive
    inside the answer; Gemini and gpt-5-mini return reasoning as a separate field.
    Counted over every published matrix capture, not over a sample."""
    answer_re = re.compile(r"<!-- cloud=.*?-->\n(.*?)\ncatalog calls:", re.S)
    carrying = hidden = 0
    echo = {"the call budget": 0, "the word \"eight\"": 0}
    for path in glob.glob(os.path.join(rm.RAW, "matrix", "*.txt")):
        with open(path) as handle:
            body = handle.read()
        found = answer_re.search(body)
        if not found or "<thinking>" not in found.group(1):
            continue
        carrying += 1
        think = " ".join(re.findall(r"<thinking>(.*?)</thinking>", found.group(1), re.S))
        visible = re.sub(r"<thinking>.*?</thinking>", "", found.group(1), flags=re.S)
        seen = set(re.findall(r"\b\d{1,3}\b", visible))
        # A count or largest id the reasoning states and the answer never shows.
        claims = re.findall(r"(?:largest|maximum|max)\b[^\d\n]{0,40}(\d{1,3})", think, re.I)
        claims += [a or b for a, b in re.findall(
            r"(\d{1,3})\s+rows?\b[^\d\n]{0,40}(?:10 or more|>= ?10)"
            r"|(?:10 or more|>= ?10)[^\d\n]{0,40}?(\d{1,3})", think, re.I)]
        hidden += any(c not in seen for c in claims)
        echo["the call budget"] += "budget" in think.lower()
        echo["the word \"eight\""] += "eight" in think.lower()
    return ["", "## 5. Reasoning that arrives inside the answer text",
            "#  Every published matrix capture. Only Nova Micro's answers carry it.",
            "  %3d answers carry <thinking> in the text a caller receives" % carrying,
            "  %3d of those state a count or largest id the visible answer never shows" % hidden,
            ] + ["  %3d echo %s from the agent's own instruction" % (n, w) for w, n in echo.items()]


def says_eight(answer: str) -> bool:
    """The matrix scorer's count patterns, for a bare answer with no stamped header."""
    body = "<!-- cloud=x model=y catalog=apache-polaris instruction=v3 catalog_calls=0 -->\n%s\ncatalog calls: 0\n"
    return rm.score_scan(body % answer, rm.ground_truth()["apache-polaris"])["correct_count"]


def summarise() -> str:
    from iceberg_tool import INSTRUCTION

    labels = {(v[0], v[1]): v[2] for v in direct_variants(INSTRUCTION)}
    truth = rm.ground_truth()["apache-polaris"]
    out = ["# Why Strands on Nova Micro missed the Test 5 count, and what changed.",
           "# Generated by iceberg-agent/nova_diagnosis.py from the diagnostic captures of",
           "# 2026-09-15, scored with the matrix scorer. All on the local Polaris control:",
           "# probe table ids %s -- largest %s, %s of them 10 or more."
           % ([r[0] for r in ROWS], truth["max_id"], truth["ids_at_least_10"]), "",
           "## 1. Nova Micro called directly (Bedrock Converse, no agent): how many ids are 10 or more"]
    for fn in ["results", "bisect", "ablate", "order", "format"]:
        by = {}
        with open(os.path.join(CAPTURES, "nova-count", fn + ".jsonl")) as handle:
            for line in handle:
                row = json.loads(line)
                by.setdefault(row["variant"], []).append(says_eight(row["answer"]))
        for variant, oks in by.items():
            out.append("  %2d of %2d right   %s" % (sum(oks), len(oks), labels[(fn, variant)]))
    out += ["", "## 2. The Strands agent on Nova Micro, and controls: 10 runs each"]
    index = lambda p: int(re.search(r"(\d+)\.txt$", p).group(1))
    for name, label in AGENT_SETS:
        runs = []
        for path in sorted(glob.glob(os.path.join(CAPTURES, name, "run-*.txt")), key=index):
            with open(path) as handle:
                body = handle.read()
            scored = rm.score_scan(body, truth)
            runs.append((bool(rm.answer_of(body).strip()), scored["correct_max_id"],
                         scored["correct_count"], "COMPLETE:" in body or "COUNT: exactly" in body))
        out.append("  answered %2d  largest id %2d  count %2d  read every row %2d  of %2d   %s"
                   % tuple([sum(r[i] for r in runs) for i in range(4)] + [len(runs), label]))
    out += ["", "## 3. Test 1 (row count and columns), Strands on Nova Micro, 10 runs each",
            "#  'last message' is what the Strands runner scored before the fix; 'whole turn'",
            "#  is every assistant message, which ADK and Agent Framework already collected."]
    for name, label in [("t1-nova-greedy", "temperature 0 topK 1"),
                        ("t1-nova-provider", "Bedrock's own defaults (no decoding fields)")]:
        runs = []
        for path in sorted(glob.glob(os.path.join(CAPTURES, name, "run-*.txt")), key=index):
            with open(path) as handle:
                body = handle.read()
            last = rm.score(body, truth)
            turn = re.sub(r"<thinking>.*?</thinking>", "", body[body.find("question:"):body.find("<!-- cloud=")],
                          flags=re.S)
            runs.append((last["correct_row_count"], last["names_all_columns"],
                         all(rm.word(c, turn) for c in truth["columns"].split(","))))
        out.append("  row count %2d  columns in last message %2d  columns in whole turn %2d  of %2d   %s"
                   % tuple([sum(r[i] for r in runs) for i in range(3)] + [len(runs), label]))
    out += bare_section(truth)
    out += thinking_section()
    out += ["", "## What changed in the harness",
            "  - The Strands runner scored only the last assistant message; it now takes every",
            "    assistant message of the turn, as the other two frameworks' runners did (section 3).",
            "  - The v1 scan printed 'the rows above are a SAMPLE' whenever a model asked for",
            "    more than 100 rows, beside the COMPLETE line of an 11-row table. Fixed; on its",
            "    own it did not change Nova's count (section 2).",
            "  - The v2 scan filters in the engine and returns an exact COUNT, MIN and MAX. Its",
            "    filter error says what `where` accepts: models had written 'ORDER BY id DESC'.",
            "  - Nova runs with Amazon's documented tool-use decoding, temperature 0 and topK 1:",
            "    https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html",
            "", "discarded-filter-v1/ holds agent runs of a first filter-only scan, stopped when",
            "it proved to push models toward ORDER BY for the largest id; they are not scored here."]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--direct", action="store_true",
                        help="re-run the direct Bedrock calls before summarising")
    parser.add_argument("--bare", action="store_true",
                        help="re-run the no-agent counting question on both models")
    args = parser.parse_args()
    if args.direct:
        run_direct()
    if args.bare:
        run_bare()
    text = summarise()
    with open(OUT, "w") as handle:
        handle.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
