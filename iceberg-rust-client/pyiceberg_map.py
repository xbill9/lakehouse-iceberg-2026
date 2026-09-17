"""How each of paper 1's probes maps onto pyiceberg 0.12.0's RestCatalog.

The other client's counterpart to `operation_map.py`. Same shape, same
statuses, hand-read from the installed package on 2026-09-17, one entry per
probe, each carrying the file and line it was read from. Nothing here is
inferred from documentation, and nothing here is a measurement.

Line references are into
`pyiceberg/catalog/rest/__init__.py` unless another file is named.

Statuses are `operation_map.py`'s, unchanged, so the two clients can be put in
one table:

  reachable    a public method issues the probe's request
  implicit     the request is issued, but by the client itself rather than on
               behalf of a caller
  degraded     a public method issues the request, but cannot send the query
               parameter this probe is about
  unsupported  the method exists and returns an error instead of a request
  absent       no method, and no endpoint template that could construct the URL

A fifth field per entry carries something the Rust crate has no equivalent of.
`_check_endpoint` (:649) compares the endpoint against the set parsed from the
`endpoints` array of GET /v1/config (:731), so most calls are gated on what the
catalog *declared*, which is the axis paper 1 measured. The gate is not a
status -- a gated call is still reachable -- so it is recorded separately:

  refuses       raises NotImplementedError before sending anything
  substitutes   silently sends a different request that answers the same
                question
  silent-empty  returns an empty result without sending anything
  None          no gate; the request is sent whatever /v1/config declared

Where a catalog returns no `endpoints` array at all, the client falls back to
DEFAULT_ENDPOINTS (:198), twelve namespace and table endpoints; the HEAD
endpoints, credentials, scan planning and views are not among them.
"""

CLIENT = "pyiceberg 0.12.0"
READ_ON = "2026-09-17"

