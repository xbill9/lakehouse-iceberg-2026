# Seven Iceberg REST Catalogs: What They Declare, and What They Serve

*Subtitle: One request suite against seven Apache Iceberg REST catalog implementations, comparing what each declares it supports against what it actually serves.*

This article provides a step by step comparison of seven Apache Iceberg REST
catalog implementations, measuring what each one actually serves against the
published specification. A Python probe harness is built to issue one identical
request suite to every catalog and store the raw response as evidence.

https://github.com/xbill9/lakehouse-iceberg-2026

Every vendor with a lakehouse now ships an Iceberg REST catalog, and every one of
them says it implements the same specification. That claim is checkable. The
specification also asks a server to publish a machine-readable list of the
endpoints it supports, which makes a second claim checkable: does a catalog agree
with itself?

All results below were measured on 2026-09-03.

Nothing here is about the REST catalog being broken. It works — every catalog
served the core read path.

## What Do You Need to Reproduce This?

Seven catalogs means seven accounts, and three of mine were trials that will have
expired by the time most people read this. Read this section before investing an
afternoon.

| Catalog | What you need | What I used |
|---|---|---|
| Apache Polaris | Docker | local container, free |
| Google BigLake | GCP project, Lakehouse API enabled | owned project |
| AWS Glue | AWS account | owned account |
| AWS S3 Tables | AWS account | owned account |
| Databricks Unity | **Premium** workspace | 14-day trial |
| Snowflake Horizon | any Snowflake account | 30-day Enterprise trial |
| Microsoft OneLake | Fabric licence on a **work** account | 60-day Fabric trial capacity |

Three of those need saying plainly.

**Databricks Free Edition will not work.** Enabling external data access is an
account-level action, and Free Edition documents no access to the account console.

**A personal Microsoft account cannot hold a Fabric licence.** The Fabric API
returns `UserNotLicensed` and no configuration changes it. A work or school
account in an Entra tenant can, and the free 60-day trial capacity is enough —
the paid F-SKU the Azure portal steers you toward is not needed.

**Snowflake Open Catalog is closed to new signups.** Snowflake's documentation
directs new customers to Horizon, which is what this measures.

Being on a trial tier is also a genuine confound in the results, not only an
inconvenience. The limitations section returns to it.

## What Is Apache Iceberg?

Iceberg is a table format. A table is a directory of Parquet files plus a chain of
JSON metadata files recording which of those files belong to the table right now,
what the schema is, how it is partitioned, and what it looked like at every
previous commit. That history is why engines can time-travel and why two writers
can commit without corrupting each other.

Something has to hold the pointer to the current metadata file. That something is
the catalog. It answers one question — for table `X`, where is the metadata right
now — and it makes commits atomic by swapping that pointer.

## What Is the REST Catalog?

For years each engine brought its own catalog: Hive Metastore, a Glue client, a
JDBC catalog, a filesystem convention. Every engine needed a driver for every
catalog.

The Iceberg REST catalog replaces that with one HTTP API. A client speaks HTTP to
a URL and the vendor implements the endpoints behind it. The specification lives
in the Iceberg repository as `open-api/rest-catalog-open-api.yaml`.

```console
$ curl -sL -o irc.yaml https://raw.githubusercontent.com/apache/iceberg/main/open-api/rest-catalog-open-api.yaml
$ python3 - <<'EOF'
import re
lines = open('irc.yaml').read().split('\n')
inpaths = False; cur = None; ops = []
for l in lines:
    if re.match(r"^paths:", l): inpaths = True; continue
    if inpaths and re.match(r"^\S", l): break
    m = re.match(r"^  (/\S*):\s*$", l)
    if m: cur = m.group(1); continue
    m2 = re.match(r"^    (get|put|post|delete|head|patch):\s*$", l)
    if m2 and cur: ops.append('%s %s' % (m2.group(1).upper(), cur))
print("spec operations:", len(ops))
EOF
spec operations: 35
```

