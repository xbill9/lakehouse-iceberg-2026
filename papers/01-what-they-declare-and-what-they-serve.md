# Seven Iceberg REST Catalogs: What They Declare, and What They Serve

Every vendor with a lakehouse now ships an Apache Iceberg REST catalog, and every
one of them says it implements the same specification. That claim is checkable,
and as far as I can find nobody has published the check.

So I built one request suite and pointed it at seven implementations: Google
Cloud's Lakehouse REST catalog, AWS Glue, AWS S3 Tables, Databricks Unity,
Snowflake Horizon, Microsoft OneLake Table APIs, and a self-hosted Apache
Polaris 1.7.0 as the control. Same probes, same table, same day.

All results below were measured on 2026-09-03.

Nothing here is about the REST catalog being broken. It works — every catalog
served the core read path. This is about what happens underneath that, and about
one specific thing the spec asks a server to publish about itself: a
machine-readable list of the endpoints it supports.

---

## What you need to reproduce this, and what it costs

Read this before you invest an afternoon. Seven catalogs means seven accounts,
and three of mine were trials that will have expired by the time most people
read this.

| catalog | what you need | what I used |
|---|---|---|
| Apache Polaris | Docker | local container, free |
| Google BigLake | GCP project, Lakehouse API enabled | owned project, pay-as-you-go |
| AWS Glue | AWS account | owned account |
| AWS S3 Tables | AWS account | owned account |
| Databricks Unity | **Premium** workspace — Free Edition cannot enable external data access | 14-day trial, started 2026-09-03 |
| Snowflake Horizon | any Snowflake account | 30-day Enterprise trial, started 2026-09-03 |
| Microsoft OneLake | Fabric licence **on a work/school account** + capacity | 60-day Fabric trial capacity, started 2026-09-03 |

Three of those need saying plainly.

**Databricks Free Edition will not work.** Enabling external data access is an
account-level action, and Free Edition documents no access to the account
console. The 14-day Premium trial does work.

**A personal Microsoft account cannot hold a Fabric licence.** The Fabric API
returns `UserNotLicensed` and no amount of configuration changes it. You need a
work or school account in an Entra tenant. Once you have one, the **free 60-day
trial capacity is enough** — the paid F-SKU that the Azure portal steers you
toward starts around $260/month and is not needed for this.

**Snowflake Open Catalog is closed to new signups.** Snowflake's docs state that
customers without an existing Open Catalog account cannot create their first
one, and direct new customers to Horizon. Horizon is what this measures.

Being on a trial tier is also a genuine confound in the results, not just an
inconvenience — Horizon's refusal of one operation reads *"not allowed for
Horizon **accounts**"*, which is explicit account-type language. The Limitations
section at the end returns to this.

---

## What is Apache Iceberg, and what is the REST catalog?

Iceberg is a table format. A table is a directory of Parquet files plus a chain
of JSON metadata files that says which of those files are part of the table right
now, what the schema is, how it is partitioned, and what it looked like at every
previous commit. That last part is why engines can time-travel and why two
writers can commit without corrupting each other.

Something has to hold the pointer to the current metadata file. That something is
the catalog. It answers one question — *for table `X`, where is the metadata
right now* — and it makes commits atomic by swapping that pointer.

For years each engine brought its own catalog: Hive Metastore, a Glue client, a
JDBC catalog, a filesystem convention. Every engine needed a driver for every
catalog.

The **Iceberg REST catalog** replaces that with one HTTP API. A client speaks
HTTP to a URL; the vendor implements the endpoints behind it. The specification
lives in the Iceberg repository as
[`open-api/rest-catalog-open-api.yaml`](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml),
and it defines **35 operations** — listing namespaces, loading a table,
committing an update, creating a view, planning a scan, and so on.

The endpoint every client calls first is `GET /v1/config`. It returns the
routing prefix to use for every later request, and it may return one more thing:

