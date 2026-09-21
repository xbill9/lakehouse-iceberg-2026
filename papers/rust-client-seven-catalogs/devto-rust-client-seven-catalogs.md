---
title: "What One Rust Client Can Reach Across Seven Iceberg Catalogs"
published: false
description: "Step by step: the Apache Rust Iceberg REST client against seven Iceberg catalogs. It logs in to five of them, and on every one it logs in to, all 13 endpoints it implements answer — 7 reads on three catalogs and 11 writes on the local one, with no failures. Two lines of Cargo.toml and one AWS auth scheme are what stand in the way."
tags: rust, iceberg, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/rust-client-seven-catalogs/cover.fd3f64f1.jpg
---

This article provides a step by step guide to pointing the Apache Rust client for Iceberg REST catalogs at seven catalogs and recording what works. A Python script runs a small Rust program against each catalog and saves every result.

https://github.com/xbill9/lakehouse-iceberg-2026

---

#### What is this project trying to Do?

An earlier article tested what seven Iceberg REST catalogs support. This one asks from the other side: if you write a lakehouse tool in Rust today, will it work with the catalog you already pay for, and what do you need to set up? The client is `iceberg-catalog-rest` 0.10.1 from the Apache Iceberg project, and the catalogs, tests and test table are the same as in that article:

- **Apache Polaris** 1.7.0, running locally as the reference
- **Google BigLake** and **Microsoft OneLake**, over the internet
- **AWS Glue** and **AWS S3 Tables**, over the internet
- **Databricks Unity** and **Snowflake Horizon**, not run here

The result is a short one. This client implements 13 of the 25 operations the earlier article tested, it logs in to five of the seven catalogs, and on every catalog it logs in to, all 13 answer. Two lines of `Cargo.toml` and one AWS authentication scheme are what stand between it and the rest.

---

#### What Does Each Result Mean?

The test suite is 33 checks covering 25 of the 35 operations in the Iceberg REST specification. Each check gets one of five results:

| result | meaning |
|---|---|
| `OK` | the client sent the request and got an answer |
| `FAILED` | the client sent the request and got an error |
| `IMPLICIT` | the client sends this request on its own, and there is no way to call it directly |
| `NOT-EXPRESSIBLE` | the client has no method for this operation |
| `NOT-ISSUED` | the client supports it, but it is a write, and that run only reads |

---

#### Where do I start?

The strategy for testing the client is an incremental step by step approach.

First, a local Polaris catalog is started and the client's source is read to list which operations it supports. The test program is then built and run against Polaris, reads first and writes after, then against the managed catalogs one login method at a time, and finally it tries to read a table's files.

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

The last two lines add a TLS backend and the cloud storage backends. *What You Add Beyond the Client*, near the end, says what happens without each of them.

```console
$ cd ../iceberg-rust-client
$ cargo build --release
    Finished `release` profile [optimized] target(s) in 1m 41s
```

---

#### Step 3 — List What the Client Supports

Each of the 33 checks is matched to a method in the client's published source code, with the file and line number, and `check_refs.py` confirms all 25 of those lines still sit inside the function they name. Counting each endpoint once, since five checks use the same `update_table` endpoint:

```plaintext
13 of 25 distinct endpoints are expressible through this client.
Counted per probe the figure is 19 of 33, which is the same fact
weighted by how many probes paper 1 happened to point at one endpoint.
```

The 12 endpoints it cannot reach split two ways:

- **Missing — 11 endpoints.** All seven view operations, scan planning, metrics reporting, the separate credentials endpoint, and `commitTransaction`. The client builds eight URLs in total (`catalog.rs:177-215`), and none of them is a view, a scan plan, a metrics report or a transaction.
- **Stubbed — 1 endpoint.** `Catalog::update_namespace` exists, but returns the error `"Updating namespace not supported yet!"` (`catalog.rs:659`) and sends nothing.

Two endpoints it does reach, it reaches only in part, and both are counted among the 13: `load_table` cannot ask for `?snapshots=all`, and `list_namespaces` handles paging internally and never sends `pageSize`. It also reaches `registerTable`, which is one of the ten operations the earlier article did not cover, so it sits outside this count of 25.

