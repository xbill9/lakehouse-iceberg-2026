---
title: "Two Iceberg Clients, One Protocol: Where the Time Actually Goes"
published: false
description: "Timing iceberg-catalog-rest 0.10.1 and pyiceberg 0.12.0 over the same Iceberg REST catalog operations, then decomposing the difference: 90 to 94 percent of a pyiceberg call is the HTTP stack, and half a second of cold start is importing one library."
tags: rust, python, iceberg, performance
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/two-iceberg-clients-cost/cover.86e57ed3.jpg
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

All results below were measured on 2026-09-17 against `iceberg-catalog-rest`
0.10.1 built in release mode with `rustc` 1.98.1, and `pyiceberg` 0.12.0 on
Python 3.14.7, both pointed at Apache Polaris 1.7.0 over loopback.

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
- Cold start: process spawn to one answered call.
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

## How the Benchmark Avoids Measuring Itself

Every rule below exists because it is a way to get a wrong number.

- **Release build.** The driver refuses to write evidence from a debug binary.
- **Both clients spawned as fresh processes.** The driver is itself Python, so
  timing `pyiceberg` in-process would hand it a warm interpreter while Rust paid
  for an exec.
- **Startup outside every sample.** Each process builds its catalog and runs a
  discarded warmup first, so the config fetch and the token grant are paid once
  and appear in no sample.
- **Startup also measured**, separately, as wall clock from spawn to one answered
  call.
- **Rounds interleaved.** The clients alternate which goes first, so a machine
  that slows halfway through slows both equally.
- **Every sample stored.** Percentiles are computed in code at collection time
  and are re-derivable from the file.

```console
$ cargo build --release
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 bench.py --rounds 4 --iters 15
apache-polaris     6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
wrote evidence/bench-apache-polaris-20260917T163335Z.json
```

## The Ratios, and the Reason They Are an Upper Bound

Six read operations both clients can express, p50 in microseconds, quoted as the
range across two runs:

| op | rust p50 | pyiceberg p50 | py/rust |
|---|---|---|---|
| list_namespaces | 578.0–768.1 | 1460.8–1479.4 | 1.90x–2.56x |
| load_namespace | 550.6–699.3 | 1143.8–1451.2 | 2.08x |
| head_namespace | 526.4–584.8 | 1306.8–1362.7 | 2.33x–2.48x |
| list_tables | 491.6–552.1 | 1412.6–1551.3 | 2.56x–3.16x |
| load_table | 5347.9–5764.4 | 6555.8–7344.8 | 1.23x–1.27x |
| head_table | 4876.7–5298.0 | 5538.4–6155.4 | 1.14x–1.16x |

Two things in that table matter more than the headline ratio.

**The four cheap metadata calls sit around 2x to 3x, and the two expensive ones
at 1.14x to 1.27x** — and the expensive pair is exactly where the server does the
most work. That is the check that the harness is measuring the clients rather
than itself.

**The ratios are an upper bound.** This is loopback to a local container, so the
client's own cost is the whole cost. Adding twenty milliseconds of vendor latency
to both sides moves every ratio toward 1.

A range rather than a point, because two runs a minute apart on an idle machine
moved `list_namespaces` p50 by 32.9%. Every run is stored as its own file for
that reason, and the report prints the spread beside the number.

## Cold Start Is the Number That Survives the Network

Process spawn to one answered call, p50 of five spawns each, two runs:

| client | cold start |
|---|---|
| rust | 18.6 ms and 26.0 ms |
| pyiceberg | 525.8 ms and 557.9 ms |

Unlike the per-call ratios, this does not compress under network latency, because
it is paid before any request. It is most of the difference for a CLI, a lambda
or a short-lived agent process, and none of it for a long-running service.

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

Across five runs:

- **Transport is 90% to 94% of the call**, every time.
- `reqwest` p50 **323.2 to 479.7 us** against `requests` p50 **864.3 to 1286.4 us**
  on the same GET, same bearer, same server.
- The transport gap is **541.2 to 914.2 us**; everything `pyiceberg` does above
  transport is **57.3 to 134.7 us**.