> **endpoints**: A list of endpoints that the server supports. The format of each
> endpoint must be `"<HTTP verb> <resource path from OpenAPI REST spec>"`.
>
> — `rest-catalog-open-api.yaml`, `CatalogConfig`

That field is the reason this article exists. A catalog publishes a
machine-readable list of what it supports. Nothing stops a client from trusting
it. So: do the seven agree with themselves?

Throughout, I use **declared** to mean "named in that `endpoints` array" and
**served** to mean "returned a 2xx to the probe". Where a catalog declares an
endpoint and does not serve it, I call that an **overclaim**, on the strength of
the spec's own word *supports*.

### What this suite does not do

Apache ships a **REST Compatibility Kit** — `RESTCompatibilityKitSuite` in the
Iceberg repo — which tests a server's behaviour against the Java reference
implementation. It is the right tool for "is this catalog correct". It does not
compare a server's `endpoints` declaration against what that server actually
serves, which is the axis here. The two are complementary and I am not
replacing it.

This suite also never checks whether a returned value is *right*. It checks
whether a field is present. A catalog returning a wrong `last-column-id` scores
the same as one returning the correct value.

---

## Vendor summary

Seven catalogs, measured 2026-09-03. Read and write surfaces are scored
separately and not summed — a catalog that is read-only by design scores zero on
writes, and folding that into one number makes a deliberate design read as a
broken implementation.

| catalog | read probes | write probes | not tested | declares |
|---|---|---|---|---|
| Apache Polaris 1.7.0 | 15/16 | 16/17 | 0 | 36 |
| Databricks Unity | 12/14 | 10/17 | 2 | 18 |
| Snowflake Horizon | 12/14 | 7/14 | 5 | 23 |
| Google BigLake | 11/14 | 10/14 | 5 | 15 |
| Microsoft OneLake | 11/15 | 0/14 | 4 | 13 |
| AWS Glue | 9/15 | 10/17 | 1 | none |
| AWS S3 Tables | 9/15 | 10/17 | 1 | none |

Denominators differ because probes that could not be tested are excluded rather
than counted as failures. If a catalog refuses to create a namespace, the probes
that needed one prove nothing about the endpoints they target. The `not tested`
column is that count, so every denominator reconstructs.

Three things in that table are worth saying out loud.

**Two of seven publish no `endpoints` list at all.** Glue and S3 Tables return a
config with no declaration, so a client cannot discover their capabilities
without probing. That is not a spec violation — the field is optional — but it
means capability discovery is unavailable on both AWS catalogs.

**The two AWS catalogs score identically and are not the same implementation.**
They agree on totals and disagree on behaviour, which the results section covers.

**OneLake's read surface is mid-pack, not last.** 11/15 puts it level with
Google and ahead of both AWS catalogs. Its zero on writes is its documented
design, not a deficiency, and the two numbers should not be added together.

Each catalog's routing prefix, from its own `/v1/config`:

| catalog | prefix as returned |
|---|---|
| Polaris | `quickstart_catalog` |
| Glue | `catalogs/AWS_ACCOUNT_ID` |
| S3 Tables | `arn%3Aaws%3As3tables%3Aus-east-1%3A…%3Abucket%2Ficeberg-probe` |
| Unity | `catalogs/workspace` |
| BigLake | `projects/GCP_PROJECT_NUMBER/catalogs/GCP_PROJECT-iceberg-probe` |
| OneLake | `<workspaceId>/<lakehouseId>` |
| Horizon | `PROBE_DB` |

These are worth showing because a prefix is not a single path segment. Google
returns four, Unity and OneLake return two, and S3 Tables returns a
percent-encoded ARN. A client that treats the prefix as one segment, or that
re-encodes it, will produce URLs the server does not route. I made that mistake
twice while building this.

---

## Step by step: bringing up each catalog

Every catalog needed at least one non-obvious step before it would answer. These
are the exact sequences that worked.

Client versions throughout: Python 3.13.13, `requests` 2.34.2, `pyiceberg` 0.12.0
with `pyarrow` 24.0.0, `botocore` 1.43.34.

