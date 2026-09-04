"""How each of paper 1's probes maps onto iceberg-catalog-rest 0.10.1.

Hand-read from the published crate source on 2026-09-04, one entry per probe,
each carrying the file and line it was read from. Nothing here is inferred from
documentation, and nothing here is a measurement -- this is what the client can
*attempt*. What a catalog does with the attempt is the run's business.

Statuses:

  reachable    a public method issues the probe's request
  implicit     the request is issued, but by the client itself rather than on
               behalf of a caller -- there is no way to not make it, and no way
               to make it alone
  degraded     a public method issues the request, but cannot send the query
               parameter this probe is about, so the probe's question cannot be
               put through this client at all
  unsupported  the trait method exists and compiles, and returns an error
               instead of a request
  absent       no method, and no endpoint builder that could construct the URL

The distinction between `unsupported` and `absent` is the client-side echo of
paper 1's declared-vs-served split: `update_namespace` is named in the API a
caller compiles against, and is not served by the client itself.
"""

CRATE = "iceberg-catalog-rest 0.10.1"
READ_ON = "2026-09-04"

# probe id -> (status, rust symbol, source ref, note)
MAP = {
    # ---------------------------------------------------------------- read
    "config": (
        "implicit", "RestCatalog::load_config", "catalog.rs:426",
        "Issued once when the catalog is built, and `warehouse` is sent when "
        "the builder was given one (catalog.rs:432). Not callable on its own, "
        "so a client that cannot authenticate never reaches any other row."),
    "list_namespaces": (
        "reachable", "Catalog::list_namespaces", "catalog.rs:512", ""),
    "list_namespaces_paged": (
        "degraded", "Catalog::list_namespaces", "catalog.rs:512",
        "The probe asks who honours `pageSize`. The crate never sends it: it "
        "follows `next-page-token` in a loop and returns the whole list "
        "(catalog.rs:530, 545). Pagination is handled, but not steerable, so "
        "this probe has no Rust equivalent to run."),
    "list_namespaces_parent": (
        "reachable", "Catalog::list_namespaces", "catalog.rs:526",
        "`parent` is sent when the caller passes Some(ns)."),
    "load_namespace": (
        "reachable", "Catalog::get_namespace", "catalog.rs:603", ""),
    "head_namespace": (
        "reachable", "Catalog::namespace_exists", "catalog.rs:631", ""),
    "list_tables": (
        "reachable", "Catalog::list_tables", "catalog.rs:687", ""),
    "load_table": (
        "reachable", "Catalog::load_table", "catalog.rs:822", ""),
    "load_table_snapshots_all": (
        "degraded", "Catalog::load_table", "catalog.rs:822",
        "`load_table` builds its request with no query parameters at all "
        "(catalog.rs:825-828), so `?snapshots=all` cannot be sent. A caller "
        "gets the server's default -- refs-only, where the server honours the "
        "parameter -- and cannot ask for the full history."),
    "head_table": (
        "reachable", "Catalog::table_exists", "catalog.rs:886", ""),
    "load_credentials": (
        "absent", None, "grep, no match",
        "No `/credentials` endpoint builder. Vended credentials are modelled "
        "only where they arrive inside a loadTable response "
        "(StorageCredential, types.rs:235), not fetched separately."),
    "list_views": ("absent", None, "grep, no match", "No view support at all."),
    "plan_table_scan": (
        "absent", None, "grep, no match",
        "No `/plan` endpoint builder; scan planning is client-side."),
    "report_metrics": (
        "absent", None, "grep, no match",
        "No `/metrics` endpoint builder."),

    # --------------------------------------------------------------- write
    "create_namespace": (
        "reachable", "Catalog::create_namespace", "catalog.rs:567", ""),
    "update_namespace_props": (
        "unsupported", "Catalog::update_namespace", "catalog.rs:652",
        'Returns FeatureUnsupported, "Updating namespace not supported yet!". '
        "The method is in the trait a caller compiles against; there is no "
        "`/properties` endpoint builder behind it."),
    "create_table": (
        "reachable", "Catalog::create_table", "catalog.rs:739", ""),
    "commit_table": (
        "reachable", "Catalog::update_table", "catalog.rs:1005", ""),
    "commit_remove_properties": (
        "reachable", "Catalog::update_table", "catalog.rs:1005",
        "Same endpoint; the update is expressed as a TableCommit."),
    "commit_add_schema": (
        "reachable", "Catalog::update_table", "catalog.rs:1005", ""),
    "commit_set_current_schema": (
        "reachable", "Catalog::update_table", "catalog.rs:1005", ""),
    "commit_upgrade_format_version": (
        "reachable", "Catalog::update_table", "catalog.rs:1005", ""),
    "commit_transaction": (
        "absent", None, "grep, no match",
        "No `/v1/{prefix}/transactions/commit` endpoint builder. "
        "CommitTransactionRequest exists as a type (types.rs:279) with no "
        "method that sends it."),
    "rename_table": (
        "reachable", "Catalog::rename_table", "catalog.rs:908", ""),
    "drop_table_purge": (
        "reachable", "Catalog::purge_table", "catalog.rs:881",
        "`purgeRequested=true` via delete_table(purge=true), catalog.rs:388."),
    "drop_table": (
        "reachable", "Catalog::drop_table", "catalog.rs:875", ""),
    "create_view": ("absent", None, "grep, no match", "No view support."),
    "load_view": ("absent", None, "grep, no match", "No view support."),
    "head_view": ("absent", None, "grep, no match", "No view support."),
    "replace_view": ("absent", None, "grep, no match", "No view support."),
    "rename_view": ("absent", None, "grep, no match", "No view support."),
    "drop_view": ("absent", None, "grep, no match", "No view support."),
    "drop_namespace": (
        "reachable", "Catalog::drop_namespace", "catalog.rs:663", ""),
}

# Operations the crate reaches that paper 1 never probed. Recorded so the
# comparison is not quietly one-directional: a client can be ahead of the
# sweep as well as behind it.
BEYOND_THE_SWEEP = [
    ("register_table", "Catalog::register_table", "catalog.rs:940",
     "POST /v1/{prefix}/namespaces/{namespace}/register, built at "
     "catalog.rs:205. RegisterTable is in the specification and is one of the "
     "10 operations paper 1 did not cover."),
    ("token refresh", "RestCatalog::regenerate_token / ::invalidate_token",
     "catalog.rs:493, 503",
     "OAuth2 refresh as a first-class public operation rather than a "
     "reconnect."),
]

# Read from the `iceberg` core crate, not this one, so it is not asserted here.
UNVERIFIED = [
    "NamespaceIdent::to_url_string() lives in the `iceberg` core crate. "
    "Whether a dotted namespace is joined with the unit separator the spec "
    "requires was NOT read, and must not be claimed until it is -- either "
    "from that crate's source or from the wire.",
]
