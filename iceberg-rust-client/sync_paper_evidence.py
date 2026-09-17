#!/usr/bin/env python3
"""Copy each paper's evidence into its own directory, from a manifest.

    $ python3 sync_paper_evidence.py
    rust-client-seven-catalogs   4 file(s)
    two-iceberg-clients-cost     7 file(s)

The publishing kit's pre-flight anchors check-facts at `<article dir>/evidence`,
and it matches a claim on digits alone. Point it at everything and a figure
"traces" to a file that does not contain it: `13 of 25` traced to a benchmark
JSON whose samples merely contain those digits, and paper 3 ran against 1450
files, which is the condition that produces exactly that.

So each paper carries only the artifacts it cites, listed here rather than
copied by hand, and a missing one fails the run instead of quietly shrinking
the evidence set.

Deliberately excluded: bench-breakdown-*.invalid.txt. It is a real artifact of
a real mistake and it stays in this directory, but a known-wrong file in an
evidence set can back a claim by digit coincidence, which is the same failure
this script exists to prevent.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
PAPERS = os.path.join(HERE, os.pardir, "papers")

MANIFEST = {
    "rust-client-seven-catalogs": [
        "third-party-figures.txt",
        "versions.txt",
        "rust-client-operation-surface.txt",
        "rust-client-auth-surface.txt",
        "rust-run-apache-polaris.json",
        "declaration-gate-cost.txt",
    ],
    "two-iceberg-clients-cost": [
        "third-party-figures.txt",
        "versions.txt",
        "bench-comparison.txt",
        "client-comparison.txt",
        "declaration-gate-cost.txt",
        "pyiceberg-client-operation-surface.txt",
        "pyiceberg-run-apache-polaris.json",
        "rust-client-operation-surface.txt",
    ],
}

# Globs, for the artifacts that accumulate one file per run.
GLOBS = {
    "two-iceberg-clients-cost": ["bench-breakdown-apache-polaris-*.txt"],
}

# Also deliberately excluded: bench-<catalog>-<ts>.json, the per-run sample
# arrays. MEASURED 2026-09-17 -- with them in the set, every claim in paper 6's
# plan "traced", including `13 of 25` and `21 of 25`, which appear in no
# benchmark file at all: 720 nanosecond samples contain every short digit
# sequence. They stay in iceberg-rust-client/evidence/, committed and published,
# so figures remain re-derivable; the paper cites bench-comparison.txt, which
# carries the rendered numbers and is checkable by eye.

EXCLUDE_SUFFIX = (".invalid.txt",)


def main():
    import glob
    failed = False
    for paper, names in MANIFEST.items():
        out = os.path.join(PAPERS, paper, "evidence")
        wanted = list(names)
        for pattern in GLOBS.get(paper, []):
            for path in sorted(glob.glob(os.path.join(EV, pattern))):
                base = os.path.basename(path)
                if not base.endswith(EXCLUDE_SUFFIX):
                    wanted.append(base)

        missing = [n for n in wanted if not os.path.exists(os.path.join(EV, n))]
        if missing:
            print("%-28s MISSING %s" % (paper, ", ".join(missing)))
            failed = True
            continue

        os.makedirs(out, exist_ok=True)
        # Drop anything no longer in the manifest, so a renamed artifact cannot
        # linger and keep tracing claims that nothing produces any more.
        for stale in os.listdir(out):
            if stale not in wanted:
                os.remove(os.path.join(out, stale))
                print("%-28s removed stale %s" % (paper, stale))
        for name in wanted:
            shutil.copy2(os.path.join(EV, name), os.path.join(out, name))
        print("%-28s %d file(s)" % (paper, len(wanted)))

    if failed:
        sys.exit("manifest names an artifact that does not exist")


if __name__ == "__main__":
    main()
