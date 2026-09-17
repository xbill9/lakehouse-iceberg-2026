# Paper 5 — One Rust Client, Seven Iceberg Catalogs: What It Reaches, and What It Takes

Working title. Question-style, sentence case, matching papers 1 to 3.

Harness: [`iceberg-rust-client/`](../../iceberg-rust-client/README.md), shared
with paper 6. This file tracks paper 5 only.

## The question

If you build a lakehouse tool in Rust today, does it work against the catalog
you are paying for, and what does it take? Answerable about one client, and
answered by running it.

**Not** a comparison. `pyiceberg` appears in this paper only where a control is
needed to show that a refusal is the client's and not the catalog's. The
comparison is paper 6 and the two must not bleed.

## What is claimed, and what is not

- Presence, not correctness. A reached endpoint is not a correct endpoint.
- One client, `iceberg-catalog-rest` 0.10.1, pinned. Every number dies with the
  next release and the paper says so near the top.
- Not "Rust is missing features". The REST specification does not require SigV4;
  the two AWS catalogs layer it on top.
- Paper 1's standing caveats carry over: trial accounts, no versions from
  managed catalogs, one region at one moment, 25 of the spec's 35 operations.

## Prior art, and what it leaves

Searched 2026-09-17. Everything below is public; the paper cites it rather than
rediscovering it.

- [apache/iceberg-rust discussion #1239](https://github.com/apache/iceberg-rust/discussions/1239)
  — a user hitting 403 "Missing Authentication Token" from S3 Tables. SigV4
  "isn't supported for the REST Catalog implementation yet", tracked as #1236,
  open. **The SigV4 gap is not this paper's discovery and must not be written
  as one.**
- `iceberg-catalog-glue` 0.10.1 and `iceberg-catalog-s3tables` 0.10.1 exist in
  the same Apache project (`cargo info`, 2026-09-17). A Rust caller reaches both
  AWS catalogs — just not through the REST protocol.
- [smithclay/icepick](https://github.com/smithclay/icepick) — a Rust CLI and
  library for S3 Tables and Cloudflare R2. It does **not** document SigV4 for
  REST catalogs; it reaches S3 Tables through the AWS SDK and the default
  credential provider chain, native platforms only, because "S3 Tables requires
  the AWS SDK and is only available on native platforms ... It does not compile
  to WASM." So it is another instance of leaving the REST protocol to reach AWS,
  not an instance of anyone signing REST catalog requests in Rust. (The first
  draft of this plan said the opposite, on a search summary rather than the
  source.)
- [The 2026 Iceberg REST Catalog Compatibility Report](https://datalakehousehub.com/blog/iceberg-rest-catalog-compatibility-report-2026/)
  — published 2026-09-10: seven catalogs, 25 of the specification's 35
  operations, declared-versus-served, stored evidence. Close to paper 1's scope,
  independently. Client libraries are **out of scope** there; it recommends a
  separate "client-compatibility job" running "the same suite driven through the
  client libraries you actually deploy", which is exactly what papers 5 and 6
  are. Worth citing for that reason.
- [apache/iceberg#18126](https://github.com/apache/iceberg/issues/18126) — a
  client-library tracking issue for catalog labels only. No operations matrix,
  no auth, no performance.

**What none of them do:** point one Rust client at seven managed catalogs and
report what happened. That is this paper, and its value is reporting rather than
discovery. It cannot open on SigV4.

## Findings so far

Source-read and control-catalog only. Nothing below has touched a vendor.

1. **13 of 25 endpoints expressible.** Absent 11, unsupported 1
   (`update_namespace` compiles and returns `FeatureUnsupported`,
   "Updating namespace not supported yet!", catalog.rs:659), degraded 2
   (`?snapshots=all` and `pageSize` cannot be sent). Absences confirmed by grep
   as well as by reading.
2. **Five of seven catalogs reachable through this one client.** Not five of
   seven in Rust — the correct sentence is about protocol uniformity: the REST
   spec promises one protocol and one client for every vendor, and in Rust that
   promise does not hold for AWS, where a caller writes against three catalog
   clients instead of one. In Python it holds.
3. **Storage is a separate dependency, and was a harness bug first.** `iceberg`
   0.10.1 ships `local-fs` and `memory` factories only; the cloud backends are
   in `iceberg-storage-opendal`, per that crate's own README line 70. Our
   `Cargo.toml` lacked it. Fixed; the control is green under `local-fs` and
   `opendal` both.

   The blast radius, counted rather than estimated. Table location schemes, read
   from paper 1's stored `loadTable` responses:

   | catalog | scheme | reachable by this client |
   |---|---|---|
   | apache-polaris | `file://` | yes, and the only one the two core factories cover |
   | google-lakehouse | `gs://` | yes |
   | databricks-unity | `s3://` | yes |
   | snowflake-horizon | `s3://` | yes |
   | microsoft-onelake | `abfss://` | yes |
   | aws-glue | `s3://` | no — auth, before storage |
   | aws-s3tables | `s3://` | no — auth, before storage |

   So six of seven are cloud-backed, and **four** of those are ones this client
   could otherwise reach; the other two are out on SigV4 first. Of the four,
   Unity and Horizon currently carry placeholder config (`enabled: false`), so
   BigLake and OneLake are the two that would have failed on a run today.
4. **Control catalog green:** 7 OK, 1 implicit, 11 not-issued, 14
   not-expressible, 0 failed. `NOT-ISSUED` and `NOT-EXPRESSIBLE` are counted
   apart; conflating them understated the crate by eleven rows, which was a bug
   in this harness.

## What is owed before this is publishable

1. **The five catalogs whose auth this client can express**, one at a time,
   `--storage opendal`. The questions only a run answers: does Horizon accept
   the crate's bare-`client_secret` grant; does a statically minted gcloud or
   Azure bearer survive a run, and what happens at expiry given the crate cannot
   refresh it; do vended credentials from `loadTable` reach the storage layer.
2. **The SigV4 demonstration** on Glue or S3 Tables — a signature computed for
   `GET /v1/config` lifted into `header.Authorization` and refused on the second
   request. Written as a consequence of a known limitation, with #1236 cited,
   never as news.
3. **The write surface**, eleven `NOT-ISSUED` rows today. Same `--allow-writes`
   discipline as paper 1, same check for `irc_probe_*` residue.

## Evidence this paper owns

`papers/rust-client-seven-catalogs/evidence/`, built by
`iceberg-rust-client/sync_paper_evidence.py` from a manifest so the set stays
scoped and cannot drift:

    rust-client-operation-surface.txt     what the crate can attempt
    rust-client-auth-surface.txt          the auth surface, read from source
    rust-run-<catalog>.json               one run per catalog
    declaration-gate-cost.txt             shared with paper 6, context only

**Read `check-facts.py` output by the file it names, not by the tick.** It
matches on digits and reports the first match, not the best one: `13 of 25`
traces to `declaration-gate-cost.txt`, which does not contain that string, while
`rust-client-operation-surface.txt` in the same set does. The claim is backed;
the attribution is not. Confirm with a literal grep before quoting a figure as
sourced.

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

Follows the dev.to skeleton: opening line and bare repo URL, "What is this
project trying to Do?", "Where do I start?", "At This Point You Should Have…",
`Step N —` sections with real commands and their real output, and the goal/key/
results close. Measurement sections keep the understated register: state what is
not being claimed early, foreground method before results, report null results
plainly, and quote error text verbatim.
