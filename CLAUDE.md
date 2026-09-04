# Working in this repository

Measured write-ups of Apache Iceberg lakehouse behaviour across cloud vendors,
plus the harness that produced each result. Public repo:
`xbill9/lakehouse-iceberg-2026`.

The whole value of this project is that its numbers are defensible. Vendor
comparisons attract hostile readers, and every claim here has to survive one.

---

## The rule that matters most

**Before reporting any failure as a vendor finding, prove it is not ours.**

Fourteen harness bugs were found this way and none reached publication. Several
would have been striking, quotable and completely false — "OneLake omits column
IDs" (it does not; the walker took `schemas[0]`, an empty placeholder), "Unity's
metrics endpoint 500s" (an incomplete ScanReport of ours), "Horizon overclaims
six endpoints" (four; two probes had no fixture to act on).

The checks, in order of how often they caught something:

1. **Does the control column fail too?** Apache Polaris is configured
   permissively on purpose. A red cell there is almost always our bug, not a
   spec gap. Two view probes and two commit probes were fixed this way.
2. **Is the payload spec-complete?** Most "vendor rejects X" turned out to be a
   missing required field. `set-current-schema: -1` means *the schema added in
   this same commit*; `timestamp-ms` must be an integer, not a quoted string.
3. **Did a prerequisite fail?** If `create_namespace` was refused, everything
   after it fails for reasons unrelated to the endpoint under test. That is what
   `depends_on` and the `INDETERMINATE` verdict exist for.
4. **Are our own credentials too narrow?** An over-tight IAM policy and writing
   through vended rather than local credentials both produced failures that
   looked like Snowflake defects.
5. **Is the fixture the same shape?** A catalog whose table is unpartitioned
   cannot report a partition transform. Fixture shapes are measured from the
   wire and published for this reason.

When a failure survives all five, say what it is precisely and quote the error
text verbatim.

---

## Harness invariants — do not regress these

Each of these was a bug once.

- **Prefixes go in raw.** `/v1/config` returns a routing prefix that is often
  several path segments (`projects/<n>/catalogs/<c>`) and sometimes a
  percent-encoded ARN. Never re-encode it and never collapse its slashes.
  Namespace and table names *are* encoded, and a dotted namespace uses the unit
  separator.
- **Sign exactly what is sent.** SigV4 signs the literal query string. Build the
  URL once and pass it whole; letting `requests` re-encode `params` separately
  breaks the signature.
- **`surface` is not `tier`.** `tier` says when a probe runs, `surface` says
  what the operation is. `loadView` and `viewExists` run in the write phase
  because they need a view to exist, but they are reads. Scoring by phase
  understates a read-only catalog's read surface.
- **Reconcile by endpoint signature, not by probe.** Several probes share one
  endpoint; judging each separately invents overclaims out of probe ordering.
- **A 404 is not always a missing route.** "Requested Api is not found" is
  evidence; "the given table does not exist" is not. `route_is_missing()` draws
  that line.
- **Field paths search every list element.** Catalogs put an empty placeholder
  at `schemas[0]`.
- **Never overwrite good evidence with a failed run.** A sweep where everything
  died at transport writes `evidence.failed.json` instead.
- **Redact before disk.** `loadTable` can vend live storage credentials.

---

## Never commit

`.secrets/`, `catalogs.yaml`, `evidence/`, `.warehouse/`, the sprint PDF,
`sprint-rows.*`, `gen_rows.py`, `PROJECT-IDEAS.md`. The last three carry a real
name, email and country.

Published evidence goes through `anonymize_evidence.py` into `evidence-public/`.
It fails loudly if an identifier survives. Run an **independent** grep for known
real values afterwards anyway — the residual scanner has missed a GCP project id
before, because it did not match any of the patterns it looked for.

**That warning was not enough, and the miss happened again.** On 2026-09-04 the
project id and project number were found in 8 tracked files, 33 hits of them
inside `evidence-public/`, after the anonymiser had reported clean: it had no
pattern for either, so its own scan could not see them. The independent grep is
now a script rather than an instruction:

```console
$ ./check-no-identifiers.sh          # run before every push
clean
```

It greps **everything about to be committed** -- tracked, staged, and
untracked-but-not-ignored -- for literal known-real values, so it does not
depend on guessing the shape of the next identifier. Add a line to it whenever
a new real value enters the work. `anonymize_evidence.py` now also maps and
scans GCP project ids and numbers.

