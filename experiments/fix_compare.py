"""Before and after for the three acceptance rule repairs.

Runs the same corpus twice, once with the repairs disabled and once with them
live, so the comparison is not against a number remembered from an earlier
commit. The switch is explicit rather than a git checkout, which keeps both
arms on identical code paths apart from the three changes under test.

  spread      the variance preservation term in the local structural distance
  ood         the scale free degenerate test for the OOD hypothesis
  depth       action_risk consuming improvement depth rather than the posterior

Usage:
    python -u experiments/fix_compare.py --device cuda --n 800
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402

import introact_ts.agent as A  # noqa: E402
import introact_ts.risk as R  # noqa: E402
import introact_ts.structure as S  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

PROTECTED = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")

#: The pre repair local weights, for the disabled arm.
OLD_LOCAL = {"shape": 0.35, "extremes": 0.25, "patch": 0.25, "footprint": 0.15}
NEW_LOCAL = dict(S.LOCAL_WEIGHTS)


def set_arm(enabled: bool):
    """Toggle the three repairs together."""
    S.LOCAL_WEIGHTS.clear()
    S.LOCAL_WEIGHTS.update(NEW_LOCAL if enabled else OLD_LOCAL)
    A.USE_DEPTH = enabled
    R.OOD_SCALE_FREE = enabled


def score(traces, windows, states):
    byid = {w.window_id: w for w in windows}
    dmg, before, after = [], [], []
    per = {}
    var_ratios = {}
    for t in traces:
        w = byid[t.window_id]
        d = per.setdefault(w.stratum, {"n": 0, "mod": 0})
        d["n"] += 1
        if t.modified:
            d["mod"] += 1
            # Spread ratio only means "was signal destroyed" for operators that
            # rewrite in place. RESEGMENT keeps a sub segment, and a calm
            # segment of a volatile window has a lower spread than the whole
            # window by definition, which is a correct crop rather than a
            # flattening. Measuring it the naive way reported five destructive
            # edits on clean_ood that were all RESEGMENT with a spread part of
            # exactly 0.000, so the ratio is now taken against the same span
            # the operator kept.
            if np.isfinite(w.series).all():
                src = w.series[t.crop_offset:t.crop_offset + len(t.final_series)]
                denom = float(np.std(src)) if len(src) >= 8 else float(np.std(w.series))
                r = float(np.std(t.final_series)) / max(denom, 1e-9)
                var_ratios.setdefault(w.stratum, []).append(r)
        if w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        a = _nmse(t.final_series, w.clean_series[t.crop_offset:], ref_var)
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(_nmse(w.series, w.clean_series, ref_var))
            after.append(a)
    b, af = float(np.mean(before)), float(np.mean(after))

    hyp = Counter()
    for w, s in zip(windows, states):
        if w.stratum == "clean_ood":
            hyp[s.hypothesis] += 1

    return {
        "mean_damage": float(np.mean(dmg)),
        "repair_reduction": (1.0 - af / b) if b > 1e-9 else 0.0,
        "n_modified": sum(1 for t in traces if t.modified),
        "per_stratum": per,
        "clean_ood_hypotheses": dict(hyp),
        "variance_ratios": {k: v for k, v in var_ratios.items()},
        "destructive_edits": {
            k: sum(1 for r in v if r < 0.5) for k, v in var_ratios.items()
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--preset", default="multi-family")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    #: The repairs and the holdout tau selection were developed separately and
    #: the first comparison ran the repairs at the old default of 0.12. The
    #: spread term is designed to be decisive just above the selected 0.02, so
    #: that comparison could not show what it was built to show.
    ap.add_argument("--tau", type=float, default=0.02)
    args = ap.parse_args()

    n = args.n
    spec = CorpusSpec(
        n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
        n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
        n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125),
        seed=args.seed,
    )
    windows = build_corpus(spec, source="ett")
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)
    print(f"{len(windows)} windows, seed {args.seed}, tau {args.tau}", flush=True)

    out = {}
    for label, enabled in [("before", False), ("after", True)]:
        set_arm(enabled)
        agent = IntroActAgent(
            models, AgentConfig(verification=VerifyConfig(tau=args.tau)))
        t0 = time.time()
        states = agent.perceive(windows)
        traces = [agent.curate_window(w, s, peer_idx=i)
                  for i, (w, s) in enumerate(zip(windows, states))]
        r = score(traces, windows, states)
        r["seconds"] = time.time() - t0
        out[label] = r
        print(f"{label:7s} damage {r['mean_damage']:.4f}  "
              f"repair {r['repair_reduction']:+.3f}  edited {r['n_modified']:4d}  "
              f"{r['seconds']:.0f}s", flush=True)

    b, a = out["before"], out["after"]
    print()
    print("clean_ood hypotheses")
    print(f"  before {b['clean_ood_hypotheses']}")
    print(f"  after  {a['clean_ood_hypotheses']}")
    print()
    print(f"{'stratum':14s}{'n':>5s}{'mod before':>12s}{'mod after':>11s}"
          f"{'destr before':>14s}{'destr after':>13s}")
    for k in sorted(b["per_stratum"]):
        pb, pa = b["per_stratum"][k], a["per_stratum"][k]
        print(f"{k:14s}{pb['n']:5d}{pb['mod']:12d}{pa['mod']:11d}"
              f"{b['destructive_edits'].get(k, 0):14d}"
              f"{a['destructive_edits'].get(k, 0):13d}")
    print()
    dd = 100 * (1 - a["mean_damage"] / max(b["mean_damage"], 1e-12))
    print(f"damage {dd:+.1f} percent, repair change "
          f"{a['repair_reduction'] - b['repair_reduction']:+.4f}")

    (ROOT / "results" / "fix_compare.json").write_text(
        json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("___FIX_COMPARE_DONE___", flush=True)


if __name__ == "__main__":
    main()
