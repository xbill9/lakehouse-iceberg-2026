# One Iceberg table, four MCP servers, three CLI hosts

Supports **paper 4** of the series. The question is what a host can learn about
the *same* Apache Iceberg table depending on which MCP server it is given, and
whether the host itself changes the answer.

## What is not being claimed

Nothing here is about the community servers being deficient. They are small,
focused projects and one of them is doing something Google's server does not
(writing). The comparison is of **surfaces**, measured against one table.

This is also not "I built an Iceberg MCP server". Two already exist and are
under test here; the contribution is the measurement, not another server.

## What varies, and what does not

The rule is the one `iceberg-agent/` already runs on: share everything that is
not the variable under test.

| shared, one implementation | different, on purpose |
|---|---|
| the Iceberg table, already seeded for the conformance sweep | the MCP server |
| the question set, versioned | the CLI host |
| the grading, against ground truth read from the catalog | |

Two axes, so a difference can be attributed:

    axis A   host fixed, servers vary    -> isolates the server surface
    axis B   server fixed, hosts vary    -> isolates the host

## The servers

Surfaces verified from each project's own documentation on 2026-09-04 and
recorded in `evidence/server-surfaces.txt`. The headline is visible before a
single question is asked:

| server | tools | returns rows? |
|---|---|---|
| BigQuery MCP (Google, first-party) | 6, including `execute_sql` | yes, SQL over Iceberg/BigLake |
| Managed Spark MCP (Google, first-party) | cluster and job control | no, it is a compute control plane |
| morristai/iceberg-mcp (Rust) | `namespaces`, `tables`, `table_schema`, `table_properties` | **no, metadata only** |
| ahodroj/mcp-iceberg-service (Python) | LIST/DESCRIBE/SELECT/INSERT | yes, via PyIceberg |

So one axis of the result is settled by reading the tool lists: a question that
needs a row count cannot be answered through morristai/iceberg-mcp at all. That
is a finding about scope, not about quality, and the paper has to say so in
those words.

## The hosts

Claude Code, Codex and Antigravity. Each is configured with the same server set
and asked the same questions.

Three, not four. Google retired the standalone Gemini CLI on 2026-06-18 and
replaced it with Antigravity, so the `gemini` command on this machine is a
one-line wrapper around `agy` -- the same binary, wearing the old name. Counting
both would have put two identical rows in the matrix, and they would have agreed
perfectly, which reads as a result rather than as a duplicate.
`evidence/host-inventory.txt` has the sources and the qualifier.

## Knowing whether a tool was called at all

Grading reads the host's answer, and prose cannot tell a fetched number from an
invented one. Paper 3 only resolved its worst question -- where a count nobody
could source had come from -- because every tool call was on record.

`mcp_trace.py` is that instrument one layer down: the host talks to it, it talks
to the server, and it copies every JSON-RPC frame aside. Arguments are recorded
by name and size and results by size, because a result body can carry catalog
credentials; `--full` keeps the bodies for debugging and is never used for a
published run.

It is byte-transparent, which was verified rather than assumed: a server emitting
compact JSON comes back compact through the proxy, and the same comparison fires
on a deliberately respaced stream, so "identical" means something.

**Only the two local servers can be wrapped.** `bigquery` and `managed-spark` are
HTTP endpoints the host dials directly, so those cells have no trace at all.
Absent is not empty, so `traced` is recorded per row and a missing trace never
reads as "made no tool calls".

The check this buys is `answered_without_tools`: a substantive answer, no
refusal, and nothing called behind it.

## What a surface cannot say

`answers_rows` was read from each project's documentation before any run, and Q6
needs the same treatment. Retrieved from Google's own docs on 2026-09-16:
bigquery-mcp's `get_table_info` returns table metadata and carries a
`biglakeConfiguration` for Iceberg, but the documented output includes **no
snapshot id, metadata file location or table version**, and the documentation
names no `INFORMATION_SCHEMA` view or table option that exposes them either.

So "cite the exact table version you read" cannot be answered through that
server, and scoring it 0 would measure the vocabulary the server was given --
something already known before the run. `cites_version` records it, and Q6 is
graded as refusal-quality there, exactly as Q4/Q5 are on a server with no
row-returning tool.

