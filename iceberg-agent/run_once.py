#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask one cloud's agent one question, and print what it answered.

Deliberately not a benchmark. This is the single-leg harness that proves a leg
works end to end -- the agent reached its catalog, called the tools, and cited a
table version -- before any of it is worth running three times and scoring.

    python3 run_once.py gcp "How many rows are in the probe table?"

Each leg reads its own cloud's catalog, so the answer is grounded in whatever
that cloud actually serves. `--catalog` overrides for testing a leg against the
local control.
"""
import argparse
import asyncio
import contextlib
import io
import importlib.util
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load(cloud: str):
    spec = importlib.util.spec_from_file_location(
        cloud + "_agent", os.path.join(HERE, cloud, "agent.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_gcp(agent, question: str) -> str:
    """ADK drives its agent through a Runner with a session."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="iceberg-agent")
    session = await runner.session_service.create_session(
        app_name="iceberg-agent", user_id="probe")
    out = []
    async for event in runner.run_async(
        user_id="probe",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    print("   -> tool: %s(%s)" % (
                        part.function_call.name,
                        ", ".join("%s=%r" % kv for kv in
                                  (part.function_call.args or {}).items())), flush=True)
                elif getattr(part, "text", None):
                    out.append(part.text)
    return "\n".join(out).strip()


async def run_aws(agent, question: str) -> str:
    """Strands calls the agent directly."""
    result = agent(question)
    return str(result)


async def run_azure(agent, question: str) -> str:
    """Agent Framework awaits the agent."""
    reply = await agent.run(question)
    return str(reply)


RUNNERS = {"gcp": run_gcp, "aws": run_aws, "azure": run_azure}

#: --warm sends this through the agent before the timed question, with its output
#: discarded, and builds the catalog client, so tokens and connections are held
#: before the clock starts. MEASURED 2026-09-15: a cold first token costs 1.25 to
#: 1.53s through DefaultAzureCredential, 0.52 to 0.54s through Vertex ADC and
#: 0.06s through the AWS chain, all of which landed inside answer time.
WARMUP = "This is a connection check. Reply with the single word ready and call no tools."


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cloud", choices=sorted(RUNNERS))
    ap.add_argument("question")
    ap.add_argument("--catalog", help="override the catalog this leg reads")
    ap.add_argument("--warm", action="store_true",
                    help="run an untimed warm-up turn first, so sign-in is not timed")
    args = ap.parse_args()

    import common
    import iceberg_tool

    # Settled before the agent is built, and before any tool call, so the leg
    # cannot end up reading a catalog nobody asked for.
    os.environ["ICEBERG_CATALOG"] = args.catalog or common.resolve_catalog(args.cloud)

    iceberg_tool.reset_budget()
    module = load(args.cloud)
    agent = module.build()
    catalog = os.environ.get("ICEBERG_CATALOG", common.resolve_catalog(args.cloud))
    model = common.resolve_model(args.cloud, module.DEFAULT_MODEL)

    print("cloud=%s model=%s catalog=%s" % (args.cloud, model, catalog))
    print("question: %s\n" % args.question)

    warm_seconds = None
    if args.warm:
        warm_started = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            iceberg_tool.catalog()
            asyncio.run(RUNNERS[args.cloud](agent, WARMUP))
        warm_seconds = time.monotonic() - warm_started
        if isinstance(getattr(agent, "messages", None), list):
            agent.messages.clear()      # Strands keeps the conversation on the agent
        iceberg_tool.reset_budget()

    started = time.monotonic()
    answer = asyncio.run(RUNNERS[args.cloud](agent, args.question))
    agent_seconds = time.monotonic() - started

    print("\n" + common.header(args.cloud, model, catalog, iceberg_tool.catalog_count()))
    print(answer)
    print("\ncatalog calls: %d of %d" % (iceberg_tool.catalog_count(),
                                         iceberg_tool.CATALOG_BUDGET))
    # Agent seconds is the answer alone, after imports and agent construction;
    # tool seconds is the part of it spent inside the tools. The difference is
    # the model and the framework.
    print("agent seconds: %.2f | tool seconds: %.2f"
          % (agent_seconds, iceberg_tool.catalog_seconds()))
    if warm_seconds is not None:
        print("warm-up seconds: %.2f" % warm_seconds)


if __name__ == "__main__":
    main()
