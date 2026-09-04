---
title: "One Iceberg Tool, Three Agent Frameworks: What Ports, and What Doesn't"
published: false
description: "One read-only Apache Iceberg REST catalog tool bound into Google ADK, AWS Strands and Microsoft Agent Framework, run against five catalogs. 24 runs, 24 correct answers with cited table versions, and a 4.46x latency spread that follows the framework rather than the catalog."
tags: iceberg, aiagents, lakehouse, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/iceberg-agent-three-clouds/cover.62b85b80.jpg
---

This article provides a step by step build of one read-only Apache Iceberg REST
catalog tool, bound into three vendor-native agent frameworks and run against
five catalogs. A Python tool suite is built so that only the framework, the
model and the catalog differ, and every answer is scored against ground truth
read from the catalog itself.

https://github.com/xbill9/lakehouse-iceberg-2026

An earlier article measured seven Iceberg REST catalogs and found that the read
path is the only surface all seven serve. This one asks the obvious follow-up:
if an agent only reads, is it portable?

All results below were measured on 2026-09-04.

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

And the runs are split into two axes rather than one grid:

- **Axis A** holds the catalog still and varies the framework and model
- **Axis B** holds the leg still and varies the catalog

Three runs per cell, so a disagreement means something.

## At This Point You Should Have

- Python 3.13 with `pyiceberg`, and the three frameworks installed
- A catalog to read, seeded with a table
- Each cloud configured: Vertex AI for ADK, Bedrock model access for Strands,
  and a Foundry project endpoint for Agent Framework

```console
$ python3 -c "
import google.adk, strands, agent_framework, pyiceberg, sys
print('python          ', sys.version.split()[0])
print('google-adk      ', google.adk.__version__)
print('agent-framework ', agent_framework.__version__)
print('pyiceberg       ', pyiceberg.__version__)"
python           3.13.13
google-adk       2.6.3
agent-framework  1.17.0
pyiceberg        0.12.0
```

## The Tools

Four async callables, read-only, sharing one budget of eight catalog calls per
answer:

- `iceberg_list_tables` — discovery
- `iceberg_describe_table` — columns, partitioning, and the metadata location
- `iceberg_count_rows` — exact count from the snapshot summary
- `iceberg_scan_table` — sampled rows, and says so when the view is partial

Read-only is a decision, not a limitation of effort. The conformance work found
the read surface is the one all seven catalogs agree on, so a reading agent is
the portable case worth measuring.

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
current-snapshot-id: 665485744733371229
metadata-location: file:/.../metadata/00006-d1d68896-6de0-4417-80b8-1cc149ebed7e.metadata.json

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
11 rows, from the snapshot summary (total-records) of snapshot-id 665485744733371229. This is exact for that snapshot.
```

The scan tool also warns when the view it returned is partial, which is what
stops a sample being reported as a total:

```console
NOTE: exactly 3 row(s) came back, which is the limit, so there are probably more.
Do NOT report this as the table's row count. If you were asked how many rows the
table has, say you sampled 3 and could not count the whole table.
```

## Three Frameworks, Three Shapes for the Same Agent

Here is the entire construction on each cloud. Not excerpts — this is all of it,
and the tools and instruction are the same objects in all three.

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

Agent(
    client=FoundryChatClient(project_endpoint=..., model=model, credential=...),
    instructions=common.INSTRUCTION,    # `instructions`
    tools=list(iceberg_tool.TOOLS),
)
```

A model id string, a model object, a client object. `instruction`,
`system_prompt`, `instructions`. That is the whole delta.

## Reading the Data Is Not the Same as Reading the Catalog

Three configurations reach the catalog and cannot read the data. Each one is
reproduced deliberately in the evidence, with `iceberg_list_tables` succeeding
immediately before `iceberg_scan_table` fails, so the catalog is demonstrably
reachable in all three.