Thirty-five operations: listing namespaces, loading a table, committing an update,
creating a view, planning a scan.

## What Does a Catalog Say About Itself?

The endpoint every client calls first is `GET /v1/config`. It returns the routing
prefix for every later request, and it may return one more thing:

> **endpoints**: A list of endpoints that the server supports. The format of each
> endpoint must be `"<HTTP verb> <resource path from OpenAPI REST spec>"`.
>
> — `rest-catalog-open-api.yaml`, `CatalogConfig`

That field is the reason this article exists. A catalog publishes a
machine-readable list of what it supports, and nothing stops a client from
trusting it.

Throughout, **declared** means named in that array and **served** means returned a
2xx to the probe. Where a catalog declares an endpoint and does not serve it, I
call that an **overclaim**, on the strength of the spec's own word *supports*.

## What This Suite Does Not Do

Apache ships a REST Compatibility Kit, `RESTCompatibilityKitSuite`, which tests a
server's behaviour against the Java reference implementation. It is the right tool
for "is this catalog correct". It does not compare a server's declaration against
what that server serves, which is the axis here. The two are complementary.

This suite also never checks whether a returned value is *right*. It checks
whether a field is present.

## The Harness

Three tiers of evidence, from one identical request suite:

- **Endpoint tier** — does the operation exist, and what status comes back
- **Field tier** — 30 specification field paths checked against each `loadTable`
- **Declaration tier** — the `endpoints` array cross-checked against behaviour

```console
$ python3 -c "
import sys; sys.path.insert(0,'.')
from probe import spec
sigs = {p.signature() for p in spec.PROBES + spec.WRITE_PROBES}
print('probes:', len(spec.PROBES) + len(spec.WRITE_PROBES))
print('distinct endpoint signatures:', len(sigs))
"
probes: 33
distinct endpoint signatures: 25
```

Twenty-five of the specification's 35 operations, or 71%.

Two design rules matter for reading the results. Raw request and response are
stored for every probe, so a verdict is re-derivable without re-running against a
vendor. And a probe whose prerequisite failed is marked not-tested rather than
failed — if a catalog refuses to create a namespace, the probes that needed one
prove nothing about the endpoints they target.

## At This Point You Should Have

- Docker, for the control catalog
- Python 3.13 with `requests`, `pyiceberg` and `botocore`
- An account on whichever vendors you intend to probe
- The maximum privilege available on each — every result below was gathered with
  `roles/owner`, AWS account root, `ACCOUNTADMIN`, Databricks account admin,
  Fabric workspace Admin, and the Polaris root principal

```console
$ python3 -c "
import sys, pyiceberg, pyarrow, requests, botocore
print('python     ', sys.version.split()[0])
print('pyiceberg  ', pyiceberg.__version__)
print('pyarrow    ', pyarrow.__version__)
print('requests   ', requests.__version__)
print('botocore   ', botocore.__version__)
"
python      3.13.13
pyiceberg   0.12.0
pyarrow     24.0.0
requests    2.34.2
botocore    1.43.34
```

## Bringing Up Apache Polaris, the Control

