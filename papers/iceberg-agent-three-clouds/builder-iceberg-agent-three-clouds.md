# Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't

This article provides a step by step build of one small Apache Iceberg data
agent, written three times -- in Google ADK, in AWS Strands and in Microsoft
Agent Framework -- and run against five Iceberg catalogs. Every answer is checked
against the catalog itself, so the differences between the three agents can be
measured rather than described.

https://github.com/xbill9/lakehouse-iceberg-2026

## What Is This Project Trying to Do?

All three hyperscalers now ship their own agent framework. The tables those
agents would read are increasingly in Apache Iceberg, an open table format whose
whole point is that no single engine owns the data. The data is designed to move
between clouds. Is an agent that reads it designed to move too?

An [earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
measured the data side: seven Iceberg REST catalogs, and nine read operations
that every one of them serves. This project measures the agent side. It builds a
small data analyst -- list the tables, describe one, count its rows, read its
rows, and cite the exact table version it read -- and builds it three times:

- **Google** — ADK on `gemini-2.5-flash`, reading BigLake
- **AWS** — Strands on `us.amazon.nova-micro-v1:0`, reading Glue
- **Azure** — Agent Framework on `gpt-5-mini`, reading OneLake

The four tools and the instruction are the same Python objects in all three.
Only the framework, the model and the catalog change.

If this agent were built on one cloud and had to move to another, three things
could cost you: **the code**, **the behaviour** -- whether the same agent answers
the same way at the same speed -- and **the plumbing** under the tools that reads
a catalog's files. Each of those can be measured instead of guessed at.

The results below were measured on 2026-09-15 (UTC), ten runs per cell.

## What Did It Find?

**The code barely changes.** Building the same agent in the three frameworks
takes three small construction differences: a model id string, a model object or
a client object, and a different name for the instruction. The tools and the
instruction bind unchanged.

**Speed goes mostly with the model, and measurably with the framework.** The
three agents as each cloud ships them are about 5x apart in answer time (15.45s
against 3.00s at the median), with no overlap in the middle half of their runs.
Swapping the model under the same Strands framework moved the median by 2.21x.
Swapping the framework under the same Gemini model moved it by 1.32x. Neither
pair overlaps.

**The plumbing is where the per-cloud work is.** Every framework calls the same
four tools, but the storage wiring underneath -- `FsspecFileIO` and an account
host for OneLake, local credentials for Glue, vended credentials for S3 Tables --
is written once per catalog. Get it wrong and the catalog still answers while the
data read fails, with an error that names something else.

**Once written, that wiring works on all three clouds.** Asked a question that
forces a scan, every agent read its own cloud's data files. ADK and Agent
Framework answered correctly in all ten runs. Strands on Nova Micro found the
largest id in nine runs and the filtered row count in one.

**On the simpler question, all three were right.** Every one of 110 runs gave the
correct row count, named every column, and cited the exact table version it
read.

## What Is Apache Iceberg, and Why Does It Matter?

A lakehouse keeps its data as ordinary files -- usually Parquet -- in object
storage such as S3, GCS or ADLS. On their own, those files are just a pile:
nothing says which of them make up a table, which version is current, or what
happens when two writers change the table at once. Apache Iceberg is the open
table format that answers those questions. It adds a metadata layer over the
files: a schema, the list of files in each version of the table, and a chain of
immutable snapshots, one per committed change.

That metadata is what makes the rest possible:

- **Many engines, one table.** Spark, Trino, Flink and the cloud warehouses can
  all read and write the same Iceberg table, so the data does not have to be
  copied into every tool that needs it.
- **Versions you can point at.** Every change creates a new snapshot. A query can
  read the table as it was at a given snapshot, and an answer can name exactly
  which version it came from -- which is what the agents in this article do.
- **Change without rewrites.** Columns can be added or renamed, and partitioning
  changed, without rewriting the data files already written.
- **A standard way in.** The Iceberg REST catalog specification defines one API
  for finding tables and their current metadata.

That last point is why Iceberg is becoming the common ground between platforms
that otherwise compete. Google, AWS, Microsoft, Snowflake and Databricks all now
serve an Iceberg REST catalog; the
[earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
measured seven of them against the specification.

Why it matters depends on your job:

- **Developers** can build against one open API instead of one vendor's
  warehouse. A tool, a service or an agent written for the REST catalog can, in
  principle, be pointed at a different catalog -- which is exactly the claim this
  article puts to the test.
- **Platform and cloud admins** keep the data in their own buckets, as open
  files, and govern access at the catalog. The catch, measured below, is that
  each catalog wires storage credentials its own way.
- **Data engineers and analysts** get reproducible reads. A report, a pipeline or
  an AI agent's answer can be tied to an exact snapshot, and checked later
  against the same data.

For a deeper dive:

- [Iceberg table specification](https://iceberg.apache.org/spec/) -- snapshots,
  schemas, partitioning and the metadata files themselves
- [REST catalog specification](https://iceberg.apache.org/rest-catalog-spec/) and
  its [OpenAPI definition](https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml)
  -- the API every catalog in this article serves
- [PyIceberg](https://py.iceberg.apache.org/) -- the Python library the tools here
  are built on, including its REST catalog and FileIO configuration

## What Is Apache Polaris, and Why Is It Here?

Apache Polaris is an open-source implementation of the Iceberg REST catalog --
the same API that BigLake, Glue, S3 Tables and OneLake serve, run on your own
machine instead of as a managed service. Here it runs locally in Docker, started
by one script, and holds the same 11-row test table as three of the four managed
catalogs.

It is the **control**: the catalog every agent is checked against before a cloud
is involved. A control exists to answer one question whenever something fails:
is this a finding about a vendor, or a problem with the test? Polaris is
configured permissively on purpose, so when an agent fails against it, the cause
is in the agent's wiring or the harness, not in a managed catalog.

It does four jobs in this article:

- **It proves the wiring.** Every agent answers its first question against
  Polaris before it touches a cloud catalog.
- **It holds the catalog still.** Tests 1 and 3 read only Polaris, so there is no
  network hop, managed service or region inside their timings -- three catalog
  calls take 0.12 seconds -- and a difference between agents belongs to the
  framework or the model.
- **It sets the baseline for the managed catalogs.** In Test 2 the same agent
  reads Polaris and the four cloud catalogs, so the extra tool time on each cloud,
  0.52 to 2.29 seconds, is measured against a catalog that adds none.
- **It measures the noise.** One cell, ADK on Polaris, runs in both Test 1 and
  Test 2, in separate sittings. Its medians differed by 0.26 seconds; a smaller
  difference than that cannot be told from run-to-run variation.

What it cannot test is storage wiring. Polaris keeps its table as local files, so
an agent reading it never touches cloud storage credentials or `FsspecFileIO`.
That part is tested only against the real clouds, in Test 4 and in the storage
wiring cases.

For a deeper dive: the [Apache Polaris site](https://polaris.apache.org/), its
[documentation](https://polaris.apache.org/docs/), and the
[source on GitHub](https://github.com/apache/polaris), which includes quickstarts
for running it locally.

## How the Tests Work

A single run of each cloud's agent proves the wiring works and nothing else. If
the framework, the model and the catalog all change together, no difference can
be attributed to any of them. So the shared parts are exactly one implementation
each:

| shared, one implementation | different, on purpose |
|---|---|
| the four Iceberg tools | the agent framework |
| the instruction, versioned | the model |
| the catalog-call budget | the catalog each leg reads |
| the stamped answer header | the serving runtime |

The runs are split into four tests. Each test changes one thing and holds the
rest still, so that when an answer comes back slower or wrong, there is only one
thing it can be blamed on:

| test | what changes | what stays the same | what it answers | evidence files |
|---|---|---|---|---|
| **Test 1** — the three agents, side by side | framework and model together | the catalog: the local control | how the three agents compare | Axis A |
| **Test 2** — same agent, five catalogs | the catalog | the agent: ADK on Gemini | whether where the data lives changes anything | Axis B |
| **Test 3** — framework or model? | the framework or the model, one at a time | the catalog | which of the two a speed difference belongs to | Axis C |
| **Test 4** — reading the real data | a data question, each agent on its own cloud | the question | whether each agent can read its own cloud's files | Axis D |

**Ten runs per cell, in shuffled rounds.** Each round runs every cell of a test
once, in an order shuffled from a fixed seed, so a slow patch on a model endpoint
lands across all cells rather than on whichever ran then. Separation between
cells is judged on the middle half of their runs, not the extremes. No run
failed to answer.

**Every time is answer time, on a warm agent.** Before the clock starts, each run
imports its framework, builds the agent, signs in and holds the catalog client,
by sending one untimed warm-up turn. Sign-in alone costs 1.25 to 1.53 seconds
through `DefaultAzureCredential`, 0.52 to 0.54 through Vertex AI's credentials and
0.06 through the AWS credential chain, and importing the frameworks takes 0.78
seconds for ADK, 0.45 for Strands and 0.24 for Agent Framework. Neither is in any
figure below. The timed answer is what a long-running agent would see.

**Every answer is scored against ground truth read straight from the catalog**,
not through any agent. Only the answer text is scored, with any reasoning a
framework prints inside it -- Nova Micro's `<thinking>` blocks -- removed first.
The row count has to sit beside the word "rows", each column has to appear as a
whole word, and the snapshot id and metadata location have to appear exactly. A
run that does all four passes every check. Before any evidence is published, the
scorer has to fail a planted answer that contains the right numbers without
stating them, such as `snapshot-id exists; payload region. 11`.

## Test 1: The Three Agents, Side by Side

Three legs, one catalog, ten runs each. The catalog is the local control, so
nothing about it varies between legs.

The three models are not matched. They differ in kind as well as speed:
Bedrock's model catalog lists Nova Micro as text in, text out, where Nova Lite and
Pro also take images and video. Each ran with its defaults -- no temperature,
thinking budget or reasoning effort was set on any leg. Each leg runs a model its
own cloud serves, which is the arrangement a real deployment would have, and it
is also why Test 3 exists.

| leg | framework and model | runs passing every check | answer seconds min/med/max | middle half of runs |
|---|---|---|---|---|
| aws | Strands, `us.amazon.nova-micro-v1:0` | 10/10 | 2.78 / 3.00 / 3.33 | 2.90 – 3.06 |
| gcp | ADK, `gemini-2.5-flash` | 10/10 | 4.77 / 5.67 / 7.05 | 5.19 – 6.69 |
| azure | Agent Framework, `gpt-5-mini` | 10/10 | 12.16 / 15.45 / 34.44 | 13.98 – 16.40 |

All three reach the same correct answer with the same three calls -- list,
describe, count. What separates them is latency: **about 5x from the fastest
median to the slowest** (15.45s / 3.00s = 5.14x). The middle halves do not
touch: AWS's upper quartile (3.06s) is below Google's lower (5.19s), and Google's
upper (6.69s) is below Azure's lower (13.98s).

The ordering is the same in every complete run of this test: 3.80x, 4.17x and
4.29x in three earlier runs of three repeats each, and 5.14x in this one. The
earlier runs timed sign-in inside each answer and ran cells in blocks, so their
ratios are not directly comparable with this one; the order is.

The tools are not where the time goes: three catalog calls take 0.12 seconds on
a warm client, about 2% of a median answer. Azure's slowest run took 34.44
seconds with almost none of it in the tools; the rest is the model, the framework
and the endpoint between them. And because this is a local catalog, the ratio is specific
to it: reading each leg's own managed catalog adds catalog time to every leg
(Test 2), which would narrow it.

## Test 2: Same Agent, Five Catalogs

One leg -- ADK on Gemini -- against five catalogs, ten runs each.

| catalog | runs passing every check | answer seconds min/med/max | middle half of runs | median seconds in tools |
|---|---|---|---|---|
| apache-polaris | 10/10 | 4.76 / 5.93 / 7.05 | 5.58 – 6.62 | 0.12 |
| aws-s3tables | 10/10 | 5.41 / 6.47 / 7.35 | 5.83 – 6.76 | 0.52 |
| aws-glue | 10/10 | 5.20 / 6.45 / 23.50 | 5.96 – 7.18 | 0.63 |
| google-lakehouse | 10/10 | 6.10 / 7.05 / 8.31 | 6.63 – 7.81 | 1.56 |
| microsoft-onelake | 10/10 | 6.18 / 8.45 / 29.60 | 6.84 – 9.88 | 2.29 |

The catalog shows up mostly in the tool column: 0.12 seconds for three calls
against the local control, and 0.52 to 2.29 seconds against the four managed
catalogs. That is distance from this machine as much as anything the catalog
does, and it is not a ranking of the services.

In the totals it is a smaller part. Cell medians run from 5.93 to 8.45 seconds, a
2.52-second range, narrower than the gaps between legs in Test 1 (2.66 and 9.78
seconds). Two managed catalogs produced one slow outlier each: OneLake's slowest
answer spent most of its time in a single slow read, and Glue's in the model.

Tests 1 and 2 both measure one cell, ADK on Polaris, in separate sittings, so the
matrix measures its own noise. That cell's medians were 5.67 and 5.93 seconds,
0.26 apart. A difference between catalogs smaller than that is not
distinguishable from run-to-run variation.

OneLake's correct answer differs from the others -- 6 rows and 3 columns, where
the rest hold 11 and 4 -- because it was loaded through the Fabric load-table API
rather than seeded with pyiceberg. Each answer is scored against its own catalog.

## Test 3: Framework or Model?

Test 1 cannot say how much of the 5x is the framework, because each leg pairs one
framework with one model. Test 3 adds one crossover: the Strands agent, unchanged
except for its model object, on `gemini-2.5-flash` through Vertex AI -- the model
and endpoint ADK uses. All thirty runs share shuffled rounds against the local
control.

| framework | model | runs passing every check | answer seconds min/med/max | middle half of runs |
|---|---|---|---|---|
| ADK | `gemini-2.5-flash` | 10/10 | 4.35 / 5.30 / 9.27 | 4.93 – 5.79 |
| Strands | `gemini-2.5-flash` | 10/10 | 6.12 / 6.97 / 8.51 | 6.55 – 7.90 |
| Strands | `us.amazon.nova-micro-v1:0` | 10/10 | 2.69 / 3.16 / 3.68 | 2.98 – 3.38 |

**The model matters most.** Holding Strands still and swapping Gemini for Nova
Micro moved the median by 3.81 seconds, 2.21x, with no overlap. That comparison
also changes provider and route -- Vertex AI in `us-central1` against Bedrock in
`us-east-1` -- and this layout cannot separate those from the model.

**The framework matters too.** Holding Gemini still and swapping ADK for Strands
moved the median by 1.67 seconds, 1.32x, and the middle halves do not overlap.
Both of those cells call the same model through the same endpoint, so this
comparison is the cleaner of the two. It is ten runs each, against a noise figure
of 0.26 seconds between sittings.

Agent Framework was not run on another model, so its 15.45-second median in Test 1
describes Agent Framework with `gpt-5-mini`, not Agent Framework alone. That model
may not be a free choice. In
[an earlier build](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
`store=False` -- which keeps the conversation from being stored server-side --
made the framework request encrypted reasoning content, which a non-reasoning
model rejected. This leg sets `store=False` too; that was not re-tested here.

## Test 4: Reading the Real Data

Tests 1 to 3 ask a question the agent's metadata tools can answer: the row count
lives in the snapshot summary and the columns in the schema. Not one of those
runs opens a data file. Test 4 asks something none of the agent's metadata tools
can answer, and sends each agent to its own cloud's catalog, so that answering
means reading GCS, S3 or ADLS through the storage wiring:

> What is the largest id in the probe table, and how many of its rows have an id
> of 10 or more? Cite the exact table version you read.

Iceberg's own metadata is not blind to this. Manifests carry per-file column
bounds, and on the control they put the largest id at 23 without reading a row.
None of the four tools exposes those bounds, so an agent here has to scan.

Ground truth comes from scanning each table directly: 23 and 8 on BigLake and
Glue, 21 and 4 on OneLake. The same scan checks each snapshot's `total-records`
against the rows in its data files, and they agree on all five catalogs.

| agent and catalog | largest id | rows with id of 10 or more | answer seconds min/med/max | middle half of runs |
|---|---|---|---|---|
| ADK / `gemini-2.5-flash` on BigLake | 10/10 | 10/10 | 11.75 / 13.66 / 19.89 | 12.99 – 15.17 |
| Strands / `us.amazon.nova-micro-v1:0` on Glue | 9/10 | 1/10 | 5.07 / 7.19 / 10.85 | 5.64 – 7.71 |
| Agent Framework / `gpt-5-mini` on OneLake | 10/10 | 10/10 | 23.21 / 27.88 / 30.54 | 24.95 – 28.79 |

**Every agent read its data.** ADK and Strands log a scan call in every run.
Agent Framework does not log its calls, but its answers name values that none of
the metadata tools return, in all ten runs.

**Strands on Nova Micro is the outlier.** It found the largest id in nine runs and
the filtered count in one, after four scans. The other runs gave a wrong count or
said they could not count, and one reported the largest id as 0. It also made
more catalog calls than the other two, up to seven against their three or four.
ADK and Agent Framework counted correctly from the same tool. Test 4 ran Strands
only on Nova Micro, so it cannot say whether the miscount belongs to the framework
or to the model.

Every leg is slower here than in Tests 1 to 3: a scan against a managed catalog
takes more tool time than metadata calls to the local control, and the rest of
each answer took longer too. The legs read different catalogs in different
regions, so these times compare nothing across clouds.

One behaviour of the scan tool is worth knowing: when an agent asks for exactly as
many rows as the table holds, the tool reports both that every row came back and
that there may be more.

## How Are the Three Agents Different?

The instruction is one string, the four tools are four async Python functions
with typed arguments and docstrings, and the budget of eight catalog calls is
enforced inside the tools. None of that changed between clouds. What changed is
everything around it.

### Building It

Here is the entire construction on each cloud. Not excerpts -- this is all of it.

**Google, ADK:**

```python
from google.adk.agents import LlmAgent
from google.adk.models.registry import LLMRegistry

LlmAgent(
    model=LLMRegistry.new_llm(model),   # resolved from a model id string
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
and Agent Framework take the functions as they are. ADK accepts a bare model id,
but resolves it to a new client each time the agent runs; resolving it once keeps
the client, and its token, alive between turns. None of that is hard, and none of
it translates: there is no shared agent object to write once. What ports is what
the frameworks are given, not the agents themselves.

### Running It

Calling each agent is a different job:

```python
# ADK: an agent does not run on its own. It needs a runner, a session,
# and a loop over the events the runner yields.
runner = InMemoryRunner(agent=agent, app_name="iceberg-agent")
session = await runner.session_service.create_session(app_name="iceberg-agent", user_id="probe")
async for event in runner.run_async(user_id="probe", session_id=session.id, new_message=message):
    ...   # collect the text parts, and the function_call parts to see the tools

# Strands: call the agent like a function. It keeps the conversation on the agent.
result = agent(question)

# Agent Framework: await the agent.
reply = await agent.run(question)
```

ADK assumes the agent lives inside an application with sessions. Strands assumes
a script, and remembers every turn on the agent object until you clear
`agent.messages`. Agent Framework sits between them.

### Signing In

- **ADK on Vertex AI** uses Application Default Credentials, the same login the
  `gcloud` CLI uses.
- **Strands on Bedrock** uses the boto credential chain. On a machine signed in
  with `aws login` that chain needs `botocore[crt]`; without it the agent fails
  before its first call while `aws sts get-caller-identity` still succeeds,
  because the CLI ships its own copy.
- **Agent Framework on Foundry** takes a project endpoint and a
  `DefaultAzureCredential`, which here resolved through the `az` CLI -- the
  slowest first sign-in of the three.

### What You Can See While It Runs

Two things differ here, and both mattered in this project.

**Whether you can see which tools the agent called.** ADK hands every tool call
back to your code as an event, and Strands prints a `Tool #1`, `Tool #2` line as
each one runs, so for both it could be confirmed from the captures that they
scanned the data in Test 4. Agent Framework, out of the box, shows only the final
answer, so its reading of OneLake had to be shown from the values in its answers
instead. It can report its tool calls through middleware or OpenTelemetry, which
were not turned on here.

**Whether the model's reasoning ends up inside the answer.** Nova Micro writes
`<thinking>` text, and Strands passes it through as part of the answer. Anything
that reads agent output automatically -- a scorer, a pipeline, another agent -- can
mistake it for the answer, because a number that appears only in the reasoning
looks like a stated result. The scorer here removes `<thinking>` blocks before
checking. Gemini under the same Strands agent produced none, so this comes from
the model, not the framework.

| framework / model | shows each tool call | reasoning inside the answer |
|---|---|---|
| ADK / `gemini-2.5-flash` | 80/80 | 0/80 |
| Strands / `gemini-2.5-flash` | 10/10 | 0/10 |
| Strands / `us.amazon.nova-micro-v1:0` | 30/30 | 30/30 |
| Agent Framework / `gpt-5-mini` | 0/20 | 0/20 |

Strands also streams every answer to the terminal as it is written, so code that
prints the result shows it twice; `callback_handler=None` turns that off.

## Storage Wiring Per Catalog

Three configurations reach the catalog and cannot read the data. Each is
reproduced in the evidence with `iceberg_list_tables` succeeding immediately
before `iceberg_scan_table` fails, and a control runs the same two calls with the
tool's wiring unchanged, and reads.

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
catalog vends rather than local ones. In all three, the error names something
other than the missing configuration.

One configuration that looks as though it should fail does not. With fsspec and
the OneLake account host in place, removing only the ADLS credential still reads
the table, because adlfs resolves `DefaultAzureCredential` on its own.

Signing the catalog calls and reading the files the catalog points at take two
different credentials. That wiring -- `FsspecFileIO` and an account host for
OneLake, local credentials for Glue, vended ones for S3 Tables' managed bucket --
lives inside the tool and is written once per catalog. It differs even between
two catalogs on the same cloud. An agent that reads Iceberg is portable at the
catalog. At the files, it is configured.

## Where Do I Start?

The strategy for building a portable Iceberg agent is an incremental step by step
approach.

First, the Python environment is set up and the local Polaris control catalog is
brought up, so every leg can be tested without a cloud catalog in the path.

Then, each leg is asked one question against the control. Once all three answer
it correctly, ground truth is captured from every catalog, the tests run, and the
evidence is re-scored and published.

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

Both requirements files are needed: the tool imports the conformance harness's
credential flows rather than reimplementing six of them. In a fresh venv the pair
resolves in about 20 seconds.

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

```console
$ cd ../iceberg-conformance
$ cp catalogs.example.yaml catalogs.yaml
$ ./polaris-up.sh
$ curl -s http://localhost:8182/q/health/ready
{"status": "UP", "checks": [...]}
```

`polaris-up.sh` starts the container and seeds `probe_ns.probe_table`: 11 rows,
four columns, partitioned by day -- the same fixture as three of the four managed
catalogs. The flags it needs are explained in the earlier article.

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

Every answer carries that stamped header -- cloud, model, catalog, instruction
version and call count -- so an answer produced by an older instruction, or by an
agent that never called its tools, can be told apart. The last line splits the
answer's time into tool time and the rest. Add `--warm` to sign in and build the
catalog client before the clock starts, as the tests do.

Run the same command with `aws` and `azure`, check that each answers 11 rows for
the same snapshot, and then drop `--catalog` so each leg reads its own cloud's
catalog: BigLake for ADK, Glue for Strands, OneLake for Agent Framework.

### The Four Tools

Four async callables, read-only, sharing one budget of eight catalog calls per
answer:

- `iceberg_list_tables` — discovery
- `iceberg_describe_table` — columns, partitioning, and the metadata location
- `iceberg_count_rows` — exact count from the snapshot summary
- `iceberg_scan_table` — rows, and says whether it returned every row of the
  snapshot or only some of them

They use only operations in the nine that all seven catalogs serve, so a reading
agent built this way is the portable case. A tool that listed views or planned a
scan would not be: views fail on six of the seven, and scan planning on all
seven.

Every table description ends with the version to cite. An Iceberg table's
`metadata-location` and `snapshot-id` name an exact immutable version, so handing
them to the model makes a real citation cheaper than an invented one, and makes
the claim checkable. The
[research-agent version of this comparison](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc)
does the same with source URLs.

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

Counting uses the snapshot summary in one metadata call. The scan tool returns
at most 100 rows, and says when it may have stopped short, so a sample is not
reported as a total:

```console
$ python3 -c "
import asyncio, iceberg_tool as t
print(asyncio.run(t.iceberg_count_rows('probe_ns.probe_table')))
print(asyncio.run(t.iceberg_scan_table('probe_ns.probe_table', limit=3)))"
11 rows, from the snapshot summary (total-records) of snapshot-id 5653331815319537848. This is exact for that snapshot.
...
NOTE: exactly 3 row(s) came back, which is the limit, so there are probably more. Do NOT report this as the table's row count. If you were asked how many rows the table has, say you sampled 3 and could not count the whole table.
```

## Step 5 — Capture Ground Truth

Ground truth comes from pyiceberg against each catalog, with no agent in the
path:

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
the summary against the data. `max_id` and `ids_at_least_10` are what Test 4 is
scored against. Nothing is written unless every catalog answers.

## Step 6 — Run the Tests

```console
$ python3 run_matrix.py --axis A --repeat 10
...
$ python3 run_matrix.py --axis B --repeat 10
...
$ python3 run_matrix.py --axis C --repeat 10
...
$ python3 run_matrix.py --axis D --repeat 10
  ...
  aws                               aws-glue            run 5    9.1s  agent=7.57s tool=2.16s  correct_max_id=NO correct_count=NO cites_snapshot=ok calls=5
  ...
  azure                             microsoft-onelake   run 6   42.1s  agent=28.37s tool=5.0s  correct_max_id=ok correct_count=ok cites_snapshot=ok calls=4
  ...
```

The scripts keep the letters A to D for Tests 1 to 4. Each run warms up before it
is timed, and each round shuffles the cell order from a fixed seed. Run each test
alone: its latencies are published, and anything else running on the machine or
against the same model endpoints is in them. Runs write only to a gitignored raw
directory, because a loaded table can carry real account identifiers.

## Step 7 — Publish the Evidence

```console
$ python3 publish_evidence.py
...
$ cd .. && ./check-no-identifiers.sh
...
clean
```

`publish_evidence.py` is the only path into the article's evidence directory. It
re-scores every capture from its own body rather than trusting the runner,
refuses if the two disagree, refuses if the scorer passes a planted empty answer,
counts any run that did not answer, and maps account identifiers to stable
pseudonyms on the way out. Every figure in this article comes from the evidence
files it writes.

## How Does This Compare to Other Work?

A search of published work in September 2026 found related pieces on each side of
this question, and none that combines them: the same agent built in the three
hyperscalers' frameworks, reading several Iceberg REST catalogs, with answers
scored against ground truth read from the catalog.

**Comparing agent frameworks.** The closest is
[LaunchDarkly's benchmark](https://launchdarkly.com/docs/tutorials/agent-graph-experiments)
of LangGraph, Strands, the OpenAI Agents SDK and ADK on the same agent graph, with
the model pinned to one Claude model, over 36 runs scored by an LLM judge.
Strands was fastest, and most differences were "within a few percent". That
agrees in direction with Test 3 here, where swapping the framework moved answer
time far less than swapping the model. It covers research-paper analysis rather
than data, and does not include Agent Framework or any catalog.

**Benchmarking data agents.**
[DAB](https://arxiv.org/abs/2603.20576), [FDABench](https://arxiv.org/abs/2509.02473)
and [KramaBench](https://arxiv.org/abs/2506.06541) measure whether agents answer
questions over databases and data lakes correctly. DAB's 54 queries across four
database systems left the best of five models at 38% pass@1. These benchmarks
vary the model and the task; this article holds the task deliberately simple and
varies the framework and the catalog instead.

**Where agent time goes.**
[Bian et al.](https://arxiv.org/abs/2510.16276) found that environment and tool
latency can reach 53.7% of total latency in web-based agents. Against a local
Iceberg catalog, tool time here was about 2% of an answer; against managed
catalogs it was larger. That is why every answer here records its tool time
separately.

**Agents over Iceberg.** Tooling exists -- an official
[AWS Labs MCP server for S3 Tables](https://github.com/awslabs/mcp/tree/main/src/s3-tables-mcp-server),
community Iceberg MCP servers, and written patterns such as
[MCP and Apache Iceberg](https://iceberglakehouse.com/iceberg/iceberg-mcp/) --
along with architectures such as AWS's
[multi-cloud lakehouse for agentic AI](https://aws.amazon.com/blogs/big-data/multi-cloud-lakehouse-architecture-on-aws-for-agentic-ai-part-1-architecture-and-best-practices/),
which federates Databricks and Snowflake catalogs through Glue. None of these
publish measurements of correctness or latency.

This article builds on two earlier ones: the
[catalog side](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj),
which measured seven Iceberg REST catalogs, and the
[framework side](https://dev.to/gde/three-clouds-one-brief-what-actually-differs-between-adk-strands-and-agent-framework-2kgc),
which built one research agent in the same three frameworks.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and across catalogs. The key
to the solution was building one implementation of the four tools, binding it
into three frameworks unchanged, and splitting the runs into four tests so that
the catalog, the framework, the model and the data path could each be varied on
its own. The results were:

- **The code ports.** Three small construction differences; the tools and the
  instruction bind unchanged.
- **Speed goes mostly with the model, and measurably with the framework.** About
  5x between the three agents as shipped, 2.21x from swapping the model under
  Strands, 1.32x from swapping the framework under Gemini.
- **The storage wiring does not port, and works once written.** Every agent read
  its own cloud's data files; ADK and Agent Framework answered the data question
  correctly in all ten runs, and Strands on Nova Micro counted correctly in one.
- **All three answer the simple question correctly** and cite the table version
  they read, in every one of 110 runs.

Scope:

- One machine, 2026-09-15, the versions shown above, every model at its defaults.
- Ten runs per cell in shuffled rounds, on a warm agent: 110 runs of a metadata
  question and 30 of a data question. Enough to see a separation, not to estimate
  a rate precisely.
- Test 3 separates framework from model for ADK and Strands only; Agent Framework
  stays confounded with `gpt-5-mini`. The model comparison also changes provider
  and region.
- Polaris is local and the other catalogs are managed services in different
  regions, so no time here is a fair comparison between clouds.
- The OneLake fixture differs from the other four; output length, cost and token
  counts were not controlled or measured.
- Earlier runs of three repeats each are published under
  `evidence/superseded-runs/`, re-scored by the same checks.

The strategy for using one shared set of Iceberg tools across three agent
frameworks was validated with an incremental step by step approach.
