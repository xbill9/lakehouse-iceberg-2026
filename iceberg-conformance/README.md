# Iceberg REST Catalog conformance harness

One identical request suite, pointed at seven Iceberg REST Catalog
implementations, recording what each actually returns.

Supports **Project #1** of the Lakehouse/Iceberg Content Sprint 2026 (see
`../PROJECT-IDEAS.md`).

## Why

The IRC is a published spec and every vendor claims to implement it. Nobody has
published a conformance matrix. Two facts are visible before the first run:
Microsoft OneLake is documented read-only with single-level namespaces, and AWS
ships two independent implementations (Glue and S3 Tables) that may not agree
with each other. Both are findings, not obstacles.

## Design rules

1. **Record raw, judge later.** Every request and response lands in
   `evidence/<catalog>/evidence.json`. The matrix is derived from those files,
   so a verdict can be re-derived without re-running against four vendors.
   `--report-only` rebuilds the matrix with no network access at all.
2. **Read-only by default.** The mutating tier runs only under `--allow-writes`,
   against a timestamped scratch namespace.
3. **Redact before disk.** `loadTable` can vend live storage credentials, and
   this evidence is meant to be published. Authorization headers and anything
   matching token/secret/credential/password/session/signature/access-key are
   replaced with a length marker before being written.
4. **One vendor's failure is not the run's failure.** An unreachable catalog is
   recorded as `TRANSPORT_ERROR` and the run continues.

## Two tiers of evidence

**Endpoint tier** — does the endpoint exist, and what status comes back.
`501` (honest not-implemented) is kept distinct from `404` (route never
registered); both mean unsupported, and telling them apart is half the point.

**Field tier** — every catalog returns 200 for `loadTable`. They disagree about
what is *in* it. The harness walks 30 spec field paths and reports
`PRESENT` / `ABSENT` / `NULL` / `EMPTY` as four distinct states. This is where
column IDs, snapshot history, sort orders and v2 sequence numbers either show up
or quietly do not.

## Use

```bash
pip install -r requirements.txt
cp catalogs.example.yaml catalogs.yaml   # then fill it in
python3 run.py                           # read-only, all catalogs
python3 run.py --only google-lakehouse,apache-polaris
python3 run.py --allow-writes            # mutating tier, scratch namespace
python3 run.py --report-only             # rebuild matrix from evidence, no network
```

Output: `out/conformance-matrix.md` and `out/conformance-matrix.csv`.

## The control column (local Polaris)

```bash
./polaris-up.sh                     # starts Polaris, creates the catalog, seeds the table
export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
python3 run.py --only apache-polaris --allow-writes
```

`polaris-up.sh` documents four non-obvious requirements inline; the short version
is that FILE storage needs two feature flags plus a readiness opt-out, and that
running the container as your own uid needs `/etc/passwd` mounted or Hadoop's
`UserGroupInformation` login fails with a 503 that reads like a storage error.

`seed_polaris.py` deliberately builds a *rich* table: three appends, a schema
evolution and a tag, so the seeded metadata has 2 schemas, 3 snapshots, a
snapshot-log, a 5-entry metadata-log and 2 refs. An empty table would leave those
fields absent, and an absent field in the control column is indistinguishable
from a vendor omitting it.

### Baseline result (Polaris 1.7.0)

20/22 endpoints OK, 26/30 loadTable fields present. Two genuine gaps:

| Probe | Result | Reading |
|---|---|---|
| `plan_table_scan` | 404 | Server-side scan planning not implemented in 1.7.0 |
| `drop_table_purge` | 403 | Purge gated behind `DROP_WITH_PURGE_ENABLED` |

**Caveat on two field-tier cells.** The control catalog uses FILE storage, so
`config` and `storage-credentials` are absent from its loadTable response. That
is a storage-type artifact, not a catalog limitation — Polaris vends credentials
happily through the dedicated `load_credentials` endpoint, which returns 200.
Do not read those two cells as a Polaris gap when comparing against S3- or
GCS-backed vendors. `metadata.statistics` and `partition-statistics` are EMPTY
rather than absent because the seed writes no statistics files.

### First real comparison: BigLake vs the control (2026-09-03)

