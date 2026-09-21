#!/usr/bin/env python3
"""Archive every source line a paper cites outside the two operation maps.

    $ python3 source_citations.py
    wrote evidence/rust-source-citations.txt   7 citation(s), 1 grep

check_refs.py resolves the file:line references that live inside
operation_map.py and pyiceberg_map.py. The prose cites seven more lines -- the
credential split, the update_namespace stub, the two storage factories, the
azdls signer context -- and those were read by hand and never written down, so
a reader held a line number with no way to check it.

Each citation here carries the text the line must contain. A line that moves
fails the run rather than printing a quietly wrong quotation, which is the same
job check_refs.py does for the maps.
"""

import glob
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "evidence", "rust-source-citations.txt")

CRATES = {
    "iceberg-catalog-rest": "0.10.1",
    "iceberg": "0.10.1",
    "opendal-service-azdls": "0.57.0",
}

# crate, file inside src/, line, what the paper says about it, text the line
# must contain.
CITATIONS = [
    ("iceberg-catalog-rest", "catalog.rs", 238,
     "a `credential` with no colon is sent as client_secret with no client_id,"
     " which is the shape Horizon wants",
     "fn credential"),
    ("iceberg-catalog-rest", "catalog.rs", 455,
     "load_file_io copies the response's `config` settings and nothing else,"
     " so a vended storage credential is never read",
     "config.props.clone()"),
    ("iceberg-catalog-rest", "catalog.rs", 659,
     "update_namespace compiles and returns FeatureUnsupported without"
     " sending a request",
     "Updating namespace not supported yet!"),
    ("iceberg-catalog-rest", "types.rs", 226,
     "the response type models storage credentials, so the client receives"
     " them and discards them",
     "storage_credentials"),
    ("iceberg", "io/storage/local_fs.rs", 330,
     "one of the two storage factories the core crate ships",
     "StorageFactory for LocalFsStorageFactory"),
    ("iceberg", "io/storage/memory.rs", 250,
     "the other one; every cloud backend lives in iceberg-storage-opendal",
     "StorageFactory for MemoryStorageFactory"),
    ("opendal-service-azdls", "backend.rs", 297,
     "the signer context is built with no command executor, so the chain's"
     " Azure CLI provider cannot run",
     "Context::new()"),
]

# (crate, pattern, what its absence supports)
GREPS = [
    ("opendal-service-azdls", "with_command_execute",
     "nothing in the crate gives the context a command executor"),
]

CONTEXT = 3


def crate_root(name):
    version = CRATES[name]
    found = sorted(glob.glob(os.path.expanduser(
        "~/.cargo/registry/src/*/%s-%s/src" % (name, version))))
    if not found:
        raise SystemExit("crate source not installed: %s %s" % (name, version))
    return found[-1]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def main():
    out, problems, roots = [], [], {}
    out.append("# Source lines cited in the prose of papers 5 and 6, quoted"
               " verbatim.")
    out.append("# Written by source_citations.py from the installed crate"
               " sources.")
    out.append("#")
    out.append("# The file:line references inside operation_map.py and"
               " pyiceberg_map.py are")
    out.append("# checked by check_refs.py instead. These are the ones the"
               " prose cites directly.")
    out.append("")

    for name in sorted(CRATES):
        roots[name] = crate_root(name)
    out.append("## Crates read")
    out.append("")
    home = os.path.expanduser("~")
    for name in sorted(CRATES):
        shown = roots[name]
        if shown.startswith(home):
            shown = "~" + shown[len(home):]
        out.append("  %-24s %-8s %s" % (name, CRATES[name], shown))
    out.append("")

    out.append("## Citations")
    out.append("")
    for crate, filename, lineno, claim, expect in CITATIONS:
        path = os.path.join(roots[crate], filename)
        if not os.path.exists(path):
            problems.append("no such file: %s" % path)
            continue
        lines = read(path)
        digest = hashlib.sha256(
            open(path, "rb").read()).hexdigest()[:12]
        if not 1 <= lineno <= len(lines):
            problems.append("%s:%d is past the end of the file (%d lines)"
                            % (filename, lineno, len(lines)))
            continue
        if expect not in lines[lineno - 1]:
            problems.append("%s:%d no longer contains %r; it reads %r"
                            % (filename, lineno, expect,
                               lines[lineno - 1].strip()))
            continue
        out.append("  %s %s:%d   [%s %s]"
                   % (crate, filename, lineno, filename.split("/")[-1],
                      digest))
        out.append("      %s" % claim)
        out.append("")
        lo = max(1, lineno - CONTEXT)
        hi = min(len(lines), lineno + CONTEXT)
        for n in range(lo, hi + 1):
            mark = "->" if n == lineno else "  "
            out.append("      %s %5d  %s" % (mark, n, lines[n - 1].rstrip()))
        out.append("")

    if GREPS:
        out.append("## Greps, quoted with their result")
        out.append("")
        for crate, pattern, claim in GREPS:
            root = roots[crate]
            proc = subprocess.run(["grep", "-rn", pattern, root],
                                  capture_output=True, text=True)
            hits = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            out.append("  $ grep -rn %s <%s %s>/src"
                       % (pattern, crate, CRATES[crate]))
            hits = [ln.replace(os.path.expanduser("~"), "~") for ln in hits]
            if hits:
                for ln in hits:
                    out.append("  %s" % ln.replace(root, ""))
                problems.append("%s: %r now matches in %s; the paper says it"
                                " does not appear"
                                % (crate, pattern, root))
            else:
                out.append("  (no matches)")
            out.append("      %s" % claim)
            out.append("")

    if problems:
        for p in problems:
            sys.stderr.write("FAIL  %s\n" % p)
        raise SystemExit("refusing to write %s" % os.path.relpath(OUT, HERE))

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")
    print("wrote %s   %d citation(s), %d grep"
          % (os.path.relpath(OUT, HERE), len(CITATIONS), len(GREPS)))


if __name__ == "__main__":
    main()
