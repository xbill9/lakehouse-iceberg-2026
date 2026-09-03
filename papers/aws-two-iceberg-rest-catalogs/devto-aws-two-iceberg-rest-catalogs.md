---
title: "AWS Has Two Iceberg REST Catalogs: What Each One Actually Serves"
published: false
description: "Glue and S3 Tables both implement the Apache Iceberg REST catalog specification. One identical request suite against both shows the same totals and thirteen behavioural differences, including two that require opposite things of the same drop request."
tags: aws, iceberg, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/aws-two-iceberg-rest-catalogs/cover.aa8793f0.jpg
---

This article provides a step by step comparison of the two Apache Iceberg REST
catalog implementations AWS ships — AWS Glue and Amazon S3 Tables — measuring what
each one actually serves. A Python probe harness issues one identical request
suite to both and stores the raw response as evidence.

https://github.com/xbill9/lakehouse-iceberg-2026

AWS ships two Iceberg REST catalogs. Both are managed, both are SigV4-signed, and
both implement the same published specification. If you are choosing between them,
or writing a client that has to work against either, the interesting question is
where they diverge.

They score identically and behave differently in thirteen places.

All results below were measured on 2026-09-03.

## What Is the Iceberg REST Catalog?

An Iceberg table is a directory of Parquet files plus a chain of JSON metadata
files recording which files belong to the table right now. Something has to hold
the pointer to the current metadata file, and make commits atomic by swapping it.
That is the catalog.

The REST catalog is one HTTP API for that job, so an engine needs one driver
rather than one per catalog. The specification lives in the Iceberg repository as
`open-api/rest-catalog-open-api.yaml` and defines 35 operations.

```console
$ curl -sL https://raw.githubusercontent.com/apache/iceberg/main/open-api/rest-catalog-open-api.yaml -o irc.yaml
$ grep -cE '^    (get|post|delete|head|put):' irc.yaml
35
```

This harness probes 25 of those 35, or 71%.

## At This Point You Should Have

- An AWS account, and credentials with enough privilege to create a Glue database,
  an S3 bucket and an S3 Tables table bucket
- Python 3.13 with `requests`, `pyiceberg` and `botocore`
- `botocore` available for SigV4 signing

```console
$ aws sts get-caller-identity --query Arn --output text
arn:aws:iam::AWS_ACCOUNT_ID:root
$ python3 -c "
import sys, pyiceberg, requests, botocore
print('python    ', sys.version.split()[0])
print('pyiceberg ', pyiceberg.__version__)
print('requests  ', requests.__version__)
print('botocore  ', botocore.__version__)"
python     3.13.13
pyiceberg  0.12.0
requests   2.34.2
botocore   1.43.34
```

Everything below was measured with account root, so no result here is a
permissions artefact.

## Where Are the Two Endpoints?

They are different services with different signing names.

| | AWS Glue | Amazon S3 Tables |
|---|---|---|
| Endpoint | `https://glue.us-east-1.amazonaws.com/iceberg` | `https://s3tables.us-east-1.amazonaws.com/iceberg` |
| SigV4 signing name | `glue` | `s3tables` |
| Warehouse | the account id | the table bucket ARN |

```console
$ # GET /v1/config against Glue
{"defaults":{"header.Content-Type":"application/x-amz-json-1.1","rest.sigv4-enabled":"true",
 "rest-table-scan-enabled":"true","prefix":"AWS_ACCOUNT_ID","rest.signing-region":"us-east-1",
 "rest.signing-name":"glue", ...}}
```

## Signing Is Where the First Hour Goes

SigV4 signs the exact query string, so the URL you sign must be the URL you send.
Building the URL and then letting an HTTP client re-encode the parameters
separately produces a different canonical string:

```console
$ # signing one URL, sending another
HTTP 403
{"message":"The request signature we calculated does not match the signature you
provided. Check your AWS Secret Access Key and signing method."}
```

Build it once and send it whole. `urlencode`'s default `quote_plus` is also wrong
here, because SigV4 wants `%20` rather than `+`. With both fixed, the same request
reaches the service and returns a real answer:

```console
$ # same probe, correct canonical query string
HTTP 404
{"error":{"code":404,"message":"The specified bucket does not exist.","type":"no_such_bucket"}}
```

A 403 signature error and a 404 no-such-bucket look equally like failure in a log.
Only one of them is about the catalog.

## Bringing Up AWS Glue

```console
$ aws s3api create-bucket --bucket $BUCKET --region us-east-1
$ aws glue create-database --region us-east-1 \
    --database-input "{\"Name\":\"probe_ns\",\"LocationUri\":\"s3://$BUCKET/probe_ns/\"}"
$ aws glue get-databases --region us-east-1 --query 'DatabaseList[].Name' --output text
probe_ns
```

Glue rejects `createTable` without an explicit table location:

