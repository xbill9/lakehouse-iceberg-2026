#!/usr/bin/env python3
"""Time both clients over the same operations, against the same catalog.

    $ cargo build --release
    $ export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t
    $ python3 bench.py --rounds 5 --iters 20
    apache-polaris   6 ops, 2 clients, 5 rounds x 20 iters = 1200 samples
    wrote evidence/bench-apache-polaris.json

The comparison stream's harness. The surface tables say what each client can
express; this says what it costs to use, which is the part that cannot be read
out of either repository.

Rules this harness follows, each of which was a way to get a wrong number:

  release build          A debug Rust binary is not the artifact anyone ships.
                         The driver refuses to run against target/debug.
  fresh process, both    Both clients are spawned. The driver is itself Python,
                         so timing pyiceberg in-process would give it a warm
                         interpreter while Rust paid for an exec.
  startup excluded       Each process builds its catalog, runs a warmup, and
                         only then records. Config fetch and token grant are
                         paid once, outside every sample.
  startup also measured  Separately, as cold start: wall clock from spawn
                         to exit, with the catalog built and each of the six
                         operations answered once. Not "one call" -- that
                         was this file's description until 2026-09-18, and
                         on a vendor the difference is six round trips on
                         each side. Symmetric, so the comparison holds.
  interleaved rounds     Clients alternate round by round, so a machine that
                         gets slower halfway through slows both equally.
  every sample kept      Percentiles are computed here, from the stored
                         samples, and are re-derivable without re-running.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, os.pardir, "iceberg-conformance")
sys.path.insert(0, HERE)
sys.path.insert(0, CONF)

import yaml                                          # noqa: E402
import pyiceberg                                     # noqa: E402
import redact                                        # noqa: E402
import run_pyiceberg as rp                           # noqa: E402
import run_rust as rr                                # noqa: E402

RELEASE = os.path.join(HERE, "target", "release", "irc-probe")
WORKER = os.path.join(HERE, "bench_worker.py")
OPS = ["list_namespaces", "load_namespace", "head_namespace",
       "list_tables", "load_table", "head_table"]


def percentile(samples, q):
    """Nearest-rank, on sorted samples. No interpolation, no averaging."""
    if not samples:
        return None
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, int(round(q / 100.0 * len(ordered) + 0.5)) - 1))
    return ordered[k]


def spawn(cmd, env, timeout=600):
    started = time.perf_counter_ns()
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=timeout)
    wall = time.perf_counter_ns() - started
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            rows.append(json.loads(line))
    return rows, wall, proc.returncode, proc.stderr.strip()


def rust_env(cat, storage, warmup, iters):
    mode, _ = rr.auth_plan(cat.get("auth"))
    if mode == "absent":
        return None
    env = rr.build_env(cat, mode, storage)
    env.update({"IRC_MODE": "bench", "IRC_WARMUP": str(warmup),
                "IRC_ITERS": str(iters)})
    return env


def py_env(cat, warmup, iters, token=None):
    env = dict(os.environ)
    env.update({"IRC_CATALOG": cat["name"], "IRC_WARMUP": str(warmup),
                "IRC_ITERS": str(iters)})
    if token:
        env["IRC_TOKEN"] = token
    return env


def stats_for(samples):
    return {
        "n": len(samples),
        "min_us": round(min(samples) / 1000.0, 1),
        "p50_us": round(percentile(samples, 50) / 1000.0, 1),
        "p90_us": round(percentile(samples, 90) / 1000.0, 1),
        "p99_us": round(percentile(samples, 99) / 1000.0, 1),
        "max_us": round(max(samples) / 1000.0, 1),
        "stdev_us": round(statistics.stdev(samples) / 1000.0, 1) if len(samples) > 1 else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="apache-polaris", help="catalog name")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--iters", type=int, default=20, help="per op, per round")
    ap.add_argument("--warmup", type=int, default=3, help="per op, per round")
    ap.add_argument("--storage", default="local-fs",
                    choices=["local-fs", "memory", "opendal", "none"])
    ap.add_argument("--allow-debug-build", action="store_true",
                    help="measure the debug binary anyway. Never for evidence.")
    args = ap.parse_args()

    binary = RELEASE
    if not os.path.exists(binary):
        if not args.allow_debug_build:
            sys.exit("no release binary at %s -- run `cargo build --release`. "
                     "A debug build is 2-10x slower and is not what anyone "
                     "ships; measuring it would compare a profile, not a "
                     "client." % os.path.relpath(binary, HERE))
        binary = os.path.join(HERE, "target", "debug", "irc-probe")

    cfg = yaml.safe_load(open(os.path.join(CONF, "catalogs.yaml")))
    cat = next((c for c in cfg["catalogs"]
                if c["name"] == args.only and c.get("enabled", True)), None)
    if cat is None:
        sys.exit("not configured or not enabled: %s" % args.only)

    r_env = rust_env(cat, args.storage, args.warmup, args.iters)
    # The same pre-minted bearer for both clients, when the auth is a static
    # token. rust_env already carries one in IRC_TOKEN.
    p_env = py_env(cat, args.warmup, args.iters,
                   token=(r_env or {}).get("IRC_TOKEN") if (
                       rr.auth_plan(cat.get("auth"))[0] == "static") else None)
    if r_env is None:
        print("%s: the Rust client cannot express this catalog's auth; "
              "pyiceberg only" % cat["name"])

    # A failing round prints whatever the client felt like printing, and a
    # vendor URL carries the account. Same rule as the runners: scrub, then
    # refuse to write if anything configured survived.
    pairs = redact.values_for(cat, redact.secret_env_names(cat))

    samples = []
    errors = []
    for rnd in range(args.rounds):
        # Alternate who goes first, so neither client always pays for a cold
        # page cache or always benefits from a warm one.
        order = [("rust", binary), ("pyiceberg", WORKER)]
        if rnd % 2:
            order.reverse()
        for client, target in order:
            if client == "rust":
                if r_env is None:
                    continue
                rows, _wall, rc, stderr = spawn([target], r_env)
            else:
                rows, _wall, rc, stderr = spawn([sys.executable, target], p_env)
            if rc != 0:
                errors.append({"client": client, "round": rnd, "rc": rc,
                               "stderr": redact.scrub(stderr, pairs)[:400]})
            for row in rows:
                if "ns" in row and "op" in row:
                    row["round"] = rnd
                    samples.append(row)

    # Cold start: spawn to exit with IRC_ITERS=1 and no warmup, so each client
    # builds its catalog and answers each of the six operations once. Measured
    # last, so it cannot warm anything the timed rounds depend on.
    cold = {}
    for client, target, env in (("rust", binary, r_env),
                                ("pyiceberg", WORKER, p_env)):
        if env is None:
            continue
        one = dict(env, IRC_WARMUP="0", IRC_ITERS="1")
        walls = []
        for _ in range(5):
            cmd = [target] if client == "rust" else [sys.executable, target]
            _rows, wall, rc, _stderr = spawn(cmd, one)
            if rc == 0:
                walls.append(wall)
        if walls:
            cold[client] = stats_for(walls)

    # A sample that carries an error_kind timed a refusal, not the operation.
    # Kept in the file, never in the stats. Found 2026-09-18 when BigLake
    # answered a burst of back-to-back runs with 429: no stored run contained
    # one, but nothing had stopped it from being averaged in.
    by = {}
    error_samples = 0
    for row in samples:
        if "error_kind" in row:
            error_samples += 1
            continue
        by.setdefault((row["client"], row["op"]), []).append(row["ns"])

    stats = []
    for op in OPS:
        row = {"op": op}
        for client in ("rust", "pyiceberg"):
            got = [s for s in by.get((client, op), [])]
            if got:
                row[client] = stats_for(got)
        if "rust" in row and "pyiceberg" in row and row["rust"]["p50_us"]:
            # Computed here, not read off the table by eye.
            row["p50_ratio_py_over_rust"] = round(
                row["pyiceberg"]["p50_us"] / row["rust"]["p50_us"], 2)
        stats.append(row)

    rustc = subprocess.run(["rustc", "--version"], capture_output=True,
                           text=True).stdout.strip()
    meta = {
        "catalog": cat["name"],
        "control": cat["name"] == "apache-polaris",
        "rust_client": "iceberg-catalog-rest 0.10.1",
        "rust_profile": "release" if binary == RELEASE else "debug (NOT EVIDENCE)",
        "rustc": rustc,
        "python": sys.version.split()[0],
        "pyiceberg": pyiceberg.__version__,
        "storage_factory": args.storage,
        "rounds": args.rounds,
        "iters_per_round": args.iters,
        "warmup_per_round": args.warmup,
        "ops": OPS,
        "cpu_count": os.cpu_count(),
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample_count": len(samples),
        "error_sample_count": error_samples,
    }
    if errors:
        meta["errors"] = errors

    document = {"meta": meta, "cold_start_wall": cold, "stats": stats,
                "samples": samples}
    redact.verify(document, pairs)

    # One file per run, never overwritten. A benchmark whose evidence is
    # replaced by the next run cannot show its own run-to-run spread, and that
    # spread is the difference between a number and a measurement.
    out = os.path.join(HERE, "evidence", "bench-%s-%s.json" % (
        cat["name"], meta["measured_utc"].replace("-", "").replace(":", "")))
    with open(out, "w") as fh:
        json.dump(document, fh, indent=2)
        fh.write("\n")

    print("%-18s %d ops, %d clients, %d rounds x %d iters = %d samples" % (
        cat["name"], len(OPS), 2 if r_env else 1, args.rounds, args.iters,
        len(samples)))
    print("wrote %s" % os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
