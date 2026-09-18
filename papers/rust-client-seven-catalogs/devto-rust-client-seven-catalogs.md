---
title: "What One Rust Client Can Reach Across Seven Iceberg Catalogs"
published: false
description: "Running iceberg-catalog-rest 0.10.1 against the same 33-probe suite used on seven Iceberg REST catalogs: 13 of 25 endpoints are expressible, three catalogs answer every probe it can send, two refuse every probe once a SigV4 signature is carried as a header, and a working setup needs a TLS backend and a storage crate the client does not pull in."
tags: rust, iceberg, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/rust-client-seven-catalogs/cover.a8b2a39d.jpg
---

This article provides a step by step comparison of what a Rust Iceberg client can
reach, measured against the same probe suite used earlier on seven Apache Iceberg
REST catalogs. A Python harness drives a small Rust binary, merges the result
against a hand-read map of the client's own source, and stores every verdict as
evidence.

https://github.com/xbill9/lakehouse-iceberg-2026

An earlier article measured what seven Iceberg REST catalogs serve. This one
turns the question around and asks what a *client* can ask for. The two are not
the same question, and the gap between them is where a portable tool either works
or quietly cannot be written.

All results below were measured on 2026-09-17 and 2026-09-18 against
`iceberg-catalog-rest` 0.10.1, `iceberg` 0.10.1, `iceberg-storage-opendal`
0.10.1 and Apache Polaris 1.7.0, and against the managed catalogs named in each
section.

**Nothing here is about the Rust client being broken.** It is a young library
that implements what the REST specification describes, and everything it can
express worked on every catalog it could authenticate to, 7 probes of 7 on each. Nor is this a comparison
with any other client; where `pyiceberg` appears, it is only as a second opinion
on whether a refusal belongs to the client or to the catalog.

**One scope statement up front, because it changes how every table below should
be read.** Five of the seven catalogs were run: the control, Google BigLake and
Microsoft OneLake through the client's read probes, and AWS Glue and S3 Tables
through a demonstration of why they refuse it. Databricks Unity and Snowflake
Horizon were not run — their configuration in this repository still holds
placeholder values — and every row about them is read from the client's source.

## What Is This Project Trying to Do?

The Iceberg REST catalog specification is a protocol, and a protocol is only as
portable as its clients. Seven vendors serve it. The question a reader actually
has, before any comparison is interesting, is whether a tool written in Rust
today can talk to the catalog they are already paying for.

That question splits into three that can be answered separately:

- Which operations does the client have a method for at all?
- Can it authenticate to each catalog?
- Once it has a table, can it read it?

The interesting part is that these fail in different places and for different
reasons. The third one is not about Iceberg at all.

## What Does "Reach" Mean Here?

The earlier article's suite is 33 probes covering 25 of the specification's 35
operations. Reusing it exactly is what makes the two articles comparable rather
than merely adjacent: the server side of every cell is already measured, so a
cell that fails here is a client difference.

A probe can fail to run for reasons that are not failures, and conflating them
was the first bug in this harness. Four verdicts, and they mean different things:

| verdict | meaning |
|---|---|
| `OK` | the client issued the probe's request and got a value back |
| `IMPLICIT` | the request is issued by the client itself, not on a caller's behalf |
| `NOT-EXPRESSIBLE` | there is no method and no endpoint builder — no request to send |
| `NOT-ISSUED` | the client can express it; this read-only runner did not send it |

The first version of the driver reported both of the last two as
`NOT-EXPRESSIBLE`. That counted eleven writes the crate can perform as writes it
cannot, which is a striking and entirely false sentence. They are counted apart
now.

## At This Point You Should Have

- Rust 1.94 or newer and `cargo`
- Docker, for the control catalog
- Python 3.10+ with `pyiceberg` 0.12.0 and `pyyaml`
- A clone of the repository above
- Optional: credentials for a managed Iceberg REST catalog. Everything up to the
  vendor runs needs only the control catalog, which runs locally and costs
  nothing.

## Bringing Up the Control Catalog

Every result starts against Apache Polaris, configured permissively on purpose.
A red cell there is this harness's bug until proven otherwise — a rule that has
earned its place repeatedly.

```console
$ cd iceberg-conformance
$ ./polaris-up.sh
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
```

```console
$ cd ../iceberg-rust-client
$ cargo build --release
    Finished `release` profile [optimized] target(s) in 1m 41s
```

## Reading the Client Instead of Its Documentation

