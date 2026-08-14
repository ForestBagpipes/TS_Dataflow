"""Downstream evaluation restricted to the windows curation actually touched.

The full corpus evaluation is diluted by construction. Curation modified 71 of
800 windows for our own system, and a downstream model trained on all 560
training windows sees the same untouched data under every method, so the
comparison adds an identical constant to every arm and divides the difference
by the whole corpus. The measured effects were 0.1 to 1.3 percent, which is
inside the noise floor the linear models show.

The fix is not to raise the contamination rate. The 67 percent point already
demonstrated what that does: the corpus mean becomes level_shift wearing a
disguise, and naive repair wins by construction. It is also not a realistic
setting to report.

Instead the evaluation is aligned to the scope of the intervention. A window no
method edited contributes identically to every arm, so it carries no
information about curation and only dilutes. The affected subset is the union
of windows edited by the methods that choose where to act.

`always_clean` is excluded from the union while still being scored on it.
Including it would make the union the entire corpus, since it edits every
window unconditionally, which would defeat the purpose. It is still evaluated
on the resulting subset so its row stays comparable.

Both views are reported side by side. The full corpus number is not discarded.

Usage:
    python -u experiments/downstream_scoped.py --device cuda --n 800 --seeds 42
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from baselines import BASELINES  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from downstream import evaluate, split_windows  # noqa: E402
from downstream_gated import _GatedTrace  # noqa: E402
from gating import gate, proposals_of  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402

#: Methods whose edited windows define the affected subset. always_clean is
#: absent by design, see the module docstring.
UNION_SOURCES = ("stat_only", "stat_only_gated", "always_clean_gated",
                 "introact_full")


def touched_ids(traces, windows) -> set:
    """Window ids whose series differs from the input."""
    byid = {w.window_id: w for w in windows}
    out = set()
    for t in traces:
        src = byid[t.window_id].series
        cur = t.final_series
        off = getattr(t, "crop_offset", 0)
        if off or len(cur) != len(src) or not np.allclose(
                np.nan_to_num(cur), np.nan_to_num(src[off:off + len(cur)]),
                rtol=0, atol=1e-12):
            out.add(t.window_id)
    return out


def run_seed(seed, n, tau, device, deep):
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=seed,
    )
    windows = build_corpus(spec, source="ett")
    train_ids, test_ids = split_windows(windows, train_frac=0.7, seed=seed)

    models = make_pool(PRESETS["multi-family"]["curation"], device=device)
    cfg = VerifyConfig(tau=tau)
    agent = IntroActAgent(models, AgentConfig(verification=cfg))
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"  perceive {time.time() - t0:.0f}s", flush=True)
    byid = {w.window_id: (w, s, i)
            for i, (w, s) in enumerate(zip(windows, states))}

    # Curate once per method, keep the traces, evaluate twice.
    curated = {}
    for name in ["no_action", "stat_only", "always_clean"]:
        t0 = time.time()
        curated[name] = BASELINES[name](windows, states, models)
        print(f"  curate {name} {time.time() - t0:.0f}s", flush=True)
        if name == "no_action":
            continue
        t0 = time.time()
        gated = []
        for t in curated[name]:
            w, s, idx = byid[t.window_id]
            plan = proposals_of(t)
            if not plan:
                gated.append(_GatedTrace(w.window_id, np.asarray(w.series, float)))
                continue
            series, crop, _, _ = gate(w, s, models, plan, agent, idx, cfg)
            gated.append(_GatedTrace(w.window_id, series, crop))
        curated[f"{name}_gated"] = gated
        print(f"  curate {name}_gated {time.time() - t0:.0f}s", flush=True)

    t0 = time.time()
    curated["introact_full"] = [agent.curate_window(w, s, peer_idx=i)
                                for i, (w, s) in enumerate(zip(windows, states))]
    print(f"  curate introact_full {time.time() - t0:.0f}s", flush=True)

    affected = set()
    per_method_touched = {}
    for name in UNION_SOURCES:
        t = touched_ids(curated[name], windows)
        per_method_touched[name] = len(t)
        affected |= t
    ac = touched_ids(curated["always_clean"], windows)
    print(f"  affected union {len(affected)} of {len(windows)} windows "
          f"(always_clean alone touches {len(ac)}, excluded from the union)",
          flush=True)
    print(f"  per method touched: {per_method_touched}", flush=True)

    tr_sub, te_sub = train_ids & affected, test_ids & affected
    print(f"  subset split: {len(tr_sub)} train, {len(te_sub)} test", flush=True)

    out = {"full": {}, "affected": {},
           "n_affected": len(affected), "n_total": len(windows),
           "touched_per_method": per_method_touched,
           "always_clean_touched": len(ac),
           "n_affected_train": len(tr_sub), "n_affected_test": len(te_sub)}
    for name, traces in curated.items():
        out["full"][name] = evaluate(traces, windows, train_ids, test_ids,
                                     include_deep=deep, seed=seed)
        out["affected"][name] = evaluate(traces, windows, tr_sub, te_sub,
                                         include_deep=deep, seed=seed)
        print(f"  eval {name} done", flush=True)
    return out


def table(per_seed, view, seeds, label):
    order = ["no_action", "stat_only", "stat_only_gated", "always_clean",
             "always_clean_gated", "introact_full"]
    mdls = sorted({m for s in seeds for v in per_seed[s][view].values()
                   for m, x in v.items() if isinstance(x, dict) and "mse" in x})
    print(f"\n===== {label} =====")
    for mdl in mdls:
        rows = []
        base = None
        for k in order:
            vals = [per_seed[s][view][k][mdl]["mse"] for s in seeds
                    if k in per_seed[s][view] and mdl in per_seed[s][view][k]]
            if not vals:
                continue
            m, sd = float(np.mean(vals)), float(np.std(vals))
            if k == "no_action":
                base = m
            rows.append((k, m, sd, 100 * (1 - m / max(base, 1e-12)) if base else 0.0))
        if not rows:
            continue
        print(f"\n-- {mdl}")
        print(f"{'method':22s}{'mse':>11s}{'std':>10s}{'vs no_action':>14s}"
              f"{'std as pct':>12s}")
        for k, m, sd, rel in rows:
            pct = 100 * sd / max(m, 1e-12)
            print(f"{k:22s}{m:11.5f}{sd:10.5f}{rel:+13.1f}%{pct:11.2f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--tau", type=float, default=0.02)
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--deep", action="store_true")
    args = ap.parse_args()

    per_seed = {}
    for seed in args.seeds:
        print(f"[seed {seed}]", flush=True)
        per_seed[seed] = run_seed(seed, args.n, args.tau, args.device, args.deep)
        (ROOT / "results" / "downstream_scoped.json").write_text(
            json.dumps(per_seed, indent=1, default=float), encoding="utf-8")

    table(per_seed, "full", args.seeds, "full corpus, diluted by untouched windows")
    table(per_seed, "affected", args.seeds, "affected subset, the scope of the intervention")
    print("\n___DOWNSTREAM_SCOPED_DONE___", flush=True)


if __name__ == "__main__":
    main()