### Apache Polaris — the control

Runs locally in Docker. Four things are not obvious and each one cost a failed
attempt.

```console
$ docker run -d --name polaris -p 8181:8181 -p 8182:8182 \
    --user "$(id -u):$(id -g)" \
    -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
    -v "$WH:$WH" \
    -e HADOOP_USER_NAME="$(id -un)" \
    -e POLARIS_BOOTSTRAP_CREDENTIALS=POLARIS,root,s3cr3t \
    -e JAVA_OPTS_APPEND="-Dpolaris.features.\"ALLOW_INSECURE_STORAGE_TYPES\"=true \
       -Dpolaris.features.\"SUPPORTED_CATALOG_STORAGE_TYPES\"=[\"FILE\"] \
       -Dpolaris.readiness.ignore-severe-issues=true \
       -Dpolaris.features.\"DROP_WITH_PURGE_ENABLED\"=true" \
    apache/polaris:latest
```

1. FILE storage is refused by default. Enabling it needs **both**
   `ALLOW_INSECURE_STORAGE_TYPES` and `SUPPORTED_CATALOG_STORAGE_TYPES`.
2. Enabling it then escalates the production-readiness check from warning to
   fatal, so `polaris.readiness.ignore-severe-issues` is required as well. Without
   it the container exits 1 with `Severe production readiness issues detected`.
3. The container writes table metadata and the client writes data files, so both
   need the same warehouse path — hence the bind mount at an identical absolute
   path, and `--user` so the files are owned by you.
4. With `--user`, Hadoop's `UserGroupInformation` cannot resolve the uid and the
   login fails. The symptom is a **503 that reads like a storage error**:
   `RuntimeIOException: Failed to get file system for path`. Mounting
   `/etc/passwd` read-only fixes it.

`DROP_WITH_PURGE_ENABLED` is on deliberately. With it off, Polaris refuses both
`drop_table?purgeRequested=true` and `dropView`, which would put artificial red
cells in the control column.

Then the catalog and grants:

```console
$ TOK=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
    -d grant_type=client_credentials -d client_id=root -d client_secret=s3cr3t \
    -d scope=PRINCIPAL_ROLE:ALL | jq -r .access_token)

$ curl -s -X POST http://localhost:8181/api/management/v1/catalogs \
    -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
    -d '{"catalog":{"name":"quickstart_catalog","type":"INTERNAL",
         "properties":{"default-base-location":"file://'$WH'"},
         "storageConfigInfo":{"storageType":"FILE",
           "allowedLocations":["file://'$WH'"]}}}'
```

### Google BigLake

Endpoint: `https://biglake.googleapis.com/iceberg/v1/restcatalog`. Note `v1`, not
`v1beta` — both resolve and return identical config, but `v1` is what the docs
give.

```console
$ gcloud services enable biglake.googleapis.com --project=$PROJECT
$ gcloud storage buckets create gs://$PROJECT-iceberg-probe \
    --project=$PROJECT --location=us-central1 --uniform-bucket-level-access
```

Two things are required beyond the URL. The API is enabled under the name
`biglake.googleapis.com` but the error calls it the **Lakehouse API**, and every
request needs an `x-goog-user-project` header or it returns 403. The warehouse is
`gs://BUCKET` for a single-bucket catalog or
`bl://projects/PROJECT/catalogs/CATALOG` for a multi-bucket one — not `bq://`,
which addresses the separate BigQuery federation endpoint.

Seeding writes data files to GCS using application-default credentials, which are
separate from the `gcloud` user token. If you see `invalid_rapt`, run
`gcloud auth application-default login`.

### AWS Glue

Endpoint: `https://glue.us-east-1.amazonaws.com/iceberg`, SigV4-signed with
signing name `glue`. The warehouse is the account id.

