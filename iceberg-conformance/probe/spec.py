import json
import re
# -*- coding: utf-8 -*-
"""The probe suite: one identical set of requests aimed at every catalog.

Two tiers of evidence come out of a run:

  endpoint tier  does the endpoint exist at all, and what status does it return
  field tier     for a successful loadTable, which spec fields are actually present

The field tier is the interesting one. Every vendor returns 200 for loadTable;
they disagree about what is *in* it, and that disagreement is invisible unless
you enumerate the spec's fields and check them one at a time.

Path templates use {prefix}, {ns} and {tbl}. {prefix} is the vendor's routing
prefix from GET /v1/config (often empty, `bq://...` on Google, a catalog name
elsewhere), which is itself one of the things worth recording.
"""

READ = "read"
WRITE = "write"


class Probe(object):
    def __init__(self, id, method, path, category, why,
                 params=None, body=None, tier=READ, spec_ref="", variant_of=None,
                 depends_on=None, surface=None):
        self.id = id
        self.method = method
        self.path = path
        self.category = category
        self.why = why
        self.params = params or {}
        self.body = body
        self.tier = tier
        self.spec_ref = spec_ref
        # Set when this probe differs from another only by query parameters.
        # Such probes share a signature, so they are excluded from the
        # declared-vs-observed tier: a 400 on ?parent= says nothing about
        # whether GET /v1/{prefix}/namespaces is implemented.
        self.variant_of = variant_of
        # Probe that must have succeeded for this one's result to mean anything.
        # If create_table never ran, a later "table does not exist" says nothing
        # about whether the endpoint is implemented.
        self.depends_on = depends_on
        # `tier` says WHEN a probe runs; `surface` says what it IS. loadView and
        # viewExists are GET and HEAD -- reads -- but they can only run after a
        # view has been created, so they sit in the write phase. Scoring them as
        # writes inflates every catalog's write denominator and understates its
        # read surface, which is exactly the number a read-only catalog is
        # judged on.
        self.surface = surface or tier

    def __repr__(self):
        return "<Probe %s %s %s>" % (self.id, self.method, self.path)

    def signature(self):
        """The probe as an IRC spec endpoint string, e.g.

            GET /v1/{prefix}/namespaces/{namespace}/tables/{table}

        This is the exact form a catalog uses in the `endpoints` array of its
        /v1/config response, so a probe can be matched against what the catalog
        claims to support. Scratch placeholders normalise to the spec's own
        names -- a probe against {scratch_ns} exercises the same endpoint as one
        against {ns}.
        """
        path = self.path
        for placeholder, canonical in (("{scratch_ns}", "{namespace}"),
                                       ("{ns}", "{namespace}"),
                                       ("{scratch_tbl}", "{table}"),
                                       ("{tbl}", "{table}"),
                                       ("{scratch_view}", "{view}")):
            path = path.replace(placeholder, canonical)
        return "%s %s" % (self.method, path)


# ---------------------------------------------------------------- read tier