Both catalogs seeded with the identical table via `seed_table.py`.

| | Polaris 1.7.0 | BigLake |
|---|---|---|
| Endpoints OK | 21/23 | 17/23 |
| loadTable fields | 26/30 | 26/30 |

**The field tiers are identical.** Every one of the 30 spec fields that Polaris
returns, BigLake also returns -- schemas, column IDs, partition specs, sort
orders, full snapshot list with per-snapshot summaries and v2 sequence numbers,
snapshot-log, metadata-log and refs. The only divergence is `statistics` /
`partition-statistics`, EMPTY on Polaris and ABSENT on BigLake, which is a
difference in how each renders "no statistics files" rather than a capability.

All the differentiation is in the endpoint tier:

| Probe | Polaris | BigLake | Reading |
|---|---|---|---|
| `rename_table` | 204 | 404 | Not routed |
| `commit_transaction` | 204 | 404 | Multi-table commit not routed |
| `list_views` | 200 | 404 | "Method not found" |
| `drop_table_purge` | 403 | 200 | Inverted: Polaris gates purge, BigLake honours it |
| `plan_table_scan` | 404 | 404 | Neither implements scan planning |

So the headline is not that BigLake returns less metadata -- it returns exactly
what the spec asks for. It declines to route four endpoints.

**Caveat, not a finding.** BigLake's `load_credentials` returns 400 "Precondition
check failed" even with `X-Iceberg-Access-Delegation: vended-credentials`. Its
`/v1/config` reports `catalog_credential_mode: CREDENTIAL_MODE_END_USER`, so this
is a credential-mode configuration consequence, not proof the endpoint is
unimplemented. Same class as the FILE-storage caveat above: worth flagging in
prose, not scoring in the matrix.

### Four catalogs (2026-09-03)

| | Polaris | BigLake | Glue | S3 Tables |
|---|---|---|---|---|
| Endpoints OK | 21/23 | 17/23 | 15/23 | 15/23 |
| loadTable fields | 26/30 | 26/30 | 26/30 | 27/30 |
| Declares endpoints | 36 | 15 | no | no |

**The two AWS catalogs contradict each other on purge.** This was the open
question going in -- AWS ships two independent IRC implementations, do they
agree? They do not, and not by omission but by opposite requirement:

| Catalog | `DELETE .../tables/{table}?purgeRequested=true` |
|---|---|
| Polaris | 403 -- gated behind `DROP_WITH_PURGE_ENABLED` |
| BigLake | 200 -- honoured |
| Glue | 400 "PurgeRequested cannot be true for Glue iceberg tables" |
| S3 Tables | 200 -- and a *plain* drop is refused: "S3 Tables only supports dropping tables with purge enabled" |

Glue forbids purge. S3 Tables mandates it. A client that hardcodes either one
breaks on the other, inside the same cloud.

**Glue returns HTTP 200 with an error in the body.** `plan_table_scan`,
`report_metrics` and `commit_transaction` all answer `200 OK` carrying
`{"Output": {"__type": "com.amazon.coral.service#UnknownOperationException"}}`.
Scored naively that is three working endpoints. The harness gives them their own
verdict (`200_WITH_ERROR`) for this reason. It compounds: Glue's `/v1/config`
advertises `rest-table-scan-enabled: true`, and scan planning is one of the three.

**Only two of four declare their endpoints.** Polaris lists 36 and BigLake 15 in
`/v1/config`; Glue and S3 Tables list none, so a client cannot discover their
capabilities without probing -- which is the argument for this harness existing.