Stated as absence in the retrieved documentation, not as impossibility. If a run
shows a host citing a real snapshot id through that server, `cited_despite_surface`
marks it and `evidence/server-surfaces.txt` is what it contradicts. For
morristai, `cites_version` is **None**: `table_properties` is a candidate and the
documentation does not settle it, so it is unresolved rather than assumed.

## Ground truth

Generated and current for both catalogs, read live on
2026-09-16. It is **not committed**: the Google one names a GCS bucket after the
project, so the raw files stay local and reach the repo only through an
anonymising publish step, which paper 4 does not have yet. That step is a
prerequisite for publishing anything here, not an afterthought.

The two catalogs disagree on every citation field, which is the whole reason the
grader was split:

| catalog | snapshot_id | metadata |
|---|---|---|
| apache-polaris | 4496289927168545616 | `file://...` |
| google-lakehouse | 6042367411917366632 | `gs://...` |

## The scorer refuses to run unless it can say no

`SCORER_VERSION` is recorded in the axis JSON, and ten planted answers run before
any cell. Half of them must **fail**: a check that cannot produce a negative is
indistinguishable from one that always passes, and paper 3 shipped a version that
silently regressed twelve correct answers because nothing like this existed.

v1 got **4 of the 10 wrong**, all of them false positives -- a host recorded as
correct when it was not:

| planted answer | v1 | v2 |
|---|---|---|
| `Read on 2026-09-11 from the catalog.` | counted as 11 rows | rejected |
| `The query took 11.5 seconds over the rows.` | counted as 11 rows | rejected |
| `The table has 11 columns.` | counted as 11 rows | rejected |
| `Columns: ids, ts, payloads, regions.` | all four columns named | rejected |

The patterns are paper 3's, not new ones: a value must sit next to its own noun
within a line rather than appear anywhere, with lookarounds refusing a longer
number and a decimal; URIs and long digit runs are blanked for pairing only, so
a snapshot id's digits neither break a span nor supply a false match, while the
citation checks still read the answer as written; and column names match as whole
identifiers, so *identifier* is not `id` and *payloads* is not `payload`.

## Declared is not served, here too

`iceberg-mcp` is built and installed: v0.1.0 at commit `8ffb3b45`, a 39.7 MB
release binary identifying as rmcp 0.8.3. Asking it directly produced the first
measured result in this paper, and it is paper 1's method applied to a tool list:

| | |
|---|---|
| declared, in the project README | `namespaces`, `tables`, `table_schema`, `table_properties` |
| served, by `tools/list` | `get_namespaces`, `get_tables`, `get_table_schema`, `get_table_properties` |

The four capabilities match; the names do not. Every served name carries a `get_`
prefix the documentation does not show, so anything keyed on the documented names
finds nothing and reports it as a tool that was never called.

All four servers are now reachable: `uvx` is present for ahodroj and the two
Google servers are remote HTTP.

**What still blocks a run is permission, not plumbing.** Invoking the CLI hosts
from an agent session is refused by the harness classifier as unsafe agent
creation, so the matrix has to be run by a person or under a Bash permission rule
for `claude`, `codex` and `agy`.

## Status

Scaffolding, and not yet run. A run started by accident during development was
stopped and its two captures discarded rather than kept -- a partial run is not
evidence.

Done: three axes, per-catalog grading with stale and missing refusals, the frame
trace with verified byte-transparency, arithmetic provenance, capability read
from documentation, scorer v2 with a self-test that must be able to fail, and
ground truth live for both catalogs.

Next: an anonymising publish step, then the fixture, then repeats.

**Ground truth is per catalog, and the grader refuses without it.** Two servers
read the local Polaris and two read Google, so they are different physical tables
holding the same seeded fixture, with different snapshot ids and metadata
locations. One shared ground-truth file would have scored every Google cell 0 on
the citation checks by construction -- a scoring artefact that reads exactly like
a finding about the server. `ground_truth.py` now writes one file per catalog,
each row records which catalog it was graded against, and the runner stops rather
than falling back to another catalog's answers.

It also stops on a **stale** file. The first `ground-truth.txt` here cited a
metadata location under `/home/xbill/data-sprint/`, a path from another machine
that no longer exists, so every citation check would have been compared against a
file that is not there. The check that catches it was verified against that real
file before being relied on. One run of a cell is one sample -- paper 3
learned that the hard way on a model whose decoding made twenty runs a single
answer repeated -- so the runner still needs `--repeat` and seeded shuffled
rounds before any number here is worth quoting.
