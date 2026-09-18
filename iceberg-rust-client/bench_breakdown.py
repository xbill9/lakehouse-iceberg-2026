#!/usr/bin/env python3
"""Where does pyiceberg's extra time go? Decompose one call, and one startup.

    $ python3 bench_breakdown.py
    wrote evidence/bench-breakdown-apache-polaris-<ts>.txt

The benchmark says pyiceberg is slower. That is a number, not an explanation,
and an explanation guessed at is worth nothing. This takes the same catalog
object the benchmark uses and times the same request at three depths:

  transport    catalog._session.get(url) -- the exact same connection pool,
               the same auth header, the response body read and not parsed
  + json       the same, plus json.loads on the body
  + pydantic   the same, plus the model the client validates into
  + client     catalog.list_namespaces(), the whole method

Each layer adds one thing, so the differences are attributable rather than
inferred. cProfile over the same calls then names the functions.

The layers are interleaved, one iteration of each in turn, for the reason
bench.py interleaves its clients: run them in blocks and a server that warms
up over the run hands its later blocks a discount. The first version of this
script did exactly that and reported transport as slower than the whole call
that contains it, which is a number that cannot be true and was a useful thing
to have printed.

Startup is decomposed the same way: a bare interpreter, an interpreter that
imports the client, and the client's own catalog construction.
"""

import argparse
import cProfile
import io
import json
import os
import pstats
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
from bench import percentile                         # noqa: E402
from make_surface import _wrap                       # noqa: E402
from pyiceberg.catalog.rest import RestCatalog       # noqa: E402


def timed_interleaved(layers, iters, warmup=5, pace_s=0.0):
    """One iteration of each layer in turn, so drift lands on all of them.

    `pace_s` sleeps between calls, outside every timed region. BigLake
    answered back-to-back calls with 429 on 2026-09-18; the pause keeps the
    request rate under its quota without entering any sample.
    """
    for _ in range(warmup):
        for _name, fn in layers:
            fn()
            time.sleep(pace_s)
    out = {name: [] for name, _ in layers}
    for _ in range(iters):
        for name, fn in layers:
            t = time.perf_counter_ns()
            fn()
            out[name].append(time.perf_counter_ns() - t)
            time.sleep(pace_s)
    return out


def p50_diff_interval(a, b, resamples=2000, seed=20260918):
    """95% bootstrap interval of p50(a) - p50(b), in nanoseconds.

    Not 2xSEM: a vendor round trip has a heavy tail -- one OneLake run had a
    stdev of 1.6 s around a 176 ms median -- and a mean-based bound drowns a
    median difference that every quantile agrees on. Fixed seed, so the
    interval is reproducible from the stored samples.
    """
    import random
    import statistics
    rng = random.Random(seed)
    diffs = []
    for _ in range(resamples):
        ra = [rng.choice(a) for _ in a]
        rb = [rng.choice(b) for _ in b]
        diffs.append(statistics.median(ra) - statistics.median(rb))
    diffs.sort()
    return diffs[int(0.025 * resamples)], diffs[int(0.975 * resamples) - 1]


def us(samples):
    return (percentile(samples, 50) / 1000.0,
            percentile(samples, 90) / 1000.0,
            statistics.stdev(samples) / 1000.0 if len(samples) > 1 else 0.0)


def sem_us(samples):
    """Standard error of the mean, in microseconds.

    A layer difference smaller than a couple of these is not a measurement of
    that layer, it is the machine. Printed beside every delta because the first
    version of this file did not, and four runs of it produced pydantic deltas
    of -0.5, +17.7, +16.9 and -22.8 us -- which a paper then quoted as "+17 us"
    by taking the two that agreed.
    """
    if len(samples) < 2:
        return 0.0
    return statistics.stdev(samples) / (len(samples) ** 0.5) / 1000.0


