#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emit the Builder Center body: title and subtitle removed, paragraphs unwrapped.

`make-builder.py` carries the title and subtitle as the first lines of its
output so they survive as text. Builder Center has its own Title and
Description fields, so pasting those lines into the body duplicates them.

Stripping them in the browser after pasting does not work: the editor accepts a
synthetic paste but ignores programmatic selection and `execCommand('delete')`,
so a second paste appends rather than replaces and the article ends up twice.
The fix is to paste the right bytes once, which means stripping them here.

The bodies are hard-wrapped at 80 columns, and Builder Center's contenteditable
preserves every one of those wraps as a line break -- so a 60-paragraph article
arrives as ~370 separate blocks with the sentences shredded across them. Joining
each paragraph back into one line is what `references/browser-publishing.md` in
the publishing kit requires, and it is also what keeps the document model small
enough for the editor to save. Blank lines, headings, table rows, list items,
block quotes and fenced code all keep their own lines.

    python3 make-builder-body.py <builder-file>.md
"""
import re
import sys

#: Lines that carry their own meaning at line granularity. Joining any of these
#: into the paragraph above changes what the markdown means, so each one ends
#: the paragraph it follows and stands alone.
STANDALONE = re.compile(r"""^(
      \s*$                   # blank
    | \#{1,6}\s              # heading
    | \|                     # table row or separator
    | \s*([-*+]|\d+[.)])\s   # list item
    | >                      # block quote
    | \s{4,}\S               # indented code
    | (---|\*\*\*|___)\s*$   # thematic break
)""", re.VERBOSE)

FENCE = re.compile(r"^\s*(```|~~~)")


def strip(text: str) -> str:
    """Drop the leading title and subtitle lines."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("# ")
                              or lines[i].startswith("*Subtitle:")
                              or not lines[i].strip()):
        i += 1
    return "\n".join(lines[i:])


def unwrap(text: str) -> str:
    """Join each hard-wrapped paragraph into a single line.

    Everything inside a fenced code block is copied through untouched, wraps
    included: a line break there is content, not formatting.
    """
    out, para, in_fence = [], [], False

    def flush():
        if para:
            out.append(" ".join(line.strip() for line in para))
            para.clear()

    for line in text.split("\n"):
        if FENCE.match(line):
            flush()
            in_fence = not in_fence
            out.append(line)
        elif in_fence:
            out.append(line)
        elif STANDALONE.match(line):
            flush()
            out.append(line)
        else:
            para.append(line)
    flush()
    return "\n".join(out)


if __name__ == "__main__":
    src = sys.argv[1]
    out = src.replace("builder-", "builder-body-", 1)
    body = unwrap(strip(open(src).read()))
    open(out, "w").write(body)
    longest = max(len(line) for line in body.split("\n"))
    print("%s -> %s  (%d chars, %d lines, longest %d)"
          % (src, out, len(body), body.count("\n") + 1, longest))
