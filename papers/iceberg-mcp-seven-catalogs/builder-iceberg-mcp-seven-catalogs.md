# One Iceberg MCP Server, Seven Catalogs: What It Takes to Reach Each One

This article provides a step by step guide to one MCP server for Apache Iceberg tables, pointed at seven Iceberg REST catalogs in turn. The server offers four read-only tools, and one environment variable decides which catalog it reads.

https://github.com/xbill9/lakehouse-iceberg-2026

---

#### What is this project trying to Do?

An MCP server gives any MCP client, such as Claude Code or another coding agent, a fixed set of tools. This one has four, all reads:

- **`iceberg_list_tables`** — every `namespace.table` in the catalog
- **`iceberg_describe_table`** — columns, partitioning, snapshots and the metadata location
- **`iceberg_count_rows`** — the exact row count from the snapshot summary
- **`iceberg_scan_table`** — a few rows, plus an exact count, min and max

Every Iceberg REST catalog speaks the same protocol, so in principle the same server should work against all of them. This project checks that against seven catalogs:

- **Apache Polaris** 1.7.0, in Docker on the same machine
- **Google BigLake**, **Microsoft OneLake**, **AWS Glue**, **AWS S3 Tables** and **Snowflake Horizon**, over the internet
- **Databricks Unity**, not run: its trial account has ended

The server is called directly over MCP, with no AI model involved, so each result depends only on the catalog and the server's settings. Measured on 2026-09-18 and 2026-09-19 (UTC), one run per catalog, reads only.

---

#### Where do I start?

The strategy is an incremental step by step approach.

First, the local Polaris catalog, which needs only Docker. Then the MCP server, called directly to check all four tools. Then one catalog at a time: its login, its storage package, and a run of the same four calls.

---

#### At This Point You Should Have…

- Docker, for the local Polaris catalog
- Python 3.10+ with `pyiceberg` 0.12.0 — this run used Python 3.14.7
- For each managed catalog you want to reach, an account with a table in it and a working command-line login: `gcloud`, `az`, `aws` or a Snowflake key pair

---

#### Step 1 — Start Polaris

```console
$ git clone https://github.com/xbill9/lakehouse-iceberg-2026
$ cd lakehouse-iceberg-2026/iceberg-conformance
$ ./polaris-up.sh
$ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
$ python3 seed_table.py --catalog apache-polaris
```

That creates `probe_ns.probe_table`: 11 rows, partitioned by day, with four snapshots.

---

#### Step 2 — Look at the Server

The server is `iceberg-mcp-hosts/servers/iceberg_mcp.py`. It speaks MCP over stdio as newline-delimited JSON-RPC and answers `initialize`, `tools/list`, `tools/call` and `ping`, with no MCP SDK.

It picks its catalog from two environment variables:

```console
$ ICEBERG_CATALOG=aws-glue ICEBERG_CATALOGS_FILE=catalogs.yaml python3 servers/iceberg_mcp.py
```

`catalogs.yaml` holds one entry per catalog: the URL, the warehouse, and how to log in. The server code is the same for every catalog.

---

#### Step 3 — Call It Without a Model

`sweep_catalogs.py` starts the server once per catalog and makes the same MCP calls each time: `initialize`, `tools/list`, then the four tools on the first table listed.

```console
$ cd ../iceberg-mcp-hosts
$ python3 sweep_catalogs.py --only apache-polaris
apache-polaris       probe_ns.probe_table                 list_tables=ok(1.0s)  describe_table=ok(0.4s)  count_rows=ok(0.0s)  scan_table=ok(0.1s)
```

The scan's reply shows what a client receives:

```plaintext
id | ts | payload | region
0 | 2026-09-01 00:00:00+00:00 | row-0-0 | None
2 | 2026-09-01 02:00:00+00:00 | row-0-2 | None
3 | 2026-09-01 03:00:00+00:00 | row-0-3 | None

3 of 11 row(s) shown, read from snapshot-id 1196292829914853564
COUNT: exactly 11 row(s) are in the table in snapshot-id 1196292829914853564. Exact, over the whole table.
MIN and MAX of id over those 11 row(s): 0 and 23. Exact.
```

A failed catalog call comes back as text starting `CATALOG ERROR`, so an agent can still say what it could not read. The sweep counts that text as a failure.

---

#### Step 4 — Add One Entry per Catalog

