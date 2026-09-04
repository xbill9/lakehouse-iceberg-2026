# -*- coding: utf-8 -*-
"""Everything the three cloud legs share, so that only the framework varies.

The rule this directory is built on is the one the research-agent mesh already
proved: **share everything that is not the variable under test.** Three agents
that differ in framework, model, serving stack, instruction, tool and budget
cannot attribute any result to any of them.

Here the variable under test is the agent framework and its host. Shared,
exactly one implementation each:

  - the three Iceberg tools, in ``iceberg_tool``
  - the instruction, versioned
  - the catalog-call budget
  - the answer format

Different, on purpose:

  - the agent framework      ADK / Strands / Agent Framework
  - the model                whatever each cloud runs
  - the catalog it reads     BigLake / Glue / OneLake
  - the serving stack        each vendor's own

The catalog is in the *different* column deliberately. Pointing all three at
one catalog would test three frameworks against one server; pointing each at
its own cloud's catalog tests the thing the conformance work says is the only
interoperable surface -- and it is the arrangement a real deployment would have.
"""
import os

from iceberg_tool import INSTRUCTION, INSTRUCTION_VERSION, TOOLS  # noqa: F401

AGENT_NAME = "iceberg_analyst"
DESCRIPTION = (
    "An agent that answers questions about Apache Iceberg tables by reading "
    "them through a REST catalog, and cites the table version it read"
)

#: Which catalog each leg reads, unless overridden. These are names in
#: ``iceberg-conformance/catalogs.yaml``, so a leg is repointed by editing that
#: file rather than this one.
DEFAULT_CATALOG = {
    "gcp": "google-lakehouse",
    "aws": "aws-glue",
    "azure": "microsoft-onelake",
}

#: Every leg falls back to the local control catalog when its cloud is not
#: configured. A leg that cannot reach its catalog should fail loudly in its own
#: logs, not answer from a different cloud's data by accident -- so this is only
#: consulted when ICEBERG_CATALOG is unset and the cloud has no default.
FALLBACK_CATALOG = "apache-polaris"


def resolve_catalog(cloud: str) -> str:
    """The catalog name this leg reads."""
    return os.getenv("ICEBERG_CATALOG") or DEFAULT_CATALOG.get(cloud, FALLBACK_CATALOG)


def resolve_model(cloud: str, default: str) -> str:
    """The model this leg runs, overridable per cloud.

    Carried in the answer header so a result can be attributed to a model rather
    than to the framework wrapping it.
    """
    return os.getenv("ICEBERG_MODEL_" + cloud.upper()) or os.getenv("ICEBERG_MODEL") or default


def header(cloud: str, model: str, catalog: str, calls: int) -> str:
    """One stamped line at the top of every answer.

    The research mesh learned to carry the instruction version and the tool
    count into the answer itself: without them, a draft that looks wrong cannot
    be told from a draft produced by an older instruction, and an agent that
    silently never called its tool looks identical to one that did.
    """
    return (
        "<!-- cloud=%s model=%s catalog=%s instruction=v%d catalog_calls=%d -->"
        % (cloud, model, catalog, INSTRUCTION_VERSION, calls)
    )