So the HTTP stack is **85% to 90% of the per-call difference**. That last figure
is arithmetic over the two above — gap divided by gap plus library — and is
labelled as arithmetic rather than measured.

The consequence is worth stating plainly: this is not a language verdict. The
dominant term is a library choice, and the Iceberg-specific code is small on both
sides.

## What Is Not Separable, and Why That Is Printed

The obvious next question is which part of `pyiceberg` costs what. The honest
answer is that this harness cannot say, and an earlier draft of this work claimed
it could.

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

## A Method Note That Cost a Retry

The first version of the decomposition ran its layers in blocks rather than
interleaved. Polaris warmed up across the run, the later blocks got the benefit,
and the tool reported transport as **slower than the whole call that contains
it** — a number that cannot be true.

That run is kept in the evidence directory as `bench-breakdown-*.invalid.txt`
rather than deleted, and it is excluded from the evidence set so it can never
back a figure. Anything compared has been interleaved since.

## Cold Start Decomposes Too

Three subprocess measurements, p50 of five each, across five runs:

| step | cost |
|---|---|
| bare interpreter, `python3 -c pass` | 9.1–11.2 ms |
| plus `import pyiceberg.catalog.rest` | a further 337.9–366.3 ms |
| catalog construction: config fetch and OAuth2 grant | 7.2–12.4 ms |

The only part that touches the network is the smallest. The half second is
importing Python.

## The Published Lambda Floor Excludes Exactly This

Rust-versus-Python cold start is a well-covered genre, and the published numbers
are the reason this section exists rather than a restatement of them. *Cold Starts
Are Dead* measures AWS Lambda at **88.3 ms p50 for Python 3.13 on arm64** (106.2
ms on x86_64) against **14.1 ms for Rust** (17.0 ms), at 512 MB with minimal
hello-world handlers — and states plainly that this is the platform floor with
**no framework dependencies**.

The measurement here is five times that floor, and the decomposition says why:
337.9 to 366.3 ms of it is importing one library. The genre figure is the floor;
this is what a single dependency adds on top of it.

## What This Does Not Cover Yet

- **One catalog, over loopback.** The ratios compress under real network latency
  and the vendor runs have not been done.
- **Two runs, one machine, one afternoon.** The spread across runs is already a
  third on one operation; repeats across days are owed.
- **Six read operations.** No writes are timed.
- **Nothing about correctness.**

## Summary

The goal of this article was to measure what two Apache Iceberg REST clients cost
to use, rather than what each one supports. The key to the solution was spawning
both as fresh processes against one catalog, keeping startup out of every sample,
and then taking a single request apart until the difference had a location. The
timing results were:

- **Cheap metadata calls run 1.90x to 3.16x faster in Rust**, the expensive two
  1.14x to 1.27x — and the narrow pair is where the server does the work, which
  is how the harness proves it is measuring the clients.
- **Cold start is 18.6 and 26.0 ms against 525.8 and 557.9 ms**, and it is the
  figure that survives the network because it is paid before any request.
- **Transport is 90% to 94% of a `pyiceberg` call**, making the HTTP stack 85% to
  90% of the per-call difference, by arithmetic over the measured gap.
- **Half a second of cold start is importing one library**, 337.9 to 366.3 ms of
  it, against 7.2 to 12.4 ms for the config fetch and token grant that actually
  touch the network.
- **The split inside the library layer is not separable at this sample size**, and
  the harness now prints that verdict beside every delta rather than leaving it
  to prose.

Scope: two clients — `iceberg-catalog-rest` 0.10.1 in a release build with `rustc`
1.98.1, and `pyiceberg` 0.12.0 on Python 3.14.7 — measured on 2026-09-17 on one
16-core Linux host against Apache Polaris 1.7.0 in Docker over loopback with
`file://` storage; two benchmark runs of 4 rounds x 15 iterations over six read
operations, 720 samples each, plus five decomposition runs of 60 to 120
iterations; cold start is the p50 of five spawns per client per run; no vendor
catalog and no network beyond loopback was involved, so every ratio here is an
upper bound; and the fixture is the single seeded probe table used by the earlier
articles.

The strategy for comparing two Iceberg REST clients by cost rather than by feature
count was validated with an incremental step by step approach.