The map from probe to client method is hand-read from the published crate source,
one entry per probe, each carrying the file and line it came from. No entry is
inferred from documentation.

A hand-read line number rots silently, so it is checked:

```console
$ python3 check_refs.py
rust       iceberg-catalog-rest 0.10.1    25 refs, 25 symbol refs resolved  [catalog.rs 50a770995fbf]
pyiceberg  pyiceberg 0.12.0               60 refs, 33 symbol refs resolved  [__init__.py 2a2976d888c4]
ok  every cited line is inside the symbol it is cited for
```

That resolves all 85 cited lines against the installed source and fails if one no
longer sits inside the function it names. It cannot check that the reading was
right. It checks that the reading still points where it pointed, which is the
part that breaks on a version bump.

## Thirteen of Twenty-Five Endpoints Are Expressible

Counted by endpoint signature rather than by probe, because five probes share
`update_table`:

```console
$ python3 make_surface.py
wrote evidence/rust-client-operation-surface.txt   33 probes
```

    13 of 25 distinct endpoints are expressible through this client.
    Counted per probe the figure is 19 of 33, which is the same fact
    weighted by how many probes happened to point at one endpoint.

## The Twelve That Are Not Divide Into Three Kinds

Collapsing them into one number would hide the only interesting distinction.

- **Absent — 11 endpoints.** All six view operations, scan planning, metrics
  reporting, the separate credentials endpoint, and `commitTransaction`. There is
  no method and no endpoint builder that could construct the URL. Confirmed by
  grep as well as by reading: `views`, `/plan`, `metrics` and
  `transactions/commit` have zero hits in the crate's source.
- **Unsupported — 1 endpoint.** `Catalog::update_namespace` compiles, is part of
  the trait a caller builds against, and returns an error instead of a request:
  `FeatureUnsupported, "Updating namespace not supported yet!"` (`catalog.rs:659`).
  It is the client-side echo of a catalog declaring an endpoint it does not serve.
- **Degraded — 2 probes on reachable endpoints.** `load_table` builds its request
  with no query parameters, so `?snapshots=all` cannot be asked for, and
  `list_namespaces` follows `next-page-token` internally and never sends
  `pageSize`. The endpoint is reachable; the probe's question is not expressible.

A probe that cannot be issued is not a failed probe, and is never scored as one.

## Two Catalogs Need a Signature the Client Cannot Make

The crate supports a bearer `token`, OAuth2 `credential` with
`oauth2-server-uri` and `scope`, and static `header.<name>` values. Its
dependency list contains no AWS SDK and no signing crate.

A SigV4 signature is computed per request over the canonical request, so a static
header cannot carry one. The earlier article measured Glue and S3 Tables as
SigV4-signed.

| auth | catalogs | through this client |
|---|---|---|
| oauth2 | Polaris | native |
| bearer from env | Unity | native |
| keypair-signed JWT | Horizon | native: a `credential` with no colon is sent as `client_secret` with no `client_id` (`catalog.rs:238`), which is the shape Horizon wants |
| gcloud ADC, Azure CLI | BigLake, OneLake | a bearer minted outside the crate, which the crate cannot refresh — `regenerate_token()` re-runs an OAuth2 grant, which is not how that token was obtained |
| SigV4 | Glue, S3 Tables | **absent** |

**This is known upstream, and it is not a discovery here.**
`apache/iceberg-rust` issue #1236, *"REST catalog: support AWS sigV4"*, is open
and asks for `rest.sigv4-enabled`, `rest.signing-name` and `rest.signing-region`
— the same three properties `pyiceberg` already implements. Discussion #1239 is a
user hitting it as a 403 `Missing Authentication Token` against S3 Tables.

**And it does not mean a Rust caller cannot reach those two catalogs.** The same
Apache project ships `iceberg-catalog-glue` and `iceberg-catalog-s3tables`, both
at 0.10.1, which talk to the AWS APIs directly. What is unreachable is Glue and
S3 Tables *through the REST protocol*.

That is a claim about protocol uniformity rather than capability, and it is worth
stating precisely. The promise of a REST catalog is one protocol and one client
for every vendor. In Rust today that promise does not hold for AWS: a tool that
covers all seven writes against three different catalog clients. In Python it
holds, because `rest.sigv4-enabled` lives in the same client as everything else.

## What Happens When a Signature Is Passed as a Header?

The source says a static header cannot carry a per-request signature. The run
checks that on the wire, because a claim about a mechanism should survive
contact with the endpoint.

