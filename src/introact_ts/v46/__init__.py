"""v4.6: the frozen-configuration run that produces the reported TEST numbers.

v4.6 changes three things relative to v4.4 and nothing else:

* the replay bank is built from the whole TRAIN region (train + dev rows)
  rather than from 60 % of the train rows, because the v4.4 bank was the
  binding constraint on the local estimator;
* (k, beta) are selected per backbone by leave-one-parent-out cross-validation
  on the bank itself, under a harmful-intervention cap anchored on the best
  fixed intervention, rather than on a separate 48-parent gate block;
* the headline numbers are computed on a held-out TEST region that no part of
  the development touched.

The action catalog, the state features, the missingness protocol, the metrics
and the aggregation ladder are imported unchanged from ``introact_ts.v44``.
"""