Start with the control, not the clouds. A red cell in a permissively configured
reference implementation is almost always your bug, not a specification gap.

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
$ curl -sf http://localhost:8182/q/health/ready
{"status": "UP", "checks": [...]}
```

Four things there are not obvious, and each one cost a failed attempt.

FILE storage is refused by default, and enabling it needs **both**
`ALLOW_INSECURE_STORAGE_TYPES` and `SUPPORTED_CATALOG_STORAGE_TYPES`. Enabling it
then escalates the production-readiness check from warning to fatal:

```console
$ docker logs polaris 2>&1 | grep -A1 'Severe production'
Caused by: java.lang.IllegalStateException: Severe production readiness issues
detected, startup aborted!
```

So `polaris.readiness.ignore-severe-issues` is required as well. Third, the
container writes table metadata while the client writes data files, so both need
the same warehouse path — hence the bind mount at an identical absolute path and
`--user` so files are owned by you.

Fourth, and the one that wastes an hour: with `--user`, Hadoop's
`UserGroupInformation` cannot resolve the uid, and the failure surfaces as a 503
that reads like a storage error.

```console
$ # symptom before mounting /etc/passwd
RuntimeIOException: Failed to get file system for path: file:/.../metadata/00000-....json
```

Mounting `/etc/passwd` read-only fixes it. `DROP_WITH_PURGE_ENABLED` is on
deliberately: with it off, Polaris refuses both a purge drop and `dropView`, which
would put artificial red cells in the control.

Then the catalog and its grants:

```console
$ TOK=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
    -d grant_type=client_credentials -d client_id=root -d client_secret=s3cr3t \
    -d scope=PRINCIPAL_ROLE:ALL | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
$ curl -s -o /dev/null -w "create catalog: HTTP %{http_code}\n" \
    -X POST http://localhost:8181/api/management/v1/catalogs \
    -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
    -d "{\"catalog\":{\"name\":\"quickstart_catalog\",\"type\":\"INTERNAL\", ... }}"
create catalog: HTTP 201
```

## Bringing Up Google BigLake

The endpoint is `https://biglake.googleapis.com/iceberg/v1/restcatalog`. Note
`v1`, not `v1beta` — both resolve and return identical config, but `v1` is what
the documentation gives.

```console
$ gcloud services enable biglake.googleapis.com --project=$PROJECT
Operation "operations/acat...." finished successfully.
$ gcloud storage buckets create gs://$PROJECT-iceberg-probe \
    --project=$PROJECT --location=us-central1 --uniform-bucket-level-access
Creating gs://$PROJECT-iceberg-probe/...
```

Two things are required beyond the URL. The API is enabled under the name
`biglake.googleapis.com`, but the error calls it the Lakehouse API:

```console
$ curl -s "https://biglake.googleapis.com/iceberg/v1/restcatalog/v1/config?warehouse=gs://$BUCKET" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)"
{"error": {"code": 403, "message": "Lakehouse API has not been used in project
... before or it is disabled."}}
```

And every request needs an `x-goog-user-project` header. With both in place:

```console
$ curl -s "https://biglake.googleapis.com/iceberg/v1/restcatalog/v1/config?warehouse=gs://$BUCKET" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "x-goog-user-project: $PROJECT"
{"overrides":{"prefix":"projects/GCP_PROJECT_NUMBER/catalogs/GCP_PROJECT-iceberg-probe",
 "catalog_credential_mode":"CREDENTIAL_MODE_END_USER"},"defaults":{...},"endpoints":[...]}
```

The warehouse is `gs://BUCKET` for a single-bucket catalog or
`bl://projects/PROJECT/catalogs/CATALOG` for a multi-bucket one — **not** `bq://`,
which addresses the separate BigQuery federation endpoint.

Seeding writes data files to GCS with application-default credentials, which are
separate from the `gcloud` user token. A `invalid_rapt` error means
`gcloud auth application-default login`.

## Bringing Up AWS Glue

The endpoint is `https://glue.us-east-1.amazonaws.com/iceberg`, SigV4-signed with
signing name `glue`, and the warehouse is the account id.

```console
$ aws s3api create-bucket --bucket $BUCKET --region us-east-1
$ aws glue create-database --region us-east-1 \
    --database-input "{\"Name\":\"probe_ns\",\"LocationUri\":\"s3://$BUCKET/probe_ns/\"}"
$ aws glue get-databases --region us-east-1 --query 'DatabaseList[].Name' --output text
probe_ns
```

Glue rejects `createTable` without an explicit table location, which every other
catalog here infers:

```console
$ # createTable with no location
BadRequestException: Location information cannot be null while creating an iceberg table
```

## Bringing Up AWS S3 Tables

