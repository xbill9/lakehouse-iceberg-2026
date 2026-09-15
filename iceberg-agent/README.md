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
reproduced deliberately by `failure_modes.py`, into
[`../papers/iceberg-agent-three-clouds/evidence/failure-modes.txt`](../papers/iceberg-agent-three-clouds/evidence/failure-modes.txt),
which shows `iceberg_list_tables` succeeding immediately before
`iceberg_scan_table` fails, so the catalog is demonstrably reachable in all
three. A control runs the same calls with the wiring unchanged.

| configuration | what the data call returns |
|---|---|
| OneLake, no ADLS configuration at all (`PyArrowFileIO`, no `adls.*` properties) | `TypeError: __init__() takes exactly 1 positional argument (0 given)` |
| OneLake, ADLS credential but `PyArrowFileIO` | `OSError: GetProperties failed for 'https://onelake.blob.core.windows.net/...'` -- a host that does not exist, because PyArrow ignores `adls.account-host` |
| Glue, SigV4 for the catalog but no local S3 credentials | `OSError: ... AWS Error ACCESS_DENIED during HeadObject` on a bucket the caller owns outright |
| OneLake, fsspec and account host, `adls.credential` removed | reads -- adlfs resolves `DefaultAzureCredential` itself when handed none |

The first row was labelled "no ADLS credential" until 2026-09-14, when removing
only the credential turned out to read successfully -- the last row. The
`TypeError` needs the whole Azure storage configuration absent. The last row is
kept as a null result.

Signing the catalog calls, and being able to read the files the catalog points
at, are two different credentials. In each failing case the error names
something other than the missing configuration. The tool now configures both.

OneLake's data path also needs `adlfs`, the fsspec filesystem for `abfss://`. It
is an optional pyiceberg extra, and without it every scan returns
`ModuleNotFoundError` while every metadata call succeeds. `requirements.txt`
names it.

## Producing the evidence

Nothing writes into `../papers/iceberg-agent-three-clouds/evidence/` except
`publish_evidence.py`. Every run writes to the gitignored
`../iceberg-conformance/evidence/paper3-raw/`, which holds real account
identifiers.

A re-run overwrites the previous run's captures by name. Archive the previous
run first, then add it to `SUPERSEDED` in `publish_evidence.py`, which publishes
every archived run under `superseded-runs/` and writes the replication figures
into `derived-figures.txt`:

```console
$ cd ../iceberg-conformance/evidence/paper3-raw && mkdir runN-<label> && cp -a matrix matrix-axis-*.json *.txt runN-<label>/ && cd -
$ python3 capture_ground_truth.py          # read each catalog directly; also environment.txt
$ python3 run_matrix.py --axis A --repeat 3
$ python3 run_matrix.py --axis B --repeat 3
$ python3 run_matrix.py --axis C --repeat 3  # model fixed, framework varies: Strands on Gemini is the crossover
$ python3 capture_runs.py                  # each leg against its own cloud's catalog
$ python3 failure_modes.py
$ python3 publish_evidence.py              # re-score, summarise, anonymise, publish
```

Run the two axes alone. Their latencies are published, and anything else
running on the machine or against the same model endpoints is in them.

`publish_evidence.py` re-scores every capture from its body rather than trusting
the runner, and refuses to publish if the two disagree. It exists because the
first matrix named captures `leg__catalog__run`: both axes run gcp against the
control, so Axis B overwrote three Axis A captures, and the article published
three rows with nothing behind them. Captures now carry the axis in their name.

Every answer also records `agent seconds` (the answer alone, after imports) and
`tool seconds` (the part spent inside the Iceberg tools). The difference is the
model and the framework, which is how a slow run is attributed instead of
guessed at.
