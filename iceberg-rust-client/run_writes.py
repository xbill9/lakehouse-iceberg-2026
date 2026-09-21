#!/usr/bin/env python3
"""Issue every write endpoint the crate can express, against the control only.

    $ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
    $ python3 run_writes.py
    apache-polaris     11 ok, 1 unsupported, 0 failed
    wrote evidence/rust-write-surface.txt

run_rust.py is read-only by construction, so it reports the eleven write
endpoints as NOT-ISSUED: the crate has a method and no request was sent. That
is a claim about the sweep. Whether those endpoints work is a different claim
and needs the request.

The control catalog is the only place this runs. It is local, permissive and
disposable, and paper 1's rule is that a red cell there is our bug rather than
a finding -- which is exactly what a write probe needs to be trusted. Every
request goes through wire_proxy.py, so what the client put on the wire is
recorded beside what came back.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, os.pardir, "iceberg-conformance")
sys.path.insert(0, CONF)
sys.path.insert(0, HERE)

import yaml                                          # noqa: E402
import wire_proxy                                    # noqa: E402
import run_rust                                      # noqa: E402
import operation_map as om                           # noqa: E402

OUT = os.path.join(HERE, "evidence", "rust-write-surface.txt")

# The eleven the read-only sweep reports as NOT-ISSUED, plus the one it
# reports as NOT-EXPRESSIBLE because the method is a stub. Ordered as the
# binary issues them.
EXPECTED = [
    "create_namespace", "update_namespace_props", "create_table",
    "commit_table", "commit_remove_properties", "commit_add_schema",
    "commit_set_current_schema", "commit_upgrade_format_version",
    "rename_table", "drop_table_purge", "drop_table", "drop_namespace",
]


def endpoint_of(probe_id):
    row = om.MAP.get(probe_id)
    return row[0] if row else "--"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="apache-polaris",
                    help="control catalog name in catalogs.yaml")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(CONF, "catalogs.yaml")))
    cats = {c["name"]: c for c in cfg["catalogs"]}
    cat = cats.get(args.catalog)
    if cat is None:
        sys.exit("no such catalog: %s" % args.catalog)
    if not str(cat.get("base_url", "")).startswith(("http://localhost",
                                                    "http://127.0.0.1")):
        sys.exit("refusing to write to a catalog that is not local: %s"
                 % cat.get("base_url"))

    base, log, shutdown = wire_proxy.start(cat["base_url"])
    mode, _detail = run_rust.auth_plan(cat.get("auth") or {})
    env = run_rust.build_env(cat, mode, "local-fs")
    env["IRC_URI"] = base
    env["IRC_MODE"] = "writes"
    env["IRC_ALLOW_WRITES"] = "yes"

    binary = os.environ.get("IRC_BINARY") or os.path.join(
        HERE, "target", "release", "irc-probe")
    try:
        proc = subprocess.run([binary], env=env, capture_output=True,
                              text=True, timeout=300)
    finally:
        shutdown()

    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            rows.append(json.loads(line))
    by_probe = {r["probe"]: r for r in rows if "probe" in r}

    ok = sum(1 for p in EXPECTED
             if by_probe.get(p, {}).get("ok") is True)
    unsupported = sum(
        1 for p in EXPECTED
        if by_probe.get(p, {}).get("error_kind") == "FeatureUnsupported")
    failed = sum(1 for p in EXPECTED
                 if by_probe.get(p, {}).get("ok") is False
                 and by_probe[p].get("error_kind") != "FeatureUnsupported")

    if not by_probe:
        sys.stderr.write(proc.stderr)
        sys.exit("the binary produced no probe rows")

    out = []
    out.append("Write surface of iceberg-catalog-rest 0.10.1, issued against"
               " the control catalog.")
    out.append("Written by run_writes.py. Every request went through"
               " wire_proxy.py, which")
    out.append("logged method, path and the update kinds in the body. Header"
               " values are never logged.")
    out.append("")
    out.append("  catalog        %s" % args.catalog)
    out.append("  scratch        %s"
               % by_probe.get("_writes_scratch", {}).get("namespace", "--"))
    out.append("  binary         %s" % os.path.relpath(binary, HERE))
    out.append("")
    out.append("## Probes")
    out.append("")
    out.append("  %-30s %-12s %-6s %s"
               % ("probe", "verdict", "ms", "endpoint"))
    for p in EXPECTED:
        r = by_probe.get(p)
        if r is None:
            verdict, ms = "MISSING", "--"
        elif r.get("ok") is True:
            verdict, ms = "OK", r.get("ms", "--")
        elif r.get("error_kind") == "FeatureUnsupported":
            verdict, ms = "UNSUPPORTED", r.get("ms", "--")
        else:
            verdict, ms = "FAILED", r.get("ms", "--")
        out.append("  %-30s %-12s %-6s %s"
                   % (p, verdict, ms, endpoint_of(p)))
    out.append("")
    out.append("  %d ok, %d unsupported, %d failed"
               % (ok, unsupported, failed))
    out.append("")

    out.append("## What each probe returned")
    out.append("")
    for p in EXPECTED:
        r = by_probe.get(p) or {}
        detail = r.get("detail")
        if detail is not None:
            out.append("  %-30s %s" % (p, json.dumps(detail, sort_keys=True)))
        elif r.get("error"):
            out.append("  %-30s %s: %s"
                       % (p, r.get("error_kind"), r.get("error")))
    for extra in ("_create_table_format_version_property",
                  "_create_namespace_two_level",
                  "_load_namespace_two_level",
                  "_drop_namespace_two_level"):
        r = by_probe.get(extra) or {}
        if r.get("detail") is not None:
            out.append("  %-30s %s"
                       % (extra, json.dumps(r["detail"], sort_keys=True)))
        elif r.get("error"):
            out.append("  %-30s %s: %s"
                       % (extra, r.get("error_kind"), r.get("error")))
    residue = by_probe.get("_residue_check", {}).get("detail")
    out.append("")
    out.append("  residue check                  %s"
               % json.dumps(residue, sort_keys=True))
    out.append("")

    out.append("## Requests on the wire, in order")
    out.append("")
    out.append("  %-7s %-4s %s" % ("method", "code", "path"))
    for entry in log:
        line = "  %-7s %-4s %s" % (entry["method"], entry["status"],
                                   entry["path"])
        if entry["query"]:
            line += "?" + entry["query"]
        out.append(line)
        sent = entry.get("sent") or {}
        if sent.get("updates"):
            out.append("          updates: %s" % ", ".join(
                str(u) for u in sent["updates"]))
        if sent.get("requirements"):
            out.append("          requirements: %s" % ", ".join(
                str(u) for u in sent["requirements"]))
        elif sent.get("keys") and not sent.get("updates"):
            # A create or rename body. The field NAMES answer what the crate
            # can express; the values are the caller's and stay out of here.
            out.append("          body fields: %s" % ", ".join(sent["keys"]))
    out.append("")
    out.append("  %d request(s)" % len(log))

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")

    print("%-18s %d ok, %d unsupported, %d failed"
          % (args.catalog, ok, unsupported, failed))
    print("wrote %s   %d request(s)" % (os.path.relpath(OUT, HERE), len(log)))
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)


if __name__ == "__main__":
    main()