def subprocess_ms(args, runs=5):
    walls = []
    for _ in range(runs):
        t = time.perf_counter_ns()
        subprocess.run(args, capture_output=True, check=True)
        walls.append(time.perf_counter_ns() - t)
    return percentile(walls, 50) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="apache-polaris")
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--pace-ms", type=int, default=0,
                    help="pause between calls, outside every sample; for a "
                         "catalog with a request-rate quota")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(CONF, "catalogs.yaml")))
    cat = next(c for c in cfg["catalogs"] if c["name"] == args.only)
    mode, _ = rp.auth_plan(cat.get("auth"))
    pairs = redact.values_for(cat, redact.secret_env_names(cat))

    construct = []
    for _ in range(3):
        t = time.perf_counter_ns()
        catalog = RestCatalog(cat["name"], **rp.base_props(cat, mode))
        construct.append(time.perf_counter_ns() - t)

    # The same URL the method builds, so nothing below is a different request.
    url = catalog.url("namespaces")
    session = catalog._session

    from pyiceberg.catalog.rest import ListNamespaceResponse

    def transport_no_env():
        # requests re-reads the proxy environment on every request unless
        # trust_env is off. Same session, same auth, one flag: whatever this
        # saves is a cost a caller can remove without changing library.
        session.trust_env = False
        try:
            return ok_text(session.get(url))
        finally:
            session.trust_env = True

    def ok_text(response):
        # A 429 or a 5xx is a fast answer to a different question. BigLake
        # returned 429 to a burst on 2026-09-18 and the transport layer would
        # have timed it happily; only the pydantic layer noticed.
        if response.status_code != 200:
            raise RuntimeError("HTTP %d from the catalog; refusing to time it"
                               % response.status_code)
        return response.text

    layers = [
        ("transport only", lambda: ok_text(session.get(url))),
        ("transport, no env", transport_no_env),
        ("+ json.loads", lambda: json.loads(ok_text(session.get(url)))),
        ("+ pydantic", lambda: ListNamespaceResponse.model_validate_json(
            ok_text(session.get(url)))),
        ("+ client method", lambda: catalog.list_namespaces()),
    ]
    timings = timed_interleaved(layers, args.iters, pace_s=args.pace_ms / 1000.0)
    results = [(name, timings[name]) for name, _ in layers]

    prof = cProfile.Profile()
    for _ in range(args.iters):
        prof.enable()
        catalog.list_namespaces()
        prof.disable()
        time.sleep(args.pace_ms / 1000.0)
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(22)
    profile_lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]

    # The same GET, through Rust's HTTP stack. Without this the Python-side
    # decomposition says where pyiceberg's time goes but not why the other
    # client is quicker.
    rust_bin = os.path.join(HERE, "target", "release", "irc-probe")
    rust_floor = []
    rust_floor_error = None
    if os.path.exists(rust_bin):
        env = dict(os.environ)
        env.update({"IRC_MODE": "transport", "IRC_PROBE_URL": url,
                    "IRC_TOKEN": rp.bearer_from_harness(cat["auth"], cat["base_url"])
                    if (cat.get("auth") or {}).get("type") != "none" else "",
                    "IRC_WARMUP": "5", "IRC_ITERS": str(args.iters),
                    "IRC_PACE_MS": str(args.pace_ms),
                    # Everything the Python session sends beyond auth and
                    # the transport's own defaults, so the GET is identical.
                    "IRC_HEADERS_JSON": json.dumps({
                        k: v for k, v in session.headers.items()
                        if k.lower() not in ("authorization", "user-agent",
                                             "accept", "accept-encoding",
                                             "connection")})})
        proc = subprocess.run([rust_bin], env=env, capture_output=True,
                              text=True, timeout=300)
        for line in proc.stdout.splitlines():
            if line.startswith("{"):
                row = json.loads(line)
                if "ns" in row and "error" not in row:
                    rust_floor.append(row["ns"])
                elif "error" in row:
                    rust_floor_error = redact.scrub(row["error"], pairs)

    bare = subprocess_ms([sys.executable, "-c", "pass"])
    imported = subprocess_ms(
        [sys.executable, "-c", "import pyiceberg.catalog.rest"])
    rust_bin = os.path.join(HERE, "target", "release", "irc-probe")

    out, w = [], None
    out = []
    w = out.append
    w("# Where pyiceberg's extra time goes, on %s." % cat["name"])
    w("# Generated by bench_breakdown.py. Same catalog object, same session,")
    w("# same URL at every depth, so each line differs from the one above it")
    w("# by exactly one thing.")
    w("")
    w("  client      pyiceberg %s on python %s" % (
        pyiceberg.__version__, sys.version.split()[0]))
    w("  iterations  %d, after 5 discarded" % args.iters)
    if args.pace_ms:
        w("  pacing      %d ms between calls, outside every sample" % args.pace_ms)
    w("  measured    %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    w("")

    w("## One GET /v1/{prefix}/namespaces, at three depths (microseconds)")
    w("")
    w("  %-20s %9s %9s %9s %12s %8s  %s" % (
        "layer", "p50", "p90", "stdev", "added p50", "2xSEM", "separable?"))
    previous = None
    previous_samples = None
    for name, samples in results:
        p50, p90, sd = us(samples)
        sem = sem_us(samples)
        if previous is None:
            added, bound, verdict = "--", "--", ""
        else:
            delta = p50 - previous
            # Two standard errors of the noisier of the two layers being
            # differenced. Cheap, and the only thing standing between a
            # 17-microsecond delta and a sentence in an article.
            threshold = 2 * max(sem, sem_us(previous_samples))
            added = "%+.1f" % delta
            bound = "%.1f" % threshold
            verdict = "yes" if abs(delta) > threshold else "NO -- noise"
        w("  %-20s %9.1f %9.1f %9.1f %12s %8s  %s" % (
            name, p50, p90, sd, added, bound, verdict))
        previous, previous_samples = p50, samples
    w("")
    for line in _wrap(
            "A delta is called separable only when it exceeds twice the "
            "standard error of the mean of the noisier layer it is differenced "
            "against. Anything marked NO is this machine, not that layer, and "
            "must not be quoted as the cost of it."):
        w("  %s" % line)
    w("")
    transport = us(results[0][1])[0]
    total = us(results[-1][1])[0]
    w("  transport is %.0f%% of the call; everything the library does on top of"
      % (transport / total * 100.0))
    w("  it is the other %.0f%%." % (100.0 - transport / total * 100.0))
    w("")

    if rust_floor:
        r50, r90, rsd = us(rust_floor)
        w("## The same GET through the other client's HTTP stack")
        w("")
        w("  %-20s %9s %9s %9s" % ("layer", "p50", "p90", "stdev"))
        w("  %-20s %9.1f %9.1f %9.1f" % ("rust, reqwest", r50, r90, rsd))
        w("  %-20s %9.1f %9.1f %9.1f" % (
            "python, requests", transport, us(results[0][1])[1],
            us(results[0][1])[2]))
        w("")
        for line in _wrap(
                "Both are a GET to the same URL with the same bearer, body "
                "read and discarded, against the same server%s. The "
                "server's own time is inside both of them, so the difference "
                "between these two lines is the HTTP client and nothing else."
                % (" on loopback" if cat["name"] == "apache-polaris"
                   else ", over the network, where the round trip is inside both")):
            w("  %s" % line)
        w("")
        lo, hi = p50_diff_interval(results[0][1], rust_floor)
        w("  transport gap      %+.1f us   95%% bootstrap interval [%+.1f, %+.1f]  %s"
          % (transport - r50, lo / 1000.0, hi / 1000.0,
             "separable" if lo > 0 or hi < 0 else "NO -- interval spans zero"))
        w("  pyiceberg's own    %+.1f us  (the client method above transport)"
          % (total - transport))
        if cat["name"] != "apache-polaris":
            w("")
            for line in _wrap(
                    "Caveat: the Rust floor is one block run after the Python "
                    "layers, not interleaved with them. On loopback the gap is "
                    "several times the noise and survives that. Over the network "
                    "a gap of a millisecond is within the drift of a round trip "
                    "between two blocks a minute apart, so the interval above "
                    "says the two blocks differed, not that the HTTP clients do. "
                    "bench.py interleaves the clients round by round and is the "
                    "measurement to read for that."):
                w("  %s" % line)
        w("")

    elif rust_floor_error:
        w("## The same GET through the other client's HTTP stack")
        w("")
        w("  not measured: the Rust floor stopped on %s" % rust_floor_error)
        w("")

    w("## What the library does on top, by cumulative time")
    w("")
    for line in profile_lines[:30]:
        w("  %s" % line)
    w("")

    w("## Startup, decomposed (milliseconds, p50 of 5)")
    w("")
    w("  %-40s %9.1f" % ("bare interpreter, `python3 -c pass`", bare))
    w("  %-40s %9.1f" % ("+ import pyiceberg.catalog.rest", imported))
    w("  %-40s %9.1f" % ("  of which, the import itself", imported - bare))
    w("  %-40s %9.1f" % ("catalog construction (config + auth)",
                         percentile(construct, 50) / 1e6))
    w("")
    for line in _wrap(
            "The benchmark's cold start figure is larger than these lines add "
            "up to because the worker imports more than the client: yaml, the "
            "conformance harness's auth provider and this directory's own "
            "modules are all on the path before a request is made. The point "
            "stands either way -- the dominant term is importing Python code, "
            "and it is paid before the client does anything."):
        w("  %s" % line)
    w("")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(HERE, "evidence",
                        "bench-breakdown-%s-%s.txt" % (cat["name"], stamp))
    text = "\n".join(line.rstrip() for line in out).rstrip() + "\n"
    text = redact.scrub(text, pairs)
    redact.verify({"text": text}, pairs)
    with open(path, "w") as fh:
        fh.write(text)
    # The samples beside the text, so every interval is re-derivable.
    with open(path.replace(".txt", ".samples.json"), "w") as fh:
        json.dump({"catalog": cat["name"], "unit": "ns",
                   "layers": {name: smp for name, smp in results},
                   "rust_transport_floor": rust_floor}, fh)
        fh.write("\n")
    print("wrote %s" % os.path.relpath(path, HERE))
    for line in out:
        print(line)


if __name__ == "__main__":
    main()