Both of those properties were bugs first, found on 2026-09-04 by testing the
script instead of reading it. It searched tracked files only, so running it
before `git add` -- the natural order -- skipped every new file, which is where
a fresh identifier is most likely to be. And its two generic fallback patterns
were written with BRE braces and passed to `grep -E`, so neither had ever
matched anything. **When you change this script, plant a value and watch it
fail.** A check that cannot fail reads exactly like a check that passes.

---

## Writing the papers

Match the existing register, which is understated and declarative. Study the
published pieces on `dev.to/xbill` — *Cross Cloud A2A Agent Card Field
Comparison* and *Three Clouds, One Brief* are the closest models.

**Do:**

- Question-style headers, sentence case. Lowercase table headers.
- State exact versions and the measurement date near the top.
- `console` blocks with `$` prefixes; real commands that ran.
- Say what is *not* being claimed, early. "Nothing here is about X being broken."
- Foreground method before results — what was held constant, and why.
- Report null results plainly. "24 of 30 field rows are identical" is a finding.
- Lead with the measurement, not with an adjective.

**Do not:**

- Accuse vendors of bad faith. No "lying to you", no "dirty secret". A
  declaration that does not match behaviour is drift — a stale field or a bug —
  and calling it deception is a claim the evidence does not support. This has
  been corrected before; do not reintroduce it.
- Invent terminology. Use the spec's words. "Declared" means named in the
  `endpoints` array; "served" means returned 2xx.
- Overstate a mechanism. Glue's `200` carrying `UnknownOperationException` is
  the AWS protocol layer answering an unrouted operation, not a broken success
  on an implemented endpoint. Both matter to a client; only one is accurate.
- Publish a comparison score that sums read and write surfaces. It makes a
  deliberately read-only catalog read as broken.

---

## Running the harness

```console
$ cd iceberg-conformance
$ ./polaris-up.sh                              # control column, needs only Docker
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 run.py --only apache-polaris --allow-writes
$ python3 run.py --allow-writes                # everything configured
$ python3 run.py --report-only                 # rebuild the matrix, no network
```

Get the control green before touching a credentialed vendor.

`--allow-writes` creates and drops a scratch namespace on every selected
catalog. Check for `irc_probe_*` residue afterwards.

Catalogs still holding placeholder config must carry `enabled: false`. Without
it they answer with real HTTP errors that look like findings but only describe a
wrong warehouse, and the transport-level quarantine cannot catch that.

---

## Per-catalog gotchas

Each of these cost a failed attempt; the detail is in
`iceberg-conformance/README.md`.

| catalog | the thing that blocks you |
|---|---|
| Polaris | FILE storage needs two feature flags, which then escalate the readiness check to fatal, needing a third. Running as your uid breaks Hadoop's `UserGroupInformation` unless `/etc/passwd` is mounted — it surfaces as a 503 that reads like a storage error. |
| BigLake | `v1`, not `v1beta`. Requires the Lakehouse API enabled and an `x-goog-user-project` header. Seeding writes to GCS with ADC, not the gcloud token. |
| Glue | `createTable` requires an explicit `location`. |
| S3 Tables | Namespace names reject uppercase. `createTable` requires `stage-create`. PyArrow's writer is rejected; use `FsspecFileIO`. A plain drop is refused — purge is mandatory. |
| Unity | The Iceberg endpoint needs an `all-apis` token; the granular `unity-catalog` scope is rejected. External data access is off by default per metastore. `EXTERNAL USE SCHEMA` must be granted on the *catalog*. Vended credentials deny `s3:PutObject`, so seed natively. |
| Horizon | Warehouse is a **database** name. Scope is `session:role:<role>`, and the grant carries a JWT in `client_secret` with no `client_id`. Needs a default external volume on the database or `createTable` returns 403. `TIMESTAMP_LTZ(6)`, not `TIMESTAMP_TZ(9)`. |
| OneLake | Needs a Fabric licence on a **work or school** account — a personal MSA cannot hold one. The free 60-day trial capacity is sufficient; the paid F-SKU is not needed. |

---

## Standing caveats for any result

Three of the seven were measured on trial accounts, which is a genuine confound —
one Horizon refusal is worded *"not allowed for Horizon accounts"*. Managed
catalogs expose no version. Every run is one region at one moment. Coverage is
25 of the spec's 35 operations. Presence is checked, not correctness.

State these; do not let a paper imply otherwise.