```console
$ # A. OneLake, no ADLS credential configured
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

Signing the catalog calls and reading the files the catalog points at are two
different credentials. In all three cases the error names something other than
the missing credential.

## Axis A: Catalog Fixed, Framework and Model Vary

Three legs, one catalog, three runs each. The catalog is the local Polaris
control, so nothing about it varies between legs.

| leg | framework and model | correct | cites snapshot | cites metadata | seconds min/med/max |
|---|---|---|---|---|---|
| 🥇 aws | Strands, `us.amazon.nova-micro-v1:0` | 3/3 | 3/3 | 3/3 | 4.6 / 4.6 / 4.8 |
| 🥈 gcp | ADK, `gemini-2.5-flash` | 3/3 | 3/3 | 3/3 | 11.3 / 13.4 / 15.1 |
| 🥉 azure | Agent Framework, `gpt-5-mini` | 3/3 | 3/3 | 3/3 | 18.5 / 20.5 / 23.0 |

Every run used exactly three catalog calls: list, describe, count.

All three frameworks reach the same correct answer with the same call pattern.
What separates them is latency, and the separation is clean — **4.46x from the
fastest median to the slowest**, with no overlap between any pair. AWS's slowest
run (4.8s) is faster than Google's fastest (11.3s), and Google's slowest (15.1s)
is faster than Azure's fastest (18.5s).

That figure is a framework-and-model result together, not a framework result.
This layout holds the catalog still, so it separates the catalog out — it does
not separate the framework from the model it runs.

## Axis B: Leg Fixed, Catalog Varies

One leg — ADK on Gemini — against five catalogs, three runs each.

| catalog | correct | cites snapshot | cites metadata | seconds min/med/max |
|---|---|---|---|---|
| apache-polaris | 3/3 | 3/3 | 3/3 | 12.8 / 13.3 / 13.3 |
| google-lakehouse | 3/3 | 3/3 | 3/3 | 13.5 / 15.6 / 15.8 |
| aws-glue | 3/3 | 3/3 | 3/3 | 12.3 / 12.6 / 13.3 |
| aws-s3tables | 3/3 | 3/3 | 3/3 | 11.5 / 11.7 / 12.4 |
| microsoft-onelake | 3/3 | 3/3 | 3/3 | 12.1 / 13.0 / 15.0 |

Five catalogs on four clouds, and none is distinguishable from another. The
whole range is 11.5 to 15.8 seconds, narrower than the gap between any two legs
in Axis A.

The correct answer is not the same in every row. OneLake's table holds 6 rows
and 3 columns where the others hold 11 and 4, because it was loaded through the
Fabric load-table API rather than seeded with pyiceberg. Each answer is scored
against ground truth read from its own catalog, so a leg that reported 11 rows
against OneLake would be marked wrong.

## What the Agents Actually Answered

```console
$ python3 run_once.py azure "How many rows are in the probe table, and what columns does it have? Cite the exact table version you read."
<!-- cloud=azure model=gpt-5-mini catalog=microsoft-onelake instruction=v2 catalog_calls=3 -->
- Exact row count: 6 rows.
  - Source: iceberg_count_rows for dbo.probe_table, true for snapshot-id 3346142071915475645.
  - metadata-location abfss://...@onelake.dfs.fabric.microsoft.com/.../Tables/probe_table/metadata/v3.metadata.json
```

Every answer carries a stamped header giving the cloud, model, catalog,
instruction version and call count. Without it, an answer that looks wrong
cannot be told from one produced by an older instruction, and an agent that
never called its tools looks identical to one that did.

## Summary

The goal of this article was to find out whether a data agent that only reads
Apache Iceberg is portable across agent frameworks and across catalogs. The key
to the solution was building one tool implementation, binding it into three
frameworks unchanged, and splitting the runs into two axes so that the framework
and the catalog could be varied separately. The results were:

- **24 of 24 runs answered correctly**, across three frameworks and five
  catalogs, each citing the metadata location and snapshot id of the version it
  read.
- **No invented columns in any run.** OneLake's table has no `region` column and
  no answer against OneLake named one.
- **Every run used exactly three catalog calls** — list, describe, count — out
  of a budget of eight.
- **The framework and model together account for a 4.46x latency spread**, with
  no overlap between legs.
- **The catalog accounts for none of it.** Five catalogs across four clouds span
  11.5 to 15.8 seconds through the same leg.
- **Binding the same tool three times is a three-line difference** — a model id
  string against a model object against a client object.

Scope: one question, asked three times per cell, on 2026-09-04; Axis A is three
legs against one catalog and Axis B is one leg against five, so 24 runs rather
than the full 45-cell grid; every cell passed every check, which means the
question is not hard enough to discriminate beyond latency; the three legs vary
framework and model together and this layout cannot separate them; Polaris runs
locally while the other four are managed services in different regions, so the
Axis B latencies are not a fair comparison between clouds; and the OneLake
fixture differs from the other four because it was loaded through the Fabric API
rather than pyiceberg.

The strategy for using one shared Iceberg tool across three agent frameworks was
validated with an incremental step by step approach.