```console
$ aws s3api create-bucket --bucket $BUCKET --region us-east-1
$ aws glue create-database --region us-east-1 \
    --database-input "{\"Name\":\"probe_ns\",\"LocationUri\":\"s3://$BUCKET/probe_ns/\"}"
```

Glue rejects `createTable` without an explicit table location:
`Location information cannot be null while creating an iceberg table`. Every
other catalog here infers it.

### AWS S3 Tables

Endpoint: `https://s3tables.us-east-1.amazonaws.com/iceberg`, SigV4 with signing
name `s3tables`. The warehouse is the table bucket ARN.

```console
$ ARN=$(aws s3tables create-table-bucket --name iceberg-probe \
    --region us-east-1 --query arn --output text)
$ aws s3tables create-namespace --table-bucket-arn "$ARN" \
    --namespace probe_ns --region us-east-1
```

Two constraints that are not in the error messages until you hit them. Namespace
names are case-sensitive and **uppercase is rejected** — a scratch namespace
stamped `irc_probe_20260903T1626` fails on the `T`. And `createTable` requires
`stage-create` in the body.

S3 Tables' managed bucket also rejected `pyiceberg`'s default PyArrow writer with
`The authorization mechanism you have provided is not supported. Please use
Signature Version 4`. Switching to `pyiceberg.io.fsspec.FsspecFileIO` worked.

### Databricks Unity

Endpoint:
`https://<workspace>.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest`.

Three prerequisites, in order:

```console
# 1. external data access is off by default, per metastore
$ curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
    "$HOST/api/2.1/unity-catalog/metastores/$METASTORE_ID" \
    -d '{"external_access_enabled": true}'

# 2. the privilege, granted on the CATALOG
$ ... "GRANT EXTERNAL USE SCHEMA ON CATALOG workspace TO \`user@example.com\`"
```

Granting on a *schema* in the default `workspace` catalog fails with
`PRIVILEGE_NOT_APPLICABLE_TO_ENTITY` — those schemas are `SCHEMA_DB_STORAGE`
entities. Granting on the catalog works.

Third: **the Iceberg endpoint requires a token with the `all-apis` scope.** A PAT
scoped to `unity-catalog` + `sql` — which is sufficient for Unity's own REST API
and for the SQL statement API — is rejected by the Iceberg endpoint with
`403 Provided access token does not have required scopes: all-apis`. Probing the
open-standard surface needs a broader credential than the vendor's own APIs do.

Unity also rejects two things during seeding. `identifier_field_ids` in a create
request returns `Table with identifier columns is not allowed`, and managed
Iceberg tables reject `write.delete.mode` with
`MANAGED_ICEBERG_OPERATION_NOT_SUPPORTED`.

Finally, Unity's vended credentials **explicitly deny `s3:PutObject`** on
Databricks-managed storage, so an external engine can create a table through the
REST catalog but cannot write data files into it. That table was seeded through
Databricks SQL instead.

### Snowflake Horizon

Endpoint: `https://<account>.snowflakecomputing.com/polaris/api/catalog` — the
same path as Open Catalog, because Apache Polaris is embedded in Horizon. The
warehouse is a Snowflake **database** name, not a warehouse.

Auth is key-pair, which means no password is ever handled:

```console
$ openssl genrsa -out sf_key.pem 2048
$ openssl rsa -in sf_key.pem -pubout -out sf_key.pub
```

Register the public key once, then everything else runs over the SQL API:

```sql
ALTER USER MYUSER SET RSA_PUBLIC_KEY='MIIBIjANBgkq...';
```

The token exchange differs from stock Polaris in two ways: the scope is
`session:role:<role>` rather than `PRINCIPAL_ROLE:ALL`, and the
`client_credentials` grant carries a signed JWT in `client_secret` with no
`client_id` at all.

```console
$ curl -X POST "$HOST/polaris/api/catalog/v1/oauth/tokens" \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode 'scope=session:role:ACCOUNTADMIN' \
    --data-urlencode "client_secret=$JWT"
```

