#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Iceberg MCP server this paper measures hosts through.

    ICEBERG_CATALOG=apache-polaris python3 servers/iceberg_mcp.py

**Why our own rather than the community ones.** Paper 4 began by comparing four
third-party servers, and that design measured the wrong thing twice over. Axis A
varied the tool surface, but the surfaces differ because four projects made four
independent decisions about scope -- one exposes SQL, one exposes four metadata
calls, one is a compute control plane. A difference between them is a difference
between maintainers, and it does not generalise to anything. Then the instrument
broke: `ahodroj` cannot start at all (its package is on no registry, and from git
it dies against the current MCP SDK), so a leg of the matrix would have scored a
server that never ran as a server that answered nothing.

So the server becomes the constant and the host becomes the variable. These are
paper 3's four tools, unchanged, imported rather than reimplemented -- the same
callables that produced that matrix, carrying three versions of instruction
learned from measured failures. Holding them fixed is what lets a difference
between `claude`, `codex` and `agy` be attributed to the host.

**What axis A becomes.** Not an accident of packaging, but one deliberate
variable: whether the arithmetic is done by the engine or by the model.
`ICEBERG_SCAN_FILTER=1` gives the scan tool a `where` and returns an exact
COUNT, MIN and MAX over every matching row; `ICEBERG_SCAN_FILTER=0` returns rows
only and leaves the counting to whatever is driving. Paper 3 measured that
difference across three agent frameworks on models it chose. Paper 4 measures it
across three CLI hosts on the models those hosts pick for themselves, which is
the case a reader actually meets.

**Why no MCP SDK.** The protocol needed here is four methods of newline-delimited
JSON-RPC, and `ahodroj` is the argument against taking a dependency for it: its
pyproject asks for `mcp>=1.0.0`, uv resolves 2.x, and the API it registers
against is gone. Speaking the wire directly cannot rot that way, and it keeps the
server byte-transparent to `mcp_trace.py`, which relays the same framing.