```console
$ # createTable with no location field
InvalidInputException: Location information cannot be null while creating an iceberg table
```

Every other catalog in this suite infers it from the warehouse. Glue does not.

## Bringing Up Amazon S3 Tables

```console
$ ARN=$(aws s3tables create-table-bucket --name iceberg-probe \
    --region us-east-1 --query arn --output text)
$ echo $ARN
arn:aws:s3tables:us-east-1:AWS_ACCOUNT_ID:bucket/iceberg-probe
$ aws s3tables create-namespace --table-bucket-arn "$ARN" \
    --namespace probe_ns --region us-east-1
{"tableBucketARN": "arn:aws:s3tables:us-east-1:AWS_ACCOUNT_ID:bucket/iceberg-probe",
 "namespace": ["probe_ns"]}
```

Two constraints surface only when you hit them. Namespace names reject uppercase,
which a timestamped scratch namespace will contain:

```console
$ # createNamespace named irc_probe_20260903T1626
HTTP 400
The specified namespace name isn't valid. Specify a different namespace name, and
then try again.
```

And `createTable` requires `stage-create` in the body:

```console
$ # createTable without it
HTTP 400  stage-create is a required field and cannot be null
```

Seeding a table also failed against the managed bucket with `pyiceberg`'s default
writer:

```console
$ # appending with the default PyArrow FileIO
AWS Error [code 134] during CreateMultipartUpload operation: The authorization
mechanism you have provided is not supported. Please use Signature Version 4.
```

Switching to `pyiceberg.io.fsspec.FsspecFileIO` worked. Note the bucket name in
that error is not the one you created — S3 Tables stores data in a managed bucket
of its own.

## The Prefixes Do Not Look Alike

Every client reads the routing prefix from `/v1/config` and puts it in every later
URL. The two services return very different shapes:

| Catalog | Prefix as returned |
|---|---|
| Glue | `catalogs/AWS_ACCOUNT_ID` |
| S3 Tables | `arn%3Aaws%3As3tables%3Aus-east-1%3A...%3Abucket%2Ficeberg-probe` |

Glue returns two path segments. S3 Tables returns a percent-encoded ARN. A client
that assumes one segment, or that re-encodes what it was handed, produces URLs
neither service routes.

## The Scores Are Identical

| | 🥈 AWS Glue | 🥈 Amazon S3 Tables |
|---|---|---|
| Read probes served | 9/15 | 9/15 |
| Write probes served | 10/17 | 10/17 |
| Not tested | 1 | 1 |
| `loadTable` fields present | 26/30 | 27/30 |
| Endpoints declared in `/v1/config` | none | none |

Read and write surfaces are scored separately rather than summed, and probes whose
prerequisite failed are excluded rather than counted as failures.

That table is the least interesting thing in this article. The two implementations
arrive at the same totals by different routes.

## Neither One Tells You What It Supports

The specification lets a server advertise its own surface:

> **endpoints**: A list of endpoints that the server supports.
>
> — `rest-catalog-open-api.yaml`, `CatalogConfig`

Five of the seven catalogs in the wider comparison publish that array. Neither AWS
catalog does:

```console
$ python3 -c "
import json
for c in ('aws-glue','aws-s3tables'):
    d = json.load(open('evidence/%s.json' % c))
    print('%-14s declares %s endpoints' % (c, len(d.get('declared_endpoints') or []) or 'no'))
"
aws-glue       declares no endpoints
aws-s3tables   declares no endpoints
```

The field is optional, so this is not a specification violation. It does mean
capability discovery is unavailable on both, and a client has no way to learn what
either serves short of probing it — which is what this harness does.

## Thirteen Probes Behave Differently

Of 33 probes, 20 return the same verdict on both and 13 do not.

| Probe | AWS Glue | Amazon S3 Tables |
|---|---|---|
| `list_views` | ❌ 406 not supported | ❌ 404 unknown operation |
| `create_view` | ❌ 406 not supported | ❌ 404 unknown operation |
| `load_view` | ❌ 406 not supported | ❌ 404 unknown operation |
| `replace_view` | ❌ 406 not supported | ❌ 404 unknown operation |
| `rename_view` | ❌ 406 not supported | ❌ 404 unknown operation |
| `drop_view` | ❌ 406 not supported | ❌ 404 unknown operation |
| `rename_table` | ❌ 406 not supported | ✅ 204 |
| `update_namespace_props` | ✅ 200 | ❌ 404 unknown operation |
| `plan_table_scan` | ⚠️ 200 with exception | ❌ 404 unknown operation |
| `report_metrics` | ⚠️ 200 with exception | ❌ 400 not supported |
| `commit_transaction` | ⚠️ 200 with exception | ❌ 404 unknown operation |
| `drop_table_purge` | ❌ 400 purge forbidden | ✅ 204 |
| `drop_table` | ✅ 204 | ❌ 400 purge required |

