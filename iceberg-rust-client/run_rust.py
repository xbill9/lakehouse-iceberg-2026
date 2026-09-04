#!/usr/bin/env python3
"""Drive the Rust probe binary against a catalog and write merged evidence.

    $ cargo build
    $ python3 run_rust.py --only apache-polaris --storage local-fs
    apache-polaris   7 issued, 6 ok, 1 failed, 26 not expressible
    wrote evidence/rust-run-apache-polaris.json

Control first, as everywhere else in this repository: a red cell on Polaris is
this harness's bug until proven otherwise, and the first run of this driver
proved exactly that (see `load_table` and IRC_STORAGE in the README).

Catalog configuration, and the token minting for the providers that need it,
are taken from the conformance harness rather than reimplemented -- the two
papers have to be measuring the same catalogs, with the same credentials, or
the comparison is between two setups instead of two clients.

Nothing that could identify an account is written to disk: the evidence carries
the catalog's name, never its URL, warehouse, namespace or any token.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, os.pardir, "iceberg-conformance")
sys.path.insert(0, CONF)

import yaml                                          # noqa: E402
from probe import auth as probe_auth                 # noqa: E402
import operation_map as om                           # noqa: E402
from probe.spec import PROBES, WRITE_PROBES          # noqa: E402

BINARY = os.path.join(HERE, "target", "debug", "irc-probe")

# Which probes the Rust binary issues. It is the driver's job, not the
# binary's, to say why the others were not issued.
ISSUED_BY_BINARY = [
    "config", "list_namespaces", "list_namespaces_parent", "load_namespace",
    "head_namespace", "list_tables", "load_table", "head_table",
]


def auth_plan(spec):
    """How, if at all, this catalog's auth can be expressed to the crate.

    Returns (mode, detail). `mode` is one of:

      native      the crate has a first-class mechanism for it
      static      a token is minted outside the crate and passed as a static
                  bearer. It works, and it cannot be refreshed by the crate:
                  regenerate_token() re-runs an OAuth2 client_credentials
                  grant, which is not how this token was obtained.
      absent      the crate cannot express it at all
    """
    kind = (spec or {}).get("type", "none")
    if kind == "none":
        return "native", "no authentication"
    if kind == "oauth2":
        return "native", "credential + oauth2-server-uri + scope"
    if kind == "bearer_env":
        return "native", "token"
    if kind == "snowflake_keypair":
        # catalog.rs:238 -- a `credential` with no colon is sent as
        # client_secret with no client_id, which is the shape Horizon wants.
        # Whether Horizon accepts the crate's grant is a measurement, not an
        # assumption, so this is still run rather than asserted.
        return "native", "credential with no client_id (bare secret)"
    if kind in ("gcloud", "azure_cli"):
        return "static", "bearer token minted outside the crate; not refreshable by it"
    if kind == "sigv4":
        return "absent", ("SigV4 is computed per request over the canonical "
                          "request; the crate has no signer and a static "
                          "header cannot carry a per-request signature")
    return "absent", "unrecognised auth type %r" % kind


def bearer_from_harness(spec, url):
    """Mint a token using the conformance harness's own provider."""
    provider = probe_auth.build(spec)
    headers = provider.apply("GET", url, {}, None)
    value = headers.get("Authorization", "")
    if not value.startswith("Bearer "):
        raise RuntimeError("provider %r did not yield a bearer token" % spec.get("type"))
    return value[len("Bearer "):]


def build_env(cat, mode, storage):
    env = dict(os.environ)
    env["IRC_CATALOG"] = cat["name"]
    env["IRC_URI"] = cat["base_url"]
    env["IRC_NAMESPACE"] = cat["namespace"]
    env["IRC_TABLE"] = cat["table"]
    env["IRC_STORAGE"] = storage
    if cat.get("warehouse"):
        env["IRC_WAREHOUSE"] = cat["warehouse"]

    spec = cat.get("auth") or {}
    kind = spec.get("type")
    if mode == "native" and kind == "oauth2":
        cid = os.environ.get(spec.get("client_id_env", ""), "")
        sec = os.environ.get(spec.get("client_secret_env", ""), "")
        if not sec:
            raise RuntimeError("%s is unset" % spec.get("client_secret_env"))
        env["IRC_CREDENTIAL"] = "%s:%s" % (cid, sec) if cid else sec
        if spec.get("token_url"):
            env["IRC_OAUTH2_SERVER_URI"] = spec["token_url"]
        if spec.get("scope"):
            env["IRC_SCOPE"] = spec["scope"]
    elif mode == "native" and kind == "bearer_env":
        env["IRC_TOKEN"] = os.environ.get(spec["env_var"], "")
    elif mode == "native" and kind == "snowflake_keypair":
        env["IRC_CREDENTIAL"] = bearer_from_harness(spec, cat["base_url"])
    elif mode == "static":
        env["IRC_TOKEN"] = bearer_from_harness(spec, cat["base_url"])
    return env


