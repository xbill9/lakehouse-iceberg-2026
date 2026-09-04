# What a Rust client can reach: iceberg-rust against seven catalogs

Supports the **Rust client paper**. Paper 1 measured what seven Iceberg REST
catalogs *serve*. This measures what a *client implementation* can reach across
the same seven, with `pyiceberg` as the control.

Standalone, and deliberately not part of `iceberg-mcp-hosts/`. That paper
measures MCP tool surfaces, and the fact that one server under test happens to be
written in Rust is incidental to it. Rust is the subject here.

## What varies, and what does not

| shared, one implementation | different, on purpose |
|---|---|
| the seven catalogs, already configured | the client library |
| the fixture table, already seeded | |
| the operation set, taken from paper 1's probes | |
| the evidence and anonymisation discipline | |

    control     pyiceberg 0.12.0        Python, and what paper 1 measured with
    subject     iceberg-catalog-rest    Rust, Apache, 0.10.1 (2026-08-01)

Using paper 1's own probe list means the two papers are comparable rather than
merely adjacent: a cell that a catalog served for Python and refuses for Rust is
a client difference, because the server side is already measured.

## The finding that is already visible in the source

`evidence/rust-client-auth-surface.txt` records it, read from the published crate
rather than from documentation: the crate has **no AWS SigV4**. It supports a
bearer `token`, OAuth2 `credential` + `oauth2-server-uri` + `scope`, and static
`header.<name>` values, and its dependency list contains no AWS SDK or signing
crate.

Paper 1 measured Glue and S3 Tables as SigV4-signed. A SigV4 signature is
computed per request, so a static header cannot carry one. As shipped, two of the
seven are out of reach.

That is a reading of the source, not a result. **The paper has to demonstrate the
failure against a live endpoint**, in the same way paper 1 refused to report a
verdict it had not seen on the wire. Until then it is a hypothesis with a grep
behind it.

## What this is not

Not "Rust is missing features". The REST specification does not require SigV4;
the crate implements what the spec describes, and the two AWS catalogs layer an
AWS-specific signing requirement on top of it. The interesting sentence is about
what a portable client can assume, not about who is at fault.

## The second finding, also from the source

`make_surface.py` joins paper 1's 33 probes against `operation_map.py`, a
hand-read of the crate's `Catalog` impl with a file and line behind every entry,
and writes `evidence/rust-client-operation-surface.txt`. Counted by endpoint
signature rather than by probe, because five of paper 1's probes share
`update_table`:

    13 of 25 distinct endpoints are expressible through this client

The 12 that are not divide into three kinds, and the paper should not blur them:

- **absent**, 11 endpoints. All six view operations, scan planning, metrics
  reporting, the separate credentials endpoint, and `commitTransaction`. There
  is no method and no endpoint builder that could construct the URL.
- **unsupported**, 1 endpoint. `Catalog::update_namespace` compiles and returns
  `FeatureUnsupported, "Updating namespace not supported yet!"`. It is named in
  the API a caller builds against and is not served by the client -- the
  client-side echo of paper 1's declared-versus-served split.
- **degraded**, 2 probes that share reachable endpoints. `load_table` sends no
  query parameters, so `?snapshots=all` cannot be asked for; `list_namespaces`
  follows `next-page-token` internally and never sends `pageSize`. The endpoint
  is reachable, the probe's question is not expressible.

A probe that cannot be issued is not a failed probe. The run reports those as
`NOT-EXPRESSIBLE`, never as a red cell, for the same reason `INDETERMINATE`
exists in the conformance harness.

Running `make_surface.py` fails loudly if a probe has no mapping, if a mapping
names a probe that no longer exists, or if two probes sharing one endpoint
signature disagree about its status.

## Running it

```console
$ cargo build
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 run_rust.py                      # control only, the default
apache-polaris     1 implicit, 25 not-expressible, 7 ok
wrote evidence/rust-run-apache-polaris.json
$ python3 make_surface.py                  # rebuild the surface, no network
```

`src/main.rs` issues the probes and prints one JSON object each; `run_rust.py`
merges that against `operation_map.py` so all 33 of paper 1's probes get a row,
and takes catalog configuration and token minting from the conformance harness
rather than reimplementing them -- the two papers have to be pointed at the same
catalogs with the same credentials or the comparison is between two setups.

The binary has no write path, so a run cannot leave residue on a vendor catalog.
Nothing from a `loadTable` response reaches disk except counts and integers, and
the evidence carries a catalog's name but never its URL, warehouse or namespace.

## What the control run says

Polaris, 2026-09-04, `local-fs` storage: **7 OK, 1 implicit, 25 not-expressible,
0 failed.** Every operation this client can express against the control works,
which is the precondition for pointing it at a credentialed vendor.

Getting there cost one bug, caught by the rule that catches most of them. The
first run failed `load_table` on the control:

```console
StorageFactory must be provided for RestCatalog.
Use `with_storage_factory` to configure it.
```

Ours, not Polaris's. But the underlying fact is worth the paper's attention:
`load_table` returns a `Table`, a `Table` carries a `FileIO`, so this client
will not hand back a `loadTable` response at all without storage wiring -- the
HTTP round trip had already succeeded when it refused. And `iceberg` 0.10.1
ships exactly two storage factories, local filesystem and memory. What a caller
does for `s3://`, `gs://` or `abfss://` is a question the vendor runs will have
to answer, and it is a separate question from SigV4. `IRC_STORAGE` is therefore
a recorded property of every run, never a silent default.

## The auth plan, per catalog

`run_rust.py` classifies each catalog's auth before running it, and the
classification is itself a result:

| auth | catalogs | through the crate |
|---|---|---|
| oauth2 | Polaris | native: `credential` + `oauth2-server-uri` + `scope` |
| bearer from env | Unity | native: `token` |
| keypair-signed JWT | Horizon | native: a `credential` with no colon is sent as `client_secret` with no `client_id` (catalog.rs:238), which is the shape Horizon wants. Whether Horizon accepts the crate's grant is still a measurement |
| gcloud ADC, Azure CLI | BigLake, OneLake | static: a bearer minted outside the crate. It works, and the crate cannot refresh it -- `regenerate_token()` re-runs an OAuth2 grant, which is not how the token was obtained |
| SigV4 | Glue, S3 Tables | absent |

## Status

Control column green. Two surfaces read from the crate -- auth and operations --
and one measured run, against Polaris.

Next, in order:

1. The five expressible vendors, one at a time. Each is a real cost and a real
   round trip, so none of them runs without being asked for.
2. The SigV4 demonstration. Reading the source says a static header cannot carry
   a per-request signature; the paper still owes a live endpoint refusing one.
   The honest form is to lift a signature computed for `GET /v1/config` into
   `header.Authorization` and show the second request rejected -- that
   demonstrates the mechanism rather than merely the absence.
3. The `pyiceberg` control column, so the comparison is client-versus-client
   rather than Rust-versus-paper-1's-raw-requests.
