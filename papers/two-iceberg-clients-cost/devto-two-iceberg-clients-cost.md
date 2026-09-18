---
title: "Two Iceberg Clients, One Protocol: Where the Time Goes"
published: false
description: "Step by step: timing the Rust and Python Iceberg REST clients on the same operations, on a local catalog and on BigLake and OneLake. Rust is 2x to 4x faster per call on the same machine, the two are even over the internet, and Python takes half a second longer to start on every catalog."
tags: rust, python, iceberg, performance
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/two-iceberg-clients-cost/cover.d48183ca.jpg
---

This article provides a step by step comparison of the Rust and Python clients for Apache Iceberg REST catalogs. It times both clients on the same operations against the same tables, then breaks one request down to see where the time goes.

https://github.com/xbill9/lakehouse-iceberg-2026

---

#### What is this project trying to Do?

Two Apache clients talk to the same catalogs:

- **`iceberg-catalog-rest` 0.10.1**, the Rust client, built in release mode
- **`pyiceberg` 0.12.0**, the Python client, on Python 3.14.7

They run against three catalogs:

- **Apache Polaris** 1.7.0 in Docker on the same machine, so there is no network time
- **Google BigLake** and **Microsoft OneLake** over the internet

Three things are measured: how long each call takes, how long each client takes to start, and where the time in one call is spent.

The benchmark measures speed only. It does not check that answers are correct, and a client that lacks an operation you need is the wrong choice however fast it is.

---

#### Why Not Just Count Features?

The Rust client supports 13 of the 25 catalog endpoints tested, and `pyiceberg` supports 21. Anyone can count that from the two repositories, and it only holds for these two versions.

How long a call takes is in neither repository, so that is what this article measures.

---

#### Where do I start?

The strategy for comparing the two clients is an incremental step by step approach.

First, both clients are timed against a local catalog, where only the client's own time is measured. Then one request is broken down to find where the time goes. The same benchmark then runs against two managed catalogs, the two clients' requests are compared, and startup time is measured last.

---

#### At This Point You Should Have…

- Rust 1.94 or newer, and a **release** build — this run used `rustc` 1.98.1
- Python 3.10+ with `pyiceberg` 0.12.0
- Docker, for the local Polaris catalog
- A quiet machine — this one is a 16-core Linux host
- Optional: a managed Iceberg REST catalog, for the internet runs

---

