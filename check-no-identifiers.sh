#!/usr/bin/env bash
# Independent residual grep over every file git would publish -- tracked,
# staged, and untracked-but-not-ignored -- run separately from
# anonymize_evidence.py's own scan.
#
# MEASURED 2026-09-04: a real GCP project id and project number sat in 8 tracked
# files, 33 hits of them inside evidence-public/, because the anonymiser had no
# pattern for either. Its residual scan checked GUIDs, 12-digit AWS accounts and
# emails only, so it reported clean. A scanner that only looks for what it knows
# cannot tell you about what it does not -- hence this second, dumber check
# against literal known-real values.
#
# MEASURED 2026-09-04: the first version searched tracked files only, via a
# bare `git grep`. That is the wrong set. A brand new file is untracked until
# it is staged, so running this before `git add` -- the natural order, and the
# order the instructions gave -- scanned everything except the files most
# likely to carry a fresh identifier. `--untracked` widens the search to what
# is actually about to be committed. Ignored paths stay excluded, which is
# deliberate: catalogs.yaml, .secrets/ and evidence/ hold real values on
# purpose and are never published.
#
# Add a line per real value. Keep it out of anything published.
set -u
fail=0

# Values are read from .known-identifiers, which is gitignored. They are NOT
# inline here: this script is tracked, so a literal would put the very value it
# is checking for into the repo. That happened -- the first version of this file
# carried the email and the check failed on itself, after the push.
LIST=".known-identifiers"
if [ ! -f "$LIST" ]; then
  echo "FAIL  $LIST is missing; cannot check. Copy it from a machine that has it."
  exit 1
fi

while IFS='|' read -r val what; do
  case "$val" in ''|\#*) continue ;; esac
  hits=$(git grep --untracked -c -- "$val" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "FAIL  $what is in files about to be committed:"
    echo "$hits" | sed 's/^/        /'
    fail=1
  else
    echo "ok    no $what in tracked, staged or new files"
  fi
done < "$LIST"

# Generic shapes, in case a new real value appears that no line above names.
#
# MEASURED 2026-09-04: these were written with BRE braces -- [0-9]\{6,\} -- and
# passed to `grep -E`, where a backslashed brace is a literal brace. Both
# patterns had therefore never matched anything since the day they were added,
# including the project number they were added for. A safety net that cannot
# fail is indistinguishable from one that is working; this half was the former.
# Verified after the fix by grepping a file that contains both shapes.
for pat in 'projects/[0-9]{6,}' 'arn:aws:[a-z0-9-]*:[a-z0-9-]*:[0-9]{12}'; do
  hits=$(git grep --untracked -lE "$pat" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "FAIL  pattern $pat still present in:"; echo "$hits" | sed 's/^/        /'; fail=1
  fi
done

[ $fail -eq 0 ] && echo "clean" || echo "identifiers found -- do not push"
exit $fail
