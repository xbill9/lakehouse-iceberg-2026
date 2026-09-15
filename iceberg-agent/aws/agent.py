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
        # Nova runs with the decoding Amazon documents for Nova tool use: greedy,
        # temperature 0 and topK 1, topK going through additionalModelRequestFields.
        # https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html
        # MEASURED on the scan question: default decoding ended the loop before its
        # filter call in 2 of 10 runs; greedy, 0 of 10. Every other model keeps its
        # provider's defaults. ICEBERG_TEMPERATURE / ICEBERG_TOP_K override, for
        # diagnostics only.
        # ICEBERG_DECODING=provider sends no decoding fields at all, so Bedrock's own
        # defaults apply -- the only honest "default" to compare greedy against.
        greedy = "nova" in model and os.getenv("ICEBERG_DECODING") != "provider"
        extra = {}
        temperature = os.getenv("ICEBERG_TEMPERATURE", "0" if greedy else None)
        top_k = os.getenv("ICEBERG_TOP_K", "1" if greedy else None)
        if temperature is not None:
            extra["temperature"] = float(temperature)
        if top_k is not None:
            extra["additional_request_fields"] = {"inferenceConfig": {"topK": int(top_k)}}
        brain = BedrockModel(model_id=model, **extra)
    return Agent(
        model=brain,                                 # a model object
        system_prompt=common.INSTRUCTION,            # `system_prompt`
        tools=[tool(fn) for fn in iceberg_tool.TOOLS],  # explicitly decorated
    )
