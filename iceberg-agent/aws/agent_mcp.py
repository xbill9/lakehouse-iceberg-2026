# -*- coding: utf-8 -*-
"""AWS leg, tools over MCP: a Strands agent calling the Iceberg MCP server.

The same agent as `agent.py`, with one thing changed. There, the four Iceberg
tools are Python callables imported into the process and decorated. Here they
are a separate process, reached over stdio JSON-RPC, and the agent learns what
they are by asking.

That is the claim MCP makes -- the tools are behind a wire protocol, so they are
not a property of the framework -- and this leg is where it gets tested rather
than repeated.

**What the swap costs, visible in the shape of this file.** In `agent.py`,
`build()` returns an Agent and the tools are valid for as long as the process
lives. An MCP client holds a subprocess and a session, and the tools are only
valid while it is open, so `build()` cannot return an Agent on its own: the
caller has to hold something. This module returns a context manager instead.
Nothing about the Iceberg tools required that; the transport did.
"""
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
# `common` re-exports the instruction from `iceberg_tool`, which imports the
# conformance harness's auth module. Worth noticing rather than papering over:
# with the tools behind MCP this process should need no Iceberg dependency at
# all -- the server is what talks to the catalog -- and it needs one only
# because the shared instruction lives in the same module as the tools.
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "iceberg-conformance"))

import common

CLOUD = "aws"
DEFAULT_MODEL = "us.amazon.nova-micro-v1:0"

#: The server under test. One process, four tools, no framework import in it.
SERVER = os.path.join(os.path.dirname(ROOT), "iceberg-mcp-hosts", "servers",
                      "iceberg_mcp.py")
CATALOGS = os.path.join(os.path.dirname(ROOT), "iceberg-conformance", "catalogs.yaml")


def server_env(catalog):
    """What the server process needs, and nothing else.

    The catalog is passed to the SERVER, not held by the agent. That is the
    division of labour MCP asks for: the agent knows the question, the server
    knows the data. It is also why the same server answers for Polaris, BigLake
    or Glue without the agent changing at all.
    """
    env = dict(os.environ)
    env["ICEBERG_CATALOG"] = catalog
    env.setdefault("ICEBERG_CATALOGS_FILE", CATALOGS)
    return env


def brain(model):
    """Identical to agent.py's model selection -- deliberately not refactored.

    Holding the model construction the same is what makes a difference between
    this leg and `agent.py` a difference of tool transport. Nova keeps the
    greedy decoding Amazon documents for tool use.
    """
    from strands.models import BedrockModel
    if model.startswith("gemini"):
        from strands.models.gemini import GeminiModel
        return GeminiModel(model_id=model)
    extra = {}
    if "nova" in model and os.getenv("ICEBERG_DECODING") != "provider":
        extra["temperature"] = float(os.getenv("ICEBERG_TEMPERATURE", "0"))
        extra["additional_request_fields"] = {
            "inferenceConfig": {"topK": int(os.getenv("ICEBERG_TOP_K", "1"))}}
    return BedrockModel(model_id=model, **extra)


@contextlib.contextmanager
def build():
    """Yield a Strands agent whose tools come from the MCP server.

    Yields (agent, tool_names) so a caller can record what the server actually
    offered. The tool list is read from the server rather than declared here --
    if the two disagree, that is a finding about the server, and it cannot be
    one if the agent was told the answer in advance.
    """
    from mcp import StdioServerParameters, stdio_client
    from strands import Agent
    from strands.tools.mcp import MCPClient

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    catalog = os.getenv("ICEBERG_CATALOG") or common.resolve_catalog(CLOUD)

    client = MCPClient(lambda: stdio_client(StdioServerParameters(
        command=sys.executable, args=[SERVER], env=server_env(catalog))))

    with client:
        tools = client.list_tools_sync()
        names = sorted(getattr(t, "tool_name", None) or str(t) for t in tools)
        yield Agent(model=brain(model),
                    system_prompt=common.INSTRUCTION,
                    tools=tools), names
