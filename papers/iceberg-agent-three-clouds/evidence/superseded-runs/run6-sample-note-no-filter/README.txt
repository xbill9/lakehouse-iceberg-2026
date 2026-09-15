# a complete run at ten repeats per cell, Axes A to E, captured 2026-09-15,
# SUPERSEDED and kept. Its scan tool added a SAMPLE note whenever a model asked
# for more than 100 rows, beside the COMPLETE line of an 11-row table, and had
# no filter, so a filtered count was arithmetic the model did in its head.
# Nova Micro, given the agent's instruction and every row, gave the count right
# in 1 of 20 direct calls.
# The Strands runner also scored only the last assistant message, where ADK's
# and Agent Framework's runners took every message of the turn; Nova named the
# columns in an earlier message. The scan now filters in the engine and returns
# an exact COUNT, MIN and MAX, the Strands runner takes the whole turn, Nova runs
# with Amazon's documented tool-use decoding, and every axis was re-run.
# nova-diagnosis.txt has the measurements. Re-scored below, not changed.

AXIS A
  A__aws__apache-polaris__1.txt                   3.4s  WRONG  calls=3
  A__gcp__apache-polaris__1.txt                   6.7s  correct  calls=3
  A__azure__apache-polaris__1.txt                13.2s  correct  calls=3
  A__aws__apache-polaris__2.txt                   3.4s  correct  calls=3
  A__gcp__apache-polaris__2.txt                   5.2s  correct  calls=3
  A__azure__apache-polaris__2.txt                15.2s  correct  calls=3
  A__azure__apache-polaris__3.txt                13.7s  correct  calls=3
  A__aws__apache-polaris__3.txt                   2.8s  correct  calls=3
  A__gcp__apache-polaris__3.txt                   5.6s  correct  calls=3
  A__aws__apache-polaris__4.txt                   3.4s  correct  calls=3
  A__gcp__apache-polaris__4.txt                   5.0s  correct  calls=3
  A__azure__apache-polaris__4.txt                11.4s  correct  calls=3
  A__gcp__apache-polaris__5.txt                   4.5s  correct  calls=3
  A__azure__apache-polaris__5.txt                12.6s  correct  calls=3
  A__aws__apache-polaris__5.txt                   3.5s  correct  calls=3
  A__azure__apache-polaris__6.txt                11.9s  correct  calls=3
  A__aws__apache-polaris__6.txt                   3.0s  correct  calls=3
  A__gcp__apache-polaris__6.txt                   4.6s  correct  calls=3
  A__aws__apache-polaris__7.txt                   2.9s  correct  calls=3
  A__gcp__apache-polaris__7.txt                   6.0s  correct  calls=3
  A__azure__apache-polaris__7.txt                14.0s  correct  calls=3
  A__aws__apache-polaris__8.txt                   3.2s  correct  calls=3
  A__azure__apache-polaris__8.txt                14.8s  correct  calls=3
  A__gcp__apache-polaris__8.txt                   6.5s  correct  calls=3
  A__aws__apache-polaris__9.txt                   3.2s  correct  calls=3
  A__azure__apache-polaris__9.txt                12.5s  correct  calls=3
  A__gcp__apache-polaris__9.txt                   5.2s  correct  calls=3
  A__azure__apache-polaris__10.txt               13.3s  correct  calls=3
  A__aws__apache-polaris__10.txt                  3.3s  correct  calls=3
  A__gcp__apache-polaris__10.txt                  4.7s  correct  calls=3