PROBES = [
    Probe("config", "GET", "/v1/config", "config",
          "Advertises the routing prefix and vendor overrides. Everything else "
          "depends on what this returns.",
          params={"warehouse": "{warehouse}"}, spec_ref="GetConfig"),

    Probe("list_namespaces", "GET", "/v1/{prefix}/namespaces", "namespace",
          "The baseline read. If this 404s the prefix is wrong, not the catalog.",
          spec_ref="ListNamespaces"),

    Probe("list_namespaces_paged", "GET", "/v1/{prefix}/namespaces", "namespace",
          "Pagination is optional in the spec. Who honours pageSize, who ignores it?",
          params={"pageSize": "1"}, spec_ref="ListNamespaces", variant_of="list_namespaces"),

    Probe("list_namespaces_parent", "GET", "/v1/{prefix}/namespaces", "namespace",
          "Multi-level namespaces. OneLake documents that it does NOT support the "
          "parent param, so this cell is a known negative going in.",
          params={"parent": "{ns}"}, spec_ref="ListNamespaces", variant_of="list_namespaces"),

    Probe("load_namespace", "GET", "/v1/{prefix}/namespaces/{ns}", "namespace",
          "Namespace properties round-trip.", spec_ref="LoadNamespaceMetadata"),

    Probe("head_namespace", "HEAD", "/v1/{prefix}/namespaces/{ns}", "namespace",
          "Existence check without a body. Commonly unimplemented.",
          spec_ref="NamespaceExists"),

    Probe("list_tables", "GET", "/v1/{prefix}/namespaces/{ns}/tables", "table",
          "Table listing within a namespace.", spec_ref="ListTables"),

    Probe("load_table", "GET", "/v1/{prefix}/namespaces/{ns}/tables/{tbl}", "table",
          "The load-bearing call. Feeds the entire field tier below.",
          spec_ref="LoadTable"),

    Probe("load_table_snapshots_all", "GET",
          "/v1/{prefix}/namespaces/{ns}/tables/{tbl}", "table",
          "Full snapshot history vs. the refs-only default. Time travel depends on it.",
          params={"snapshots": "all"}, spec_ref="LoadTable", variant_of="load_table"),

    Probe("head_table", "HEAD", "/v1/{prefix}/namespaces/{ns}/tables/{tbl}", "table",
          "Existence check without a body.", spec_ref="TableExists"),

    Probe("load_credentials", "GET",
          "/v1/{prefix}/namespaces/{ns}/tables/{tbl}/credentials", "credentials",
          "Vended storage credentials. The newest and least evenly adopted endpoint.",
          spec_ref="LoadCredentials"),

    Probe("list_views", "GET", "/v1/{prefix}/namespaces/{ns}/views", "view",
          "Iceberg views are a separate spec section and adoption is patchy.",
          spec_ref="ListViews"),

    Probe("plan_table_scan", "POST",
          "/v1/{prefix}/namespaces/{ns}/tables/{tbl}/plan", "planning",
          "Server-side scan planning. Recent addition; expect mostly 404/501.",
          body={"select": ["*"], "case-sensitive": False},
          spec_ref="PlanTableScan"),

    Probe("report_metrics", "POST",
          "/v1/{prefix}/namespaces/{ns}/tables/{tbl}/metrics", "telemetry",
          "Metrics reporting. Widely stubbed to 204 without storing anything. "
          "Body must be a complete ScanReport or a 400 tells you nothing.",
          body={"report-type": "scan-report",
                "table-name": "{tbl}",
                "snapshot-id": 1,
                "filter": {"type": "eq", "term": "id", "value": 1},
                "schema-id": 0,
                "projected-field-ids": [1],
                "projected-field-names": ["id"],
                "metrics": {
                    "total-planning-duration": {
                        "count": 1, "time-unit": "nanoseconds", "total-duration": 1},
                    "total-file-size-in-bytes": {"unit": "bytes", "value": 1},
                    "result-data-files": {"unit": "count", "value": 1}}},
          spec_ref="ReportMetrics"),
]

# --------------------------------------------------------------- write tier
# Mutating. Skipped unless --allow-writes is passed, and they run against a
# scratch namespace so a half-finished run cannot damage a real table.

