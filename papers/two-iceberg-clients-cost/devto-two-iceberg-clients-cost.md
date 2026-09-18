---
title: "Two Iceberg Clients, One Protocol: Where the Time Actually Goes"
published: false
description: "Timing iceberg-catalog-rest 0.10.1 and pyiceberg 0.12.0 over the same Iceberg REST operations on a local catalog and two managed ones: the per-call gap is the HTTP stack and disappears into a real round trip, and half a second of cold start is importing one library and does not."
tags: rust, python, iceberg, performance
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/two-iceberg-clients-cost/cover.196381f2.jpg
---

This article provides a step by step comparison of two Apache Iceberg REST
catalog clients, measuring what each one costs per call and at startup. A Python
harness spawns both clients against the same catalog and the same table, stores
every timing sample, and then takes one request apart layer by layer to find
where the difference lives.

https://github.com/xbill9/lakehouse-iceberg-2026

Two Apache clients speak the same REST protocol to the same catalog. Comparing
what they *support* is a documentation exercise. Comparing what they *cost* is
not in either repository.

All results below were measured on 2026-09-17 and 2026-09-18 against
`iceberg-catalog-rest` 0.10.1 built in release mode with `rustc` 1.98.1, and
`pyiceberg` 0.12.0 on Python 3.14.7. The catalogs are Apache Polaris 1.7.0 over
loopback, then Google BigLake and Microsoft OneLake over the internet from the
same machine.

**Nothing here is a ranking, and nothing here is about either client being badly
built.** They are at different points in their lives, this measurement does not
adjust for that, and the most useful finding turns out not to be about Iceberg at
all. **Nothing here is about correctness either** — a benchmark says nothing
about whether an answer was right, and speed is never a reason to choose a client
that cannot reach the operations a workload needs.

## What Is This Project Trying to Do?

An earlier article measured what seven Iceberg REST catalogs serve. A second one
measured what a Rust client can reach. This one measures what the two clients
cost to use, on the operations both can express.

Three numbers, deliberately kept apart:

- Steady-state latency per operation, with the catalog object already built.
- Cold start: process spawn to exit, with the catalog built and each operation
  answered once.
- Where the per-call time goes, which is the only one that explains the other two.

## Why Not Just Count Features?

The two clients' operation surfaces are 13 of 25 endpoints for the Rust crate and
21 of 25 for `pyiceberg`. That number is real, and it is nearly useless here: it
is derivable from both repositories in an afternoon, it is true only of those two
versions, and a library that has been shipping longer implementing more of a
specification is not a finding.

So the surface tables are context in this article and never the headline, and no
score is summed across read and write surfaces. What is not in either repository
is what a call costs.

## At This Point You Should Have

- Rust 1.94 or newer, and a **release** build — a debug binary is not the
  artifact anyone ships
- Python 3.10+ with `pyiceberg` 0.12.0
- Docker, for the control catalog
- A quiet machine, which matters more than it sounds
- Optional: a managed Iceberg REST catalog, for the network half

## How the Benchmark Avoids Measuring Itself

Every rule below exists because it is a way to get a wrong number, and the last
three were found while this work was being done.

- **Release build.** The driver refuses to write evidence from a debug binary.
- **Both clients spawned as fresh processes.** The driver is itself Python, so
  timing `pyiceberg` in-process would hand it a warm interpreter while Rust paid
  for an exec.
- **Startup outside every sample.** Each process builds its catalog and runs a
  discarded warmup first, so the config fetch and the token grant are paid once
  and appear in no sample.
- **Rounds interleaved.** The clients alternate which goes first, so a machine
  that slows halfway through slows both equally.
- **Every sample stored.** Percentiles are computed in code at collection time
  and are re-derivable from the file.
- **Same credential path.** For a catalog whose bearer is minted by `gcloud` or
  `az`, the driver mints it once and hands the same token to both clients. The
  first vendor runs had the Python worker minting its own inside its timed
  spawn, which put a `gcloud` call on one side of the cold-start comparison.
  Those runs were discarded.
- **A non-2xx is not a sample.** BigLake's `irc_catalog_requests` quota is 75
  requests a minute, and it answered a burst with 429. Every timed layer now
  refuses a non-2xx, and error rows are kept out of the statistics.
- **Same request, or no ratio.** Covered below, because it changed one row.

```console
$ cargo build --release
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 bench.py --rounds 4 --iters 15
apache-polaris     6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench.py --only google-lakehouse --rounds 4 --iters 15 --storage opendal
google-lakehouse   6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench.py --only microsoft-onelake --rounds 4 --iters 15 --storage opendal
microsoft-onelake  6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench_report.py
wrote evidence/bench-comparison.txt   8 run(s) across 3 catalog(s)
```

