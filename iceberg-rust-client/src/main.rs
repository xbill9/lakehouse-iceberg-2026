//! Issue paper 1's read probes through iceberg-catalog-rest, one JSON object
//! per probe on stdout.
//!
//! Only the probes this client can actually express are here. The other 14 are
//! not this binary's business: `operation_map.py` records why each one cannot
//! be issued, and the Python driver merges the two so a probe that has no Rust
//! request is reported as NOT-EXPRESSIBLE rather than as a failure.
//!
//! Read-only by construction. There is no write path in this file, so a run
//! against a credentialed catalog cannot leave residue behind.
//!
//! Nothing from a loadTable response is printed except counts and integers.
//! That response can carry vended storage credentials and bucket paths, and
//! this output is written to disk.

use std::collections::HashMap;
use std::env;
use std::sync::Arc;
use std::time::Instant;

use iceberg::io::{LocalFsStorageFactory, MemoryStorageFactory, StorageFactory};
use iceberg::{Catalog, CatalogBuilder, NamespaceIdent, TableIdent};
use iceberg_catalog_rest::{
    REST_CATALOG_PROP_URI, REST_CATALOG_PROP_WAREHOUSE, RestCatalog, RestCatalogBuilder,
};
use serde_json::{json, Value};

const CRATE_VERSION: &str = "0.10.1";

fn env_opt(key: &str) -> Option<String> {
    match env::var(key) {
        Ok(v) if !v.is_empty() => Some(v),
        _ => None,
    }
}

fn env_req(key: &str) -> String {
    env_opt(key).unwrap_or_else(|| {
        eprintln!("{} is required", key);
        std::process::exit(2);
    })
}

fn emit(v: Value) {
    println!("{}", v);
}

/// A probe that ran. `ok` is whether the client returned a value, which is not
/// the same question as whether the catalog behaved -- the driver decides that.
fn record(probe: &str, started: Instant, outcome: Result<Value, iceberg::Error>) {
    let ms = started.elapsed().as_millis() as u64;
    match outcome {
        Ok(detail) => emit(json!({
            "probe": probe, "ok": true, "ms": ms, "detail": detail,
        })),
        Err(e) => emit(json!({
            "probe": probe,
            "ok": false,
            "ms": ms,
            "error_kind": format!("{:?}", e.kind()),
            "error": e.to_string(),
        })),
    }
}

/// Build the catalog from environment, mirroring the conformance harness's
/// config keys. `prefix` is deliberately absent: the crate takes it from
/// /v1/config itself, and paper 1's rule is that a prefix goes in raw.
async fn build_catalog() -> RestCatalog {
    let mut props: HashMap<String, String> = HashMap::new();
    props.insert(REST_CATALOG_PROP_URI.into(), env_req("IRC_URI"));
    if let Some(w) = env_opt("IRC_WAREHOUSE") {
        props.insert(REST_CATALOG_PROP_WAREHOUSE.into(), w);
    }
    // The crate's auth surface, in full: a bearer token, OAuth2 client
    // credentials, or static headers. There is no SigV4 here because there is
    // none in the crate.
    if let Some(t) = env_opt("IRC_TOKEN") {
        props.insert("token".into(), t);
    }
    if let Some(c) = env_opt("IRC_CREDENTIAL") {
        props.insert("credential".into(), c);
    }
    if let Some(u) = env_opt("IRC_OAUTH2_SERVER_URI") {
        props.insert("oauth2-server-uri".into(), u);
    }
    if let Some(s) = env_opt("IRC_SCOPE") {
        props.insert("scope".into(), s);
    }

    // `load_table` builds a Table, and a Table carries a FileIO, so the client
    // refuses to hand back a loadTable response at all without a storage
    // factory. iceberg 0.10.1 ships exactly two -- local filesystem and memory
    // -- so which one is in play is a property of the run and is recorded with
    // it, never defaulted silently.
    let mut builder = RestCatalogBuilder::default();
    match env_opt("IRC_STORAGE").as_deref() {
        Some("local-fs") => {
            builder = builder.with_storage_factory(Arc::new(LocalFsStorageFactory) as Arc<dyn StorageFactory>)
        }
        Some("memory") => {
            builder = builder.with_storage_factory(Arc::new(MemoryStorageFactory) as Arc<dyn StorageFactory>)
        }
        None | Some("none") => {}
        Some(other) => {
            eprintln!("IRC_STORAGE must be local-fs, memory or none (got {})", other);
            std::process::exit(2);
        }
    }

    match builder
        .load(env_req("IRC_CATALOG"), props)
        .await
    {
        Ok(c) => c,
        Err(e) => {
            emit(json!({
                "probe": "build", "ok": false, "ms": 0,
                "error_kind": format!("{:?}", e.kind()),
                "error": e.to_string(),
            }));
            std::process::exit(1);
        }
    }
}

#[tokio::main]
async fn main() {
    let ns = NamespaceIdent::from_strs(env_req("IRC_NAMESPACE").split('.'))
        .expect("namespace must have at least one level");
    let table = TableIdent::new(ns.clone(), env_req("IRC_TABLE"));

    emit(json!({
        "probe": "_meta",
        "crate": "iceberg-catalog-rest",
        "version": CRATE_VERSION,
        "catalog": env_req("IRC_CATALOG"),
        "storage_factory": env_opt("IRC_STORAGE").unwrap_or_else(|| "none".into()),
    }));

    let catalog = build_catalog().await;

    // GET /v1/config is issued by the client on first use and cannot be called
    // on its own, so it is not a row this binary can measure. Reported, not
    // guessed at: whether it succeeded is visible only through the first probe
    // below, and the driver reads it that way.
    emit(json!({
        "probe": "config",
        "ok": null,
        "status": "implicit",
        "note": "issued by RestCatalog on first use; not separately callable",
    }));

    let t = Instant::now();
    record("list_namespaces", t, catalog.list_namespaces(None).await
        .map(|v| json!({"count": v.len()})));

    let t = Instant::now();
    record("list_namespaces_parent", t, catalog.list_namespaces(Some(&ns)).await
        .map(|v| json!({"count": v.len()})));

    let t = Instant::now();
    record("load_namespace", t, catalog.get_namespace(&ns).await
        .map(|n| json!({"property_count": n.properties().len()})));

    let t = Instant::now();
    record("head_namespace", t, catalog.namespace_exists(&ns).await
        .map(|b| json!({"exists": b})));

    let t = Instant::now();
    record("list_tables", t, catalog.list_tables(&ns).await
        .map(|v| json!({"count": v.len()})));

    // Counts and integers only. No location, no UUID, no property values.
    let t = Instant::now();
    record("load_table", t, catalog.load_table(&table).await.map(|tbl| {
        let md = tbl.metadata();
        json!({
            "format_version": format!("{:?}", md.format_version()),
            "schema_field_count": md.current_schema().as_struct().fields().len(),
            "snapshot_count": md.snapshots().count(),
            "has_current_snapshot": md.current_snapshot().is_some(),
            "partition_field_count": md.default_partition_spec().fields().len(),
            "sort_order_field_count": md.default_sort_order().fields.len(),
        })
    }));

    let t = Instant::now();
    record("head_table", t, catalog.table_exists(&table).await
        .map(|b| json!({"exists": b})));
}