WRITE_PROBES = [
    Probe("create_namespace", "POST", "/v1/{prefix}/namespaces", "namespace",
          "First real write. OneLake is documented read-only, so this is where "
          "that shows up as a status code.",
          body={"namespace": ["{scratch_ns}"], "properties": {}},
          tier=WRITE, spec_ref="CreateNamespace"),

    Probe("update_namespace_props", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/properties", "namespace",
          "Property updates are separately optional from namespace creation.",
          body={"removals": [], "updates": {"probe": "conformance"}},
          tier=WRITE, spec_ref="UpdateProperties", depends_on="create_namespace"),

    Probe("create_table", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables", "table",
          "Table creation with an explicit schema, partition spec and sort order — "
          "checks whether all three survive a round-trip.",
          body={
              "name": "{scratch_tbl}",
              "schema": {
                  "type": "struct",
                  "schema-id": 0,
                  "fields": [
                      {"id": 1, "name": "id", "required": True, "type": "long"},
                      {"id": 2, "name": "ts", "required": False, "type": "timestamptz"},
                      {"id": 3, "name": "payload", "required": False, "type": "string"},
                  ],
              },
              "partition-spec": {
                  "spec-id": 0,
                  "fields": [{"source-id": 2, "field-id": 1000,
                              "transform": "day", "name": "ts_day"}],
              },
              "write-order": {
                  "order-id": 1,
                  "fields": [{"source-id": 1, "transform": "identity",
                              "direction": "asc", "null-order": "nulls-first"}],
              },
              "properties": {"probe": "conformance"},
              "location": "{scratch_location}",
              "stage-create": False,
          },
          tier=WRITE, spec_ref="CreateTable", depends_on="create_namespace"),

    Probe("commit_table", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "commit",
          "A property-set commit — the cheapest possible exercise of the update path.",
          body={"requirements": [{"type": "assert-table-uuid", "uuid": "{table_uuid}"}],
                "updates": [{"action": "set-properties",
                             "updates": {"probe-commit": "1"}}]},
          tier=WRITE, spec_ref="UpdateTable", depends_on="create_table"),

    # --- updateTable actions -------------------------------------------------
    # All five share one endpoint signature, so they are marked variant_of
    # commit_table and excluded from the declaration tier: the question here is
    # not "is POST .../tables/{table} routed" but "which of the spec's 25 update
    # actions does it accept". Each carries the same assert-table-uuid
    # requirement that commit_table already proved works, so a failure isolates
    # the action rather than the requirement.
    Probe("commit_remove_properties", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "commit",
          "remove-properties: the inverse of the one action every catalog serves.",
          body={"requirements": [{"type": "assert-table-uuid", "uuid": "{table_uuid}"}],
                "updates": [{"action": "remove-properties", "removals": ["probe"]}]},
          tier=WRITE, spec_ref="UpdateTable",
          variant_of="commit_table", depends_on="create_table"),

    Probe("commit_add_schema", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "commit",
          "add-schema together with set-current-schema:-1 in a single commit. "
          "That pairing is the spec's idiom -- -1 means the schema added by this "
          "same request, so splitting them across two commits is meaningless.",
          body={"requirements": [{"type": "assert-table-uuid", "uuid": "{table_uuid}"}],
                "updates": [{"action": "add-schema",
                             "schema": {"type": "struct", "schema-id": 1,
                                        "fields": [
                                            {"id": 1, "name": "id", "required": True,
                                             "type": "long"},
                                            {"id": 2, "name": "ts", "required": False,
                                             "type": "timestamptz"},
                                            {"id": 3, "name": "payload", "required": False,
                                             "type": "string"},
                                            {"id": 4, "name": "added_col", "required": False,
                                             "type": "string"}]}},
                            {"action": "set-current-schema", "schema-id": -1}]},
          tier=WRITE, spec_ref="UpdateTable",
          variant_of="commit_table", depends_on="create_table"),

    Probe("commit_set_current_schema", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "commit",
          "set-current-schema naming an existing schema (0), exercising the action "
          "on its own rather than as part of an add-schema commit.",
          body={"requirements": [{"type": "assert-table-uuid", "uuid": "{table_uuid}"}],
                "updates": [{"action": "set-current-schema", "schema-id": 0}]},
          tier=WRITE, spec_ref="UpdateTable",
          variant_of="commit_table", depends_on="create_table"),

    Probe("commit_upgrade_format_version", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "commit",
          "upgrade-format-version to 2. The fixture is already v2, so this is a "
          "no-op for a conformant server -- rejecting it is the finding.",
          body={"requirements": [{"type": "assert-table-uuid", "uuid": "{table_uuid}"}],
                "updates": [{"action": "upgrade-format-version", "format-version": 2}]},
          tier=WRITE, spec_ref="UpdateTable",
          variant_of="commit_table", depends_on="create_table"),

    Probe("commit_transaction", "POST", "/v1/{prefix}/transactions/commit", "commit",
          "Multi-table atomic commit. Rarely implemented; a clean differentiator. "
          "Carries one real change: an empty transaction gets rejected as invalid, "
          "which would be indistinguishable from unimplemented.",
          body={"table-changes": [
              {"identifier": {"namespace": ["{scratch_ns}"], "name": "{scratch_tbl}"},
               "requirements": [],
               "updates": [{"action": "set-properties",
                            "updates": {"probe-txn": "1"}}]}]},
          tier=WRITE, spec_ref="CommitTransaction", depends_on="create_table"),

    Probe("rename_table", "POST", "/v1/{prefix}/tables/rename", "table",
          "Rename is one of the most commonly missing write endpoints.",
          body={"source": {"namespace": ["{scratch_ns}"], "name": "{scratch_tbl}"},
                "destination": {"namespace": ["{scratch_ns}"], "name": "{scratch_tbl}_r"}},
          tier=WRITE, spec_ref="RenameTable", depends_on="create_table"),


    Probe("drop_table_purge", "DELETE",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "table",
          "Whether purgeRequested is honoured. Purge semantics vary widely and "
          "several catalogs gate it behind a server flag.",
          params={"purgeRequested": "true"}, tier=WRITE, spec_ref="DropTable", depends_on="create_table", variant_of="drop_table"),

    Probe("drop_table", "DELETE",
          "/v1/{prefix}/namespaces/{scratch_ns}/tables/{scratch_tbl}", "cleanup",
          "Plain drop, and the cleanup that must succeed. A 404 here is the "
          "expected outcome when the purge drop above already removed the table.",
          tier=WRITE, spec_ref="DropTable", depends_on="create_table"),

    # --- views ---------------------------------------------------------------
    # Views are a separate section of the spec with six operations. Probing only
    # listViews, as this suite originally did, cannot distinguish "views are
    # unimplemented" from "list is unimplemented" -- which matters, because
    # Horizon declares seven view endpoints.
    Probe("create_view", "POST", "/v1/{prefix}/namespaces/{scratch_ns}/views", "view",
          "createView with a minimal SQL representation.",
          body={"name": "{scratch_view}",
                "schema": {"type": "struct", "schema-id": 0,
                           "fields": [{"id": 1, "name": "id", "required": False,
                                       "type": "long"}]},
                "view-version": {
                    "version-id": 1, "schema-id": 0, "timestamp-ms": "{now_ms}",
                    "summary": {"operation": "create"},
                    "default-namespace": ["{scratch_ns}"],
                    "representations": [{"type": "sql", "sql": "SELECT 1 AS id",
                                         "dialect": "spark"}]},
                "properties": {"probe": "conformance"}},
          tier=WRITE, spec_ref="CreateView", depends_on="create_namespace"),

    Probe("load_view", "GET",
          "/v1/{prefix}/namespaces/{scratch_ns}/views/{scratch_view}", "view",
          "loadView -- the read counterpart of loadTable for views.",
          tier=WRITE, spec_ref="LoadView", surface=READ, depends_on="create_view"),

    Probe("head_view", "HEAD",
          "/v1/{prefix}/namespaces/{scratch_ns}/views/{scratch_view}", "view",
          "viewExists.", tier=WRITE, spec_ref="ViewExists", surface=READ, depends_on="create_view"),

    Probe("replace_view", "POST",
          "/v1/{prefix}/namespaces/{scratch_ns}/views/{scratch_view}", "view",
          "replaceView: a property-set commit against the view.",
          body={"requirements": [],
                "updates": [{"action": "set-properties",
                             "updates": {"probe-commit": "1"}}]},
          tier=WRITE, spec_ref="ReplaceView", depends_on="create_view"),

    Probe("rename_view", "POST", "/v1/{prefix}/views/rename", "view",
          "renameView -- separate from renameTable in the spec.",
          body={"source": {"namespace": ["{scratch_ns}"], "name": "{scratch_view}"},
                "destination": {"namespace": ["{scratch_ns}"],
                                "name": "{scratch_view}_r"}},
          tier=WRITE, spec_ref="RenameView", depends_on="create_view"),

    Probe("drop_view", "DELETE",
          "/v1/{prefix}/namespaces/{scratch_ns}/views/{scratch_view}", "cleanup",
          "dropView, and the cleanup that must succeed before the namespace goes.",
          tier=WRITE, spec_ref="DropView", depends_on="create_view"),

    Probe("drop_namespace", "DELETE", "/v1/{prefix}/namespaces/{scratch_ns}", "cleanup",
          "Cleanup.", tier=WRITE, spec_ref="DropNamespace", depends_on="create_namespace"),
]