#### Step 1 — Build Both Clients and Start Polaris

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-conformance && ./polaris-up.sh
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ cd ../iceberg-rust-client && cargo build --release
```

The benchmark will not save results from a debug build.

---

#### Step 2 — Time Both Clients Locally

To keep the comparison fair:

- **Each client runs in its own new process.** The benchmark script is Python, so running `pyiceberg` inside it would give Python a head start.
- **Startup is timed separately.** Each process connects and warms up before any call is timed.
- **The clients take turns.** They alternate going first, so a machine that slows down slows both.
- **Every timing is saved**, and the medians are computed from the saved files.

```console
$ python3 bench.py --rounds 4 --iters 15
apache-polaris     6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench_report.py
wrote evidence/bench-comparison.txt   8 run(s) across 3 catalog(s)
```

Six read operations both clients support, median time in microseconds, lowest to highest across four runs on two days:

| op | rust | pyiceberg | python ÷ rust |
|---|---|---|---|
| list_namespaces | 301.3–768.1 | 883.2–1479.4 | 1.90x–4.29x |
| load_namespace | 312.2–699.3 | 784.7–1451.2 | 2.08x–3.52x |
| head_namespace | 328.4–584.8 | 1048.6–1362.7 | 2.33x–3.19x |
| list_tables | 327.0–552.1 | 1003.2–1551.3 | 2.56x–3.53x |
| load_table | 4634.1–5764.4 | 6405.6–7344.8 | 1.23x–1.38x |
| head_table | 4266.1–5298.0 | 5167.9–6155.4 | 1.14x–1.21x |

**Rust is 1.90x to 4.29x faster on the four small calls, and 1.14x to 1.38x on the two table calls**, where the server itself does more work.

**The numbers vary a lot between runs.** The Rust time for `list_namespaces` ranged from 301.3 to 768.1 microseconds, a spread of 154.9%. That is why the table shows ranges.

With no network involved, these ratios are as large as the difference can get. Step 4 adds the internet.

---

#### Step 3 — Break One Request Down

The same `list_namespaces` request is timed in stages on one `pyiceberg` connection: the raw HTTP request, then parsing the JSON, then building Python objects, then the full client call. The same raw HTTP request is then timed from Rust.

```console
$ python3 bench_breakdown.py --iters 120
```

Across seven runs on the local catalog, over two days:

- **The raw HTTP request is 90% to 94% of `pyiceberg`'s call time.**
- The same HTTP request takes **269.8 to 479.7 microseconds** from Rust's HTTP library, `reqwest`, and **864.3 to 1286.4 microseconds** from Python's, `requests`.
- Everything `pyiceberg` does after the HTTP request adds **57.3 to 134.7 microseconds**.

So 85% to 90% of the difference between the two clients is the HTTP library. That percentage is calculated from the two ranges above, run by run.

---

#### 🔎 Tip: Small Differences Are Noise Here

The breakdown tool prints, next to each stage, whether the time that stage added is bigger than the normal run-to-run noise. Only JSON parsing was. How the rest of `pyiceberg`'s 57.3 to 134.7 microseconds splits up cannot be measured at this sample size.

One setting is worth knowing about. `requests` re-reads proxy settings from the environment on every call unless `trust_env=False` is set. Turning it off saved between 32.9 and 89.9 microseconds in each of five runs, but that saving was bigger than the noise in only one run.

---

#### Step 4 — Time Them Over the Internet

The same benchmark against BigLake and OneLake. Both clients use the same login token, created once before the run:

```console
$ python3 bench.py --only google-lakehouse --rounds 4 --iters 15 --storage opendal
google-lakehouse   6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
$ python3 bench.py --only microsoft-onelake --rounds 4 --iters 15 --storage opendal
microsoft-onelake  6 ops, 2 clients, 4 rounds x 15 iters = 720 samples
```

Two runs each, median time in milliseconds:

| op | BigLake rust | BigLake py | ratio | OneLake rust | OneLake py | ratio |
|---|---|---|---|---|---|---|
| list_namespaces | 102.4–103.1 | 92.2–106.7 | 0.90x–1.04x | 36.0–36.4 | 35.9–36.0 | 0.99x–1.00x |
| load_namespace | 199.4–201.6 | 199.1–200.9 | 0.99x–1.01x | 44.6–45.1 | 45.3–46.3 | 1.02x–1.03x |
| head_namespace | 198.4–200.4 | 199.2–200.0 | 0.99x–1.01x | 44.8–45.9 | 45.3–46.6 | 0.99x–1.04x |
| list_tables | 202.7–205.5 | 203.2–206.1 | 1.00x | 45.0–46.3 | 45.4–45.6 | 0.98x–1.01x |
| load_table | 296.4–297.1 | 281.9–284.3 | 0.95x–0.96x | 36.3–39.0 | 160.7–167.7 | **4.12x–4.62x** |
| head_table | 201.7–205.0 | 199.9–201.4 | 0.98x–0.99x | 53.2–54.4 | 53.4–53.8 | 0.98x–1.01x |

Apart from `load_table`, every ratio is between 0.90x and 1.04x. The local difference is under a millisecond per call, and a round trip of 36 to 200 milliseconds hides it.

On BigLake, `pyiceberg` was 4% to 5% faster on `load_table` in both runs, for a reason this test did not identify.

---

#### 🔎 Tip: BigLake Allows 75 Catalog Requests a Minute

BigLake limits catalog requests to 75 a minute per project, and answers faster bursts with HTTP 429. The benchmark discards any timing that did not return success, and `bench_breakdown.py --pace-ms` waits between requests. The limit is visible with:

```console
$ gcloud alpha services quota list --service=biglake.googleapis.com \
    --consumer=projects/<project> \
    --format="table(metric,consumerQuotaLimits[0].unit,consumerQuotaLimits[0].quotaBuckets[0].effectiveLimit)"