The harness signs the one request the crate sends first — `GET /v1/config` with
its `warehouse` query and the two headers the crate adds — and hands the result to
the crate as `header.Authorization`, `header.X-Amz-Date` and
`header.X-Amz-Security-Token`. The crate attaches them unchanged to every request.

```console
$ python3 run_rust.py --only aws-glue --only aws-s3tables --sigv4-demo --storage opendal
$ python3 vendor_report.py
wrote evidence/rust-vendor-runs.txt
```

From `rust-vendor-runs.txt`:

    aws-glue
      through the crate: 7 of 7 issued probes refused with InvalidSignatureException, 0 succeeded
      replay, GET /v1/config (the signed request): 200
      replay, GET /v1/{prefix}/namespaces (same headers): 403

    aws-s3tables
      through the crate: 7 of 7 issued probes refused with InvalidSignatureException, 0 succeeded
      replay, GET /v1/config (the signed request): 200
      replay, GET /v1/{prefix}/namespaces (same headers): 403

The replay is the control. The crate's config fetch is implicit and cannot be
observed on its own, so the same headers are sent again from outside the crate, to
the request they were computed for and then to the next one. The signature is
good for exactly one request. Both services word the refusal identically:

    The request signature we calculated does not match the signature you provided.
    Check your AWS Secret Access Key and signing method.

That is the expected consequence of #1236, not a new result. What it adds is
that the crate's static-header mechanism, the one general-purpose way to hand it
a credential it does not model, cannot stand in for a signer.

## The First Vendor Run Failed Before Any HTTP Status

The control catalog is `http://` on loopback. The first run against BigLake and
OneLake failed 7 of 7 probes on both, identically. That run's files were not
kept, so the failure was reproduced for the evidence with a binary built the same
way, into a separate target directory:

```console
$ IRC_BINARY=<no-tls build> python3 run_rust.py --only google-lakehouse \
      --only microsoft-onelake --storage opendal --tag no-tls
google-lakehouse   7 failed, 1 implicit, 14 not-expressible, 11 not-issued
microsoft-onelake  7 failed, 1 implicit, 14 not-expressible, 11 not-issued
```

    Unexpected => Failed to execute http request, source: error sending request
    for url (<uri>/v1/config?warehouse=<warehouse>)

No status code: the request never completed. `iceberg-catalog-rest` 0.10.1
declares `reqwest` with `default-features = false` and the single feature `json`,
and declares no cargo features of its own. No TLS backend is compiled in unless
the caller names one:

```toml
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls"] }
```

That line in the caller's own manifest is the whole fix. Cargo unifies features
across the dependency graph, so the client picks up a TLS backend it does not
declare. With it, both vendors answered every probe.

**This is also known upstream.** `apache/iceberg-rust` issue #2888, *"Add TLS
features to iceberg-catalog-rest"*, is open, describes the same failure against
another catalog, and names the same workaround: *"a very implicit and brittle
solution."* The point here is only where it lands for a reader: every managed
catalog is `https://`, so a caller whose dependency graph does not already enable
a `reqwest` TLS feature meets this on the first vendor request.

## Loading a Table Needs a Second Crate

`load_table` returns a `Table`, a `Table` carries a `FileIO`, and the client will
not hand back a `loadTable` response without storage wiring. The first control
run failed on exactly that:

```console
StorageFactory must be provided for RestCatalog.
Use `with_storage_factory` to configure it.
```

The HTTP round trip had already succeeded when the client refused. `iceberg`
0.10.1 ships exactly two `StorageFactory` implementations — `LocalFsStorageFactory`
(`io/storage/local_fs.rs:330`) and `MemoryStorageFactory` (`io/storage/memory.rs:250`)
— and has no cargo features at all.

The tempting reading is that a caller has to implement cloud storage themselves.
That reading is wrong, and the crate says so in its own README at line 70: *"For
storage backend support (S3, GCS, local filesystem, etc.), use the
`iceberg-storage-opendal` crate."* The cloud config structs left in core —
`S3Config`, `GcsConfig`, `AzdlsConfig` — are the seam that crate plugs into.

**It was a real bug here, though, and it would have read as a vendor finding.**
This harness pinned `iceberg` with no storage crate. Table locations, read from
the earlier article's stored `loadTable` responses, are `file://` on the control
and `s3://`, `gs://` or `abfss://` everywhere else. Four of the catalogs this
client can otherwise reach are cloud-backed, so a vendor run would have produced
four red `load_table` cells caused by a dependency list and nothing else.