def run_binary(cat, mode, storage):
    if not os.path.exists(BINARY):
        sys.exit("%s not built -- run `cargo build` first" % BINARY)
    env = build_env(cat, mode, storage)
    started = time.time()
    proc = subprocess.run([BINARY], env=env, capture_output=True, text=True,
                          timeout=180)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows, proc.returncode, proc.stderr.strip(), time.time() - started


def merge(rows):
    """One row per probe in paper 1's list, issued or not."""
    by_probe = {r["probe"]: r for r in rows if r.get("probe") != "_meta"}
    out = []
    for p in list(PROBES) + list(WRITE_PROBES):
        status, symbol, ref, note = om.MAP[p.id]
        row = {
            "probe": p.id,
            "surface": p.surface,
            "endpoint": p.signature(),
            "client_status": status,
            "rust_symbol": symbol,
            "source_ref": ref,
        }
        if p.id in by_probe:
            r = by_probe[p.id]
            row["verdict"] = ("IMPLICIT" if r.get("ok") is None
                              else "OK" if r["ok"] else "FAILED")
            row["ms"] = r.get("ms")
            if r.get("ok") is True:
                row["detail"] = r.get("detail")
            elif r.get("ok") is False:
                row["error_kind"] = r.get("error_kind")
                row["error"] = r.get("error")
            else:
                row["note"] = r.get("note")
        else:
            # Not a failure. There is no request to send.
            row["verdict"] = "NOT-EXPRESSIBLE"
            row["why"] = note or "no method issues this request"
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[],
                    help="catalog name; repeatable. Default: apache-polaris only.")
    ap.add_argument("--storage", default="local-fs",
                    choices=["local-fs", "memory", "none"],
                    help="StorageFactory to give the client. Recorded with the run.")
    ap.add_argument("--all", action="store_true",
                    help="every enabled catalog. Costs vendor calls; control first.")
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
            "crate": "iceberg-catalog-rest 0.10.1",
            "control": cat["name"] == "apache-polaris",
            "storage_factory": args.storage,
            "auth_mode": mode,
            "auth_detail": detail,
            "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if mode == "absent":
            # Recorded, and not run: there is no request this client can sign.
            # The paper still owes a live demonstration of that, which is a
            # separate mode of this driver and not this row.
            print("%-18s auth not expressible: %s" % (cat["name"], detail))
            rows, rc, stderr = [], None, ""
        else:
            rows, rc, stderr, _ = run_binary(cat, mode, args.storage)
            meta["exit_code"] = rc
            if stderr:
                meta["stderr"] = stderr
            for r in rows:
                if r.get("probe") == "_meta":
                    meta["binary_reported"] = {k: v for k, v in r.items()
                                               if k not in ("probe", "catalog")}

        merged = merge(rows)
        counts = {}
        for r in merged:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        meta["counts"] = counts

        out = os.path.join(HERE, "evidence", "rust-run-%s.json" % cat["name"])
        # Never overwrite good evidence with a failed run.
        if mode != "absent" and rc not in (0, None) and not any(
                r["verdict"] == "OK" for r in merged):
            out = out.replace(".json", ".failed.json")
        with open(out, "w") as fh:
            json.dump({"meta": meta, "rows": merged}, fh, indent=2)
            fh.write("\n")

        print("%-18s %s" % (cat["name"], ", ".join(
            "%d %s" % (v, k.lower()) for k, v in sorted(counts.items()))))
        print("wrote %s" % os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
