# -*- coding: utf-8 -*-
"""The MCP servers under test, as launch specs.

Surfaces are recorded in ../evidence/server-surfaces.txt, quoted from each
project's own documentation. `answers_rows` is set from that reading, not from
a run: it is what the tool list says the server can do, and the point of the
experiment is whether the host's behaviour matches it.
"""
import os

POLARIS_URI = os.getenv("IRC_POLARIS_URI", "http://localhost:8181/api/catalog")

SERVERS = {
    # Community, Rust. Four tools, none of which return rows.
    "morristai": {
        "key": "morristai",
        "answers_rows": False,
        "spec": {
            "command": "iceberg-mcp",
            "args": [],
            "env": {"CATALOG_KIND": "rest", "REST_URI": POLARIS_URI,
                    "LOG_LEVEL": "info"},
        },
    },
    # Community, Python. SELECT and INSERT through PyIceberg.
    "ahodroj": {
        "key": "ahodroj",
        "answers_rows": True,
        "spec": {
            "command": "uvx",
            "args": ["mcp-iceberg-service"],
            "env": {"ICEBERG_CATALOG_URI": POLARIS_URI},
        },
    },
    # Google, first-party, remote. execute_sql over BigLake/Iceberg.
    "bigquery": {
        "key": "bigquery",
        "answers_rows": True,
        "spec": {"type": "http", "url": "https://bigquery.googleapis.com/mcp"},
    },
    # Google, first-party, remote. Compute control plane, not a query surface --
    # included precisely because a data question should fail on it.
    "managed-spark": {
        "key": "managed-spark",
        "answers_rows": False,
        "spec": {"type": "http",
                 "url": "https://dataproc-us-central1.googleapis.com/mcp"},
    },
}
