#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read each catalog's answer directly, so grading never goes through an agent.

The thing being measured cannot also be the thing that says whether the
measurement was right. Every value here comes from pyiceberg against the REST
catalog, built by the same ``iceberg_tool.catalog()`` the agents use -- so a
credential the agents lack, this lacks too, and it fails here first.

    python3 capture_ground_truth.py

Writes ground-truth.txt and environment.txt into the raw evidence directory.
Nothing is written unless every catalog answers: a partial ground truth would
score the missing catalog's runs against nothing.
"""
import datetime
import importlib.metadata
import os
import platform
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "iceberg-conformance"))
os.environ.setdefault("ICEBERG_CATALOGS_FILE",
                      os.path.join(ROOT, "iceberg-conformance", "catalogs.yaml"))

from run_matrix import CATALOGS, LEGS, RAW  # noqa: E402

PACKAGES = ["google-adk", "google-genai", "strands-agents", "agent-framework-core",
            "agent-framework-foundry", "pyiceberg", "pyarrow", "fsspec", "botocore",
            "azure-identity"]
#: OneLake maps Fabric schemas to namespaces, so its fixture is not in probe_ns.
TABLE = {"microsoft-onelake": "dbo.probe_table"}


def read(catalog: str) -> list:
    import iceberg_tool

    os.environ["ICEBERG_CATALOG"] = catalog
    iceberg_tool._catalog = None      # built once per process; rebuild per catalog
    name = TABLE.get(catalog, "probe_ns.probe_table")
    tbl = iceberg_tool.catalog().load_table(name)
    snap = tbl.current_snapshot()
    rows = snap.summary.get("total-records") if snap else None
    if rows is None:
        raise RuntimeError("no total-records in the current snapshot summary")
    return ["catalog=%s table=%s" % (catalog, name),
            "  rows=%s" % rows,
            "  columns=%s" % ",".join(f.name for f in tbl.schema().fields),
            "  snapshot_id=%s" % snap.snapshot_id,
            "  metadata_location=%s" % tbl.metadata_location]


def environment(now: str) -> list:
    import common
    import iceberg_tool
    from run_once import load

    lines = ["# environment the paper 3 evidence was measured in, captured %s" % now,
             "python=%s" % platform.python_version(),
             "platform=%s" % platform.system()]
    lines += ["%s=%s" % (p, importlib.metadata.version(p)) for p in PACKAGES]
    for leg in LEGS:
        lines.append("model.%s=%s" % (leg, common.resolve_model(leg, load(leg).DEFAULT_MODEL)))
    lines += ["vertex_ai=%s" % os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "unset"),
              "vertex_location=%s" % os.getenv("GOOGLE_CLOUD_LOCATION", "unset"),
              "aws_region=%s" % os.getenv("AWS_REGION", "unset"),
              "catalog_budget=%d" % iceberg_tool.CATALOG_BUDGET,
              "instruction=v%d" % iceberg_tool.INSTRUCTION_VERSION]
    return lines


def main() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    truth, failed = [], []
    for catalog in CATALOGS:
        try:
            block = read(catalog)
        except Exception as exc:  # noqa: BLE001 - report every catalog, then refuse
            failed.append(catalog)
            print("FAILED %s: %s: %s" % (catalog, type(exc).__name__, str(exc)[:300]))
            continue
        print("\n".join(block))
        truth += block
    if failed:
        sys.exit("\nground truth NOT written; failed: %s" % ", ".join(failed))

    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "ground-truth.txt"), "w") as handle:
        handle.write("# ground truth captured %s, read directly from each catalog\n"
                     "# not via any agent; every agent answer is checked against this\n\n"
                     % now)
        handle.write("\n".join(truth) + "\n")
    env = environment(now)
    with open(os.path.join(RAW, "environment.txt"), "w") as handle:
        handle.write("\n".join(env) + "\n")
    print("\n".join(env))
    print("\nwrote %s/ground-truth.txt and environment.txt" % RAW)


if __name__ == "__main__":
    main()