Reads only. Nothing here creates, commits or drops anything.
"""
import asyncio
import inspect
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# iceberg_tool lives with paper 3's agent and authenticates through the
# conformance harness's probe.auth, so both are on the path. Importing the tool
# rather than copying it is the whole point: a copy would drift, and then the
# two papers would not be measuring the same instrument.
sys.path.insert(0, os.path.join(ROOT, "iceberg-agent"))
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))

import iceberg_tool  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "iceberg"
SERVER_VERSION = "1.0.0"

#: Tools to withhold, comma-separated, so a variant can remove a capability
#: rather than merely discourage it. `ICEBERG_SCAN_FILTER=0` alone was not
#: enough: it reverts the scan tool to returning rows only, but leaves
#: iceberg_count_rows offered, so every host answered "how many rows" with the
#: engine's exact count in BOTH variants and the arithmetic axis measured
#: nothing. MEASURED 2026-09-16 over 72 runs -- Q4 used iceberg_count_rows in
#: 6 of 6 runs on each variant, and the two tool lists were identical.
WITHHELD = tuple(t.strip() for t in os.getenv("ICEBERG_WITHHOLD", "").split(",")
                 if t.strip())


def _instructions(names):
    """Paper 3's instruction, told the truth about which tools are present.

    It names its four tools and says "To answer how many rows a table has, use
    iceberg_count_rows". Withholding that tool while keeping the sentence would
    point the model at something it cannot see -- a second variable, and a
    needlessly unfair one. So the roster and that one sentence are conditioned on
    what is actually offered, and nothing else in the text changes.

    The replacements are asserted rather than attempted. A silent no-op here
    would leave the rows variant instructed to call a tool it does not have,
    which reads as the model failing rather than as the text being stale.
    """
    text = iceberg_tool.INSTRUCTION
    if not WITHHELD:
        return text

    roster_was = ("four tools that read Apache Iceberg tables through a REST "
                  "catalog: iceberg_list_tables, iceberg_describe_table, "
                  "iceberg_count_rows and iceberg_scan_table.")
    count_was = ("To answer how many rows a table has, use iceberg_count_rows. ")
    words = {1: "one tool", 2: "two tools", 3: "three tools", 4: "four tools"}
    roster_now = ("%s that read Apache Iceberg tables through a REST catalog: %s."
                  % (words[len(names)], ", ".join(names[:-1]) + " and " + names[-1]
                     if len(names) > 1 else names[0]))

    for old, new in ((roster_was, roster_now),
                     (count_was, "" if "iceberg_count_rows" in WITHHELD else count_was)):
        if old and old not in text:
            raise SystemExit(
                "iceberg_mcp: INSTRUCTION no longer contains the text this "
                "server rewrites for a withheld tool, so the rows variant would "
                "be instructed to call a tool it does not have.\n  missing: %r"
                % old[:70])
        text = text.replace(old, new)
    return text

_ARG_LINE = re.compile(r"^\s{4,}(\w+):\s*(.+)$")


def _doc_parts(fn):
    """Split a Google-style docstring into prose and per-argument descriptions.

    The Args text is not decoration: it carries measured guidance -- that a scan
    returns a sample and must not be counted, that `where` takes a row filter and
    not an ORDER BY. Dropping it on the way into the schema would quietly hand
    the model a weaker tool than paper 3 handed its agents.
    """
    doc = inspect.getdoc(fn) or ""
    prose, args, section = [], {}, None
    pending = None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped in ("Args:", "Returns:", "Raises:"):
            section = stripped[:-1].lower()
            continue
        if section == "args":
            match = _ARG_LINE.match(line)
            if match:
                pending = match.group(1)
                args[pending] = match.group(2).strip()
            elif stripped and pending:
                # A wrapped continuation line belongs to the argument above it.
                args[pending] += " " + stripped
            continue
        if section == "returns":
            # Kept in the prose: the model needs to know a result ends with an
            # exact COUNT before it decides to count rows itself.
            if stripped:
                prose.append(stripped)
            continue
        prose.append(line)
    return "\n".join(prose).strip(), args


_JSON_TYPE = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema(fn, arg_docs):
    props, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        kind = _JSON_TYPE.get(param.annotation, "string")
        entry = {"type": kind}
        if name in arg_docs:
            entry["description"] = arg_docs[name]
        props[name] = entry
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            entry["default"] = param.default
    return {"type": "object", "properties": props, "required": required}


def _tools():
    out = []
    for fn in iceberg_tool.TOOLS:
        if fn.__name__ in WITHHELD:
            continue
        prose, arg_docs = _doc_parts(fn)
        out.append({"name": fn.__name__, "description": prose,
                    "inputSchema": _schema(fn, arg_docs), "_fn": fn})
    if not out:
        raise SystemExit("iceberg_mcp: ICEBERG_WITHHOLD removed every tool")
    return out


TOOLS = _tools()
BY_NAME = {t["name"]: t for t in TOOLS}
INSTRUCTIONS = _instructions([t["name"] for t in TOOLS])


def _declared():
    """What tools/list returns -- the public shape, with the callable removed.

    Paper 4's first finding against a third-party server was a declared-vs-served
    mismatch: the tool list named `namespaces`, the server answered only
    `get_namespaces`. Building the list from the same objects that dispatch makes
    that particular lie impossible to tell here, which is the point of saying so.
    """
    return [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]


def _coerce(tool, arguments):
    """Bring arguments to the types the schema declares, and say nothing about it.

    MEASURED 2026-09-16, first traced run: `claude` sent `"limit": "5"` -- a
    string, against a schema declaring integer. Python accepted it, so the tool
    behaved correctly and nothing surfaced. That is the problem: a host that
    honours the declared type and one that does not would produce identical
    results here, and the difference would show up later as an unexplained error
    on some other tool. Coercing centrally keeps the instrument identical for
    every host; the raw argument is still in the trace, which is where a claim
    about host behaviour has to come from anyway.
    """
    props = tool["inputSchema"]["properties"]
    out = {}
    for key, value in (arguments or {}).items():
        want = props.get(key, {}).get("type")
        try:
            if want == "integer" and not isinstance(value, bool):
                value = int(value)
            elif want == "number" and not isinstance(value, bool):
                value = float(value)
            elif want == "string" and value is not None:
                value = str(value)
        except (TypeError, ValueError):
            pass          # leave it; the tool's own failure text is clearer
        out[key] = value
    return out


def _call(name, arguments):
    tool = BY_NAME.get(name)
    if tool is None:
        return {"content": [{"type": "text",
                             "text": "No such tool: %s. Available: %s"
                                     % (name, ", ".join(sorted(BY_NAME)))}],
                "isError": True}
    try:
        result = tool["_fn"](**_coerce(tool, arguments))
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return {"content": [{"type": "text", "text": str(result)}], "isError": False}
    except TypeError as exc:
        # A bad argument set is the model's mistake to see and correct, not a
        # crash: the tools already return their own failures as text.
        return {"content": [{"type": "text", "text": "Bad arguments: %s" % exc}],
                "isError": True}
    except Exception as exc:  # noqa: BLE001 - a dead server scores as a silent wrong answer
        return {"content": [{"type": "text",
                             "text": "%s failed: %s: %s"
                                     % (name, type(exc).__name__, exc)}],
                "isError": True}


def handle(message):
    """Return a response object, or None for a notification."""
    method = message.get("method")
    mid = message.get("id")

    if method == "initialize":
        return {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                               "instructionVersion": iceberg_tool.INSTRUCTION_VERSION,
                               "scanFilter": os.getenv("ICEBERG_SCAN_FILTER", "1"),
                               "catalog": iceberg_tool.catalog_name()},
                "instructions": INSTRUCTIONS}
    if method == "tools/list":
        return {"tools": _declared()}
    if method == "tools/call":
        params = message.get("params") or {}
        return _call(params.get("name"), params.get("arguments"))
    if method == "ping":
        return {}
    if mid is None:
        return None          # any other notification, including initialized
    raise LookupError(method)


def main():
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        mid = message.get("id")
        try:
            result = handle(message)
        except LookupError as exc:
            reply = {"jsonrpc": "2.0", "id": mid,
                     "error": {"code": -32601, "message": "Method not found: %s" % exc}}
        else:
            if mid is None:
                continue     # notification: nothing is sent back
            reply = {"jsonrpc": "2.0", "id": mid, "result": result}
        out.write(json.dumps(reply) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
