---
title: "What One Rust Client Can Reach Across Seven Iceberg Catalogs"
published: false
description: "Step by step: the Apache Rust Iceberg REST client against seven Iceberg catalogs. It supports 13 of 25 endpoints, answers every supported read on Polaris, BigLake and OneLake, reads table files on Polaris and BigLake, cannot log in to the two AWS catalogs, and needs a TLS library and a storage crate added by hand."
tags: rust, iceberg, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/rust-client-seven-catalogs/cover.fd3f64f1.jpg
---

This article provides a step by step guide to pointing the Apache Rust client for Iceberg REST catalogs at seven catalogs and recording what works. A Python script runs a small Rust program against each catalog and saves every result.

https://github.com/xbill9/lakehouse-iceberg-2026

---

#### What is this project trying to Do?

An earlier article tested what seven Iceberg REST catalogs support. This one asks the question from the other side: if you write a lakehouse tool in Rust today, will it work with the catalog you already pay for, and what do you need to set up?

The client is `iceberg-catalog-rest` 0.10.1 from the Apache Iceberg project. The catalogs, tests and test table are the same as in the earlier article:

- **Apache Polaris** 1.7.0, running locally as the reference
- **Google BigLake** and **Microsoft OneLake**, over the internet
- **AWS Glue** and **AWS S3 Tables**, over the internet
- **Databricks Unity** and **Snowflake Horizon**, not run here

Three questions, and each one fails in a different place: which operations the client supports, whether it can log in, and whether it can read the table's files. The third depends on the storage library and on how each cloud handles logins.

On every catalog the client could log in to, every operation it supports worked.

---

#### What Does Each Result Mean?

The test suite is 33 checks covering 25 of the 35 operations in the Iceberg REST specification. Each check gets one of five results:

| result | meaning |
|---|---|
| `OK` | the client sent the request and got an answer |
| `FAILED` | the client sent the request and got an error |
| `IMPLICIT` | the client sends this request on its own, and there is no way to call it directly |
| `NOT-EXPRESSIBLE` | the client has no method for this operation |
| `NOT-ISSUED` | the client supports it, but it is a write, and this test only reads |

---

#### Where do I start?

The strategy for testing the client is an incremental step by step approach.

First, a local Polaris catalog is started and the client's source code is checked to list which operations it supports. Then the test program is built and run against Polaris. The same program then runs against the managed catalogs, one login method at a time, and finally tries to read a table's files.

---

#### At This Point You Should Have…

- Rust 1.94 or newer and `cargo` — this run used `rustc` 1.98.1
- Docker, for the local Polaris catalog
- Python 3.10+ with `pyyaml`, for the test scripts
- Optional: logins for any managed catalog — `gcloud` for BigLake, `az` for OneLake, the AWS CLI for Glue and S3 Tables

---

#### Step 1 — Start Polaris

Polaris runs locally with permissive settings. Anything that fails here is a problem in the test scripts, so it is fixed before any cloud catalog is tested:

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-conformance
$ ./polaris-up.sh
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
```

---

#### Step 2 — Build the Test Program

The versions are pinned exactly, so every result applies to one release:

```toml
iceberg = "=0.10.1"
iceberg-catalog-rest = "=0.10.1"
iceberg-storage-opendal = { version = "=0.10.1", features = ["opendal-gcs", "opendal-azdls"] }
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls"] }
```

The last two lines add things the client needs but does not bring with it. The two tips after Step 7 explain each one.

```console
$ cd ../iceberg-rust-client
$ cargo build --release
    Finished `release` profile [optimized] target(s) in 1m 41s
