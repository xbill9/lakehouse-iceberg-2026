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
//!
//! Three modes. The default issues each probe once and is what the viability
//! stream records. IRC_MODE=bench issues a fixed set of read operations
//! IRC_ITERS times after IRC_WARMUP discarded iterations, emitting one sample
//! per iteration in nanoseconds, and is what the comparison stream measures.
//! IRC_MODE=transport is not the Iceberg client at all: it times a raw GET to
//! IRC_PROBE_URL with a bearer token, so that the HTTP stack underneath can be
//! compared against Python's on the same request. Without that floor, "the
//! Rust client is faster" cannot be separated from "reqwest is faster than
//! requests", and those are different sentences with different consequences.
//!
//! All modes share one catalog object or one HTTP client, so the config fetch
//! and the token grant are paid once and are not inside any sample.

use std::collections::HashMap;
use std::env;
use std::sync::Arc;
use std::time::Instant;

use iceberg::io::{LocalFsStorageFactory, MemoryStorageFactory, StorageFactory};
use iceberg_storage_opendal::OpenDalResolvingStorageFactory;
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
    // Static headers, the crate's `header.<name>` properties. Used only by the
    // SigV4 demonstration: one signature, computed outside the crate for one
    // request, handed over as though it were a credential.
    if let Some(h) = env_opt("IRC_HEADERS_JSON") {
        let parsed: HashMap<String, String> =
            serde_json::from_str(&h).expect("IRC_HEADERS_JSON must be a JSON object of strings");
        for (k, v) in parsed {
            props.insert(format!("header.{}", k), v);
        }
    }

    // `load_table` builds a Table, and a Table carries a FileIO, so the client
    // refuses to hand back a loadTable response at all without a storage
    // factory. iceberg 0.10.1 ships exactly two -- local filesystem and memory.
    // The cloud backends live in iceberg-storage-opendal, whose resolving
    // factory picks one by the scheme of the table's location, and without it
    // every s3://, gs:// and abfss:// catalog fails on our packaging rather
    // than on anything the catalog did. Which factory is in play is a property
    // of the run and is recorded with it, never defaulted silently.
    let mut builder = RestCatalogBuilder::default();
    match env_opt("IRC_STORAGE").as_deref() {
        Some("local-fs") => {
            builder = builder.with_storage_factory(Arc::new(LocalFsStorageFactory) as Arc<dyn StorageFactory>)
        }
        Some("memory") => {
            builder = builder.with_storage_factory(Arc::new(MemoryStorageFactory) as Arc<dyn StorageFactory>)
        }
        Some("opendal") => {
            builder = builder.with_storage_factory(
                Arc::new(OpenDalResolvingStorageFactory::new()) as Arc<dyn StorageFactory>,
            )
        }
        None | Some("none") => {}
        Some(other) => {
            eprintln!(
                "IRC_STORAGE must be local-fs, memory, opendal or none (got {})",
                other
            );
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

/// One timed operation, IRC_ITERS times, after IRC_WARMUP discarded runs.
///
/// The warmup is not decoration: the first call pays TLS, DNS and the
/// connection pool, and a benchmark that leaves it in measures the network
/// rather than the client. Every sample is emitted; percentiles are computed
/// by the driver, never here and never by hand.
macro_rules! bench_op {
    ($name:expr, $warmup:expr, $iters:expr, $call:expr) => {{
        for _ in 0..$warmup {
            let _ = $call.await;
        }
        for i in 0..$iters {
            let t = Instant::now();
            let outcome = $call.await;
            let ns = t.elapsed().as_nanos() as u64;
            match outcome {
                Ok(_) => emit(json!({
                    "client": "rust", "op": $name, "iter": i, "ns": ns,
                })),
                Err(e) => {
                    emit(json!({
                        "client": "rust", "op": $name, "iter": i, "ns": ns,
                        "error_kind": format!("{:?}", e.kind()),
                    }));
                    break;
                }
            }
        }
    }};
}

async fn bench(catalog: &RestCatalog, ns: &NamespaceIdent, table: &TableIdent) {
    let warmup: u32 = env_opt("IRC_WARMUP").and_then(|v| v.parse().ok()).unwrap_or(3);
    let iters: u32 = env_opt("IRC_ITERS").and_then(|v| v.parse().ok()).unwrap_or(30);

    bench_op!("list_namespaces", warmup, iters, catalog.list_namespaces(None));
    bench_op!("load_namespace", warmup, iters, catalog.get_namespace(ns));
    bench_op!("head_namespace", warmup, iters, catalog.namespace_exists(ns));
    bench_op!("list_tables", warmup, iters, catalog.list_tables(ns));
    bench_op!("load_table", warmup, iters, catalog.load_table(table));
    bench_op!("head_table", warmup, iters, catalog.table_exists(table));
}

/// A raw GET, body read and discarded, timed the way bench_op! times a call.
/// Deliberately the same shape as the Python side's `session.get(url).text`.
async fn transport_floor() {
    let url = env_req("IRC_PROBE_URL");
    let token = env_opt("IRC_TOKEN");
    let warmup: u32 = env_opt("IRC_WARMUP").and_then(|v| v.parse().ok()).unwrap_or(5);
    let iters: u32 = env_opt("IRC_ITERS").and_then(|v| v.parse().ok()).unwrap_or(60);

    let pace = std::time::Duration::from_millis(
        env_opt("IRC_PACE_MS").and_then(|v| v.parse().ok()).unwrap_or(0));
    // The same extra headers the Python session sends, so this is the same
    // request and not a cheaper one. BigLake refuses a call without
    // x-goog-user-project; before this, its floor would have timed a 403.
    let extra: HashMap<String, String> = env_opt("IRC_HEADERS_JSON")
        .map(|h| serde_json::from_str(&h).expect("IRC_HEADERS_JSON must be a JSON object"))
        .unwrap_or_default();

    let client = reqwest::Client::new();
    let fetch = || async {
        let mut req = client.get(&url);
        if let Some(t) = &token {
            req = req.bearer_auth(t);
        }
        for (k, v) in &extra {
            req = req.header(k.as_str(), v.as_str());
        }
        match req.send().await {
            // A 429 or a 403 is a fast answer to a different question; it is
            // an error here, never a sample.
            Ok(resp) if !resp.status().is_success() => Err(format!("HTTP {}", resp.status().as_u16())),
            Ok(resp) => resp.text().await.map(|b| b.len()).map_err(|e| e.to_string()),
            Err(e) => Err(e.to_string()),
        }
    };

    for _ in 0..warmup {
        let _ = fetch().await;
        tokio::time::sleep(pace).await;
    }
    for i in 0..iters {
        let t = Instant::now();
        let outcome = fetch().await;
        let ns = t.elapsed().as_nanos() as u64;
        tokio::time::sleep(pace).await;
        match outcome {
            Ok(_) => emit(json!({
                "client": "rust", "op": "transport only", "iter": i, "ns": ns,
            })),
            Err(e) => {
                emit(json!({
                    "client": "rust", "op": "transport only", "iter": i,
                    "ns": ns, "error": e,
                }));
                break;
            }
        }
    }
}

#[tokio::main]
async fn main() {
    if env_opt("IRC_MODE").as_deref() == Some("transport") {
        transport_floor().await;
        return;
    }

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

    if env_opt("IRC_MODE").as_deref() == Some("bench") {
        // Cold start is the driver's measurement, not this process's: it is
        // wall-clock from spawn to exit with IRC_ITERS=1, so the catalog is
        // built and each operation answered once, and a process cannot time
        // its own exec. What this reports is the steady state, with the
        // catalog already built.
        bench(&catalog, &ns, &table).await;
        return;
    }

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

    // Not one of paper 1's probes: the first byte read through the client's
    // own storage layer. load_table builds a FileIO and never uses it, so a
    // green load_table says nothing about storage. This reads the metadata
    // file the catalog pointed at. The crate sends no
    // X-Iceberg-Access-Delegation header, so whatever credentials this uses
    // are either vended unasked or ambient; the config key NAMES are recorded
    // to tell which, never their values, and never the path.
    let t = Instant::now();
    let touched = async {
        let tbl = catalog.load_table(&table).await?;
        let io = tbl.file_io();
        let mut keys: Vec<String> = io.config().props().keys().cloned().collect();
        keys.sort();
        // Emitted before the read, so a failed read still says what the
        // storage layer was handed.
        emit(json!({"probe": "storage_fileio_config", "keys": keys.clone()}));
        let loc = tbl.metadata_location_result()?.to_string();
        // `file:/path` has one slash, so split on the colon, not on "://".
        let scheme = loc.split(':').next().unwrap_or("").to_string();
        let t_read = Instant::now();
        let bytes = io.new_input(&loc)?.read().await?;
        Ok::<Value, iceberg::Error>(json!({
            "scheme": scheme,
            "bytes_read": bytes.len(),
            "read_ms": t_read.elapsed().as_millis() as u64,
            "fileio_config_keys": keys,
        }))
    }
    .await;
    record("storage_read_metadata", t, touched);
}
