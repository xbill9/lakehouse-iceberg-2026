# -*- coding: utf-8 -*-
"""Executes the probe suite against one or more catalogs and records evidence.

Design rule: record raw, judge later. Every request and response is written to
disk as JSON, and the conformance matrix is derived from those files. Re-deriving
a verdict must never require re-running against four cloud vendors.

Safety rules, in order of importance:

  1. Read-only by default. The write tier runs only under --allow-writes.
  2. Writes go to a scratch namespace, never a real one.
  3. Credentials are redacted before anything touches the disk. loadTable can
     vend live storage credentials, and this evidence is meant to be published.
"""
import copy
import json
import os
import re
import time
import urllib.parse

import requests

from . import auth as auth_mod
from . import spec as spec_mod

USER_AGENT = "iceberg-conformance-probe/0.1 (+sprint-2026)"
TIMEOUT = 60

# Header names and JSON keys whose values never reach the evidence files.
_SECRET_HEADERS = {"authorization", "x-amz-security-token", "cookie", "set-cookie"}
_SECRET_KEY_RE = re.compile(
    r"(token|secret|credential|password|session|signature|access-key|private)",
    re.I)


def _redact(obj, _depth=0):
    """Recursively blank anything that looks like a credential.

    Keeps the key and records the length, so the field tier can still answer
    "was storage-credentials present?" without the value ever being written.
    """
    if _depth > 30:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SECRET_KEY_RE.search(str(k)) and isinstance(v, (str, bytes)):
                out[k] = "<redacted:%d chars>" % len(v)
            else:
                out[k] = _redact(v, _depth + 1)
        return out
    if isinstance(obj, list):
        return [_redact(v, _depth + 1) for v in obj]
    return obj


def _redact_headers(h):
    return {k: ("<redacted>" if k.lower() in _SECRET_HEADERS else v)
            for k, v in dict(h or {}).items()}


def _fill(value, ctx):
    """Substitute {placeholders} through strings, dicts and lists alike.

    A string that is exactly one placeholder resolves to the context value with
    its type intact. JSON is typed, and a spec field declared as an integer --
    createView's `timestamp-ms` -- is rejected when it arrives quoted.
    """
    if isinstance(value, str):
        m = re.fullmatch(r"\{(\w+)\}", value)
        if m and m.group(1) in ctx and not isinstance(ctx[m.group(1)], str):
            return ctx[m.group(1)]
        def sub(m):
            key = m.group(1)
            return str(ctx.get(key, m.group(0)))
        return re.sub(r"\{(\w+)\}", sub, value)
    if isinstance(value, dict):
        return {k: _fill(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, ctx) for v in value]
    return value


def _fill_path(template, ctx):
    """Substitute into a URL path.

    Two different rules apply, and conflating them breaks real catalogs:

    `prefix` is a *path prefix* and goes in raw. Its slashes are structure, not
    data -- Google returns `projects/<number>/catalogs/<catalog>`, which has to
    stay three path segments. The reference Iceberg client inserts it verbatim,
    so this does too. An empty prefix drops the segment entirely rather than
    leaving `/v1//namespaces` behind.

    Namespace and table names are *data* and get percent-encoded. The IRC spec
    joins multi-level namespaces with the unit-separator character, so a dotted
    namespace is translated before encoding.
    """
    prefix = str(ctx.get("prefix", "")).strip("/")
    template = template.replace("{prefix}/", prefix + "/" if prefix else "")

    def sub(m):
        key = m.group(1)
        if key not in ctx:
            return m.group(0)
        val = str(ctx[key])
        if key in ("ns", "scratch_ns") and "." in val:
            val = val.replace(".", "\x1f")
        return urllib.parse.quote(val, safe="")

    return re.sub(r"\{(\w+)\}", sub, template)


def _dig(obj, path):
    """Resolve a dotted field path. `[]` descends into a list.

    Returns (present, value). Present-but-null is distinct from absent, which is
    why this returns a pair rather than just the value.

    List descent searches every element rather than taking index 0. Catalogs
    legitimately carry empty leading entries -- OneLake's `schemas` starts with
    an empty schema-0 and puts the real columns in schema-1 -- so indexing
    blindly reports column IDs as missing when they are plainly there. The
    question this tier asks is whether a field appears at all, so any element
    satisfying the rest of the path counts.
    """
    def walk(cur, parts):
        if not parts:
            return True, cur
        part, rest = parts[0], parts[1:]
        descend = part.endswith("[]")
        if descend:
            part = part[:-2]
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
        if not descend:
            return walk(cur, rest)
        if not isinstance(cur, list):
            return False, None
        best = (False, None)
        for item in cur:
            ok, val = walk(item, rest)
            if ok and val is not None:
                return True, val
            if ok and not best[0]:
                best = (True, val)      # present but null; keep looking
        return best

    return walk(obj, path.split("."))


