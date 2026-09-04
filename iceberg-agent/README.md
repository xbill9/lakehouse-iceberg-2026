# One Iceberg tool, three clouds' agents

Three vendor-native agents, each built with its own cloud's framework, each
reading Apache Iceberg tables through its own cloud's REST catalog, all sharing
one tool implementation.

Supports **paper 3** of the series (see `../papers/iceberg-agent-three-clouds/`).

## What varies, and what does not

The rule is the one the research-agent mesh already proved: share everything
that is not the variable under test. Three agents differing in framework,
model, tool, instruction and budget cannot attribute any result to any of them.

| shared, one implementation | different, on purpose |
|---|---|
| the four Iceberg tools | the agent framework |
| the instruction, versioned | the model |
| the catalog-call budget | the catalog each leg reads |
| the stamped answer header | the serving stack |

The catalog is in the right-hand column deliberately. Pointing all three at one
catalog would test three frameworks against one server; pointing each at its own
cloud's catalog exercises the surface the conformance work found to be the only
interoperable one.

| leg | framework | model | catalog |
|---|---|---|---|
| `gcp/` | Google ADK | `gemini-2.5-flash` | BigLake |
| `aws/` | AWS Strands | `us.amazon.nova-micro-v1:0` | Glue |
| `azure/` | Microsoft Agent Framework | `gpt-5-mini` | OneLake |

Framework differences are the whole delta: ADK takes a model id string and plain
callables, Strands takes a model *object* and decorated tools, Agent Framework
takes a chat client object and calls the system prompt `instructions`.

## The tools

`iceberg_tool.py` — read-only, four async callables sharing one budget:

- `iceberg_list_tables` — discovery
- `iceberg_describe_table` — columns, partitioning, and the metadata location
- `iceberg_count_rows` — exact count from the snapshot summary, no scan
- `iceberg_scan_table` — sampled rows, and says so when the view is partial

Every result carries the table's `metadata-location` and `snapshot-id`. That is
the data-side equivalent of putting a URL on a search result: an agent asked
where a figure came from will otherwise name a table it never opened, and those
two values name an exact immutable version a reader can check.

`iceberg_count_rows` exists because counting by scanning is not counting.
`iceberg_scan_table` returns at most 100 rows and says so, so counting what it
returns gives the sample size rather than the table's. Before this tool existed,
answering "how many rows" required the model to guess a limit large enough to
cover the table -- which measures the guess, not the catalog. Counting now reads
`total-records` from the snapshot summary in one metadata call.

## Running one leg

```console
$ export PYTHONPATH=../iceberg-conformance
$ export ICEBERG_CATALOGS_FILE=../iceberg-conformance/catalogs.yaml
$ python3 run_once.py gcp "How many rows are in the probe table?"
```

`--catalog NAME` points a leg at a different catalog, which is how a leg is
tested against the local Polaris control before spending tokens on a cloud.

Each leg needs its own cloud configured: `GOOGLE_GENAI_USE_VERTEXAI` and a
project for ADK, AWS credentials and Bedrock model access for Strands, and
`FOUNDRY_PROJECT_ENDPOINT` for Agent Framework.

## Reading the data is not the same as reading the catalog

Three configurations reach the catalog and cannot read the data. Each is
reproduced deliberately in
[`../papers/iceberg-agent-three-clouds/evidence/failure-modes.txt`](../papers/iceberg-agent-three-clouds/evidence/failure-modes.txt),
which shows `iceberg_list_tables` succeeding immediately before
`iceberg_scan_table` fails, so the catalog is demonstrably reachable in all
three.

| configuration | what the data call returns |
|---|---|
| OneLake, no ADLS credential | `TypeError: __init__() takes exactly 1 positional argument (0 given)` |
| OneLake, ADLS credential but `PyArrowFileIO` | `OSError: GetProperties failed for 'https://onelake.blob.core.windows.net/...'` -- a host that does not exist, because PyArrow ignores `adls.account-host` |
| Glue, SigV4 for the catalog but no local S3 credentials | `OSError: ... AWS Error ACCESS_DENIED during HeadObject` on a bucket the caller owns outright |

Signing the catalog calls, and being able to read the files the catalog points
at, are two different credentials. In each case the error names something other
than the missing credential. The tool now configures both.
