# One Iceberg Tool, Three Agent Frameworks: What Ports, and What Doesn't

This article provides a step by step build of one small Apache Iceberg data
agent, written three times -- in Google ADK, in AWS Strands and in Microsoft
Agent Framework -- and run against five Iceberg catalogs. Every answer is checked
against the catalog itself, so the differences between the three agents can be
measured rather than described.

https://github.com/xbill9/lakehouse-iceberg-2026

## What Is This Project Trying to Do?

Two things are true of the lakehouse in 2026, and they pull in opposite
directions.

All three hyperscalers now ship their own agent framework, tied to their own
models and their own hosting. And the tables those agents would read are
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
The speed difference, between ADK and Strands, is mostly the model. And the
plumbing under the tools is where the real per-cloud work is.

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

And the runs are split into three axes rather than one grid:

- **Axis A** holds the catalog still and varies the framework and model
- **Axis B** holds the leg still and varies the catalog
- **Axis C** holds the model still and varies the framework

Three runs per cell, so a disagreement means something.

Every answer is scored by string comparison against ground truth read straight
from the catalog, not through any agent, and only the answer text is scored. The
row count has to sit beside the word "rows", each column has to appear as a whole
word, and the snapshot id and metadata location have to appear exactly. A run
that does all four passes every check, and that is what the tables below count. The first
version of the scorer searched the whole capture with looser matches, and an
answer reading `snapshot-id exists; payload region. 11` passed it with a correct
count and every column named. The scorer now has to fail that answer before any
evidence is published. Re-scoring every run with the stricter version changed no
result.

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

<!-- cloud=gcp model=gemini-2.5-flash catalog=apache-polaris instruction=v2 catalog_calls=3 -->
The table `probe_ns.probe_table` has 11 rows. This count is exact for snapshot-id 5653331815319537848, from the table described by metadata-location `file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json`.

catalog calls: 3 of 8
agent seconds: 7.14 | tool seconds: 0.33
```

Run the same command with `aws` and `azure`. All three answered 11 rows for the
same snapshot. Strands answered this shorter question in two calls, skipping
describe, because nothing in it asks for columns.

Then drop `--catalog`, and each leg reads its own cloud's catalog: BigLake for
ADK, Glue for Strands, OneLake for Agent Framework.

## The Tools

Four async callables, read-only, sharing one budget of eight catalog calls per
answer:

- `iceberg_list_tables` — discovery
- `iceberg_describe_table` — columns, partitioning, and the metadata location
- `iceberg_count_rows` — exact count from the snapshot summary
- `iceberg_scan_table` — sampled rows, and says so when the view is partial

Read-only is a decision, not a limitation of effort. These four tools use only
operations in the nine that all seven catalogs serve, so a reading agent built
this way is the portable case worth measuring. A tool that listed views or
planned a scan would not be: views fail on six of the seven, and scan planning
on all seven.

## Why Every Result Carries a Metadata Location

The research-agent version of this mesh puts the source URL on every search
result, because an agent told to cite its sources and handed snippets without
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
wrong. Every published capture was measured for it:

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

**Agent Framework returns the reply and nothing else.** Its captures record that
three catalog calls were made, because the tools count them, but not which ones.
Its answers were also the longest, at about twice the length of the others, and
usually restated the table's description before giving the count. With only one
model on this framework, that cannot be split between Agent Framework and
`gpt-5-mini`.

### How Fast It Answers

Between ADK and Strands, speed follows the model rather than the framework. The
same Gemini model took a median 8.8 seconds under ADK and 9.4 under Strands; the
same Strands agent took 9.4 on Gemini and 4.0 on Nova Micro. Axis C, below, is
where those numbers come from.

Agent Framework on `gpt-5-mini`, a reasoning model, was the slowest leg at 15.8
seconds, and was not run on another model. That model was not a free choice. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
`store=False` -- which keeps the conversation from being stored server-side --
made the framework request encrypted reasoning content, which a non-reasoning
model rejected.

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
  columns=id,ts,payload,region
  snapshot_id=5653331815319537848
  metadata_location=file:/.../metadata/00006-57dbb327-b002-43cc-9ed3-93e61cab024e.metadata.json
...
catalog=microsoft-onelake table=dbo.probe_table
  rows=6
  columns=id,ts,payload
  snapshot_id=3346142071915475645
```

