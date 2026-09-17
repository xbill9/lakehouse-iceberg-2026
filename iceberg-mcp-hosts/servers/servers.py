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

#: iceberg_tool resolves ICEBERG_CATALOGS_FILE relative to the *server's* cwd,
#: defaulting to a bare "catalogs.yaml". A host that launches the server from
#: anywhere but iceberg-conformance/ then gets FileNotFoundError on every tool
#: call -- which arrives at the model as a catalog error and reads like a dead
#: catalog rather than a missing path of ours. Pinned absolutely, as
#: capture_ground_truth.py and failure_modes.py already do, so a cell does not
#: depend on the cwd the host happened to start in.
CATALOGS_FILE = os.getenv(
    "ICEBERG_CATALOGS_FILE",
    os.path.join(os.path.dirname(HERE), "iceberg-conformance", "catalogs.yaml"))


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
    # ---------------------------------------------------------------- ours --
    # The instrument. Two entries, one server, one deliberate difference: who
    # does the arithmetic. Everything else is held still, which is what makes a
    # difference between hosts attributable to the host.
    #
    # This replaced a design that varied third-party servers. That design
    # measured four maintainers' scope decisions rather than any property of a
    # host, and it could not even be run: see evidence/server-surfaces.txt for
    # the ahodroj post-mortem. The servers it compared are kept below, disabled,
    # because the reason for the change is part of the result.
    "ours-engine": {
        "key": "ours-engine",
        "answers_rows": True,
        "traced": TRACE,
        "catalog": os.getenv("ICEBERG_CATALOG", "apache-polaris"),
        "cites_version": True,   # describe/count/scan all return the snapshot id
        "missing_binary": False,
        "arithmetic": "engine",
        "spec": {
            "command": sys.executable,
            "args": [os.path.join(HERE, "servers", "iceberg_mcp.py")],
            "env": {"ICEBERG_SCAN_FILTER": "1",
                    "ICEBERG_CATALOGS_FILE": CATALOGS_FILE,
                    "ICEBERG_CATALOG": os.getenv("ICEBERG_CATALOG",
                                                 "apache-polaris")},
        },
    },
    # The same server with the scan's `where`, COUNT, MIN and MAX withheld, so
    # the only way to a filtered count is for the model to do it. Paper 3
    # measured this on three frameworks; here it is measured on three hosts
    # running whatever model they pick for themselves.
    "ours-rows": {
        "key": "ours-rows",
        "answers_rows": True,
        "traced": TRACE,
        "catalog": os.getenv("ICEBERG_CATALOG", "apache-polaris"),
        "cites_version": True,
        "missing_binary": False,
        "arithmetic": "model",
        "spec": {
            "command": sys.executable,
            "args": [os.path.join(HERE, "servers", "iceberg_mcp.py")],
            # Both halves of the withholding. SCAN_FILTER=0 reverts the scan
            # tool to rows only; WITHHOLD removes the exact-count tool, which
            # SCAN_FILTER does not touch. Without the second, every host still
            # answered "how many rows" from the engine and the axis measured
            # nothing -- 6 of 6 runs on each variant, 2026-09-16.
            "env": {"ICEBERG_SCAN_FILTER": "0",
                    "ICEBERG_WITHHOLD": "iceberg_count_rows",
                    "ICEBERG_CATALOGS_FILE": CATALOGS_FILE,
                    "ICEBERG_CATALOG": os.getenv("ICEBERG_CATALOG",
                                                 "apache-polaris")},
        },
    },
}

#: Kept as the record of the abandoned design, and not run. `enabled: false` is
#: the same convention iceberg-conformance uses for a catalog holding
#: placeholder config: without it a broken entry answers with real errors that
#: read like findings. ahodroj is the case in point -- it cannot start, and a
#: matrix that included it would have scored a server that never ran.
RETIRED = {
    "morristai": {"why": "community Rust server, four tools, none return rows; "
                         "starts, but its surface is its maintainer's scope choice"},
    "ahodroj": {"why": "cannot start: package on no registry, and from git it "
                       "dies against mcp 2.x. See evidence/server-surfaces.txt"},
    "bigquery": {"why": "first-party but read-only SQL over a different catalog, "
                        "and exposes no snapshot id, so Q6 is unanswerable by surface"},
    "managed-spark": {"why": "compute control plane, no table read surface at all"},
}


# Wrap after definition so the specs above stay readable as what each project
# documents, rather than as what the harness launches.
for _s in SERVERS.values():
    _s["spec"] = _traced(_s["spec"])

# Remote servers have no binary to miss.
for _s in SERVERS.values():
    _s.setdefault("missing_binary", False)
