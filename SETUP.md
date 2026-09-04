# Setting this up on another machine

The clone carries all of the code, `catalogs.example.yaml`, `polaris-up.sh` and
the pinned `Cargo.lock`. It deliberately carries no credentials, no live
configuration and no evidence. This page is the gap between the two.

Nothing here is about any of it being difficult. Most of the work is not on the
machine at all -- it is the cloud-side state the fixtures live in, and that is
the part a copied key cannot restore.

## What is not in the clone?

Four files, all gitignored on purpose.

| file | what it is | without it |
|---|---|---|
| `iceberg-conformance/catalogs.yaml` | base URLs, warehouses, namespace and table names, and the auth block for all seven catalogs | nothing runs; `catalogs.example.yaml` is the template and annotates what each vendor needs beyond a URL |
| `iceberg-conformance/.secrets/sf_key.pem` | Snowflake RSA private key, referenced as `private_key_file` | Horizon cannot mint a JWT |
| `iceberg-conformance/.secrets/databricks_token` | the value behind `DATABRICKS_TOKEN` | Unity refuses |
| `.known-identifiers` | literal real values for `check-no-identifiers.sh`, one per line | **the check exits 1 and refuses to run**, so a fresh clone cannot pass its own pre-push gate |

The last one is the one that gets forgotten. It is gitignored because a tracked
script holding the values it greps for is how the email got committed in the
first place.

`evidence/`, `out/` and `.warehouse/` are ignored too and do not need copying.
They regenerate.

## What has to be installed?

| | for | note |
|---|---|---|
| Docker | the Polaris control | the only prerequisite for a green control column |
| Python 3 | everything | `pip install -r iceberg-conformance/requirements.txt` -- requests, PyYAML, botocore |
| Rust | paper 5 | built and run on 1.98.0; `Cargo.lock` is committed, so the dependency set is pinned |
| `gcloud` | BigLake | both `auth login` and `auth application-default login`: the token reads the catalog, ADC writes the data files |
| `az` | OneLake | `az login` on a work or school account |
| AWS credentials | Glue, S3 Tables | SigV4, signed by botocore |
| `claude`, `codex`, `agy` | paper 4 | on PATH; `agy` also answers to `gemini`, which is a wrapper around it |

## Which environment variables?

```console
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ export DATABRICKS_TOKEN="$(cat iceberg-conformance/.secrets/databricks_token)"
```

The agent legs additionally want `GOOGLE_GENAI_USE_VERTEXAI` and a project for
ADK, Bedrock model access for Strands, and `FOUNDRY_PROJECT_ENDPOINT` for Agent
Framework. `iceberg-agent/README.md` has the per-leg detail.

## Start with the control

Docker is the only thing this needs, and it validates the harness before a
credential is involved.

```console
$ cd iceberg-conformance
$ pip install -r requirements.txt
$ ./polaris-up.sh                      # brings up Polaris and seeds the fixture
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 run.py --only apache-polaris --allow-writes
```

`polaris-up.sh` bind-mounts a warehouse directory, mounts `/etc/passwd` so
Hadoop can resolve your uid, and sets four feature flags: two to permit FILE
storage, a third because permitting it escalates the readiness check to fatal,
and a fourth for purge-on-drop, which is off by default and whose absence would
put artificial red cells in the control column. The
comments at the top of it say why each one is there; every one of them cost a
failed attempt.

A red cell in the control column is this harness's bug, not a finding. That is
what the control is for.

## Then the Rust client

```console
$ cd iceberg-rust-client
$ cargo build
$ python3 run_rust.py                  # control only, the default
$ python3 make_surface.py              # rebuild the operation surface, no network
```

`run_rust.py` reads `catalogs.yaml` and mints tokens through the conformance
harness rather than reimplementing either, so it needs the same files the sweep
does.

## What a bucket cannot restore

Six of the seven catalogs are account state, not files. Each needs its
`probe_ns.probe_table` fixture, seeded with:

```console
$ python3 seed_table.py --catalog NAME
```

and seeding only works once that vendor's prerequisite is already true. The
per-catalog table in `CLAUDE.md` and the annotations in `catalogs.example.yaml`
are the checklist. The short version: BigLake wants the Lakehouse API enabled
and an `x-goog-user-project` header; Unity wants `EXTERNAL USE SCHEMA` granted
on the catalog and external data access switched on for the metastore; Horizon
wants a default external volume on the database; OneLake wants a Fabric licence
on a work or school account; Glue wants an explicit `location` on create; S3
Tables rejects uppercase namespaces and mandates purge on drop.

Three of the seven were measured on trial accounts. Those will have expired, so
expect to re-provision rather than re-point. A catalog still holding template
configuration must carry `enabled: false` -- without it, it answers with real
HTTP errors that look like findings but only describe a wrong warehouse.

## Before the first push

```console
$ ./check-no-identifiers.sh
clean
```

It greps everything about to be committed -- tracked, staged and
untracked-but-not-ignored -- for the literal values in `.known-identifiers`. Add
a line whenever a new real value enters the work, which includes anything a
second machine introduces: a different project, bucket, account identifier or
workspace. A value with no line is a value the check cannot see.