Line numbers quoted here were read by hand and are archived, with the lines themselves, in `evidence/rust-source-citations.txt`.

---

#### Step 4 — Run the Reads Against Polaris

```console
$ python3 run_rust.py --storage opendal
apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-apache-polaris.json
```

All 7 supported read operations work. The one `IMPLICIT` result is the config request the client sends when it first connects, and the 11 `NOT-ISSUED` are writes this run does not send.

---

#### Step 5 — Run the Writes Against Polaris

The client has a method for each of those 11, and the read-only run sends none of them. A method that compiles can still fail on the wire, so this step sends them. Polaris is local, permissive and disposable, so the writes run there and on no other catalog, and every request goes through a small logging proxy that records what the client sent beside what came back:

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

All eleven work, and the scratch namespace is dropped at the end. The one refusal is the stub from Step 3, and the proxy log shows why it takes 0 ms: no request to the properties endpoint appears anywhere in the run.

---

#### 🔎 Tip: The Proxy Log Shows Three Things

**A properties commit always sends both update kinds.** Setting a property and removing one produce the same pair, `set-properties` and `remove-properties`, because the crate's properties action builds both every time (`update_properties.rs:95`). The two differ in their contents.

**Adding a column is one request carrying two updates**, with a requirement attached:

```plaintext
  POST    200  /v1/quickstart_catalog/namespaces/irc_probe_rust_1790009108/tables/t1
          updates: add-schema, set-current-schema
          requirements: assert-current-schema-id
```

**Every commit re-reads the table first**, so one property change is a `GET` and then a `POST`. That reload is also why a transaction commits against the table's current state, which is open upstream as `apache/iceberg-rust` #3134.

The log also confirms one thing: a two-level namespace goes out as `...%1Fchild`, the unit separator the specification asks for.

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

The specification's own security schemes are OAuth2 and bearer tokens; the signing it describes covers storage access. Glue and S3 Tables require SigV4 on the catalog requests themselves, a layer above what the specification defines, and `apache/iceberg-rust` #1236 is the open request to support it. The token the client does hold is refreshed by `regenerate_token()`, which only knows how to repeat an OAuth2 login, so a long-running program on BigLake or OneLake mints its own.

Fixed headers look like a way round the signing gap, and they are worth one measurement: a signature minted for `GET /v1/config` and passed as a static header got a 200 on that request and a 403 on the next, on Glue and S3 Tables both, with all 7 checks refused through the client. A signature covers the request it signs.

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

The same result as Polaris: all 7 supported read operations work on both, over the internet, with a token minted by `gcloud` and by `az`.

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

Local files and Google Cloud Storage read fine, the second one on the Google login already on the machine. No catalog passed along a storage credential, because the client never asks for one: it sends no `X-Iceberg-Access-Delegation` header, so the storage library finds a login on its own.

Azure is where that runs out. The Azure backend, `opendal-service-azdls` 0.57.0, has code to use your `az login` and is never given a way to run the `az` command (`backend.rs:297`), which leaves an account key, a SAS token or a service principal secret — and OneLake has no account key. Asking for a credential does not change it: OneLake hands one out, and with the delegation header passed as a static header the read still timed out, after 47181 ms. The client reads the credential from the response (`types.rs:226`) and copies only the response's `config` settings into file access (`catalog.rs:455`). Both halves are open upstream, as #2931 and #1442.

---

#### What You Add Beyond the Client

| | needed for | what happens without it |
|---|---|---|
| a `reqwest` TLS feature | any `https://` catalog | every request fails before any response: 7 failed, 0 ok, no HTTP status. Upstream #2888 |
| `iceberg-storage-opendal` | loading any cloud-stored table | `load_table` refuses: *"StorageFactory must be provided for RestCatalog"* |
| a storage login in your environment | reading any table file | the read fails or hangs; catalog-issued credentials are read and unused |
| a SigV4 signer | Glue and S3 Tables over REST | no login at all; use `iceberg-catalog-glue` or `iceberg-catalog-s3tables` instead |

