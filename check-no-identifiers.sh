#!/usr/bin/env bash
# Independent residual grep over TRACKED files, run separately from
# anonymize_evidence.py's own scan.
#
# MEASURED 2026-09-04: a real GCP project id and project number sat in 8 tracked
# files, 33 hits of them inside evidence-public/, because the anonymiser had no
# pattern for either. Its residual scan checked GUIDs, 12-digit AWS accounts and
# emails only, so it reported clean. A scanner that only looks for what it knows
# cannot tell you about what it does not -- hence this second, dumber check
# against literal known-real values.
#
# Add a line per real value. Keep it out of anything published.
set -u
fail=0

# real value                      what it is
for pair in \
  "aisprint-491218|GCP project id" \
  "289270257791|GCP project number" \
  "xbill@glitnir.com|personal email" \
; do
  val="${pair%%|*}"; what="${pair##*|}"
  hits=$(git grep -c "$val" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "FAIL  $what ($val) is in tracked files:"
    echo "$hits" | sed 's/^/        /'
    fail=1
  else
    echo "ok    no $what in tracked files"
  fi
done

# Generic shapes, in case a new real value appears that no line above names.
for pat in 'projects/[0-9]\{6,\}' 'arn:aws:[a-z0-9-]*:[a-z0-9-]*:[0-9]\{12\}'; do
  hits=$(git grep -lE "$pat" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "FAIL  pattern $pat still present in:"; echo "$hits" | sed 's/^/        /'; fail=1
  fi
done

[ $fail -eq 0 ] && echo "clean" || echo "identifiers found -- do not push"
exit $fail
