# a complete matrix run captured earlier on 2026-09-14, SUPERSEDED and kept.
# It was run before the tools recorded where an answer's time went. Two of its
# Axis B runs were far slower than the rest (google-lakehouse run 3, onelake
# run 2) with nothing in their captures to attribute the time to, so both axes
# were re-run, instrumented. It was not re-run to change a result.

AXIS A
  A__gcp__apache-polaris__1.txt                   8.1s  correct  calls=3
  A__gcp__apache-polaris__2.txt                   9.5s  correct  calls=3
  A__gcp__apache-polaris__3.txt                  10.5s  correct  calls=3
  A__aws__apache-polaris__1.txt                   4.2s  correct  calls=3
  A__aws__apache-polaris__2.txt                   4.1s  correct  calls=3
  A__aws__apache-polaris__3.txt                   4.1s  correct  calls=3
  A__azure__apache-polaris__1.txt                15.7s  correct  calls=3
  A__azure__apache-polaris__2.txt                14.4s  correct  calls=3
  A__azure__apache-polaris__3.txt                15.6s  correct  calls=3

AXIS B
  B__gcp__apache-polaris__1.txt                   9.1s  correct  calls=3
  B__gcp__apache-polaris__2.txt                   8.9s  correct  calls=3
  B__gcp__apache-polaris__3.txt                   9.5s  correct  calls=3
  B__gcp__google-lakehouse__1.txt                11.0s  correct  calls=3
  B__gcp__google-lakehouse__2.txt                 9.7s  correct  calls=3
  B__gcp__google-lakehouse__3.txt                21.8s  correct  calls=3
  B__gcp__aws-glue__1.txt                         9.3s  correct  calls=3
  B__gcp__aws-glue__2.txt                         9.0s  correct  calls=3
  B__gcp__aws-glue__3.txt                         9.4s  correct  calls=3
  B__gcp__aws-s3tables__1.txt                     9.7s  correct  calls=3
  B__gcp__aws-s3tables__2.txt                     9.4s  correct  calls=3
  B__gcp__aws-s3tables__3.txt                     9.4s  correct  calls=3
  B__gcp__microsoft-onelake__1.txt               13.2s  correct  calls=3
  B__gcp__microsoft-onelake__2.txt               32.3s  correct  calls=3
  B__gcp__microsoft-onelake__3.txt               10.0s  correct  calls=3
