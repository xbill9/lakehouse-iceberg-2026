# Axis D's first run, captured 2026-09-15, SUPERSEDED and kept.
# Instruction v2 told every agent that iceberg_scan_table returns a sample and
# must never be counted, and the scan tool never said when it had returned the
# whole table. Two of three ADK runs declined to scan at all, and every answer
# that did scan hedged 'based on a sample', although each scan had returned
# every row. That is this harness's wording, not a framework's behaviour, so
# the instruction (v3) and the scan tool's output were changed and the axis was
# re-run. Re-scored below under the current scorer, not changed.

  capture                                  max id count  snapshot  calls  answer s
  D__gcp__google-lakehouse__1.txt          WRONG  WRONG  ok        3      23.72
  D__gcp__google-lakehouse__2.txt          ok     ok     ok        3      19.10
  D__gcp__google-lakehouse__3.txt          WRONG  WRONG  ok        2      22.15
  D__aws__aws-glue__1.txt                  ok     WRONG  ok        3      5.94
  D__aws__aws-glue__2.txt                  WRONG  WRONG  ok        5      8.31
  D__aws__aws-glue__3.txt                  ok     WRONG  ok        4      6.00
  D__azure__microsoft-onelake__1.txt       ok     ok     ok        4      26.79
  D__azure__microsoft-onelake__2.txt       ok     ok     ok        4      33.08
  D__azure__microsoft-onelake__3.txt       ok     ok     ok        4      36.11
