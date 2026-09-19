#!/usr/bin/env python3
"""One Iceberg MCP server, pointed at each catalog in turn.

    python3 sweep_catalogs.py                       # every catalog in catalogs.yaml
    python3 sweep_catalogs.py --only apache-polaris

For each catalog this starts servers/iceberg_mcp.py over stdio with only
ICEBERG_CATALOG changed, speaks MCP to it directly -- initialize, tools/list,
then each of the four tools -- and records what came back. No model is
involved, so a difference between two catalogs is a difference between the
catalogs, not between two answers.

Raw results go to evidence/catalog-sweep-<catalog>.json, which is ignored:
tool output carries metadata locations, bucket names and account ids. Publish
through the anonymiser.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(HERE, "servers", "iceberg_mcp.py")
CATALOGS = os.path.join(ROOT, "iceberg-conformance", "catalogs.yaml")
EVIDENCE = os.path.join(HERE, "evidence")
TIMEOUT = 180


class Session(object):
    """A stdio MCP client: one JSON object per line, ids in order."""

    def __init__(self, catalog):
        env = dict(os.environ, ICEBERG_CATALOG=catalog,
                   ICEBERG_CATALOGS_FILE=CATALOGS, ICEBERG_SCAN_FILTER="1",
                   ICEBERG_CATALOG_BUDGET="1000")
        self.proc = subprocess.Popen([sys.executable, SERVER], env=env,
                                     cwd=os.path.join(ROOT, "iceberg-conformance"),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.next_id = 0

    def notify(self, method, params=None):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method,
               "params": params or {}}
        t0 = time.monotonic()
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        seconds = time.monotonic() - t0
        if not line:
            raise RuntimeError("server closed stdout: %s"
                               % self.proc.stderr.read()[-2000:])
        reply = json.loads(line)
        if reply.get("id") != self.next_id:
            raise RuntimeError("reply id %r for request %r" % (reply.get("id"), self.next_id))
        return reply, seconds

    def call(self, name, arguments):
        reply, seconds = self.request("tools/call", {"name": name, "arguments": arguments})
        result = reply.get("result") or {}
        text = "".join(c.get("text", "") for c in result.get("content") or [])
        return {"tool": name, "arguments": arguments, "seconds": round(seconds, 3),
                # iceberg_tool reports a failed catalog call as text so an agent
                # can still answer, which leaves isError false. Count it anyway.
                "isError": (bool(result.get("isError")) or "error" in reply
                            or text.startswith("CATALOG ERROR")),
                "text": text or json.dumps(reply.get("error"))}

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def first_table(listing):
    """The first `namespace.table` line of iceberg_list_tables' output."""
    for line in listing.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if "." in line and " " not in line and not line.endswith(":"):
            return line
    return None


def sweep(catalog, table=None):
    record = {"catalog": catalog, "measured": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "calls": []}
    s = Session(catalog)
    try:
        init, secs = s.request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "sweep_catalogs", "version": "1"}})
        s.notify("notifications/initialized")
        record["initialize"] = {"seconds": round(secs, 3),
                                "serverInfo": init.get("result", {}).get("serverInfo")}
        tools, _ = s.request("tools/list")
        record["tools"] = [t["name"] for t in tools.get("result", {}).get("tools", [])]

        listing = s.call("iceberg_list_tables", {})
        record["calls"].append(listing)
        table = table or first_table(listing["text"])
        record["table"] = table
        if table:
            for name, args in (("iceberg_describe_table", {"table": table}),
                               ("iceberg_count_rows", {"table": table}),
                               ("iceberg_scan_table", {"table": table, "limit": 3})):
                record["calls"].append(s.call(name, args))
    except Exception as exc:  # noqa: BLE001 - a transport failure is a result too
        record["transport_error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        s.close()
    return record


def summary_line(r):
    if "transport_error" in r and not r["calls"]:
        return "%-20s TRANSPORT  %s" % (r["catalog"], r["transport_error"][:90])
    cells = []
    for c in r["calls"]:
        short = c["tool"].replace("iceberg_", "")
        cells.append("%s=%s(%.1fs)" % (short, "ERR" if c["isError"] else "ok", c["seconds"]))
    return "%-20s %-36s %s" % (r["catalog"], r.get("table") or "(no table)", "  ".join(cells))


def report():
    """evidence/catalog-sweep-summary.txt, rebuilt from the saved JSON only."""
    import glob
    import platform
    from importlib import metadata

    out = ["# One Iceberg MCP server (servers/iceberg_mcp.py), one catalog per process.",
           "# Rebuilt by `python3 sweep_catalogs.py --report-only` from the saved JSON.",
           "#",
           "# python %s" % platform.python_version()]
    for pkg in ("pyiceberg", "pyarrow", "fsspec", "s3fs", "adlfs", "botocore",
                "azure-identity", "google-auth"):
        try:
            out.append("# %s %s" % (pkg, metadata.version(pkg)))
        except metadata.PackageNotFoundError:
            out.append("# %s not installed" % pkg)
    out += ["", "%-19s %-21s %-22s %5s  %-15s %s" % (
        "catalog", "measured (UTC)", "table", "rows", "partitioned", "seconds: list describe count scan")]
    for path in sorted(glob.glob(os.path.join(EVIDENCE, "catalog-sweep-*.json"))):
        if path.endswith(".failed.json"):
            continue
        r = json.load(open(path))
        calls = {c["tool"]: c for c in r["calls"]}
        desc = calls.get("iceberg_describe_table", {}).get("text", "")
        part = next((l.split(": ", 1)[1] for l in desc.splitlines()
                     if l.startswith("partitioned by: ")), "-")
        count = calls.get("iceberg_count_rows", {}).get("text", "")
        rows = count.split(" ", 1)[0] if count[:1].isdigit() else "-"
        secs = " ".join("%.1f%s" % (c["seconds"], "!" if c["isError"] else "")
                        for c in r["calls"])
        out.append("%-19s %-21s %-22s %5s  %-15s %s" % (
            r["catalog"], r["measured"], r.get("table") or "-", rows, part, secs))
        out.append("%-19s tools/list: %s" % ("", ", ".join(r.get("tools") or [])))
    out += ["", "! marks a call whose result was an error. One run per catalog;",
            "the first call includes building the catalog client and fetching its token."]
    path = os.path.join(EVIDENCE, "catalog-sweep-summary.txt")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild catalog-sweep-summary.txt, no network")
    ap.add_argument("--only", help="comma-separated catalog names")
    ap.add_argument("--table", help="namespace.table to use instead of the first listed")
    a = ap.parse_args()
    if a.report_only:
        return report()

    entries = yaml.safe_load(open(CATALOGS))["catalogs"]
    names = [e["name"] for e in entries if e.get("enabled", True)]
    if a.only:
        wanted = a.only.split(",")
        names = [n for n in names if n in wanted]
    os.makedirs(EVIDENCE, exist_ok=True)
    for name in names:
        r = sweep(name, a.table)
        path = os.path.join(EVIDENCE, "catalog-sweep-%s.json" % name)
        dead = not r["calls"] or all(c["isError"] for c in r["calls"])
        if dead and os.path.exists(path):
            # Never overwrite good evidence with a run where nothing answered.
            path = path.replace(".json", ".failed.json")
        with open(path, "w") as fh:
            json.dump(r, fh, indent=2)
        print(summary_line(r))
    report()


if __name__ == "__main__":
    main()