```

---

#### Step 3 — List What the Client Supports

Each of the 33 checks is matched to a method in the client's published source code, with the file and line number. A script confirms every line in that map still points at the function it names:

```console
$ python3 check_refs.py
rust       iceberg-catalog-rest 0.10.1    25 refs, 25 symbol refs resolved  [catalog.rs 50a770995fbf]
pyiceberg  pyiceberg 0.12.0               60 refs, 33 symbol refs resolved  [__init__.py 2a2976d888c4]
ok  every cited line is inside the symbol it is cited for
```

Counting each endpoint once, since five checks use the same `update_table` endpoint:

```console
$ python3 make_surface.py
wrote evidence/rust-client-operation-surface.txt   33 probes
```

```plaintext
13 of 25 distinct endpoints are expressible through this client.
Counted per probe the figure is 19 of 33, which is the same fact
weighted by how many probes paper 1 happened to point at one endpoint.
```

The 12 endpoints it cannot reach split two ways:

- **Missing — 11 endpoints.** All seven view operations, scan planning, metrics reporting, the separate credentials endpoint, and `commitTransaction`. The words `views`, `/plan`, `metrics` and `transactions/commit` do not appear anywhere in the client's source.
- **Stubbed — 1 endpoint.** `Catalog::update_namespace` exists, but returns the error `"Updating namespace not supported yet!"` (`catalog.rs:659`) and sends nothing.

Two endpoints it does reach, it reaches only in part, and both are counted among the 13: `load_table` cannot ask for `?snapshots=all`, and `list_namespaces` handles paging internally and never sends `pageSize`. The line numbers quoted from here on were read by hand and are archived, with the lines themselves, in `evidence/rust-source-citations.txt`.

The client also reaches `registerTable`, which is one of the ten operations the earlier article did not cover, so it sits outside this count of 25.

---

#### Step 4 — Run It Against Polaris

```console
$ python3 run_rust.py --storage opendal
apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-apache-polaris.json
```

All 7 supported read operations work. The one `IMPLICIT` result is the config request the client sends when it first connects.

---

#### Step 5 — Issue the Write Endpoints

The run above leaves eleven endpoints untried. The client has a method for each of them, and a read-only program sends none of them, which are two separate statements: a method that compiles can still fail on the wire. Polaris is local, permissive and disposable, so the writes run there and on no other catalog. Every request goes through a small logging proxy, so what the client put on the wire is recorded beside what came back.

```console
$ python3 run_writes.py
apache-polaris     11 ok, 1 unsupported, 0 failed
wrote evidence/rust-write-surface.txt   22 request(s)
```

```plaintext
  probe                          verdict      ms     endpoint
  create_namespace               OK           60     reachable
  update_namespace_props         UNSUPPORTED  0      unsupported
  create_table                   OK           64     reachable
  commit_table                   OK           112    reachable
  commit_remove_properties       OK           119    reachable
  commit_add_schema              OK           116    reachable
  commit_set_current_schema      OK           116    reachable
  commit_upgrade_format_version  OK           99     reachable
  rename_table                   OK           3      reachable
  drop_table_purge               OK           16     reachable
  drop_table                     OK           3      reachable
  drop_namespace                 OK           1      reachable
```

All eleven work. The scratch namespace is dropped at the end and a `HEAD` on it afterwards returns 404.

The refusal is the stub from Step 3, and the proxy log shows why it takes 0 ms: there is no `POST` to the properties endpoint anywhere in the run. The method returns `FeatureUnsupported` before building a URL.

---

#### 🔎 Tip: What the Proxy Log Shows

Four things about this client are visible in the requests and not in its documentation.

**A table commit costs two requests.** Each commit re-reads the table first, so one property change is a `GET` and then a `POST`:

```plaintext
  GET     200  /v1/quickstart_catalog/namespaces/irc_probe_rust_1790009108/tables/t1
  POST    200  /v1/quickstart_catalog/namespaces/irc_probe_rust_1790009108/tables/t1
          updates: set-properties, remove-properties
```

**A properties commit always sends both update kinds.** Setting a property and removing one produce the same pair, `set-properties` and `remove-properties`, because the crate's properties action builds both every time (`update_properties.rs:95`). The two differ in their contents.

**Adding a column is one request carrying two updates.** The schema action sends `add-schema` and `set-current-schema` together, with `assert-current-schema-id` as the requirement:

```plaintext
  POST    200  /v1/quickstart_catalog/namespaces/irc_probe_rust_1790009108/tables/t1
          updates: add-schema, set-current-schema
          requirements: assert-current-schema-id
```

**The format version you ask for in `TableCreation` is dropped.** `CreateTableRequest` has no field for it (`types.rs:250`), so the create body is `name`, `schema` and `stage-create`, and the catalog's default decides. A table created as V1 came back V2. Setting it as a table property works:

```plaintext
  POST    200  /v1/quickstart_catalog/namespaces/irc_probe_rust_1790009108/tables
          body fields: name, properties, schema, stage-create
