#!/usr/bin/env python3
"""What the three Rust catalog crates implement, method by method.

    $ python3 aws_catalog_crates.py
    wrote evidence/rust-catalog-crates.txt   3 crates, 15 trait methods

A Rust program that wants all seven catalogs cannot use one client: the REST
crate has no SigV4 signer, so Glue and S3 Tables are reached through
iceberg-catalog-glue and iceberg-catalog-s3tables instead. All three implement
the same `Catalog` trait, so the swap is a dependency change rather than a
rewrite -- and what changes underneath is the set of operations that answer.

This reads each crate's `impl Catalog for` block from the installed source and
records, per method, whether the body returns FeatureUnsupported and with what
message. It refuses to write if a crate is missing or its impl block cannot be
found, because an empty parse and a crate with nothing unsupported produce the
same table.
"""

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "evidence", "rust-catalog-crates.txt")

CRATES = [
    ("iceberg-catalog-rest", "0.10.1", "catalog.rs"),
    ("iceberg-catalog-glue", "0.10.1", "catalog.rs"),
    ("iceberg-catalog-s3tables", "0.10.1", "catalog.rs"),
]

SHORT = {"iceberg-catalog-rest": "rest",
         "iceberg-catalog-glue": "glue",
         "iceberg-catalog-s3tables": "s3tables"}


def crate_src(name, version):
    found = sorted(glob.glob(os.path.expanduser(
        "~/.cargo/registry/src/*/%s-%s/src" % (name, version))))
    if not found:
        raise SystemExit("crate source not installed: %s %s" % (name, version))
    return found[-1]


def impl_block(text):
    """The `impl Catalog for X { ... }` block, ending at a `}` in column 0."""
    m = re.search(r"^impl Catalog for .*?\{$", text, re.M)
    if not m:
        return None
    rest = text[m.end():]
    end = re.search(r"^\}", rest, re.M)
    return rest[:end.start()] if end else None


def methods(block):
    """Each trait method, with its FeatureUnsupported message if it has one."""
    out = []
    parts = re.split(r"\n    (?:async )?fn ", "\n" + block)
    for part in parts[1:]:
        name = part.split("(")[0].strip()
        msg = None
        m = re.search(r"ErrorKind::FeatureUnsupported,\s*\n\s*\"([^\"]+)\"",
                      part)
        if m:
            msg = m.group(1)
        out.append((name, msg))
    return out


def main():
    tables, problems = {}, []
    for name, version, filename in CRATES:
        path = os.path.join(crate_src(name, version), filename)
        if not os.path.exists(path):
            problems.append("no such file: %s" % path)
            continue
        with open(path, encoding="utf-8") as fh:
            block = impl_block(fh.read())
        if not block:
            problems.append("no `impl Catalog for` block in %s" % path)
            continue
        found = methods(block)
        if not found:
            problems.append("no trait methods parsed from %s" % path)
            continue
        tables[name] = dict(found)

    if problems:
        for p in problems:
            sys.stderr.write("FAIL  %s\n" % p)
        raise SystemExit("refusing to write %s" % os.path.relpath(OUT, HERE))

    names = [n for n, _v, _f in CRATES]
    every = []
    for n in names:
        for m in tables[n]:
            if m not in every:
                every.append(m)

    out = []
    out.append("The three Rust catalog crates of the Apache Iceberg project,")
    out.append("method by method. Written by aws_catalog_crates.py from the")
    out.append("installed crate sources.")
    out.append("")
    out.append("Reading: a method absent from a crate's `impl Catalog for`")
    out.append("block is `--`; one whose body returns FeatureUnsupported is")
    out.append("`refused`, with its message below the table.")
    out.append("")
    out.append("  %-24s %-10s %-10s %s"
               % ("Catalog trait method", *[SHORT[n] for n in names]))
    for m in every:
        row = []
        for n in names:
            if m not in tables[n]:
                row.append("--")
            elif tables[n][m] is None:
                row.append("sent")
            else:
                row.append("refused")
        out.append("  %-24s %-10s %-10s %s" % (m, *row))
    out.append("")

    out.append("## What each refusal says")
    out.append("")
    for n in names:
        for m, msg in sorted(tables[n].items()):
            if msg:
                out.append("  %-10s %-24s %s" % (SHORT[n], m, repr(msg)))
    out.append("")
    out.append("## Crates read")
    out.append("")
    home = os.path.expanduser("~")
    for name, version, _f in CRATES:
        src = crate_src(name, version)
        out.append("  %-26s %-8s %s"
                   % (name, version,
                      "~" + src[len(home):] if src.startswith(home) else src))

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")
    print("wrote %s   %d crates, %d trait methods"
          % (os.path.relpath(OUT, HERE), len(tables), len(every)))


if __name__ == "__main__":
    main()
