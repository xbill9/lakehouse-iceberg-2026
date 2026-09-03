# Iceberg REST Catalog conformance matrix

| Catalog | Endpoint | Auth | Prefix | Run at |
|---|---|---|---|---|
| apache-polaris | `http://localhost:8181/api/catalog` | oauth2 | `quickstart_catalog` | 2026-09-03T21:31:44Z |
| aws-glue | `https://glue.us-east-1.amazonaws.com/iceberg` | sigv4 | `catalogs/106059658660` | 2026-09-03T21:32:06Z |
| aws-s3tables | `https://s3tables.us-east-1.amazonaws.com/iceberg` | sigv4 | `arn%3Aaws%3As3tables%3Aus-east-1%3A106059658660%3Abucket%2Ficeberg-probe` | 2026-09-03T21:32:09Z |
| databricks-unity | `https://dbc-731fd292-4c2d.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest` | bearer_env | `catalogs/workspace` | 2026-09-03T21:32:58Z |
| google-lakehouse | `https://biglake.googleapis.com/iceberg/v1/restcatalog` | gcloud | `projects/289270257791/catalogs/aisprint-491218-iceberg-probe` | 2026-09-03T21:31:59Z |
| microsoft-onelake | `https://onelake.table.fabric.microsoft.com/iceberg` | azure_cli | `daeb5aeb-8d04-4c52-9281-53e6efee093f/739f7d11-d9b7-46a5-92eb-c1b6f121adb3` | 2026-09-03T21:32:02Z |
| snowflake-horizon | `https://yxhtdkw-br89127.snowflakecomputing.com/polaris/api/catalog` | snowflake_keypair | `PROBE_DB` | 2026-09-03T21:32:34Z |

## Endpoint tier

What each catalog does with an identical request. `501` is an honest not-implemented; `404` usually means the route was never registered.


| Probe                         | Category    | apache-polaris | aws-glue | aws-s3tables | databricks-unity | google-lakehouse | microsoft-onelake | snowflake-horizon |
|-------------------------------|-------------|----------------|----------|--------------|------------------|------------------|-------------------|-------------------|
| config                        | config      | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| list_namespaces               | namespace   | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| list_namespaces_paged         | namespace   | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| list_namespaces_parent        | namespace   | yes            | 400      | 400          | yes              | yes              | yes               | yes               |
| load_namespace                | namespace   | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| head_namespace                | namespace   | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| list_tables                   | table       | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| load_table                    | table       | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| load_table_snapshots_all      | table       | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| head_table                    | table       | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| load_credentials              | credentials | yes            | 404      | 404          | yes              | 400              | yes               | yes               |
| list_views                    | view        | yes            | HTTP_406 | 404          | 404              | 404              | 404               | auth              |
| plan_table_scan               | planning    | 404            | 200!     | 404          | 400              | 404              | 405               | 404               |
| report_metrics                | telemetry   | yes            | 200!     | 400          | yes              | yes              | 405               | yes               |
| create_namespace              | namespace   | yes            | yes      | yes          | yes              | yes              | 404               | yes               |
| update_namespace_props        | namespace   | yes            | yes      | 404          | 400              | yes              | 405               | auth              |
| create_table                  | table       | yes            | yes      | yes          | yes              | yes              | 404               | yes               |
| commit_table                  | commit      | yes            | yes      | yes          | yes              | yes              | 404               | yes               |
| commit_remove_properties      | commit      | yes            | yes      | yes          | yes              | yes              | 404               | 5xx               |
| commit_add_schema             | commit      | yes            | yes      | yes          | yes              | yes              | 404               | yes               |
| commit_set_current_schema     | commit      | yes            | yes      | yes          | yes              | yes              | 404               | 409               |
| commit_upgrade_format_version | commit      | yes            | yes      | yes          | yes              | yes              | 404               | 400               |
| commit_transaction            | commit      | yes            | 200!     | 404          | 404              | 404              | 405               | auth              |
| rename_table                  | table       | yes            | HTTP_406 | yes          | yes              | 404              | 404               | yes               |
| drop_table_purge              | table       | yes            | 400      | yes          | yes              | yes              | n/t               | yes               |
| drop_table                    | cleanup     | 404            | yes      | 400          | 404              | 404              | n/t               | 404               |
| create_view                   | view        | yes            | HTTP_406 | 404          | 404              | 404              | 404               | auth              |
| load_view                     | view        | yes            | HTTP_406 | 404          | n/t              | n/t              | 404               | n/t               |
| head_view                     | view        | yes            | n/t      | n/t          | n/t              | n/t              | n/t               | n/t               |
| replace_view                  | view        | yes            | HTTP_406 | 404          | 404              | n/t              | 404               | n/t               |
| rename_view                   | view        | yes            | HTTP_406 | 404          | 404              | n/t              | 405               | n/t               |
| drop_view                     | cleanup     | yes            | HTTP_406 | 404          | 404              | n/t              | 404               | n/t               |
| drop_namespace                | cleanup     | yes            | yes      | yes          | yes              | yes              | n/t               | yes               |