```

```plaintext
  _create_table_format_version_property {"asked_for": "V1 in TableCreation and in the format-version property", "format_version": "V1"}
```

One more, for anyone building a client: a two-level namespace goes out with the unit separator the specification asks for, as `.../namespaces/irc_probe_rust_1790009108%1Fchild`, and Polaris created, loaded and dropped it through the client.

---

#### Step 6 — Match the Login to Each Catalog

The client can log in with a token, with an OAuth2 client ID and secret, or with fixed extra headers. It has no AWS request signing.

| login | catalogs | with this client |
|---|---|---|
| OAuth2 | Polaris | built in |
| token from an environment variable | Unity | built in |
| key-pair JWT | Horizon | built in: a `credential` with no colon is sent as `client_secret` with no `client_id` (`catalog.rs:238`), which is what Horizon expects |
| `gcloud` or `az` login | BigLake, OneLake | a token created outside the client, which the client cannot renew |
| AWS SigV4 signing | Glue, S3 Tables | **not supported** |

The client's `regenerate_token()` only knows how to repeat an OAuth2 login. BigLake and OneLake tokens come from the `gcloud` and `az` command-line tools, so a long-running program has to fetch new ones itself.

Missing SigV4 is already known. `apache/iceberg-rust` issue #1236, *"REST catalog: support AWS sigV4"*, is open and asks for the same three settings `pyiceberg` already has: `rest.sigv4-enabled`, `rest.signing-name` and `rest.signing-region`. Discussion #1239 shows a user getting a 403 from S3 Tables because of it.

Rust code can still use both AWS catalogs. The same project publishes `iceberg-catalog-glue` and `iceberg-catalog-s3tables`, both 0.10.1, which call the AWS APIs directly. The cost is that a Rust tool covering all seven catalogs needs three different catalog clients. In Python, one client covers all seven.

---

#### Step 7 — Point It at a Managed Catalog

```console
$ python3 run_rust.py --only google-lakehouse --only microsoft-onelake --storage opendal
google-lakehouse   1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-google-lakehouse.json
microsoft-onelake  1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-microsoft-onelake.json
```

The same result as Polaris: all 7 supported read operations work on both.

---

#### 🔎 Tip: The Client Has No TLS Built In

`iceberg-catalog-rest` 0.10.1 includes its HTTP library, `reqwest`, with TLS switched off, and offers no option to switch it on. Built that way, every request to an `https://` catalog fails before getting any response:

```console
$ IRC_BINARY=<no-tls build> python3 run_rust.py --only google-lakehouse \
      --only microsoft-onelake --storage opendal --tag no-tls
google-lakehouse   7 failed, 1 implicit, 14 not-expressible, 11 not-issued
microsoft-onelake  7 failed, 1 implicit, 14 not-expressible, 11 not-issued
```

```plaintext
Unexpected => Failed to execute http request, source: error sending request
for url (<uri>/v1/config?warehouse=<warehouse>)
```

The fix is the `rustls-tls` line from Step 2 in your own `Cargo.toml`. Cargo merges features across all dependencies, so the client picks up TLS from your line. If another dependency of yours already turns on TLS in `reqwest`, you will never see this error.

This is tracked as `apache/iceberg-rust` #2888, *"Add TLS features to iceberg-catalog-rest"*, which is open and calls the workaround *"a very implicit and brittle solution."*

---

#### 🔎 Tip: Loading a Table Needs a Second Crate

Without a storage library, `load_table` gets the table from the catalog and then refuses to return it:

```plaintext
StorageFactory must be provided for RestCatalog.
Use `with_storage_factory` to configure it.
```

The core `iceberg` 0.10.1 crate can only read local files and memory (`io/storage/local_fs.rs:330`, `io/storage/memory.rs:250`). Its README points to the rest, at line 70: *"For storage backend support (S3, GCS, local filesystem, etc.), use the `iceberg-storage-opendal` crate."*

Polaris stores its table on local disk. Every managed catalog here stores tables in S3, Google Cloud Storage or Azure, so without that crate `load_table` fails on all of them.

---

#### Step 8 — Read the Table's Files

