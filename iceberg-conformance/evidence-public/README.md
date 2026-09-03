# Anonymized evidence

Produced by `anonymize_evidence.py` from the raw run output. Every
identifier tied to the accounts these runs were gathered against has
been replaced with a stable pseudonym: AWS account numbers, bucket
names, the Databricks workspace host, the Snowflake account locator,
and all GUIDs.

The mapping is consistent across every file, so cross-references still
hold -- the `table-uuid` returned by `create_table` is the same value
the later `assert-table-uuid` requirement carries.

Nothing else is rewritten. Status codes, verdicts, error message text,
field states, declared endpoint lists, timings and the harness
fingerprint are the evidence and are reproduced as recorded.

Public API hostnames are kept, because they identify the vendor rather
than the account.