## The Ratios on Loopback, and Why They Are an Upper Bound

Six read operations both clients can express, p50 in microseconds, quoted as the
range across four runs on two days:

| op | rust p50 | pyiceberg p50 | py/rust |
|---|---|---|---|
| list_namespaces | 301.3–768.1 | 883.2–1479.4 | 1.90x–4.29x |
| load_namespace | 312.2–699.3 | 784.7–1451.2 | 2.08x–3.52x |
| head_namespace | 328.4–584.8 | 1048.6–1362.7 | 2.33x–3.19x |
| list_tables | 327.0–552.1 | 1003.2–1551.3 | 2.56x–3.53x |
| load_table | 4634.1–5764.4 | 6405.6–7344.8 | 1.23x–1.38x |
| head_table | 4266.1–5298.0 | 5167.9–6155.4 | 1.14x–1.21x |

**The four cheap metadata calls sit between 1.90x and 4.29x, and the two
expensive ones between 1.14x and 1.38x.** The expensive pair is exactly where the
server does the most work, which is the check that the harness is measuring the
clients rather than itself.

**The ranges are wide, and that is part of the result.** The Rust p50 for
`list_namespaces` spread by 154.9% across the four runs. The two runs on the
second day gave Rust a lower p50 on every operation and `pyiceberg` a lower one on
five of six. Every run is
stored as its own file, and the report prints the spread beside the number,
because a single p50 here would be quoting the machine's mood.

**The ratios are an upper bound.** This is loopback to a local container, so the
client's own cost is the whole cost. A real network puts the same round trip on
both sides of every ratio. The next section measures exactly that.

## What Happens Over a Real Network?

The same benchmark against two managed catalogs, two runs each, p50 in
milliseconds:

| op | BigLake rust | BigLake py | ratio | OneLake rust | OneLake py | ratio |
|---|---|---|---|---|---|---|
| list_namespaces | 102.4–103.1 | 92.2–106.7 | 0.90x–1.04x | 36.0–36.4 | 35.9–36.0 | 0.99x–1.00x |
| load_namespace | 199.4–201.6 | 199.1–200.9 | 0.99x–1.01x | 44.6–45.1 | 45.3–46.3 | 1.02x–1.03x |
| head_namespace | 198.4–200.4 | 199.2–200.0 | 0.99x–1.01x | 44.8–45.9 | 45.3–46.6 | 0.99x–1.04x |
| list_tables | 202.7–205.5 | 203.2–206.1 | 1.00x | 45.0–46.3 | 45.4–45.6 | 0.98x–1.01x |
| load_table | 296.4–297.1 | 281.9–284.3 | 0.95x–0.96x | 36.3–39.0 | 160.7–167.7 | **4.12x–4.62x** |
| head_table | 201.7–205.0 | 199.9–201.4 | 0.98x–0.99x | 53.2–54.4 | 53.4–53.8 | 0.98x–1.01x |

Every ratio except `load_table` sits between 0.90x and 1.04x. The per-call
difference that loopback shows as 2x to 4x is a fraction of a millisecond, and a
round trip of 36 to 200 milliseconds absorbs it.

Two rows need a sentence each, and the next section is the larger one.

BigLake's `load_table` ran 4% to 5% faster through `pyiceberg` in both runs. The
access-delegation header below is not the cause: BigLake returns a
response of the same size and the same keys with and without it, and the timing difference between
the two did not clear its interval. This harness does not explain that row.

## The One Ratio That Is Not About the Client

OneLake's `load_table` came out 4.12x to 4.62x, while the five other operations
against the same catalog sat at about 1.00x. A ratio that stands out from its
neighbours is a reason to check the requests before the clients.

The two clients do not send the same request. `pyiceberg` sets
`X-Iceberg-Access-Delegation: vended-credentials` on its session by default
(`catalog/rest/__init__.py:881`). `iceberg-catalog-rest` 0.10.1 sends no such
header. So on `loadTable` the two clients ask OneLake different questions, and
OneLake does extra work for one of them.

`bench_delegation.py` times the one request on the same `pyiceberg` session five
ways, interleaved. Differences come with a 95% bootstrap interval, because a
round trip's tail is heavy and a mean-based bound drowns a median that every
quantile agrees on:

```console
$ python3 bench_delegation.py --only microsoft-onelake --iters 40
```

    row                                  p50       p90
    GET, header sent                   146.6     235.5
    GET, header removed                 38.1      41.3
    whole load_table                   148.5     182.4
    whole load_table, no header         36.6      42.4

    header cost at transport                   +108.5 ms  [+102.4, +122.2]  separable
    header cost through the method             +111.9 ms  [+105.8, +120.8]  separable
    client above transport, header removed       -1.5 ms  [-2.7, +1.1]  NO -- interval spans zero

