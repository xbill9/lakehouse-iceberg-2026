#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seeds an identical, deliberately rich control table into any configured catalog.

The conformance matrix only means something if every catalog is asked about the
same shape of table. A vendor whose table has no snapshots would show `snapshots`
absent for reasons that have nothing to do with its REST implementation, so this
builds the same thing everywhere: an explicit partition spec and sort order,
three appends (snapshots, snapshot-log, sequence numbers), a schema evolution
(schema history, a longer metadata-log) and a tag (refs beyond main).

Reads the same catalogs.yaml the harness uses, so the seed and the probe can
never drift apart on endpoint, warehouse or auth.
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

import pyarrow as pa
import yaml
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table.sorting import NullOrder, SortDirection, SortField, SortOrder
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import LongType, NestedField, StringType, TimestamptzType


def build_catalog(cfg):
    """Translate one catalogs.yaml entry into a pyiceberg RestCatalog."""
    props = {
        "uri": cfg["base_url"],
        "warehouse": cfg.get("warehouse", ""),
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    for k, v in (cfg.get("headers") or {}).items():
        props["header.%s" % k] = v
    props.update(cfg.get("io_properties") or {})

    auth = cfg.get("auth") or {}
    kind = auth.get("type")
    if kind == "gcloud":
        props["token"] = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True).stdout.strip()
    elif kind == "bearer_env":
        props["token"] = os.environ[auth["env_var"]]
    elif kind == "oauth2":
        props["credential"] = "%s:%s" % (os.environ[auth["client_id_env"]],
                                         os.environ[auth["client_secret_env"]])
        props["scope"] = auth.get("scope", "PRINCIPAL_ROLE:ALL")
        props["oauth2-server-uri"] = auth["token_url"]
    elif kind == "snowflake_keypair":
        # Write data files with OUR credentials, not the ones the catalog vends.
        # Snowflake session-scopes vended credentials without s3:DeleteObject,
        # so pyiceberg cannot clean up its own uncommitted manifests and the
        # commit reports an indeterminate state. The bucket is ours; use it
        # directly. This is a property of how we seed, not of the catalog.
        from botocore.session import Session as BotoSession
        _c = BotoSession().get_credentials().get_frozen_credentials()
        props["s3.access-key-id"] = _c.access_key
        props["s3.secret-access-key"] = _c.secret_key
        if _c.token:
            props["s3.session-token"] = _c.token
        props["s3.region"] = cfg.get("io_properties", {}).get("s3.region", "us-east-1")
        # Mint the same access token the probe harness uses, so the seed and the
        # probe reach the catalog by an identical path.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from probe.auth import SnowflakeKeyPair
        props["token"] = SnowflakeKeyPair(**{k: v for k, v in auth.items()
                                             if k != "type"}).token()
    elif kind == "sigv4":
        # pyiceberg signs REST calls itself when told the service and region.
        props["rest.sigv4-enabled"] = "true"
        props["rest.signing-name"] = auth["service"]
        props["rest.signing-region"] = auth["region"]
        # Setting any s3.* property makes pyiceberg build the FileSystem
        # explicitly, which then skips the default boto credential chain and
        # writes anonymously. So if we set one, we must set the credentials too.
        # Skipped when the catalog vends its own scoped credentials, which take
        # precedence and are the only ones its managed bucket accepts.
        vending = "vended-credentials" in str(
            (cfg.get("headers") or {}).get("X-Iceberg-Access-Delegation", ""))
        if not vending:
            from botocore.session import Session as BotoSession
            c = BotoSession().get_credentials().get_frozen_credentials()
            props["s3.access-key-id"] = c.access_key
            props["s3.secret-access-key"] = c.secret_key
            if c.token:
                props["s3.session-token"] = c.token
    elif kind not in (None, "none"):
        sys.exit("seeding does not support auth type %r (probe-only)" % kind)
    return RestCatalog(cfg["name"], **props)


