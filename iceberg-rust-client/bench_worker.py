#!/usr/bin/env python3
"""The pyiceberg half of the benchmark, in its own process.

Contract, identical to the Rust binary's IRC_MODE=bench: build the catalog
once, run each operation IRC_WARMUP times without recording, then IRC_ITERS
times emitting one JSON line per iteration with a nanosecond duration.

A separate process on purpose. The driver is itself Python, so timing this
in-process would hand pyiceberg a warm interpreter and an already-imported
library while the Rust side pays for a fresh exec. Both sides are spawned, both
sides exclude their own startup from the samples, and startup is measured
separately as its own number.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, os.pardir, "iceberg-conformance")
sys.path.insert(0, HERE)
sys.path.insert(0, CONF)

import yaml                                          # noqa: E402
import run_pyiceberg as rp                           # noqa: E402
from pyiceberg.catalog.rest import RestCatalog       # noqa: E402


def main():
    name = os.environ["IRC_CATALOG"]
    warmup = int(os.environ.get("IRC_WARMUP", "3"))
    iters = int(os.environ.get("IRC_ITERS", "30"))

    cfg = yaml.safe_load(open(os.path.join(CONF, "catalogs.yaml")))
    cat = next(c for c in cfg["catalogs"] if c["name"] == name)
    mode, _detail = rp.auth_plan(cat.get("auth"))
    # A static bearer is minted by the driver and passed in, exactly as the
    # Rust binary receives it, so the spawn-to-answer wall is the client's.
    catalog = RestCatalog(name, **rp.base_props(
        cat, mode, token=os.environ.get("IRC_TOKEN") or None))

    ns = tuple(cat["namespace"].split("."))
    table = ns + (cat["table"],)

    ops = [
        ("list_namespaces", lambda: catalog.list_namespaces()),
        ("load_namespace", lambda: catalog.load_namespace_properties(ns)),
        ("head_namespace", lambda: catalog.namespace_exists(ns)),
        ("list_tables", lambda: catalog.list_tables(ns)),
        ("load_table", lambda: catalog.load_table(table)),
        ("head_table", lambda: catalog.table_exists(table)),
    ]

    for op, call in ops:
        for _ in range(warmup):
            try:
                call()
            except Exception:                        # noqa: BLE001
                break
        for i in range(iters):
            started = time.perf_counter_ns()
            try:
                call()
            except Exception as e:                   # noqa: BLE001
                print(json.dumps({"client": "pyiceberg", "op": op, "iter": i,
                                  "ns": time.perf_counter_ns() - started,
                                  "error_kind": type(e).__name__}))
                break
            print(json.dumps({"client": "pyiceberg", "op": op, "iter": i,
                              "ns": time.perf_counter_ns() - started}))


if __name__ == "__main__":
    main()