`load_table` sets up file access but does not read anything, so each run also reads the table's metadata file through the client. The output lists the names of the settings the storage library received, never their values:

```plaintext
apache-polaris
  fileio config keys: ...
  storage credential keys among them: none
  read: ok, scheme file, 5614 bytes, 21 ms
google-lakehouse
  fileio config keys: ...
  storage credential keys among them: none
  read: ok, scheme gs, 5497 bytes, 451 ms
microsoft-onelake
  fileio config keys: ...
  storage credential keys among them: none
  read: FAILED after 47066 ms
  error: Unexpected => Failure in doing io operation, source: Unexpected
  (persistent) at read, context: { timeout: 10 } => io timeout reached
```

No catalog passed along a storage credential, because the client never asks for one. It does not send the `X-Iceberg-Access-Delegation` header. The storage library has to find a login on its own.

**Google Cloud Storage works.** It uses the Google login already on the machine (application-default credentials).

**Azure fails.** The Azure part of the storage library, `opendal-service-azdls` 0.57.0, has code to use your `az login`, but it is never given a way to run the `az` command (`backend.rs:297`). It also ignores Azure environment variables such as `AZURE_CLIENT_ID`. The logins left are an account key, a SAS token or a service principal secret. OneLake has no account key. The timeout is consistent with the library then trying the Azure VM metadata service, which does not exist on this machine.

**Asking OneLake for a credential does not fix it.** OneLake does hand one out: the same request from `pyiceberg`, which sends `X-Iceberg-Access-Delegation: vended-credentials` by default, gets one back. The Rust client can send that header too, as a fixed extra header:

```console
$ python3 run_rust.py --only microsoft-onelake --storage opendal \
      --access-delegation vended-credentials
microsoft-onelake  1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-microsoft-onelake-delegation.json
```

The read still timed out, after 47181 ms. The client reads the credential out of the response (`types.rs:226`) and then never uses it: when it sets up file access, it copies only the response's `config` settings (`catalog.rs:455`).

Both problems are open upstream. `apache/iceberg-rust` #2931 covers using catalog-issued storage credentials, and #1442 covers the Azure SAS token format those credentials use.

For now, reading OneLake's files from this client needs a service principal, or a SAS token created separately.

---

#### Step 9 — Try a SigV4 Signature as a Header

A SigV4 signature covers one specific request. The test signs the first request the client sends, `GET /v1/config`, and gives the client the signature as fixed headers. The client then sends those same headers with every request.

```console
$ python3 run_rust.py --only aws-glue --only aws-s3tables --sigv4-demo --storage opendal
$ python3 vendor_report.py
wrote evidence/rust-vendor-runs.txt
```

```plaintext
aws-glue
  through the crate: 7 of 7 issued probes refused with InvalidSignatureException, 0 succeeded
  replay, GET /v1/config (the signed request): 200
  replay, GET /v1/{prefix}/namespaces (same headers): 403

aws-s3tables
  through the crate: 7 of 7 issued probes refused with InvalidSignatureException, 0 succeeded
  replay, GET /v1/config (the signed request): 200
  replay, GET /v1/{prefix}/namespaces (same headers): 403
```

The "replay" lines send the same headers directly: they work once, on the request they were signed for, and are refused on the next. Glue and S3 Tables give the same error:

```plaintext
The request signature we calculated does not match the signature you provided.
Check your AWS Secret Access Key and signing method. Consult the service
documentation for details.
```

Fixed headers cannot replace request signing, so this client cannot use the AWS REST catalogs.

---

#### 🔎 Tip: pyiceberg Checks the Endpoint List First

When `pyiceberg` connects, the catalog sends a list of the endpoints it supports, and `pyiceberg` refuses to call anything not on the list. The Rust client never reads that list.

Against the lists the seven catalogs published in the earlier article (`evidence/declaration-gate-cost.txt`), the check blocks 2 working endpoints across the seven, both of them `loadCredentials`, and answers 4 more with a substituted request, all HEADs on the two AWS catalogs. It leaves 3 of the seven catalogs alone. The Rust client has no method for `loadCredentials`, so 0 of the blocked cases are requests it could have sent.

---

#### Compare and Contrast

The `writes, not run` column counts endpoints the seven-catalog run left alone, all of which Step 5 issued against Polaris.

