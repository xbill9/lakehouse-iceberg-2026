# Axes A, C, D, E and F, captured 2026-09-15, SUPERSEDED and kept. Their answers
# carry Nova Micro's <thinking> text, because the runner returned model output as
# it arrived: 130 of them, 9 stating a count or largest id the visible answer never
# showed, 113 echoing the agent's own call budget back to the caller. run_once.py
# now strips <thinking> on every leg, so a published capture is the text a caller
# receives, and every axis was re-run. Scores are unchanged -- the scorer always
# read the answer with those blocks removed. nova-diagnosis.txt counts them here.

  capture                                  max id count  snapshot  calls  answer s
  A__aws__apache-polaris__1.txt            correct                3      3.24
  A__gcp__apache-polaris__1.txt            correct                3      4.53
  A__azure__apache-polaris__1.txt          correct                3      13.15
  A__aws__apache-polaris__2.txt            correct                3      3.15
  A__gcp__apache-polaris__2.txt            correct                3      6.30
  A__azure__apache-polaris__2.txt          correct                3      14.58
  A__azure__apache-polaris__3.txt          correct                3      13.06
  A__aws__apache-polaris__3.txt            correct                3      3.28
  A__gcp__apache-polaris__3.txt            correct                3      5.44
  A__aws__apache-polaris__4.txt            correct                3      3.27
  A__gcp__apache-polaris__4.txt            correct                3      5.54
  A__azure__apache-polaris__4.txt          correct                3      12.07
  A__gcp__apache-polaris__5.txt            correct                3      5.40
  A__azure__apache-polaris__5.txt          correct                3      15.61
  A__aws__apache-polaris__5.txt            correct                3      3.32
  A__azure__apache-polaris__6.txt          correct                3      14.10
  A__aws__apache-polaris__6.txt            correct                3      3.31
  A__gcp__apache-polaris__6.txt            correct                3      5.41
  A__aws__apache-polaris__7.txt            correct                3      3.26
  A__gcp__apache-polaris__7.txt            correct                3      5.71
  A__azure__apache-polaris__7.txt          correct                3      12.51
  A__aws__apache-polaris__8.txt            correct                3      3.22
  A__azure__apache-polaris__8.txt          correct                3      11.74
  A__gcp__apache-polaris__8.txt            correct                3      6.96
  A__aws__apache-polaris__9.txt            correct                3      3.25
  A__azure__apache-polaris__9.txt          correct                3      13.23
  A__gcp__apache-polaris__9.txt            correct                3      5.79
  A__azure__apache-polaris__10.txt         correct                3      12.06
  A__aws__apache-polaris__10.txt           correct                3      3.23
  A__gcp__apache-polaris__10.txt           correct                3      6.90
  C__aws__gemini-2.5-flash__apache-polaris__1.txt correct                3      7.05
  C__gcp__gemini-2.5-flash__apache-polaris__1.txt correct                3      5.99
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__1.txt correct                3      3.33
  C__aws__gemini-2.5-flash__apache-polaris__2.txt correct                3      6.87
  C__gcp__gemini-2.5-flash__apache-polaris__2.txt correct                3      4.98
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__2.txt correct                3      3.48
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__3.txt correct                3      3.36
  C__aws__gemini-2.5-flash__apache-polaris__3.txt correct                3      6.71
  C__gcp__gemini-2.5-flash__apache-polaris__3.txt correct                3      4.56
  C__aws__gemini-2.5-flash__apache-polaris__4.txt correct                3      8.47
  C__gcp__gemini-2.5-flash__apache-polaris__4.txt correct                3      5.93
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__4.txt correct                3      3.48
  C__gcp__gemini-2.5-flash__apache-polaris__5.txt correct                3      5.80
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__5.txt correct                3      3.30
  C__aws__gemini-2.5-flash__apache-polaris__5.txt correct                3      7.44
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__6.txt correct                3      3.22
  C__aws__gemini-2.5-flash__apache-polaris__6.txt correct                3      6.32
  C__gcp__gemini-2.5-flash__apache-polaris__6.txt correct                3      5.18
  C__aws__gemini-2.5-flash__apache-polaris__7.txt correct                3      6.15
  C__gcp__gemini-2.5-flash__apache-polaris__7.txt correct                3      4.61
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__7.txt correct                3      3.29
  C__aws__gemini-2.5-flash__apache-polaris__8.txt correct                3      8.04
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__8.txt correct                3      3.32
  C__gcp__gemini-2.5-flash__apache-polaris__8.txt correct                3      4.64
  C__aws__gemini-2.5-flash__apache-polaris__9.txt correct                3      6.03
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__9.txt correct                3      3.24
  C__gcp__gemini-2.5-flash__apache-polaris__9.txt correct                3      4.73
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__10.txt correct                3      3.36
  C__aws__gemini-2.5-flash__apache-polaris__10.txt correct                3      8.53
  C__gcp__gemini-2.5-flash__apache-polaris__10.txt correct                3      4.63
  D__aws__aws-glue__1.txt                  ok     ok     ok        5      6.21
  D__gcp__google-lakehouse__1.txt          ok     ok     ok        4      17.67
  D__azure__microsoft-onelake__1.txt       ok     ok     ok        4      30.43
  D__aws__aws-glue__2.txt                  ok     ok     ok        5      6.33
  D__gcp__google-lakehouse__2.txt          ok     ok     ok        4      14.94
  D__azure__microsoft-onelake__2.txt       ok     ok     ok        4      46.20
  D__azure__microsoft-onelake__3.txt       ok     ok     ok        4      26.07
  D__aws__aws-glue__3.txt                  ok     ok     ok        5      6.16
  D__gcp__google-lakehouse__3.txt          ok     ok     ok        4      13.07
  D__aws__aws-glue__4.txt                  ok     ok     ok        5      6.37
  D__gcp__google-lakehouse__4.txt          ok     ok     ok        4      14.21
  D__azure__microsoft-onelake__4.txt       ok     ok     ok        4      26.39
  D__gcp__google-lakehouse__5.txt          ok     ok     ok        4      14.57
  D__azure__microsoft-onelake__5.txt       ok     ok     ok        4      21.05
  D__aws__aws-glue__5.txt                  ok     ok     ok        5      6.01
  D__azure__microsoft-onelake__6.txt       ok     ok     ok        4      23.31
  D__aws__aws-glue__6.txt                  ok     ok     ok        5      6.35
  D__gcp__google-lakehouse__6.txt          ok     ok     ok        4      14.93
  D__aws__aws-glue__7.txt                  ok     ok     ok        5      6.04
  D__gcp__google-lakehouse__7.txt          ok     ok     ok        4      12.21
  D__azure__microsoft-onelake__7.txt       ok     ok     ok        4      26.18
  D__aws__aws-glue__8.txt                  ok     ok     ok        5      6.41
  D__azure__microsoft-onelake__8.txt       ok     ok     ok        4      21.79
  D__gcp__google-lakehouse__8.txt          ok     ok     ok        4      13.43
  D__aws__aws-glue__9.txt                  ok     ok     ok        5      6.29
  D__azure__microsoft-onelake__9.txt       ok     ok     ok        4      24.94
  D__gcp__google-lakehouse__9.txt          ok     ok     ok        4      11.79
  D__azure__microsoft-onelake__10.txt      ok     ok     ok        4      35.49
  D__aws__aws-glue__10.txt                 ok     ok     ok        5      6.32
  D__gcp__google-lakehouse__10.txt         ok     ok     ok        4      13.62
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__1.txt ok     ok     ok        3      8.25
  E__gcp__rows-only__apache-polaris__1.txt ok     ok     ok        3      5.79
  E__aws__provider-decoding__apache-polaris__1.txt ok     ok     ok        4      4.02
  E__azure__rows-only__apache-polaris__1.txt ok     ok     ok        4      16.58
  E__aws__rows-only__apache-polaris__1.txt ok     WRONG  ok        3      3.27
  E__aws__apache-polaris__1.txt            ok     ok     ok        4      3.78
  E__gcp__apache-polaris__1.txt            ok     ok     ok        4      20.90
  E__azure__apache-polaris__1.txt          ok     ok     ok        4      19.25
  E__aws__gemini-2.5-flash__apache-polaris__1.txt ok     ok     ok        4      11.94
  E__aws__rows-only-provider-decoding__apache-polaris__1.txt ok     WRONG  ok        3      3.46
  E__aws__rows-only-provider-decoding__apache-polaris__2.txt ok     WRONG  ok        3      3.35
  E__azure__apache-polaris__2.txt          ok     ok     ok        4      17.52
  E__gcp__rows-only__apache-polaris__2.txt ok     ok     ok        4      8.71
  E__aws__gemini-2.5-flash__apache-polaris__2.txt ok     ok     ok        4      12.25
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__2.txt ok     ok     ok        3      8.70
  E__aws__rows-only__apache-polaris__2.txt ok     WRONG  ok        3      3.37
  E__gcp__apache-polaris__2.txt            ok     ok     ok        4      7.21
  E__aws__apache-polaris__2.txt            ok     ok     ok        4      3.58
  E__azure__rows-only__apache-polaris__2.txt ok     ok     ok        4      18.43
  E__aws__provider-decoding__apache-polaris__2.txt ok     ok     ok        4      4.48
  E__aws__apache-polaris__3.txt            ok     ok     ok        4      3.72
  E__aws__provider-decoding__apache-polaris__3.txt ok     ok     ok        4      4.28
  E__aws__rows-only-provider-decoding__apache-polaris__3.txt ok     WRONG  ok        3      4.28
  E__aws__rows-only__apache-polaris__3.txt ok     WRONG  ok        3      3.45
  E__aws__gemini-2.5-flash__apache-polaris__3.txt ok     ok     ok        4      9.63
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__3.txt ok     ok     ok        3      10.92
  E__azure__apache-polaris__3.txt          ok     ok     ok        4      17.24
  E__azure__rows-only__apache-polaris__3.txt ok     ok     ok        4      22.53
  E__gcp__rows-only__apache-polaris__3.txt ok     ok     ok        3      6.55
  E__gcp__apache-polaris__3.txt            ok     ok     ok        4      10.14
  E__aws__provider-decoding__apache-polaris__4.txt ok     ok     ok        4      4.55
  E__aws__rows-only__apache-polaris__4.txt ok     WRONG  ok        3      3.66
  E__gcp__apache-polaris__4.txt            ok     ok     ok        4      6.66
  E__azure__rows-only__apache-polaris__4.txt ok     ok     ok        4      19.17
  E__aws__gemini-2.5-flash__apache-polaris__4.txt ok     ok     ok        4      12.06
  E__aws__apache-polaris__4.txt            ok     ok     ok        4      3.63
  E__aws__rows-only-provider-decoding__apache-polaris__4.txt ok     WRONG  ok        3      4.01
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__4.txt ok     ok     ok        4      10.59
  E__azure__apache-polaris__4.txt          ok     ok     ok        4      20.60
  E__gcp__rows-only__apache-polaris__4.txt ok     ok     ok        3      8.39
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__5.txt ok     ok     ok        3      9.47
  E__azure__apache-polaris__5.txt          ok     ok     ok        4      20.00
  E__aws__rows-only-provider-decoding__apache-polaris__5.txt ok     WRONG  ok        3      3.51
  E__aws__provider-decoding__apache-polaris__5.txt ok     ok     ok        4      3.86
  E__gcp__apache-polaris__5.txt            ok     ok     ok        4      7.57
  E__aws__rows-only__apache-polaris__5.txt ok     WRONG  ok        3      3.31
  E__aws__gemini-2.5-flash__apache-polaris__5.txt ok     ok     ok        4      10.38
  E__gcp__rows-only__apache-polaris__5.txt ok     ok     ok        3      8.51
  E__aws__apache-polaris__5.txt            ok     ok     ok        4      4.21
  E__azure__rows-only__apache-polaris__5.txt ok     ok     ok        3      15.80
  E__aws__provider-decoding__apache-polaris__6.txt ok     ok     ok        5      5.39
  E__aws__apache-polaris__6.txt            ok     ok     ok        4      3.72
  E__gcp__apache-polaris__6.txt            ok     ok     ok        4      9.29
  E__azure__rows-only__apache-polaris__6.txt ok     ok     ok        4      17.65
  E__aws__rows-only-provider-decoding__apache-polaris__6.txt ok     WRONG  ok        4      4.24
  E__gcp__rows-only__apache-polaris__6.txt ok     ok     ok        3      7.33
  E__aws__rows-only__apache-polaris__6.txt ok     WRONG  ok        3      3.45
  E__aws__gemini-2.5-flash__apache-polaris__6.txt ok     ok     ok        4      13.03
  E__azure__apache-polaris__6.txt          ok     ok     ok        4      19.89
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__6.txt ok     ok     ok        3      10.61
  E__azure__rows-only__apache-polaris__7.txt ok     ok     ok        4      18.10
  E__aws__gemini-2.5-flash__apache-polaris__7.txt ok     ok     ok        4      10.71
  E__gcp__apache-polaris__7.txt            ok     ok     ok        4      9.05
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__7.txt ok     ok     ok        3      10.56
  E__aws__rows-only__apache-polaris__7.txt ok     WRONG  ok        3      3.31
  E__aws__apache-polaris__7.txt            ok     ok     ok        4      3.66
  E__aws__rows-only-provider-decoding__apache-polaris__7.txt ok     WRONG  ok        3      3.65
  E__gcp__rows-only__apache-polaris__7.txt ok     ok     ok        3      6.21
  E__azure__apache-polaris__7.txt          ok     ok     ok        4      20.66
  E__aws__provider-decoding__apache-polaris__7.txt ok     ok     ok        4      4.99
  E__aws__apache-polaris__8.txt            ok     ok     ok        4      3.62
  E__aws__rows-only-provider-decoding__apache-polaris__8.txt ok     ok     ok        3      3.50
  E__azure__apache-polaris__8.txt          ok     ok     ok        4      18.93
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__8.txt ok     ok     ok        3      10.32
  E__azure__rows-only__apache-polaris__8.txt ok     ok     ok        4      20.81
  E__aws__provider-decoding__apache-polaris__8.txt ok     ok     ok        4      3.40
  E__gcp__rows-only__apache-polaris__8.txt ok     ok     ok        3      8.10
  E__aws__gemini-2.5-flash__apache-polaris__8.txt ok     ok     ok        4      10.38
  E__gcp__apache-polaris__8.txt            ok     ok     ok        4      7.84
  E__aws__rows-only__apache-polaris__8.txt ok     WRONG  ok        3      3.29
  E__aws__rows-only-provider-decoding__apache-polaris__9.txt ok     WRONG  ok        3      4.59
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__9.txt ok     ok     ok        3      8.46
  E__azure__apache-polaris__9.txt          ok     ok     ok        4      19.50
  E__aws__provider-decoding__apache-polaris__9.txt ok     ok     ok        4      4.27
  E__aws__rows-only__apache-polaris__9.txt ok     WRONG  ok        3      3.92
  E__aws__gemini-2.5-flash__apache-polaris__9.txt ok     ok     ok        4      9.75
  E__gcp__rows-only__apache-polaris__9.txt ok     ok     ok        4      8.17
  E__azure__rows-only__apache-polaris__9.txt ok     ok     ok        4      19.59
  E__aws__apache-polaris__9.txt            ok     ok     ok        4      3.61
  E__gcp__apache-polaris__9.txt            ok     ok     ok        4      10.95
  E__azure__apache-polaris__10.txt         ok     ok     ok        4      20.30
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__10.txt ok     ok     ok        3      12.04
  E__aws__provider-decoding__apache-polaris__10.txt ok     ok     ok        4      3.73
  E__gcp__apache-polaris__10.txt           ok     ok     ok        4      9.43
  E__aws__rows-only-provider-decoding__apache-polaris__10.txt ok     ok     ok        3      3.77
  E__aws__gemini-2.5-flash__apache-polaris__10.txt ok     ok     ok        4      19.36
  E__gcp__rows-only__apache-polaris__10.txt ok     ok     ok        3      10.89
  E__aws__apache-polaris__10.txt           ok     ok     ok        4      4.19
  E__aws__rows-only__apache-polaris__10.txt ok     WRONG  ok        3      5.10
  E__azure__rows-only__apache-polaris__10.txt ok     ok     ok        4      22.57
  E__gcp__rows-only__apache-polaris__11.txt ok     ok     ok        3      7.35
  E__azure__rows-only__apache-polaris__11.txt ok     ok     ok        4      18.34
  E__aws__rows-only__apache-polaris__11.txt ok     WRONG  ok        3      3.50
  E__aws__rows-only-provider-decoding__apache-polaris__11.txt ok     ok     ok        3      3.75
  E__aws__gemini-2.5-flash__apache-polaris__11.txt ok     ok     ok        4      9.85
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__11.txt ok     ok     ok        3      12.91
  E__aws__provider-decoding__apache-polaris__11.txt ok     WRONG  ok        3      3.62
  E__aws__apache-polaris__11.txt           ok     ok     ok        4      3.74
  E__azure__apache-polaris__11.txt         ok     ok     ok        4      21.44
  E__gcp__apache-polaris__11.txt           ok     ok     ok        4      7.53
  E__aws__provider-decoding__apache-polaris__12.txt ok     WRONG  ok        3      3.58
  E__gcp__apache-polaris__12.txt           ok     ok     ok        4      9.58
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__12.txt ok     ok     ok        3      8.76
  E__aws__gemini-2.5-flash__apache-polaris__12.txt ok     ok     ok        4      8.98
  E__aws__rows-only-provider-decoding__apache-polaris__12.txt ok     WRONG  ok        3      3.30
  E__azure__rows-only__apache-polaris__12.txt ok     ok     ok        4      20.24
  E__aws__apache-polaris__12.txt           ok     ok     ok        4      3.68
  E__gcp__rows-only__apache-polaris__12.txt ok     ok     ok        3      7.69
  E__aws__rows-only__apache-polaris__12.txt ok     WRONG  ok        3      5.08
  E__azure__apache-polaris__12.txt         ok     ok     ok        4      20.45
  E__azure__apache-polaris__13.txt         ok     ok     ok        4      20.15
  E__aws__rows-only-provider-decoding__apache-polaris__13.txt ok     WRONG  ok        3      4.00
  E__azure__rows-only__apache-polaris__13.txt ok     ok     ok        4      16.76
  E__gcp__rows-only__apache-polaris__13.txt ok     ok     ok        4      7.42
  E__aws__apache-polaris__13.txt           ok     ok     ok        4      3.65
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__13.txt ok     ok     ok        3      9.28
  E__aws__rows-only__apache-polaris__13.txt ok     WRONG  ok        3      3.77
  E__gcp__apache-polaris__13.txt           ok     ok     ok        4      7.83
  E__aws__provider-decoding__apache-polaris__13.txt ok     ok     ok        4      3.77
  E__aws__gemini-2.5-flash__apache-polaris__13.txt ok     ok     ok        4      11.88
  E__azure__rows-only__apache-polaris__14.txt ok     ok     ok        3      15.95
  E__aws__rows-only-provider-decoding__apache-polaris__14.txt ok     WRONG  ok        3      4.55
  E__aws__provider-decoding__apache-polaris__14.txt ok     WRONG  ok        4      3.61
  E__gcp__rows-only__apache-polaris__14.txt ok     ok     ok        4      11.47
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__14.txt ok     ok     ok        3      9.12
  E__aws__apache-polaris__14.txt           ok     ok     ok        4      3.62
  E__gcp__apache-polaris__14.txt           ok     ok     ok        4      7.66
  E__aws__rows-only__apache-polaris__14.txt ok     WRONG  ok        3      3.37
  E__aws__gemini-2.5-flash__apache-polaris__14.txt ok     ok     ok        4      10.45
  E__azure__apache-polaris__14.txt         ok     ok     ok        4      19.85
  E__aws__rows-only__apache-polaris__15.txt ok     WRONG  ok        3      3.43
  E__gcp__rows-only__apache-polaris__15.txt ok     ok     ok        3      7.92
  E__azure__rows-only__apache-polaris__15.txt ok     ok     ok        4      19.74
  E__azure__apache-polaris__15.txt         ok     ok     ok        4      17.08
  E__aws__gemini-2.5-flash__apache-polaris__15.txt ok     ok     ok        4      10.35
  E__aws__provider-decoding__apache-polaris__15.txt ok     ok     ok        4      4.50
  E__aws__apache-polaris__15.txt           ok     ok     ok        4      3.74
  E__aws__rows-only-provider-decoding__apache-polaris__15.txt ok     WRONG  ok        4      4.36
  E__gcp__apache-polaris__15.txt           ok     ok     ok        4      9.23
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__15.txt ok     ok     ok        3      8.14
  E__aws__apache-polaris__16.txt           ok     ok     ok        4      3.73
  E__aws__rows-only__apache-polaris__16.txt ok     WRONG  ok        3      3.51
  E__aws__provider-decoding__apache-polaris__16.txt ok     ok     ok        4      4.92
  E__aws__rows-only-provider-decoding__apache-polaris__16.txt ok     ok     ok        3      4.06
  E__gcp__apache-polaris__16.txt           ok     ok     ok        4      9.19
  E__gcp__rows-only__apache-polaris__16.txt ok     ok     ok        3      8.02
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__16.txt ok     ok     ok        3      9.81
  E__azure__apache-polaris__16.txt         ok     ok     ok        4      24.32
  E__azure__rows-only__apache-polaris__16.txt ok     ok     ok        4      17.19
  E__aws__gemini-2.5-flash__apache-polaris__16.txt ok     ok     ok        4      8.81
  E__aws__apache-polaris__17.txt           ok     ok     ok        4      3.68
  E__azure__rows-only__apache-polaris__17.txt ok     ok     ok        4      18.08
  E__gcp__rows-only__apache-polaris__17.txt ok     ok     ok        3      8.14
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__17.txt ok     ok     ok        3      9.11
  E__aws__rows-only__apache-polaris__17.txt ok     WRONG  ok        3      3.34
  E__azure__apache-polaris__17.txt         ok     ok     ok        4      20.35
  E__aws__gemini-2.5-flash__apache-polaris__17.txt ok     ok     ok        4      11.13
  E__gcp__apache-polaris__17.txt           ok     ok     ok        4      6.92
  E__aws__provider-decoding__apache-polaris__17.txt ok     WRONG  ok        3      3.63
  E__aws__rows-only-provider-decoding__apache-polaris__17.txt ok     WRONG  ok        4      4.88
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__18.txt ok     ok     ok        3      9.04
  E__azure__rows-only__apache-polaris__18.txt ok     ok     ok        4      22.27
  E__gcp__apache-polaris__18.txt           ok     ok     ok        4      6.62
  E__gcp__rows-only__apache-polaris__18.txt ok     ok     ok        3      6.99
  E__aws__provider-decoding__apache-polaris__18.txt ok     ok     ok        4      3.30
  E__aws__rows-only-provider-decoding__apache-polaris__18.txt ok     WRONG  ok        4      4.59
  E__aws__rows-only__apache-polaris__18.txt ok     WRONG  ok        3      3.42
  E__aws__apache-polaris__18.txt           ok     ok     ok        4      3.99
  E__aws__gemini-2.5-flash__apache-polaris__18.txt ok     ok     ok        4      11.22
  E__azure__apache-polaris__18.txt         ok     ok     ok        4      18.99
  E__gcp__apache-polaris__19.txt           ok     ok     ok        4      7.39
  E__gcp__rows-only__apache-polaris__19.txt ok     ok     ok        3      9.27
  E__azure__rows-only__apache-polaris__19.txt ok     ok     ok        4      23.04
  E__aws__rows-only__apache-polaris__19.txt ok     WRONG  ok        3      3.41
  E__aws__apache-polaris__19.txt           ok     ok     ok        4      3.77
  E__aws__gemini-2.5-flash__apache-polaris__19.txt ok     ok     ok        4      12.31
  E__aws__provider-decoding__apache-polaris__19.txt ok     ok     ok        4      3.82
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__19.txt ok     ok     ok        3      10.16
  E__azure__apache-polaris__19.txt         ok     ok     ok        4      19.61
  E__aws__rows-only-provider-decoding__apache-polaris__19.txt ok     WRONG  ok        3      3.30
  E__gcp__apache-polaris__20.txt           ok     ok     ok        4      9.86
  E__aws__apache-polaris__20.txt           ok     ok     ok        4      4.24
  E__aws__gemini-2.5-flash__rows-only__apache-polaris__20.txt ok     ok     ok        3      10.88
  E__gcp__rows-only__apache-polaris__20.txt ok     ok     ok        3      6.64
  E__azure__rows-only__apache-polaris__20.txt ok     ok     ok        4      20.90
  E__aws__gemini-2.5-flash__apache-polaris__20.txt ok     ok     ok        4      11.05
  E__aws__rows-only__apache-polaris__20.txt ok     WRONG  ok        3      3.21
  E__azure__apache-polaris__20.txt         ok     ok     ok        4      20.56
  E__aws__provider-decoding__apache-polaris__20.txt ok     ok     ok        5      5.03
  E__aws__rows-only-provider-decoding__apache-polaris__20.txt ok     WRONG  ok        3      3.81
  F__aws__provider-decoding__apache-polaris__1.txt correct                3      3.45
  F__aws__apache-polaris__1.txt            correct                3      3.24
  F__aws__provider-decoding__apache-polaris__2.txt correct                3      3.52
  F__aws__apache-polaris__2.txt            correct                3      3.24
  F__aws__provider-decoding__apache-polaris__3.txt correct                3      3.21
  F__aws__apache-polaris__3.txt            correct                3      3.46
  F__aws__apache-polaris__4.txt            correct                3      3.48
  F__aws__provider-decoding__apache-polaris__4.txt correct                3      2.98
  F__aws__provider-decoding__apache-polaris__5.txt correct                3      3.22
  F__aws__apache-polaris__5.txt            correct                3      3.45
  F__aws__apache-polaris__6.txt            correct                3      3.17
  F__aws__provider-decoding__apache-polaris__6.txt correct                3      2.78
  F__aws__apache-polaris__7.txt            correct                3      3.27
  F__aws__provider-decoding__apache-polaris__7.txt correct                3      3.07
  F__aws__provider-decoding__apache-polaris__8.txt correct                3      3.36
  F__aws__apache-polaris__8.txt            correct                3      3.36
  F__aws__apache-polaris__9.txt            correct                3      3.76
  F__aws__provider-decoding__apache-polaris__9.txt correct                3      3.35
  F__aws__provider-decoding__apache-polaris__10.txt correct                3      3.31
  F__aws__apache-polaris__10.txt           correct                3      3.24

Strands answers with a line break inside a word or number the model streamed whole: 0 of 180
