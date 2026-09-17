---
title: "What One Rust Client Can Reach Across Seven Iceberg Catalogs"
published: false
description: "Reading iceberg-catalog-rest 0.10.1 against the same 33-probe suite used on seven Iceberg REST catalogs: 13 of 25 endpoints are expressible, two catalogs are unreachable before any request is sent, and loading a table needs a second crate."
tags: rust, iceberg, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/rust-client-seven-catalogs/cover.ebb86f90.jpg
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

All results below were measured on 2026-09-17 against `iceberg-catalog-rest`
0.10.1, `iceberg` 0.10.1, `iceberg-storage-opendal` 0.10.1 and Apache Polaris
1.7.0.

**Nothing here is about the Rust client being broken.** It is a young library
that implements what the REST specification describes, and everything it can
express worked on the first catalog it was pointed at. Nor is this a comparison
with any other client; where `pyiceberg` appears, it is only as a second opinion
on whether a refusal belongs to the client or to the catalog.

**One scope statement up front, because it changes how every table below should
be read.** Only the control catalog has been run. Reachability across the other
six is read from the client's source and joined against the earlier article's
measurements of those catalogs — it is a statement about what the client can
attempt, not a report of what happened when it did.

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
- Optional: credentials for any managed Iceberg REST catalog, which this article
  does not need

Nothing here costs anything. The control catalog runs locally.

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

## Two Catalogs Are Unreachable Before Any Request Is Sent

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

**It was a real bug here, though, and it is the kind that only shows up on a bill.**
This harness pinned `iceberg` with no storage crate. Table locations, read from
the earlier article's stored `loadTable` responses, are `file://` on the control
and `s3://`, `gs://` or `abfss://` everywhere else. Four of the catalogs this
client can otherwise reach are cloud-backed, so a vendor run would have produced
four red `load_table` cells caused by a dependency list and nothing else.

`IRC_STORAGE` is therefore a recorded property of every run, never a silent
default:

```console
$ python3 run_rust.py --storage opendal
apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
wrote evidence/rust-run-apache-polaris.json
```

## What the Control Run Says

Polaris 1.7.0, same fixture table as the earlier article, both storage factories:

| verdict | count |
|---|---|
| OK | 7 |
| IMPLICIT | 1 |
| NOT-ISSUED | 11 |
| NOT-EXPRESSIBLE | 14 |
| FAILED | **0** |

Every operation this client can express against the control works. That is the
precondition for spending a vendor call, and it is the whole of what has been
run so far.

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

## What This Does Not Cover Yet

- **Six of the seven catalogs have not been run.** Every row about them is a
  statement about what the client can attempt.
- **No write has been issued.** Eleven probes are `NOT-ISSUED` rather than
  measured.
- **The SigV4 refusal has not been demonstrated on the wire.** Reading the source
  says a static header cannot carry a per-request signature; that still owes a
  live endpoint refusing one.
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
- **Two of seven catalogs are unreachable through this client**, because it ships
  no request signer. Both are reachable in Rust through separate AWS-specific
  catalog crates, so the finding is about protocol uniformity, not capability.
- **Reading a cloud-backed table needs a second crate**, and the core crate's two
  storage factories cover local paths and memory only.
- **Everything the client can express works against the control**, 7 OK and 0
  failed.
- **A client-side declaration gate costs almost nothing.** Two blocked endpoints
  across seven catalogs, both `loadCredentials`, neither reachable from the Rust
  client anyway.

Scope: one client at `iceberg-catalog-rest` 0.10.1 with `iceberg` 0.10.1 and
`iceberg-storage-opendal` 0.10.1, measured 2026-09-17 against Apache Polaris 1.7.0
running locally under Docker with non-default permissive flags and `file://`
storage; 33 probes covering 25 of the specification's 35 operations, read-only, so
eleven write probes were not issued; the other six catalogs were not run, and
every statement about them is read from the client's source joined against
measurements taken on 2026-09-03 for the earlier article, three of those catalogs
on trial accounts; managed catalogs expose no version, so no result can be tied to
a release.

The strategy for measuring an Iceberg REST client against a fixed probe suite was
validated with an incremental step by step approach.
