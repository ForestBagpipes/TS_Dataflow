import sys, traceback, time
sys.path.insert(0, "scripts"); sys.path.insert(0, "src")
import numpy as np, torch
import v54_external_imputers_par as par
import v54_external_t1 as T1
src = sys.argv[1]; bs = int(sys.argv[2])
T1.CONFIG["batch_size"] = bs
cols, fit_rows = par.collect(T1.ROOT, T1.FIT_BLOCK, src, None)
stacked = np.stack([r[2] for r in fit_rows])
finite_any = np.isfinite(stacked).any(axis=(0, 1))
drop = [j for j in range(1, stacked.shape[2]) if not finite_any[j]]
if drop:
    keep = np.array([j for j in range(stacked.shape[2]) if j not in set(drop)])
    cols = cols[keep]; fit_rows = [(e, p, panel[:, keep]) for e, p, panel in fit_rows]
cfg = T1.build_cfg(src, len(cols), 1, 0.1)
print("src", src, "channels", len(cols), "batch", T1.CONFIG["batch_size"], flush=True)
try:
    t0 = time.perf_counter()
    T1.fit_t1(cfg, [p for _e, _p, p in fit_rows], torch.device("cuda:0"))
    print("FIT OK in", round(time.perf_counter() - t0, 1), "s", flush=True)
except Exception as exc:
    print("FIT FAILED:", type(exc).__name__, str(exc)[:120], flush=True)