The first two are one line each. `iceberg-catalog-rest` 0.10.1 declares `reqwest` with TLS switched off and offers no feature to switch it on, so a build that never names a TLS backend fails on the first `https://` request; Cargo merges features across dependencies, so your own line fixes it, and a project already using `reqwest` with TLS will never see it. The core `iceberg` 0.10.1 crate ships two storage factories, local files and memory (`io/storage/local_fs.rs:330`, `io/storage/memory.rs:250`), with its README pointing at the other crate on line 70.

---

#### Compare and Contrast

| catalog | login | ok | failed | table files |
|---|---|---|---|---|
| Apache Polaris | 🟢 OAuth2 | 7 reads, 11 writes | 0 | 🟢 read |
| Google BigLake | 🟢 `gcloud` token | 7 reads | 0 | 🟢 read, on the machine's Google login |
| Microsoft OneLake | 🟢 `az` token | 7 reads | 0 | ❌ timed out |
| AWS Glue | ❌ SigV4 | 0 | 7 | — |
| AWS S3 Tables | ❌ SigV4 | 0 | 7 | — |
| Databricks Unity | token, not run | — | — | — |
| Snowflake Horizon | key-pair JWT, not run | — | — | — |

Behind those numbers every catalog that answered showed the same shape: 14 endpoints the client has no method for, and every endpoint it does implement returning an answer.

---

#### Summary

The goal of this article was to point the Apache Rust Iceberg REST client at seven catalogs and record what works and what it takes. The key to the solution was matching every test to a line in the client's source code, running the same tests against each catalog, and logging every request the client sent. The results were:

- 🟢 Every endpoint the client implements answered on every catalog it could log in to: 7 reads on Polaris, BigLake and OneLake, and 11 writes on Polaris, with 0 failures
- 🟢 13 of 25 endpoints are implemented; of the other 12, 11 are missing and 1 is a stub that sends no request
- ⚠️ Two lines of `Cargo.toml` stand in front of that: a TLS backend (upstream #2888) and `iceberg-storage-opendal` for cloud storage
- ❌ Glue and S3 Tables require SigV4, which this client cannot send, so a Rust tool covering all seven catalogs needs three catalog clients where Python needs one (upstream #1236)
- ❌ OneLake's files could not be read: the Azure backend cannot use an `az login`, and a credential from the catalog is read and then ignored (upstream #2931, #1442)

Scope: `iceberg-catalog-rest` 0.10.1 with `iceberg` 0.10.1, `iceberg-storage-opendal` 0.10.1 and `reqwest` 0.12.28 with `rustls-tls`, built with `rustc` 1.98.1. Source read 2026-09-04, versions captured 2026-09-17, catalog runs 2026-09-18, write run 2026-09-21, one run each from one machine in one region. Polaris 1.7.0 ran in Docker with permissive settings and local file storage, and the writes ran there alone, so those results describe one permissive server. Glue and S3 Tables were tested only with the signature experiment, and Unity and Horizon were not run at all, their rows coming from the source. The tests check that each operation answers; the answers themselves are not checked. Three of the seven catalogs were on trial accounts in the earlier article, and managed catalogs do not report a version.

The strategy for testing what one Rust Iceberg client can reach was validated with an incremental step by step approach.

---

#### References

* [lakehouse-iceberg-2026 | GitHub](https://github.com/xbill9/lakehouse-iceberg-2026)
* [apache/iceberg-rust](https://github.com/apache/iceberg-rust)
* [iceberg-rust #1236 — REST catalog: support AWS sigV4](https://github.com/apache/iceberg-rust/issues/1236)
* [iceberg-rust #2888 — Add TLS features to iceberg-catalog-rest](https://github.com/apache/iceberg-rust/issues/2888)
* [iceberg-rust #2931 — Support refreshing vended storage credentials for REST catalog tables](https://github.com/apache/iceberg-rust/issues/2931)
* [iceberg-rust #1442 — ADLS: Support vended "adls.sas-token.xxx" prefixed tokens](https://github.com/apache/iceberg-rust/issues/1442)
* [iceberg-rust #3134 — Transaction commits against a base it never validated](https://github.com/apache/iceberg-rust/issues/3134)
* [Seven Iceberg REST Catalogs: What They Declare, and What They Serve](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