## Fixture shapes (measured, not assumed)

Not every catalog accepts the same seed, so the tables are not identical. Rows in the field tier marked † depend on the fixture rather than the implementation and must not be read as capability.

| Catalog           | schemas | part-fields | sort-fields | snapshots | refs             | delete-snap | delete-files |
|-------------------|---------|-------------|-------------|-----------|------------------|-------------|--------------|
| apache-polaris    | 2       | 1           | 1           | 4         | control_tag,main | yes         | 0            |
| aws-glue          | 2       | 1           | 1           | 4         | control_tag,main | yes         | 0            |
| aws-s3tables      | 2       | 1           | 1           | 4         | control_tag,main | yes         | 0            |
| databricks-unity  | 2       | 0           | 0           | 4         | main             | yes         | 0            |
| google-lakehouse  | 2       | 1           | 1           | 4         | control_tag,main | yes         | 0            |
| microsoft-onelake | 2       | 0           | 0           | 1         | main             | no          | 0            |
| snowflake-horizon | 2       | 1           | 1           | 3         | main             | no          | 0            |

## Field tier — what loadTable actually returns

Every catalog returns 200 for loadTable. They disagree about what is inside it, and that is invisible without enumerating the spec field by field.


| Field                                             | apache-polaris | aws-glue | aws-s3tables | databricks-unity | google-lakehouse | microsoft-onelake | snowflake-horizon |
|---------------------------------------------------|----------------|----------|--------------|------------------|------------------|-------------------|-------------------|
| `metadata-location`                               | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `config`                                          | no             | yes      | yes          | yes              | no               | no                | yes               |
| `storage-credentials`                             | no             | no       | no           | empty            | no               | no                | no                |
| `metadata.format-version`                         | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.table-uuid`                             | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.location`                               | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.last-updated-ms`                        | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.last-column-id`                         | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.schemas`                                | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.current-schema-id`                      | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.schemas[].fields[].id`                  | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.schemas[].fields[].required`            | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.partition-specs`                        | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.default-spec-id`                        | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.partition-specs[].fields[].transform` † | yes            | yes      | yes          | no               | yes              | no                | yes               |
| `metadata.last-partition-id`                      | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.sort-orders`                            | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.default-sort-order-id`                  | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.properties`                             | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.current-snapshot-id`                    | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshots` †                            | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshots[].summary` †                  | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshots[].manifest-list` †            | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshots[].schema-id` †                | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshots[].sequence-number` †          | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.snapshot-log` †                         | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.metadata-log`                           | yes            | empty    | yes          | yes              | yes              | yes               | yes               |
| `metadata.refs` †                                 | yes            | yes      | yes          | yes              | yes              | yes               | yes               |
| `metadata.statistics`                             | empty          | no       | empty        | empty            | no               | empty             | empty             |
| `metadata.partition-statistics`                   | empty          | no       | empty        | empty            | no               | empty             | empty             |

## Declared vs. observed

The spec lets a catalog advertise its supported endpoints in `/v1/config`. That claim is checkable. **DECLARED, FAILS** is an overclaim; *undeclared, works* is functionality a client trusting the declaration would never reach.