def seed(cat, ns, tbl_name, location=None):
    if (ns,) not in cat.list_namespaces():
        cat.create_namespace(ns)
        print("created namespace", ns)

    ident = "%s.%s" % (ns, tbl_name)
    # S3 Tables refuses a plain drop ("only supports dropping tables with purge
    # enabled"), so a silent failure here leaves the old table in place and the
    # create below fails with TableAlreadyExists. Try purge as a fallback.
    for how, fn in (("drop", cat.drop_table), ("purge", getattr(cat, "purge_table", None))):
        if fn is None:
            continue
        try:
            fn(ident)
            print("dropped existing %s (%s)" % (ident, how))
            break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:90])
    else:
        pass

    schema = Schema(
        NestedField(1, "id", LongType(), required=True),
        NestedField(2, "ts", TimestamptzType(), required=False),
        NestedField(3, "payload", StringType(), required=False),
        # No identifier_field_ids: Databricks Unity rejects them outright
        # ("Table with identifier columns is not allowed", ErrorCode 2014), and
        # they are not needed by any probe. Dropping them is what lets one seed
        # path serve every catalog, which is what makes the field tier
        # comparable in the first place.
    )
    spec = PartitionSpec(
        PartitionField(source_id=2, field_id=1000, transform=DayTransform(), name="ts_day"))
    order = SortOrder(
        SortField(source_id=1, transform=IdentityTransform(),
                  direction=SortDirection.ASC, null_order=NullOrder.NULLS_FIRST))

    # Glue rejects create_table without an explicit location; catalogs that
    # manage their own storage (Polaris, BigLake, S3 Tables) infer it.
    extra = {"location": location} if location else {}
    # merge-on-read makes a delete produce delete FILES rather than rewriting
    # data files. Without this the table carries no v2 delete metadata at all,
    # and the delete-related field paths cannot be probed.
    props = {"probe": "control-column",
             "write.delete.mode": "merge-on-read",
             "write.update.mode": "merge-on-read",
             "write.merge.mode": "merge-on-read",
             "format-version": "2"}
    tbl = cat.create_table(ident, schema=schema, partition_spec=spec, sort_order=order,
                           properties=props, **extra)
    print("created table", ident)

    base = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    arrow_schema = tbl.schema().as_arrow()
    for n in range(3):
        day = base + dt.timedelta(days=n % 2)
        batch = pa.Table.from_pylist(
            [{"id": n * 10 + i, "ts": day + dt.timedelta(hours=i),
              "payload": "row-%d-%d" % (n, i)} for i in range(4)], schema=arrow_schema)
        tbl.append(batch)
        print("append %d -> snapshot %s" % (n + 1, tbl.current_snapshot().snapshot_id))

    # A delete, so the table has v2 delete metadata to probe. This is the point
    # of the whole exercise for the delete-related field paths: without it,
    # total-delete-files is 0 everywhere and those rows measure nothing.
    try:
        tbl.delete(delete_filter="id = 1")
        print("deleted id=1 -> snapshot", tbl.current_snapshot().snapshot_id)
    except Exception as e:
        print("delete FAILED:", type(e).__name__, str(e)[:160])

    with tbl.update_schema() as us:
        us.add_column("region", StringType(), doc="added to exercise schema history")
    print("evolved schema -> current-schema-id", tbl.schema().schema_id)

    try:
        with tbl.manage_snapshots() as ms:
            ms.create_tag(tbl.current_snapshot().snapshot_id, "control_tag")
        print("created tag control_tag")
    except Exception as e:
        print("tag skipped:", type(e).__name__, str(e)[:120])

    md = cat.load_table(ident).metadata
    dels = sum(int((sn.summary or {}).get("total-delete-files", 0) or 0)
               for sn in (md.snapshots or []))
    print("\n--- seeded metadata ---")
    print("  %-16s %s" % ("delete-files", dels))
    for label, val in [("format-version", md.format_version),
                       ("schemas", len(md.schemas)),
                       ("partition-specs", len(md.partition_specs)),
                       ("sort-orders", len(md.sort_orders)),
                       ("snapshots", len(md.snapshots)),
                       ("snapshot-log", len(md.snapshot_log)),
                       ("metadata-log", len(md.metadata_log)),
                       ("refs", list(md.refs))]:
        print("  %-16s %s" % (label, val))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True, help="name from catalogs.yaml")
    ap.add_argument("--config", default="catalogs.yaml")
    args = ap.parse_args()
    with open(args.config) as f:
        entries = yaml.safe_load(f)["catalogs"]
    match = [c for c in entries if c["name"] == args.catalog]
    if not match:
        sys.exit("no catalog %r in %s" % (args.catalog, args.config))
    cfg = match[0]
    print("seeding %s (%s)" % (cfg["name"], cfg["base_url"]))
    seed(build_catalog(cfg), cfg.get("namespace", "probe_ns"),
         cfg.get("table", "probe_table"), cfg.get("location"))


if __name__ == "__main__":
    main()