The endpoint is `https://s3tables.us-east-1.amazonaws.com/iceberg`, SigV4 with
signing name `s3tables`, and the warehouse is the table bucket ARN.

```console
$ ARN=$(aws s3tables create-table-bucket --name iceberg-probe \
    --region us-east-1 --query arn --output text)
$ echo $ARN
arn:aws:s3tables:us-east-1:AWS_ACCOUNT_ID:bucket/iceberg-probe
$ aws s3tables create-namespace --table-bucket-arn "$ARN" \
    --namespace probe_ns --region us-east-1
{"tableBucketARN": "...", "namespace": ["probe_ns"]}
```

Two constraints do not appear until you hit them. Namespace names reject
uppercase, so a scratch namespace stamped `irc_probe_20260903T1626` fails on the
`T`:

```console
$ # createNamespace with an uppercase character
The specified namespace name isn't valid. Specify a different namespace name.
```

And `createTable` requires `stage-create` in the body. S3 Tables' managed bucket
also rejected `pyiceberg`'s default PyArrow writer:

```console
$ # seeding with the default FileIO
AWS Error [code 134] during CreateMultipartUpload operation: The authorization
mechanism you have provided is not supported. Please use Signature Version 4.
```

Switching to `pyiceberg.io.fsspec.FsspecFileIO` worked.

## Bringing Up Databricks Unity

The endpoint is
`https://<workspace>.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest`.
Three prerequisites, in order.

External data access is off by default, per metastore:

```console
$ curl -s -H "Authorization: Bearer $TOKEN" "$HOST/api/2.1/unity-catalog/metastore_summary" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['external_access_enabled'])"
False
$ curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
    "$HOST/api/2.1/unity-catalog/metastores/$METASTORE_ID" \
    -d '{"external_access_enabled": true}' | python3 -c "import sys,json;print(json.load(sys.stdin)['external_access_enabled'])"
True
```

Second, the privilege, which must be granted on the **catalog**:

```console
$ # on a schema in the default workspace catalog
GRANT EXTERNAL USE SCHEMA ON SCHEMA workspace.probe_ns TO `you@example.com`
[INVALID_PARAMETER_VALUE.PRIVILEGE_NOT_APPLICABLE_TO_ENTITY] Privilege EXTERNAL
USE SCHEMA is not applicable to this entity [workspace.probe_ns:SCHEMA/SCHEMA_DB_STORAGE]

$ GRANT EXTERNAL USE SCHEMA ON CATALOG workspace TO `you@example.com`
SUCCEEDED
```

Third, and the one worth knowing: the Iceberg endpoint requires a token with the
`all-apis` scope. A PAT scoped to `unity-catalog` plus `sql` — sufficient for
Unity's own REST API and for the SQL statement API — is rejected:

```console
$ curl -s -H "Authorization: Bearer $SCOPED_TOKEN" \
    "$HOST/api/2.1/unity-catalog/iceberg-rest/v1/config?warehouse=workspace"
{"error_code":403,"message":"Provided access token does not have required scopes: all-apis"}
```

Probing the open-standard surface needs a broader credential than the vendor's own
APIs do.

Unity also rejects two things during seeding — `identifier_field_ids` returns
`Table with identifier columns is not allowed`, and managed Iceberg tables reject
`write.delete.mode` with `MANAGED_ICEBERG_OPERATION_NOT_SUPPORTED`. Finally, its
vended credentials explicitly deny `s3:PutObject` on Databricks-managed storage,
so an external engine can create a table through the REST catalog but cannot write
data files into it:

```console
$ # pyiceberg appending through Unity's vended credentials
AWS Error ACCESS_DENIED during CreateMultipartUpload operation: User: ... is not
authorized to perform: s3:PutObject ... with an explicit deny in a resource-based policy
```

That table was seeded through Databricks SQL instead.

## Bringing Up Snowflake Horizon

