# -*- coding: utf-8 -*-
"""Azure leg, tools over MCP: Agent Framework calling the Iceberg MCP server.

The same agent as `agent.py`, with the four Iceberg tools moved out of the
process and behind stdio JSON-RPC.

**Where this differs from the Strands leg, and it is not cosmetic.** Strands
hands you a client, you ask it for a list of tools, and you pass that list to
the Agent -- the same shape as passing callables, with a discovery step in
front. Agent Framework does not give you a list at all: `MCPStdioTool` IS the
tool, one object standing for the whole server, and the Agent is given that.

So the two frameworks disagree about what an MCP server is to an agent. One
treats it as a source of tools, the other as a tool. The agent code cannot be
shared across them even though the server, the protocol and the tools are
identical -- which is the same shape of result paper 3 found one layer down,
where the tools ported and the code around them did not.

The instruction stays `common.INSTRUCTION`, as on every other leg. The server
also sends its own instructions in the initialize result, and ignoring them
keeps the only variable the transport.
"""
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "iceberg-conformance"))

import common

CLOUD = "azure"
DEFAULT_MODEL = "gpt-5-mini"

SERVER = os.path.join(os.path.dirname(ROOT), "iceberg-mcp-hosts", "servers",
                      "iceberg_mcp.py")
CATALOGS = os.path.join(os.path.dirname(ROOT), "iceberg-conformance", "catalogs.yaml")


def server_env(catalog):
    """What the server process needs. The agent holds no catalog config."""
    env = dict(os.environ)
    env["ICEBERG_CATALOG"] = catalog
    env.setdefault("ICEBERG_CATALOGS_FILE", CATALOGS)
    return env


@contextlib.asynccontextmanager
async def build():
    """Yield an Agent Framework agent whose tools come from the MCP server.

    Async, where the Strands leg is sync. Agent Framework is async throughout
    and its MCP tool connects on entry, so the lifecycle the transport imposes
    lands in this leg as an async context manager and in the AWS leg as an
    ordinary one. Two frameworks, one protocol, two shapes of `build`.

    Yields (agent, tool_names) so a caller can record what the server offered.
    """
    from agent_framework import Agent, MCPStdioTool
    from agent_framework.foundry import FoundryChatClient
    from azure.identity import DefaultAzureCredential

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    catalog = os.getenv("ICEBERG_CATALOG") or common.resolve_catalog(CLOUD)

    server = MCPStdioTool(
        name="iceberg",
        command=sys.executable,
        args=[SERVER],
        env=server_env(catalog),
    )
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model,
        credential=DefaultAzureCredential(),
    )
    async with server:
        names = sorted(f.name for f in (server.functions or []))
        yield Agent(
            client=client,
            name=common.AGENT_NAME,
            description=common.DESCRIPTION,
            instructions=common.INSTRUCTION,
            tools=[server],                 # the SERVER is the tool, not its tools
            default_options={"store": False},
        ), names