With the header, OneLake's response gains one `storage-credentials` entry.
Without it, `pyiceberg`'s whole `load_table` is 36.6 ms at the median, which is
the Rust client's number. The 4x is a catalog minting a credential for one client
and not the other. Against the control, the header changes nothing: Polaris vends
nothing for `file://` storage, and the header's cost there did not clear its
interval.

**The comparison to take away is not "which is faster".** One default gets the
caller a working storage credential. The other gets a faster `loadTable` and no
credential. The companion article on the Rust client shows what that costs when
the caller then tries to read the table's files.

## Cold Start Is the Number That Survives the Network

Process spawn to exit, with the catalog built and each of the six operations
answered once, p50 of five spawns per client per run:

| catalog | rust | pyiceberg | difference, per run |
|---|---|---|---|
| Polaris, loopback, 4 runs | 16.4–26.0 ms | 525.8–557.9 ms | 507.2–535.1 ms |
| BigLake, 2 runs | 1376.3–1410.3 ms | 1911.8–2016.7 ms | 535.5–606.4 ms |
| OneLake, 2 runs | 955.9–996.2 ms | 1723.5–1772.4 ms | 767.6–776.2 ms |

The ratio compresses from 21.4x to 33.6x on loopback to 1.4x on BigLake and 1.8x
on OneLake,
because six round trips and a config fetch are now on both sides. **The
difference does not compress.** Half a second or more is paid before the first
request, whatever the network does afterwards. It is most of the difference for
a CLI, a lambda or a short-lived agent process, and none of it for a
long-running service.

## Where Does the Time Actually Go?

A ratio is a number, not an explanation. The same request is timed at increasing
depth on the same catalog object and the same session — transport, plus
`json.loads`, plus the pydantic model, plus the whole client method — and then
the identical GET is issued through the Rust binary's bare `reqwest` path.

```console
$ python3 bench_breakdown.py --iters 120
```

    layer                      p50       p90     stdev    added p50    2xSEM  separable?
    transport only           864.3    1088.5     207.1           --       --
    transport, no env        831.4    1068.4     235.3        -32.9     43.0  NO -- noise
    + json.loads             890.1    1091.1     205.0        +58.7     43.0  yes
    + pydantic               874.7    1159.3     284.6        -15.5     52.0  NO -- noise
    + client method          921.7    1198.8     202.6        +47.0     52.0  NO -- noise

Across the seven valid runs on the control, two days, 80 or 120 iterations each,
six of them with the Rust floor:

- **Transport is 90% to 94% of the call**, every time.
- `reqwest` p50 **269.8 to 479.7 us** against `requests` p50 **864.3 to 1286.4 us**
  on the same GET, same bearer, same server.
- The transport gap is **541.2 to 914.2 us**; everything `pyiceberg` does above
  transport is **57.3 to 134.7 us**.

So the HTTP stack is **85% to 90% of the per-call difference**. That last figure
is arithmetic over the two above, gap divided by gap plus library, run by run,
and is labelled as arithmetic rather than measured.

The consequence is worth stating plainly: this is not a language verdict. The
dominant term is a library choice, and the Iceberg-specific code is small on both
sides.

## What Is Not Separable, and Why That Is Printed

The obvious next question is which part of `pyiceberg` costs what. This harness
cannot say, and an earlier draft of this work claimed it could.

Across four runs the pydantic delta read **-0.5, +17.7, +16.9 and -22.8 us** —
and the draft quoted the two that agreed. The deltas are smaller than the
machine's noise on a call with a standard deviation of 200 to 700 microseconds.

So every delta is now printed beside twice the standard error of the mean of the
layer it is differenced against, and marked `NO -- noise` when it does not clear
it. At 120 iterations only the `json.loads` delta cleared the bound, and the
client-method delta did not.

`trust_env=False` is in the same position — `requests` re-reads the proxy
environment on every request unless it is off, and turning it off measured -32.9,
-55.0 and -89.9 us across three runs: negative every time, clearing the bound
once. Direction consistent, magnitude not established.

What the harness supports is the *size of the whole library layer*, not its
internal shares.

## Does the Transport Gap Survive a Round Trip?

The same decomposition against OneLake, twice. The library layer disappears: the
client method's p50 was within noise of bare transport in both runs, +89.2 and
+209.8 us against bounds of 1050.3 and 800.7.

The transport gap does not resolve. The two runs read +1385.9 us, with an interval
spanning zero, and +1632.1 us, with an interval that excludes it. The reason is
method, and the tool now prints it beside the number. The Rust floor is one
block run after the Python layers, not interleaved with them. On loopback the gap
is several times the noise and survives that. Over the network, a millisecond is
within the drift of a round trip between two blocks a minute apart.

