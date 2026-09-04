# Lakehouse and Apache Iceberg, measured

Measured write-ups of Apache Iceberg lakehouse behaviour across cloud vendors,
with the harness that produced each result.

The rule for everything here: **published numbers come from stored evidence, and
the evidence is re-derivable without re-running against a vendor.** Where a
result depends on how a fixture was built, the fixture's shape is measured from
the wire and published alongside it.

## Papers

| # | paper | channel | status |
|---|---|---|---|
| 1 | [Seven Iceberg REST Catalogs: What They Declare, and What They Serve](papers/iceberg-rest-catalog-conformance/devto-iceberg-rest-catalog-conformance.md) | dev.to `gde`, Builder Center, Medium | published |
| 2 | [AWS Has Two Iceberg REST Catalogs: What Each One Actually Serves](papers/aws-two-iceberg-rest-catalogs/devto-aws-two-iceberg-rest-catalogs.md) | dev.to `aws-builders`, Builder Center, Medium | published |
| 3 | [One Iceberg Tool, Three Agent Frameworks: What Ports, and What Doesn't](papers/iceberg-agent-three-clouds/devto-iceberg-agent-three-clouds.md) | dev.to `gde` | measured and written, not yet published |
| 4 | One Iceberg table, four MCP servers, three CLI hosts ([`iceberg-mcp-hosts/`](iceberg-mcp-hosts/README.md)) | — | scaffolding, nothing run |
| 5 | What a Rust client can reach, across the same seven catalogs ([`iceberg-rust-client/`](iceberg-rust-client/README.md)) | — | control column green, no vendor run yet |

Published URLs for each paper are recorded in that paper's `links.txt`.

Each paper directory holds the article, its cover, and an `evidence/` directory
carrying the artifacts every figure in it traces back to.

## Code

### `iceberg-conformance/`

One request suite pointed at seven Iceberg REST catalog implementations: Apache
Polaris, Google BigLake, AWS Glue, AWS S3 Tables, Databricks Unity, Snowflake
Horizon and Microsoft OneLake.

33 probes covering 25 of the specification's 35 operations. Three tiers of
evidence:

- **endpoint tier** — does the operation exist, and what status comes back
- **field tier** — 30 spec field paths checked against each `loadTable` response
- **declaration tier** — what a catalog names in the `endpoints` array of its own
  `/v1/config`, cross-checked against what it actually serves

See [`iceberg-conformance/README.md`](iceberg-conformance/README.md) for design
rules, per-catalog setup, coverage against the spec, the privilege audit and the
limitations.

### `iceberg-agent/`

Three vendor-native agents — Google ADK, AWS Strands and Microsoft Agent
Framework — each reading Iceberg through its own cloud's REST catalog, sharing
one read-only tool implementation. Built on the finding from paper 1 that the
read surface is the only one all seven catalogs agree on.

See [`iceberg-agent/README.md`](iceberg-agent/README.md).

## Reproducing

[`SETUP.md`](SETUP.md) is the bring-up for a new machine: what the clone does
not carry, what has to be installed, and the account state a copied credential
cannot restore.

Seven catalogs means seven accounts. Start with the control, which needs only
Docker:

```console
$ cd iceberg-conformance
$ pip install -r requirements.txt
$ ./polaris-up.sh
$ cp catalogs.example.yaml catalogs.yaml     # then fill in
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 run.py --only apache-polaris --allow-writes
```

Getting a clean control column working end to end validates the harness before
any credentialed vendor is involved. Every `base_url` in `catalogs.example.yaml`
is annotated with what that vendor requires beyond the URL — an enabled API, a
particular token scope, a licence, or a privilege that has to be granted first.

Three of the seven catalogs in paper 1 were measured on trial accounts that will
have expired; paper 1 opens with what each catalog costs and requires.

## What is not in this repository

`catalogs.yaml`, `.secrets/` and `evidence/` are ignored. Evidence files contain
account identifiers, bucket names and workspace GUIDs from the accounts they were
gathered against, so the stored runs are not published as-is. The harness
regenerates them.

## Licence

Apache-2.0.