The endpoint is `https://<account>.snowflakecomputing.com/polaris/api/catalog` —
the same path as Open Catalog, because Apache Polaris is embedded in Horizon. The
warehouse is a Snowflake **database** name, not a warehouse.

Authentication is key-pair, so no account password is handled:

```console
$ openssl genrsa -out sf_key.pem 2048
$ openssl rsa -in sf_key.pem -pubout -out sf_key.pub
writing RSA key
```

Register the public key once, then everything else runs over the SQL API:

```sql
ALTER USER MYUSER SET RSA_PUBLIC_KEY='MIIBIjANBgkq...';
Statement executed successfully.
```

The token exchange differs from stock Polaris in two ways: the scope is
`session:role:<role>` rather than `PRINCIPAL_ROLE:ALL`, and the
`client_credentials` grant carries a signed JWT in `client_secret` with no
`client_id`.

```console
$ curl -s -X POST "$HOST/polaris/api/catalog/v1/oauth/tokens" \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode 'scope=session:role:ACCOUNTADMIN' \
    --data-urlencode "client_secret=$JWT" | head -c 60
{"access_token":"eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

Snowflake-managed Iceberg tables need an external volume, which needs an IAM role
whose trust policy names values you only get after creating the volume:

```sql
CREATE OR REPLACE EXTERNAL VOLUME SF_ICEBERG_PROBE
  STORAGE_LOCATIONS = ((NAME='us-east-1-s3' STORAGE_PROVIDER='S3'
    STORAGE_BASE_URL='s3://mybucket/snowflake/'
    STORAGE_AWS_ROLE_ARN='arn:aws:iam::ACCOUNT:role/snowflake-iceberg-probe'))
  ALLOW_WRITES = TRUE;
SF_ICEBERG_PROBE successfully created.

DESC EXTERNAL VOLUME SF_ICEBERG_PROBE;
STORAGE_AWS_IAM_USER_ARN: arn:aws:iam::...:user/...
STORAGE_AWS_EXTERNAL_ID:  ..._SFCRole=...
```

Update the role's trust policy with those two values, then verify:

```sql
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('SF_ICEBERG_PROBE');
{"success": true, "writeResult": "PASSED", "readResult": "PASSED",
 "listResult": "PASSED", "deleteResult": "PASSED",
 "awsRoleArnValidationResult": "PASSED"}
```

Two more. Snowflake rejects `TIMESTAMP_TZ(9)` for Iceberg tables and wants
`TIMESTAMP_LTZ(6)`. And creating a table through the REST catalog requires the
database to carry a default external volume, or `createTable` returns 403 and four
downstream probes fail for reasons unrelated to the endpoints they target:

```sql
ALTER DATABASE PROBE_DB SET EXTERNAL_VOLUME = 'SF_ICEBERG_PROBE';
Statement executed successfully.
```

## Bringing Up Microsoft OneLake

The endpoint is `https://onelake.table.fabric.microsoft.com/iceberg`. Warehouse
and prefix are both `<workspaceId>/<dataItemId>`, and the bearer token audience is
`https://storage.azure.com`.

The gate here is licensing, not configuration:

```console
$ FT=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
$ curl -s -H "Authorization: Bearer $FT" https://api.fabric.microsoft.com/v1/workspaces
{"requestId":"...","errorCode":"UserNotLicensed","message":"User is not licensed","isRetriable":false}
```

That is a personal Microsoft account, and no configuration changes it. On a work
account, with the free 60-day trial capacity activated:

```console
$ curl -s -H "Authorization: Bearer $FT" https://api.fabric.microsoft.com/v1/capacities \
    | python3 -c "
import sys,json
for c in json.load(sys.stdin)['value']:
    print(c['displayName'], c['sku'], c['state'], c['region'])"
Trial-...  FTL4  Active  East US 2
```

Then a workspace on that capacity, and a lakehouse in it:

