---
title: "Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't"
published: false
description: "Four read-only Apache Iceberg tools bound into Google ADK, AWS Strands and Microsoft Agent Framework, run against five catalogs, 180 timed runs. The agent code ports; speed follows the model and how much it writes; the storage wiring under the tools is the per-cloud work."
tags: iceberg, aiagents, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/iceberg-agent-three-clouds/cover.30ed1e97.jpg
---

This article provides a step by step build of one small Apache Iceberg data
agent, written three times -- in Google ADK, in AWS Strands and in Microsoft
Agent Framework -- and run against five Iceberg catalogs. Every answer is checked
against the catalog itself, so the differences between the three agents can be
measured rather than described.

https://github.com/xbill9/lakehouse-iceberg-2026

## What Is This Project Trying to Do?

All three hyperscalers now ship their own agent framework. The tables those
agents would read are increasingly in Apache Iceberg, an open table format built
so that any engine can read the same data. The data is readable from anywhere. Is
an agent that reads it portable too?

An [earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
measured the catalog side: seven Iceberg REST catalogs, and the read operations
all of them serve. This project measures the agent side. It builds a small data
analyst -- list the tables, describe one, count or read its rows, and cite the
exact table version it read -- three times:

- **Google** — ADK on `gemini-2.5-flash`, reading BigLake
- **AWS** — Strands on `us.amazon.nova-micro-v1:0`, reading Glue
- **Azure** — Agent Framework on `gpt-5-mini`, reading OneLake

The four tools and the instruction are the same Python objects in all three.
Moving this agent between clouds could cost you in three places: the code, the
behaviour -- does it answer the same way, as fast -- and the plumbing that reads a
catalog's files. Each is measured below, on 2026-09-15 (UTC), ten runs per cell.

## What Did It Find?

**Building the agent ports; running it does not.** Construction differs by three
small things: a model id string, a model object or a client object, and a
different name for the instruction. Calling the agent, signing in, and reading its
answer text are each a different job per framework.

**Speed follows the model, and how much it writes.** As each cloud ships them, the
three agents are 4.04x apart at the median (13.25s against 3.28s), with no overlap
in the middle half of their runs. But `gpt-5-mini` generates far more tokens than
Nova Micro. Per 100 generated tokens the three take 0.67 to 0.98 seconds.

**The framework effect depends on the question.** On a simple question, Strands
was 1.42x slower than ADK on the same Gemini model, at the same token count. On a
question that requires reading the data, the two were level.

**The per-cloud work is the storage wiring.** The tools bind unchanged, but reading
a catalog's files needs different configuration for OneLake, Glue and S3 Tables --
and when it is wrong, the catalog still answers while the data read fails with an
error that names something else.

**Once wired, every agent read its cloud's data, and one model could not count.**
On the same 11-row table, ADK, Agent Framework, and Strands on Gemini answered the
data question correctly in all ten runs. Strands on Nova Micro got the filtered
count right once. The miscount is the model's.

## What Is Apache Iceberg, and Why Does It Matter?

A lakehouse keeps its data as ordinary files -- usually Parquet -- in object
storage such as S3, GCS or ADLS. On their own those files are just a pile: nothing
says which make up a table, which version is current, or what happens when two
writers change it at once. Apache Iceberg is the open table format that answers
those questions, with a metadata layer over the files: a schema, the list of files
in each version, and a chain of immutable snapshots.

- **Many engines, one table.** Spark, Trino, Flink and the cloud warehouses read
  and write the same table, so the data is not copied into every tool.
- **Versions you can point at.** Every change creates a snapshot, and an answer can
  name exactly which version it came from -- which is what the agents here do.
- **Change without rewrites.** Columns and partitioning can change without
  rewriting data files.
- **A standard way in.** The REST catalog specification defines one API for finding
  tables. Google, AWS, Microsoft, Snowflake and Databricks all serve it; the
  earlier article measured seven implementations.

For developers that means one open API instead of one vendor's warehouse -- the
claim this article tests. Platform admins keep data in their own buckets and govern
access at the catalog. Data engineers and analysts get reads they can reproduce
against an exact snapshot.

Deeper dives: the [table specification](https://iceberg.apache.org/spec/), the
[REST catalog specification](https://iceberg.apache.org/rest-catalog-spec/) and its
[OpenAPI definition](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml),
and [PyIceberg](https://py.iceberg.apache.org/), the Python library these tools use.

## What Is Apache Polaris, and Why Is It Here?

Apache Polaris is an open-source implementation of the Iceberg REST catalog, run
here locally in Docker, with the same 11-row test table as three of the four
managed catalogs. It is the **control**: the catalog every agent meets before any
cloud is involved, so that a failure can be sorted into "the vendor" or "the test".
A failure against Polaris rules out the vendor; it does not rule out the model.

- **It proves the wiring** before a cloud catalog is in the path.
- **It holds the catalog still** in Tests 1, 3 and 5: no network hop, managed
  service or region in their timings.
- **It is the baseline** for the managed catalogs' tool time in Test 2.
- **It measures the noise.** ADK on Gemini against Polaris is measured in three
  separate tests; its medians spread by 0.95 seconds. A difference smaller than that
  is not a finding.

It cannot test storage wiring, because Polaris keeps its table as local files.
See the [Polaris site](https://polaris.apache.org/),
[documentation](https://polaris.apache.org/docs/) and
[source](https://github.com/apache/polaris).

## How the Tests Work

Each test changes one thing and holds the rest still:

| test | what changes | what stays the same | what it answers | evidence files |
|---|---|---|---|---|
| **Test 1** | framework and model together | the catalog: Polaris | how the three agents compare | Axis A |
| **Test 2** | the catalog | the agent: ADK on Gemini | whether the catalog changes anything | Axis B |
| **Test 3** | framework or model, one at a time | the catalog: Polaris | which a speed difference belongs to | Axis C |
| **Test 4** | a data question, each agent on its own cloud | the question | whether each agent reads its cloud's files | Axis D |
| **Test 5** | the same data question, all four setups | the table: Polaris | who can count, like for like | Axis E |

**Ten runs per cell, in shuffled rounds** from a fixed seed, so a slow patch on an
endpoint lands across cells. Separation is judged on the middle half of each cell's
runs. No run failed to answer.

**Every time is warm answer time.** Each run imports its framework, builds the agent,
signs in and sends one untimed warm-up turn before the clock starts. That excludes
0.78 / 0.45 / 0.24 seconds of import for ADK / Strands / Agent Framework, and
1.25 to 1.53 seconds of first sign-in on Azure, 0.52 to 0.54 on Vertex AI and 0.06
on AWS. A long-running agent never pays those again. A serverless agent that scales
to zero pays them on every cold start, where Agent Framework's first sign-in alone
adds more than a second over the AWS leg.

**Tokens and model calls are recorded per answer.** Frameworks report reasoning
differently -- Strands' Gemini provider folds it into output -- so comparisons use
tokens generated, output plus reasoning.

**Every answer is scored against ground truth read straight from the catalog**, on
the answer text alone, with any `<thinking>` blocks removed. The row count must sit
beside "rows", each column must appear as a whole word, and the snapshot id and
metadata location must appear exactly. Ground truth also scans every data file, and
the row counts agree with each snapshot's summary on all five catalogs. Before
anything is published, the scorer must fail a planted answer that holds the right
numbers without stating them.

## Test 1: The Three Agents, Side by Side

Three legs, Polaris, ten runs each. The models are not matched -- Bedrock's catalog
lists Nova Micro as text in, text out, where Nova Lite and Pro also take images and
video -- and each ran at its defaults, with no temperature, thinking budget or
reasoning effort set.

| leg | framework and model | runs passing every check | answer seconds min/med/max | tokens generated |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 9/10 | 2.78 / 3.28 / 3.55 | 471 |
| gcp | ADK, `gemini-2.5-flash` | 10/10 | 4.53 / 5.20 / 6.65 | 633.5 |
| azure | Agent Framework, `gpt-5-mini` | 10/10 | 11.41 / 13.25 / 15.16 | 1395 |

All three answer with the same three calls -- list, describe, count. The spread is
4.04x at the median, and the middle halves do not touch: AWS's upper quartile
(3.40s) sits below Google's lower (4.74s), and Google's upper (5.91s) below Azure's
lower (12.52s). Tool time is 0.12 seconds, about 2% of an answer.

Most of that spread is how much each model writes. Per 100 generated tokens, Nova
Micro took 0.67 seconds, Gemini 0.82 and `gpt-5-mini` 0.98. The one failed check is
a Nova Micro answer that gave the row count and table version but never listed the
columns.

Against a managed catalog every leg would add tool time (Test 2), which narrows
the ratio; these figures are specific to a local catalog.

## Test 2: Same Agent, Five Catalogs

ADK on Gemini against five catalogs, ten runs each. Every run passed every check.

| catalog | answer seconds min/med/max | median seconds in tools |
|---|---|---|
| apache-polaris | 4.76 / 5.63 / 7.40 | 0.14 |
| aws-s3tables | 5.53 / 6.21 / 6.97 | 0.49 |
| aws-glue | 5.90 / 6.43 / 7.18 | 0.69 |
| google-lakehouse | 6.43 / 7.37 / 8.23 | 1.40 |
| microsoft-onelake | 6.36 / 7.51 / 16.93 | 1.79 |

The catalog shows up in the tool column: 0.14 seconds against Polaris, 0.49 to 1.79
against the managed four. That is distance from this machine as much as the
service, and not a ranking. OneLake's table holds 6 rows and 3 columns, loaded
through the Fabric API; each answer is scored against its own catalog.

## Test 3: Framework or Model?

Strands, unchanged except for its model object, runs `gemini-2.5-flash` through
Vertex AI beside ADK on the same model and endpoint, and beside itself on Nova
Micro. All thirty runs passed every check.

| framework | model | answer seconds min/med/max | middle half of runs | tokens generated |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 4.89 / 6.15 / 7.31 | 5.76 – 6.71 | 705.5 |
| Strands | `gemini-2.5-flash` | 6.63 / 8.75 / 11.51 | 6.94 – 9.25 | 690.5 |
| Strands | `us.amazon.nova-micro-v1:0` | 3.00 / 3.18 / 4.62 | 3.06 – 3.45 | 461.5 |

**Swapping the model** under Strands moved the median 2.75x, with no overlap. That
comparison also changes provider and region, Vertex AI in `us-central1` against
Bedrock in `us-east-1`.

**Swapping the framework** under Gemini moved it 1.42x (2.60 seconds), with no
overlap and the same number of tokens generated -- and Strands made no more model
calls than ADK. On this question the gap is the framework's handling of each call,
and it clears the 0.95-second noise. On the data question in Test 5 it disappears.

Agent Framework ran only `gpt-5-mini`, so its figures describe that pairing. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
its `store=False` setting made a non-reasoning model fail; that was not re-tested.

## Test 4: Each Agent Reads Its Own Cloud's Data

> What is the largest id in the probe table, and how many of its rows have an id
> of 10 or more? Cite the exact table version you read.

None of the four tools can answer that without scanning: counts come from snapshot
summaries and columns from the schema. (Iceberg manifests do carry per-file column
bounds -- they put the largest id at 23 on Polaris -- but no tool exposes them.)
Answering means reading GCS, S3 or ADLS through each cloud's storage wiring.

| agent and catalog | largest id | rows with id of 10 or more | median answer seconds | median seconds in tools |
|---|---|---|---|---|
| ADK / Gemini on BigLake | 10/10 | 10/10 | 15.42 | 3.42 |
| Strands / Nova Micro on Glue | 9/10 | 1/10 | 6.01 | 1.64 |
| Agent Framework / `gpt-5-mini` on OneLake | 10/10 | 10/10 | 26.48 | 4.49 |

Every agent read its data: ADK and Strands log each scan, and Agent Framework's
answers name values no metadata tool returns. But these cells are not like for
like -- different catalogs, regions, and a smaller OneLake table -- so correctness
is compared in Test 5.

## Test 5: The Same Data Question, Like for Like

All four setups, the same 11-row Polaris table, ten runs each.

| framework / model | largest id | rows with id of 10 or more | median answer seconds | tokens generated |
|---|---|---|---|---|
| ADK / `gemini-2.5-flash` | 10/10 | 10/10 | 12.36 | 1635.5 |
| Strands / `gemini-2.5-flash` | 10/10 | 10/10 | 12.16 | 1359 |
| Strands / `us.amazon.nova-micro-v1:0` | 7/10 | 1/10 | 4.53 | 728.5 |
| Agent Framework / `gpt-5-mini` | 10/10 | 10/10 | 21.54 | 3050.5 |

**The miscount is Nova Micro's.** The same Strands agent counted correctly in all ten
runs on Gemini, and in one on Nova Micro. Its wrong answers gave counts such as 5 and
11, or said it could not count.

**The framework gap from Test 3 is gone.** ADK and Strands on Gemini are level here
(12.36s against 12.16s, with overlapping middle halves), so that 1.42x is not a
constant cost of either framework.

## How Are the Three Agents Different?

The instruction is one string; the four tools are async Python functions with
typed arguments and docstrings; the budget of eight catalog calls lives inside the
tools. None of that changed. Everything around it did.

**Building it** takes a model id string (ADK), a model object (Strands) or a chat
client holding an endpoint and credential (Agent Framework), and the instruction is
`instruction`, `system_prompt` or `instructions`. Strands wraps each tool in
`tool()`. ADK re-resolves a bare model id to a new client on every run; resolving it
once keeps the client, and its token, alive.

**Running it** is three jobs. ADK needs a runner, a session and a loop over events.
Strands is called like a function, and keeps the conversation on the agent until
`agent.messages` is cleared. Agent Framework is awaited.

**Signing in** uses Application Default Credentials for ADK, the boto credential
chain for Strands -- which needs `botocore[crt]` after `aws login`, while the CLI
works without it -- and `DefaultAzureCredential` for Agent Framework, the slowest
first sign-in of the three.

**Reading the answer** is where the traps are:

| framework / model | shows each tool call | reasoning inside the answer |
|---|---|---|
| ADK / `gemini-2.5-flash` | 90/90 | 0/90 |
| Strands / `gemini-2.5-flash` | 20/20 | 0/20 |
| Strands / `us.amazon.nova-micro-v1:0` | 40/40 | 40/40 |
| Agent Framework / `gpt-5-mini` | 0/30 | 0/30 |

- **Tool calls.** ADK returns each call as an event and Strands prints a `Tool #n`
  line; Agent Framework shows only the final answer unless middleware or
  OpenTelemetry is switched on. Without them, what an agent read can only be
  inferred from what it said.
- **Reasoning in the answer.** Nova Micro's `<thinking>` text arrives inside the
  answer on Strands. Anything that reads output automatically can take a number
  from the reasoning as the result.
- **Text blocks joined with line breaks.** Strands' `str(result)` adds a line break
  after every text block, and its Gemini provider can split one answer into several
  blocks. In an earlier run of Test 5, three Strands-on-Gemini answers came back
  with breaks inside a word or number -- "23" as "2", newline, "3" -- and none of
  its Nova Micro answers did. Join `result.message["content"]` text blocks directly.
- **Printing.** Strands also streams every answer to the terminal, so printing the
  result shows it twice; `callback_handler=None` turns that off.

## Storage Wiring Per Catalog

Signing the catalog calls and reading the files the catalog points at take
different configuration, and it lives inside the tool, written once per catalog:
`FsspecFileIO` and an account host for OneLake, local credentials for Glue, the
vended credentials S3 Tables' managed bucket requires. It differs even between two
catalogs on the same cloud. Three wrong configurations, each reproduced with the
catalog call succeeding immediately before the data call fails:

```console
$ # A. OneLake, no ADLS configuration at all (PyArrowFileIO, no adls.* properties)
CATALOG ERROR while scanning dbo.probe_table: TypeError: __init__() takes exactly 1 positional argument (0 given).

$ # B. OneLake, ADLS credential set but PyArrowFileIO instead of fsspec
CATALOG ERROR while scanning dbo.probe_table: OSError: GetProperties failed for
'https://onelake.blob.core.windows.net/...' Cannot initialise an ObjectInp.

$ # C. Glue, SigV4 for the catalog but no local S3 credentials
CATALOG ERROR while scanning probe_ns.probe_table: OSError: ... AWS Error
ACCESS_DENIED during HeadObject operation
```

B builds a hostname that does not exist, because PyArrow ignores
`adls.account-host`; C is `ACCESS_DENIED` on a bucket the caller owns, because
pyiceberg used the catalog's vended credentials. None of the three errors names the
missing setting. An agent that reads Iceberg is portable at the catalog; at the
files, it is configured.

## How Does This Compare to Other Work?

A September 2026 search found related work on each side, and none that builds the
same agent in the three hyperscalers' frameworks, reads several Iceberg REST
catalogs, and scores answers against ground truth.

- **Framework benchmarks.** [LaunchDarkly](https://launchdarkly.com/docs/tutorials/agent-graph-experiments)
  ran LangGraph, Strands, the OpenAI Agents SDK and ADK on one agent graph with the
  model pinned, over 36 runs with an LLM judge: Strands was fastest, and most
  differences were "within a few percent". Here the framework gap was 1.42x on one
  question and absent on another -- both results say framework cost is small next to
  the model, and not a constant.
- **Data-agent benchmarks.** [DAB](https://arxiv.org/abs/2603.20576),
  [FDABench](https://arxiv.org/abs/2509.02473) and
  [KramaBench](https://arxiv.org/abs/2506.06541) measure answer correctness over
  databases and data lakes; DAB's best model reached 38% pass@1. They vary model and
  task; this holds the task simple and varies framework and catalog.
- **Agent latency.** [Bian et al.](https://arxiv.org/abs/2510.16276) found
  environment latency up to 53.7% of the total in web agents. Catalog time here was
  about 2% locally and larger against managed catalogs, which is why it is recorded
  separately.
- **Agents over Iceberg.** An [AWS Labs MCP server for S3 Tables](https://github.com/awslabs/mcp/tree/main/src/s3-tables-mcp-server),
  [MCP-over-Iceberg patterns](https://iceberglakehouse.com/iceberg/iceberg-mcp/) and
  a [multi-cloud lakehouse architecture](https://aws.amazon.com/blogs/big-data/multi-cloud-lakehouse-architecture-on-aws-for-agentic-ai-part-1-architecture-and-best-practices/)
  exist; none publish correctness or latency measurements.

This builds on the [catalog side](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
and the [framework side](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc).

## Where Do I Start?

The strategy for building a portable Iceberg agent is an incremental step by step
approach. First, the environment is set up and Polaris is brought up. Then each leg
answers one question against Polaris, ground truth is captured, the tests run, and
the evidence is published. Full detail is in
[`iceberg-agent/README.md`](https://github.com/xbill9/lakehouse-iceberg-2026/blob/main/iceberg-agent/README.md).

## Build It Yourself

You need Python 3.14, Docker, Vertex AI on a Google Cloud project, Bedrock access
to Nova Micro in `us-east-1`, and a Foundry project with a `gpt-5-mini` deployment.
The managed catalogs are optional; the earlier article brings each one up.

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-agent
$ python3 -m venv .venv && . .venv/bin/activate
$ pip install -r ../iceberg-conformance/requirements.txt -r requirements.txt
$ (cd ../iceberg-conformance && cp catalogs.example.yaml catalogs.yaml && ./polaris-up.sh)
$ export PYTHONPATH=../iceberg-conformance ICEBERG_CATALOGS_FILE=../iceberg-conformance/catalogs.yaml
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t AWS_REGION=us-east-1
$ export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_LOCATION=us-central1 GOOGLE_CLOUD_PROJECT=<your-project>
$ export FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
```

Two things that fail quietly: install `agent-framework-core` and
`agent-framework-foundry`, not the `agent-framework` meta package, which failed to
resolve after 1,445 seconds here; and install `adlfs`, without which every OneLake
metadata call works and every scan fails.

Ask one leg against Polaris before any cloud:

```console
$ python3 run_once.py gcp --catalog apache-polaris "How many rows are in the probe table?"
   -> tool: iceberg_list_tables()
   -> tool: iceberg_describe_table(table='probe_ns.probe_table')
   -> tool: iceberg_count_rows(table='probe_ns.probe_table')

<!-- cloud=gcp model=gemini-2.5-flash catalog=apache-polaris instruction=v3 catalog_calls=3 -->
The `probe_ns.probe_table` contains 11 rows. This count is exact for snapshot-id 5653331815319537848, from metadata-location file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json.

catalog calls: 3 of 8
agent seconds: 6.75 | tool seconds: 0.32
```

The header stamps cloud, model, catalog, instruction version and call count, so an
answer from an older instruction, or an agent that never called its tools, stands
out. Then capture ground truth, run the tests and publish:

```console
$ python3 capture_ground_truth.py
$ for t in A B C D E; do python3 run_matrix.py --axis $t --repeat 10; done
$ python3 publish_evidence.py && (cd .. && ./check-no-identifiers.sh)
```

`publish_evidence.py` re-scores every capture from its own text, refuses if that
disagrees with the runner or if the scorer passes a planted empty answer, and maps
account identifiers to pseudonyms. Every figure in this article comes from the
files it writes.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and catalogs. The key to the
solution was one implementation of four tools bound into three frameworks
unchanged, and five tests that each move one thing. The results were:

- **Building the agent ports; running it does not.** Calling, signing in and
  reading the answer differ per framework, with real traps in the last.
- **Speed follows the model and how much it writes.** 4.04x between the agents as
  shipped, 0.67 to 0.98 seconds per 100 generated tokens.
- **Framework cost is real but not constant.** Strands was 1.42x slower than ADK on
  one question at equal tokens, and level on another.
- **The per-cloud work is storage wiring.** Once written, every agent read its
  cloud's data files.
- **Correctness belongs to the model.** On the same table, every setup counted the
  data correctly except Nova Micro; on the simple question, every run but one named
  every column, and every run cited the exact table version.

Scope:

- One machine, 2026-09-15, every model at its defaults; 180 timed runs, ten per
  cell, warm, in shuffled rounds. Enough to see separation, not to estimate rates.
- Agent Framework ran only `gpt-5-mini`. The model comparison in Test 3 also changes
  provider and region.
- Polaris is local and the managed catalogs are in different regions, so no time
  here compares clouds.
- Timings exclude imports and first sign-in; a serverless agent pays both on a cold
  start. Cost was not measured.
- Earlier runs are published under `evidence/superseded-runs/`, re-scored by the
  same checks.

The strategy for using one shared set of Iceberg tools across three agent
frameworks was validated with an incremental step by step approach.
