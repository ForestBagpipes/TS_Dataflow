"""Does the out of distribution inversion survive on real cross domain data?

The clean_ood stratum is four generated shapes, and it now carries the central
finding, so the finding has to be checked against data nobody constructed for
it. This builds one corpus holding both, the synthetic shapes and real windows
drawn from daily exchange rates and ten minute solar power, and measures the
same quantity on each.

If real out of distribution windows reproduce the inversion, the finding is
about unfamiliarity rather than about how the synthetic shapes were generated.
If they do not, the finding is limited to the construction and has to be
written that way.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402
from stratum_risk import describe, mann_whitney  # noqa: E402

from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", default=str(ROOT / "results" / "ood_check.json"))
    args = ap.parse_args()

    spec = CorpusSpec(
        n_contaminated=350, n_clean=200, n_hard=100, n_rare_valid=100,
        n_changepoint=100, n_clean_ood=150, n_real_ood=150, seed=42,
    )
    windows = build_corpus(spec, source="ett")
    counts = {}
    for w in windows:
        counts[w.stratum] = counts.get(w.stratum, 0) + 1
    print(f"corpus {len(windows)} windows: {counts}", flush=True)

    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    agent = IntroActAgent(models, AgentConfig())
    t0 = time.time()
    states = agent.perceive(windows)
    print(f"perception {time.time() - t0:.0f}s", flush=True)

    by = {}
    for w, s in zip(windows, states):
        d = by.setdefault(w.stratum, {"behav": [], "stat": []})
        d["behav"].append(s.behav_risk)
        d["stat"].append(s.defect_strength)

    payload = {"counts": counts, "strata": {}, "tests": {}}
    for k, d in by.items():
        payload["strata"][k] = {
            "behavioural_risk": describe(d["behav"]),
            "statistical_risk": describe(d["stat"]),
        }
    ref = by["contaminated"]
    for k, d in by.items():
        if k == "contaminated":
            continue
        payload["tests"][k] = {
            "behavioural": mann_whitney(d["behav"], ref["behav"]),
            "statistical": mann_whitney(d["stat"], ref["stat"]),
        }

    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print()
    print(f"{'stratum':16s}{'n':>6s}{'median behav':>14s}{'auc vs contam':>15s}{'p':>12s}")
    for k in sorted(by):
        m = payload["strata"][k]["behavioural_risk"]["median"]
        t = payload["tests"].get(k, {}).get("behavioural")
        auc = f"{t['auc']:.3f}" if t else "ref"
        p = f"{t['p']:.2e}" if t else ""
        print(f"{k:16s}{len(by[k]['behav']):6d}{m:+14.3f}{auc:>15s}{p:>12s}", flush=True)
    print("___OOD_CHECK_DONE___", flush=True)


if __name__ == "__main__":
    main()
