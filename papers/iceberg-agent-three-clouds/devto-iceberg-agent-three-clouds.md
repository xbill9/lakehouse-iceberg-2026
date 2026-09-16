---
title: "Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't"
published: false
description: "Four read-only Apache Iceberg tools bound into Google ADK, AWS Strands and Microsoft Agent Framework, run against five catalogs, 360 timed runs. Building the agent ports and running it does not; speed follows the model and how much it writes; the storage wiring under the tools is the per-cloud work."
tags: iceberg, aiagents, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/iceberg-agent-three-clouds/cover.30ed1e97.jpg
---

This article is a step by step build of one small Apache Iceberg data agent, written
three times: in Google ADK, in AWS Strands and in Microsoft Agent Framework. Each
version runs against five Iceberg catalogs.

Every answer is checked against the catalog itself, so the differences between the
three agents are measured rather than described.

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
catalog's files. Each is measured below, on 2026-09-15 (UTC), ten runs per cell and
twenty in Test 5.

## What Did It Find?

**Building the agent ports; running it does not.** Construction differs by one
argument and one keyword. Calling the agent, signing in and reading its answer are
three different jobs per framework.

**Speed follows the model, and how much it writes.** The three agents sit 3.72x apart
at the median, 12.36s against 3.33s, with no overlap in the middle half of their runs.
Per 100 generated tokens they take 0.59 to 0.97 seconds. `gpt-5-mini` is slowest
because it writes the most.

**The framework adds a smaller cost.** On the same Gemini model, Strands was slower
than ADK on both questions: 1.52x on the simple one, 10.86s against 7.89s on the data
one. It was slower per generated token in both.

**The per-cloud work is the storage wiring.** The tools bind unchanged, but reading a
catalog's files needs its own configuration for OneLake, Glue and S3 Tables. Get it
wrong and the catalog still answers while the data read fails, with an error naming
something else.

**Every agent read its own cloud's Iceberg data, and they all answered alike.** Each
leg scanned GCS, S3 or ADLS through its own catalog and cited the exact snapshot. All
four setups gave the largest id and the filtered count in all twenty runs. That holds
because the scan filters and counts in PyIceberg.

## What Is Apache Iceberg, and Why Does It Matter?

A lakehouse keeps its data as ordinary files, usually Parquet, in object storage such
as S3, GCS or ADLS.

On their own those files are a pile. Nothing says which of them make up a table,
which version is current, or what happens when two writers change it at once.

Apache Iceberg answers those questions with a metadata layer over the files: a
schema, the list of files in each version, and a chain of immutable snapshots.

- **Many engines, one table.** Spark, Trino, Flink and the cloud warehouses read
  and write the same table, so the data is not copied into every tool.
- **Versions you can point at.** Every change creates a snapshot, so an answer can
  name exactly which version it came from. That is what the agents here do.
- **Change without rewrites.** Columns and partitioning can change without
  rewriting data files.
- **A standard way in.** The REST catalog specification defines one API for finding
  tables. Google, AWS, Microsoft, Snowflake and Databricks all serve it; the
  earlier article measured seven implementations.

For developers that means one open API instead of one vendor's warehouse, which is
the claim this article tests. Platform admins keep data in their own buckets and
govern access at the catalog. Analysts get reads they can reproduce against an exact
snapshot.

