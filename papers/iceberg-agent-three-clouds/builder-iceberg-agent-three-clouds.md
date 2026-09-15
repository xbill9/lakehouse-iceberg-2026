# Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't

This article provides a step by step build of one small Apache Iceberg data
agent, written three times -- in Google ADK, in AWS Strands and in Microsoft
Agent Framework -- and run against five Iceberg catalogs. Every answer is checked
against the catalog itself, so the differences between the three agents can be
measured rather than described.

https://github.com/xbill9/lakehouse-iceberg-2026

## What Is This Project Trying to Do?

Two things are true of the lakehouse in 2026, and they pull in opposite
directions.

All three hyperscalers now ship their own agent framework. And the tables those
agents would read are
increasingly in Apache Iceberg, an open table format whose whole point is that
no single engine owns the data. The data is designed to move between clouds. Is
an agent that reads it designed to move too?

An [earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
measured the data side: seven Iceberg REST catalogs, and nine read operations
that every one of them serves. This project measures the agent side. It builds a
small data analyst -- list the tables, describe one, count its rows, and cite the
exact table version it read -- and builds it three times:

- **Google** — ADK on `gemini-2.5-flash`, reading BigLake
- **AWS** — Strands on `us.amazon.nova-micro-v1:0`, reading Glue
- **Azure** — Agent Framework on `gpt-5-mini`, reading OneLake

The four tools and the instruction are the same Python objects in all three.
Only the framework, the model and the catalog change.

## Why Measure It?

Because "portable" is easy to say and expensive to find out about. If this agent
were built on one cloud and had to move to another, three things could cost you:

1. **The code.** How much of the agent is specific to its framework?
2. **The behaviour.** Given the same tools and the same instruction, do the
   three answer the same way, at the same speed?
3. **The plumbing.** What has to change underneath the tools before a different
   catalog's files can be read?

Each of those can be answered with a measurement instead of a feature list. The
answers turned out to live in different places. The code difference is small.
The speed difference, between ADK and Strands, goes with the model and the
endpoint serving it. And the plumbing under the tools is where the real per-cloud
work is -- which is why one set of runs asks a question that forces every agent
to read its own cloud's data files.

The results below were measured on 2026-09-15 (UTC). Two earlier complete runs
of the same matrix, from 2026-09-14, are published beside them.

## Where Do I Start?

The strategy for building a portable Iceberg agent is an incremental step by step
approach.

First, the Python environment is set up and the local Apache Polaris control
catalog is brought up, so every leg can be tested without a cloud catalog in the
path.

Then, each leg is asked one question against the control. Once all three answer
it correctly, ground truth is captured from every catalog, the matrix runs, and
the evidence is re-scored and published.

## What Is Being Compared, and What Is Held Still

A single run of each cloud's agent proves the wiring works and nothing else. If
the framework, the model and the catalog all change together, no difference can
be attributed to any of them.

So the shared parts are exactly one implementation each:

| shared, one implementation | different, on purpose |
|---|---|
| the four Iceberg tools | the agent framework |
| the instruction, versioned | the model |
| the catalog-call budget | the catalog each leg reads |
| the stamped answer header | the serving runtime |

The runs are split into four tests rather than one grid. Each test changes one
thing and holds the rest still, so that when an answer comes back slower or
wrong, there is only one thing it can be blamed on:

| test | what changes | what stays the same | what it answers | evidence files |
|---|---|---|---|---|
| **Test 1** — the three agents, side by side | framework and model together | the catalog: the local control | how the three agents compare | Axis A |
| **Test 2** — same agent, five catalogs | the catalog | the agent: ADK on Gemini | whether where the data lives changes anything | Axis B |
| **Test 3** — framework or model? | the framework or the model, one at a time | the catalog | which of the two a speed difference belongs to | Axis C |
| **Test 4** — reading the real data | a data question, each agent on its own cloud | the question | whether each agent can read its own cloud's files | Axis D |

Three runs per cell. That is enough to see a clean separation, or the absence of
one, and not enough to estimate a distribution. Treat what follows as a
reproducible probe, not a benchmark.

Every time in the results is **answer time**: from the question going in to the
answer coming out, after the framework has been imported and the agent built.
Importing the frameworks alone takes 0.78 seconds for ADK, 0.45 for Strands and
0.24 for Agent Framework, which is why start-up is left out of every figure.

Every answer is scored by string comparison against ground truth read straight
from the catalog, not through any agent, and only the answer text is scored. The
row count has to sit beside the word "rows", each column has to appear as a whole
word, and the snapshot id and metadata location have to appear exactly. A run
that does all four passes every check, and that is what the tables below count.
Before any evidence is published, the scorer has to fail a planted answer that
contains the right numbers without stating them, such as
`snapshot-id exists; payload region. 11`.

## At This Point You Should Have…

- Python 3.14 and Docker
- Vertex AI enabled on a Google Cloud project, for ADK
- Bedrock model access to Nova Micro in `us-east-1`, for Strands
- A Microsoft Foundry project with a `gpt-5-mini` deployment, for Agent Framework
- Optional: the managed catalogs, seeded. The
  [earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
  brings up each one. Everything through Step 4 needs only the local control.

## Step 1 — Clone and Install

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-agent
$ python3 -m venv .venv && . .venv/bin/activate
$ pip install -r ../iceberg-conformance/requirements.txt -r requirements.txt
```

Both requirements files are needed. The tool imports the conformance harness's
credential flows rather than reimplementing six of them. In a fresh venv the pair
resolves in about 20 seconds.

Once everything is installed, check the versions:

```console
$ python3 -c "
import importlib.metadata as md, sys
print('python                 ', sys.version.split()[0])
for d in ['google-adk', 'strands-agents', 'agent-framework-core', 'agent-framework-foundry', 'pyiceberg']:
    print('%-23s' % d, md.version(d))"
python                  3.14.7
google-adk              2.8.0
strands-agents          1.55.0
agent-framework-core    1.17.0
agent-framework-foundry 1.12.0
pyiceberg               0.12.0
```

###  Tip: Install `agent-framework-core`, Not `agent-framework`

The meta package depends on every connector Microsoft ships. On this machine pip
resolved it for 1,445 seconds and then gave up with `resolution-too-deep`. Core
and `agent-framework-foundry` together resolve in about a second, and both are
needed: `FoundryChatClient` lives in the second.

###  Tip: OneLake Needs `adlfs`

`adlfs` is the fsspec filesystem for `abfss://`, and pyiceberg only pulls it in
as an optional extra. Without it every metadata call against OneLake succeeds and
every scan returns `ModuleNotFoundError: No module named 'adlfs'`.

## Step 2 — Bring Up the Control Catalog

Start with the control, not the clouds. Apache Polaris runs locally in Docker,
costs nothing, and carries the same fixture as three of the four managed
catalogs, so a leg that fails against it has a wiring problem rather than a
catalog problem.

```console
$ cd ../iceberg-conformance
$ cp catalogs.example.yaml catalogs.yaml
$ ./polaris-up.sh
$ curl -s http://localhost:8182/q/health/ready
{"status": "UP", "checks": [...]}
```

`polaris-up.sh` starts the container and seeds `probe_ns.probe_table`: 11 rows,
four columns, partitioned by day. The four flags it needs, and the failed attempt
behind each one, are in the earlier article.

## Step 3 — Set the Environment

```console
$ cd ../iceberg-agent
$ export PYTHONPATH=../iceberg-conformance
$ export ICEBERG_CATALOGS_FILE=../iceberg-conformance/catalogs.yaml
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_LOCATION=us-central1
$ export GOOGLE_CLOUD_PROJECT=<your-project>
$ unset GOOGLE_API_KEY                    # keep ADK on Vertex AI
$ export AWS_REGION=us-east-1
```

The Foundry endpoint is the project's `AI Foundry API` endpoint, which the
management API returns:

```console
$ ID=$(az cognitiveservices account show -n <resource> -g <resource-group> --query id -o tsv)
$ az rest --method get --url "https://management.azure.com$ID/projects?api-version=2025-06-01" \
    --query "value[0].properties.endpoints.\"AI Foundry API\"" -o tsv
https://<resource>.services.ai.azure.com/api/projects/<project>
$ export FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
```

## Step 4 — Ask One Leg, Against the Control

`--catalog` points a leg at the control, so the wiring is proven before a cloud
catalog is involved:

```console
$ python3 run_once.py gcp --catalog apache-polaris "How many rows are in the probe table?"
cloud=gcp model=gemini-2.5-flash catalog=apache-polaris
question: How many rows are in the probe table?

   -> tool: iceberg_list_tables()
   -> tool: iceberg_describe_table(table='probe_ns.probe_table')
   -> tool: iceberg_count_rows(table='probe_ns.probe_table')

<!-- cloud=gcp model=gemini-2.5-flash catalog=apache-polaris instruction=v3 catalog_calls=3 -->
The `probe_ns.probe_table` contains 11 rows. This count is exact for snapshot-id 5653331815319537848, from metadata-location file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json.

catalog calls: 3 of 8
agent seconds: 6.75 | tool seconds: 0.32
```

Run the same command with `aws` and `azure`, and check that each answers 11 rows
for the same snapshot before going further.

Then drop `--catalog`, and each leg reads its own cloud's catalog: BigLake for
ADK, Glue for Strands, OneLake for Agent Framework.

## The Tools

Four async callables, read-only, sharing one budget of eight catalog calls per
answer:

- `iceberg_list_tables` — discovery
- `iceberg_describe_table` — columns, partitioning, and the metadata location
- `iceberg_count_rows` — exact count from the snapshot summary
- `iceberg_scan_table` — rows, and says whether it returned every row of the
  snapshot or only some of them

Read-only is a decision, not a limitation of effort. These four tools use only
operations in the nine that all seven catalogs serve, so a reading agent built
this way is the portable case worth measuring. A tool that listed views or
planned a scan would not be: views fail on six of the seven, and scan planning
on all seven.

## Why Every Result Carries a Metadata Location

The [research-agent version of this comparison](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc)
puts the source URL on every search result, because an agent told to cite its sources and handed snippets without
them invents citations that look real.

The data version of that failure is an agent naming a table it never opened. An
Iceberg table's `metadata-location` and `snapshot-id` name an exact immutable
version, so carrying them into the model's context makes a real citation cheaper
to produce than an invented one — and makes the claim checkable afterwards.

```console
$ python3 -c "
import asyncio, iceberg_tool as t
print(asyncio.run(t.iceberg_describe_table('probe_ns.probe_table')))"
table: probe_ns.probe_table
format-version: 2
columns:
  id               long           required
  ts               timestamptz    optional
  payload          string         optional
  region           string         optional
partitioned by: ts_day
snapshots: 4
current-snapshot-id: 5653331815319537848
metadata-location: file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json

Cite the metadata-location and current-snapshot-id above when you state a figure from this table.
```

## Counting Is Not Scanning

`iceberg_scan_table` returns at most 100 rows and says so. Counting what it
returns therefore gives the sample size, not the table's size, and before
`iceberg_count_rows` existed the row-count question was answerable only by
guessing a limit large enough to cover the table — which measures the guess
rather than the catalog.

Counting is now one metadata call against the snapshot summary:

```console
$ python3 -c "
import asyncio, iceberg_tool as t
print(asyncio.run(t.iceberg_count_rows('probe_ns.probe_table')))"
11 rows, from the snapshot summary (total-records) of snapshot-id 5653331815319537848. This is exact for that snapshot.
```

The scan tool also warns when the view it returned is partial, which is what
stops a sample being reported as a total:

```console
$ python3 -c "
import asyncio, iceberg_tool as t
print(asyncio.run(t.iceberg_scan_table('probe_ns.probe_table', limit=3)))"
...
NOTE: exactly 3 row(s) came back, which is the limit, so there are probably more. Do NOT report this as the table's row count. If you were asked how many rows the table has, say you sampled 3 and could not count the whole table.
```

## How Are the Three Agents Different?

Start with what is the same, because it is most of the agent. The instruction is
one string. The four tools are four async Python functions with typed arguments
and docstrings. The budget of eight catalog calls is enforced inside the tools,
not by any framework. None of that changed between clouds.

What changed is everything around it: how the agent is built, how it is called,
how it signs in, what it shows you while it works, and how fast it answers.

### Building It

Here is the entire construction on each cloud. Not excerpts — this is all of it.

**Google, ADK:**

```python
from google.adk.agents import LlmAgent

LlmAgent(
    model=model,                        # a model id string
    name=..., description=...,
    instruction=common.INSTRUCTION,     # `instruction`
    tools=list(iceberg_tool.TOOLS),     # plain callables
)
```

**AWS, Strands:**

```python
from strands import Agent, tool
from strands.models import BedrockModel

Agent(
    model=BedrockModel(model_id=model),              # a model *object*
    system_prompt=common.INSTRUCTION,                # `system_prompt`
    tools=[tool(fn) for fn in iceberg_tool.TOOLS],   # explicitly decorated
)
```

**Azure, Agent Framework:**

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=model,
    credential=DefaultAzureCredential(),
)
Agent(
    client=client,                      # a chat *client* object
    instructions=common.INSTRUCTION,    # `instructions`
    tools=list(iceberg_tool.TOOLS),
)
```

A model id string, a model object, a client object. `instruction`,
`system_prompt`, `instructions`. Strands wraps each tool in `tool()`, while ADK
and Agent Framework take the functions as they are.

None of that is hard, and none of it translates. There is no shared agent object
to write once and hand to all three. What ports is what the frameworks are
given -- the tools and the instruction -- not the agents themselves.

### Running It

Building is the smaller difference. Calling each agent is a different job:

```python
# ADK: an agent does not run on its own. It needs a runner, a session,
# and a loop over the events the runner yields.
runner = InMemoryRunner(agent=agent, app_name="iceberg-agent")
session = await runner.session_service.create_session(app_name="iceberg-agent", user_id="probe")
async for event in runner.run_async(user_id="probe", session_id=session.id, new_message=message):
    ...   # collect the text parts, and the function_call parts to see the tools

# Strands: call the agent like a function.
result = agent(question)

# Agent Framework: await the agent.
reply = await agent.run(question)
```

ADK assumes the agent lives inside an application with sessions, and makes you
build that much of one. Strands assumes a script. Agent Framework sits between
them.

### Signing In

- **ADK on Vertex AI** uses Application Default Credentials, the same login the
  `gcloud` CLI uses.
- **Strands on Bedrock** uses the boto credential chain. On a machine signed in
  with `aws login` that chain needs `botocore[crt]`, and without it the agent
  fails before its first call while `aws sts get-caller-identity` still
  succeeds, because the CLI ships its own copy.
- **Agent Framework on Foundry** takes a project endpoint and a
  `DefaultAzureCredential`, which here resolved through the `az` CLI.

### What You Can See While It Runs

This is where the three differ most, and it matters the first time an answer is
wrong. The table is what each framework shows **by default, as this harness runs
it** -- not what each one can show. Strands goes quiet with
`callback_handler=None`, ADK's events are visible only because the harness reads
them, and Agent Framework has middleware and OpenTelemetry instrumentation that
this harness does not turn on. Every published capture was measured:

| framework / model | tool calls visible | answer printed twice | model reasoning visible | median answer |
|---|---|---|---|---|
| ADK / `gemini-2.5-flash` | 21/21 | 0/21 | 0/21 | 391 chars, 9 lines |
| Strands / `gemini-2.5-flash` | 3/3 | 3/3 | 0/3 | 459 chars, 9 lines |
| Strands / `us.amazon.nova-micro-v1:0` | 6/6 | 6/6 | 6/6 | 463 chars, 9 lines |
| Agent Framework / `gpt-5-mini` | 0/3 | 0/3 | 0/3 | 886 chars, 21 lines |

**ADK reports, and does not print.** Each tool call arrives as an event carrying
its name and arguments, so the harness can show list, describe, count as they
happen. Nothing reaches the terminal unless you print it.

**Strands prints for you.** An agent built without a `callback_handler` gets a
`PrintingCallbackHandler`, which streams the model's text and a `Tool #n` line to
stdout as the run happens. The answer therefore appears once while it streams and
again when the result is printed. That happened in all nine Strands runs, on both
models, which puts it on the framework. The `<thinking>` blocks are the model's:
they appeared in all six Nova Micro runs, and in none of the three where the same
Strands agent ran Gemini.

**Agent Framework, run this way, returns the reply and nothing else.** Its captures record that
three catalog calls were made, because the tools count them, but not which ones.
Its answers were also the longest, at about twice the length of the others, and
usually restated the table's description before giving the count. With only one
model on this framework, that cannot be split between Agent Framework and
`gpt-5-mini`.

### How Fast It Answers

Between ADK and Strands, speed follows the model and the endpoint serving it,
rather than the framework. The same Gemini model took a median 7.66 seconds to
answer under ADK and 8.63 under Strands; the same Strands agent took 8.63 on
Gemini and 3.51 on Nova Micro. Test 3, below, is where those numbers come from.

Agent Framework on `gpt-5-mini` was the slowest leg at 14.57 seconds, and was not
run on another model. That model may not be a free choice. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
`store=False` -- which keeps the conversation from being stored server-side --
made the framework request encrypted reasoning content, which a non-reasoning
model rejected. This leg sets `store=False` too, but that was not re-tested here.

So the three agents differ a little in how they are built, a lot in how they are
run and observed, and in speed mostly because of the model each cloud serves.

## Reading the Data Is Not the Same as Reading the Catalog

Three configurations reach the catalog and cannot read the data. Each one is
reproduced deliberately in the evidence, with `iceberg_list_tables` succeeding
immediately before `iceberg_scan_table` fails, so the catalog is demonstrably
reachable in all three. A control runs the same two calls with the tool's
wiring unchanged, and reads.

```console
$ # A. OneLake, no ADLS configuration at all (PyArrowFileIO, no adls.* properties)
-- metadata call (iceberg_list_tables):
dbo.probe_table
-- data call (iceberg_scan_table):
CATALOG ERROR while scanning dbo.probe_table: TypeError: __init__() takes exactly 1 positional argument (0 given).
```

```console
$ # B. OneLake, ADLS credential set but PyArrowFileIO instead of fsspec
CATALOG ERROR while scanning dbo.probe_table: OSError: GetProperties failed for
'https://onelake.blob.core.windows.net/...' Cannot initialise an ObjectInp.
```

```console
$ # C. Glue, SigV4 for the catalog but no local S3 credentials
CATALOG ERROR while scanning probe_ns.probe_table: OSError: ... AWS Error
ACCESS_DENIED during HeadObject operation
```

The second builds a hostname that does not exist: PyArrow's Azure filesystem
ignores `adls.account-host`, and fsspec honours it. The third is `ACCESS_DENIED`
on a bucket the caller owns outright, because pyiceberg used the credentials the
catalog vends rather than local ones.

One configuration that looks as though it should fail does not. With fsspec and
the OneLake account host in place, removing only the ADLS credential still reads
the table, because adlfs resolves `DefaultAzureCredential` on its own when handed
none. The `TypeError` in the first case needs the whole Azure storage
configuration to be absent, not just the credential.

Signing the catalog calls and reading the files the catalog points at are two
different credentials. In all three failing cases the error names something
other than the missing configuration.

This is the part that does not port. Every framework binds the same four tool
objects, but the storage wiring underneath them -- `FsspecFileIO` and an account
host for OneLake, local rather than vended credentials for Glue, and the vended
ones S3 Tables' managed bucket requires -- is written once per catalog, inside
the tool. It differs even between two catalogs on the same cloud. An agent that reads Iceberg is portable at the
catalog. At the files, it is configured.

## Step 5 — Capture Ground Truth

The thing being measured cannot also be the thing that says whether the
measurement was right. Ground truth comes from pyiceberg against each catalog,
with no agent in the path:

```console
$ python3 capture_ground_truth.py
catalog=apache-polaris table=probe_ns.probe_table
  rows=11
  rows_scanned=11
  rows_agree=yes
  max_id=23
  ids_at_least_10=8
  columns=id,ts,payload,region
  snapshot_id=5653331815319537848
  metadata_location=file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json
...
catalog=microsoft-onelake table=dbo.probe_table
  rows=6
  rows_scanned=6
  rows_agree=yes
  max_id=21
  ids_at_least_10=4
  columns=id,ts,payload
  snapshot_id=3346142071915475645
```

`rows` comes from the snapshot summary, the same place `iceberg_count_rows`
reads. `rows_scanned` comes from reading every data file, so `rows_agree` checks
the summary against the data rather than against itself. `max_id` and
`ids_at_least_10` are the answers Test 4 is scored against.

Nothing is written unless every catalog answers. A partial ground truth would
score the missing catalog's runs against nothing.

## Step 6 — Run the Matrix

```console
$ python3 run_matrix.py --axis A --repeat 3
...
$ python3 run_matrix.py --axis B --repeat 3
...
$ python3 run_matrix.py --axis C --repeat 3
...
$ python3 run_matrix.py --axis D --repeat 3
  gcp                               google-lakehouse    run 1   16.0s  agent=14.82s tool=3.76s  correct_max_id=ok correct_count=ok cites_snapshot=ok calls=3
  ...
  aws                               aws-glue            run 1    6.1s  agent=5.56s tool=1.61s  correct_max_id=ok correct_count=NO cites_snapshot=ok calls=3
  ...
  azure                             microsoft-onelake   run 2   25.3s  agent=24.08s tool=4.75s  correct_max_id=ok correct_count=ok cites_snapshot=ok calls=3
  ...
wrote .../evidence/paper3-raw/matrix-axis-D.json (9 runs)
```

The scripts keep the letters A to D; they are Tests 1 to 4 here.

Run each test alone. Its latencies are published, and anything else running on
the machine or against the same model endpoints is in them. Runs write only to a
gitignored raw directory, because a loaded table can carry real account
identifiers.

## Step 7 — Publish the Evidence

```console
$ python3 publish_evidence.py
...
mapped 13 identifiers; published 116 files to .../papers/iceberg-agent-three-clouds/evidence
$ cd .. && ./check-no-identifiers.sh
...
clean
```

`publish_evidence.py` is the only path into the article's evidence directory. It
re-scores every capture from its own body rather than trusting the runner,
refuses if the two disagree, refuses if the scorer passes a planted empty answer,
and maps account identifiers to stable pseudonyms on the way out. Every figure
below comes from the evidence files it writes.

## Where the Control Fits

Apache Polaris is the open-source Iceberg REST catalog, run locally in Docker and
configured permissively on purpose. It does four jobs in this article, and it
cannot do a fifth.

**It proves the wiring.** Every leg answers its first question against Polaris,
before any cloud catalog is involved (Step 4). A failure there is almost always a
bug in the harness, not a finding about a vendor.

**It holds the catalog still.** Tests 1 and 3 both read Polaris. There is no
network hop, no managed service and no region, so tool time is 0.31 to 0.39
seconds in every leg and the rest of the answer can be put on the framework and
the model.

**It is the baseline for the managed catalogs.** In Test 2 the same leg reads all
five catalogs. Three calls take 0.31 seconds against Polaris and 1.01 to 2.09
seconds against the four managed ones. The difference is distance from this
machine plus whatever the service adds, and it is not a ranking.

**It measures the noise.** ADK on Polaris is the one cell both Test 1 and Test 2
run. Its answer-time medians differed by 0.44 seconds in this run and 1.63 in the
one before it; the first run, which recorded only process time, gave 0.40. That is the run-to-run variation every other comparison in
this article has to clear.

**What it cannot test is the storage wiring.** Polaris keeps its data as local
files in a warehouse directory the client shares, so an agent reading it never
touches `FsspecFileIO`, an OneLake account host, or vended S3 credentials -- the
part of this agent that does not port. A leg that works against Polaris has
proven its agent and its catalog calls, not its file access.

Neither do Tests 1 to 3, on any catalog. Their question is answered from metadata,
so no run in them reads a data file at all. File access is tested in two other
places: by the failure modes above, against OneLake and Glue with their own
controls, and by Test 4, where each agent has to read its own cloud's data files
to answer at all.

It has one consequence for the headline. The about-4x spread in Test 1 was
measured against a local catalog, where the tools are about 5% of an answer.
Reading each leg's own managed catalog would add between 1.01 and 2.09 seconds of
tool time to each leg, depending on the catalog, and adding time to both ends of
a ratio narrows it. That was not measured here.

## Test 1: The Three Agents, Side by Side

Three legs, one catalog, three runs each. The catalog is the local Polaris
control, so nothing about it varies between legs.

The three models are not matched, and this table should not be read as if they
were. They differ in kind as well as speed: Bedrock's model catalog lists Nova
Micro as text in, text out, where Nova Lite and Pro also take images and video.
Each ran with its defaults --
no temperature, thinking budget or reasoning effort was set on any leg. Each leg
runs a model its own cloud serves, which is the arrangement a real deployment
would have, and it is also why Test 3 exists.

| leg | framework and model | runs passing every check | answer seconds min/med/max | median seconds in tools |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 2/3 | 3.14 / 3.40 / 3.49 | 0.31 |
| gcp | ADK, `gemini-2.5-flash` | 3/3 | 6.57 / 6.69 / 8.17 | 0.31 |
| azure | Agent Framework, `gpt-5-mini` | 3/3 | 14.03 / 14.57 / 27.43 | 0.39 |

Every run used exactly three catalog calls. ADK and Strands log each tool call,
and in every one of their runs the calls were list, describe, count; Agent
Framework does not log them, and its answers report what those same three
returned. Three is what this question needs -- it asks for columns as well as a
count -- rather than a fixed property of the legs.

All three frameworks reach the same correct row count with the same call
pattern. What separates them is latency, and the separation is clean — **about
4x from the fastest median to the slowest** (14.57s / 3.40s = 4.29x in this run),
with no overlap between any pair. AWS's slowest answer (3.49s) is faster than
Google's fastest (6.57s), and Google's slowest (8.17s) is faster than Azure's
fastest (14.03s).

That separation replicates. This is the third complete run of both tests, and all
three produced the same order with no overlap between legs, at spreads of 4.17x
and 4.29x in answer time for the two instrumented runs, and 3.80x for the first,
which recorded only process time. The second decimal moves between runs; the
ordering and the gaps do not.

The tools are not where that time goes. Each answer records how long it spent
inside the four tools, and against this catalog that is 0.31 to 0.39 seconds in
every leg — about 5% of a median answer. Azure's second run took 27.43 seconds,
of which 0.39 were in the tools; the rest is the model, the framework and the
endpoint between them. One slow answer in three moves the maximum and leaves the
median alone.

One answer failed a check. Strands run 3 gave the right count, columns and
snapshot id, and then wrote:

> The metadata-location and snapshot-id that I cited above identify the exact
> immutable version of the table from which these figures are derived.

It had cited the snapshot id and not the metadata location. The describe call
that returns the location did run -- the answer reports the columns that came
back with it -- so the location was in context and was not carried into the
answer. The check is an exact string comparison against ground truth, which is
what separates a citation that is made from one that is only described.

## Test 2: Same Agent, Five Catalogs

One leg — ADK on Gemini — against five catalogs, three runs each.

| catalog | runs passing every check | answer seconds min/med/max | median seconds in tools |
|---|---|---|---|
| apache-polaris | 3/3 | 6.70 / 7.13 / 7.90 | 0.31 |
| google-lakehouse | 3/3 | 8.02 / 8.77 / 10.40 | 2.09 |
| aws-glue | 3/3 | 7.88 / 8.31 / 8.53 | 1.02 |
| aws-s3tables | 3/3 | 7.61 / 8.19 / 9.01 | 1.01 |
| microsoft-onelake | 3/3 | 8.53 / 9.76 / 10.19 | 2.08 |

The catalog is visible here, and only in the tool column. Three catalog calls
take 0.31 seconds against the local control and between 1.01 and 2.09 seconds
against the four managed catalogs. That is distance from this machine as much as
anything the catalog does, and it is not a ranking of the services.

In the totals it is a smaller part. Cell medians run from 7.13 to 9.76 seconds, a
2.63-second range, narrower than the gap between either pair of adjacent legs'
medians in Test 1 (3.29 and 7.88 seconds). That holds for this leg: with a
3.4-second leg such as Strands on Nova Micro, the same two seconds of catalog
time would be a third of the answer.

Both tests measure one cell -- ADK on Polaris -- so the matrix measures its own
noise. That cell's medians were 6.69 seconds in Test 1 and 7.13 in Test 2, 0.44
seconds apart; in the two earlier runs the same comparison gave 1.63 seconds, and
0.40 seconds in process time. A difference between two catalogs smaller than
that is not distinguishable from run-to-run variation.

The correct answer is not the same in every row. OneLake's table holds 6 rows
and 3 columns where the others hold 11 and 4, because it was loaded through the
Fabric load-table API rather than seeded with pyiceberg. Each answer is scored
against ground truth read from its own catalog, so a leg that reported 11 rows
against OneLake would be marked wrong.

## Test 3: Framework or Model?

Test 1 cannot say how much of that 4x is the framework, because each leg pairs
one framework with one model. Test 3 adds one crossover: the Strands agent from
the AWS leg, unchanged except for its model object, on `gemini-2.5-flash`
through Vertex AI -- the model and endpoint ADK uses. It runs beside the two
cells it shares one thing with, all nine runs in one sitting against the same
Polaris catalog.

| framework | model | runs passing every check | answer seconds min/med/max | median seconds in tools |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 3/3 | 5.71 / 7.66 / 8.04 | 0.31 |
| Strands | `gemini-2.5-flash` | 3/3 | 7.64 / 8.63 / 8.99 | 0.30 |
| Strands | `us.amazon.nova-micro-v1:0` | 3/3 | 3.30 / 3.51 / 4.07 | 0.31 |

Changing the framework with the model held still moved the median by 0.97
seconds, 1.13x, and the two cells overlap: ADK's slowest answer (8.04s) is slower
than Strands' fastest (7.64s). Changing the model with the framework held still
moved it by 5.12 seconds, 2.46x, with no overlap.

So between these two frameworks, the latency difference in Test 1 goes with the
model -- more precisely, with the model and the endpoint serving it. Both Gemini
cells call Vertex AI in `us-central1`, so the framework comparison shares a
route; Nova Micro is served by Bedrock from `us-east-1`, so the model comparison
also changes provider and distance, and this layout cannot separate those.

Whether ADK and Strands differ at all is not settled. The 0.97-second gap is
larger than the run-to-run variation measured in this run, 0.44 seconds, and
smaller than the 1.63 seconds measured in the run before it. Three runs per cell
cannot decide between those, so this article does not rank the two.

The crossover covers two of the three frameworks. Agent Framework was not run on
another model, so the Azure leg's framework and model remain confounded, and its
14.57-second median describes Agent Framework with `gpt-5-mini`, not Agent
Framework alone.

## Test 4: Reading the Real Data

Tests 1 to 3 ask a question the agent's metadata tools can answer: the row count
lives in the snapshot summary and the columns in the schema. Not one of those
runs opens a data file. Test 4 asks something none of the agent's metadata tools
can answer, and sends each agent to its own cloud's catalog, so that answering
means reading GCS, S3 or ADLS through the storage wiring described earlier.

Iceberg's own metadata is not blind to it. Manifests carry per-file column
bounds, and on the control they put the largest id at 23 without reading a row.
None of the four tools exposes those bounds, so an agent here has to scan:

> What is the largest id in the probe table, and how many of its rows have an id
> of 10 or more? Cite the exact table version you read.

Ground truth for it comes from scanning each table directly: 23 and 8 on BigLake
and Glue, 21 and 4 on OneLake. The same scan checks each snapshot's
`total-records` against the rows actually in its data files, and they agree on
all five catalogs.

| agent and catalog | largest id | rows with id of 10 or more | answer seconds min/med/max | median seconds in tools |
|---|---|---|---|---|
| ADK / `gemini-2.5-flash` on BigLake | 3/3 | 3/3 | 12.84 / 14.82 / 15.76 | 3.81 |
| Strands / `us.amazon.nova-micro-v1:0` on Glue | 3/3 | 0/3 | 5.56 / 5.97 / 6.53 | 2.21 |
| Agent Framework / `gpt-5-mini` on OneLake | 3/3 | 3/3 | 24.08 / 26.05 / 65.90 | 6.10 |

**Every agent read its data.** ADK and Strands log a scan call in every run.
Agent Framework does not log its calls, but its answers name values that none of
the metadata tools return, three times out of three. The storage wiring that
does not port does work, on all three clouds, once it is written.

**Strands on Nova Micro found the largest id every time and miscounted every
time**: 6, 4 and 11, against 8. Each of those runs called the scan tool. ADK and
Agent Framework counted correctly from the same tool. Test 4 ran Strands only on Nova Micro, so it cannot say
whether the miscount belongs to the framework or to the model. It is nine runs,
not a rate.

One quirk of the scan tool shows up once in these captures. When an agent asks
for exactly as many rows as the table holds, the tool reports both that every row
came back and that there are probably more. An ADK run asked for 11 and answered
correctly.

Two things about the times. Agent Framework's first answer took 65.90 seconds,
48.41 of them in the tools, where its other two runs spent 4.75 and 6.10: one slow
OneLake read in three. And every leg is slower here than in Tests 1 to 3. Part of
that is tool time, a scan against a managed catalog in place of metadata calls to
the local control, and the rest of each answer took longer too; this run does not
separate why. The legs also read different catalogs in
different regions, so these times compare nothing across clouds.

## What the Agents Actually Answered

```console
$ python3 run_once.py azure "How many rows are in the probe table, and what columns does it have? Cite the exact table version you read."
<!-- cloud=azure model=gpt-5-mini catalog=microsoft-onelake instruction=v2 catalog_calls=3 -->
...
- metadata-location: abfss://...@onelake.dfs.fabric.microsoft.com/.../Tables/probe_table/metadata/v3.metadata.json
- current-snapshot-id: 3346142071915475645

Row count
- Exact number of rows: 6 rows.
- This count is exact for the table version identified above (metadata-location and snapshot id quoted). The count was taken from the snapshot summary (total-records) for snapshot-id 3346142071915475645.

catalog calls: 3 of 8
agent seconds: 19.35 | tool seconds: 3.43
```

This answer was captured under instruction v2. Test 4 ran with v3, which changes
only when a scan may be counted.

Every answer carries a stamped header giving the cloud, model, catalog,
instruction version and call count. Without it, an answer that looks wrong
cannot be told from one produced by an older instruction, and an agent that
never called its tools looks identical to one that did. The last line splits
the answer's time into the part spent in the tools and the rest.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and across catalogs. The key
to the solution was building one implementation of the four tools, binding it
into three frameworks unchanged, and splitting the runs into four tests so that
the catalog, the framework, the model and the data path could each be varied on
its own. The results were:

- **Every run of the metadata question gave the correct row count and named
  every column**, across three frameworks and five catalogs -- 24 of 24 in Tests 1 and 2, and all nine in Test 3 -- and every one cited the snapshot id of the
  version it read.
- **All but one cited the metadata location.** The one that did not said that it
  had, and only an exact comparison against ground truth shows the difference.
  It is one run of one model on one question, not a rate.
- **No invented columns in any run.** OneLake's table has no `region` column and
  no answer against OneLake named one.
- **Every run in Tests 1 to 3 used exactly three catalog calls** out of a budget
  of eight — the three that question needs.
- **Framework and model together account for about a 4x spread in answer time**
  against the local control, with no overlap between legs and the same order in
  all three complete runs: 4.29x and 4.17x in answer time, and 3.80x in the first
  run, which recorded only process time. The tools took 0.31 to 0.39 seconds of
  it in every leg.
- **Between ADK and Strands, that spread goes with the model and its endpoint.**
  Holding Gemini still and swapping the framework moved the median 0.97 seconds
  (1.13x, overlapping); holding Strands still and swapping the model moved it 5.12
  seconds (2.46x, no overlap). Agent Framework was not crossed over.
- **Through the ADK leg, the catalog shows up in tool time more than in the
  totals.** Three calls take 0.31 to 2.09 seconds depending on the catalog; cell
  medians through that leg span 7.13 to 9.76 seconds, and the one cell both tests
  measure has differed by up to 1.63 seconds between them.
- **The frameworks differ more in how they run than in how they are built.**
  Construction is three small differences. Calling the agent, signing in and
  seeing its tool calls are three different jobs: ADK reports each tool call as
  an event, Strands prints every answer twice by default, and Agent Framework
  showed only the reply.
- **What does not port is the storage wiring, and it works once written.** The
  tools bind unchanged; the file access beneath them is configured per catalog.
  In Test 4 every agent read its own cloud's data files. ADK and Agent Framework
  answered correctly in all three of their runs; Strands on Nova Micro found the
  largest id in all three and miscounted the rows in all three -- nine runs, not a
  rate.

Scope: two questions, each asked three times per cell, on 2026-09-15, from one
machine, with the versions shown above and every model at its defaults; times
are answer time, after imports and agent construction; cost and token counts
were not measured; Tests 1 to 3 are 33 runs of a metadata question, mostly
against the local control, and Test 4 is 9 runs of a data question with each leg
on its own catalog, rather than a full grid; the metadata question is not hard
enough to separate the legs beyond latency, and the data question separated
only one; ground truth reads the same snapshot summary as the count tool, and is
cross-checked by a full scan of the data files, which agreed on every catalog; Test 3 separates framework from model for ADK and Strands only, on one pair of
models, and leaves Agent Framework confounded with `gpt-5-mini`; Polaris runs locally while the other four are managed services in
different regions, so neither the Test 2 latencies, the tool times nor Test 4's
times are a fair comparison between clouds; and the OneLake fixture differs from the other four
because it was loaded through the Fabric API rather than pyiceberg. Two earlier
complete runs from 2026-09-14, and an earlier Test 4 run, are published under
`evidence/superseded-runs/`, re-scored by the same checks.

The strategy for using one shared set of Iceberg tools across three agent frameworks was
validated with an incremental step by step approach.