Each managed catalog needs its own login in `catalogs.yaml`. The server builds a PyIceberg `RestCatalog` from it:

| catalog | login | how files are read |
|---|---|---|
| Polaris | OAuth2 client ID and secret | PyArrow, local `file:` |
| BigLake | `gcloud` token, `x-goog-user-project` header | PyArrow, `gs://` |
| OneLake | `az` token | fsspec with `adlfs`, `abfss://` |
| Glue | SigV4, service `glue` | PyArrow, `s3://`, local AWS login |
| S3 Tables | SigV4, service `s3tables` | fsspec with `s3fs`, catalog-issued credential |
| Horizon | Snowflake key-pair JWT | PyArrow, `s3://`, catalog-issued credential |

S3 Tables issues a storage credential when asked with the `X-Iceberg-Access-Delegation: vended-credentials` header. Horizon returns one without being asked.

---

#### Step 5 — Install the Storage Packages

Listing, describing and counting read only catalog metadata, so they work with `pyiceberg` alone. Scanning reads data files, and three catalogs need packages that `pyiceberg` does not install by default. Without them the server answers three of the four tools and the scan fails:

```plaintext
CATALOG ERROR while scanning dbo.probe_table: ModuleNotFoundError: No module named 'adlfs'.

CATALOG ERROR while scanning probe_ns.probe_table: ModuleNotFoundError: No module named 's3fs'.
```

AWS logins made with the newer `aws login` command need one more package before any call works:

```plaintext
CATALOG ERROR while listing tables: MissingDependencyException: Missing Dependency: Using the login credential provider requires an additional dependency. You will need to pip install "botocore[crt]" before proceeding.
```

```console
$ pip install adlfs s3fs "botocore[crt]"
```

| package | needed for |
|---|---|
| `adlfs` | OneLake scans |
| `s3fs` | S3 Tables scans |
| `botocore[crt]` | Glue and S3 Tables with an `aws login` session |

---

####  Tip: Use the `az` Credential Directly for OneLake

OneLake's data files need an Azure storage credential as well as the catalog token. `DefaultAzureCredential` is the usual choice, and it tries the Azure VM metadata service before the `az` login. Off Azure, that attempt waits out its retries:

```plaintext
     917ms No environment configuration found.
     921ms ManagedIdentityCredential will use IMDS
  553989ms DefaultAzureCredential acquired a token from AzureCliCredential
AzureCliCredential      0.6s
DefaultAzureCredential  553.1s
```

Through the MCP server, a three-row OneLake scan took 858.5 seconds with `DefaultAzureCredential` and 3.4 seconds with `AzureCliCredential`. Every other tool call was unaffected, because only the scan reads files.

---

#### Step 6 — Run All Six

```console
$ python3 sweep_catalogs.py --only apache-polaris,google-lakehouse,microsoft-onelake,aws-glue,aws-s3tables,snowflake-horizon
$ python3 sweep_catalogs.py --report-only
```

```plaintext
catalog             measured (UTC)        table                   rows  partitioned     seconds: list describe count scan
apache-polaris      2026-09-18T23:58:37Z  probe_ns.probe_table      11  ts_day          1.0 0.5 0.0 0.1
aws-glue            2026-09-18T23:58:51Z  probe_ns.probe_table      11  ts_day          2.1 0.7 0.2 1.5
aws-s3tables        2026-09-18T23:58:57Z  probe_ns.probe_table      11  ts_day          2.2 0.3 0.2 2.0
google-lakehouse    2026-09-19T00:11:14Z  probe_ns.probe_table      11  ts_day          10.1 1.6 0.5 3.6
microsoft-onelake   2026-09-18T23:58:45Z  dbo.probe_table            6  (unpartitioned) 2.5 0.2 0.2 3.2
snowflake-horizon   2026-09-18T23:59:02Z  PROBE_NS.PROBE_TABLE      12  ts_day          7.3 2.2 1.4 1.9
```

**All four tools work on all six catalogs.** Each one reported the same four tools from `tools/list`, and no call returned an error.

The first call on each catalog also builds the client and fetches a login token, which is why `list` is the slowest column. Each figure is a single call, so the times show scale only.

---

#### Step 7 — Read What Came Back

The tables were created separately for an [earlier article](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj), and the server reports what each catalog holds:

- **OneLake** names its namespace `dbo`, stores `id` as an optional `int`, and has 6 rows in an unpartitioned table
- **Horizon** returns upper-case names, `PROBE_NS.PROBE_TABLE`, and has 12 rows
- **The other four** hold the same 11-row table, partitioned by day

A client only has to use the names `iceberg_list_tables` returns. The server passes them back unchanged, so `dbo` and upper-case names need no special handling.

---

####  Tip: Horizon Hands Out Storage Credentials Unasked

Loading a Horizon table leaves S3 credentials on the client's file reader, although the catalog entry asks for none:

```plaintext
snowflake-horizon
  client.region
  py-io-impl
  s3.access-key-id
  s3.secret-access-key
  s3.session-token
  s3.session-token-expires-at-ms
```

Horizon's catalog entry supplies no storage login, so its scan reads files with that credential. It also means a Horizon table load carries a live storage credential, so logs of that response need redacting.

---

#### Step 8 — Use It From an MCP Client

Any MCP client that starts stdio servers can run it. For Claude Code, a project `.mcp.json`:

```json
{
  "mcpServers": {
    "iceberg": {
      "command": "python3",
      "args": ["iceberg-mcp-hosts/servers/iceberg_mcp.py"],
      "env": {
        "ICEBERG_CATALOG": "aws-glue",
        "ICEBERG_CATALOGS_FILE": "iceberg-conformance/catalogs.yaml"
      }
    }
  }
}
```

To reach a different catalog, change `ICEBERG_CATALOG`. The measurements above call the server directly and do not use this file.

---

#### Compare and Contrast

| catalog | four tools | extra package | login on the machine |
|---|---|---|---|
| Apache Polaris |  | — | OAuth2 client secret |
| Google BigLake |  | — | `gcloud` |
| Microsoft OneLake |  | `adlfs` | `az` |
| AWS Glue |  | `botocore[crt]` with `aws login` | `aws` |
| AWS S3 Tables |  | `s3fs`, `botocore[crt]` with `aws login` | `aws` |
| Snowflake Horizon |  | — | key pair |
| Databricks Unity | not run | | |

---

#### Summary

The goal of this article was to point one Iceberg MCP server at seven catalogs and record what each one takes. The key to the solution was keeping the server code fixed, changing only the catalog entry, and calling the tools directly so that no model sits between the catalog and the result. The results were:

-  All four tools work on all six catalogs run: Polaris, BigLake, OneLake, Glue, S3 Tables and Horizon
-  The only change between catalogs is one environment variable and one entry in `catalogs.yaml`
-  Three packages outside `pyiceberg`'s defaults are needed: `adlfs` for OneLake, `s3fs` for S3 Tables, and `botocore[crt]` for an `aws login` session; without them the metadata tools work and the scan fails
-  `DefaultAzureCredential` took 553.1 seconds off Azure; `AzureCliCredential` took 0.6
-  Horizon returns S3 credentials with a table load, unasked
-  Databricks Unity was not run, because its trial account has ended

Scope: `iceberg_mcp.py` 1.0.0 on `pyiceberg` 0.12.0, `pyarrow` 25.0.1, `s3fs` 2026.9.0, `adlfs` 2026.8.0, `botocore` 1.43.75 and `azure-identity` 1.25.3, on Python 3.14.7. Apache Polaris 1.7.0 in Docker with local file storage; the managed catalogs over the internet from one machine, AWS in `us-east-1`. One run per catalog on 2026-09-18 and 2026-09-19 (UTC); Unity not run. Reads only. The tools are checked for answering without error; the tables differ between catalogs, so values are reported and not compared. Managed catalogs do not report a version.

The strategy for pointing one Iceberg MCP server at seven catalogs was validated with an incremental step by step approach.

---

#### References

* [lakehouse-iceberg-2026 | GitHub](https://github.com/xbill9/lakehouse-iceberg-2026)
* [Model Context Protocol specification](https://modelcontextprotocol.io/specification)
* [apache/iceberg-python](https://github.com/apache/iceberg-python)
* [Apache Polaris](https://polaris.apache.org/)
* [Seven Iceberg REST Catalogs: What They Declare, and What They Serve](https://dev.to/gde/seven-iceberg-rest-catalogs-what-they-declare-and-what-they-serve-40oj)
* [Four Iceberg Tools, Three Agent Frameworks: What Ports, and What Doesn't](https://dev.to/gde/four-iceberg-tools-three-agent-frameworks-what-ports-and-what-doesnt-a5g)