**Multi-level namespaces split cleanly.** Polaris and BigLake support `?parent=`;
both AWS catalogs reject it outright ("Glue dataCatalog does not support
multipart namespace", "Multipart namespaces are not supported").

**Field tier is near-uniform.** All four return 26-30 of the 30 checked fields,
S3 Tables highest at 27. Whatever separates these catalogs, it is not the
fidelity of `loadTable`.

### Databricks Unity (2026-09-03)

18/23 endpoints, 26/30 fields, declares 18 endpoints. Three things are specific
to Unity and cost time to discover:

**The IRC endpoint demands the `all-apis` token scope.** A PAT scoped to
`unity-catalog` + `sql` -- which is what the token dialog steers you toward, and
which is sufficient for the Unity REST API and the SQL statement API -- is
rejected by the Iceberg endpoint with `403 "Provided access token does not have
required scopes: all-apis"`. So probing the open-standard surface requires the
broadest possible credential, while the vendor's own APIs accept a narrow one.

**Its prefix is two path segments** (`catalogs/workspace`), which is why prefixes
must be inserted raw. Google's is four.

**`update_namespace_props` requires a non-standard `etag`.** It returns
`400 "Etag token version is missing"`. The IRC spec's UpdateProperties request
has no etag field, so a spec-conformant client cannot call this endpoint at all.
That is the cleanest genuine overclaim in the matrix: declared, and unreachable
without a vendor extension.

`plan_table_scan` is declared and returns `400 "Table requested is not
scan-plan compatible"` -- the endpoint exists, the seeded table just is not
eligible, so this is scored as an overclaim only in the narrow sense that a
client cannot use it against an ordinary table.

Setup notes: `EXTERNAL USE SCHEMA` cannot be granted on a schema in the default
`workspace` catalog (`PRIVILEGE_NOT_APPLICABLE_TO_ENTITY` -- the schema is a
`SCHEMA_DB_STORAGE` entity); granting on the catalog works. External data access
is off by default and is flipped with
`PATCH /api/2.1/unity-catalog/metastores/{id} {"external_access_enabled": true}`.

### Snowflake Horizon: a reduced Polaris (2026-09-03)

Horizon **embeds Apache Polaris** ("Apache Polaris is integrated into Horizon
Catalog"), and serves it from the same `/polaris/api/catalog` path as Open
Catalog. That makes the upstream-vs-managed comparison possible after all, and
the two are not the same catalog:

| | upstream Polaris 1.7.0 | Snowflake Horizon |
|---|---|---|
| Endpoints declared | 36 | 23 |
| Endpoints OK | 21/23 | 18/23 |
| OAuth scope | `PRINCIPAL_ROLE:ALL` | `session:role:<role>` |
| Token grant | client_id + client_secret | signed JWT in `client_secret`, no client_id |

Snowflake ships a materially reduced Polaris surface and a different auth
handshake, which is why the harness needs a dedicated `snowflake_keypair`
provider rather than reusing the generic `oauth2` one.

**Four overclaims across the estate.** Endpoints a catalog lists in `/v1/config`
and then does not serve:

| Catalog | Endpoint | Observed |
|---|---|---|
| BigLake | `load_credentials` | 400 "Precondition check failed" |
| Horizon | `list_views` | 403 as ACCOUNTADMIN |
| Horizon | `update_namespace_props` | 403 as ACCOUNTADMIN |
| Horizon | `commit_transaction` | 403 as ACCOUNTADMIN |

Horizon's three are 403 rather than 404, so they may reflect a privilege model
rather than a missing implementation -- but they were probed with the highest
role in the account, and the endpoint is advertised without qualification.

**Setup lesson, recorded because it nearly became a finding.** Horizon first
returned 403 on `create_table`, `update_namespace_props`, `list_views` and
`commit_transaction`, and 404 on rename and commit. Setting a default external
volume on the database (`ALTER DATABASE ... SET EXTERNAL_VOLUME`) fixed four of
those six. Only the genuinely-403 three survived. Publishing before that step
would have produced four false overclaims. Also note Snowflake rejects
`TIMESTAMP_TZ(9)` for Iceberg tables; `TIMESTAMP_LTZ(6)` is required.

### Microsoft OneLake (2026-09-03) -- measured

11/23 endpoints, 25/30 fields, declares 13. Reads work; every write fails. That
matches Microsoft's documented read-only design -- but the catalog's own
`/v1/config` says otherwise.

**Four overclaims, the largest block in the matrix.** OneLake declares
`POST /namespaces`, `POST .../tables`, `POST .../tables/{table}` and
`POST /tables/rename`, and serves none of them -- each answering "Requested Api
is not found". Its documentation is correct about the behaviour; its
machine-readable declaration is not. A client that trusts `endpoints` over the
prose will try to write and fail.

Its two `DELETE` endpoints are declared and **not tested**: they answer "the
given table/namespace does not exist", which means the route is served and the
fixture was missing, because creating one was refused. See the verification pass
below -- they are marked INDETERMINATE rather than counted against OneLake.

**And the documented limitation is wrong in the other direction.** Microsoft
documents that the `parent` query parameter on listNamespaces is not supported.
Measured, it works: `?parent=dbo` returns `[]` (no children) and `?parent=zzz`
returns `NoSuchNamespaceException`. The docs understate it; the endpoint list
overstates it. Neither matches behaviour, which is the whole argument for
measuring rather than citing.

One caveat kept out of the scoring. OneLake surfaces **1 snapshot for 3 loads**:
the table is Delta virtualised to Iceberg (its properties carry
`XTABLE_METADATA` with `sourceTableFormat: DELTA`) and is unpartitioned, because
the Fabric load-table API takes no partition spec. Its snapshot and partition
rows are therefore not comparable with the other six, which were seeded
identically via pyiceberg.

An earlier draft of this section reported a 25.6-second `load_credentials` on
OneLake. That figure came from a sweep whose evidence was later overwritten, and
it is not supported by the evidence in this repository: OneLake's slowest probe
in the current run is `load_table` at 493 ms, and no probe exceeds one second.
The claim is withdrawn rather than restated, because no artifact backs it.

### What OneLake caught in the harness

Its first run reported `metadata.schemas[].fields[].id` and `.required` as
ABSENT -- "OneLake omits column IDs", which would have been a striking and
entirely false headline. OneLake returns them. The bug was mine: `_dig`
descended into `schemas[0]`, and OneLake's schema-0 is an empty placeholder with
the real columns in schema-1. List descent now searches every element for one
that satisfies the rest of the path.

### What the control column caught

Its first run found four bugs in *this harness*, not in Polaris: an incomplete
ScanReport body, a no-op empty transaction that got rejected as invalid, and a
rename that left the two cleanup probes chasing the old table name. A
spec-compliant implementation should be nearly all green — anything red is
either a real gap or your own bug, and on the first run it was mostly the latter.
That is the whole argument for having a control column before pointing this at
a vendor.

## Verification pass (2026-09-03)

The whole sweep was re-verified after the fact rather than trusted:

- **Provenance.** Evidence now records a `harness_fingerprint` (a hash of
  `spec.py` + `runner.py` + `auth.py`). All seven catalogs carry the same one,
  so no column was measured with a different probe suite than another.
- **Reproducibility.** The full sweep was run twice, back to back, and the
  verdicts, reconciliations and all 30 field states were diffed: **zero
  differences**. Then run twice again after the change below: zero differences.
- **Cell-by-cell audit.** All 46 non-OK cells were re-read with their raw
  response messages, looking for results that were artefacts rather than
  findings. One class was.
- **Residue.** Every catalog was checked for leftover `irc_probe_*` scratch
  namespaces. All clean; only the intended `probe_ns` / `dbo` remain.

### What the audit changed

OneLake's write probes all fail, but for two different reasons, and the wording
gives it away. `create_namespace`, `create_table`, `commit_table` and
`rename_table` return **"Requested Api is not found"** -- the route is not
served. `drop_table_purge`, `drop_table` and `drop_namespace` return **"The
given table/namespace does not exist"** -- the route *is* served, it looked, and
the fixture was absent because `create_namespace` had already been refused.

Scoring the second group as failures manufactured two overclaims out of this
suite's own ordering. Probes now declare a `depends_on`, and when a prerequisite
did not succeed the result is marked `INDETERMINATE` and excluded from both the
score and the reconciliation -- unless the response independently proves the
route is missing, which "Api is not found" does and "does not exist" does not.

Net effect: **OneLake 6 overclaims -> 4**, three probes marked not-tested, and
the estate total **12 -> 10**. An endpoint that could not be tested is not an
endpoint that failed.

## Second review, and what it changed

A later self-review attacked the project's own central claim -- that every
catalog was asked about the same table. It was not true, and two other things
were overstated.

### The field tier was partly measuring the seed

Three different seed paths were in use (pyiceberg, native SQL, the Fabric load
API), producing tables with different partition specs, sort orders, tags and
snapshot counts. Per-catalog field scores were therefore not comparable, and
OneLake's lower score was mostly an artefact of its fixture.

Fixed two ways. The seed is now unified wherever the catalog permits it --
Snowflake moved from native SQL onto the same pyiceberg path, giving five of
seven an identical fixture. And the harness now **measures each fixture's shape
from the wire** (schemas, partition fields, sort fields, snapshots, refs,
delete snapshot, delete files) and publishes it, with the field-tier rows that
depend on the fixture marked `†`. Where tables still differ, the reason is a
vendor limitation, recorded as such:

| Catalog | Why its fixture differs |
|---|---|
| Databricks Unity | Vended credentials **explicitly deny `s3:PutObject`** on managed storage, so an external engine can create a table through IRC but cannot write data files to it. Seeded natively instead; unpartitioned. |
| Snowflake Horizon | Rejects tags ("Creating or updating tag snapshot references is not allowed") and answers the delete commit with a 500 ("Indeterminate result during conflict resolution check"). |
| Microsoft OneLake | Read-only; its table is Delta virtualised to Iceberg, unpartitioned, single snapshot. |

### Deletes were claimed but never exercised

The submission text said the suite covered "row-level delete metadata" and that
fixtures contained "row-level deletes". Every table had `total-delete-files=0`.
The seed now performs a delete, so tables carry a delete snapshot with
`deleted-data-files` and `deleted-records` -- but pyiceberg performs
**copy-on-write**, so positional and equality delete files are still absent
(`delete_files: 0` in every fixture shape). Producing real merge-on-read delete
files needs Spark per catalog, which would re-break the uniformity that matters
more. The claim has been narrowed to "delete-snapshot metadata", which is what
is actually measured.

### "Endpoints OK" overstated the denominator

23 probes cover **19 distinct endpoint signatures** -- three signatures are
shared by probes differing only in query parameter. The column is now labelled
`Probes OK` and the report states both numbers.

### Self-inflicted problems found along the way

Two failures initially looked like vendor behaviour and were mine:

- The IAM policy written for Snowflake's external volume omitted
  `s3:DeleteObjectVersion` and over-constrained `ListBucket` with an
  `s3:prefix` condition. Loosened to the documented set.
- pyiceberg was writing through Snowflake's **vended** credentials, which are
  session-scoped without `s3:DeleteObject`, so it could not clean up its own
  uncommitted manifests and commits reported an indeterminate state. The bucket
  is ours; it now writes with local credentials. Appends went from failing on
  the third to succeeding consistently.

`identifier_field_ids` was also dropped from the seed schema: Unity rejects
identifier columns outright ("Table with identifier columns is not allowed"),
and no probe needs them. That single change is what let one seed path serve
five catalogs.

### What the review did not change

The endpoint tier and the declared-vs-observed tier do not depend on fixture
shape, and every headline finding lives there: the AWS purge contradiction,
Glue's three 200-with-error responses, the 10 overclaims, Unity's etag
requirement, OneLake's docs-versus-declaration inversion. All survived
unchanged, across two further back-to-back sweeps with zero differences
including the measured fixture shapes.

## Coverage against the spec

Probes are diffed against the operations in Apache's own
`open-api/rest-catalog-open-api.yaml`:

| | |
|---|---|
| Spec operations probed | **25 / 35 (71%)** |
| Probes | 33, covering 25 distinct endpoint signatures |
| `updateTable` actions probed | 5 / 25 |
| Table requirements probed | 1 / 8 (assert-table-uuid) |

**Not probed, and why.** `POST /v1/oauth/tokens` (exercised implicitly by the
Polaris and Snowflake auth paths); `register`, `register-view` and `unregister`
(need a pre-existing metadata file to point at); `sign` (S3 request signing, a
vendor-specific extension in practice); `tasks` and the two `plan/{plan-id}`
follow-ups (unreachable without a successful scan plan, which only Glue routes);
and the two `functions` operations (a recent spec addition no implementation
here declares).

**Apache ships a REST Compatibility Kit** (`RESTCompatibilityKitSuite`) that
tests behaviour against the Java reference implementation. It does not
cross-check the `endpoints` declaration against observed behaviour, which is
what the declaration tier here does. The two are complementary, and any writeup
should say so rather than imply no conformance tooling exists.

### Views: declared widely, implemented once

Probing only `listViews`, as this suite originally did, could not tell "views
are unimplemented" from "list is unimplemented". With all six view operations
probed, the answer is unambiguous:

| Catalog | createView / loadView / headView / replaceView / renameView / dropView |
|---|---|
| Polaris | all six work |
| Glue | 406 "ListViews endpoint is not supported for Glue Catalog" |
| S3 Tables | 404 UnknownOperation |
| Unity | `ENDPOINT_NOT_FOUND` |
| BigLake | 404 "Method not found" |
| OneLake | 404 / 405 |
| Horizon | **403 "Authorization failed" on all, as ACCOUNTADMIN** |

Horizon declares **seven** view endpoints and serves none of them. Both Horizon
and Unity were re-tested with a real native view present in the namespace, in
case the failures were an empty-namespace artefact: Unity still answers "No API
found", Horizon still answers 403. Neither is a fixture problem.

### The commit path has depth the endpoint tier missed

Five of the spec's 25 `updateTable` actions are now probed separately. Polaris,
Glue, S3 Tables, Unity and BigLake accept all five. Snowflake does not:

| Action | Horizon |
|---|---|
| set-properties | works |
| add-schema (+ set-current-schema:-1) | works |
| remove-properties | **500 / 409, nondeterministic** |
| set-current-schema (standalone) | **500** |
| upgrade-format-version | **400 "Upgrading the Iceberg format version of an existing table is not allowed for Horizon accounts"** |

The last is an explicit, deliberate refusal. The first two return
`UNEXPECTED_ERROR_SIGNALED ... Indeterminate result during conflict resolution
check` -- the same message seen during seeding on a delete commit, so it is
reproducible across three distinct operations.

**Observed nondeterminism.** Across back-to-back sweeps, Horizon's
`commit_remove_properties` and `commit_set_current_schema` each alternate
between `409 CONFLICT` and `500 SERVER_ERROR` on identical input. Both fail
either way, so the scores are stable; the status code is not. Two probes on the
same conflict-resolution path behaving this way makes it a property of that
path rather than a one-off. Every other cell was stable across six sweeps.

### Surface is scored separately from execution order

`loadView` and `viewExists` are GET and HEAD -- reads -- but they can only run
after a view exists, so they execute in the write phase. An earlier version
scored by execution phase, counting those two as writes: it inflated every
catalog's write denominator and understated its read surface, which is precisely
the number a read-only catalog should be judged on. Probes now carry a `surface`
(what the operation is) separate from `tier` (when it runs), and the summary
scores by surface.

Denominators differ per catalog because untestable probes are excluded rather
than counted as failures. The `not tested` column makes each one reconstructable.


## Privilege audit

Every finding was produced with the highest privilege available, so none can be
dismissed as a permissions problem:

| Catalog | Credential |
|---|---|
| Google BigLake | `roles/owner` on the project |
| AWS Glue / S3 Tables | account **root** |
| Databricks Unity | account admin; `all-apis` PAT; `external_access_enabled=true`; `EXTERNAL USE SCHEMA` on the catalog |
| Snowflake Horizon | `ACCOUNTADMIN` |
| Microsoft OneLake | workspace **Admin** on a Fabric trial capacity |
| Apache Polaris | root principal, `catalog_admin`, `DROP_WITH_PURGE_ENABLED` |

Polaris's purge flag is on deliberately: with it off, the control column shows
artificial 403s on `drop_table?purgeRequested=true` and `dropView`. A red cell
in the control should mean the spec is unimplemented, not that a server flag is
unset.

Two credential problems that were ours, not the vendors', are recorded in the
review section above: an over-tight IAM policy for Snowflake's external volume,
and pyiceberg writing through vended rather than local credentials.

## Limitations

Stated up front, because a vendor whose product scores badly will find these
anyway and it is better to volunteer them.

### Account tier is a genuine confound

Three of the seven ran on trial accounts:

| Catalog | Account | Region |
|---|---|---|
| Apache Polaris 1.7.0 | local container (`sha256:e66366e7…`) | n/a |
| Google BigLake | owned project | US-CENTRAL1 |
| AWS Glue / S3 Tables | owned account (root) | us-east-1 |
| Databricks Unity | **14-day trial** | us-west-2 |
| Snowflake Horizon | **30-day Enterprise trial** | AWS us-east-1 |
| Microsoft OneLake | **60-day Fabric trial capacity (FTL4)** | East US 2 |

This is not a hypothetical concern. Horizon's refusal of `upgrade-format-version`
reads *"not allowed for **Horizon accounts**"*, which is explicitly account-type
language. A finding on a trial tier may not hold on a paid one, and nothing here
can rule that out. Every Unity, Horizon and OneLake result should be read as
"observed on a trial account of this type on this date", not as a property of
the product.

### One observation, one moment, one region

Each catalog was probed in a single region at a single point in time
(2026-09-03), against one table shape. There is no repetition across days, no
concurrency, no second region, and no second fixture shape.

That matters more than it might seem, because **transient variation was
observed**: two Horizon commit probes alternate between 409 and 500 on identical
input. Every other cell was stable across six sweeps, but the existence of those
flips means any single
failing observation could in principle be infrastructure rather than
implementation. Repeated sampling over days would settle it and has not been
done.

### SaaS versions are unpinned

Polaris is pinned to 1.7.0 by image digest. The six managed catalogs expose no
version, so a finding cannot be tied to a release and "that was fixed last week"
is unfalsifiable. Evidence records `run_at` per catalog, which is the best
available substitute.

### The control column is deliberately non-default

Polaris runs locally with `ALLOW_INSECURE_STORAGE_TYPES`, FILE storage, the
production-readiness check bypassed and `DROP_WITH_PURGE_ENABLED` on. Those
choices make it a permissive reference rather than a realistic deployment, and
its score is not comparable to a managed service on operational posture --
no multi-tenancy, no network, no auth hardening. It is a spec baseline, not a
competitor.

### Coverage is 71%, and the commit path is sampled

25 of 35 spec operations, 5 of 25 `updateTable` actions, 1 of 8 table
requirements. A catalog could fail an unprobed action and score well here. The
unprobed operations and the reasons for each are listed under **Coverage against
the spec**.

### Presence is not correctness

The field tier checks whether a field is present, not whether its value is
right. A catalog returning a wrong `last-column-id` scores identically to one
returning the correct value.

### Fixtures are not identical across all seven

Five catalogs share one pyiceberg-seeded fixture. Unity, Horizon and OneLake
differ because they refuse part of that seed -- documented per catalog under
**Fixture shapes**, with the field-tier rows that depend on shape marked †. No
fixture contains positional or equality delete files, because pyiceberg performs
copy-on-write deletes; delete *snapshot* metadata is exercised, delete *files*
are not.

### Client

Probes are raw HTTP (`requests` 2.34.2). Seeding used pyiceberg 0.12.0 with
pyarrow 24.0.0 on Python 3.13.13; some seeding failures may be client-specific
rather than catalog-specific, and the two Unity/Horizon seeding refusals are
reported as what they are -- refusals of *that* client's requests.

### Scored against a moving spec

Probes were diffed against `open-api/rest-catalog-open-api.yaml` on the Apache
Iceberg main branch as of 2026-09-03. The spec is under active development; the
`functions` operations, for instance, are recent enough that no implementation
here declares them.

## Before the first real run

Verify every `base_url` in `catalogs.yaml` against the vendor's docs. A wrong
base URL produces a full column of 404s that reads like a conformance finding
but is really a typo. The harness records the prefix resolved from
`GET /v1/config`, which is the quickest way to tell the two apart: a catalog
that answers `/v1/config` but 404s everything else is a prefix problem, not a
missing implementation.

Start Polaris locally first. Getting a clean control column working end to end
validates the harness before any credentialed vendor is involved.

## Layout

| File | Role |
|---|---|
| `probe/spec.py` | the probe suite + 30 field paths + verdict vocabulary |
| `probe/auth.py` | gcloud / SigV4 / OAuth2 / az CLI / bearer-env providers |
| `probe/runner.py` | execution, templating, redaction, evidence writing |
| `probe/report.py` | matrix construction from evidence only |
| `run.py` | CLI |
