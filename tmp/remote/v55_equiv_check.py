import sys, time, json
from pathlib import Path
sys.path.insert(0, "scripts"); sys.path.insert(0, "src")
import numpy as np
from introact_ts.v47 import select as SEL
from introact_ts.v55 import select as V55
from v54_common import ROOT, load_catalogs

bb = sys.argv[1] if len(sys.argv) > 1 else "bolt"
bank_cat = load_catalogs(ROOT, "bankx", bb)
q_cat = load_catalogs(ROOT, "train_eval", bb)
blocks = SEL.blocks_of()
bank = SEL.Bank(bank_cat, blocks=blocks)
q = SEL.Queries(q_cat, blocks=blocks)
D = SEL.distance_matrices(bank, q, lopo=False)
sel = json.loads((ROOT / "results/v54/protocol" / ("selection_%s.json" % bb)).read_text())
k, beta = SEL.frozen_config(sel)
print("frozen v54 (k,beta) =", k, beta, "queries", len(q_cat))

t0 = time.perf_counter()
old = SEL.score_grid(bank, q, D, k, beta)
t1 = time.perf_counter()
mom = V55.local_moments(bank, q, D, k)
means = V55.source_action_means(bank)
new = V55.scores_from_moments(mom, means, q, beta, 0.0)
t2 = time.perf_counter()

worst = 0.0
for a in SEL.ACTIONS:
    o, n = old[a], new[a]
    both_inf = np.isinf(o) & np.isinf(n)
    fin = np.isfinite(o) & np.isfinite(n)
    mismatch = int((~both_inf & ~fin).sum())
    d = float(np.abs(o[fin] - n[fin]).max()) if fin.any() else 0.0
    worst = max(worst, d)
    print("  %-14s finite=%4d  inf-agree=%4d  pattern-mismatch=%d  max|diff|=%.3e"
          % (a, int(fin.sum()), int(both_inf.sum()), mismatch, d))
print("worst abs diff over all actions:", worst)
print("v54 score_grid %.1fs, v55 moments+scores %.1fs" % (t1 - t0, t2 - t1))

dec_old = SEL.decide(q, old)
dec_new = V55.decide(q, new, threshold=0.0)
print("decision agreement:", float((dec_old == dec_new).mean()))

for lam in (4.0, 16.0, 64.0, float("inf")):
    s = V55.scores_from_moments(mom, means, q, beta, lam)
    d = V55.decide(q, s)
    out = SEL.outcomes(q, d)
    print("lam=%-5s ir=%.3f hir=%.3f macro=%.4f"
          % (lam, out["intervention_rate"], out["conditional_hir"],
             SEL.source_macro(q, out["mase"])))
out0 = SEL.outcomes(q, dec_old)
print("lam=0     ir=%.3f hir=%.3f macro=%.4f"
      % (out0["intervention_rate"], out0["conditional_hir"],
         SEL.source_macro(q, out0["mase"])))