`IRC_STORAGE` is therefore a recorded property of every run, never a silent
default.

## What the Runs Say

Control first, then the two vendors whose auth the client can carry, all with
`--storage opendal`:

```console
$ python3 run_rust.py --storage opendal
apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-apache-polaris.json
$ python3 run_rust.py --only google-lakehouse --only microsoft-onelake --storage opendal
google-lakehouse   1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-google-lakehouse.json
microsoft-onelake  1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-microsoft-onelake.json
```

| catalog | auth through the crate | ok | failed | not issued | not expressible |
|---|---|---|---|---|---|
| Apache Polaris | native OAuth2 | 7 | 0 | 11 | 14 |
| Google BigLake | static bearer | 7 | 0 | 11 | 14 |
| Microsoft OneLake | static bearer | 7 | 0 | 11 | 14 |
| AWS Glue | none — SigV4 | 0 | 7 | — | — |
| AWS S3 Tables | none — SigV4 | 0 | 7 | — | — |
| Databricks Unity | native token | not run | | | |
| Snowflake Horizon | native, bare secret | not run | | | |

The three catalogs run through the read probes are identical, and that is the
finding: on every catalog it can authenticate to, everything this client can
express works. `IMPLICIT`, one
per catalog, is the config fetch.

The BigLake and OneLake tokens were minted outside the crate by `gcloud` and
`az`. Each run finished well inside the token's lifetime, so what happens at
expiry, when the crate's `regenerate_token()` attempts an OAuth2 grant these
tokens did not come from, was not exercised.

## Does the Client Read the Table's Files?

A green `load_table` says nothing about storage. The client builds a `FileIO`
and hands it back without using it. So each run makes one more read: the table's
current metadata file, through the client's own `FileIO`, recording the byte
count and the names — never the values — of the configuration keys the storage
layer was handed.

From `rust-vendor-runs.txt`:

    apache-polaris
      storage credential keys among them: none
      read: ok, scheme file, 5614 bytes, 21 ms
    google-lakehouse
      storage credential keys among them: none
      read: ok, scheme gs, 5497 bytes, 451 ms
    microsoft-onelake
      storage credential keys among them: none
      read: FAILED after 47066 ms
      error: Unexpected => Failure in doing io operation, source: Unexpected
      (persistent) at read, context: { timeout: 10 } => io timeout reached

None of the three carried a storage credential key. The crate sends no
`X-Iceberg-Access-Delegation` header, so no catalog was asked to vend one and
none did. The keys it did carry are the catalog's own properties, merged in
by the crate (`catalog.rs:455`).

So the storage layer finds credentials for itself, and this is where the two
clouds part. With no `gcs.*` key, the GCS backend fell back to the machine's
application-default credentials and read the file. The Azure backend has no
equivalent path for a caller signed in with `az login`, and the reason is in
its source rather than in OneLake:

- `opendal-service-azdls` 0.57.0 builds its signer's context with no command
  executor (`backend.rs:297`). The credential chain it uses does include an Azure
  CLI provider, but that provider works by running `az`, and a no-op executor
  cannot run it.
- The same context's environment is built only from `adls.*` properties, not from
  the process environment, so `AZURE_CLIENT_ID` and friends are not seen either.
- What remains is an account key, a SAS token or a service-principal secret, as
  `adls.*` properties. OneLake has no account key, and this test bed has no
  service principal.

The timeout is consistent with the chain falling through to the instance metadata
endpoint on a machine that is not an Azure VM. That last step was not traced. A
search of `apache/opendal` issues on 2026-09-18 found no report of the missing
executor. It is written here as a reading of the source, not as a confirmed
defect.

**Asking the catalog for a credential does not help either.** OneLake does vend
one: the same `loadTable` from `pyiceberg`, which sends
`X-Iceberg-Access-Delegation: vended-credentials` by default, comes back with one
`storage-credentials` entry. The Rust crate never sends that header, but it can
be made to, as a static `header.*` property:

```console
$ python3 run_rust.py --only microsoft-onelake --storage opendal \
      --access-delegation vended-credentials
microsoft-onelake  1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-microsoft-onelake-delegation.json
```

The storage read still timed out after 47181 ms, and the FileIO still carried no
`adls.*` key. The crate deserializes `storage_credentials` into its response type
(`types.rs:226`) and nothing reads the field. `load_file_io` merges the
response's `config` map and nothing else (`catalog.rs:455`), so a vended
credential arrives and is dropped.

