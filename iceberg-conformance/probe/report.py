# -*- coding: utf-8 -*-
"""Builds the conformance matrix from recorded evidence.

Reads only evidence.json files, never the network, so verdicts can be
re-derived without re-running against four vendors.
"""
import json
import os

from . import spec as spec_mod

# Compact glyphs keep a seven-column matrix readable at article width.
GLYPH = {
    "OK": "yes",
    "NOT_IMPLEMENTED": "501",
    "NOT_FOUND": "404",
    "BAD_REQUEST": "400",
    "UNAUTHORIZED": "auth",
    "METHOD_NOT_ALLOWED": "405",
    "CONFLICT": "409",
    "SERVER_ERROR": "5xx",
    "TRANSPORT_ERROR": "err",
    "200_WITH_ERROR": "200!",
    "INDETERMINATE": "n/t",
    "SKIPPED": "-",
}
FIELD_GLYPH = {"PRESENT": "yes", "ABSENT": "no", "NULL": "null",
               "EMPTY": "empty", "NO_DATA": "-"}


def load(evidence_dir):
    out = []
    for name in sorted(os.listdir(evidence_dir)):
        p = os.path.join(evidence_dir, name, "evidence.json")
        if os.path.exists(p):
            with open(p) as f:
                out.append(json.load(f))
    return out


def _table(headers, rows):
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    def line(cells):
        return "| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(headers), sep] + [line(r) for r in rows])


# Rows whose outcome is decided by the fixture, not the implementation. A
# catalog whose table is unpartitioned cannot report a partition transform, and
# saying so is not a finding about its REST surface.
SEED_SENSITIVE = {
    "metadata.partition-specs[].fields[].transform",
    "metadata.refs",
    "metadata.snapshots",
    "metadata.snapshots[].summary",
    "metadata.snapshots[].manifest-list",
    "metadata.snapshots[].schema-id",
    "metadata.snapshots[].sequence-number",
    "metadata.snapshot-log",
}


