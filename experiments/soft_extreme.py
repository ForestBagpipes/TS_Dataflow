"""Two extreme soft penalty weights, to close the was the weight large enough question.

The sweep to mu 100 shows the damage of a soft penalty flattening out: 0.0114
at mu 50 and 0.0107 at mu 100, while the hard condition reaches 0.0006. The
obvious objection is that the weight was simply not pushed far enough. These
two points answer it.

The prediction, recorded before the run: damage stalls near 0.010 and refuses
to fall further while repair keeps dropping. If that holds, the soft penalty has
a damage floor an order of magnitude above what the hard condition reaches, and
raising the weight past that point buys nothing but lost repair. If it does not
hold, the result is reported as it comes.

Only the two new weights are run. Everything else, the corpus, the proposer and
the candidate edits, is identical to `soft_vs_hard.py` by construction, since
both build from the same seed.

Usage:
    python -u experiments/soft_extreme.py --device cuda --n 800
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
from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from gating import proposals_of  # noqa: E402
from soft_vs_hard import apply_plan, score  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

EXTRA_MUS = [500.0, 1000.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--epsilon", type=float, default=0.005)
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125), seed=42)
    windows = build_corpus(spec, source="ett")
    oodw = [w for w in windows if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    models = make_pool(PRESETS["multi-family"]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"{len(windows)} windows, perceive {time.time() - t0:.0f}s", flush=True)

    proposals = {t.window_id: proposals_of(t)
                 for t in BASELINES["stat_only"](windows, states, models)}
    print(f"proposer stat_only, "
          f"{sum(len(v) for v in proposals.values())} candidate edits", flush=True)

    out = {}
    for mu in EXTRA_MUS:
        t0 = time.time()
        rows = []
        for w, s in zip(windows, states):
            plan = proposals[w.window_id]
            if not plan:
                rows.append({"window_id": w.window_id, "series": w.series,
                             "crop": 0, "kept": []})
                continue
            series, crop, kept = apply_plan(
                w, s, models, plan,
                lambda du, d, _m=mu: (du - _m * d) > args.epsilon)
            rows.append({"window_id": w.window_id, "series": series,
                         "crop": crop, "kept": kept})
        r = score(rows, windows, form)
        out[f"{mu:g}"] = r
        print(f"  soft mu {mu:6g}  damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edits {r['n_modified']:4d}  "
              f"prot {r['protected_edits']:4d}  {time.time() - t0:.0f}s", flush=True)

    # Merge into the existing sweep so the frontier can be recomputed over all
    # weights rather than over two disjoint files.
    path = ROOT / "results" / "soft_vs_hard.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("soft", {}).update(out)
        soft, hard = payload["soft"], payload["hard"]
        frontier = []
        print(f"\nfrontier recomputed over all soft weights")
        print(f"{'budget':>9s}{'soft best':>12s}{'at mu':>8s}"
              f"{'hard best':>12s}{'at tau':>9s}")
        for budget in [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10]:
            s_ok = [(v["repair_reduction"], k) for k, v in soft.items()
                    if v["mean_damage"] <= budget]
            h_ok = [(v["repair_reduction"], k) for k, v in hard.items()
                    if v["mean_damage"] <= budget]
            sb = max(s_ok) if s_ok else (float("nan"), "none")
            hb = max(h_ok) if h_ok else (float("nan"), "none")
            frontier.append({"budget": budget, "soft": sb[0], "soft_mu": sb[1],
                             "hard": hb[0], "hard_tau": hb[1]})
            print(f"{budget:9.3f}{sb[0]:+12.3f}{sb[1]:>8s}"
                  f"{hb[0]:+12.3f}{hb[1]:>9s}")
        payload["frontier"] = frontier
        lo = min(v["mean_damage"] for v in soft.values())
        lo_hard = min(v["mean_damage"] for v in hard.values())
        payload["soft_damage_floor"] = lo
        payload["hard_damage_floor"] = lo_hard
        print(f"\nlowest damage reachable by any soft weight: {lo:.4f}")
        print(f"lowest damage reachable by any hard threshold: {lo_hard:.4f}")
        print(f"ratio: {lo / max(lo_hard, 1e-12):.1f}x")
        path.write_text(json.dumps(payload, indent=1, default=float),
                        encoding="utf-8")
    print("___SOFT_EXTREME_DONE___", flush=True)


if __name__ == "__main__":
    main()