Nothing is written unless every catalog answers. A partial ground truth would
score the missing catalog's runs against nothing.

## Step 6 — Run the Matrix

```console
$ python3 run_matrix.py --axis A --repeat 3
...
$ python3 run_matrix.py --axis B --repeat 3
...
$ python3 run_matrix.py --axis C --repeat 3
  gcp    gemini-2.5-flash           apache-polaris      run 1    9.2s  agent=8.04s tool=0.32s  count=ok snap=ok meta=ok cols=ok calls=3
  ...
  aws    gemini-2.5-flash           apache-polaris      run 1    9.4s  agent=8.63s tool=0.3s  count=ok snap=ok meta=ok cols=ok calls=3
  ...
  aws    us.amazon.nova-micro-v1:0  apache-polaris      run 1    4.6s  agent=4.07s tool=0.32s  count=ok snap=ok meta=ok cols=ok calls=3
  ...
wrote .../evidence/paper3-raw/matrix-axis-C.json (9 runs)
```

Run each axis alone. Its latencies are published, and anything else running on
the machine or against the same model endpoints is in them. Runs write only to a
gitignored raw directory, because a loaded table can carry real account
identifiers.

## Step 7 — Publish the Evidence

```console
$ python3 publish_evidence.py
...
mapped 13 identifiers; published 95 files to .../papers/iceberg-agent-three-clouds/evidence
$ cd .. && ./check-no-identifiers.sh
...
clean
```

`publish_evidence.py` is the only path into the article's evidence directory. It
re-scores every capture from its own body rather than trusting the runner,
refuses if the two disagree, refuses if the scorer passes a planted empty answer,
and maps account identifiers to stable pseudonyms on the way out. Every figure
below comes from the summary it writes.

## Axis A: Catalog Fixed, Framework and Model Vary

Three legs, one catalog, three runs each. The catalog is the local Polaris
control, so nothing about it varies between legs.

The three models are not matched, and this table should not be read as if they
were. Nova Micro is the smallest of Amazon's Nova text models. `gpt-5-mini` is a
reasoning model, run here at its default reasoning effort. Gemini 2.5 Flash sits
between them and thinks by default. Each leg runs its own cloud's model, which is
the arrangement a real deployment would have -- and it is also why Axis C exists.

| leg | framework and model | runs passing every check | seconds min/med/max | median seconds in tools |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 2/3 | 3.6 / 3.9 / 4.0 | 0.31 |
| gcp | ADK, `gemini-2.5-flash` | 3/3 | 7.7 / 7.8 / 9.3 | 0.31 |
| azure | Agent Framework, `gpt-5-mini` | 3/3 | 15.3 / 15.8 / 28.6 | 0.39 |

Every run used exactly three catalog calls. ADK and Strands log each tool call,
and in every one of their runs the calls were list, describe, count; Agent
Framework does not log them, and its answers report what those same three
returned. Three is what this question needs -- it asks for columns as well as a
count -- rather than a fixed property of the legs.

All three frameworks reach the same correct row count with the same call
pattern. What separates them is latency, and the separation is clean — **about
4x from the fastest median to the slowest** (15.8s / 3.9s = 4.05x in this run),
with no overlap between any pair. AWS's slowest run (4.0s) is
faster than Google's fastest (7.7s), and Google's slowest (9.3s) is faster than
Azure's fastest (15.3s).