# ---------------------------------------------------------------- field tier
# Dotted paths checked against a successful loadTable body. `[]` means "walk
# into the first element of this list". Presence, absence and null are three
# distinct outcomes and the report keeps them apart.

LOAD_TABLE_FIELDS = [
    ("metadata-location",                  "Where the table metadata actually lives"),
    ("config",                             "Per-table client overrides"),
    ("storage-credentials",                "Vended credentials inline on load"),
    ("metadata.format-version",            "Iceberg v1 / v2 / v3"),
    ("metadata.table-uuid",                "Stable identity across renames"),
    ("metadata.location",                  "Table root"),
    ("metadata.last-updated-ms",           "Freshness"),
    ("metadata.last-column-id",            "Column-ID allocation state"),
    ("metadata.schemas",                   "Full schema history, not just current"),
    ("metadata.current-schema-id",         "Which schema is live"),
    ("metadata.schemas[].fields[].id",     "Column IDs — schema evolution depends on these"),
    ("metadata.schemas[].fields[].required", "Nullability"),
    ("metadata.partition-specs",           "Partition spec history"),
    ("metadata.default-spec-id",           "Which spec is live"),
    ("metadata.partition-specs[].fields[].transform", "Partition transforms"),
    ("metadata.last-partition-id",         "Partition field-ID allocation state"),
    ("metadata.sort-orders",               "Sort order history"),
    ("metadata.default-sort-order-id",     "Which sort order is live"),
    ("metadata.properties",                "Table properties"),
    ("metadata.current-snapshot-id",       "Current snapshot pointer"),
    ("metadata.snapshots",                 "Snapshot list — time travel"),
    ("metadata.snapshots[].summary",       "Row/file counts per snapshot"),
    ("metadata.snapshots[].manifest-list", "Manifest list pointer"),
    ("metadata.snapshots[].schema-id",     "Per-snapshot schema binding"),
    ("metadata.snapshots[].sequence-number", "v2 sequence numbers — row-level deletes"),
    ("metadata.snapshot-log",              "Snapshot lineage over time"),
    ("metadata.metadata-log",              "Previous metadata files"),
    ("metadata.refs",                      "Branches and tags"),
    ("metadata.statistics",                "Table-level statistics files"),
    ("metadata.partition-statistics",      "Partition-level statistics files"),
]