Deeper dives: the [table specification](https://iceberg.apache.org/spec/), the
[REST catalog specification](https://iceberg.apache.org/rest-catalog-spec/) and its
[OpenAPI definition](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml),
and [PyIceberg](https://py.iceberg.apache.org/), the Python library these tools use.

## What Is Apache Polaris, and Why Is It Here?

Apache Polaris is an open-source implementation of the Iceberg REST catalog. It runs
locally in Docker here, holding the same 11-row test table as three of the four
managed catalogs.

It is the **control**: the catalog every agent meets before any cloud is involved. A
failure against Polaris rules out the vendor. It does not rule out the model.

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

| test | what changes | held still | what it answers | axis |
|---|---|---|---|---|
| 1 | framework and model | Polaris | how the three agents compare | A, F |
| 2 | the catalog | ADK on Gemini | whether the catalog matters | B |
| 3 | framework or model, one at a time | Polaris | which one a speed gap belongs to | C |
| 4 | each agent on its own cloud | the question | whether it reads its cloud's files | D |
| 5 | all four setups, one data question | Polaris | who answers correctly, like for like | E |

**Ten runs per cell, twenty in Test 5**, in shuffled rounds from a fixed seed, so a
slow patch on an endpoint lands across cells. Separation is judged on the middle half
of each cell's runs. No run failed to answer.

**Every time is warm answer time.** Each run imports its framework, builds the agent,
signs in, and sends one untimed warm-up turn before the clock starts.

That excludes 0.78 / 0.45 / 0.24 seconds of import for ADK / Strands / Agent
Framework. It also excludes the first sign-in: 1.25 to 1.53 seconds on Azure, 0.52 to
0.54 on Vertex AI, 0.06 on AWS.

A long-running agent pays those once. A serverless agent that scales to zero pays
them on every cold start.

**Tokens and model calls are recorded per answer.** Frameworks report reasoning
differently, so comparisons use tokens generated: output plus reasoning.

**Every answer is scored against ground truth read straight from the catalog.**
Scoring reads the answer text alone. The row count must sit beside "rows", each
column must appear as a whole word, and the snapshot id and metadata location must
match exactly.

Two rules keep that honest. An answer is scored on the last count or largest id it
states, so a right number on the way to a wrong one fails. And the scorer must fail
planted answers before anything publishes: empty ones, swapped ones, and real
phrasings it once got wrong.

## Test 1: The Three Agents, Side by Side

Three legs, Polaris, ten runs each. The models are not matched: Bedrock lists Nova
Micro as text in, text out, where Nova Lite and Pro also take images and video.

Gemini and `gpt-5-mini` ran at their defaults. Nova Micro ran with the greedy decoding
Amazon [recommends for Nova tool use](https://docs.aws.amazon.com/nova/latest/userguide/prompting-tool-troubleshooting.html),
temperature 0 and topK 1.

That decoding is deterministic, which matters for every Nova cell here. The runs in a
cell return one answer, word for word, so a Nova score is one answer repeated. Its
timings are still real measurements.

Axis F ran the same question at Bedrock's defaults. Nova Micro gave ten different
answers, passed every check in all ten, and took 3.17 seconds at the median against
3.46 with greedy decoding.

| leg | framework and model | runs passing every check | answer seconds min/med/max | tokens generated |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 10/10 | 3.21 / 3.33 / 3.58 | 564 |
| gcp | ADK, `gemini-2.5-flash` | 10/10 | 4.88 / 5.80 / 6.72 | 712 |
| azure | Agent Framework, `gpt-5-mini` | 10/10 | 10.04 / 12.36 / 17.37 | 1155.5 |

All three answer with the same three calls -- list, describe, count. The spread is
3.72x at the median, and the middle halves do not touch: AWS's upper quartile
(3.38s) sits below Google's lower (5.37s), and Google's upper (6.18s) below Azure's
lower (11.59s). Tool time is 0.12 seconds, about 2% of an answer.

Much of that spread is how much each model writes. Per 100 generated tokens, Nova
Micro took 0.59 seconds, Gemini 0.82 and `gpt-5-mini` 0.97, so the gap between
Google's and Azure's legs is `gpt-5-mini`'s 1155.5 generated tokens against Gemini's
712.

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
against the managed four.

In total answer time, BigLake (7.35 seconds) and OneLake (7.50) sit clearly above
Polaris (4.50). S3 Tables (6.09) and Glue (6.10) clear it by little more than the
1.30-second noise, so treat those two as close.

The slowest run, 50.96 seconds on OneLake, spent 44.88 of them in the tools. That is
distance from this machine as much as the service, and not a ranking. OneLake's table
holds 6 rows and 3 columns; each answer is scored against its own catalog.

## Test 3: Framework or Model?

Strands, unchanged except for its model object, runs `gemini-2.5-flash` through
Vertex AI beside ADK on the same model and endpoint, and beside itself on Nova
Micro. All thirty runs passed every check.

| framework | model | answer seconds min/med/max | middle half of runs | tokens generated |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 4.25 / 4.88 / 5.84 | 4.39 – 5.46 | 608.5 |
| Strands | `gemini-2.5-flash` | 5.57 / 7.44 / 8.53 | 6.83 – 7.95 | 624.5 |
| Strands | `us.amazon.nova-micro-v1:0` | 3.24 / 3.34 / 3.70 | 3.29 – 3.46 | 564 |

**Swapping the model** under Strands moved the median 2.23x, with no overlap. That
comparison also changes provider and region, Vertex AI in `us-central1` against
Bedrock in `us-east-1`.

**Swapping the framework** under Gemini moved it 1.52x (2.55 seconds), with no
overlap, and it clears the 1.30-second noise. Strands generated 624.5 tokens to ADK's
608.5 and made no more model calls.

So most of the gap is the framework's handling of each call. Per 100 generated
tokens, Strands took 1.09 seconds against ADK's 0.82.

Agent Framework ran only `gpt-5-mini`, so its figures describe that pairing. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
its `store=False` setting made a non-reasoning model fail; that was not re-tested.

## Test 4: Each Agent Reads Its Own Cloud's Data

Tests 1 to 3 ask what the catalog's metadata already knows. This one does not. Each
agent is asked:

> What is the largest id in the probe table, and how many of its rows have an id
> of 10 or more? Cite the exact table version you read.

Counts come from snapshot summaries and columns from the schema; neither holds a
filtered count. Answering means reading the data files -- GCS, S3 or ADLS -- through
each cloud's storage wiring.

The scan takes a row filter such as `id >= 10`, applies it in PyIceberg, and returns
an exact count with the minimum and maximum over every matching row.

| agent and catalog | largest id | rows with id of 10 or more | median answer seconds | median seconds in tools |
|---|---|---|---|---|
| ADK / Gemini on BigLake | 10/10 | 10/10 | 13.28 | 5.00 |
| Strands / Nova Micro on Glue | 10/10 | 10/10 | 6.25 | 2.07 |
| Agent Framework / `gpt-5-mini` on OneLake | 10/10 | 10/10 | 24.35 | 5.09 |

Every agent read its data: the tools print each call they receive, whatever the
framework, and every one of the thirty captures shows a scan with a filter.

Glue's 2.07 seconds in the tools is the lowest of the three, and that is the read
path rather than the agent: in Test 2, where the catalog is the only thing that
changes, Glue costs 0.66 seconds against BigLake's 1.42 and OneLake's 2.18.

These cells are not like for like -- different catalogs, regions, and a smaller
OneLake table -- so correctness is compared in Test 5.

## Test 5: The Same Data Question, Like for Like

All four setups, the same 11-row Polaris table, twenty runs each. The scan applies
the filter in PyIceberg and returns the exact count, so no model does arithmetic over
rows.

| framework / model | largest id | rows with id of 10 or more | median answer seconds | tokens generated |
|---|---|---|---|---|
| Strands / `us.amazon.nova-micro-v1:0` | 20/20 | 20/20 | 3.69 | 540 |
| ADK / `gemini-2.5-flash` | 20/20 | 20/20 | 7.89 | 997.5 |
| Strands / `gemini-2.5-flash` | 20/20 | 20/20 | 10.86 | 1094 |
| Agent Framework / `gpt-5-mini` | 20/20 | 20/20 | 19.32 | 2720.5 |

Every capture records the tool calls, so which scan each answer used is on record:
all eighty runs above filtered, and every answer quoted the count the scan returned.

**Design the tool so the engine answers.** Rerun the same twenty runs with a scan
that returns rows and no count, and the answers stop agreeing. Gemini under both
frameworks and `gpt-5-mini` still counted correctly 20 of 20. Nova Micro got none
right under greedy decoding -- one wrong answer, repeated -- and 4 of 20 at
Bedrock's defaults.

Counting by reading cannot scale anyway, since the scan returns at most 100 rows. A
filter and an exact count belong in PyIceberg, whatever model is driving.
`nova-diagnosis.txt` has the runs behind that.

**The framework cost shows again, smaller.** On the same model and the same scan,
Strands took 10.86 seconds at the median against ADK's 7.89. That clears the
1.30-second noise.

Per 100 generated tokens it was 0.99 seconds against 0.79, slower per token as in
Test 3.

## How Are the Three Agents Different?

The instruction is one string; the four tools are async Python functions with
typed arguments and docstrings; the budget of eight catalog calls lives inside the
tools. None of that changed. Everything around it did.

**Building it** differs by one argument. ADK takes a model id string, Strands a model
object, Agent Framework a chat client holding an endpoint and credential. The
instruction is `instruction`, `system_prompt` or `instructions`.

Two traps live here. Strands wants each tool wrapped in `tool()`. ADK re-resolves a
bare model id to a new client on every run, so resolve it once and the client, and
its token, stay alive.

**Running it** is three different jobs. ADK needs a runner, a session and a loop over
events. Strands is called like a function, and keeps the conversation until
`agent.messages` is cleared. Agent Framework is awaited.

**Signing in** uses Application Default Credentials for ADK, the boto chain for
Strands and `DefaultAzureCredential` for Agent Framework. Azure's first sign-in is
the slowest of the three. Strands needs `botocore[crt]` after `aws login`, though the
CLI works without it.

**Reading the answer** is where a data agent quietly misleads the code around it.
Four questions matter, and the frameworks answer them differently:

| framework / model | can you see which tools it called? | where does the model's reasoning go? |
|---|---|---|
| ADK / `gemini-2.5-flash` | yes -- each call is an event your code receives | a separate field |
| Strands / `gemini-2.5-flash` | yes -- a `Tool #n` line is printed per call | a separate field |
| Strands / `us.amazon.nova-micro-v1:0` | yes -- a `Tool #n` line is printed per call | into the answer text, as `<thinking>` |
| Agent Framework / `gpt-5-mini` | no -- no tool call appeared in any of its 60 captures | a separate field |

That held in every captured run: all 120 ADK runs, all 180 Strands runs and all 60
Agent Framework runs. Only one model puts reasoning where a caller will read it, so
the harness strips `<thinking>` on every leg and the answers below are what a caller
receives.

- **Log the tool calls yourself.** ADK and Strands report each call; Agent Framework
  reported none in any of its 60 runs. The tools here print every call they receive,
  so the audit trail works the same on all three.
- **Strip reasoning before anything reads the answer.** Nova Micro writes its scratch
  work as `<thinking>` text, and Strands passes text through. Gemini's and
  `gpt-5-mini`'s reasoning never reaches the answer. Left in, it leaks the agent's
  instruction and figures the model discarded. This harness strips it on every leg.
- **Take the whole turn, not the last message.** Strands' `result.message` holds only
  the final message, and Nova Micro puts part of its answer beside a tool call.
  Collect every assistant message; ADK and Agent Framework already do.
- **Join text blocks with nothing between them.** Strands' `str(result)` inserts a
  line break after each block. That split "23" into "2" and "3" in three of ten Gemini
  answers: a right answer that reads as wrong.

Strands also streams every answer to the terminal, so code that prints the result
shows it twice; `callback_handler=None` turns that off.

## Storage Wiring Per Catalog

Signing the catalog calls and reading the files it points at need different
configuration. That configuration lives inside the tool, written once per catalog:
`FsspecFileIO` and an account host for OneLake, local credentials for Glue, vended
credentials for S3 Tables' managed bucket.

It differs even between two catalogs on the same cloud. Here are three wrong
configurations, each with the catalog call succeeding immediately before the data
call fails:

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
  ran LangGraph, Strands, the OpenAI Agents SDK and ADK on one agent graph, model
  pinned, 36 runs, judged by an LLM. Strands came out fastest, most differences
  "within a few percent". Here Strands was the slower of the two on both questions.
  Both results put framework cost well below model cost.
- **Data-agent benchmarks.** [DAB](https://arxiv.org/abs/2603.20576),
  [FDABench](https://arxiv.org/abs/2509.02473) and
  [KramaBench](https://arxiv.org/abs/2506.06541) score answers over databases and
  data lakes. DAB's best model reached 38% pass@1. They vary model and task; this
  keeps the task simple and varies framework and catalog.
- **Agent latency.** [Bian et al.](https://arxiv.org/abs/2510.16276) found
  environment latency up to 53.7% of the total in web agents. Catalog time here was
  about 2% locally, and more against managed catalogs. That is why it is recorded
  separately.
- **Agents over Iceberg.** There is an [AWS Labs MCP server for S3 Tables](https://github.com/awslabs/mcp/tree/main/src/s3-tables-mcp-server),
  [MCP-over-Iceberg patterns](https://iceberglakehouse.com/iceberg/iceberg-mcp/) and
  a [multi-cloud lakehouse architecture](https://aws.amazon.com/blogs/big-data/multi-cloud-lakehouse-architecture-on-aws-for-agentic-ai-part-1-architecture-and-best-practices/).
  None publish correctness or latency measurements.

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

Two things fail quietly here. Install `agent-framework-core` and
`agent-framework-foundry`, not the `agent-framework` meta package, which failed to
resolve after 1,445 seconds.

Install `adlfs` as well. Without it every OneLake metadata call works and every scan
fails.

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

`publish_evidence.py` re-scores every capture from its own text. It refuses to publish
if that disagrees with the runner, or if the scorer mis-scores a planted answer:
empty, swapped, right and then changed, or a real phrasing it once got wrong.

It also maps account identifiers to pseudonyms. Every figure in this article comes
from the files it writes.

## Summary

The question was whether a read-only Apache Iceberg agent ports across frameworks and
catalogs. One implementation of four tools went into three frameworks unchanged, and
five tests each moved one thing.

- **Building the agent ports; running it does not.** Calling, signing in and reading
  the answer differ per framework. The traps are in the last one.
- **Speed follows the model and how much it writes.** 3.72x between the agents,
  0.59 to 0.97 seconds per 100 generated tokens.
- **Framework cost is smaller.** Strands was slower than ADK on both questions, and
  slower per generated token in both.
- **The per-cloud work is storage wiring.** Once written, every agent read its
  cloud's data files.
- **Every agent answered alike.** All four setups gave the largest id and the
  filtered count in all twenty runs, each citing the exact snapshot. The scan does
  the filtering and counting.

Scope:

- One machine, 2026-09-15. 360 timed runs, warm, in shuffled rounds. Enough to see
  separation, not to estimate rates precisely.
- Every model ran at its defaults except Nova Micro, which used Amazon's recommended
  tool-use decoding. That decoding is deterministic, so a Nova cell returns one answer
  in every run: its correctness is one sample, its timings are many.
- Axis F runs Test 1's question with and without that decoding. Test 5's rows-only
  figures are also given at Bedrock's defaults, where twenty runs are twenty answers.
- Agent Framework ran only `gpt-5-mini`. The model comparison in Test 3 also changes
  provider and region.
- Polaris is local and the managed catalogs sit in different regions, so no time here
  compares clouds.
- Timings exclude imports and first sign-in. Cost was not measured.
- Earlier runs are published under `evidence/superseded-runs/`, re-scored by the same
  checks.

## How Portable Is It, Really?

Four things move when this agent changes cloud. Two of them are free.

- **The tools and the instruction port.** They were the same Python objects in all
  three frameworks. Nothing in them is vendor-specific.
- **The code around them does not.** Building the agent differs by a model id, a
  model object or a chat client. Calling it, signing in and reading its answer are
  three different jobs. Budget hours, not days.
- **The storage wiring does not, and it costs the most.** Each cloud needs its own
  file configuration under the same tool. Get it wrong and the catalog still answers
  while the data read fails, with an error naming something else.
- **Correctness follows the tool, not the cloud.** Put the filter and the count in
  PyIceberg and every model answered alike. Leave that work to the model and the
  smallest one fails.

The catalog layer really is portable. The work is in what sits around it.

The strategy for using one shared set of Iceberg tools across three agent
frameworks was validated with an incremental step by step approach.
