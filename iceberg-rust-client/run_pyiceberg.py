#!/usr/bin/env python3
"""Drive pyiceberg's RestCatalog over paper 1's read probes.

    $ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
    $ python3 run_pyiceberg.py                  # control catalog, the default
    apache-polaris     1 implicit, 12 ok, 4 not-expressible, 16 not-issued
    wrote evidence/pyiceberg-run-apache-polaris.json

Same catalogs, same fixture, same probe list and the same evidence shape as
run_rust.py, so the two runs can be put side by side and the only difference
between them is the client. Catalog configuration and token minting come from
the conformance harness rather than being reimplemented here.

Read-only by construction: the write probes are never issued, and they are
reported as NOT-ISSUED rather than as anything the client could not do.

Three catalog objects are built per run, not one. Two of paper 1's read probes
are steered by properties this client only reads at construction time --
`rest-page-size` and `snapshot-loading-mode` -- so asking both questions means
two more catalogs, and therefore two more GET /v1/config round trips. That is a
property of the client and is recorded with the run.
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, os.pardir, "iceberg-conformance")
sys.path.insert(0, CONF)

import yaml                                          # noqa: E402
from probe import auth as probe_auth                 # noqa: E402
from probe.spec import PROBES, WRITE_PROBES          # noqa: E402

import pyiceberg                                     # noqa: E402
import pyiceberg_map as pm                           # noqa: E402
import redact                                        # noqa: E402
from pyiceberg.catalog.rest import RestCatalog       # noqa: E402
from pyiceberg.catalog.rest.scan_planning import PlanTableScanRequest  # noqa: E402

# Probes this runner issues. The rest are write probes, which a read-only
# runner does not send, or absent, which no client can send.
ISSUED = [
    "list_namespaces", "list_namespaces_paged", "list_namespaces_parent",
    "load_namespace", "head_namespace", "list_tables", "load_table",
    "load_table_snapshots_all", "head_table", "load_credentials",
    "list_views", "plan_table_scan",
]


def auth_plan(spec):
    """How, if at all, this catalog's auth can be expressed to pyiceberg.

    Deliberately the same three words run_rust.py uses -- native, static,
    absent -- because the interesting output is where the two disagree.
    """
    kind = (spec or {}).get("type", "none")
    if kind == "none":
        return "native", "no authentication"
    if kind == "oauth2":
        return "native", "credential + oauth2-server-uri + scope"
    if kind == "bearer_env":
        return "native", "token"
    if kind == "snowflake_keypair":
        # auth.py:99-101 -- a credential with no colon becomes client_secret
        # with client_id None, the same shape the Rust crate sends.
        return "native", "credential with no client_id (bare secret)"
    if kind in ("gcloud", "azure_cli"):
        return "static", "bearer token minted outside the client; not refreshable by it"
    if kind == "sigv4":
        # The difference that decides two of the seven: rest.sigv4-enabled mounts
        # a botocore signer (rest/__init__.py:770), so the two AWS catalogs are
        # reachable through this client and not through the Rust crate.
        return "native", "rest.sigv4-enabled, signed per request by botocore"
    return "absent", "unrecognised auth type %r" % kind


def bearer_from_harness(spec, url):
    provider = probe_auth.build(spec)
    headers = provider.apply("GET", url, {}, None)
    value = headers.get("Authorization", "")
    if not value.startswith("Bearer "):
        raise RuntimeError("provider %r did not yield a bearer token" % spec.get("type"))
    return value[len("Bearer "):]


def base_props(cat, mode):
    props = {"uri": cat["base_url"]}
    if cat.get("warehouse"):
        props["warehouse"] = cat["warehouse"]

    spec = cat.get("auth") or {}
    kind = spec.get("type")
    if mode == "native" and kind == "oauth2":
        cid = os.environ.get(spec.get("client_id_env", ""), "")
        sec = os.environ.get(spec.get("client_secret_env", ""), "")
        if not sec:
            raise RuntimeError("%s is unset" % spec.get("client_secret_env"))
        props["credential"] = "%s:%s" % (cid, sec) if cid else sec
        if spec.get("token_url"):
            props["oauth2-server-uri"] = spec["token_url"]
        if spec.get("scope"):
            props["scope"] = spec["scope"]
    elif mode == "native" and kind == "bearer_env":
        props["token"] = os.environ.get(spec["env_var"], "")
    elif mode == "native" and kind == "snowflake_keypair":
        props["credential"] = bearer_from_harness(spec, cat["base_url"])
    elif mode == "native" and kind == "sigv4":
        props["rest.sigv4-enabled"] = "true"
        if spec.get("region"):
            props["rest.signing-region"] = spec["region"]
        if spec.get("service"):
            props["rest.signing-name"] = spec["service"]
    elif mode == "static":
        props["token"] = bearer_from_harness(spec, cat["base_url"])
    return props


class Run(object):
    """One catalog, one client, one pass over the read probes."""

    def __init__(self, cat, mode):
        self.cat = cat
        self.props = base_props(cat, mode)
        self.ns = tuple(cat["namespace"].split("."))
        self.table = self.ns + (cat["table"],)
        self.results = {}
        self.pairs = redact.values_for(cat, redact.secret_env_names(cat))

        started = time.time()
        self.catalog = RestCatalog(cat["name"], **self.props)
        self.config_ms = int((time.time() - started) * 1000)
        # Read-only introspection of what the catalog declared. This is the
        # same array paper 1's declaration tier reads, seen through the
        # client that acts on it.
        self.declared = {str(e) for e in self.catalog._supported_endpoints}

    def variant(self, **extra):
        """A second catalog object, for a probe steered by a property."""
        return RestCatalog(self.cat["name"], **dict(self.props, **extra))

    def record(self, probe_id, fn, gate=None, endpoint=None):
        """Issue one probe. A closed gate is the client's answer, not the catalog's."""
        declared = endpoint in self.declared if endpoint else None
        started = time.time()
        try:
            detail = fn()
        except NotImplementedError as e:
            # _check_endpoint refused: the endpoint was not in /v1/config.
            self.results[probe_id] = {
                "verdict": "GATED", "gate": gate, "endpoint_declared": declared,
                "ms": int((time.time() - started) * 1000),
                "error": redact.scrub(str(e), self.pairs),
            }
            return
        except Exception as e:                       # noqa: BLE001 -- recorded, not handled
            self.results[probe_id] = {
                "verdict": "FAILED", "endpoint_declared": declared,
                "ms": int((time.time() - started) * 1000),
                "error_kind": type(e).__name__,
                "error": redact.scrub(str(e), self.pairs),
            }
            return
        row = {
            "verdict": "OK", "endpoint_declared": declared,
            "ms": int((time.time() - started) * 1000), "detail": detail,
        }
        if gate and declared is False:
            # The call answered, and the probe's request was never sent.
            row["verdict"] = "SUBSTITUTED"
            row["gate"] = gate
        self.results[probe_id] = row

    def issue_all(self):
        c = self.catalog
        ns, table = self.ns, self.table

        self.record("list_namespaces",
                    lambda: {"count": len(c.list_namespaces())},
                    gate="refuses", endpoint="GET /v1/{prefix}/namespaces")

        paged = self.variant(**{"rest-page-size": "1"})
        self.record("list_namespaces_paged",
                    lambda: {"count": len(paged.list_namespaces()),
                             "page_size_sent": 1},
                    gate="refuses", endpoint="GET /v1/{prefix}/namespaces")

        self.record("list_namespaces_parent",
                    lambda: {"count": len(c.list_namespaces(ns))},
                    gate="refuses", endpoint="GET /v1/{prefix}/namespaces")

        self.record("load_namespace",
                    lambda: {"property_count": len(c.load_namespace_properties(ns))},
                    gate="refuses",
                    endpoint="GET /v1/{prefix}/namespaces/{namespace}")

        self.record("head_namespace",
                    lambda: {"exists": c.namespace_exists(ns)},
                    gate="substitutes",
                    endpoint="HEAD /v1/{prefix}/namespaces/{namespace}")

        self.record("list_tables",
                    lambda: {"count": len(c.list_tables(ns))},
                    gate="refuses",
                    endpoint="GET /v1/{prefix}/namespaces/{namespace}/tables")

        # Counts and integers only. A loadTable response carries locations and
        # can carry vended credentials; none of it belongs in a file that is
        # committed.
        loaded = {}

        def load_table():
            tbl = c.load_table(table)
            loaded["table"] = tbl
            md = tbl.metadata
            return {
                "format_version": md.format_version,
                "schema_field_count": len(md.schema().fields),
                "snapshot_count": len(md.snapshots),
                "has_current_snapshot": md.current_snapshot_id is not None,
                "partition_field_count": len(md.spec().fields),
                "sort_order_field_count": len(md.sort_order().fields),
            }

        self.record("load_table", load_table, gate="refuses",
                    endpoint="GET /v1/{prefix}/namespaces/{namespace}/tables/{table}")

        all_snaps = self.variant(**{"snapshot-loading-mode": "all"})
        self.record(
            "load_table_snapshots_all",
            lambda: {"snapshot_count": len(all_snaps.load_table(table).metadata.snapshots),
                     "snapshots_param_sent": "all"},
            gate="refuses",
            endpoint="GET /v1/{prefix}/namespaces/{namespace}/tables/{table}")

        self.record("head_table",
                    lambda: {"exists": c.table_exists(table)},
                    gate="substitutes",
                    endpoint="HEAD /v1/{prefix}/namespaces/{namespace}/tables/{table}")

        def load_credentials():
            tbl = loaded.get("table")
            if tbl is None:
                raise RuntimeError("load_table did not succeed; nothing to ask about")
            # The count, never the keys and never the values.
            return {"credential_property_count":
                    len(c.load_credentials(table, tbl.metadata.location))}

        self.record(
            "load_credentials", load_credentials, gate="refuses",
            endpoint="GET /v1/{prefix}/namespaces/{namespace}/tables/{table}/credentials")

        self.record("list_views",
                    lambda: {"count": len(c.list_views(ns))},
                    gate="silent-empty",
                    endpoint="GET /v1/{prefix}/namespaces/{namespace}/views")

        self.record(
            "plan_table_scan",
            lambda: {"file_scan_task_count": len(c.plan_scan(
                table, PlanTableScanRequest(select=["*"], case_sensitive=False)))},
            gate="refuses",
            endpoint="POST /v1/{prefix}/namespaces/{namespace}/tables/{table}/plan")


def merge(run):
    """One row per probe in paper 1's list, issued or not."""
    out = []
    for p in list(PROBES) + list(WRITE_PROBES):
        status, symbol, ref, note, gate = (tuple(pm.MAP[p.id][:4])
                                           + (pm.MAP[p.id][4],))
        row = {
            "probe": p.id,
            "surface": p.surface,
            "endpoint": p.signature(),
            "client_status": status,
            "symbol": symbol,
            "source_ref": ref,
            "declaration_gate": gate,
        }
        if p.id == "config":
            row.update({"verdict": "IMPLICIT", "ms": run.config_ms if run else None,
                        "note": "issued by RestCatalog.__init__ on construction; "
                                "not separately callable"})
            if run:
                row["detail"] = {"endpoints_declared": len(run.declared)}
        elif run and p.id in run.results:
            row.update(run.results[p.id])
        elif status not in ("reachable", "implicit"):
            row.update({"verdict": "NOT-EXPRESSIBLE",
                        "why": note or "no method issues this request"})
        else:
            # Expressible, and deliberately not sent. Not the same thing, and
            # scoring it as NOT-EXPRESSIBLE would understate the client.
            row.update({"verdict": "NOT-ISSUED",
                        "why": "read-only runner; this client can express it"})
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[],
                    help="catalog name; repeatable. Default: apache-polaris only.")
    ap.add_argument("--all", action="store_true",
                    help="every enabled catalog. Costs vendor calls; control catalog first.")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(CONF, "catalogs.yaml")))
    catalogs = [c for c in cfg["catalogs"] if c.get("enabled", True)]
    if not args.all:
        wanted = args.only or ["apache-polaris"]
        catalogs = [c for c in catalogs if c["name"] in wanted]
        missing = set(wanted) - {c["name"] for c in catalogs}
        if missing:
            sys.exit("not configured or not enabled: %s" % ", ".join(sorted(missing)))

    for cat in catalogs:
        mode, detail = auth_plan(cat.get("auth"))
        meta = {
            "catalog": cat["name"],
            "client": "pyiceberg %s" % pyiceberg.__version__,
            "control": cat["name"] == "apache-polaris",
            "auth_mode": mode,
            "auth_detail": detail,
            "catalog_objects_built": 3,
            "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        run, failed_hard = None, False
        if mode == "absent":
            print("%-18s auth not expressible: %s" % (cat["name"], detail))
        else:
            try:
                run = Run(cat, mode)
                run.issue_all()
                meta["endpoints_declared"] = sorted(run.declared)
            except Exception as e:                   # noqa: BLE001
                failed_hard = True
                pairs = redact.values_for(cat, redact.secret_env_names(cat))
                meta["transport_error"] = redact.scrub(
                    "%s: %s" % (type(e).__name__, e), pairs)

        merged = merge(run)
        counts = {}
        for r in merged:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        meta["counts"] = counts

        document = {"meta": meta, "rows": merged}
        redact.verify(document, redact.values_for(
            cat, redact.secret_env_names(cat)))

        out = os.path.join(HERE, "evidence", "pyiceberg-run-%s.json" % cat["name"])
        # Never overwrite good evidence with a failed run.
        if failed_hard:
            out = out.replace(".json", ".failed.json")
        with open(out, "w") as fh:
            json.dump(document, fh, indent=2)
            fh.write("\n")

        print("%-18s %s" % (cat["name"], ", ".join(
            "%d %s" % (v, k.lower()) for k, v in sorted(counts.items()))))
        print("wrote %s" % os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