That separation replicates. This is the third complete run of both axes, and all
three produced the same order with no overlap between legs, at spreads of 3.80x,
3.98x and 4.05x. The second decimal moves between runs; the ordering and the
gaps do not.

The tools are not where that time goes. Each answer records how long it spent
inside the four tools, and against this catalog that is 0.31 to 0.39 seconds in
every leg — about 5% of a median answer. Azure's second run took 28.6 seconds,
of which 0.39 were in the tools; the rest is the model and the framework. One
slow answer in three moves the maximum and leaves the median alone.

One answer failed a check. Strands run 3 gave the right count, columns and
snapshot id, and then wrote:

> The metadata-location and snapshot-id that I cited above identify the exact
> immutable version of the table from which these figures are derived.

It had cited the snapshot id and not the metadata location. The describe call
that returns the location did run -- the answer reports the columns that came
back with it -- so the location was in context and was not carried into the
answer. The check is an exact string comparison against ground truth, which is
what separates a citation that is made from one that is only described.

## Axis B: Leg Fixed, Catalog Varies

One leg — ADK on Gemini — against five catalogs, three runs each.

| catalog | runs passing every check | seconds min/med/max | median seconds in tools |
|---|---|---|---|
| apache-polaris | 3/3 | 7.8 / 8.3 / 9.1 | 0.31 |
| google-lakehouse | 3/3 | 9.2 / 9.9 / 11.6 | 2.09 |
| aws-glue | 3/3 | 9.1 / 9.5 / 9.7 | 1.02 |
| aws-s3tables | 3/3 | 8.8 / 9.4 / 10.2 | 1.01 |
| microsoft-onelake | 3/3 | 9.7 / 10.9 / 11.3 | 2.08 |

The catalog is visible here, and only in the tool column. Three catalog calls
take 0.31 seconds against the local control and between 1.01 and 2.09 seconds
against the four managed catalogs. That is distance from this machine as much as
anything the catalog does, and it is not a ranking of the services.

In the totals it is a small part. Cell medians run from 8.3 to 10.9 seconds, a
2.6-second range, narrower than the gap between either pair of adjacent legs'
medians in Axis A (3.9 and 8.0 seconds).

Both axes measure one cell -- ADK on Polaris -- so the matrix measures its own
noise. That cell's medians were 7.8 seconds in Axis A and 8.3 in Axis B, 0.5
seconds apart; in the two earlier runs the same comparison gave 0.4 and 1.7
seconds. Against a 2.6-second range across catalogs, a difference between two
catalogs smaller than that is not distinguishable from run-to-run variation.

The correct answer is not the same in every row. OneLake's table holds 6 rows
and 3 columns where the others hold 11 and 4, because it was loaded through the
Fabric load-table API rather than seeded with pyiceberg. Each answer is scored
against ground truth read from its own catalog, so a leg that reported 11 rows
against OneLake would be marked wrong.

## Axis C: Model Fixed, Framework Varies

Axis A cannot say how much of that 4x is the framework, because each leg pairs
one framework with one model. Axis C adds one crossover: the Strands agent from
the AWS leg, unchanged except for its model object, on `gemini-2.5-flash`
through Vertex AI -- the model and endpoint ADK uses. It runs beside the two
cells it shares one thing with, all nine runs in one sitting against the same
Polaris catalog.

| framework | model | runs passing every check | seconds min/med/max | median seconds in tools |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 3/3 | 6.9 / 8.8 / 9.2 | 0.31 |
| Strands | `gemini-2.5-flash` | 3/3 | 8.4 / 9.4 / 9.8 | 0.30 |
| Strands | `us.amazon.nova-micro-v1:0` | 3/3 | 3.8 / 4.0 / 4.6 | 0.31 |

Changing the framework with the model held still moved the median by 0.6
seconds, 1.07x, and the two cells overlap: ADK's slowest run (9.2s) is slower
than Strands' fastest (8.4s). Changing the model with the framework held still
moved it by 5.4 seconds, 2.35x, with no overlap.

