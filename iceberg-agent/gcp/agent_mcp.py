# -*- coding: utf-8 -*-
"""GCP leg, tools over MCP: an ADK agent calling the Iceberg MCP server.

The same agent as `agent.py`, with the four Iceberg tools moved out of the
process and behind stdio JSON-RPC.

**A third shape for the same thing.** The Strands leg asks a client for a list
of tools and passes the list. The Agent Framework leg passes one object that IS
the server. ADK passes a *toolset*: `MCPToolset` goes into the same `tools=`
list that took plain callables in `agent.py`, and ADK expands it internally when
it builds the declarations it sends the model.

That makes ADK the only one of the three where the MCP swap does not change the
shape of `build()`. It still returns an agent, not a context manager, because
the toolset's lifecycle is owned by ADK's runner rather than by the caller.
Three frameworks, one protocol, three different answers to "what is an MCP
server to an agent" -- and only one of them leaves the surrounding code alone.

The instruction stays `common.INSTRUCTION`, as on every leg.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "iceberg-conformance"))

import common

CLOUD = "gcp"
DEFAULT_MODEL = "gemini-2.5-flash"

SERVER = os.path.join(os.path.dirname(ROOT), "iceberg-mcp-hosts", "servers",
                      "iceberg_mcp.py")
CATALOGS = os.path.join(os.path.dirname(ROOT), "iceberg-conformance", "catalogs.yaml")


def server_env(catalog):
    """What the server process needs. The agent holds no catalog config."""
    env = dict(os.environ)
    env["ICEBERG_CATALOG"] = catalog
    env.setdefault("ICEBERG_CATALOGS_FILE", CATALOGS)
    return env


def toolset(catalog):
    """The MCP server as an ADK toolset.

    StdioConnectionParams wraps the same StdioServerParameters the raw SDK uses,
    and carries the timeout ADK applies to the session. The default is short
    enough to matter for a server that builds a catalog client on first call, so
    it is set here rather than left implicit.
    """
    from google.adk.tools.mcp_tool.mcp_toolset import (
        MCPToolset, StdioConnectionParams, StdioServerParameters)
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable, args=[SERVER], env=server_env(catalog)),
            timeout=float(os.getenv("ICEBERG_MCP_TIMEOUT", "60")),
        ),
    )


def build():
    """The native brain: ADK on Gemini, tools reached over MCP.

    Same signature as `agent.py`'s build(), which is the finding: on this
    framework the transport swap is confined to what goes in `tools=`.
    """
    from google.adk.agents import LlmAgent
    from google.adk.models.registry import LLMRegistry

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    catalog = os.getenv("ICEBERG_CATALOG") or common.resolve_catalog(CLOUD)
    return LlmAgent(
        model=LLMRegistry.new_llm(model),
        name=common.AGENT_NAME,
        description=common.DESCRIPTION,
        instruction=common.INSTRUCTION,
        tools=[toolset(catalog)],        # a toolset, where agent.py had callables
    )
