---
title: "Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't"
published: false
description: "Four read-only Apache Iceberg tools bound into Google ADK, AWS Strands and Microsoft Agent Framework, run against five catalogs, 250 timed runs. Building the agent ports and running it does not; speed follows the model and how much it writes; the storage wiring under the tools is the per-cloud work."
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

**Speed follows the model, and how much it writes.** As configured here, the
three agents are 4.03x apart at the median (13.11s against 3.25s), with no overlap
in the middle half of their runs. But `gpt-5-mini` generates far more tokens than
Nova Micro. Per 100 generated tokens the three take 0.58 to 0.90 seconds.

**The framework adds a smaller cost.** Running the same Gemini model,
Strands took longer than ADK on both questions asked: 1.43x at the median on the
simple question, and 10.46 against 9.13 seconds on the data question -- a gap only
just above the 1.12-second noise, though slower per generated token as well.

**The per-cloud work is the storage wiring.** The tools bind unchanged, but reading
a catalog's files needs different configuration for OneLake, Glue and S3 Tables --
and when it is wrong, the catalog still answers while the data read fails with an
error that names something else.

**Every agent read its cloud's data, and one model could not count what it read.**
When the scan returned rows and left the counting to the model, Gemini under both
frameworks and `gpt-5-mini` counted correctly in all ten runs. Nova Micro counted
correctly in 1 of 10 runs at Bedrock's default decoding, and its greedy decoding gave
one wrong answer ten times. When the scan filtered in PyIceberg and returned the
count, every setup was right in every run.

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
  separate tests; its medians spread by 1.12 seconds. A difference smaller than that
  is not a finding.

