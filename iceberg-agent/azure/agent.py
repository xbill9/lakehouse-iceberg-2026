# -*- coding: utf-8 -*-
"""Azure leg: a Microsoft Agent Framework agent on Foundry, reading OneLake.

Agent Framework takes a chat client object and calls the system prompt
`instructions`. OneLake's Iceberg endpoint is read-only, which costs this leg
nothing: every tool here reads.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import iceberg_tool

CLOUD = "azure"
DEFAULT_MODEL = "gpt-5-mini"


def build():
    """The native brain: Agent Framework on Foundry, with the shared tools."""
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.identity import DefaultAzureCredential

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    os.environ.setdefault("ICEBERG_CATALOG", common.resolve_catalog(CLOUD))
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model,
        credential=DefaultAzureCredential(),
    )
    return Agent(
        client=client,                       # `client`, not chat_client
        name=common.AGENT_NAME,
        description=common.DESCRIPTION,
        instructions=common.INSTRUCTION,     # `instructions`, not instruction
        tools=list(iceberg_tool.TOOLS),
        default_options={"store": False},
    )