# probe id -> (status, symbol, source ref, note, gate)
MAP = {
    # ---------------------------------------------------------------- read
    "config": (
        "implicit", "RestCatalog._fetch_config", "rest:707",
        "Called from __init__ (:422) before the session exists, and "
        "`warehouse` is sent when the builder was given one (:710). Not "
        "callable on its own. On this client the response does more than "
        "route: its `endpoints` array becomes `_supported_endpoints` (:731), "
        "which decides which of the rows below are attempted at all.", None),
    "list_namespaces": (
        "reachable", "RestCatalog.list_namespaces", "rest:1311", "", "refuses"),
    "list_namespaces_paged": (
        "reachable", "RestCatalog.list_namespaces", "rest:1316",
        "`pageSize` is sent, which the Rust crate cannot do -- but from the "
        "catalog property `rest-page-size` fixed at construction (:272, "
        ":1316-1320), not from a call argument. The method then follows "
        "`pageToken` to exhaustion (:1341-1344) and returns the whole list, so "
        "a caller can send the parameter and cannot see the page boundary it "
        "asked for.", "refuses"),
    "list_namespaces_parent": (
        "reachable", "RestCatalog.list_namespaces", "rest:1325",
        "`parent` is sent when the caller passes a namespace, encoded by "
        "_encode_namespace_path (:697): each part percent-encoded with "
        "safe=\"\", joined by the namespace separator, which defaults to the "
        "unit separator U+001F (:275) and is itself a catalog property.",
        "refuses"),
    "load_namespace": (
        "reachable", "RestCatalog.load_namespace_properties", "rest:1348", "",
        "refuses"),
    "head_namespace": (
        "reachable", "RestCatalog.namespace_exists", "rest:1383",
        "HEAD is sent only when the catalog declared it. Otherwise no HEAD "
        "request is made at all: the method calls load_namespace_properties "
        "and reads NoSuchNamespaceError as False (:1387-1392). The caller gets "
        "the right answer from a different endpoint, which is why a run has to "
        "record whether the gate was open before scoring this row.",
        "substitutes"),
    "list_tables": (
        "reachable", "RestCatalog.list_tables", "rest:1047", "", "refuses"),
    "load_table": (
        "reachable", "RestCatalog.load_table", "rest:1083",
        "Returns a Table, and a Table carries a FileIO -- the same coupling "
        "that made the first Rust run fail without a storage factory. This "
        "client resolves one per call from the table's location and the "
        "catalog properties (_load_file_io, :489), so there is nothing to "
        "register in advance and no equivalent of IRC_STORAGE.", "refuses"),
    "load_table_snapshots_all": (
        "reachable", "RestCatalog.load_table", "rest:1086",
        "`snapshots=all` is sendable, again as a construction-time property "
        "(`snapshot-loading-mode`, :262) rather than a call argument, and a "
        "value outside {all, refs} raises before any request. Two catalog "
        "objects are therefore needed to measure both this probe and "
        "load_table, which the runner builds.", "refuses"),
    "head_table": (
        "reachable", "RestCatalog.table_exists", "rest:1411",
        "Gated like head_namespace, and the substitute is more expensive: an "
        "undeclared HEAD becomes a full load_table (:1419-1425).",
        "substitutes"),
    "load_credentials": (
        "reachable", "RestCatalog.load_credentials", "rest:1120",
        "The public method takes a location and returns only the best-matching "
        "credential properties (_resolve_storage_credentials, :470); the raw "
        "response is private (_load_credentials, :1104).", "refuses"),
    "list_views": (
        "reachable", "RestCatalog.list_views", "rest:1186",
        "The gate here neither refuses nor substitutes. An undeclared "
        "GET .../views returns [] with no request sent (:1187-1188), so a "
        "catalog that serves views without declaring them is indistinguishable "
        "from a catalog with no views.", "silent-empty"),
    "plan_table_scan": (
        "reachable", "RestCatalog.plan_scan", "rest:554",
        "Public, and handles the whole lifecycle including the follow-up "
        "fetch-scan-tasks pagination. _plan_table_scan (:502) sends the probe's "
        "request. Server-side planning is additionally governed by the "
        "`scan-planning-mode` property, which defaults to client (:266), so "
        "supports_server_side_planning (:496) can be False on a catalog that "
        "declares the endpoint.", "refuses"),
    "report_metrics": (
        "absent", None, "grep, no match",
        "No `/metrics` endpoint template and no ScanReport type anywhere in "
        "the package. Metrics reporting is not modelled at all.", None),

    # --------------------------------------------------------------- write
    "create_namespace": (
        "reachable", "RestCatalog.create_namespace", "rest:1287", "", "refuses"),
    "update_namespace_props": (
        "reachable", "RestCatalog.update_namespace_properties", "rest:1362",
        "Served by the client, which is the one place the two clients differ "
        "in kind rather than in degree: the Rust method compiles and returns "
        "FeatureUnsupported.", "refuses"),
    "create_table": (
        "reachable", "RestCatalog.create_table", "rest:927",
        "The probe's body is expressible, including partition spec and sort "
        "order. `stage-create` is not: the public create_table hardcodes "
        "stage_create=False (:943) and only create_table_transaction (:949) "
        "sets it True. Paper 1 records S3 Tables as requiring stage-create, so "
        "that is a distinction with somewhere to land.", "refuses"),
    "commit_table": (
        "reachable", "RestCatalog.commit_table", "rest:1239", "", "refuses"),
    "commit_remove_properties": (
        "reachable", "RestCatalog.commit_table", "rest:1239",
        "Same endpoint; expressed as a RemoveProperties update.", "refuses"),
    "commit_add_schema": (
        "reachable", "RestCatalog.commit_table", "rest:1239",
        "Same endpoint; expressed as an AddSchema update.", "refuses"),
    "commit_set_current_schema": (
        "reachable", "RestCatalog.commit_table", "rest:1239",
        "Same endpoint; expressed as a SetCurrentSchema update.", "refuses"),
    "commit_upgrade_format_version": (
        "reachable", "RestCatalog.commit_table", "rest:1239",
        "Same endpoint; expressed as an UpgradeFormatVersion update.",
        "refuses"),
    "commit_transaction": (
        "absent", None, "grep, no match",
        "No `/v1/{prefix}/transactions/commit` template. create_table_"
        "transaction (:949) is a client-side transaction that ends in a single "
        "commit_table, not the multi-table endpoint.", None),
    "rename_table": (
        "reachable", "RestCatalog.rename_table", "rest:1149",
        "The probe's one request, plus three the probe did not ask for: both "
        "namespaces are checked with namespace_exists first (:1158-1163) and "
        "the renamed table is loaded afterwards (:1171).", "refuses"),
    "drop_table_purge": (
        "reachable", "RestCatalog.purge_table", "rest:1144",
        "`purgeRequested=true` via drop_table(purge_requested=True), :1135.",
        "refuses"),
    "drop_table": (
        "reachable", "RestCatalog.drop_table", "rest:1131", "", "refuses"),
    "create_view": (
        "reachable", "RestCatalog.create_view", "rest:972",
        "Ungated, and alone in that: there is no V1_CREATE_VIEW capability at "
        "all, so this request is sent whatever /v1/config declared, while "
        "load_view and drop_view beside it are refused unless declared.",
        None),
    "load_view": (
        "reachable", "RestCatalog.load_view", "rest:1224", "", "refuses"),
    "head_view": (
        "reachable", "RestCatalog.view_exists", "rest:1446",
        "Ungated: the HEAD is sent whatever was declared, unlike the table and "
        "namespace HEADs, which substitute.", None),
    "replace_view": (
        "absent", None, "grep, no match",
        "No replace_view and no view commit path. A view's version cannot be "
        "updated through this client, only created and dropped.", None),
    "rename_view": (
        "absent", None, "grep, no match",
        "No rename_view, and no entry in Endpoints (:138) that could build the "
        "URL.", None),
    "drop_view": (
        "reachable", "RestCatalog.drop_view", "rest:1496", "", "refuses"),
    "drop_namespace": (
        "reachable", "RestCatalog.drop_namespace", "rest:1299", "", "refuses"),
}

# Operations this client reaches that paper 1 never probed. Recorded for the
# same reason operation_map.py records them: the comparison must not be
# one-directional.
BEYOND_THE_SWEEP = [
    ("register_table", "RestCatalog.register_table", "rest:1011",
     "POST /v1/{prefix}/namespaces/{namespace}/register. One of the 10 spec "
     "operations paper 1 did not cover; the Rust crate reaches it too."),
    ("register_view", "RestCatalog.register_view", "rest:1472",
     "POST /v1/{prefix}/namespaces/{namespace}/register-view, which the Rust "
     "crate has no view support to reach."),
    ("fetch_scan_tasks", "RestCatalog._fetch_scan_tasks", "rest:528",
     "POST /v1/{prefix}/namespaces/{namespace}/tables/{table}/tasks, the "
     "second half of server-side planning."),
    ("SigV4", "RestCatalog._init_sigv4", "rest:770",
     "Not an operation, and the reason this client has a column for all seven "
     "catalogs: `rest.sigv4-enabled` mounts a requests adapter that signs each "
     "request with botocore's SigV4Auth (:813). This is the capability the "
     "Rust crate does not ship."),
]

UNVERIFIED = [
    "Whether a catalog's own /v1/config `endpoints` array is complete is a "
    "property of the catalog, not of this client, and paper 1 measured it. "
    "What is claimed here is only that this client gates on it.",
]