Snowflake-managed Iceberg tables need an external volume, which needs an IAM
role whose trust policy names Snowflake's IAM user and external id — values you
only get *after* creating the volume:

```sql
CREATE OR REPLACE EXTERNAL VOLUME SF_ICEBERG_PROBE
  STORAGE_LOCATIONS = ((NAME='us-east-1-s3' STORAGE_PROVIDER='S3'
    STORAGE_BASE_URL='s3://mybucket/snowflake/'
    STORAGE_AWS_ROLE_ARN='arn:aws:iam::ACCOUNT:role/snowflake-iceberg-probe'))
  ALLOW_WRITES = TRUE;
DESC EXTERNAL VOLUME SF_ICEBERG_PROBE;   -- read STORAGE_AWS_IAM_USER_ARN + EXTERNAL_ID
```

Update the role's trust policy with those two values, then
`SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('SF_ICEBERG_PROBE')` should return
`"success": true` with read, write, list and delete all `PASSED`.

Two more: Snowflake rejects `TIMESTAMP_TZ(9)` for Iceberg tables and wants
`TIMESTAMP_LTZ(6)`; and creating a table through the REST catalog requires the
database to carry a default external volume
(`ALTER DATABASE PROBE_DB SET EXTERNAL_VOLUME = ...`). Without it, `createTable`
returns 403 and four downstream probes fail for reasons that have nothing to do
with the endpoints they target.

### Microsoft OneLake

Endpoint: `https://onelake.table.fabric.microsoft.com/iceberg`. Warehouse and
prefix are both `<workspaceId>/<dataItemId>`. The bearer token audience is
`https://storage.azure.com`.

The gate here is licensing, not configuration. A personal Microsoft account
cannot hold a Fabric licence — the Fabric API returns `UserNotLicensed` and the
account console shows no capacity. A work or school account in an Entra tenant
can, and the **free 60-day trial capacity is sufficient**; no paid F-SKU is
required.

```console
$ az login
$ # portal: account manager -> Free trial -> Start trial -> Fabric and Power BI
```

Then a workspace on that capacity, and a lakehouse in it:

```console
$ curl -s -X POST -H "Authorization: Bearer $FT" "$API/workspaces" \
    -d '{"displayName":"iceberg-probe-ws"}'
$ curl -s -X POST -H "Authorization: Bearer $FT" \
    "$API/workspaces/$WS/assignToCapacity" -d "{\"capacityId\":\"$CAP\"}"
$ curl -s -X POST -H "Authorization: Bearer $FT" \
    "$API/workspaces/$WS/lakehouses" -d '{"displayName":"probe_lh"}'
```

The table is loaded from CSV through the Fabric load-table API and stored as
Delta. OneLake exposes it through the Iceberg endpoint by virtualisation — its
table properties carry `XTABLE_METADATA` with `"sourceTableFormat":"DELTA"`.

---

## Results

The suite runs 33 probes covering 25 of the specification's 35 operations (71%),
diffed against `rest-catalog-open-api.yaml` on the Iceberg main branch as of
2026-09-03.

### Views are declared widely and implemented once

The specification has six view operations. Probing only `listViews` cannot tell
"views are unimplemented" from "list is unimplemented", so all six are probed.

| catalog | createView / loadView / viewExists / replaceView / renameView / dropView |
|---|---|
| Polaris | all six served |
| Glue | 406 — `ListViews endpoint is not supported for Glue Catalog` |
| S3 Tables | 404 `UnknownOperationException` |
| Unity | 404 `ENDPOINT_NOT_FOUND` |
| BigLake | 404 `Method not found` |
| OneLake | 404 / 405 |
| Horizon | **403 `Authorization failed`, as ACCOUNTADMIN** |

Horizon declares **seven** view endpoints and serves none of them. Both Horizon
and Unity were re-tested with a real native view present in the namespace, in
case the failures were an empty-namespace artefact. Unity still answers
`No API found`; Horizon still answers 403. Neither is a fixture problem, and
ACCOUNTADMIN is the highest role in a Snowflake account.