def build_markdown(runs):
    names = [r["catalog"] for r in runs]
    parts = ["# Iceberg REST Catalog conformance matrix", ""]

    parts.append("| Catalog | Endpoint | Auth | Prefix | Run at |")
    parts.append("|---|---|---|---|---|")
    for r in runs:
        parts.append("| %s | `%s` | %s | `%s` | %s |" % (
            r["catalog"], r["base_url"], r["auth_kind"],
            r.get("resolved_prefix") or "(none)", r["run_at"]))

    # ---- endpoint tier
    parts += ["", "## Endpoint tier", "",
              "What each catalog does with an identical request. "
              "`501` is an honest not-implemented; `404` usually means the route "
              "was never registered.", ""]
    by_probe = {}
    for r in runs:
        for rec in r["probes"]:
            by_probe.setdefault(rec["probe"], {})[r["catalog"]] = rec
    order = [p.id for p in spec_mod.PROBES] + [p.id for p in spec_mod.WRITE_PROBES]
    rows = []
    for pid in order:
        cells = by_probe.get(pid, {})
        if not cells:
            continue
        any_rec = next(iter(cells.values()))
        rows.append([pid, any_rec.get("category", "")] +
                    [GLYPH.get(cells.get(n, {}).get("verdict", "-"),
                               cells.get(n, {}).get("verdict", "-")) for n in names])
    parts += ["", _table(["Probe", "Category"] + names, rows)]

    # ---- field tier
    # ---- fixture shapes
    parts += ["", "## Fixture shapes (measured, not assumed)", "",
              "Not every catalog accepts the same seed, so the tables are not "
              "identical. Rows in the field tier marked † depend on the fixture "
              "rather than the implementation and must not be read as capability.", ""]
    rows = []
    for r in runs:
        p = r.get("seed_profile") or {}
        rows.append([r["catalog"], p.get("schemas", "?"), p.get("partition_fields", "?"),
                     p.get("sort_fields", "?"), p.get("snapshots", "?"),
                     ",".join(p.get("refs") or []) or "-",
                     "yes" if p.get("has_delete_snapshot") else "no",
                     p.get("delete_files", "?")])
    parts += [_table(["Catalog", "schemas", "part-fields", "sort-fields", "snapshots",
                      "refs", "delete-snap", "delete-files"], rows)]

    parts += ["", "## Field tier — what loadTable actually returns", "",
              "Every catalog returns 200 for loadTable. They disagree about what "
              "is inside it, and that is invisible without enumerating the spec "
              "field by field.", ""]
    rows = []
    for path, why in spec_mod.LOAD_TABLE_FIELDS:
        cells = []
        for r in runs:
            st = (r.get("load_table_fields") or {}).get(path, {}).get("state", "-")
            cells.append(FIELD_GLYPH.get(st, st))
        mark = " †" if path in SEED_SENSITIVE else ""
        rows.append(["`%s`%s" % (path, mark)] + cells)
    parts += ["", _table(["Field"] + names, rows)]

    # ---- declared vs observed
    parts += ["", "## Declared vs. observed", "",
              "The spec lets a catalog advertise its supported endpoints in "
              "`/v1/config`. That claim is checkable. **DECLARED, FAILS** is an "
              "overclaim; *undeclared, works* is functionality a client trusting "
              "the declaration would never reach.", ""]
    rows = [["_declared count_", ""] +
            [str(len(r.get("declared_endpoints") or [])) for r in runs]]
    for pid in order:
        cells = by_probe.get(pid, {})
        if not cells:
            continue
        vals = []
        for n in names:
            rec = cells.get(n, {})
            vals.append(rec.get("reconciled", "-") if rec.get("reconciled") else "-")
        if all(v in ("-", "declared, works") for v in vals):
            continue          # unremarkable: everyone declares it and it works
        any_rec = next(iter(cells.values()))
        rows.append([pid, any_rec.get("category", "")] + vals)
    if len(rows) > 1:
        parts += [_table(["Probe", "Category"] + names, rows)]
    else:
        parts += ["_Every probe reconciled cleanly against every declaration._"]

    # ---- summary
    nsig = len({p.signature() for p in spec_mod.PROBES + spec_mod.WRITE_PROBES})
    ntot = len(spec_mod.PROBES) + len(spec_mod.WRITE_PROBES)
    parts += ["", "## Coverage summary", "",
              "Read and write surfaces are scored separately and deliberately not summed: a catalog that is read-only by design scores zero on writes, and folding that into one number makes a deliberate design read as a broken implementation. Counts are of probes, not endpoints: %d probes cover %d distinct "
              "endpoint signatures, because several probes differ only by query "
              "parameter (`?parent=`, `?snapshots=all`, `?purgeRequested=`). "
              "Probes that could not be tested are excluded from the denominator."
              % (ntot, nsig), ""]
    rows = []
    for r in runs:
        # Indeterminate probes leave the denominator: an endpoint that could
        # not be tested is not an endpoint that failed.
        live = [x for x in r["probes"]
                if x.get("verdict") not in (spec_mod.SKIPPED, spec_mod.INDETERMINATE)]
        # Scored by surface (what the operation is), not tier (when it runs).
        rd = [x for x in live if (x.get("surface") or x.get("tier")) == spec_mod.READ]
        wr = [x for x in live if (x.get("surface") or x.get("tier")) == spec_mod.WRITE]
        nok = lambda xs: sum(1 for x in xs if x.get("verdict") == spec_mod.OK)
        flds = r.get("load_table_fields") or {}
        fok = sum(1 for v in flds.values() if v.get("state") == "PRESENT")
        nt = sum(1 for x in r["probes"]
                 if x.get("verdict") == spec_mod.INDETERMINATE)
        rows.append([r["catalog"], "%d/%d" % (nok(rd), len(rd)),
                     "%d/%d" % (nok(wr), len(wr)), nt,
                     "%d/%d" % (fok, len(flds) or len(spec_mod.LOAD_TABLE_FIELDS))])
    parts += [_table(["Catalog", "Read probes OK", "Write probes OK", "not tested",
                      "loadTable fields present"], rows), "",
              "Denominators differ by catalog because untestable probes are "
              "excluded rather than counted as failures: when a catalog refuses "
              "to create a namespace, the probes that needed one prove nothing "
              "about the endpoints they target. The `not tested` column is that "
              "count, so every denominator is reconstructable.", ""]
    return "\n".join(parts)


def build_csv(runs):
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    names = [r["catalog"] for r in runs]
    w.writerow(["tier", "key", "category"] + names)
    by_probe = {}
    for r in runs:
        for rec in r["probes"]:
            by_probe.setdefault(rec["probe"], {})[r["catalog"]] = rec
    for pid in [p.id for p in spec_mod.PROBES] + [p.id for p in spec_mod.WRITE_PROBES]:
        cells = by_probe.get(pid)
        if not cells:
            continue
        cat = next(iter(cells.values())).get("category", "")
        w.writerow(["endpoint", pid, cat] +
                   [cells.get(n, {}).get("verdict", "") for n in names])
    for path, _why in spec_mod.LOAD_TABLE_FIELDS:
        w.writerow(["field", path, "loadTable"] +
                   [(r.get("load_table_fields") or {}).get(path, {}).get("state", "")
                    for r in runs])
    return buf.getvalue()
