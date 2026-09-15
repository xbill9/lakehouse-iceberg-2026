# a complete instrumented matrix run captured earlier on 2026-09-14, SUPERSEDED
# and kept. The article originally reported it. The whole pipeline was then run
# again from ground truth onwards, to check that the result replicates rather
# than to change one; the replication is in derived-figures.txt.

AXIS A
  A__gcp__apache-polaris__1.txt                   8.8s  correct  calls=3
  A__gcp__apache-polaris__2.txt                   8.6s  correct  calls=3
  A__gcp__apache-polaris__3.txt                   8.7s  correct  calls=3
  A__aws__apache-polaris__1.txt                   3.5s  correct  calls=3
  A__aws__apache-polaris__2.txt                   3.7s  correct  calls=3
  A__aws__apache-polaris__3.txt                   3.3s  correct  calls=3
  A__azure__apache-polaris__1.txt                15.5s  correct  calls=3
  A__azure__apache-polaris__2.txt                13.1s  correct  calls=3
  A__azure__apache-polaris__3.txt                14.6s  correct  calls=3

AXIS B
  B__gcp__apache-polaris__1.txt                   6.6s  correct  calls=3
  B__gcp__apache-polaris__2.txt                   7.1s  correct  calls=3
  B__gcp__apache-polaris__3.txt                  17.0s  correct  calls=3
  B__gcp__google-lakehouse__1.txt                 9.7s  correct  calls=3
  B__gcp__google-lakehouse__2.txt                10.9s  correct  calls=3
  B__gcp__google-lakehouse__3.txt                 8.7s  correct  calls=3
  B__gcp__aws-glue__1.txt                         9.1s  correct  calls=3
  B__gcp__aws-glue__2.txt                         7.9s  correct  calls=3
  B__gcp__aws-glue__3.txt                         8.6s  correct  calls=3
  B__gcp__aws-s3tables__1.txt                     9.1s  correct  calls=3
  B__gcp__aws-s3tables__2.txt                     7.7s  correct  calls=3
  B__gcp__aws-s3tables__3.txt                     9.0s  correct  calls=3
  B__gcp__microsoft-onelake__1.txt               10.0s  correct  calls=3
  B__gcp__microsoft-onelake__2.txt                8.7s  correct  calls=3
  B__gcp__microsoft-onelake__3.txt                9.8s  correct  calls=3
