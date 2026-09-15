# -*- coding: utf-8 -*-
"""AWS leg: a Strands agent on Bedrock, reading Iceberg through Glue.

Strands wants tools decorated rather than passed bare, and takes a model
*object* rather than an id string. Those two differences are the whole delta
from the ADK leg -- the tools and the instruction are the same objects.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import iceberg_tool

CLOUD = "aws"
DEFAULT_MODEL = "us.amazon.nova-micro-v1:0"


def build():
    """The native brain: Strands on Bedrock, with the shared Iceberg tools."""
    from strands import Agent, tool
    from strands.models import BedrockModel

    model = common.resolve_model(CLOUD, DEFAULT_MODEL)
    os.environ.setdefault("ICEBERG_CATALOG", common.resolve_catalog(CLOUD))
    if model.startswith("gemini"):
        # The Axis C crossover: this same Strands agent on Gemini, so framework
        # and model can be separated. genai.Client() picks Vertex AI from
        # GOOGLE_GENAI_USE_VERTEXAI exactly as ADK's does -- same model, same
        # endpoint, different framework.
        from strands.models.gemini import GeminiModel
        brain = GeminiModel(model_id=model)
    else:
        brain = BedrockModel(model_id=model)
    return Agent(
        model=brain,                                 # a model object
        system_prompt=common.INSTRUCTION,            # `system_prompt`
        tools=[tool(fn) for fn in iceberg_tool.TOOLS],  # explicitly decorated
    )