biglake.googleapis.com/irc_catalog_requests          1/min/{project}       75
biglake.googleapis.com/irc_read_requests             1/min/{project}       600
```

---

#### Step 5 — Compare the Two Clients' Requests

OneLake's `load_table` took 4.12x to 4.62x longer through `pyiceberg`, while every other OneLake call was even. The two clients send different requests.

`pyiceberg` sends the header `X-Iceberg-Access-Delegation: vended-credentials` by default (`catalog/rest/__init__.py:881`). It asks the catalog to include a temporary storage credential with the table. The Rust client sends no such header.

`bench_delegation.py` times the same `pyiceberg` request with and without the header:

```console
$ python3 bench_delegation.py --only microsoft-onelake --iters 40
```

```plaintext
row                                  p50       p90
GET, header sent                   146.6     235.5
GET, header removed                 38.1      41.3
whole load_table                   148.5     182.4
whole load_table, no header         36.6      42.4
```

With the header, OneLake adds a storage credential to the response and takes 108.5 ms longer. Without it, `pyiceberg`'s `load_table` takes 36.6 ms, inside the Rust client's 36.3–39.0 ms. On Polaris and BigLake the header made no measurable difference.

So `pyiceberg` pays 108.5 to 111.9 ms and gets a credential for reading the table's files. The Rust client pays nothing and gets no credential. The companion article on the Rust client covers what happens when it then tries to read the files.

---

#### Step 6 — Measure Startup Time

Startup here means starting a new process, connecting, and answering each of the six operations once. Median of five starts per client per run:

| catalog | rust | pyiceberg | python takes longer by |
|---|---|---|---|
| Polaris, local, 4 runs | 16.4–26.0 ms | 525.8–557.9 ms | 507.2–535.1 ms |
| BigLake, 2 runs | 1376.3–1410.3 ms | 1911.8–2016.7 ms | 535.5–606.4 ms |
| OneLake, 2 runs | 955.9–996.2 ms | 1723.5–1772.4 ms | 767.6–776.2 ms |

Over the internet both clients wait on the same round trips, so the ratio drops from 21.4x–33.6x locally to 1.4x on BigLake and 1.8x on OneLake. **The extra half second stays.** It matters for a CLI, a Lambda function or a short-lived agent, and hardly at all for a service that starts once.

Where the half second goes, median of five, across seven local runs:

| step | time |
|---|---|
| start Python, `python3 -c pass` | 9.0–11.2 ms |
| `import pyiceberg.catalog.rest` | a further 337.9–366.3 ms |
| connect: fetch the catalog config and log in | 6.8–12.4 ms |

Most of it is importing the library. Connecting to the catalog is the smallest part.

On OneLake the import took 338.9 and 341.4 ms, the same as locally, and fetching the config took 447.3 and 493.8 ms. Both clients fetch the config; only `pyiceberg` pays for the import.

---

#### How This Compares to Published Lambda Numbers

*Cold Starts Are Dead* measured AWS Lambda start times of **88.3 ms for Python 3.13 on arm64** (106.2 ms on x86_64) and **14.1 ms for Rust** (17.0 ms), at 512 MB, with hello-world functions and **no libraries**.

The local Python startup here is about six times that: 525.8 to 557.9 ms against 88.3 ms. The difference is mostly the 337.9 to 366.3 ms spent importing `pyiceberg`.

---

#### Compare and Contrast

| | 🦀 iceberg-catalog-rest | 🐍 pyiceberg |
|---|---|---|
| `list_namespaces`, local, µs | 🥇 301.3–768.1 | 883.2–1479.4 |
| Small calls over the internet | tie, 0.90x–1.04x | tie |
| HTTP library | 🥇 `reqwest` | `requests`, 85%–90% of the difference |
| Extra startup time | 🥇 — | 507.2–776.2 ms |
| Of which, importing the library | — | 337.9–366.3 ms |
| `load_table` on OneLake, ms | 🥇 36.3–39.0, no credential | 160.7–167.7, with a storage credential |
| Requests storage credentials | no | 🥇 yes, by default |
| Endpoints supported | 13 of 25 | 🥇 21 of 25 |

---

#### So, Which One?

**For a long-running service, pick by features.** Over the internet the per-call difference disappears, and startup happens once. Choose the client that supports the operations and login method you need.

**For a CLI, a Lambda function or a short-lived agent, startup decides it.** Python adds half a second or more per process on every catalog tested.

---

#### Summary

The goal of this article was to measure how fast the Rust and Python Iceberg REST clients are. The key to the solution was running both as separate processes against the same catalogs, timing startup separately, and breaking one request down to see where the time goes. The results were:

- 🟢 Locally, Rust is 1.90x to 4.29x faster on small calls, and 85% to 90% of that difference is the HTTP library
- 🟢 Over the internet the difference disappears: 0.90x to 1.04x on BigLake and OneLake
- ⚠️ Python starts 507.2 to 776.2 ms slower on every catalog, mostly from importing the library (337.9 to 366.3 ms locally)
- ⚠️ OneLake's 4x on `load_table` comes from `pyiceberg` requesting a storage credential by default, which the Rust client never does
- ❌ `pyiceberg` was 4% to 5% faster on BigLake's `load_table`, cause unknown

Scope: `iceberg-catalog-rest` 0.10.1 in a release build with `rustc` 1.98.1 and `rustls` 0.23.45, and `pyiceberg` 0.12.0 on Python 3.14.7 with `requests` 2.34.2 over OpenSSL 3.5.7, on one 16-core Linux host. Apache Polaris 1.7.0 in Docker on the same machine with local file storage: four benchmark runs on 2026-09-17 and 2026-09-18, and seven breakdown runs of 80 to 120 requests each. Google BigLake and Microsoft OneLake over the internet on 2026-09-18: two benchmark runs each. Each benchmark run is 720 timed calls across six read operations; startup is the median of five starts per client per run. No writes were timed. Managed catalogs do not report a version, and each internet run is one region at one point in time.

The strategy for comparing two Iceberg REST clients by speed was validated with an incremental step by step approach.

---

#### References

* [lakehouse-iceberg-2026 | GitHub](https://github.com/xbill9/lakehouse-iceberg-2026)
* [apache/iceberg-rust](https://github.com/apache/iceberg-rust)
* [apache/iceberg-python](https://github.com/apache/iceberg-python)
* [Cold Starts Are Dead](https://dev.to/aws/cold-starts-are-dead-5fod)
* [querygraph/catalog-bench](https://github.com/querygraph/catalog-bench)
* [Seven Iceberg REST Catalogs: What They Declare, and What They Serve](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
