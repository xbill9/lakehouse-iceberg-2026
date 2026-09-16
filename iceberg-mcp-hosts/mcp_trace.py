#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sit between a CLI host and a local MCP server, and write down every frame.

    python3 mcp_trace.py --label claude__morristai__Q4 -- iceberg-mcp

Why this exists, from paper 3. That matrix could only be defended because the
tool logged every call it received: when Nova Micro answered with a count nobody
could source, the capture showed the scan it had actually run and the filter it
had actually sent. Without that the investigation had no floor -- a wrong number
and a right number look the same in prose.

Paper 4 has the same exposure one layer down. `score()` reads the host's answer
text, so a row count the model fetched and a row count it made up score
identically, and `invented_an_answer` can only fire for servers that have no
row-returning tool. That check cannot see invention on `bigquery` or `ahodroj`,
which are exactly the cells where it would matter most.

So: the host talks to this, this talks to the server, and neither notices. MCP
stdio framing is newline-delimited JSON, so relaying line by line is lossless --
bytes are passed through unchanged and only copied aside, never rewritten. A
proxy that reformatted frames would be measuring itself.

What lands in the trace, one JSON object per line:

    {"t": 0.412, "dir": "host->server", "method": "tools/call",
     "name": "query", "args": {"sql": "SELECT COUNT(*) FROM probe_ns.probe_table"},
     "id": 3}
    {"t": 0.907, "dir": "server->host", "id": 3, "bytes": 1841, "is_error": false}

Arguments are recorded **in full**, because the argument is the measurement: a
row count produced by `SELECT COUNT(*)` and one produced by the model counting
the rows of a `SELECT *` are the same number from different places, and a length
cannot tell them apart. Credential-shaped keys are withheld and long values are
clipped. Results are recorded by size, because a result body can carry catalog
credentials; `--full` keeps those too, for a debugging run, and publish never
reads a --full trace.

Only the two local servers can be wrapped this way. `bigquery` and
`managed-spark` are remote HTTP endpoints the host dials directly, so for those
cells the trace is absent rather than empty -- a distinction the grader has to
respect, and the reason `traced` is recorded per row rather than assumed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TRACES = os.path.join(HERE, "evidence", "traces")


SECRET = re.compile(r"token|secret|password|passwd|credential|api[_-]?key|auth", re.I)
REDACT = "<withheld>"
ARG_MAX = 2000


def _clip(v):
    s = v if isinstance(v, str) else json.dumps(v)
    return s if len(s) <= ARG_MAX else s[:ARG_MAX] + "...<%d more>" % (len(s) - ARG_MAX)


def summarise(obj, full):
    """What a frame was, without its payload unless asked."""
    out = {}
    if "method" in obj:
        out["method"] = obj["method"]
        params = obj.get("params") or {}
        if obj["method"] == "tools/call":
            out["name"] = params.get("name")
            args = params.get("arguments") or {}
            # Values, not sizes. The argument is the measurement: whether a row
            # count came from the engine or from the model counting rows is the
            # difference between SELECT COUNT(*) and SELECT *, and a length tells
            # those apart not at all. Paper 3's last finding was exactly this --
            # an exact number, cited, and wrong, because of the predicate sent.
            # Only credential-shaped keys are withheld; a query the model wrote
            # is not a secret.
            out["args"] = {k: (REDACT if SECRET.search(k) else _clip(v))
                           for k, v in args.items()}
    if "id" in obj:
        out["id"] = obj["id"]
    if "result" in obj:
        r = obj["result"]
        out["bytes"] = len(json.dumps(r))
        out["is_error"] = bool(r.get("isError")) if isinstance(r, dict) else False
        if isinstance(r, dict) and isinstance(r.get("tools"), list):
            out["tools"] = [t.get("name") for t in r["tools"]]
        if full:
            out["result"] = r
    if "error" in obj:
        out["error"] = obj["error"].get("message") if isinstance(obj["error"], dict) else True
    return out


def pump(src, dst, direction, log, started, full, lock):
    """Relay one direction verbatim, copying a summary aside."""
    for raw in iter(src.readline, b""):
        dst.write(raw)
        dst.flush()
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            # Not a JSON frame: servers do write plain text to stdout during
            # start-up. Record that it happened, not the content.
            rec = {"nonjson_bytes": len(line)}
        else:
            rec = summarise(obj, full)
        rec["t"] = round(time.time() - started, 3)
        rec["dir"] = direction
        with lock:
            log.write(json.dumps(rec) + "\n")
            log.flush()
    try:
        dst.close()
    except Exception:                                    # noqa: BLE001
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default=os.getenv("MCP_TRACE_LABEL"),
                    help="trace filename stem; defaults to $MCP_TRACE_LABEL, which the runner sets per question")
    ap.add_argument("--full", action="store_true",
                    help="keep argument and result bodies; never used for published runs")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
    if not cmd:
        ap.error("no server command given; use: mcp_trace.py --label X -- <server> [args]")
    if not a.label:
        ap.error("no --label and no $MCP_TRACE_LABEL; an untagged trace cannot be attributed to a cell")

    os.makedirs(TRACES, exist_ok=True)
    path = os.path.join(TRACES, a.label + ".jsonl")
    started = time.time()
    lock = threading.Lock()

    with open(path, "a") as log:
        log.write(json.dumps({"t": 0.0, "dir": "runner", "spawn": cmd,
                              "full": bool(a.full)}) + "\n")
        log.flush()
        child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=None)
        up = threading.Thread(target=pump, args=(sys.stdin.buffer, child.stdin,
                                                 "host->server", log, started, a.full, lock))
        down = threading.Thread(target=pump, args=(child.stdout, sys.stdout.buffer,
                                                   "server->host", log, started, a.full, lock))
        up.daemon = down.daemon = True
        up.start(); down.start()
        code = child.wait()
        down.join(timeout=5)
        with lock:
            log.write(json.dumps({"t": round(time.time() - started, 3), "dir": "runner",
                                  "exit": code}) + "\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