class CatalogRun(object):
    """One catalog, one pass of the suite."""

    def __init__(self, cfg, evidence_dir, allow_writes=False, verbose=True):
        self.name = cfg["name"]
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        self.auth = auth_mod.build(cfg.get("auth"))
        self.session = requests.Session()
        self.allow_writes = allow_writes
        self.verbose = verbose
        self.dir = os.path.join(evidence_dir, self.name)
        os.makedirs(self.dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d%H%M%S")   # no 'T': S3 Tables rejects uppercase
        self.ctx = {
            "prefix": cfg.get("prefix", ""),
            "warehouse": cfg.get("warehouse", ""),
            "ns": cfg.get("namespace", ""),
            "tbl": cfg.get("table", ""),
            "scratch_ns": cfg.get("scratch_namespace", "irc_probe_%s" % stamp),
            # Catalogs that do not manage their own storage (Glue) reject
            # create_table without one; the rest ignore it.
            "scratch_location": ("%s/irc_probe_%s" % (cfg["location_base"].rstrip("/"), stamp)
                                 if cfg.get("location_base") else ""),
            "scratch_tbl": "probe_tbl",
            "scratch_view": "probe_view",
            "now_ms": int(time.time() * 1000),
            "table_uuid": "00000000-0000-0000-0000-000000000000",
        }
        self.results = []

    # ------------------------------------------------------------------ http

    def _url(self, path):
        return self.base + _fill_path(path, self.ctx)

    def _send(self, probe):
        url = self._url(probe.path)
        params = _fill(probe.params, self.ctx)
        params = {k: v for k, v in params.items() if v not in ("", None)}
        body = _fill(probe.body, self.ctx) if probe.body is not None else None
        if isinstance(body, dict):
            body = {k: v for k, v in body.items() if v != ""}
        payload = json.dumps(body).encode() if body is not None else None

        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        headers.update(self.cfg.get("headers") or {})
        if payload is not None:
            headers["Content-Type"] = "application/json"

        # SigV4 signs the exact query string, so it must be built once here and
        # sent verbatim. Letting requests re-encode `params` separately produces
        # a different canonical string and the signature fails. urlencode's
        # default quote_plus is also wrong for SigV4, which requires %20.
        qs = urllib.parse.urlencode(
            params, quote_via=urllib.parse.quote, safe="") if params else ""
        full = url + ("?" + qs if qs else "")
        rec = {
            "probe": probe.id,
            "category": probe.category,
            "tier": probe.tier,
            "surface": probe.surface,
            "spec_ref": probe.spec_ref,
            "why": probe.why,
            "request": {"method": probe.method, "url": full,
                        "body": _redact(body) if body is not None else None},
            "catalog": self.name,
            "signature": probe.signature(),
            "variant_of": probe.variant_of,
            "depends_on": probe.depends_on,
            "ts": time.time(),
        }

        try:
            signed = self.auth.apply(probe.method, full, headers, payload)
            t0 = time.time()
            r = self.session.request(probe.method, full, data=payload,
                                     headers=signed, timeout=TIMEOUT)
            rec["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
            rec["request"]["headers"] = _redact_headers(signed)
            rec["response"] = {
                "status": r.status_code,
                "headers": _redact_headers(r.headers),
                "body": self._decode(r),
            }
            rec["verdict"] = spec_mod.classify(r.status_code)
            if rec["verdict"] == spec_mod.OK and \
                    spec_mod.looks_like_error_body(rec["response"]["body"]):
                rec["verdict"] = spec_mod.FALSE_OK
        except Exception as e:                      # transport, auth, DNS, TLS
            rec["error"] = "%s: %s" % (type(e).__name__, str(e)[:400])
            rec["verdict"] = spec_mod.TRANSPORT_ERROR
            rec["response"] = None
        return rec

    @staticmethod
    def _decode(r):
        if not r.content:
            return None
        try:
            return _redact(r.json())
        except ValueError:
            return {"_raw": r.text[:4000]}

    # ------------------------------------------------------------------ flow

    def _log(self, rec):
        if self.verbose:
            status = rec.get("response", {}).get("status") if rec.get("response") else "---"
            print("  %-26s %-4s %-18s %sms" % (
                rec["probe"], status, rec["verdict"], rec.get("elapsed_ms", "-")))

    def resolve_prefix(self):
        """GET /v1/config first — the prefix it returns steers every later path."""
        rec = self._send(spec_mod.PROBES[0])
        self.results.append(rec)
        self._log(rec)
        body = (rec.get("response") or {}).get("body") or {}
        if isinstance(body, dict):
            self.declared = list(body.get("endpoints") or [])
            if self.verbose and self.declared:
                print("  -> /v1/config declares %d endpoints" % len(self.declared))
            overrides = body.get("overrides") or {}
            found = overrides.get("prefix") or (body.get("defaults") or {}).get("prefix")
            if found and not self.cfg.get("prefix"):
                self.ctx["prefix"] = found
                if self.verbose:
                    print("  -> prefix from /v1/config: %r" % found)
        return rec

    def run(self):
        print("\n=== %s (%s) ===" % (self.name, self.base))
        self.resolve_prefix()

        for probe in spec_mod.PROBES[1:]:
            rec = self._send(probe)
            self.results.append(rec)
            self._log(rec)
            if probe.id == "load_table":
                self._field_tier(rec)
                self.seed_profile = self._seed_profile(rec)
                if self.verbose and self.seed_profile:
                    p = self.seed_profile
                    print("  -> fixture: %d schema(s), %d partition field(s), %d sort field(s), "
                          "%d snapshot(s), refs=%s, delete-snapshot=%s"
                          % (p["schemas"], p["partition_fields"], p["sort_fields"],
                             p["snapshots"], ",".join(p["refs"]) or "-",
                             p["has_delete_snapshot"]))

        if self.allow_writes:
            print("  -- write tier (mutating, scratch namespace %r) --"
                  % self.ctx["scratch_ns"])
            for probe in spec_mod.WRITE_PROBES:
                rec = self._send(probe)
                self.results.append(rec)
                self._log(rec)
                if probe.id == "create_table":
                    body = (rec.get("response") or {}).get("body") or {}
                    uuid = _dig(body, "metadata.table-uuid")[1]
                    if uuid:
                        self.ctx["table_uuid"] = uuid
                elif probe.id == "rename_view" and rec.get("verdict") == spec_mod.OK:
                    self.ctx["scratch_view"] = self.ctx["scratch_view"] + "_r"
                elif probe.id == "rename_table" and rec.get("verdict") == spec_mod.OK:
                    # The table now answers to a different name. Without this the
                    # cleanup probes chase the old one and report a false 404/409.
                    self.ctx["scratch_tbl"] = self.ctx["scratch_tbl"] + "_r"
        else:
            for probe in spec_mod.WRITE_PROBES:
                self.results.append({
                    "probe": probe.id, "category": probe.category, "tier": probe.tier,
                    "surface": probe.surface,
                    "spec_ref": probe.spec_ref, "why": probe.why, "catalog": self.name,
                    "verdict": spec_mod.SKIPPED,
                    "note": "write tier skipped; pass --allow-writes to run it",
                })

        self._write_evidence()
        return self.results

    def _field_tier(self, load_rec):
        """Enumerate spec fields against the loadTable body."""
        body = (load_rec.get("response") or {}).get("body")
        fields = {}
        if isinstance(body, dict) and load_rec.get("verdict") == spec_mod.OK:
            for path, why in spec_mod.LOAD_TABLE_FIELDS:
                present, val = _dig(body, path)
                if not present:
                    state = "ABSENT"
                elif val is None:
                    state = "NULL"
                elif isinstance(val, (list, dict)) and len(val) == 0:
                    state = "EMPTY"
                else:
                    state = "PRESENT"
                fields[path] = {"state": state, "why": why}
        else:
            for path, why in spec_mod.LOAD_TABLE_FIELDS:
                fields[path] = {"state": "NO_DATA", "why": why}
        self.fields = fields
        present = sum(1 for f in fields.values() if f["state"] == "PRESENT")
        if self.verbose:
            print("  -> field tier: %d/%d present" % (present, len(fields)))

    def _seed_profile(self, load_rec):
        """Measure the fixture's actual shape from the loadTable response.

        Several field-tier rows only mean something if the underlying tables are
        alike. Not every catalog accepts the same seed -- Unity refuses external
        data writes to managed storage, OneLake is read-only, Snowflake rejects
        tags -- so the shapes genuinely differ. Recording the shape measured from
        the wire, rather than asserting the seed script's intent, is what makes
        the field tier interpretable instead of merely comparable-looking.
        """
        body = (load_rec.get("response") or {}).get("body")
        if not isinstance(body, dict):
            return {}
        md = body.get("metadata") or {}
        specs = md.get("partition-specs") or []
        sorts = md.get("sort-orders") or []
        snaps = md.get("snapshots") or []
        ops = [(sn.get("summary") or {}).get("operation") for sn in snaps]
        return {
            "schemas": len(md.get("schemas") or []),
            "partition_fields": sum(len(x.get("fields") or []) for x in specs),
            "sort_fields": sum(len(x.get("fields") or []) for x in sorts),
            "snapshots": len(snaps),
            "refs": sorted((md.get("refs") or {}).keys()),
            "has_delete_snapshot": any(o in ("overwrite", "delete") for o in ops if o),
            "delete_files": sum(int((sn.get("summary") or {}).get("total-delete-files", 0) or 0)
                                for sn in snaps),
        }

    def _mark_indeterminate(self):
        """Neutralise results whose fixture never existed.

        If create_namespace was refused, every later write probe fails for a
        reason that has nothing to do with whether its endpoint is implemented.
        Scoring those as failures invents overclaims out of this suite's own
        ordering. The exception is a response that independently proves the
        route is absent -- "Requested Api is not found" is evidence regardless
        of what the fixture looked like, while "the given table does not exist"
        is not.
        """
        ok = {r["probe"]: r.get("verdict") == spec_mod.OK for r in self.results}
        for rec in self.results:
            dep = rec.get("depends_on")
            if not dep or rec.get("verdict") in (spec_mod.OK, spec_mod.SKIPPED):
                continue
            if ok.get(dep):
                continue
            resp = rec.get("response") or {}
            if spec_mod.route_is_missing(resp.get("status"), resp.get("body")):
                continue
            rec["verdict"] = spec_mod.INDETERMINATE
            rec["indeterminate_reason"] = "prerequisite %r did not succeed" % dep

    def _reconcile(self):
        """Attach the declared-vs-observed verdict to every probe record.

        Aggregated by endpoint signature rather than per probe. Several probes
        can target one endpoint -- drop_table and drop_table_purge both hit
        DELETE .../tables/{table}, and whichever runs second necessarily 404s
        because the first removed the table. Judging those individually invents
        an overclaim out of the suite's own ordering, so an endpoint counts as
        working if any probe against it succeeded.
        """
        declared = set(getattr(self, "declared", []))
        works = {}
        for rec in self.results:
            sig = rec.get("signature")
            if not sig or rec.get("verdict") in (spec_mod.SKIPPED, spec_mod.INDETERMINATE):
                continue
            works[sig] = works.get(sig, False) or rec.get("verdict") == spec_mod.OK
        for rec in self.results:
            sig = rec.get("signature")
            if not sig or rec.get("verdict") in (spec_mod.SKIPPED, spec_mod.INDETERMINATE):
                continue
            if rec.get("variant_of"):
                continue          # shares a signature with its base probe
            rec["declared"] = sig in declared
            rec["reconciled"] = spec_mod.reconcile(sig in declared, 
                                                   spec_mod.OK if works.get(sig) else "FAILED")

    @staticmethod
    def _harness_fingerprint():
        """Hash of the probe suite, so evidence records which harness produced it.

        Columns gathered under different versions of the suite are not
        comparable; this makes that checkable instead of assumed.
        """
        import hashlib
        h = hashlib.sha256()
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("spec.py", "runner.py", "auth.py"):
            with open(os.path.join(here, name), "rb") as f:
                h.update(f.read())
        return h.hexdigest()[:12]

    def _write_evidence(self):
        self._mark_indeterminate()
        self._reconcile()
        out = {
            "catalog": self.name,
            "base_url": self.base,
            "resolved_prefix": self.ctx["prefix"],
            "auth_kind": getattr(self.auth, "kind", "?"),
            "harness_fingerprint": self._harness_fingerprint(),
            "declared_endpoints": getattr(self, "declared", []),
            "namespace": self.ctx["ns"],
            "table": self.ctx["tbl"],
            "allow_writes": self.allow_writes,
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "probes": self.results,
            "load_table_fields": getattr(self, "fields", {}),
            "seed_profile": getattr(self, "seed_profile", {}),
        }
        attempted = [r for r in self.results if r.get("verdict") != spec_mod.SKIPPED]
        all_dead = attempted and all(
            r.get("verdict") == spec_mod.TRANSPORT_ERROR for r in attempted)
        name = "evidence.failed.json" if all_dead else "evidence.json"
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            json.dump(out, f, indent=2, sort_keys=False)
        if all_dead:
            # Every probe died at the transport layer, which means a broken
            # endpoint, expired credentials or no network -- not a conformance
            # result. Overwriting good evidence with it would silently destroy
            # a real run, so it is parked under a different name.
            print("  !! every probe failed at transport; last good evidence kept")
            print("  failed run -> %s" % path)
        else:
            print("  evidence -> %s" % path)