| catalog | login | ok | failed | writes, not run | unsupported | table files |
|---|---|---|---|---|---|---|
| Apache Polaris | 🟢 OAuth2 | 7 | 0 | 11 | 14 | 🟢 read |
| Google BigLake | 🟢 `gcloud` token | 7 | 0 | 11 | 14 | 🟢 read, using the machine's Google login |
| Microsoft OneLake | 🟢 `az` token | 7 | 0 | 11 | 14 | ❌ timed out |
| AWS Glue | ❌ SigV4 | 0 | 7 | — | — | — |
| AWS S3 Tables | ❌ SigV4 | 0 | 7 | — | — | — |
| Databricks Unity | token | not run | | | | |
| Snowflake Horizon | key-pair JWT | not run | | | | |

What you add beyond the client itself:

| | needed for | how |
|---|---|---|
| TLS | any `https://` catalog | a `reqwest` TLS feature in your `Cargo.toml` |
| `iceberg-storage-opendal` | loading any cloud-stored table | a second crate |
| storage login | reading any table file | from your environment; catalog-issued credentials are not used |
| SigV4 signing | Glue and S3 Tables over REST | not available; use `iceberg-catalog-glue` or `iceberg-catalog-s3tables` |

---

#### Summary

The goal of this article was to point the Apache Rust Iceberg REST client at seven catalogs and record what works and what it takes. The key to the solution was matching every test to a line in the client's source code, running the same tests against each catalog, and reading one file through the client's own storage code. The results were:

- 🟢 The client supports 13 of 25 endpoints; of the other 12, 11 are missing and 1 is a stub. Two of the 13 it reaches only in part
- 🟢 Polaris, BigLake and OneLake: all 7 supported read operations work on each
- 🟢 All 11 write endpoints work against the local Polaris: 11 ok, 0 failed, with every request logged. The stubbed one sends no request at all
- ❌ Glue and S3 Tables: the client cannot sign AWS requests, and a signature passed as a header works for one request only (upstream #1236)
- ⚠️ The client has no TLS built in, so every `https://` catalog fails until you add it (upstream #2888)
- ⚠️ Loading a cloud-stored table also needs `iceberg-storage-opendal`
- ❌ OneLake's files could not be read: the Azure storage code cannot use an `az login`, and a credential from the catalog is read and then ignored (upstream #2931, #1442)

Scope: `iceberg-catalog-rest` 0.10.1 with `iceberg` 0.10.1, `iceberg-storage-opendal` 0.10.1 and `reqwest` 0.12.28 with `rustls-tls`, built with `rustc` 1.98.1. Source code read on 2026-09-04 and versions captured on 2026-09-17; every run on 2026-09-18, one run per catalog from one machine in one region. Polaris 1.7.0 ran in Docker with permissive settings and local file storage. Glue and S3 Tables were tested only with the signature experiment. Unity and Horizon were not run, and their rows come from reading the source. 33 checks covering 25 of the specification's 35 operations. The seven catalogs were run read-only. The eleven write endpoints were issued on 2026-09-21 against the local Polaris alone, so the write results describe that one permissive server. The tests check that each operation answers; the answers themselves are not checked. Three of the seven catalogs were on trial accounts in the earlier article, and managed catalogs do not report a version.

The strategy for testing what one Rust Iceberg client can reach was validated with an incremental step by step approach.

---

#### References

* [lakehouse-iceberg-2026 | GitHub](https://github.com/xbill9/lakehouse-iceberg-2026)
* [apache/iceberg-rust](https://github.com/apache/iceberg-rust)
* [iceberg-rust #1236 — REST catalog: support AWS sigV4](https://github.com/apache/iceberg-rust/issues/1236)
* [iceberg-rust #2888 — Add TLS features to iceberg-catalog-rest](https://github.com/apache/iceberg-rust/issues/2888)
* [iceberg-rust #2931 — Support refreshing vended storage credentials for REST catalog tables](https://github.com/apache/iceberg-rust/issues/2931)
* [iceberg-rust #1442 — ADLS: Support vended "adls.sas-token.xxx" prefixed tokens](https://github.com/apache/iceberg-rust/issues/1442)
* [Seven Iceberg REST Catalogs: What They Declare, and What They Serve](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