So between these two frameworks, the latency difference in Axis A belongs to the
model. A 0.6-second difference is inside the run-to-run variation measured above
in Axis B -- up to 1.7 seconds for one cell -- so this run does not rank ADK
against Strands in either direction.

The crossover covers two of the three frameworks. Agent Framework was not run on
another model, so the Azure leg's framework and model remain confounded, and its
15.8-second median describes Agent Framework with `gpt-5-mini`, not Agent
Framework alone.

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

Every answer carries a stamped header giving the cloud, model, catalog,
instruction version and call count. Without it, an answer that looks wrong
cannot be told from one produced by an older instruction, and an agent that
never called its tools looks identical to one that did. The last line splits
the answer's time into the part spent in the tools and the rest.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and across catalogs. The key
to the solution was building one tool implementation, binding it into three
frameworks unchanged, and splitting the runs into three axes so that the catalog,
the framework and the model could each be varied on its own. The results were:

- **24 of 24 runs gave the correct row count and columns**, across three
  frameworks and five catalogs, and all 24 cited the snapshot id of the version
  they read.
- **23 of 24 cited the metadata location.** The one that did not said that it
  had, and only an exact comparison against ground truth shows the difference.
  It is one run of one model on one question, not a rate.
- **No invented columns in any run.** OneLake's table has no `region` column and
  no answer against OneLake named one.
- **Every run used exactly three catalog calls** out of a budget of eight — the
  three this question needs.
- **Framework and model together account for about a 4x latency spread**, with
  no overlap between legs and the same order in all three complete runs (3.80x,
  3.98x, 4.05x). The tools took 0.31 to 0.39 seconds of it in every leg.
- **Between ADK and Strands, that spread is the model's.** Holding Gemini still
  and swapping the framework moved the median 0.6 seconds (1.07x, overlapping);
  holding Strands still and swapping the model moved it 5.4 seconds (2.35x, no
  overlap). Agent Framework was not crossed over.
- **Through the ADK leg, the catalog shows up in tool time, not in the
  totals.** A faster leg would feel the same tool time more. Three calls take
  0.31 to 2.09 seconds depending on the catalog; cell medians through one leg
  span 8.3 to 10.9 seconds, and the one cell both axes measure has differed by
  up to 1.7 seconds between them.
- **The frameworks differ more in how they run than in how they are built.**
  Construction is three small differences. Calling the agent, signing in and
  seeing its tool calls are three different jobs: ADK reports each tool call as
  an event, Strands prints every answer twice by default, and Agent Framework
  showed only the reply.
- **What does not port is the storage wiring.** The tools bind unchanged; the
  file access beneath them is configured per cloud.

Scope: one question, asked three times per cell, on 2026-09-15, from one
machine, with the versions shown above; cost and token counts were not
measured; Axis A is three legs against one catalog and Axis B is one leg
against five, so 24 runs rather than the full 45-cell grid; every run gave the
correct count and only one missed a check, which means the question is not hard
enough to discriminate between legs beyond latency; Axis C separates framework from model for ADK and Strands only, on one pair of
models, and leaves Agent Framework confounded with `gpt-5-mini`; Polaris runs locally while the other four are managed services in
different regions, so neither the Axis B latencies nor the tool times are a fair
comparison between clouds; and the OneLake fixture differs from the other four
because it was loaded through the Fabric API rather than pyiceberg. Two earlier
complete runs from 2026-09-14 are published under `evidence/superseded-runs/`.
The first was made before answers recorded their tool time, and was replaced
because two of its slow runs could not be attributed. The second is the run this
article first reported; the whole pipeline was then run again from ground truth
onwards, to check that the result replicates. Both scored 24 of 24 on every
check, including the metadata citation, and neither was replaced because of a
result in it.

The strategy for using one shared Iceberg tool across three agent frameworks was
validated with an incremental step by step approach.
