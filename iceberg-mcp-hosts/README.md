# One Iceberg table, four CLI hosts, three MCP servers

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

## Status

Scaffolding. Nothing has been run yet. Fixture and question set next.
