#!/usr/bin/env python3
"""Drive the Rust probe binary against a catalog and write merged evidence.

    $ cargo build
    $ python3 run_rust.py --only apache-polaris --storage local-fs
    apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
    wrote evidence/rust-run-apache-polaris.json

NOT-EXPRESSIBLE and NOT-ISSUED are different answers and are counted apart. The
first means this client has no request to send; the second means the binary is
read-only and did not send one it could have. Folding the write probes into the
first understated the crate by eleven rows.

Control first, as everywhere else in this repository: a red cell on Polaris is
this harness's bug until proven otherwise, and the first run of this driver
proved exactly that (see `load_table` and IRC_STORAGE in the README).

Catalog configuration, and the token minting for the providers that need it,
are taken from the conformance harness rather than reimplemented -- the two
papers have to be measuring the same catalogs, with the same credentials, or
the comparison is between two setups instead of two clients.

Nothing that could identify an account is written to disk: the evidence carries
the catalog's name, never its URL, warehouse, namespace or any token. Error text
comes from the client rather than from us, so it goes through redact.py, which
refuses to write a document in which a configured value survived.
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
import redact                                        # noqa: E402
from probe.spec import PROBES, WRITE_PROBES          # noqa: E402

# IRC_BINARY exists for one purpose: reproducing the no-TLS failure with a
# binary built without `rustls-tls`, into its own target directory, so the
# evidence binary is never the one rebuilt. Runs made with it carry --tag.
BINARY = os.environ.get("IRC_BINARY") or os.path.join(HERE, "target", "debug", "irc-probe")

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
                          "request; this crate has no signer and a static "
                          "header cannot carry a per-request signature "
                          "(upstream issue #1236, open). Reachable in Rust "
                          "only by leaving the REST protocol for "
                          "iceberg-catalog-glue or iceberg-catalog-s3tables")
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


def run_binary(cat, mode, storage, delegation=None):
    if not os.path.exists(BINARY):
        sys.exit("%s not built -- run `cargo build` first" % BINARY)
    env = build_env(cat, mode, storage)
    if delegation:
        # The crate never sends this header on its own; pyiceberg sends
        # `vended-credentials` by default. As a static header.* property the
        # crate attaches it to every request, which is how a Rust caller
        # would have to ask.
        env["IRC_HEADERS_JSON"] = json.dumps(
            {"X-Iceberg-Access-Delegation": delegation})
    started = time.time()
    proc = subprocess.run([BINARY], env=env, capture_output=True, text=True,
                          timeout=180)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows, proc.returncode, proc.stderr.strip(), time.time() - started


def sigv4_demo(cat, storage):
    """Hand the crate one SigV4 signature as a static header, and watch what
    it is worth.

    SigV4 signs the method, path, query string and a set of headers, so a
    signature is valid for exactly one request. The crate's only way to carry
    an arbitrary credential is `header.<name>`, which it attaches to every
    request unchanged. This signs the first request the crate will send --
    GET /v1/config with its warehouse query and the two headers the crate adds
    -- and nothing else. It is a consequence of a known limitation (upstream
    #1236, open), demonstrated rather than asserted; it is not a finding.
    """
    from urllib.parse import urlencode
    spec = cat.get("auth") or {}
    provider = probe_auth.build(spec)
    url = cat["base_url"].rstrip("/") + "/v1/config"
    if cat.get("warehouse"):
        # The crate builds this with reqwest's .query(), which is
        # form-urlencoding. Sign exactly what is sent.
        url += "?" + urlencode({"warehouse": cat["warehouse"]})
    signed = provider.apply("GET", url, {
        "content-type": "application/json",
        "x-client-version": "0.14.1",     # catalog.rs:56, sent on every request
    }, None)
    carry = {k: v for k, v in signed.items()
             if k.lower() in ("authorization", "x-amz-date", "x-amz-security-token")}
    env = build_env(cat, "static-headers", storage)
    env["IRC_HEADERS_JSON"] = json.dumps(carry)
    proc = subprocess.run([BINARY], env=env, capture_output=True, text=True,
                          timeout=180)
    rows = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]

    # The crate's GET /v1/config is implicit, so the run alone cannot say
    # whether the signature was good for the one request it was computed for.
    # Replay the same headers outside the crate, to that request and to the
    # next one, and record both statuses: the control for this demonstration.
    import requests
    replay = {}
    base = {"content-type": "application/json", "x-client-version": "0.14.1"}
    r = requests.get(url, headers=dict(base, **carry), timeout=30)
    replay["GET /v1/config (the signed request)"] = r.status_code
    # overrides first, then defaults, as paper 1's runner does: S3 Tables puts
    # its prefix under defaults, and reading overrides alone sent the replay to
    # a route that does not exist (404) on the first attempt.
    body = r.json() if r.ok else {}
    prefix = ((body.get("overrides") or {}).get("prefix")
              or (body.get("defaults") or {}).get("prefix"))
    nxt = cat["base_url"].rstrip("/") + "/v1/" + (prefix + "/" if prefix else "") + "namespaces"
    r2 = requests.get(nxt, headers=dict(base, **carry), timeout=30)
    replay["GET /v1/{prefix}/namespaces (same headers)"] = r2.status_code
    try:
        replay["second response message"] = r2.json().get("message")
    except ValueError:
        pass
    rows.append({"probe": "_replay", "replay": replay})
    # The signature and the key id it names are identifiers too.
    extra = []
    creds = provider._credentials()
    for v in (creds.access_key, creds.token, carry.get("Authorization")):
        if v:
            extra.append((v, "<aws-credential>"))
    return rows, proc.returncode, proc.stderr.strip(), extra


def merge(rows, pairs):
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
                row["error"] = redact.scrub(r.get("error"), pairs)
            else:
                row["note"] = r.get("note")
        elif status not in ("reachable", "implicit"):
            # Not a failure. There is no request to send.
            row["verdict"] = "NOT-EXPRESSIBLE"
            row["why"] = note or "no method issues this request"
        else:
            # Expressible, and deliberately not sent: the binary is read-only
            # by construction. Scoring these as NOT-EXPRESSIBLE counted every
            # write the crate can do as a write the crate cannot do.
            row["verdict"] = "NOT-ISSUED"
            row["why"] = "read-only binary; this client can express it"
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[],
                    help="catalog name; repeatable. Default: apache-polaris only.")
    ap.add_argument("--storage", default="local-fs",
                    choices=["local-fs", "memory", "opendal", "none"],
                    help="StorageFactory to give the client. Recorded with the run. "
                         "Cloud-backed catalogs need `opendal`; the two factories "
                         "in the core crate only reach local paths and memory.")
    ap.add_argument("--access-delegation", metavar="MODE",
                    help="send X-Iceberg-Access-Delegation: MODE as a static "
                         "header, e.g. vended-credentials. Written to "
                         "rust-run-<catalog>-delegation.json, never over the "
                         "plain run.")
    ap.add_argument("--tag", help="suffix for the evidence file, e.g. no-tls; "
                                  "a tagged run never overwrites an untagged one")
    ap.add_argument("--sigv4-demo", action="store_true",
                    help="for a SigV4 catalog: pass one precomputed signature as "
                         "a static header and record what each request gets. "
                         "Writes rust-sigv4-demo-<catalog>.json.")
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

    if args.sigv4_demo:
        for cat in catalogs:
            if (cat.get("auth") or {}).get("type") != "sigv4":
                sys.exit("%s is not a SigV4 catalog" % cat["name"])
            rows, rc, stderr, extra = sigv4_demo(cat, args.storage)
            pairs = sorted(redact.values_for(cat) + extra, key=lambda kv: -len(kv[0]))
            out_rows, replay = [], None
            for r in rows:
                if r.get("probe") == "_meta":
                    continue
                if r.get("probe") == "_replay":
                    replay = {k: redact.scrub(v, pairs) if isinstance(v, str) else v
                              for k, v in r["replay"].items()}
                    continue
                r = dict(r)
                if r.get("error"):
                    r["error"] = redact.scrub(r["error"], pairs)
                out_rows.append(r)
            document = {
                "meta": {
                    "catalog": cat["name"],
                    "crate": "iceberg-catalog-rest 0.10.1",
                    "what": "one SigV4 signature for GET /v1/config, passed as "
                            "static header.Authorization / header.X-Amz-Date / "
                            "header.X-Amz-Security-Token",
                    "upstream": "apache/iceberg-rust#1236 (open)",
                    "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "exit_code": rc,
                    "stderr": redact.scrub(stderr, pairs) if stderr else None,
                    "replay_outside_crate": replay,
                },
                "rows": out_rows,
            }
            redact.verify(document, pairs)
            out = os.path.join(HERE, "evidence", "rust-sigv4-demo-%s.json" % cat["name"])
            with open(out, "w") as fh:
                json.dump(document, fh, indent=2)
                fh.write("\n")
            for r in out_rows:
                print("%-24s %s %s" % (r["probe"], {True: "ok", False: "FAILED", None: "implicit"}[r.get("ok")],
                                       (r.get("error") or "")[:160]))
            print("replay: %s" % json.dumps(replay))
            print("wrote %s" % os.path.relpath(out, HERE))
        return

    for cat in catalogs:
        mode, detail = auth_plan(cat.get("auth"))
        pairs = redact.values_for(cat, redact.secret_env_names(cat))
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
            rows, rc, stderr, _ = run_binary(cat, mode, args.storage,
                                             args.access_delegation)
            if args.access_delegation:
                meta["access_delegation_header"] = args.access_delegation
            meta["exit_code"] = rc
            if stderr:
                meta["stderr"] = redact.scrub(stderr, pairs)
            for r in rows:
                if r.get("probe") == "storage_read_metadata":
                    # Outside paper 1's probe list, so it lives in meta rather
                    # than as a row that would change the probe counts.
                    if r.get("error"):
                        r["error"] = redact.scrub(r["error"], pairs)
                    meta["storage_touch"] = {k: v for k, v in r.items()
                                             if k != "probe"}
                if r.get("probe") == "storage_fileio_config":
                    meta["storage_fileio_config_keys"] = r.get("keys")
                if r.get("probe") == "_meta":
                    meta["binary_reported"] = {k: v for k, v in r.items()
                                               if k not in ("probe", "catalog")}

        merged = merge(rows, pairs)
        counts = {}
        for r in merged:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        meta["counts"] = counts

        out = os.path.join(HERE, "evidence", "rust-run-%s%s%s.json" % (
            cat["name"], "-delegation" if args.access_delegation else "",
            "-" + args.tag if args.tag else ""))
        if args.tag:
            meta["tag"] = args.tag
            meta["binary"] = os.path.relpath(BINARY, HERE)
        # Never overwrite good evidence with a failed run.
        if not args.tag and mode != "absent" and rc not in (0, None) and not any(
                r["verdict"] == "OK" for r in merged):
            out = out.replace(".json", ".failed.json")
        document = {"meta": meta, "rows": merged}
        redact.verify(document, pairs)
        with open(out, "w") as fh:
            json.dump(document, fh, indent=2)
            fh.write("\n")

        print("%-18s %s" % (cat["name"], ", ".join(
            "%d %s" % (v, k.lower()) for k, v in sorted(counts.items()))))
        print("wrote %s" % os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
