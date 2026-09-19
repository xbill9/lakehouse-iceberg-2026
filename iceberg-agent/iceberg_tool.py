# -*- coding: utf-8 -*-
"""One Iceberg REST catalog tool, shared by every cloud's native agent.

This is the data-side counterpart of the shared `web_search` in
`multicloud-a2a-subagent/protocol/search.py`, and it is deliberately built to
the same shape: three async callables, one budget, failures returned to the
model as text rather than raised, and an identifier carried into the model's
context on every result.

**Why one shared tool rather than each cloud's own.** The same argument as the
search tool. Google ships BigQuery client libraries, AWS ships Glue ones and
Azure ships Fabric ones; handing each agent its vendor's SDK would mean the
comparison reports the gap between three SDKs as a gap between three agents.
The Iceberg REST catalog is the one interface all three clouds actually share,
so the tool speaks it directly and the only thing that varies is the agent
framework driving it.

**Why the metadata location is on every result.** The search tool puts the URL
on every entry because a researcher told to cite its sources, handed snippets
without them, invents citations that look real. The same failure has a data
shape: an agent asked where a figure came from will happily name a table it
never opened. An Iceberg table's `metadata-location` and `snapshot-id` name an
exact immutable version of the data, so carrying them into context makes a real
citation cheaper to produce than an invented one, and makes a claim checkable
after the fact.

Reads only. Nothing here creates, commits or drops anything -- an agent loop
that can write to a catalog is a different piece of work with a different risk
profile, and the conformance results say the read surface is the only one all
seven catalogs agree on anyway.
"""
import contextvars
import os
import time

# The harness already knows how to authenticate to all seven catalogs; this
# imports that rather than reimplementing six credential flows.
from probe import auth as auth_mod

DEFAULT_ROW_LIMIT = 20
MAX_ROW_LIMIT = 100

#: Catalog calls allowed per answer. The search tool learned this the hard way:
#: an unbounded budget had one model spend 24 searches on a 300-word brief. A
#: data agent has the same failure mode with a cheaper-looking call.
CATALOG_BUDGET = int(os.getenv("ICEBERG_CATALOG_BUDGET", "8"))


class _Budget:
    """Mutable, and that is the whole trick.

    A context variable copies into a child task, so *rebinding* it inside a tool
    call -- which every agent framework here runs in its own task -- is invisible
    to the responder that reads the total afterwards. The search tool measured
    this: switching to a plain int made every deployed draft report zero calls
    while the agents were demonstrably calling. Mutating one shared object is
    seen from both sides.
    """

    __slots__ = ("used", "seconds")

    def __init__(self) -> None:
        self.used = 0
        #: Wall-clock spent inside the tools, catalog HTTP and pyiceberg
        #: included. Subtracted from an answer's total it leaves the model and
        #: the framework, which is how a slow run is attributed rather than
        #: guessed at.
        self.seconds = 0.0


_used: contextvars.ContextVar[_Budget] = contextvars.ContextVar("iceberg_budget")


def _budget() -> _Budget:
    try:
        return _used.get()
    except LookupError:
        fresh = _Budget()
        _used.set(fresh)
        return fresh


def catalog_count() -> int:
    """Catalog calls made for the answer currently being written."""
    return _budget().used


def catalog_seconds() -> float:
    """Seconds spent inside the tools for the answer currently being written."""
    return _budget().seconds


def reset_budget() -> None:
    """Start a fresh budget for one answer. Called by the serving wrappers."""
    _used.set(_Budget())


def _spend() -> str | None:
    """Take one unit of budget, or return the message the model should read."""
    budget = _budget()
    if budget.used >= CATALOG_BUDGET:
        # Phrased as an instruction, not an error. An agent told only "no" keeps
        # trying; one told to answer with what it has stops.
        return (
            f"CATALOG BUDGET SPENT. You have made {budget.used} catalog calls, "
            f"which is this agent's limit for one answer. Answer now from what "
            f"you have already read, and say plainly which parts you could not "
            f"check. Do not invent tables, columns or figures."
        )
    budget.used += 1
    return None


# --------------------------------------------------------------------------
# catalog wiring


_catalog = None