It cannot test storage wiring, because Polaris keeps its table as local files.
See the [Polaris site](https://polaris.apache.org/),
[documentation](https://polaris.apache.org/docs/) and
[source](https://github.com/apache/polaris).

## How the Tests Work

Each test changes one thing and holds the rest still:

| test | what changes | what stays the same | what it answers | evidence files |
|---|---|---|---|---|
| **Test 1** | framework and model together | the catalog: Polaris | how the three agents compare | Axis A, and Axis F for Nova's decoding |
| **Test 2** | the catalog | the agent: ADK on Gemini | whether the catalog changes anything | Axis B |
| **Test 3** | framework or model, one at a time | the catalog: Polaris | which a speed difference belongs to | Axis C |
| **Test 4** | a data question, each agent on its own cloud | the question | whether each agent reads its cloud's files | Axis D |
| **Test 5** | the same data question, all four setups, counted by the engine or by the model | the table: Polaris | who answers correctly, like for like | Axis E |

**Ten runs per cell, in shuffled rounds** from a fixed seed, so a slow patch on an
endpoint lands across cells. Separation is judged on the middle half of each cell's
runs. No run failed to answer.

**Every time is warm answer time.** Each run imports its framework, builds the agent,
signs in and sends one untimed warm-up turn before the clock starts. That excludes
0.78 / 0.45 / 0.24 seconds of import for ADK / Strands / Agent Framework, and
1.25 to 1.53 seconds of first sign-in on Azure, 0.52 to 0.54 on Vertex AI and 0.06
on AWS. A long-running agent pays the imports once and sign-in only when its token
is refreshed, not on every answer. A serverless agent that scales
to zero pays them on every cold start, where Agent Framework's first sign-in alone
adds more than a second over the AWS leg.

**Tokens and model calls are recorded per answer.** Frameworks report reasoning
differently -- Strands' Gemini provider folds it into output -- so comparisons use
tokens generated, output plus reasoning.

**Every answer is scored against ground truth read straight from the catalog**, on
the answer text alone, with any `<thinking>` blocks removed. The row count must sit
beside "rows", each column must appear as a whole word, and the snapshot id and
metadata location must appear exactly. Ground truth also scans every data file, and
the row counts agree with each snapshot's summary on all five catalogs. An answer's
last stated count or largest id is the one scored, so a right number mentioned on
the way to a different final one fails. Before anything is published, the scorer
must fail planted answers that hold the right numbers without stating them, or
state them and then a different one.

## Test 1: The Three Agents, Side by Side

Three legs, Polaris, ten runs each. The models are not matched -- Bedrock's catalog
lists Nova Micro as text in, text out, where Nova Lite and Pro also take images and
video. Gemini and `gpt-5-mini` ran at their defaults, with no temperature, thinking
budget or reasoning effort set. Nova Micro ran with the greedy decoding Amazon
[recommends for Nova tool use](https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html),
temperature 0 and topK 1. That decoding is deterministic, and it matters for reading
every Nova row in this article: its ten runs return one answer, word for word, so a
Nova score is one answer repeated while its timings are ten real measurements. Run
at Bedrock's defaults instead, in a separate sitting, Nova Micro gave ten different
answers, passed every check in all ten, and took 3.27 seconds at the median against
3.31 with greedy decoding (evidence files: Axis F).

| leg | framework and model | runs passing every check | answer seconds min/med/max | tokens generated |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 10/10 | 3.15 / 3.25 / 3.32 | 564 |
| gcp | ADK, `gemini-2.5-flash` | 10/10 | 4.53 / 5.62 / 6.96 | 653.5 |
| azure | Agent Framework, `gpt-5-mini` | 10/10 | 11.74 / 13.11 / 15.61 | 1442 |

All three answer with the same three calls -- list, describe, count. The spread is
4.03x at the median, and the middle halves do not touch: AWS's upper quartile
(3.28s) sits below Google's lower (5.42s), and Google's upper (6.17s) below Azure's
lower (12.18s). Tool time is 0.12 seconds, about 2% of an answer.

Much of that spread is how much each model writes. Per 100 generated tokens, Nova
Micro took 0.58 seconds and Gemini and `gpt-5-mini` 0.90 each, so the gap between
Google's and Azure's legs is `gpt-5-mini`'s 1442 generated tokens against Gemini's
653.5.

Against a managed catalog every leg would add tool time (Test 2), which narrows
the ratio; these figures are specific to a local catalog.

## Test 2: Same Agent, Five Catalogs

ADK on Gemini against five catalogs, ten runs each. Every run passed every check.

| catalog | answer seconds min/med/max | median seconds in tools |
|---|---|---|
| apache-polaris | 4.01 / 4.50 / 6.52 | 0.12 |
| aws-s3tables | 5.53 / 6.09 / 6.29 | 0.49 |
| aws-glue | 5.17 / 6.10 / 6.71 | 0.66 |
| google-lakehouse | 5.27 / 7.35 / 8.25 | 1.42 |
| microsoft-onelake | 5.99 / 7.50 / 50.96 | 2.18 |

The catalog shows up in the tool column: 0.12 seconds against Polaris, 0.49 to 2.18
against the managed four. In total answer time BigLake (7.35 seconds) and OneLake
(7.50) sit clearly above Polaris (4.50); S3 Tables (6.09) and Glue (6.10) sit above
it by little more than the 1.12-second noise, so treat those two as close.
The slowest run, 50.96 seconds on OneLake, spent 44.88 of them in the tools. That is
distance from this machine as much as the service, and not a ranking. OneLake's
table holds 6 rows and 3 columns, loaded through the Fabric API; each answer is
scored against its own catalog.

## Test 3: Framework or Model?

Strands, unchanged except for its model object, runs `gemini-2.5-flash` through
Vertex AI beside ADK on the same model and endpoint, and beside itself on Nova
Micro. All thirty runs passed every check.

| framework | model | answer seconds min/med/max | middle half of runs | tokens generated |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 4.56 / 4.86 / 5.99 | 4.63 – 5.64 | 648.5 |
| Strands | `gemini-2.5-flash` | 6.03 / 6.96 / 8.53 | 6.42 – 7.89 | 707.5 |
| Strands | `us.amazon.nova-micro-v1:0` | 3.22 / 3.33 / 3.48 | 3.29 – 3.36 | 564 |

**Swapping the model** under Strands moved the median 2.09x, with no overlap. That
comparison also changes provider and region, Vertex AI in `us-central1` against
Bedrock in `us-east-1`.

**Swapping the framework** under Gemini moved it 1.43x (2.10 seconds), with no
overlap, and it clears the 1.12-second noise. Strands generated 707.5 tokens to
ADK's 648.5 and made no more model calls, so most of the gap is the framework's
handling of each call: per 100 generated tokens, Strands took 1.01 seconds against
ADK's 0.76.

Agent Framework ran only `gpt-5-mini`, so its figures describe that pairing. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
its `store=False` setting made a non-reasoning model fail; that was not re-tested.

## Test 4: Each Agent Reads Its Own Cloud's Data

> What is the largest id in the probe table, and how many of its rows have an id
> of 10 or more? Cite the exact table version you read.

No metadata tool can answer that: counts come from snapshot summaries and columns
from the schema. (Iceberg manifests do carry per-file column bounds -- they put the
largest id at 23 on Polaris -- but no tool exposes them.) Answering means reading
GCS, S3 or ADLS through each cloud's storage wiring. The scan tool takes a row filter
such as `id >= 10`, applies it in PyIceberg, and returns an exact count, minimum and
maximum over every matching row, so no model counts rows in its head.

| agent and catalog | largest id | rows with id of 10 or more | median answer seconds | median seconds in tools |
|---|---|---|---|---|
| ADK / Gemini on BigLake | 10/10 | 10/10 | 13.55 | 5.12 |
| Strands / Nova Micro on Glue | 10/10 | 10/10 | 6.31 | 2.08 |
| Agent Framework / `gpt-5-mini` on OneLake | 10/10 | 10/10 | 25.00 | 4.66 |

Every agent read its data: the tools print each call they receive, whatever the
framework, and every one of the thirty captures shows a scan with a filter. These
cells are not like for like --
different catalogs, regions, and a smaller OneLake table -- so correctness is
compared in Test 5.

## Test 5: The Same Data Question, Like for Like

All four setups, the same 11-row Polaris table, ten runs each -- twice. Once with the
published scan, which filters in PyIceberg and returns an exact count, minimum and
maximum; once with a scan that returns the rows only, so the model has to count them.

| framework / model | who counts | largest id | rows with id of 10 or more | median answer seconds | tokens generated |
|---|---|---|---|---|---|
| ADK / `gemini-2.5-flash` | the engine | 10/10 | 10/10 | 9.13 | 1138 |
| ADK / `gemini-2.5-flash` | the model | 10/10 | 10/10 | 10.29 | 1555.5 |
| Strands / `gemini-2.5-flash` | the engine | 10/10 | 10/10 | 10.46 | 1002 |
| Strands / `gemini-2.5-flash` | the model | 10/10 | 10/10 | 11.97 | 1352.5 |
| Strands / `us.amazon.nova-micro-v1:0` | the engine | 10/10 | 10/10 | 4.07 | 693.5 |
| Strands / `us.amazon.nova-micro-v1:0` | the model | 9/10 | 1/10 | 5.22 | 853.5 |
| Agent Framework / `gpt-5-mini` | the engine | 10/10 | 10/10 | 20.75 | 2883.5 |
| Agent Framework / `gpt-5-mini` | the model | 10/10 | 10/10 | 19.09 | 2654.5 |

Nova Micro runs at Bedrock's defaults in this table, so its ten runs are ten
different answers rather than one repeated. With greedy decoding it ran both ways
too: the engine's count right in all ten, and its own count 6 in all ten. Every
capture records the tool calls, so which scan each answer used is on record: all
fifty engine runs filtered, and no rows-only run could.

Counting by reading only works on a table this small. The rows-only scan returns at
most 100 rows, so on a real table no model can count what it cannot see. Whatever the
model, the count belongs in the engine.

**The miscount is Nova Micro's, and the engine removes it.** Gemini under both
frameworks and `gpt-5-mini` counted eleven ids correctly in every run. Nova Micro got
it right once in ten. It was not failing to read: nine of those ten runs scanned every
row, and eight of the nine still counted wrong, answering 4, 5, 7 or 11, and one
declined to answer. With the count returned by the engine it was right
in every run both ways. The runs that separate the prompt, the scan output and the
decoding are in `nova-diagnosis.txt`.

**The framework cost shows again, smaller.** On the same model with the same scan,
Strands took 10.46 seconds at the median against ADK's 9.13 -- only just above the
1.12-second noise -- and 1.03 seconds per 100 generated tokens against ADK's 0.84,
slower per token as it was in Test 3.

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

**Reading the answer** is where a data agent can quietly mislead the code around
it. Four questions matter, and the frameworks answer them differently:

| framework / model | can you see which tools it called? | does reasoning land in the answer text? |
|---|---|---|
| ADK / `gemini-2.5-flash` | yes -- each call is an event your code receives | no |
| Strands / `gemini-2.5-flash` | yes -- a `Tool #n` line is printed per call | no |
| Strands / `us.amazon.nova-micro-v1:0` | yes -- a `Tool #n` line is printed per call | yes, every time |
| Agent Framework / `gpt-5-mini` | no, unless middleware or OpenTelemetry is switched on | no |

That held in every captured run: all 100 ADK runs, all 120 Strands runs and all 40
Agent Framework runs.

- **Can you prove what the agent read?** For an agent answering from company data,
  the tool calls are the audit trail. Out of the box, ADK and Strands record each
  call and Agent Framework does not, unless middleware or OpenTelemetry is switched
  on. The table above is about the frameworks; the tools here also print every call
  they receive, which is why Tests 4 and 5 are on record for all three. A log your
  own tools write is the one that works in every framework.
- **Is the answer text only the answer?** Nova Micro writes `<thinking>` text, and
  Strands passes it through inside the answer. A dashboard, a pipeline or another
  agent that reads the output can take a number from the model's scratch work as
  its result. Strip `<thinking>` blocks before using the text.
- **Is the whole answer in the result?** Strands' `result.message` is only the last
  message of the turn. Nova Micro writes part of its answer in a message that also
  calls a tool -- the columns beside the call that counts the rows -- so the last
  message alone named the columns in none of ten greedy runs, while the turn named
  them in all ten. ADK's events and Agent Framework's `AgentResponse.text` already
  cover the whole turn; for Strands, collect the text of every assistant message
  added to `agent.messages`.
- **Is the text intact?** Strands' `str(result)` puts a line break after every text
  block, and its Gemini provider can split one answer into several blocks. Read
  through `str(result)`, three of ten Strands-on-Gemini answers to the Test 5
  question had "23" as "2", newline, "3" or similar -- a correct answer that reads as
  wrong. Join each message's text blocks with nothing between them.

Strands also streams every answer to the terminal, so code that prints the result
shows it twice; `callback_handler=None` turns that off.

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
  differences were "within a few percent". Here Strands was slower than ADK on the
  same model on both questions, 1.43x in answer time on the simple one -- both
  results say framework cost is small next to the model.
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

The README shows how to find the Foundry project endpoint from the Azure
management API.

Two things that fail quietly: install `agent-framework-core` and
`agent-framework-foundry`, not the `agent-framework` meta package, which failed to
resolve after 1,445 seconds here; and install `adlfs`, without which every OneLake
metadata call works and every scan fails.

Ask one leg against Polaris before any cloud:

```console
$ python3 run_once.py gcp --catalog apache-polaris --warm "How many rows are in the probe table?"
   -> tool: iceberg_list_tables()
   -> tool: iceberg_describe_table(table='probe_ns.probe_table')
   -> tool: iceberg_count_rows(table='probe_ns.probe_table')

<!-- cloud=gcp model=gemini-2.5-flash catalog=apache-polaris instruction=v3 catalog_calls=3 -->
The `probe_ns.probe_table` contains 11 rows. This figure is from snapshot-id 5653331815319537848, found at metadata-location file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json.

catalog calls: 3 of 8
agent seconds: 5.08 | tool seconds: 0.12
tokens: input=4660 output=161 reasoning=353 model_calls=4
warm-up seconds: 2.57
```

`--warm` sends one untimed turn first, so sign-in is not in `agent seconds`.

The header stamps cloud, model, catalog, instruction version and call count, so an
answer from an older instruction, or an agent that never called its tools, stands
out. Then capture ground truth, run the tests and publish:

```console
$ python3 capture_ground_truth.py
$ for t in A B C D E F; do python3 run_matrix.py --axis $t --repeat 10; done
$ python3 capture_runs.py && python3 failure_modes.py && python3 nova_diagnosis.py
$ python3 publish_evidence.py && (cd .. && ./check-no-identifiers.sh)
```

`publish_evidence.py` re-scores every capture from its own text, and refuses if that
disagrees with the runner or if the scorer mis-scores any planted answer -- empty,
swapped, right and then changed, or a real phrasing it once got wrong. It maps
account identifiers to pseudonyms. Every figure in this article comes from the
files it writes.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and catalogs. The key to the
solution was one implementation of four tools bound into three frameworks
unchanged, and five tests that each move one thing. The results were:

- **Building the agent ports; running it does not.** Calling, signing in and
  reading the answer differ per framework, with real traps in the last.
- **Speed follows the model and how much it writes.** 4.03x between the agents as
  configured here, 0.58 to 0.90 seconds per 100 generated tokens.
- **Framework cost is smaller.** Strands was slower than ADK on the same model on
  both questions -- 1.43x on the simple one, just above the noise on the data one --
  and slower per generated token on both.
- **The per-cloud work is storage wiring.** Once written, every agent read its
  cloud's data files.
- **One model miscounted; counting in the engine removed the error.** Left to count
  eleven ids, three setups were right in every run; Nova Micro was right in 1 of 10 at
  its default decoding. With the count computed by the scan, every setup was right in
  every run. Every run of the simple question named every column and cited the exact
  table version.

Scope:

- One machine, 2026-09-15; ten runs per cell, warm, in shuffled rounds. Enough to see
  separation, not to estimate rates.
- Every model ran at its defaults except Nova Micro, which ran with Amazon's
  recommended tool-use decoding. That decoding is deterministic: a Nova cell returns
  one answer, word for word, in all ten runs, so its correctness is one sample and its
  timing is ten. That applies to the Nova rows in Tests 1, 3 and 4. Test 5's table
  runs Nova at Bedrock's defaults instead, where ten runs are ten answers, and Axis F
  runs Test 1's question both ways.
- Agent Framework ran only `gpt-5-mini`. The model comparison in Test 3 also changes
  provider and region.
- Polaris is local and the managed catalogs are in different regions, so no time
  here compares clouds.
- Timings exclude imports and first sign-in; a serverless agent pays both on a cold
  start. Cost was not measured.
- Earlier runs are published under `evidence/superseded-runs/`, re-scored by the
  same checks.

## Why Does This Matter?

If you are building an agent that answers questions from lakehouse data, these
results change where to spend effort:

- **Choosing a framework?** Choose it for how it fits your code, your cloud and your
  observability -- not for speed. Its cost is real but small, and it was never the
  biggest number on the page.
- **Choosing a model?** It sets most of the latency, mostly through how much it
  writes. Gemini and `gpt-5-mini` counted eleven rows correctly by themselves; Nova
  Micro did not, and was right every time once the tool returned the count. Put
  aggregation in the engine. And check what a model's recommended settings do to
  your measurement: Nova's greedy decoding makes every run the same answer, so ten
  runs of it are one sample.
- **Planning a move between clouds?** Budget for the storage wiring under the tools,
  not for the agent code. Expect misleading errors the first time, and test file
  access directly, not only catalog calls.
- **Putting an agent into production?** Keep the tool calls as an audit trail, strip
  model reasoning out of answers before anything else reads them, read the answer
  text carefully, and have every answer cite the exact table version it came from --
  so that a wrong answer can be caught and checked against the same data.

The catalog layer really is portable. The work is in what sits around it.

The strategy for using one shared set of Iceberg tools across three agent
frameworks was validated with an incremental step by step approach.
