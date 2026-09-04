# -*- coding: utf-8 -*-
"""GCP leg: a Google ADK agent on Gemini, reading Iceberg through BigLake.

ADK takes plain callables as tools. The three Iceberg tools are async functions
with typed signatures and Args/Returns docstrings, which is what ADK reads to
build the declaration it sends the model -- so they are passed exactly as they
are, with no wrapper.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import iceberg_tool

CLOUD = "gcp"
DEFAULT_MODEL = "gemini-2.5-flash"


def build():
    """The native brain: ADK on Gemini, with the shared Iceberg tools."""
    from google.adk.agents import LlmAgent

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    os.environ.setdefault("ICEBERG_CATALOG", common.resolve_catalog(CLOUD))
    return LlmAgent(
        model=model,                        # a model id string
        name=common.AGENT_NAME,
        description=common.DESCRIPTION,
        instruction=common.INSTRUCTION,     # `instruction`
        tools=list(iceberg_tool.TOOLS),     # plain callables
    )