def catalog_name() -> str:
    """Read at call time, never at import.

    Bound at import this was wrong in a way that read as a credential failure:
    each leg's ``build()`` sets ICEBERG_CATALOG, but the tool module is imported
    before ``build()`` runs, so the name was already fixed to the default. The
    Azure leg then read the local Polaris catalog and failed with
    ``KeyError: 'POLARIS_CLIENT_ID'`` -- an error naming a catalog nobody had
    asked for, on a leg pointed at OneLake.
    """
    return os.getenv("ICEBERG_CATALOG", "apache-polaris")


def _config() -> dict:
    import yaml

    path = os.getenv("ICEBERG_CATALOGS_FILE", "catalogs.yaml")
    name = catalog_name()
    with open(path) as handle:
        entries = yaml.safe_load(handle)["catalogs"]
    for entry in entries:
        if entry["name"] == name:
            return entry
    raise KeyError(
        "no catalog %r in %s; set ICEBERG_CATALOG to one of: %s"
        % (name, path, ", ".join(e["name"] for e in entries))
    )


def catalog():
    """The configured catalog, built once per process.

    Each agent points at its own cloud's catalog through `ICEBERG_CATALOG`, so
    the GCP leg reads BigLake, the AWS leg reads Glue or S3 Tables and the Azure
    leg reads OneLake -- the same tool, the same protocol, three services.
    """
    global _catalog
    if _catalog is not None:
        return _catalog

    from pyiceberg.catalog.rest import RestCatalog

    cfg = _config()
    props = {
        "uri": cfg["base_url"],
        "warehouse": cfg.get("warehouse", ""),
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    for key, value in (cfg.get("headers") or {}).items():
        props["header.%s" % key] = value
    props.update(cfg.get("io_properties") or {})

    spec = cfg.get("auth") or {}
    kind = spec.get("type")
    if kind == "gcloud":
        props["token"] = auth_mod.GcloudADC().token()
    elif kind == "azure_cli":
        props["token"] = auth_mod.AzureCLI(
            resource=spec.get("resource", "https://storage.azure.com")).token()
        # The catalog token gets you the metadata; reading the DATA needs an
        # ADLS credential as well, because OneLake stores it behind
        # abfss://...onelake.dfs.fabric.microsoft.com. Without these the
        # metadata calls all succeed and only the scan fails, with a TypeError
        # from deep inside the filesystem layer that names nothing useful.
        # AzureCliCredential, not DefaultAzureCredential: the default chain tries
        # the Azure VM metadata service before the CLI, and off Azure that probe
        # waits out its retries. MEASURED 2026-09-18: 553.1s for the default
        # chain against 0.6s for AzureCliCredential, on the same login. It
        # surfaced as an 858.5s OneLake scan.
        from azure.identity import AzureCliCredential

        # PyArrow's Azure filesystem builds ...blob.core.windows.net URLs and
        # ignores adls.account-host, which for OneLake produces a hostname that
        # does not exist. Fsspec honours the host, and is what Microsoft's own
        # pyiceberg example uses.
        props["py-io-impl"] = "pyiceberg.io.fsspec.FsspecFileIO"
        props["adls.account-name"] = cfg.get("adls_account", "onelake")
        props["adls.account-host"] = cfg.get(
            "adls_host", "onelake.blob.fabric.microsoft.com")
        props["adls.credential"] = AzureCliCredential()
    elif kind == "bearer_env":
        props["token"] = os.environ[spec["env_var"]]
    elif kind == "oauth2":
        props["credential"] = "%s:%s" % (os.environ[spec["client_id_env"]],
                                         os.environ[spec["client_secret_env"]])
        props["scope"] = spec.get("scope", "PRINCIPAL_ROLE:ALL")
        props["oauth2-server-uri"] = spec["token_url"]
    elif kind == "snowflake_keypair":
        props["token"] = auth_mod.SnowflakeKeyPair(
            **{k: v for k, v in spec.items() if k != "type"}).token()
    elif kind == "sigv4":
        props["rest.sigv4-enabled"] = "true"
        props["rest.signing-name"] = spec["service"]
        props["rest.signing-region"] = spec["region"]
        # Signing the catalog calls is not the same as being able to read the
        # data. Without these, pyiceberg falls back to whatever the catalog
        # vends and HeadObject returns ACCESS_DENIED on a bucket the caller
        # owns outright -- an error that reads like a catalog permission
        # problem and is not one. Skipped where the catalog vends its own
        # scoped credentials, which S3 Tables' managed bucket requires.
        vending = "vended-credentials" in str(
            (cfg.get("headers") or {}).get("X-Iceberg-Access-Delegation", ""))
        if not vending:
            from botocore.session import Session as BotoSession

            frozen = BotoSession().get_credentials().get_frozen_credentials()
            props["s3.access-key-id"] = frozen.access_key
            props["s3.secret-access-key"] = frozen.secret_key
            if frozen.token:
                props["s3.session-token"] = frozen.token
            props.setdefault("s3.region", spec["region"])

    _catalog = RestCatalog(cfg["name"], **props)
    return _catalog


def _trace(name: str, args: dict, result: str) -> str:
    """Opt-in diagnostics: ICEBERG_TOOL_TRACE=1 prints each call's arguments and
    what the model was handed, so a capture shows what an agent actually saw on
    frameworks that do not log their tool calls. Off by default; the published
    matrix runs did not use it."""
    if os.getenv("ICEBERG_TOOL_TRACE"):
        import sys as _sys
        lines = result.splitlines()
        shown = lines if len(lines) <= 30 else lines[:30] + ["... (%d more lines)" % (len(lines) - 30)]
        print("[tool-trace] %s(%s)\n%s\n[/tool-trace]"
              % (name, ", ".join("%s=%r" % kv for kv in args.items()), "\n".join(shown)),
              file=_sys.stderr, flush=True)
    return result


def _fail(what: str, exc: Exception) -> str:
    """Report a failure to the model instead of raising it.

    An agent whose catalog call failed can still answer, and should say what it
    could not read. An agent whose loop crashed returns nothing at all, and the
    coordinator files that as a provider failure on a leg that was working.
    """
    # Traced too: a failed call is exactly the one a capture most needs to show.
    return _trace("failed", {"while": what}, (
        "CATALOG ERROR while %s: %s: %s. Do not guess the answer this call would "
        "have given. Say in your answer that this could not be read."
        % (what, type(exc).__name__, str(exc)[:300])
    ))


# --------------------------------------------------------------------------
# the tools


async def iceberg_list_tables(namespace: str = "") -> str:
    """List the Iceberg tables available in the catalog.

    Call this first, before assuming any table exists. Names returned here are
    the only ones the other tools accept.

    Args:
        namespace: Restrict to one namespace. Omit to list every namespace.

    Returns:
        One `namespace.table` per line, or a message saying none were found.
    """
    spent = _spend()
    if spent:
        return spent
    started = time.monotonic()
    try:
        cat = catalog()
        spaces = [tuple(namespace.split("."))] if namespace else cat.list_namespaces()
        lines = []
        for space in spaces:
            for ident in cat.list_tables(space):
                lines.append(".".join(ident))
        if not lines:
            return (
                "NO TABLES. The catalog returned no tables for that namespace. "
                "Do not invent a table name; say plainly that the data is not "
                "there."
            )
        return "\n".join(sorted(lines))
    except Exception as exc:  # noqa: BLE001 - a failed call must not fail the answer
        return _fail("listing tables", exc)
    finally:
        _budget().seconds += time.monotonic() - started


async def iceberg_describe_table(table: str) -> str:
    """Describe one Iceberg table: its columns, partitioning and current version.

    Read this before scanning, so you know which columns exist. The metadata
    location and snapshot id it returns identify the exact immutable version of
    the table you read, and you should quote them when citing a figure.

    Args:
        table: A `namespace.table` name, as returned by iceberg_list_tables.

    Returns:
        Column names and types, partitioning, row-level detail, and the
        metadata location and snapshot id that identify this version.
    """
    spent = _spend()
    if spent:
        return spent
    started = time.monotonic()
    try:
        tbl = catalog().load_table(table)
        meta = tbl.metadata
        cols = [
            "  %-16s %-14s %s" % (f.name, str(f.field_type),
                                  "required" if f.required else "optional")
            for f in tbl.schema().fields
        ]
        parts = [f.name for f in meta.partition_specs[meta.default_spec_id].fields] \
            if meta.partition_specs else []
        snap = tbl.current_snapshot()
        return "\n".join(
            ["table: %s" % table,
             "format-version: %s" % meta.format_version,
             "columns:", *cols,
             "partitioned by: %s" % (", ".join(parts) if parts else "(unpartitioned)"),
             "snapshots: %d" % len(meta.snapshots or []),
             "current-snapshot-id: %s" % (snap.snapshot_id if snap else "none"),
             # On the Table, not the metadata: TableMetadataV2 has no such
             # attribute, and reaching for it returns a CATALOG ERROR that
             # reads like the catalog refused the call.
             "metadata-location: %s" % (tbl.metadata_location or "unknown"),
             "",
             "Cite the metadata-location and current-snapshot-id above when you "
             "state a figure from this table."]
        )
    except Exception as exc:  # noqa: BLE001
        return _fail("describing %s" % table, exc)
    finally:
        _budget().seconds += time.monotonic() - started


async def iceberg_scan_table(table: str, columns: str = "",
                             limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Read rows from an Iceberg table.

    Use this to check a figure before stating it. Prefer naming the columns you
    need over reading all of them, and keep the limit small -- you are answering
    a question, not exporting the table.

    Args:
        table: A `namespace.table` name, as returned by iceberg_list_tables.
        columns: Comma-separated column names. Omit for all columns.
        limit: How many rows to return, at most.

    Returns:
        A header line, then one row per line, then the snapshot id the rows were
        read from.
    """
    spent = _spend()
    if spent:
        return spent
    started = time.monotonic()
    try:
        tbl = catalog().load_table(table)
        wanted = [c.strip() for c in columns.split(",") if c.strip()]
        asked = max(1, int(limit))
        capped = min(asked, MAX_ROW_LIMIT)
        scan = tbl.scan(limit=capped)
        if wanted:
            scan = scan.select(*wanted)
        rows = scan.to_arrow().to_pylist()
        if not rows:
            return (
                "NO ROWS. The table exists but the scan returned nothing. Do "
                "not invent values; say plainly that the table is empty."
            )
        names = list(rows[0])
        out = [" | ".join(names)]
        out += [" | ".join(str(r.get(n)) for n in names) for r in rows]
        snap = tbl.current_snapshot()
        out.append("")
        out.append("%d row(s), read from snapshot-id %s"
                   % (len(rows), snap.snapshot_id if snap else "unknown"))
        # Say when the view is COMPLETE, not only when it is partial: without this
        # a model told scans are samples will not count a whole table from one.
        total = (snap.summary or {}).get("total-records") if snap else None
        complete = total is not None and len(rows) == int(total)
        if complete:
            out.append(
                "COMPLETE: these are all %d rows in this snapshot (total-records %s), "
                "so values, maxima and counts read from them are exact for snapshot-id %s."
                % (len(rows), total, snap.snapshot_id))
        # A silent truncation is how a scan produces a confidently wrong total.
        # Measured: a model asked for a row count called this with limit=100000,
        # the tool clamped to MAX_ROW_LIMIT without saying so, and the answer
        # would have reported the cap as the table's size -- with a correct
        # metadata-location cited next to it. Say when the view is partial.
        # Only when it IS partial: both notes once fired beside COMPLETE, so an
        # 11-row table read with limit=10000 was called exact and a SAMPLE at once.
        elif asked > capped and len(rows) == capped:
            out.append(
                "NOTE: you asked for %d rows and this tool returns at most %d, "
                "so the rows above are a SAMPLE, not the whole table."
                % (asked, capped))
        elif len(rows) == capped:
            out.append(
                "NOTE: exactly %d row(s) came back, which is the limit, so there "
                "are probably more. Do NOT report this as the table's row count. "
                "If you were asked how many rows the table has, say you sampled "
                "%d and could not count the whole table."
                % (capped, capped))
        return _trace("iceberg_scan_table",
                      {"table": table, "columns": columns, "limit": limit}, "\n".join(out))
    except Exception as exc:  # noqa: BLE001
        return _fail("scanning %s" % table, exc)
    finally:
        _budget().seconds += time.monotonic() - started


async def iceberg_count_rows(table: str) -> str:
    """Count the rows in an Iceberg table exactly.

    Use this whenever you are asked how many rows a table has. Do not try to
    count by scanning: iceberg_scan_table returns a sample, and counting its
    rows gives you the sample size rather than the table's size.

    Args:
        table: A `namespace.table` name, as returned by iceberg_list_tables.

    Returns:
        The exact row count, how it was obtained, and the snapshot id it is
        true for.
    """
    spent = _spend()
    if spent:
        return spent
    started = time.monotonic()
    try:
        tbl = catalog().load_table(table)
        snap = tbl.current_snapshot()
        if snap is None:
            return ("0 rows: the table has no current snapshot, so no data has "
                    "been committed to it.")
        # Iceberg keeps a running total in the snapshot summary. Reading it is
        # one metadata call rather than a full scan, and it is exact for the
        # snapshot it belongs to.
        total = None
        try:
            total = (snap.summary or {}).get("total-records")
        except Exception:  # noqa: BLE001 - summary shapes vary between catalogs
            total = None
        if total is not None:
            return ("%s rows, from the snapshot summary (total-records) of "
                    "snapshot-id %s. This is exact for that snapshot."
                    % (total, snap.snapshot_id))
        # Not every catalog populates the summary -- a virtualised table may
        # not. Fall back to counting, reading one column so the whole table is
        # not materialised.
        first = tbl.schema().fields[0].name
        rows = tbl.scan(selected_fields=(first,)).to_arrow().num_rows
        return ("%d rows, counted by scanning the %s column because this "
                "catalog's snapshot summary carries no total-records. Exact "
                "for snapshot-id %s." % (rows, first, snap.snapshot_id))
    except Exception as exc:  # noqa: BLE001
        return _fail("counting %s" % table, exc)
    finally:
        _budget().seconds += time.monotonic() - started


# Diagnostic control, unset in every published run. The scan docstring tells the
# model to "keep the limit small"; ICEBERG_SCAN_DOC=read-all swaps that sentence for
# one that asks for every row needed, to measure how much that wording drives a
# model to under-read a table. Set before the frameworks read the docstring.
if os.getenv("ICEBERG_SCAN_DOC") == "read-all":
    import re as _re
    iceberg_scan_table.__doc__ = _re.sub(
        r"Prefer naming the columns you\s+need over reading all of them, and keep the limit small"
        r"\s+--\s+you are answering\s+a question, not exporting the table\.",
        "Set the limit high enough to read every row the question needs; the result says "
        "whether every row came back, and a count or maximum is only exact when it did.",
        iceberg_scan_table.__doc__)
    assert "keep the limit small" not in iceberg_scan_table.__doc__

# The published scan (v2). It filters in the engine and returns an exact COUNT, MIN
# and MAX, so no model does arithmetic over rows in its head. MEASURED 2026-09-15
# with the v1 scan above, which returned rows only: Nova Micro counted the ids >= 10
# correctly in 3 of 10 agent runs, and in 1 of 20 direct calls holding the agent's
# instruction and the 11 rows;
# with this scan, 8 of 10, and 10 of 10 with Amazon's documented Nova tool-use
# decoding (aws/agent.py). ICEBERG_SCAN_FILTER=0 restores v1, for diagnostics only.
if os.getenv("ICEBERG_SCAN_FILTER", "1") == "1":

    async def iceberg_scan_table(table: str, columns: str = "", where: str = "",
                                 limit: int = DEFAULT_ROW_LIMIT) -> str:
        """Read rows from an Iceberg table, with exact counts and ranges computed for you.

        Use this to check a figure before stating it. Every result ends with an
        exact COUNT of the matching rows and the MIN and MAX of each numeric
        column over all of them -- the whole table when `where` is omitted --
        however few rows are shown. Quote those; do not count or compare rows
        yourself.

        Args:
            table: A `namespace.table` name, as returned by iceberg_list_tables.
            columns: Comma-separated column names. Omit for all columns.
            where: A row filter only, such as "id >= 10" or "region == 'eu'". No
                ORDER BY, LIMIT or functions. Omit for all rows.
            limit: How many rows to show, at most. COUNT, MIN and MAX are exact regardless.

        Returns:
            A header line, one row per line, then the exact COUNT, MIN and MAX over
            every matching row and the snapshot id they were read from.
        """
        spent = _spend()
        if spent:
            return spent
        started = time.monotonic()
        condition = (where or "").strip()
        try:
            import pyarrow as pa
            import pyarrow.compute as pc

            tbl = catalog().load_table(table)
            wanted = tuple(c.strip() for c in (columns or "").split(",") if c.strip()) or ("*",)
            scan = tbl.scan(row_filter=condition, selected_fields=wanted) if condition \
                else tbl.scan(selected_fields=wanted)
            matched = scan.to_arrow()
            capped = min(max(1, int(limit or DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT)
            rows = matched.slice(0, capped).to_pylist()
            snap = tbl.current_snapshot()
            snap_id = snap.snapshot_id if snap else "unknown"
            scope = "match `%s`" % condition if condition else "are in the table"
            out = []
            if rows:
                names = list(rows[0])
                out = [" | ".join(names)]
                out += [" | ".join(str(r.get(n)) for n in names) for r in rows]
                out.append("")
            out.append("%d of %d row(s) shown, read from snapshot-id %s"
                       % (len(rows), matched.num_rows, snap_id))
            out.append("COUNT: exactly %d row(s) %s in snapshot-id %s. Exact, over the whole table."
                       % (matched.num_rows, scope, snap_id))
            for field in matched.schema:
                if matched.num_rows and (pa.types.is_integer(field.type) or pa.types.is_floating(field.type)):
                    span = pc.min_max(matched.column(field.name))
                    out.append("MIN and MAX of %s over those %d row(s): %s and %s. Exact."
                               % (field.name, matched.num_rows, span["min"].as_py(), span["max"].as_py()))
            return _trace("iceberg_scan_table",
                          {"table": table, "columns": columns, "where": where, "limit": limit},
                          "\n".join(out))
        except Exception as exc:  # noqa: BLE001
            if condition and type(exc).__name__ == "ParseException":
                # Measured: models wrote "true ORDER BY id DESC" to find a maximum,
                # read the bare parse error as "cannot be done", and declined.
                return _trace("failed", {"while": "where %r" % condition}, (
                    "FILTER NOT UNDERSTOOD: `where` takes a row filter only, such as "
                    "\"id >= 10\" -- no ORDER BY, LIMIT or functions (%s). For a largest "
                    "or smallest value, call this again without that clause and read the "
                    "MIN and MAX lines, which are exact over every matching row."
                    % str(exc)[:120]))
            return _fail("scanning %s where %s" % (table, condition) if condition
                         else "scanning %s" % table, exc)
        finally:
            _budget().seconds += time.monotonic() - started

TOOLS = [iceberg_list_tables, iceberg_describe_table,
         iceberg_count_rows, iceberg_scan_table]


#: Bumped whenever INSTRUCTION changes, and carried in the serving header so a
#: draft can be traced to the instruction that produced it. Same convention as
#: the research agent's INSTRUCTION_VERSION.
#: 1  first version: list, describe, scan.
#: 2  2026-09-04: adds iceberg_count_rows. Measured with v1: asked for a row
#:    count, one model called scan with limit=100000 and answered correctly
#:    while another called it with limit=1 and answered "at least 1, but likely
#:    more". Both used the tool as told; the question was answerable only by
#:    guessing a large enough limit, which measures the guess rather than the
#:    catalog. Counting is now its own tool and scanning says not to count with it.
#: v3, 2026-09-15. v2 told the model that iceberg_scan_table returns a sample and
#: must never be counted. That guard stopped a partial scan being reported as a
#: total, and it also stopped a whole table being read as one. MEASURED on Axis
#: D's first run: asked for the largest id and a filtered count, two of three ADK
#: runs declined without scanning ("the available tools do not support querying
#: for maximum values"), and every answer that did scan hedged "based on a
#: sample", although each scan had returned all 11 rows. v3 says when a scan may
#: be counted, and the scan tool now says when it returned every row.
INSTRUCTION_VERSION = 3

INSTRUCTION = (
    "You are a data analyst with four tools that read Apache Iceberg tables "
    "through a REST catalog: iceberg_list_tables, iceberg_describe_table, "
    "iceberg_count_rows and iceberg_scan_table. Given a question, you answer it "
    "from the data and nothing else. "
    "ALWAYS list the tables first, then describe the table you intend to use. "
    "To answer how many rows a table has, use iceberg_count_rows. To answer a "
    "question about the values in a table -- the largest value, or how many rows "
    "meet a condition -- read them with iceberg_scan_table. Its result says "
    "whether it returned every row of the snapshot or only some of them; count "
    "or compare rows from a scan only when it says it returned every row. "
    "Never name a table, a column or a figure you have not read. "
    "You have a budget of eight catalog calls for the whole answer, so read "
    "broadly rather than once per sentence; when the budget is spent you will "
    "be told, and you should answer from what you already have. "
    "Cite every figure by quoting the metadata-location and snapshot-id that "
    "iceberg_describe_table returned for the table it came from. Those name an "
    "exact immutable version of the data, so a reader can check you. "
    "If a call fails or returns nothing, say so plainly in the answer and do "
    "not fill the gap with a guess."
)