Neither implements views, but they refuse differently, and one of them renames
tables while the other does not.

## Glue Names the Operation It Is Refusing

Glue's refusals are specific, and they name the endpoint:

```console
$ # POST .../views against Glue
HTTP 406  CreateView endpoint is not supported for Glue Catalog.
$ # POST .../tables/rename against Glue
HTTP 406  RenameTable endpoint is not supported for Glue Catalog.
```

S3 Tables returns a bare XML document with no operation name and no JSON error
body:

```console
$ # POST .../views against S3 Tables
HTTP 404  <UnknownOperationException/>
```

Both mean the same thing to a user and not to a program. Glue's `406` with a named
operation is machine-readable enough to log usefully; the bare exception is not.

The exception to S3 Tables' silence is `report_metrics`, which is the one place it
says what it means:

```console
$ # POST .../tables/{table}/metrics against S3 Tables
HTTP 400  ReportMetrics is currently not supported.
```

## Glue Answers Three Unrouted Operations With HTTP 200

This is the finding a client author should care about most.

```console
$ # POST .../tables/{table}/plan against Glue
HTTP 200
{"Output": {"__type": "com.amazon.coral.service#UnknownOperationException"}, "Version": "1.0"}
```

The same body comes back from `report_metrics` and `commit_transaction`. The
mechanism is the AWS protocol layer answering an operation its front door does not
route, rather than Glue returning a broken success for an implemented endpoint.

The consequence does not depend on the mechanism. Code that branches on the status
code sees three endpoints that work, and only code that parses the body finds out
otherwise. The harness gives these their own verdict rather than scoring them
`OK`.

Glue's `/v1/config` also advertises `rest-table-scan-enabled: true`, and scan
planning is one of the three.

## The Drop Requirements Are Opposite

Glue refuses a purge drop. S3 Tables refuses a plain one.

```console
$ # DELETE .../tables/{table}?purgeRequested=true against Glue
HTTP 400  PurgeRequested cannot be true for Glue iceberg tables.

$ # DELETE .../tables/{table} against S3 Tables
HTTP 400  DropTable operation failed. S3 Tables only supports dropping tables with
purge enabled.
```

The two products have different storage models, so this is defensible rather than
a defect — Glue points at a bucket you own, and S3 Tables owns the storage it
drops. It is still the sharpest example of why "AWS supports the Iceberg REST
catalog" is not a sentence a client can act on.

## Neither Supports Multi-Level Namespaces

Both reject the `parent` query parameter on `listNamespaces`, and both say so
plainly:

```console
$ # GET .../namespaces?parent=probe_ns against Glue
HTTP 400  Glue dataCatalog does not support multipart namespace.
$ # the same against S3 Tables
HTTP 400  Multipart namespaces are not supported.
```

## Where They Agree

Twenty of the 33 probes return the same verdict, and the agreement is the core of
the specification. Both serve config, namespace listing and loading, table listing
and loading, `loadTable` with full snapshot history, and both accept all five
`updateTable` actions probed — `set-properties`, `remove-properties`,
`add-schema`, `set-current-schema` and `upgrade-format-version`.

Both also return nearly identical `loadTable` documents: 26 of 30 checked
specification field paths on Glue, 27 on S3 Tables. The single extra on S3 Tables
is a `config` block. Whatever separates these two, it is not the fidelity of the
metadata they return.

## Summary

The goal of this article was to measure what AWS's two Iceberg REST catalog
implementations actually serve, rather than what "supports the REST catalog"
implies. The key to the solution was issuing one identical request suite to both
and storing the raw response for every probe. The comparison results were:

- **Identical totals, thirteen behavioural differences.** Both serve 9 of 15 read
  probes and 10 of 17 write probes, and 20 of 33 probes agree.
- **Neither publishes an `endpoints` declaration**, so capability discovery is
  unavailable on both and a client must probe.
- **Glue answers three unrouted operations with HTTP 200** carrying an
  `UnknownOperationException`, one of which is the scan planning its own config
  advertises as enabled.
- **Neither implements views**, and they refuse differently — Glue with a `406`
  naming the operation, S3 Tables with a bare `<UnknownOperationException/>`.
- **The drop requirements are opposite.** Glue forbids `purgeRequested=true`, S3
  Tables requires it.
- **`rename_table` works on S3 Tables and not on Glue.**

Scope: both catalogs probed once in us-east-1 on 2026-09-03 with account root,
against one table shape seeded through pyiceberg 0.12.0, covering 25 of the
specification's 35 operations, 5 of its 25 update actions and 1 of its 8 table
requirements; neither service exposes a version, so no result here can be tied to
a release; and the field tier records that a value is present, never that it is
correct.

The strategy for comparing two managed catalogs against one specification was
validated with an incremental step by step approach.