The interleaved benchmark is the measurement to read, and it puts the two
clients' OneLake `list_namespaces` p50s within 1.2% of each other in both runs. Whatever the
HTTP stacks still differ by over TLS — `rustls` 0.23.45 on one side, OpenSSL
3.5.7 under `requests` on the other — it is below what a 36 ms round trip lets
this harness see.

## A Method Note That Cost a Retry

The first version of the decomposition ran its layers in blocks rather than
interleaved. Polaris warmed up across the run, the later blocks got the benefit,
and the tool reported transport as **slower than the whole call that contains
it** — a number that cannot be true.

That run is kept in the evidence directory as `bench-breakdown-*.invalid.txt`
rather than deleted, and it is excluded from the evidence set so it can never
back a figure. Anything compared has been interleaved since, apart from the Rust
floor described above, which is why that section carries its caveat.

## Cold Start Decomposes Too

Three subprocess measurements, p50 of five each, across the seven control runs:

| step | cost |
|---|---|
| bare interpreter, `python3 -c pass` | 9.0–11.2 ms |
| plus `import pyiceberg.catalog.rest` | a further 337.9–366.3 ms |
| catalog construction: config fetch and OAuth2 grant | 6.8–12.4 ms |

The only part that touches the network is the smallest. The half second is
importing Python.

Against OneLake the import measured 338.9 and 341.4 ms in the two runs, the same
as on loopback, and catalog construction, a single config fetch, measured 447.3
and 493.8 ms. Both clients pay that fetch. The import is paid by one of them.

## The Published Lambda Floor Excludes Exactly This

Rust-versus-Python cold start is a well-covered genre, and the published numbers
are the reason this section exists rather than a restatement of them. *Cold Starts
Are Dead* measures AWS Lambda at **88.3 ms p50 for Python 3.13 on arm64** (106.2
ms on x86_64) against **14.1 ms for Rust** (17.0 ms), at 512 MB with minimal
hello-world handlers — and states plainly that this is the platform floor with
**no framework dependencies**.

The loopback measurement here is about six times that floor — 525.8 to 557.9 ms
over 88.3 ms, which is arithmetic, 5.95 to 6.32 — and the decomposition says
why: 337.9 to 366.3 ms of it is importing one library. The genre figure is
the floor; this is what a single dependency adds on top of it.

## What This Does Not Cover

- **Two managed catalogs, one machine, one day.** Every vendor run is one region
  at one moment; the control has two days.
- **Six read operations.** No writes are timed.
- **BigLake's `load_table` edge for `pyiceberg`** is measured and not explained.
- **Nothing about correctness.**

## Summary

The goal of this article was to measure what two Apache Iceberg REST clients cost
to use, rather than what each one supports. The key to the solution was spawning
both as fresh processes against the same catalogs, keeping startup out of every
sample, and then taking a single request apart until the difference had a
location. The timing results were:

- **The per-call difference is the HTTP stack**, 85% to 90% of it by arithmetic
  over the measured gap, with transport 90% to 94% of a `pyiceberg` call on
  loopback.
- **It disappears into a real round trip.** Cheap metadata calls run 1.90x to
  4.29x faster in Rust on loopback and 0.90x to 1.04x on BigLake and OneLake.
- **Cold start does not.** `pyiceberg` pays 507.2 to 776.2 ms more per process on
  every catalog, and 337.9 to 366.3 ms of it on the control is importing one
  library.
- **One outlier was a different request, not a slower client.** OneLake's 4x on
  `load_table` is the catalog vending a credential that `pyiceberg` asks for by
  default and the Rust client does not; removing the header removes the gap.
- **The split inside the library layer is not separable at this sample size**, and
  the harness prints that verdict beside every delta rather than leaving it to
  prose.

Scope: two clients — `iceberg-catalog-rest` 0.10.1 in a release build with `rustc`
1.98.1 and `rustls` 0.23.45, and `pyiceberg` 0.12.0 on Python 3.14.7 with
`requests` 2.34.2 over OpenSSL 3.5.7 — measured on one 16-core Linux host; Apache
Polaris 1.7.0 in Docker over loopback with `file://` storage, four benchmark runs
across 2026-09-17 and 2026-09-18 and seven decomposition runs of 80 to 120
iterations; Google BigLake and Microsoft OneLake over the internet on 2026-09-18,
two benchmark runs each, two OneLake decomposition runs and one delegation run per
catalog; every benchmark run is 4 rounds x 15 iterations over six read operations,
720 samples; cold start is the p50 of five spawns per client per run; the fixture
is the single seeded probe table used by the earlier articles; managed catalogs
expose no version, and three of the seven catalogs in the series were measured on
trial accounts.

The strategy for comparing two Iceberg REST clients by cost rather than by feature
count was validated with an incremental step by step approach.