```console
$ curl -s -X POST -H "Authorization: Bearer $FT" "$API/workspaces" \
    -d '{"displayName":"iceberg-probe-ws"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])"
FABRIC_WORKSPACE_ID
$ curl -s -o /dev/null -w "assign capacity: HTTP %{http_code}\n" -X POST \
    -H "Authorization: Bearer $FT" "$API/workspaces/$WS/assignToCapacity" -d "{\"capacityId\":\"$CAP\"}"
assign capacity: HTTP 202
$ curl -s -X POST -H "Authorization: Bearer $FT" "$API/workspaces/$WS/lakehouses" \
    -d '{"displayName":"probe_lh"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])"
FABRIC_LAKEHOUSE_ID
```

The table is loaded from CSV through the Fabric load-table API and stored as
Delta. OneLake exposes it through the Iceberg endpoint by virtualisation — its
properties carry `XTABLE_METADATA` with `"sourceTableFormat":"DELTA"`.

## Vendor Summary

Read and write surfaces are scored separately and deliberately not summed. A
catalog that is read-only by design scores zero on writes, and folding that into
one number makes a deliberate design read as a broken implementation.

| Catalog | Read probes | Write probes | Not tested | Declares |
|---|---|---|---|---|
|  Apache Polaris 1.7.0 | 15/16 | 16/17 | 0 | 36 |
|  Databricks Unity | 12/14 | 10/17 | 2 | 18 |
|  Snowflake Horizon | 12/14 | 7/14 | 5 | 23 |
| Google BigLake | 11/14 | 10/14 | 5 | 15 |
| Microsoft OneLake | 11/15 | 0/14 | 4 | 13 |
| AWS Glue | 9/15 | 10/17 | 1 | none |
| AWS S3 Tables | 9/15 | 10/17 | 1 | none |

Denominators differ because probes that could not be tested are excluded rather
than counted as failures. The not-tested column makes each one reconstructable.

Two of seven publish no `endpoints` list at all, so a client cannot discover their
capabilities without probing. That is not a specification violation — the field is
optional — but it means capability discovery is unavailable on both AWS catalogs.

OneLake's read surface is mid-pack rather than last. Its zero on writes is its
documented design.

## Why the Prefix Matters

Each catalog's routing prefix, as its own `/v1/config` returns it:

| Catalog | Prefix |
|---|---|
| Polaris | `quickstart_catalog` |
| Glue | `catalogs/AWS_ACCOUNT_ID` |
| S3 Tables | `arn%3Aaws%3As3tables%3A...%3Abucket%2Ficeberg-probe` |
| Unity | `catalogs/workspace` |
| BigLake | `projects/GCP_PROJECT_NUMBER/catalogs/GCP_PROJECT-iceberg-probe` |
| OneLake | `<workspaceId>/<lakehouseId>` |
| Horizon | `PROBE_DB` |

A prefix is not a single path segment. Google returns four, Unity and OneLake
return two, and S3 Tables returns a percent-encoded ARN. A client that treats the
prefix as one segment, or that re-encodes it, produces URLs the server does not
route. I made both mistakes while building this.

## Views Are Declared Widely and Implemented Once

The specification has six view operations. Probing only `listViews` cannot
distinguish "views are unimplemented" from "list is unimplemented", so all six are
probed.

| Catalog | createView, loadView, viewExists, replaceView, renameView, dropView |
|---|---|
|  Polaris | all six served |
|  Glue | 406 — `ListViews endpoint is not supported for Glue Catalog` |
|  S3 Tables | 404 `UnknownOperationException` |
|  Unity | 404 `ENDPOINT_NOT_FOUND` |
|  BigLake | 404 `Method not found` |
|  OneLake | 404 and 405 |
|  Horizon | 403 `Authorization failed`, as ACCOUNTADMIN |

Horizon declares seven view endpoints and serves none of them. Both Horizon and
Unity were re-tested with a real native view present in the namespace, in case the
failures were an empty-namespace artefact:

```console
$ # a native view exists in both, created through each vendor's own SQL
$ curl -s -H "Authorization: Bearer $SFT" "$SF/v1/PROBE_DB/namespaces/PROBE_NS/views"
{"error":{"message":"Authorization failed","type":"ForbiddenException","code":403}}

$ curl -s -H "Authorization: Bearer $DBT" "$DBX/v1/catalogs/workspace/namespaces/probe_ns/views"
{"error_code":"ENDPOINT_NOT_FOUND","message":"No API found for 'GET .../views'"}
```

Neither is a fixture problem, and ACCOUNTADMIN is the highest role in a Snowflake
account.

## Glue Answers Unrouted Operations With HTTP 200

Three probes against Glue return `200 OK` carrying an exception:

```console
$ # POST .../tables/{table}/metrics against Glue
HTTP 200
{"Output": {"__type": "com.amazon.coral.service#UnknownOperationException"}, "Version": "1.0"}
```

The mechanism is the AWS protocol layer answering an operation its front door does
not route, rather than Glue returning a broken success for an implemented
endpoint. The consequence for a client is the same either way: code that checks
status codes sees three endpoints that work. The harness scores these with their
own verdict rather than as `OK`.

Glue's config also advertises `rest-table-scan-enabled: true`, and scan planning is
one of the three.

## Eleven Overclaims Across Four Vendors

Endpoints named in a catalog's own `endpoints` array that did not serve:

| Catalog | Overclaimed |
|---|---|
| Microsoft OneLake | `create_namespace`, `create_table`, `commit_table`, `rename_table` |
| Snowflake Horizon | `list_views`, `create_view`, `update_namespace_props`, `commit_transaction` |
| Databricks Unity | `plan_table_scan`, `update_namespace_props` |
| Google BigLake | `load_credentials` |
| Apache Polaris | none |
| AWS Glue, AWS S3 Tables | not applicable — declare nothing |

Only the open-source control declares honestly. Two catalogs cannot be judged on
this axis at all.

Two of these deserve their exact wording. Unity's `update_namespace_props`
requires a field the specification does not define:

```console
$ # POST .../namespaces/{namespace}/properties against Unity
HTTP 400
Malformed request: INVALID_PARAMETER_VALUE: Etag token version is missing
```

The specification's `UpdateProperties` request has no etag field, so a conformant
client cannot call this endpoint at all.

And OneLake's documentation and its declaration are wrong in opposite directions.
Microsoft documents the endpoint as read-only, which matches the behaviour — every
write returns `Requested Api is not found` — but `/v1/config` declares four write
endpoints anyway. Meanwhile Microsoft documents that the `parent` query parameter
on `listNamespaces` is not supported, and measured, it works:

```console
$ curl -s -H "Authorization: Bearer $ST" "$OL/v1/$PREFIX/namespaces?parent=dbo"
{"namespaces":[],"next-page-token":null}
$ curl -s -H "Authorization: Bearer $ST" "$OL/v1/$PREFIX/namespaces?parent=zzz"
{"error":{"message":"The given namespace does not exist","type":"NoSuchNamespaceException"...
```

An empty list for a namespace with no children, and a typed error for one that
does not exist. That is the parameter working.

## The Commit Path Has Depth the Endpoint List Does Not Show

`POST .../tables/{table}` is one endpoint carrying 25 distinct update actions.
Five are probed separately. Polaris, Glue, S3 Tables, Unity and BigLake accept all
five. Horizon accepts two:

| Action | Horizon |
|---|---|
|  set-properties | 200 |
|  add-schema with set-current-schema:-1 | 200 |
|  remove-properties | 409 or 500 |
|  set-current-schema, standalone | 409 or 500 |
|  upgrade-format-version | 400 |

The last is an explicit refusal:

```console
$ # upgrade-format-version to 2 against Horizon
HTTP 400
Upgrading the Iceberg format version of an existing table is not allowed for
Horizon accounts
```

The two showing two status codes are showing observed nondeterminism. Across
back-to-back sweeps both alternate between `409 CONFLICT` and `500 SERVER_ERROR`
on identical input:

```console
$ # two consecutive full sweeps, diffed
snowflake-horizon commit_remove_properties:  CONFLICT     -> SERVER_ERROR
snowflake-horizon commit_set_current_schema: SERVER_ERROR -> CONFLICT
differences across two sweeps: 2
```

The 500 carries `UNEXPECTED_ERROR_SIGNALED ... Indeterminate result during
conflict resolution check`. Both fail either way, so the scores are stable and the
status code is not. Two probes on the same conflict-resolution path behaving this
way makes it a property of that path rather than a single flaky request. Every
other cell in every catalog was stable across six sweeps.

## What Does Not Differ

The suite also checks 30 field paths in each `loadTable` response — schemas,
column IDs, partition specs, sort orders, snapshot history, refs, statistics.
Twenty-four of the thirty are identical across all seven catalogs.

Whatever separates these implementations, it is not the fidelity of `loadTable`.
Of the six rows that do differ, one is caused by the fixture rather than the
catalog, two reflect storage and credential-vending configuration, and two are the
difference between rendering "no statistics" as an empty list and omitting the
key.

This is a null result and it is worth stating plainly.

## Smaller: Purge Semantics Are Per-Catalog

Dropping a table is not uniform. Polaris refuses `purgeRequested=true` unless
`DROP_WITH_PURGE_ENABLED` is set, Glue refuses it outright, S3 Tables refuses a
plain drop, and BigLake, Unity and Horizon accept the purge form.

```console
$ # DELETE .../tables/{table}?purgeRequested=true against Glue
HTTP 400  PurgeRequested cannot be true for Glue iceberg tables.
$ # DELETE .../tables/{table} against S3 Tables
HTTP 400  DropTable operation failed. S3 Tables only supports dropping tables with purge enabled.
```

This is worth knowing when writing a client, but it is the weakest result here:
these are separate products with different storage models, and a client configures
a catalog once rather than swapping between them. I mention it because it is
measured, not because it is important.

## Summary

The goal of this article was to measure what seven Iceberg REST catalog
implementations actually serve, rather than what their documentation claims. The
key to the solution was probing the `endpoints` array each catalog publishes about
itself and comparing it against behaviour on the same request suite. The
conformance results were:

- **Eleven overclaims across four vendors.** Endpoints a catalog names in its own
  `/v1/config` and then does not serve. Only the open-source control, Apache
  Polaris, declares honestly.
- **Two of seven publish no declaration at all.** Glue and S3 Tables leave a
  client no way to discover their surface short of probing it.
- **Views are effectively a Polaris-only feature.** Six operations, six managed
  catalogs, zero implementations.
- **"Supports the REST catalog" is true and not very informative.** All seven
  served the core read path. The divergence is in the write surface, in the update
  actions inside one endpoint, and in operational semantics.
- **`loadTable` fidelity is not a differentiator.** Twenty-four of thirty checked
  field paths are identical everywhere.

Scope: seven catalogs, each probed once in a single region on 2026-09-03 against
one table shape, covering 25 of the specification's 35 operations, 5 of 25 update
actions and 1 of 8 table requirements; Polaris pinned to 1.7.0 locally with
non-default permissive flags, BigLake in us-central1, Glue and S3 Tables in
us-east-1, Unity in us-west-2, Horizon on AWS us-east-1 and OneLake in East US 2;
Unity, Horizon and OneLake on trial accounts, which is a genuine confound because
one Horizon refusal is worded "not allowed for Horizon accounts"; the six managed
catalogs expose no version, so no result can be tied to a release; fixtures are
identical on five of the seven, with the other two differing because those
catalogs refuse part of the seed; and the field tier checks that a value is
present, never that it is correct.

The strategy for using a single request suite across seven vendor catalogs was
validated with an incremental step by step approach.

Any opinions in this article are those of the individual author and may not reflect the opinions of AWS.
