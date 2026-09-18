# The Rust client harness: shared by papers 5 and 6

One directory, one probe list, two papers with different questions. The papers
are tracked separately and neither owns this directory:

| | paper | tracked in |
|---|---|---|
| 5 | Can one Rust client work against the test bed, and what does it take? | [`papers/rust-client-seven-catalogs/PLAN.md`](../papers/rust-client-seven-catalogs/PLAN.md) |
| 6 | What do the two clients cost, and what is the cost made of? | [`papers/two-iceberg-clients-cost/PLAN.md`](../papers/two-iceberg-clients-cost/PLAN.md) |

Findings, prior art and what each paper still owes live in those two files. What
follows is the harness.

`control` here always means the control **catalog**, Apache Polaris, never one
of the clients.

## What is held constant

Both papers use paper 1's probe list, paper 1's fixture tables, and the
conformance harness's own configuration and token minting. Nothing here is
pointed at a different catalog, table or credential than the paper it builds on,
because a comparison between two setups is not a comparison between two clients.

    iceberg-catalog-rest    Rust, Apache, =0.10.1, pinned
    iceberg-storage-opendal Rust, Apache, =0.10.1, for cloud-backed storage
    pyiceberg               Python, Apache, 0.12.0
    fixture                 paper 1's seeded probe table, per catalog

## The pieces

| file | what it does | network |
|---|---|---|
| `src/main.rs` | three modes: one probe per operation, `IRC_MODE=bench`, `IRC_MODE=transport` | yes |
| `run_rust.py` | drives the binary, merges against `operation_map.py`, writes a run | yes |
| `run_pyiceberg.py` | the same shape for the other client | yes |
| `bench.py` | times both clients, interleaved rounds, one file per run | yes |
| `bench_worker.py` | pyiceberg's half of the benchmark, spawned | yes |
| `bench_breakdown.py` | one request at increasing depth, plus the Rust transport floor | yes |
| `bench_delegation.py` | `load_table` with and without `X-Iceberg-Access-Delegation` | yes |
| `operation_map.py` / `pyiceberg_map.py` | hand-read maps, file and line per entry | no |
| `make_surface.py` | renders either map as a surface | no |
| `compare_clients.py` | joins both maps and both runs | no |
| `gate_cost.py` | joins paper 1's declarations against pyiceberg's gate | no |
| `bench_report.py` | renders stored benchmark runs, with cross-run spread | no |
| `vendor_report.py` | renders every Rust run and SigV4 demonstration | no |
| `check_refs.py` | resolves all 85 cited source lines | no |
| `redact.py` | scrubs, then refuses to write a surviving identifier | no |

## Running it

```console
$ cargo build --release                    # bench.py requires release
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t

$ python3 run_rust.py --storage opendal    # paper 5, control catalog
apache-polaris     1 implicit, 14 not-expressible, 11 not-issued, 7 ok
$ python3 run_pyiceberg.py                 # paper 6's other client
apache-polaris     2 gated, 1 implicit, 4 not-expressible, 16 not-issued, 10 ok
$ python3 bench.py --rounds 4 --iters 15   # paper 6, timed
apache-polaris     6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench_breakdown.py --iters 80    # paper 6, where the time goes

$ python3 run_rust.py --only google-lakehouse --only microsoft-onelake --storage opendal
$ python3 run_rust.py --only microsoft-onelake --storage opendal \
      --access-delegation vended-credentials   # does the crate use what it is vended?
$ python3 run_rust.py --only aws-glue --only aws-s3tables --sigv4-demo
$ python3 bench.py --only microsoft-onelake --storage opendal
$ python3 bench_delegation.py --only microsoft-onelake
$ python3 bench_breakdown.py --only google-lakehouse --pace-ms 900   # 75/min quota

$ python3 make_surface.py --all            # no network from here down
$ python3 compare_clients.py
$ python3 gate_cost.py
$ python3 bench_report.py
$ python3 vendor_report.py
$ python3 check_refs.py
$ python3 redact.py
```

## Harness invariants

Each of these was a bug here, not a rule imported from elsewhere.

- **`NOT-ISSUED` is not `NOT-EXPRESSIBLE`.** The first means the runner chose
  not to send a request it could send -- both runners are read-only, so every
  write probe is one. The second means the client has no request to send.
  Folding them together understated the Rust crate by eleven rows.
- **Storage is a separate crate.** `iceberg` 0.10.1 ships `local-fs` and
  `memory` only; `iceberg-storage-opendal` carries the cloud backends. Without
  it every `s3://`, `gs://` and `abfss://` catalog fails at `load_table` on our
  packaging rather than on anything the catalog did. `IRC_STORAGE` is recorded
  with every run and never defaulted silently.
- **Interleave anything compared.** Clients alternate round by round and the
  decomposition alternates layer by layer, because a server that warms up over
  a run hands its later blocks a discount. The first decomposition did not, and
  reported transport as slower than the call containing it; that run is kept as
  `evidence/bench-breakdown-*.invalid.txt`.
- **Release build or no evidence.** `bench.py` refuses a debug binary.
- **TLS is the caller's to add.** `iceberg-catalog-rest` 0.10.1 compiles
  `reqwest` with no TLS backend; `Cargo.toml` names `rustls-tls`. Without it
  every `https://` catalog fails at transport with no HTTP status.
- **Same request or no ratio.** pyiceberg sends `X-Iceberg-Access-Delegation:
  vended-credentials` by default and the Rust crate sends nothing, so a
  catalog that vends on `loadTable` is timed doing it for one client only.
  `bench_delegation.py` exists for that row.
- **Same credential path or no cold start.** A static bearer is minted once by
  the driver and handed to both clients. The pyiceberg worker used to mint its
  own with `gcloud`/`az` inside its timed spawn.
- **A non-2xx is not a sample.** BigLake's `irc_catalog_requests` quota is 75 a
  minute and answers a burst with 429. Every timed layer and the Rust transport
  floor refuse a non-2xx, `bench.py` keeps error rows out of its stats, and
  `--pace-ms` sleeps between calls outside every sample.
- **Cold start is spawn to exit**, with the catalog built and each of the six
  operations answered once -- not "one call", which this README said first.
- **One file per benchmark run.** A benchmark whose evidence is replaced by the
  next run cannot show its own spread, and the spread is the measurement.
- **Percentiles are computed in code**, from stored samples, never by hand.
- **Hand-read line numbers rot.** `check_refs.py` resolves every cited line
  against the installed source and fails if it is no longer inside the function
  it is cited for. It cannot check that the reading was right, only that it
  still points where it pointed.
- **Redact before disk.** Client error text is not ours to predict, so it goes
  through `redact.py`, which refuses to write a document in which a configured
  value survived. `python3 redact.py` plants an identifier and watches it fail.
  It matched literals only until 2026-09-18, when a percent-encoded warehouse
  in a TLS error carried a project id and two workspace GUIDs to disk while
  `verify()` passed; encoded forms, header values and warehouse components are
  matched now, and the self-test plants an encoded one.

Neither runner has a write path, so no run can leave residue on a vendor
catalog. Nothing from a `loadTable` response reaches disk except counts,
integers and key names -- never a value -- and evidence carries a catalog's name
but never its URL, warehouse or namespace.

## Standing caveats for anything either paper says

Paper 1's carry over unchanged: three of the seven catalogs were measured on
trial accounts, managed catalogs expose no version, every run is one region at
one moment, and coverage is 25 of the specification's 35 operations. Presence is
checked, not correctness -- a benchmark says nothing about whether an answer was
right, and speed is never a reason to choose a client that cannot reach the
operations a workload needs.
