# Paper 6 — Two Iceberg Clients, One Protocol: Where the Time Actually Goes

Working title. The title is deliberately about *where*, not *how much*: the
ratio is the ordinary part and the decomposition is the paper.

Harness: [`iceberg-rust-client/`](../../iceberg-rust-client/README.md), shared
with paper 5. This file tracks paper 6 only.

## The question

Two Apache clients speak the same REST protocol to the same catalog. What does
each cost to use, and what is that cost actually made of?

## Why this is not a feature comparison

A surface table between `iceberg-catalog-rest` 0.10.1 and `pyiceberg` 0.12.0
says 13 of 25 endpoints against 21 of 25. That is a documentation exercise: two
libraries at different points in their lives, derivable from both repositories
in an afternoon, and true only of those two versions. It belongs in this paper
as context and never as the headline. **No summed score, and no ranking.**

What is not in either repository is what each one costs, and what the cost is
made of. That is measurable, it is actionable for a reader who uses pyiceberg,
and as of the search below nobody has published it.

## Prior art, and what it leaves

Searched 2026-09-17.

- [querygraph/catalog-bench](https://github.com/querygraph/catalog-bench) —
  commit-path latency across five catalogs, p50/p95/p99, six rounds with
  rotate-left ordering. Deliberately drives every catalog through one binary **to
  eliminate client-side variables**. The exact complement of this paper, and its
  round-rotation is the same discipline this harness interleaves with.
- [The 2026 Iceberg REST Catalog Compatibility Report](https://datalakehousehub.com/blog/iceberg-rest-catalog-compatibility-report-2026/)
  — catalog servers only; records elapsed milliseconds per probe but does not
  compare clients, and says client compatibility is out of scope.
- Rust-versus-Python cold start is a genre with published numbers, and the
  numbers matter more than the genre. [Cold Starts Are
  Dead](https://dev.to/aws/cold-starts-are-dead-5fod) measures Lambda at
  **88.3 ms p50 for Python 3.13 on arm64** (106.2 ms x86_64) against **14.1 ms
  for Rust** (17.0 ms x86_64), 512 MB, minimal hello-world handlers, and states
  plainly that this is the "platform floor" with **no framework dependencies**.
  Our 525.8 to 557.9 ms is five times that floor, and the decomposition says
  why: 337.9 to 366.3 ms of it is importing one library. So this paper is not
  restating the genre figure, it is measuring the thing the genre figure
  excludes. (An earlier draft of this plan said "200-400 ms for Python", taken
  from a search summary rather than the article, which says nothing of the
  kind.)

- Published Rust-versus-JVM Iceberg numbers are engine-level (DataFusion against
  Spark), not client-level.

**What none of them do:** time the same catalog operation through two client
libraries, or say where a Python Iceberg client's time goes. Both are this
paper.

## Findings so far

Control catalog, Polaris over loopback, release build, two runs.

1. **Steady state.** Cheap metadata calls 1.90x to 3.16x in Rust's favour;
   `load_table` and `head_table` 1.14x to 1.27x. Both ranges are the span across
   the stored runs, printed by `bench_report.py` into `bench-comparison.txt`
   rather than rounded by hand here. The narrow pair is where the server does
   the most work, which is the check that the harness measures the clients and
   not itself.
2. **The ratios are an upper bound.** Loopback means the client's own cost is
   the whole cost. Twenty milliseconds of vendor latency on both sides moves
   every ratio toward 1. This has to be said in the same breath as the table.
3. **The decomposition, which is the paper.** Same request, increasing depth,
   layers interleaved. Across five valid runs (`--iters` 60 to 120):

   - **transport is 90% to 94% of the call**, every run
   - `reqwest` p50 **323.2 to 479.7 us** against `requests` p50 **864.3 to
     1286.4 us** — the same GET, same bearer, same server, so the difference is
     the HTTP client
   - the transport gap is **541.2 to 914.2 us**; everything pyiceberg does above
     transport is **57.3 to 134.7 us**
   - so the HTTP stack is **85% to 90% of the per-call difference**. *This is
     arithmetic over the two figures above, gap / (gap + library), and is
     labelled as arithmetic rather than measured.*

   **The split inside that library layer is not separable at this sample size,
   and the first version of this plan claimed it anyway.** Across four runs the
   pydantic delta read -0.5, +17.7, +16.9 and -22.8 us, and the plan quoted the
   two that agreed. `bench_breakdown.py` now prints twice the standard error of
   the mean beside every delta and marks anything below it `NO -- noise`; at
   n=120 only the `json.loads` delta cleared the bound, and the client-method
   delta did not. What the harness supports is the size of the whole library
   layer, not its internal shares. Separating them needs more iterations or a
   quieter machine, and until then the paper says so.

   `trust_env=False` is in the same position: -32.9, -55.0 and -89.9 us across
   the three runs that measured it, negative every time but clearing the bound
   only once. Direction consistent, magnitude not established.

4. **Cold start decomposes too**, and unlike the per-layer deltas it is far
   above the noise. Across five valid runs: bare interpreter **9.1 to 11.2 ms**,
   importing `pyiceberg.catalog.rest` a further **337.9 to 366.3 ms**, catalog
   construction — the config fetch and the OAuth2 grant, the only network in it
   — **7.2 to 12.4 ms**. The half second is importing Python. End to end the
   benchmark measured cold start at **18.6 and 26.0 ms** for Rust against
   **525.8 and 557.9 ms** for pyiceberg, p50 of five spawns each, two runs.
5. **Two consequences.** Not a language verdict — the dominant term is a library
   choice a caller could in principle replace, and the Iceberg-specific code is
   small on both sides. And it locates where the difference survives: per-call
   overhead disappears under real network latency, import cost does not.
6. **Run-to-run spread is a third.** Two runs a minute apart moved
   `list_namespaces` p50 by 32.9%, the widest of the six operations. Every run is stored as its own file and the report prints the range;
   quoting a single p50 would be quoting the machine's mood.

## Method rules, each of which was a way to get a wrong number

- Release build; the driver refuses to write evidence from a debug binary.
- Both clients spawned as fresh processes, so neither gets a warm interpreter
  the other pays for.
- Startup outside every sample, and measured separately as cold start.
- Rounds interleaved; layers in the decomposition interleaved too. **The first
  decomposition ran the layers in blocks and reported transport as slower than
  the call containing it** — kept as `bench-breakdown-*.invalid.txt`, and worth
  a sentence in the paper as the reason the interleaving is there.
- Every sample stored; percentiles computed in code, never by hand.

## What is owed before this is publishable

1. **The same benchmark against vendors**, where the network is real and the
   ratios compress. Without it this measures one local server.
2. **Repeats across days**, not minutes, given the spread already seen.
3. **The decomposition repeated against one vendor**, to show how much of the
   541–914 us transport gap survives when a real round trip dominates.
4. Optional and cheap: whether `trust_env=False` moves the end-to-end benchmark,
   not just the transport layer.

## Evidence this paper owns

`papers/two-iceberg-clients-cost/evidence/`, built by
`iceberg-rust-client/sync_paper_evidence.py` from a manifest so the set is
scoped and cannot drift:

    bench-comparison.txt                  every figure quoted, rendered
    bench-breakdown-<catalog>-<ts>.txt    the decomposition, one per run
    client-comparison.txt                 surface context, not the headline
    pyiceberg-client-operation-surface.txt
    rust-client-operation-surface.txt
    pyiceberg-run-<catalog>.json
    declaration-gate-cost.txt

**Deliberately not in that directory:** `bench-<catalog>-<timestamp>.json`, the
per-run sample arrays. They stay in `iceberg-rust-client/evidence/`, committed,
so every figure is re-derivable. MEASURED 2026-09-17: with them in the evidence
set the publishing kit's `check-facts.py` "traced" every claim in this plan,
including `13 of 25` and `21 of 25`, which appear in no benchmark file — 720
nanosecond samples contain every short digit sequence, and the check matches on
digits. A green run against them means nothing.

## Publishing route — both orgs, decided 2026-09-17

Five destinations, and **two dev.to articles, not one.** An article carries a
single `organization_id`, so a piece that runs in both communities is two posts
with byte-identical bodies and different routing — which is what paper 3 did
(`dev.to/gde/...-a5g` and `dev.to/aws-builders/...-2iib`, same title, different
slug). Do not write a second, differently-angled version; that doubles the
maintenance and guarantees drift.

| destination | route | state it lands in |
|---|---|---|
| dev.to `gde` | `publish-devto.py --create <article>.md --org-slug gde` | `published: false` |
| dev.to `aws-builders` | same file, `--org-slug aws-builders` | `published: false` |
| AWS Builder Center | browser, one JS-bridge paste into the editor | autosaved draft |
| Medium | browser, paste `<slug>-hosted.html` | editor draft |
| LinkedIn | `make-linkedin.py --api`, composer by hand | composer draft |

Order and traps, all of which have bitten before:

1. `preflight.py <article>.md --live` green **first**. `--create` runs
   `check-article.py` itself and refuses on any FAIL.
2. **Create under the final title.** The slug is fixed at creation and a rename
   does not move it.
3. **Five minutes between the two creates.** The same title twice inside that
   window is refused with 422 `Title has already been used in the last five
   minutes`.
4. `published` is not a settable field — `publish-devto.py --publish <id>` flips
   the front matter in the payload and verifies from the listing, because a
   `PUT` of `{"published": true}` returns 200 and changes nothing.
5. **`--update` unpublishes a live article**, because the source's
   `published: false` travels inside `body_markdown`. After updating anything
   already published, re-run `--publish <id>` and confirm with `--list`.
6. `links.txt` keys, matching paper 3 so `make-linkedin.py` and the announcement
   templates find them: `devto-gde`, `devto-aws`, `builder`, `medium`, `repo`,
   `linkedin`. `PENDING` fails the run on purpose.
7. **Label the two dev.to links differently** in the LinkedIn post; "dev.to"
   twice reads as a duplicate.
8. Announcements, optional and after the fact: the AWS Slack channel gets the
   **aws-builders** link, the GDE Google Chat space gets the **gde** link. Both
   generators fail on the swap.
9. `./check-no-identifiers.sh` before any push, per the project CLAUDE.md.

Still to decide, per paper: the four dev.to tags (a fifth is silently dropped)
and the Builder Center tags, which come from a fixed searchable vocabulary —
**search the picker before assuming a tag exists**; `gpu`, `benchmark` and a
usable `inference` all turned out not to.

## Structure

Same dev.to skeleton as the other papers. Specific to this one: the method
section comes before any number, the upper-bound caveat sits with the first
table rather than at the end, and the closing summary leads with the
decomposition rather than the ratio.
