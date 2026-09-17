---
title: "One Iceberg MCP Server, Three CLI Hosts: What a Tool List Bounds, and What It Doesn't"
published: false
description: "Four read-only Apache Iceberg tools served over MCP to claude, codex and agy, against an 11-row table and a 99,999-row table, 144 graded runs. One host serves no MCP tools at all; no model is accepted by two hosts; and withholding a tool from a coding agent does not withhold the capability."
tags: mcp, iceberg, aiagents, dataengineering
cover_image: https://raw.githubusercontent.com/xbill9/lakehouse-iceberg-2026/main/papers/iceberg-mcp-hosts/cover.c04aee28.jpg
---

This article is a step by step build of one Apache Iceberg MCP server, driven by three
CLI coding agents: Anthropic's `claude`, OpenAI's `codex` and Google's `agy`. The same
four tools are offered to each host, against the same two tables.

Every answer is checked against the catalog itself, and every tool call the host made
is on record, so what the host read is measured rather than described.

https://github.com/xbill9/lakehouse-iceberg-2026

## What Is This Project Trying to Do?

An [earlier article](https://dev.to/gde/four-iceberg-tools-three-agent-frameworks-what-ports-and-what-doesnt-a5g)
built the same small Iceberg data agent three times — Google ADK, AWS Strands,
Microsoft Agent Framework — and measured what ported. Those are libraries: you write
the loop, you choose the model, you hand it the tools.

A CLI coding agent is not a library. You install it, it brings its own loop and its own
model, and you give it tools by pointing it at an MCP server. The tools in that server
are the surface the agent is supposed to work through.

This project takes the four tools from that earlier agent — list the tables, describe
one, count its rows, read some rows — puts them behind an MCP server, and asks the same
six questions through each host.

- **claude** — `claude -p`, Claude Code 2.1.273
- **codex** — `codex exec`, codex-cli 0.154.0
- **agy** — `agy --print`, 1.2.3

The interesting part is not which host answers best. It is what the tool list actually
bounds. Measured on 2026-09-16 (UTC), 144 graded runs.

**Nothing here is about any of these products being broken.** Every figure any of them
reported was exact and correctly cited. One of the three is not measured at all, for a
reason given below, and that is reported rather than scored.

## Where Do I Start?

The strategy is an incremental step by step approach. First, a local Apache Polaris
catalog, so the control column needs nothing but Docker. Then a table seeded into it,
and the answers read straight out of the catalog with PyIceberg — never through a host.
Then the MCP server, proved by hand at the protocol level before any agent sees it.
Then the hosts.

## At This Point You Should Have…

- Docker, for the Apache Polaris control catalog
- Python 3.12+, with `pyiceberg` and `pyarrow`
- At least one of the three CLI hosts installed and signed in
- Optional: the seven-catalog credentials from the
  [conformance harness](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj),
  if you want to point the same server at BigLake, Glue or OneLake instead

## Setup the Basic Environment

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-conformance
$ ./polaris-up.sh
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 seed_table.py --catalog apache-polaris
```

That is the 11-row control table: three appends, a delete, a schema evolution and a tag,
so the metadata has snapshots and history to read rather than a single flat commit.

## Step 1 — Seed a Table Too Big to Count

```console
$ cd ../iceberg-mcp-hosts
$ python3 seed_large.py --catalog apache-polaris
```

```plaintext
created probe_ns.probe_large
appended 0..19999 -> snapshot ...
appended 80000..99999 -> snapshot 783184425684276424
deleted id=1000001

--- seeded ---
  total-records   99999
  snapshots       6
  schemas         2
  refs            ['main', 'scale_tag']
```

**99,999 and not 100,000 is deliberate.** A round number is the number to reach for when
guessing, and a lucky guess would be indistinguishable from a count. The ids start at
1,000,000 for the same reason: at base zero the table held 99,999 rows whose largest id
was also 99,999, and a correct count could not be told apart from an answer echoing the
largest id it had seen.

## Step 2 — Read the Answers From the Catalog

```console
$ python3 ground_truth.py --catalog apache-polaris --table probe_large
```

```plaintext
catalog=apache-polaris table=probe_ns.probe_large
  table=probe_ns.probe_large
  rows=99999
  namespaces=probe_ns
  namespace_count=1
  snapshots=6
  absent_namespace=analytics
  columns=id,ts,payload,region
  snapshot_id=520235497352034082
  metadata_location=file:/.../probe_large/metadata/00008-6afdfe20-....metadata.json
  range_id=1000000|1099999
  range_ts=2026-09-01 00:00:00+00:00|2026-09-04 23:59:59+00:00
```

Every value comes from PyIceberg against the REST catalog directly. Nothing under test
is ever asked whether it was right. `absent_namespace` is recorded only after checking
that `analytics` really is not there, so the question built on it stays a real question.

## Step 3 — Serve the Tools Over MCP

The server imports the four tools from the earlier agent rather than reimplementing
them, and speaks newline-delimited JSON-RPC directly — four methods, no SDK dependency.

```console
$ ICEBERG_CATALOG=apache-polaris python3 servers/iceberg_mcp.py
```

Proved at the protocol level before any host sees it:

```plaintext
serverInfo: {"name": "iceberg", "version": "1.0.0", "instructionVersion": 3,
             "scanFilter": "1", "catalog": "apache-polaris"}

tools/list -> 4 tools
  iceberg_list_tables      req=[]
  iceberg_describe_table   req=['table']
  iceberg_count_rows       req=['table']
  iceberg_scan_table       req=['table']

tools/call iceberg_list_tables  isError=False
probe_ns.probe_large
probe_ns.probe_table
```

### The one variable: who does the arithmetic

Two configurations of the same server:

| variant | tools offered | scan tool |
|---|---|---|
| `ours-engine` | four | takes a `where`, returns an exact count, min and max |
| `ours-rows` | three | rows only, no filter, capped at 100 |

`ours-rows` withholds `iceberg_count_rows` outright — it is absent from `tools/list`, and
a call to it is refused. The instruction the server sends is rewritten to match, so the
model is not told to use a tool it cannot see.

**This is the whole experiment.** With `ours-engine`, the engine computes and the model
quotes. With `ours-rows` against 99,999 rows, there is no tool that can produce the
count, and the scan says so:

```plaintext
100 row(s), read from snapshot-id 520235497352034082
NOTE: you asked for 100000 rows and this tool returns at most 100, so the rows
above are a SAMPLE, not the whole table.
```

Against the 11-row table the same tool says the opposite, which is why that table is the
control arm:

```plaintext
11 row(s), read from snapshot-id 4496289927168545616
COMPLETE: these are all 11 rows in this snapshot (total-records 11), so values,
maxima and counts read from them are exact for snapshot-id 4496289927168545616.
```

## Step 4 — Put Every Frame on Record

Each stdio server runs behind a proxy that logs the JSON-RPC in both directions,
arguments in full:

```plaintext
  0.00s  initialize                 {}
  0.06s  tools/list                 {}
  4.90s  tools/call  iceberg_list_tables     {"namespace": ""}
  6.32s  tools/call  iceberg_describe_table  {"table": "probe_ns.probe_table"}
  7.75s  tools/call  iceberg_count_rows      {"table": "probe_ns.probe_table"}
```

The argument is the measurement. A count produced by an aggregate and a count produced
by pulling rows back are the same number from different places, and only the frame says
which.

## Step 5 — Run the Matrix

```console
$ python3 run_matrix.py --axis A --host claude --only ours-engine,ours-rows \
      --repeat 3 --table probe_large
```

```plaintext
scorer v11: 36 planted cases pass

  claude  ours-rows     Q4 r1   35.7s  answered calls=iceberg_list_tables,iceberg_describe_table
  claude  ours-engine   Q4 r1   11.6s  answered calls=iceberg_list_tables,iceberg_describe_table,iceberg_count_rows
```

Grading is string and integer comparison against the ground-truth file. The scorer
refuses to run until 36 planted answers score as expected, half of which must fail.

🔎 **Tip: a check that cannot fail reads exactly like a check that passes.** Every field
is cross-scored against every question's answers — apply the row-count check to the
column answers, the range check to the namespace answers. A field that passes on answers
it is not for is measuring nothing. That table is published as
`evidence/scorer-discrimination.txt`.

## Test 1 — Does Each Host Serve the Tools to Its Model?

| host | registers the server | model sees the tools | calls them |
|---|---|---|---|
| claude | per invocation, `--mcp-config` | yes | yes |
| agy | global, `agy mcp add` | yes | yes |
| codex | global, `codex mcp add` | no | no |

`codex exec` registers the server — `codex mcp list` shows it enabled, and the entry is
written to `~/.codex/config.toml` for the life of the run. Asked directly, and told not
to use the shell, it answers:

```plaintext
NO MCP TOOLS
```

No frame reaches the server in any run. Checked before concluding it: the server answers
`initialize`, `tools/list` and `tools/call` correctly when spoken to directly, and the
other two hosts drive it to correct answers; registration happens; the cached tool list
holds codex's own built-in surface, not this one; and `-c experimental_use_rmcp_client=true`
changes nothing.

Two other things were found and fixed first, and neither explains it. `codex exec`
defaults to approval policy `never` inside a read-only sandbox and refuses MCP calls
outright — `--dangerously-bypass-approvals-and-sandbox` is the counterpart to the other
two hosts' `--dangerously-skip-permissions`, and without it the codex column would have
measured a flag this harness failed to set. That same read-only sandbox also stops the
trace proxy writing its file.

**codex is therefore reported, not scored.** A cell that ran with no tools would have
looked like a host answering badly, and it is not that.

The other two differ in a way that matters beyond plumbing. `claude` takes `--mcp-config`
per invocation with `--strict-mcp-config`, so nothing global changes and one run cannot
contaminate the next. `codex` and `agy` configure servers in persistent global state. On
two of the three hosts, **which tools the agent has is machine state, not a property of
the request** — and during setup both were carrying an unrelated MCP server installed by
a plugin, which `claude` never saw.

## Test 2 — Can the Model Be Held Constant Across Hosts?

No.

```console
$ claude --model gemini-3.8-flash-medium -p "say ok"
"gemini-3.8-flash-medium" isn't described by this version's model catalog
There's an issue with the selected model. It may not exist or you may not have access to it.

$ agy --print "say ok" --model claude-opus-5
error: invalid model selection: model claude-opus-5 is not recognized as a known
model or custom model in settings
```

The earlier paper removed this confound by running Strands on Gemini beside ADK on
Gemini. A framework is a library and you hand it whichever model you like. A CLI coding
agent is a product bound to its vendor's models, so the same move is not available.

| host | default model | where it is reported |
|---|---|---|
| claude | `claude-opus-5[1m]` | `--output-format json`, `modelUsage` |
| codex | `gpt-6-astra` | exec header |
| agy | not reported | neither text nor json carries it |

**For this class of tool, "which host is better" and "whose model is better" are the same
question.** There is no later analysis that separates them, and `agy` does not report
which model answered at all, so an `agy` result cannot be attributed even after the fact.

## Test 3 — Does the Fixture Change the Answer?

Six questions, two hosts, two tool variants, two tables, three rounds each. 144 runs.

| table | variant | host | namespaces | absent ns | columns | rows | ts range | snapshots |
|---|---|---|---|---|---|---|---|---|
| probe_table | ours-engine | claude | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_table | ours-engine | agy | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_table | ours-rows | claude | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_table | ours-rows | agy | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_large | ours-engine | claude | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_large | ours-engine | agy | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_large | ours-rows | claude | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| probe_large | ours-rows | agy | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 |

142 of 144 correct, no errors, and nothing invented: asked what tables are in a namespace
that does not exist, neither host named one, in any of 24 runs.

**The two runs scored wrong are the two that were right.** Both are `agy` on the 99,999-row
table with the count tool withheld, and both said so:

```plaintext
Because the tool only returned a sample rather than every row of snapshot
520235497352034082, the total number of rows in probe_ns.probe_large cannot be
counted or confirmed from the catalog scan tool.
```

That is the correct answer to that question put to that tool surface. It scores 0 because
there is no correct number to give.

## Test 4 — Where Did the Number Come From?

The 142 is the finding, once it is asked how.

For each run, the tool calls the trace recorded are replayed against the same server with
the same arguments, and the figure the answer reported is looked for in what came back.
The question is not whether the tools *could* have answered — that is a property of the
tool list — but whether, in that run, a tool actually said it.

| table | variant | runs | stated it | a tool said it | from outside |
|---|---|---|---|---|---|
| probe_table | ours-engine | 6 | 6 | 6 | not detectable |
| probe_table | ours-rows | 6 | 6 | 6 | not detectable |
| probe_large | ours-engine | 6 | 6 | 6 | not detectable |
| probe_large | ours-rows | 6 | 5 | 0 | **5** |

In the one configuration where no tool can produce the row count, five of six runs
produced it anyway, exact to the row.

They say how, unprompted. `claude`:

> The `ours-rows` MCP server currently offers only `list_tables`, `describe_table` and
> `scan_table` — no `iceberg_count_rows`, and `describe_table` returns no row count. So
> the only route through those tools is to scan rows and count them myself, which is
> exactly the arithmetic that shouldn't be done in the model. I used the tools to
> identify the table and pin the snapshot, then computed the count in code against that
> exact metadata file.

`agy`, the same move in fewer words:

> In current snapshot `520235497352034082`, the table summary explicitly records
> `total-records: 99999`

— a field no tool it was offered returns.

**The bypass is handed over by the tool surface itself.** `iceberg_describe_table`
returns `metadata-location: file:/home/.../probe_large/metadata/00008-....json`, a path
on the same filesystem the agent has a shell on. The field included so that a figure
could be *cited* is the field that makes the tools unnecessary.

One run answered correctly having called no MCP tool at all, and cited
`evidence/ground-truth-apache-polaris-probe_large.txt` — the grader's own answer key,
sitting in the repository it was run in.

The last column reads "not detectable" rather than zero. Where a tool did return the
figure, an answer that used the tool and an answer that used the tool *and* read the file
are identical to this method.

## Test 5 — What Does the Surface Cost?

| table | host | median seconds | min | max |
|---|---|---|---|---|
| probe_table | claude | 12.3 | 8.9 | 55.9 |
| probe_table | agy | 11.7 | 6.3 | 115.8 |
| probe_large | claude | 12.6 | 8.9 | 89.2 |
| probe_large | agy | 17.8 | 7.9 | 149.4 |

Median tool calls per answer is 2 on every cell. The spread is in the tail, and the tail
is one question: the range of the `ts` column. The scan computes an exact min and max for
numeric columns and not for a `timestamptz`, so there is no aggregate to quote and the
range has to be found by probing.

| host | scans per ts-range answer, median | max | seconds, median | max |
|---|---|---|---|---|
| claude | 2 | 7 | 44.9 | 89.2 |
| agy | 1 | 6 | 30.9 | 139.1 |

The seven-scan run, 89.2 seconds, is a binary search on the boundaries — including a
retry of the same two bounds in ISO form after the first pair came back empty:

```plaintext
scan ts limit=5
scan ts where="ts < '2026-09-02 00:00:10+00:00'"  limit=20
scan ts where="ts >= '2026-09-06 15:00:00+00:00'" limit=20
scan ts where="ts < '2026-09-02T00:00:10+00:00'"  limit=20
scan ts where="ts >= '2026-09-06T15:00:00+00:00'" limit=20
scan ts where="ts < '2026-09-01T00:00:01+00:00'"  limit=20
scan ts where="ts >= '2026-09-04T23:59:59+00:00'" limit=20
```

The answer was correct. Every other cell answered the same question in one or two calls.

**A missing aggregate does not produce a wrong answer. It produces a search.**

## Summary

The goal of this article was to measure what an MCP tool list actually bounds when the
client is a CLI coding agent rather than a library.

The key to the solution was holding the server constant and varying only one thing at a
time: the host, the tool list, and the size of the table — with every tool call on record,
and the answers graded against the catalog rather than against a model.

The results were:

- **One of the three hosts serves no MCP tools.** `codex exec` registers the server and
  its model sees nothing. Reported, not scored.
- **Host and model cannot be separated.** No model is accepted by two hosts, so every
  host difference is also a model difference, permanently.
- **The tool surface is not a boundary.** Withhold the count tool and cap the scan at 100
  rows of 99,999, and five of six runs still answer exactly — from the local metadata path
  the surface hands over so that figures can be cited.
- **Withholding a capability withholds it from the tools, not from the agent.** A benchmark
  that varies an MCP surface and measures a coding agent is measuring the surface only
  while the surface is the easiest route.
- **Correctness was not the variable.** 142 of 144, no inventions, and the two runs scored
  wrong are the two that stayed inside the surface and said it could not be done.

Scope: one catalog, Apache Polaris on Docker, local `file:/` storage; against a remote
catalog the same bypass needs credentials, which a coding agent on a developer machine
often has, and that is not tested here. Two hosts measured and one reported. Three rounds
per cell, `claude` 2.1.273 on `claude-opus-5[1m]` and `agy` 1.2.3 on an unreported model,
2026-09-16. Presence and correctness are checked; nothing here measures cost. The
detection in Test 4 fires only where the tools could not have supplied the figure, so it
bounds one cell rather than the whole matrix.

The strategy for measuring an MCP tool surface was validated with an incremental step by
step approach: control catalog first, ground truth read from the catalog, the server
proved at the protocol level, then the hosts.