### Glue answers unrouted operations with HTTP 200

Three probes against Glue — `plan_table_scan`, `report_metrics` and
`commit_transaction` — return `200 OK` carrying:

```json
{"Output": {"__type": "com.amazon.coral.service#UnknownOperationException"},
 "Version": "1.0"}
```

The mechanism is AWS's own protocol layer answering an operation its front door
does not route, not Glue returning a broken success for an implemented endpoint.
The consequence for a client is the same either way: a client that checks status
codes sees three endpoints that work. The suite scores these as their own verdict
rather than as `OK`.

Glue's config also advertises `rest-table-scan-enabled: true`, and scan planning
is one of the three.

### Eleven overclaims across four vendors

Endpoints named in a catalog's own `endpoints` array that did not serve:

| catalog | overclaimed |
|---|---|
| Microsoft OneLake | `create_namespace`, `create_table`, `commit_table`, `rename_table` |
| Snowflake Horizon | `list_views`, `create_view`, `update_namespace_props`, `commit_transaction` |
| Databricks Unity | `plan_table_scan`, `update_namespace_props` |
| Google BigLake | `load_credentials` |
| Apache Polaris | none |
| AWS Glue / S3 Tables | n/a — declare nothing |

Only the open-source control declares honestly. Two catalogs cannot be judged on
this axis at all, because they publish no declaration.

Two of these deserve their exact wording.

**Unity's `update_namespace_props` requires a non-standard field.** It returns
`400 Malformed request: INVALID_PARAMETER_VALUE: Etag token version is missing`.
The specification's `UpdateProperties` request has no etag field, so a
spec-conformant client cannot call this endpoint at all.

**OneLake's documentation and its declaration are wrong in opposite
directions.** Microsoft documents the endpoint as read-only, and that matches
the behaviour — every write returns `Requested Api is not found`. But its
`/v1/config` declares four write endpoints anyway. Meanwhile Microsoft documents
that the `parent` query parameter on `listNamespaces` is *not* supported, and
measured, it works: `?parent=dbo` returns `[]`, and `?parent=zzz` returns
`NoSuchNamespaceException`.

### The commit path has depth the endpoint list does not show

`POST .../tables/{table}` is one endpoint carrying 25 distinct update actions.
Five are probed separately. Polaris, Glue, S3 Tables, Unity and BigLake accept
all five. Horizon accepts two:

| action | Horizon |
|---|---|
| set-properties | 200 |
| add-schema with set-current-schema:-1 | 200 |
| remove-properties | 409 / 500 |
| set-current-schema, standalone | 409 / 500 |
| upgrade-format-version | 400 — `Upgrading the Iceberg format version of an existing table is not allowed for Horizon accounts` |

The last is an explicit refusal. The two showing two status codes are showing
**observed nondeterminism**: across back-to-back sweeps, both alternate between
`409 CONFLICT` and `500 SERVER_ERROR` on identical input, with the 500 carrying
`UNEXPECTED_ERROR_SIGNALED ... Indeterminate result during conflict resolution
check`. Both fail either way, so the scores are stable; the status code is not.
Two probes on the same conflict-resolution path behaving this way makes it a
property of that path rather than a single flaky request. Every other cell in
every catalog was stable across six sweeps.

### What does not differ

The suite also checks 30 field paths in each `loadTable` response — schemas,
column IDs, partition specs, sort orders, snapshot history, refs, statistics.
Twenty-four of the thirty are identical across all seven catalogs.

Whatever separates these implementations, it is not the fidelity of
`loadTable`. Of the six rows that do differ, one is caused by the fixture rather
than the catalog, two reflect storage and credential-vending configuration, and
two are the difference between rendering "no statistics" as an empty list versus
omitting the key. This is a null result and it is worth stating plainly.

---

### Smaller: purge semantics are per-catalog

