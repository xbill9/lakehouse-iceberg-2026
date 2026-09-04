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
import importlib.util
import os
import sys
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cloud", choices=sorted(RUNNERS))
    ap.add_argument("question")
    ap.add_argument("--catalog", help="override the catalog this leg reads")
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

    answer = asyncio.run(RUNNERS[args.cloud](agent, args.question))

    print("\n" + common.header(args.cloud, model, catalog, iceberg_tool.catalog_count()))
    print(answer)
    print("\ncatalog calls: %d of %d" % (iceberg_tool.catalog_count(),
                                         iceberg_tool.CATALOG_BUDGET))


if __name__ == "__main__":
    main()
