# Axes C and E, captured 2026-09-15, SUPERSEDED and kept. The harness read
# Strands answers with str(AgentResult), which puts a line break after every
# text block; Strands' Gemini provider returns some answers as several blocks,
# so a line break could land inside a word or number -- one of them inside the
# largest id. The count below is generated from the captures. The harness now
# joins the text blocks directly and both axes were re-run. Re-scored below,
# not changed.

  capture                                  max id count  snapshot  calls  answer s
  C__aws__gemini-2.5-flash__apache-polaris__1.txt correct                3      8.93
  C__gcp__gemini-2.5-flash__apache-polaris__1.txt correct                3      5.78
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__1.txt correct                3      3.53
  C__aws__gemini-2.5-flash__apache-polaris__2.txt correct                3      8.54
  C__gcp__gemini-2.5-flash__apache-polaris__2.txt correct                3      6.47
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__2.txt correct                3      2.98
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__3.txt WRONG                  3      3.36
  C__aws__gemini-2.5-flash__apache-polaris__3.txt correct                3      6.27
  C__gcp__gemini-2.5-flash__apache-polaris__3.txt correct                3      5.96
  C__aws__gemini-2.5-flash__apache-polaris__4.txt correct                3      7.82
  C__gcp__gemini-2.5-flash__apache-polaris__4.txt correct                3      5.65
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__4.txt correct                3      2.89
  C__gcp__gemini-2.5-flash__apache-polaris__5.txt correct                3      4.94
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__5.txt correct                3      2.98
  C__aws__gemini-2.5-flash__apache-polaris__5.txt correct                3      6.84
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__6.txt correct                3      3.42
  C__aws__gemini-2.5-flash__apache-polaris__6.txt correct                3      7.51
  C__gcp__gemini-2.5-flash__apache-polaris__6.txt correct                3      4.99
  C__aws__gemini-2.5-flash__apache-polaris__7.txt correct                3      9.05
  C__gcp__gemini-2.5-flash__apache-polaris__7.txt correct                3      5.45
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__7.txt correct                3      2.98
  C__aws__gemini-2.5-flash__apache-polaris__8.txt correct                3      8.17
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__8.txt correct                3      3.13
  C__gcp__gemini-2.5-flash__apache-polaris__8.txt correct                3      5.31
  C__aws__gemini-2.5-flash__apache-polaris__9.txt correct                3      7.35
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__9.txt WRONG                  3      3.10
  C__gcp__gemini-2.5-flash__apache-polaris__9.txt correct                3      5.37
  C__aws__us.amazon.nova-micro-v1-0__apache-polaris__10.txt correct                3      3.05
  C__aws__gemini-2.5-flash__apache-polaris__10.txt correct                3      7.79
  C__gcp__gemini-2.5-flash__apache-polaris__10.txt correct                3      5.53
  E__aws__gemini-2.5-flash__apache-polaris__1.txt ok     ok     ok        3      13.32
  E__azure__apache-polaris__1.txt          ok     ok     ok        4      18.99
  E__aws__apache-polaris__1.txt            ok     WRONG  ok        4      4.52
  E__gcp__apache-polaris__1.txt            ok     ok     ok        3      15.93
  E__aws__apache-polaris__2.txt            ok     WRONG  ok        3      4.01
  E__azure__apache-polaris__2.txt          ok     ok     ok        4      19.57
  E__aws__gemini-2.5-flash__apache-polaris__2.txt ok     ok     ok        3      13.63
  E__gcp__apache-polaris__2.txt            ok     ok     ok        4      16.08
  E__aws__apache-polaris__3.txt            ok     WRONG  ok        3      3.72
  E__gcp__apache-polaris__3.txt            ok     ok     ok        3      18.94
  E__aws__gemini-2.5-flash__apache-polaris__3.txt ok     ok     ok        3      14.69
  E__azure__apache-polaris__3.txt          ok     ok     ok        3      20.58
  E__aws__gemini-2.5-flash__apache-polaris__4.txt ok     ok     ok        3      11.88
  E__gcp__apache-polaris__4.txt            ok     ok     ok        4      12.26
  E__aws__apache-polaris__4.txt            ok     WRONG  ok        3      3.42
  E__azure__apache-polaris__4.txt          ok     ok     ok        4      22.75
  E__aws__gemini-2.5-flash__apache-polaris__5.txt ok     ok     ok        3      12.40
  E__aws__apache-polaris__5.txt            ok     WRONG  ok        5      6.03
  E__azure__apache-polaris__5.txt          ok     ok     ok        4      24.87
  E__gcp__apache-polaris__5.txt            ok     ok     ok        3      20.94
  E__aws__apache-polaris__6.txt            ok     WRONG  ok        4      3.62
  E__azure__apache-polaris__6.txt          ok     ok     ok        3      18.53
  E__gcp__apache-polaris__6.txt            ok     ok     ok        3      11.45
  E__aws__gemini-2.5-flash__apache-polaris__6.txt ok     ok     ok        3      15.18
  E__azure__apache-polaris__7.txt          ok     ok     ok        3      16.35
  E__aws__apache-polaris__7.txt            ok     WRONG  ok        3      3.28
  E__aws__gemini-2.5-flash__apache-polaris__7.txt ok     ok     ok        4      18.37
  E__gcp__apache-polaris__7.txt            ok     ok     ok        4      9.17
  E__aws__gemini-2.5-flash__apache-polaris__8.txt ok     ok     ok        4      14.76
  E__gcp__apache-polaris__8.txt            ok     ok     ok        3      10.90
  E__aws__apache-polaris__8.txt            WRONG  WRONG  ok        4      3.87
  E__azure__apache-polaris__8.txt          ok     ok     ok        4      19.77
  E__aws__apache-polaris__9.txt            ok     WRONG  ok        3      4.33
  E__aws__gemini-2.5-flash__apache-polaris__9.txt ok     ok     ok        3      26.92
  E__gcp__apache-polaris__9.txt            ok     ok     ok        3      10.88
  E__azure__apache-polaris__9.txt          ok     ok     ok        4      19.61
  E__azure__apache-polaris__10.txt         ok     ok     ok        4      21.02
  E__aws__gemini-2.5-flash__apache-polaris__10.txt WRONG  ok     ok        3      14.07
  E__gcp__apache-polaris__10.txt           ok     ok     ok        3      13.91
  E__aws__apache-polaris__10.txt           ok     WRONG  ok        3      3.39

Strands answers with a line break inside a word or number the model streamed whole: 3 of 40
  E__aws__gemini-2.5-flash__apache-polaris__10.txt        'obe_table` is 2\n3. There ar'
  E__aws__gemini-2.5-flash__apache-polaris__3.txt         '` in the `probe\n_ns.probe_t'
  E__aws__gemini-2.5-flash__apache-polaris__5.txt         'with an id of 1\n0 or more. '