Dropping a table is not uniform. Polaris refuses `purgeRequested=true` unless
`DROP_WITH_PURGE_ENABLED` is set; Glue refuses it outright with
`PurgeRequested cannot be true for Glue iceberg tables`; S3 Tables refuses a
*plain* drop with `S3 Tables only supports dropping tables with purge enabled`;
BigLake, Unity and Horizon accept the purge form.

This is worth knowing when writing a client, but it is the weakest result here:
these are separate products with different storage models, and a client
configures a catalog once rather than swapping between them. I mention it
because it is measured, not because it is important.

---

## Summary

Reading the seven results together:

**The `endpoints` field is not yet reliable for capability discovery.** Five of
seven publish one; four of those five overclaim; two publish nothing. A client
that trusts the declaration will call endpoints that 404 on four of the seven
catalogs here.

**Views are effectively a Polaris-only feature today.** Six operations, six
managed catalogs, zero implementations.

**"Supports the REST catalog" is true and not very informative.** All seven serve
the core read path. The divergence is entirely in the write surface, in the
update actions inside one endpoint, and in operational semantics like purge.

**Two of the seven cannot be asked this question at all.** Glue and S3 Tables
publish no `endpoints` array, so a client has no way to discover their surface
short of probing it.

---

## Limitations

Stated up front, because a vendor whose product scores badly will find these
anyway.

**Account tier is a real confound.** Three of the seven ran on trial accounts:
Databricks Unity on a 14-day trial, Snowflake Horizon on a 30-day Enterprise
trial, Microsoft OneLake on a 60-day Fabric trial capacity. Google and AWS ran on
owned accounts, and Polaris locally. This is not hypothetical — Horizon's refusal
of `upgrade-format-version` reads *"not allowed for Horizon accounts"*, which is
explicit account-type language. Any Unity, Horizon or OneLake result should be
read as "observed on a trial account of this type on this date".

**One observation, one region, one moment.** Each catalog was probed in a single
region on 2026-09-03 against one table shape: Polaris local, BigLake
us-central1, Glue and S3 Tables us-east-1, Unity us-west-2, Horizon AWS
us-east-1, OneLake East US 2. No repetition across days, no concurrency, no
second region. The Horizon 409/500 flip proves transient variation exists, so any
single failing observation could in principle be infrastructure rather than
implementation.

**Managed catalogs expose no version.** Polaris is pinned by image digest. The
other six cannot be tied to a release, so "that was fixed last week" is
unfalsifiable. Evidence records a timestamp per catalog, which is the best
available substitute.

**The control is deliberately non-default.** Polaris runs locally with insecure
storage types allowed, FILE storage, the readiness check bypassed and purge
enabled. It is a permissive spec baseline, not a realistic deployment, and its
score is not comparable to a managed service on operational posture.

**Coverage is 71%, and the commit path is sampled.** 25 of 35 operations, 5 of 25
update actions, 1 of 8 table requirements. A catalog could fail an unprobed
action and score well here. Not probed: `oauth/tokens`, `register`,
`register-view`, `unregister`, `sign`, `tasks`, the two `plan/{plan-id}`
follow-ups, and the two `functions` operations.

**Presence is not correctness.** The field tier checks that a field exists, not
that its value is right.

**The fixtures are not identical.** Five catalogs share one pyiceberg-seeded
table. Unity, Horizon and OneLake differ because they refuse part of that seed —
Unity denies external data writes to managed storage, Horizon rejects tag refs,
OneLake is read-only. Each fixture's shape is measured from its own `loadTable`
response and published, and the field rows that depend on shape are marked. No
fixture contains positional or equality delete files, because `pyiceberg`
performs copy-on-write deletes; delete *snapshot* metadata is exercised, delete
*files* are not.

**Privilege was maximal everywhere**, so no result here is a permissions
artefact: `roles/owner` on GCP, account root on AWS, `ACCOUNTADMIN` on Snowflake,
account admin with an `all-apis` token on Databricks, workspace Admin on Fabric,
and the root principal on Polaris.
