#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask one question of each cloud's agent, with the tools reached over MCP.

    python3 run_mcp.py --cloud aws --question "How many rows are in probe_ns.probe_table?"
    python3 run_mcp.py --all --catalog apache-polaris

The counterpart of `run_once.py`, which drives the same three agents with the
tools imported into the process. Same instruction, same tools, same catalog --
the transport is the variable.

**Why this file exists at all, rather than a flag on run_once.** The three legs
do not present the same way once the tools are behind a protocol:

    aws    build() is a sync context manager   yields (agent, tool_names)
    azure  build() is an async context manager yields (agent, tool_names)
    gcp    build() returns an agent            the runner owns the session

That is not three styles of writing the same thing. It is what each framework
decided an MCP server is: a source of tools you list, a single tool object, or a
toolset the framework expands. `run_once.py` needed one shape of `build` for all
three legs; this needs three, and the `open_leg` function below is the whole
cost of that, written out rather than summarised.
"""
import argparse
import asyncio
import contextlib
import importlib.util
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "iceberg-conformance"))

THINKING = re.compile(r"<thinking>.*?</thinking>\s*", re.S)


def require_sdk():
    """Refuse to run on an MCP SDK none of the frameworks accept.

    All three pin mcp<2. Installed 2.x, ADK fails on a removed module and Agent
    Framework on a renamed field, and both failures arrive as an exception the
    runner catches -- which a caller that scores stdout reads as a wrong answer
    rather than as a leg that never started. The version is checked here so the
    run stops with the reason instead.
    """
    import importlib.metadata as md
    version = md.version("mcp")
    if int(version.split(".")[0]) >= 2:
        raise SystemExit(
            "mcp %s is installed and google-adk, agent-framework-core and\n"
            "strands-agents all require mcp<2. Install one they accept:\n"
            "  python3 -m pip install 'mcp>=1.24,<2'" % version)
    return version


def load(cloud):
    path = os.path.join(HERE, cloud, "agent_mcp.py")
    spec = importlib.util.spec_from_file_location(cloud + "_agent_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.asynccontextmanager
async def open_leg(cloud, module):
    """Normalise the three shapes to one, so the comparison can be run.

    Every line here is a difference the MCP swap introduced. `agent.py` needed
    none of it -- `build()` returned an agent on all three clouds.
    """
    if cloud == "aws":                       # sync context manager
        with module.build() as (agent, names):
            yield agent, names
    elif cloud == "azure":                   # async context manager
        async with module.build() as (agent, names):
            yield agent, names
    else:                                    # gcp: plain build, runner owns it
        agent = module.build()
        names = sorted(t.name for t in await agent.tools[0].get_tools())
        yield agent, names


async def ask_aws(agent, question):
    before = len(agent.messages)
    result = agent(question)
    calls = [b["toolUse"]["name"] for m in agent.messages[before:]
             for b in (m.get("content") or [])
             if isinstance(b, dict) and "toolUse" in b]
    return THINKING.sub("", str(result)).strip(), calls


async def ask_azure(agent, question):
    reply = await agent.run(question)
    calls = []
    for message in getattr(reply, "messages", []) or []:
        for content in getattr(message, "contents", []) or []:
            name = getattr(content, "name", None)
            if name and type(content).__name__.startswith("FunctionCall"):
                calls.append(name)
    return THINKING.sub("", str(reply)).strip(), calls


async def ask_gcp(agent, question):
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    runner = InMemoryRunner(agent=agent, app_name="iceberg-agent")
    session = await runner.session_service.create_session(
        app_name="iceberg-agent", user_id="probe")
    calls, out = [], []
    async for event in runner.run_async(
            user_id="probe", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=question)])):
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "function_call", None):
                calls.append(part.function_call.name)
            if getattr(part, "text", None):
                out.append(part.text)
    return THINKING.sub("", "".join(out)).strip(), calls


ASK = {"aws": ask_aws, "azure": ask_azure, "gcp": ask_gcp}
DEFAULT_QUESTION = ("How many rows are in probe_ns.probe_table? "
                    "Use your tools and cite the snapshot id.")


async def one(cloud, question):
    module = load(cloud)
    started = time.time()
    async with open_leg(cloud, module) as (agent, names):
        answer, calls = await ASK[cloud](agent, question)
    return {"cloud": cloud, "tools_offered": names, "tool_calls": calls,
            "elapsed_s": round(time.time() - started, 1), "answer": answer}


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cloud", choices=sorted(ASK))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--catalog", help="overrides each leg's own cloud catalog")
    a = ap.parse_args()
    if a.catalog:
        os.environ["ICEBERG_CATALOG"] = a.catalog
    require_sdk()
    clouds = sorted(ASK) if a.all else [a.cloud or "aws"]

    for cloud in clouds:
        try:
            row = await one(cloud, a.question)
        except Exception as exc:                      # noqa: BLE001
            print("%-6s FAILED  %s: %s" % (cloud, type(exc).__name__, str(exc)[:140]))
            continue
        print("%-6s %5.1fs  tools=%d  calls=%s"
              % (row["cloud"], row["elapsed_s"], len(row["tools_offered"]),
                 ",".join(c.replace("iceberg_", "") for c in row["tool_calls"]) or "none"))
        # In full. A caller that scores this output -- compare_transport.py does
        # -- scores what is printed, and truncating here put the citation and the
        # tail of the column list past the cut. Gemini writes long answers and
        # Nova Micro short ones, so a 200-character limit read as ADK losing its
        # citation over MCP while Strands kept it. That was the printer.
        print(row["answer"])


if __name__ == "__main__":
    asyncio.run(main())