AXIS B
  B__gcp__google-lakehouse__1.txt                 8.1s  correct  calls=3
  B__gcp__aws-s3tables__1.txt                     5.8s  correct  calls=3
  B__gcp__aws-glue__1.txt                         7.2s  correct  calls=3
  B__gcp__apache-polaris__1.txt                   5.7s  correct  calls=3
  B__gcp__microsoft-onelake__1.txt                7.7s  correct  calls=3
  B__gcp__google-lakehouse__2.txt                 7.0s  correct  calls=3
  B__gcp__microsoft-onelake__2.txt                7.2s  correct  calls=3
  B__gcp__aws-s3tables__2.txt                     6.2s  correct  calls=3
  B__gcp__aws-glue__2.txt                         5.9s  correct  calls=3
  B__gcp__apache-polaris__2.txt                   4.8s  correct  calls=3
  B__gcp__microsoft-onelake__3.txt                7.6s  correct  calls=3
  B__gcp__google-lakehouse__3.txt                 6.4s  correct  calls=3
  B__gcp__apache-polaris__3.txt                   5.7s  correct  calls=3
  B__gcp__aws-glue__3.txt                         6.6s  correct  calls=3
  B__gcp__aws-s3tables__3.txt                     6.6s  correct  calls=3
  B__gcp__microsoft-onelake__4.txt                7.5s  correct  calls=3
  B__gcp__aws-glue__4.txt                         6.5s  correct  calls=3
  B__gcp__aws-s3tables__4.txt                     5.9s  correct  calls=3
  B__gcp__apache-polaris__4.txt                   7.4s  correct  calls=3
  B__gcp__google-lakehouse__4.txt                 6.6s  correct  calls=3
  B__gcp__aws-glue__5.txt                         6.0s  correct  calls=3
  B__gcp__apache-polaris__5.txt                   4.8s  correct  calls=3
  B__gcp__aws-s3tables__5.txt                     6.8s  correct  calls=3
  B__gcp__microsoft-onelake__5.txt                6.8s  correct  calls=3
  B__gcp__google-lakehouse__5.txt                 7.4s  correct  calls=3
  B__gcp__microsoft-onelake__6.txt               16.9s  correct  calls=3
  B__gcp__apache-polaris__6.txt                   6.4s  correct  calls=3
  B__gcp__google-lakehouse__6.txt                 8.2s  correct  calls=3
  B__gcp__aws-s3tables__6.txt                     6.2s  correct  calls=3
  B__gcp__aws-glue__6.txt                         6.3s  correct  calls=3
  B__gcp__microsoft-onelake__7.txt                8.0s  correct  calls=3
  B__gcp__aws-glue__7.txt                         5.9s  correct  calls=3
  B__gcp__google-lakehouse__7.txt                 7.5s  correct  calls=3
  B__gcp__apache-polaris__7.txt                   5.9s  correct  calls=3
  B__gcp__aws-s3tables__7.txt                     7.0s  correct  calls=3
  B__gcp__apache-polaris__8.txt                   5.3s  correct  calls=3
  B__gcp__microsoft-onelake__8.txt                8.1s  correct  calls=3
  B__gcp__aws-s3tables__8.txt                     6.6s  correct  calls=3
  B__gcp__aws-glue__8.txt                         6.6s  correct  calls=3
  B__gcp__google-lakehouse__8.txt                 7.4s  correct  calls=3
  B__gcp__aws-s3tables__9.txt                     6.0s  correct  calls=3
  B__gcp__microsoft-onelake__9.txt                6.4s  correct  calls=3
  B__gcp__apache-polaris__9.txt                   5.6s  correct  calls=3
  B__gcp__aws-glue__9.txt                         6.3s  correct  calls=3
  B__gcp__google-lakehouse__9.txt                 6.8s  correct  calls=3
  B__gcp__aws-glue__10.txt                        6.5s  correct  calls=3
  B__gcp__apache-polaris__10.txt                  5.3s  correct  calls=3
  B__gcp__microsoft-onelake__10.txt               7.0s  correct  calls=3
  B__gcp__google-lakehouse__10.txt                7.4s  correct  calls=3
  B__gcp__aws-s3tables__10.txt                    5.5s  correct  calls=3

AXIS C
  C__aws__gemini-2.5-flash__apache-polaris__1.txt  11.5s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__1.txt   5.7s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__1.txt   4.6s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__2.txt   6.8s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__2.txt   4.9s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__2.txt   3.1s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__3.txt   4.6s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__3.txt   9.4s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__3.txt   6.8s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__4.txt   6.7s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__4.txt   4.9s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__4.txt   3.0s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__5.txt   7.0s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__5.txt   3.2s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__5.txt  10.9s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__6.txt   3.1s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__6.txt   7.4s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__6.txt   6.2s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__7.txt   8.9s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__7.txt   6.2s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__7.txt   3.5s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__8.txt   8.7s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__8.txt   3.0s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__8.txt   7.3s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__9.txt   6.6s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__9.txt   3.4s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__9.txt   6.3s  correct  calls=3
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__10.txt   3.2s  correct  calls=3
  C__aws__gemini-2.5-flash__apache-polaris__10.txt   8.8s  correct  calls=3
  C__gcp__gemini-2.5-flash__apache-polaris__10.txt   5.9s  correct  calls=3