| Probe                  | Category    | apache-polaris    | aws-glue          | aws-s3tables      | databricks-unity  | google-lakehouse  | microsoft-onelake | snowflake-horizon |
|------------------------|-------------|-------------------|-------------------|-------------------|-------------------|-------------------|-------------------|-------------------|
| _declared count_       |             | 36                | 0                 | 0                 | 18                | 15                | 13                | 23                |
| config                 | config      | undeclared, works | undeclared, works | undeclared, works | undeclared, works | undeclared, works | undeclared, works | undeclared, works |
| list_namespaces        | namespace   | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| load_namespace         | namespace   | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| head_namespace         | namespace   | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| list_tables            | table       | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| load_table             | table       | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| head_table             | table       | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | declared, works   | declared, works   |
| load_credentials       | credentials | undeclared, works | undeclared, fails | undeclared, fails | declared, works   | DECLARED, FAILS   | declared, works   | undeclared, works |
| list_views             | view        | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | DECLARED, FAILS   |
| plan_table_scan        | planning    | undeclared, fails | undeclared, fails | undeclared, fails | DECLARED, FAILS   | undeclared, fails | undeclared, fails | undeclared, fails |
| report_metrics         | telemetry   | declared, works   | undeclared, fails | undeclared, fails | declared, works   | declared, works   | undeclared, fails | declared, works   |
| create_namespace       | namespace   | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | DECLARED, FAILS   | declared, works   |
| update_namespace_props | namespace   | declared, works   | undeclared, works | undeclared, fails | DECLARED, FAILS   | declared, works   | undeclared, fails | DECLARED, FAILS   |
| create_table           | table       | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | DECLARED, FAILS   | declared, works   |
| commit_table           | commit      | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | DECLARED, FAILS   | declared, works   |
| commit_transaction     | commit      | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | DECLARED, FAILS   |
| rename_table           | table       | declared, works   | undeclared, fails | undeclared, works | declared, works   | undeclared, fails | DECLARED, FAILS   | declared, works   |
| drop_table             | cleanup     | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | -                 | declared, works   |
| create_view            | view        | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | undeclared, fails | DECLARED, FAILS   |
| load_view              | view        | declared, works   | undeclared, fails | undeclared, fails | -                 | -                 | undeclared, fails | -                 |
| replace_view           | view        | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | -                 | undeclared, fails | -                 |
| rename_view            | view        | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | -                 | undeclared, fails | -                 |
| drop_view              | cleanup     | declared, works   | undeclared, fails | undeclared, fails | undeclared, fails | -                 | undeclared, fails | -                 |
| drop_namespace         | cleanup     | declared, works   | undeclared, works | undeclared, works | declared, works   | declared, works   | -                 | declared, works   |

## Coverage summary

Read and write surfaces are scored separately and deliberately not summed: a catalog that is read-only by design scores zero on writes, and folding that into one number makes a deliberate design read as a broken implementation. Counts are of probes, not endpoints: 33 probes cover 25 distinct endpoint signatures, because several probes differ only by query parameter (`?parent=`, `?snapshots=all`, `?purgeRequested=`). Probes that could not be tested are excluded from the denominator.

| Catalog           | Read probes OK | Write probes OK | not tested | loadTable fields present |
|-------------------|----------------|-----------------|------------|--------------------------|
| apache-polaris    | 15/16          | 16/17           | 0          | 26/30                    |
| aws-glue          | 9/15           | 10/17           | 1          | 26/30                    |
| aws-s3tables      | 9/15           | 10/17           | 1          | 27/30                    |
| databricks-unity  | 12/14          | 10/17           | 2          | 26/30                    |
| google-lakehouse  | 11/14          | 10/14           | 5          | 26/30                    |
| microsoft-onelake | 11/15          | 0/14            | 4          | 25/30                    |
| snowflake-horizon | 12/14          | 7/14            | 5          | 27/30                    |

Denominators differ by catalog because untestable probes are excluded rather than counted as failures: when a catalog refuses to create a namespace, the probes that needed one prove nothing about the endpoints they target. The `not tested` column is that count, so every denominator is reconstructable.