# ------------------------------------------------------------- classification

OK = "OK"
FALSE_OK = "200_WITH_ERROR"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
NOT_FOUND = "NOT_FOUND"
BAD_REQUEST = "BAD_REQUEST"
UNAUTHORIZED = "UNAUTHORIZED"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
CONFLICT = "CONFLICT"
SERVER_ERROR = "SERVER_ERROR"
TRANSPORT_ERROR = "TRANSPORT_ERROR"
SKIPPED = "SKIPPED"

_BY_STATUS = {
    400: BAD_REQUEST,
    401: UNAUTHORIZED,
    403: UNAUTHORIZED,
    404: NOT_FOUND,
    405: METHOD_NOT_ALLOWED,
    409: CONFLICT,
    501: NOT_IMPLEMENTED,
}


INDETERMINATE = "INDETERMINATE"

_ROUTE_MISSING = re.compile(
    r"(api is not found|no api found|unknown ?operation|not supported|"
    r"no route|matching target resource method|method not allowed)", re.I)


def route_is_missing(status, body):
    """Distinguish a missing route from a missing entity.

    Both answer 404, and the difference decides whether a result is evidence.
    "Requested Api is not found" means the endpoint is not served. "The given
    table does not exist" means the endpoint is served and looked -- so a probe
    whose fixture was never created has proved nothing about it.
    """
    if status is None:
        return False
    if status == 405:
        return True
    text = json.dumps(body) if body is not None else ""
    return bool(_ROUTE_MISSING.search(text))


HONEST = "declared, works"
OVERCLAIM = "DECLARED, FAILS"
UNDECLARED_OK = "undeclared, works"
HONEST_OMISSION = "undeclared, fails"


def reconcile(declared, verdict):
    """Cross-check what a catalog claims against what it does.

    The spec lets a catalog advertise its supported endpoints in /v1/config.
    That claim is checkable, and the interesting cell is OVERCLAIM: an endpoint
    the catalog lists and then does not serve. UNDECLARED_OK is the mirror --
    working functionality the catalog never advertises, which clients relying on
    the declaration will never use.
    """
    works = verdict == OK
    if declared and works:
        return HONEST
    if declared and not works:
        return OVERCLAIM
    if not declared and works:
        return UNDECLARED_OK
    return HONEST_OMISSION


_ERROR_IN_BODY = re.compile(
    r"(UnknownOperationException|__type|NotImplemented|NotSupported)", re.I)


def looks_like_error_body(body):
    """Detect an error payload smuggled inside a 2xx response.

    AWS Glue answers ReportMetrics with HTTP 200 and an
    `UnknownOperationException` in the body. Scoring that as a success would
    credit Glue with an endpoint it does not implement, so it gets its own
    verdict rather than being folded into either OK or a plain failure.
    """
    if not isinstance(body, dict):
        return False
    if "error" in body or "message" in body:
        return False          # a normal, honestly-shaped error response
    return bool(_ERROR_IN_BODY.search(json.dumps(body)[:2000]))


def classify(status):
    """Map an HTTP status onto the verdict vocabulary used in the matrix.

    404 vs 501 is the distinction that matters most: 501 is an honest "not
    implemented", while 404 usually means the route was never registered. Both
    mean unsupported, and telling them apart is half the point of the exercise.
    """
    if status is None:
        return TRANSPORT_ERROR
    if 200 <= status < 300:
        return OK
    if status in _BY_STATUS:
        return _BY_STATUS[status]
    if status >= 500:
        return SERVER_ERROR
    return "HTTP_%d" % status
