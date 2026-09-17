#!/usr/bin/env python3
"""Check every file:line in both operation maps against the source it names.

    $ python3 check_refs.py
    rust       iceberg-catalog-rest 0.10.1   33 refs, 24 symbol refs resolved
    pyiceberg  pyiceberg 0.12.0              37 refs, 29 symbol refs resolved
    ok  every cited line is inside the symbol it is cited for

The maps are hand-read, and a hand-read line number is exactly the kind of
claim that rots without saying so: upgrade either client and every reference in
the paper is silently off by a few lines. This resolves each one against the
installed source and fails if the line is not inside the function the map names
it for.

It cannot check that the *reading* was right. It checks that the reading still
points where it pointed.
"""

import glob
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import operation_map as rust                         # noqa: E402
import pyiceberg_map as py                           # noqa: E402

CRATE_GLOB = os.path.expanduser(
    "~/.cargo/registry/src/*/iceberg-catalog-rest-0.10.1/src")
INLINE_REF = re.compile(r"\(:(\d+)(?:-(\d+))?\)")


def crate_root():
    found = sorted(glob.glob(CRATE_GLOB))
    return found[-1] if found else None


def py_root():
    import pyiceberg.catalog.rest as mod
    return os.path.dirname(mod.__file__)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def enclosing(lines, lineno, pattern):
    """The nearest definition at or above `lineno`, by that language's syntax."""
    for i in range(min(lineno, len(lines)) - 1, -1, -1):
        m = pattern.search(lines[i])
        if m:
            return m.group(1)
    return None


class Source(object):
    def __init__(self, root, default_file, pattern, alias=None):
        self.root = root
        self.default_file = default_file
        self.pattern = pattern
        self.alias = alias or {}
        self.cache = {}

    def lines(self, filename):
        filename = self.alias.get(filename, filename)
        if filename not in self.cache:
            path = os.path.join(self.root, filename)
            if not os.path.exists(path):
                raise SystemExit("no such source file: %s" % path)
            self.cache[filename] = read(path)
        return self.cache[filename]

    def split(self, ref):
        """'catalog.rs:426', 'rest:1083' or 'catalog.rs:493, 503'.

        Returns (filename, [lineno, ...]). A map entry may cite more than one
        line for one symbol, and each of them is checked.
        """
        name, _, linenos = ref.rpartition(":")
        return ((name or self.default_file),
                [int(n) for n in linenos.replace(",", " ").split()])


def check(label, client, source, refs_in_file):
    lines_checked, symbol_refs, problems = 0, 0, []

    def visit(symbol, ref):
        nonlocal lines_checked, symbol_refs
        if not ref or ":" not in ref:
            return                                   # "grep, no match"
        filename, linenos = source.split(ref)
        lines = source.lines(filename)
        # An entry may name more than one symbol, e.g. a pair of methods that
        # are one capability. Any of them satisfies the line.
        wanted = {part.replace("::", ".").strip().rsplit(".", 1)[-1]
                  for part in (symbol or "").split("/") if part.strip()}
        for lineno in linenos:
            lines_checked += 1
            if not 1 <= lineno <= len(lines):
                problems.append("%s: line %d is past the end of %s (%d lines)"
                                % (symbol or ref, lineno, filename, len(lines)))
                continue
            if not wanted:
                continue
            symbol_refs += 1
            found = enclosing(lines, lineno, source.pattern)
            if found not in wanted:
                problems.append("%s (%s): line %d is inside %r, not %s"
                                % (symbol, ref, lineno, found,
                                   " or ".join(sorted(repr(x) for x in wanted))))

    for probe_id, row in client.MAP.items():
        visit(row[1], row[2])
    for name, symbol, ref, _note in client.BEYOND_THE_SWEEP:
        visit(symbol, ref)

    # Inline (:NNNN) references inside the notes. The enclosing symbol is not
    # named there, so only the line's existence is checked.
    text = open(refs_in_file, encoding="utf-8").read()
    for m in INLINE_REF.finditer(text):
        for group in (m.group(1), m.group(2)):
            if group:
                lines = source.lines(source.default_file)
                lines_checked += 1
                if not 1 <= int(group) <= len(lines):
                    problems.append("inline (:%s) is past the end of %s"
                                    % (group, source.default_file))

    digest = hashlib.sha256(
        "\n".join(source.lines(source.default_file)).encode()).hexdigest()[:12]
    print("%-10s %-30s %2d refs, %2d symbol refs resolved  [%s %s]"
          % (label, getattr(client, "CRATE", None) or client.CLIENT,
             lines_checked, symbol_refs, source.default_file, digest))
    return problems


def main():
    problems = []

    root = crate_root()
    if root:
        problems += check(
            "rust", rust,
            Source(root, "catalog.rs", re.compile(r"\bfn\s+([A-Za-z_][\w]*)")),
            os.path.join(HERE, "operation_map.py"))
    else:
        print("rust       skipped: crate source not in the cargo registry")

    problems += check(
        "pyiceberg", py,
        Source(py_root(), "__init__.py",
               re.compile(r"\bdef\s+([A-Za-z_][\w]*)"),
               alias={"rest": "__init__.py"}),
        os.path.join(HERE, "pyiceberg_map.py"))

    if problems:
        for p in problems:
            print("  drift  %s" % p)
        sys.exit("%d reference(s) no longer point where the map says" % len(problems))
    print("ok  every cited line is inside the symbol it is cited for")


if __name__ == "__main__":
    main()
