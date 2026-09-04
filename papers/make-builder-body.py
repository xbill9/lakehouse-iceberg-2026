#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emit the Builder Center body with the title and subtitle lines removed.

`make-builder.py` carries the title and subtitle as the first lines of its
output so they survive as text. Builder Center has its own Title and
Description fields, so pasting those lines into the body duplicates them.

Stripping them in the browser after pasting does not work: the editor accepts a
synthetic paste but ignores programmatic selection and `execCommand('delete')`,
so a second paste appends rather than replaces and the article ends up twice.
The fix is to paste the right bytes once, which means stripping here.

    python3 make-builder-body.py <builder-file>.md
"""
import sys

def strip(text: str) -> str:
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("# ")
                              or lines[i].startswith("*Subtitle:")
                              or not lines[i].strip()):
        i += 1
    return "\n".join(lines[i:])

if __name__ == "__main__":
    src = sys.argv[1]
    out = src.replace("builder-", "builder-body-", 1)
    body = strip(open(src).read())
    open(out, "w").write(body)
    print("%s -> %s  (%d chars, %d lines)" % (src, out, len(body), body.count("\n") + 1))
