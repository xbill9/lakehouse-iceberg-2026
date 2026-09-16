# -*- coding: utf-8 -*-
"""The MCP servers under test, as launch specs.

`catalog` is which catalog the server actually reads, and it is not cosmetic.
Two of these point at the local Polaris and two at Google, so they are different
physical tables holding the same seeded fixture. Grading every cell against one
catalog's snapshot id and metadata location would score the Google cells 0 on the
citation checks by construction -- a scoring artefact indistinguishable from a
finding about the server.

Surfaces are recorded in ../evidence/server-surfaces.txt, quoted from each
project's own documentation. `answers_rows` is set from that reading, not from
a run: it is what the tool list says the server can do, and the point of the
experiment is whether the host's behaviour matches it.
"""
import os
import shutil
import sys


def _binary(name):
    """Resolve a local server binary to an absolute path, or leave it named.

    `servers.py` launched this by bare name, and when the binary was absent the
    wrapper died instantly and the host reported a closed connection -- which
    reads like a server that answered nothing rather than one that never ran.
    An absolute path fails at launch with the path in the message, and
    `missing_binary` lets the runner refuse the cell instead of scoring it.

    cargo installs to ~/.cargo/bin, which is not always on a non-interactive
    PATH, so that is checked explicitly rather than trusted to the environment.
    """
    found = shutil.which(name)
    if found:
        return found, False
    cargo = os.path.expanduser("~/.cargo/bin/" + name)
    if os.path.exists(cargo):
        return cargo, False
    return name, True

POLARIS_URI = os.getenv("IRC_POLARIS_URI", "http://localhost:8181/api/catalog")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = os.getenv("MCP_TRACE", "1") == "1"


def _traced(spec):
    """Launch a stdio server through mcp_trace.py, so its calls are on record.

    Paper 3's matrix was defensible because every tool call was logged; prose
    alone cannot tell a fetched answer from an invented one. Only stdio servers
    can be wrapped -- an HTTP server is dialled by the host directly, so those
    cells have no trace at all, which is why `traced` is recorded per server
    rather than assumed for the run.

    MCP_TRACE=0 runs without the proxy, for comparing against an untraced run.
    """
    if not TRACE or spec.get("type") == "http":
        return spec
    wrapped = dict(spec)
    wrapped["command"] = sys.executable
    wrapped["args"] = [os.path.join(HERE, "mcp_trace.py"), "--",
                       spec["command"]] + list(spec.get("args") or [])
    return wrapped

SERVERS = {
    # Community, Rust. Four tools, none of which return rows.
    "morristai": {
        "key": "morristai",
        "answers_rows": False,
        "traced": TRACE,
        "catalog": "apache-polaris",
        "cites_version": None,   # UNKNOWN: table_properties may or may not carry it
        "missing_binary": _binary("iceberg-mcp")[1],
        "spec": {
            "command": _binary("iceberg-mcp")[0],
            "args": [],
            "env": {"CATALOG_KIND": "rest", "REST_URI": POLARIS_URI,
                    "LOG_LEVEL": "info"},
        },
    },
    # Community, Python. SELECT and INSERT through PyIceberg.
    "ahodroj": {
        "key": "ahodroj",
        "answers_rows": True,
        "traced": TRACE,
        "catalog": "apache-polaris",
        "cites_version": False,
        "missing_binary": _binary("uvx")[1],
        "spec": {
            "command": _binary("uvx")[0],
            "args": ["mcp-iceberg-service"],
            "env": {"ICEBERG_CATALOG_URI": POLARIS_URI},
        },
    },
    # Google, first-party, remote. execute_sql over BigLake/Iceberg.
    "bigquery": {
        "key": "bigquery",
        "answers_rows": True,
        "traced": False,
        "catalog": "google-lakehouse",
        "cites_version": False,
        "spec": {"type": "http", "url": "https://bigquery.googleapis.com/mcp"},
    },
    # Google, first-party, remote. Compute control plane, not a query surface --
    # included precisely because a data question should fail on it.
    "managed-spark": {
        "key": "managed-spark",
        "answers_rows": False,
        "traced": False,
        "catalog": "google-lakehouse",
        "cites_version": False,
        "spec": {"type": "http",
                 "url": "https://dataproc-us-central1.googleapis.com/mcp"},
    },
}


# Wrap after definition so the specs above stay readable as what each project
# documents, rather than as what the harness launches.
for _s in SERVERS.values():
    _s["spec"] = _traced(_s["spec"])

# Remote servers have no binary to miss.
for _s in SERVERS.values():
    _s.setdefault("missing_binary", False)