This is also being worked on upstream, and is not reported here as news.
`apache/iceberg-rust` #2931, open, tracks vended storage credentials across the
REST catalog, `FileIO` and the storage backends. #1442, open, tracks the
`adls.sas-token.<filesystem>.dfs.<suffix>` key format that ADLS vending uses. What
the run adds is only where 0.10.1 stands today.

Reading OneLake's files from this client therefore needs a service principal, or
a SAS token minted outside it. The catalog half works; the storage half needs a
credential the storage crate can use.

## One Client Asks the Catalog for Permission, the Other Does Not

Worth one section, because it is the only client-side behaviour with no Rust
equivalent, and because its size is smaller than its mechanism suggests.

`pyiceberg` compares every endpoint against the `endpoints` array from
`GET /v1/config` before sending anything. The Rust crate has no such check — its
config type has no `endpoints` field at all, so it cannot see the declaration
even in principle.

Joining that against the earlier article's declaration data for all seven
catalogs:

    2 working endpoints blocked across the seven, both of them loadCredentials
    4 more answered by a substituted request, all HEADs on the two AWS catalogs
    3 of the seven untouched by the gate
    0 of the blocked cases are ones the Rust crate could have sent

The mechanism is real and the cost here is nearly nothing, and both halves belong
in the same paragraph. What makes it small is that the endpoints these catalogs
underclaim are mostly ones neither client can use.

## What This Does Not Cover

- **Unity and Horizon were not run.** Their rows are read from the client's
  source. Whether Horizon accepts the crate's bare-`client_secret` grant is the
  most interesting open question here, and it is a measurement, not an
  inference.
- **No write has been issued.** Eleven probes are `NOT-ISSUED` rather than
  measured.
- **Token expiry was not exercised.** Every run finished inside a minted token's
  lifetime.
- **OneLake storage was not reached.** No service principal was available to try
  the path the storage crate supports.
- **Presence is checked, not correctness.** A reached endpoint is not a correct
  endpoint.

## Summary

The goal of this article was to measure what a Rust Iceberg REST client can reach
across the same seven catalogs an earlier article measured from the server side.
The key to the solution was reading the client's own source into a probe map with
a file and line behind every entry, then proving the map still points where it
claims. The client results were:

- **13 of 25 endpoints are expressible**, and the twelve that are not divide into
  absent, unsupported and degraded — three different problems for a caller.
- **Every probe it can express worked on all three catalogs it could
  authenticate to** — Polaris, BigLake and OneLake, 7 OK and 0 failed each.
- **Two of seven catalogs are unreachable through this client**, because it ships
  no request signer. A signature passed as a header got 200 on the one request it
  was computed for and 403 on the next, on both. Both catalogs are reachable in
  Rust through separate AWS-specific crates, so the finding is about protocol
  uniformity, not capability.
- **Two dependencies the client does not declare**: a TLS backend, without which
  no `https://` catalog answers (upstream #2888), and `iceberg-storage-opendal`,
  without which no cloud-backed table loads.
- **Storage credentials are the caller's problem**, not the catalog's: the crate
  asks for none and drops any it is sent, GCS read through application-default
  credentials, and the Azure backend has no path for an `az login` user.
- **A client-side declaration gate costs almost nothing.** Two blocked endpoints
  across seven catalogs, both `loadCredentials`, neither reachable from the Rust
  client anyway.

Scope: one client at `iceberg-catalog-rest` 0.10.1 with `iceberg` 0.10.1,
`iceberg-storage-opendal` 0.10.1 and `reqwest` 0.12.28 with `rustls-tls`, source
read and control run on 2026-09-17, vendor runs on 2026-09-18; Apache Polaris
1.7.0 locally under Docker with non-default permissive flags and `file://`
storage; Google BigLake and Microsoft OneLake, one run each from one machine in
one region; AWS Glue and S3 Tables through the SigV4 demonstration only;
Databricks Unity and Snowflake Horizon not run, their rows read from source; 33
probes covering 25 of the specification's 35 operations, read-only, so eleven
write probes were not issued; three of the seven catalogs were measured on trial
accounts in the earlier article; managed catalogs expose no version, so no result
can be tied to a release.

The strategy for measuring an Iceberg REST client against a fixed probe suite was
validated with an incremental step by step approach.
