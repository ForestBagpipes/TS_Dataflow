"""Before and after for the three acceptance rule repairs.

Runs the same corpus twice, once with the repairs disabled and once with them
live, so the comparison is not against a number remembered from an earlier
commit. The switch is explicit rather than a git checkout, which keeps both
arms on identical code paths apart from the three changes under test.

  spread      the variance preservation term in the local structural distance
  ood         the scale free degenerate test for the OOD hypothesis
  depth       action_risk consuming improvement depth rather than the posterior

The depth arm is the one section 2.3 of the progress document rests on, so this
script also carries the three read outs that claim needs and that the first
version of the comparison did not produce:

  risk vetoes     ROLLED_BACK_RISK counted separately from the other two
                  rollback reasons, since replacing the first term of R(a)
                  changes which candidates that condition stops and a total
                  rollback count hides it
  decile error    the mis edit rate among the tenth of edited windows the
                  hypothesis posterior was most confident about, computed under
                  both arms. This is the quantity that overturned the old rule,
                  and until now only the old arm's value existed
  xl scale        2000 windows, the same CorpusSpec the learning loop uses, so
                  the comparison is on the corpus the claim is made about

Usage:
    python -u experiments/fix_compare.py --device cuda --scale xl
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
sys.path.insert(0, str(ROOT / "tools"))

from monitor import Monitor  # noqa: E402

from audit import _nmse  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402
from run_agent import SCALES  # noqa: E402

import introact_ts.agent as A  # noqa: E402
import introact_ts.risk as R  # noqa: E402
import introact_ts.structure as S  # noqa: E402
from introact_ts.agent import AgentConfig, IntroActAgent  # noqa: E402
from introact_ts.types import Verdict  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402
from introact_ts.backends import PRESETS, make_pool  # noqa: E402

#: Strata whose windows should not be edited at all. ``clean_ood`` is a
#: synthetic probe layer under the 4.1.2 ruling of 2026-08-22 and is scored
#: separately, so it is no longer summed into the protected damage figure.
PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
PROBE_LAYER = "clean_ood"

#: Fraction used for the selective execution read out, matching the top row of
#: results/confidence_and_ood.md so the two are comparable.
DECILE = 0.10

#: The pre repair local weights, for the disabled arm.
OLD_LOCAL = {"shape": 0.35, "extremes": 0.25, "patch": 0.25, "footprint": 0.15}
NEW_LOCAL = dict(S.LOCAL_WEIGHTS)


#: Which repairs each arm turns on, as (spread, ood, depth).
#:
#: The original script had two arms and toggled all three repairs together,
#: which answers whether the batch helped but not which member of it did. The
#: R(a) substitution is the one section 2.3 rests on and the one whose effect on
#: the risk condition has to be attributable, so a third arm turns on that
#: repair alone. before to depth_only isolates it, depth_only to after is what
#: the other two add on top.
ARM_SPECS = {
    "before": (False, False, False),
    "depth_only": (False, False, True),
    "after": (True, True, True),
}


def set_arm(name: str):
    """Put the module level switches into the named arm's configuration."""
    spread, ood, depth = ARM_SPECS[name]
    S.LOCAL_WEIGHTS.clear()
    S.LOCAL_WEIGHTS.update(NEW_LOCAL if spread else OLD_LOCAL)
    A.USE_DEPTH = depth
    R.OOD_SCALE_FREE = ood


def selective_error(rows, fraction=DECILE):
    """Mis edit rate among the most confident ``fraction`` of edited windows.

    This reproduces the read out in results/confidence_and_ood.md: order edited
    windows by the confidence the hypothesis posterior assigned them, take the
    leading fraction, and report how many of those edits ended further from the
    clean reference than they started. Under the old rule that curve ran the
    wrong way, 0.595 at the leading tenth against 0.484 overall, which is what
    disqualified the posterior as the first term of R(a). The same number under
    the new rule is what tells us the substitution actually fixed it.
    """
    if not rows:
        return {"n": 0}
    ordered = sorted(rows, key=lambda r: -r["confidence"])
    n = len(ordered)
    k = max(1, int(round(fraction * n)))
    head = ordered[:k]
    overall = sum(int(r["error"]) for r in ordered) / n
    curve = {}
    for f in (0.10, 0.25, 0.50, 0.75, 1.00):
        m = max(1, int(round(f * n)))
        curve[f"{f:.2f}"] = sum(int(r["error"]) for r in ordered[:m]) / m
    return {
        "n": n,
        "k_head": k,
        "head_error_rate": sum(int(r["error"]) for r in head) / k,
        "overall_error_rate": overall,
        # Positive means the confident tenth is worse than average, which is the
        # failure the substitution was made to remove.
        "excess": sum(int(r["error"]) for r in head) / k - overall,
        "coverage_curve": curve,
        "confidence_spread": float(np.ptp([r["confidence"] for r in ordered])),
    }


def score(traces, windows, states):
    byid = {w.window_id: w for w in windows}
    dmg, probe_dmg, before, after = [], [], [], []
    per = {}
    var_ratios = {}
    verdicts = Counter()
    sel_rows = []
    for t in traces:
        w = byid[t.window_id]
        d = per.setdefault(w.stratum, {"n": 0, "mod": 0})
        d["n"] += 1
        for rec in t.records:
            verdicts[rec.verdict.value] += 1
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
        bfr = _nmse(w.series, w.clean_series, ref_var)
        if t.modified:
            sel_rows.append({
                "confidence": float(t.risk_state.get("confidence", 0.0)),
                "error": bool(a > bfr + 1e-9),
                "stratum": w.stratum,
            })
        if w.stratum in PROTECTED:
            dmg.append(a)
        elif w.stratum == PROBE_LAYER:
            probe_dmg.append(a)
        elif w.stratum == "contaminated":
            before.append(bfr)
            after.append(a)
    b, af = float(np.mean(before)), float(np.mean(after))

    hyp = Counter()
    for w, s in zip(windows, states):
        if w.stratum == PROBE_LAYER:
            hyp[s.hypothesis] += 1

    mis = sum(p["mod"] for k, p in per.items() if k in PROTECTED)
    return {
        "mean_damage": float(np.mean(dmg)),
        # Kept separately under the 4.1.2 ruling: the probe layer is synthetic,
        # so it characterises the signal rather than scoring protection.
        "probe_layer_damage": float(np.mean(probe_dmg)) if probe_dmg else None,
        "protected_mis_edits": int(mis),
        "repair_reduction": (1.0 - af / b) if b > 1e-9 else 0.0,
        "n_modified": sum(1 for t in traces if t.modified),
        "per_stratum": per,
        "verdicts": dict(verdicts),
        "risk_vetoes": int(verdicts.get(Verdict.ROLLED_BACK_RISK.value, 0)),
        "utility_vetoes": int(verdicts.get(Verdict.ROLLED_BACK_UTILITY.value, 0)),
        "structure_vetoes": int(verdicts.get(Verdict.ROLLED_BACK_STRUCTURE.value, 0)),
        "selective": selective_error(sel_rows),
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
    #: xl is the corpus the learning loop and the pre registration use, so the
    #: comparison now runs on the corpus the section 2.3 claim is made about.
    #: --n stays available for a cheap smoke run and is ignored unless given.
    ap.add_argument("--scale", default="xl", choices=list(SCALES))
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    #: The repairs and the holdout tau selection were developed separately and
    #: the first comparison ran the repairs at the old default of 0.12. The
    #: spread term is designed to be decisive just above the selected 0.02, so
    #: that comparison could not show what it was built to show.
    ap.add_argument("--tau", type=float, default=0.02)
    #: The node reports the host's 208 cores rather than its own share, so
    #: the default of cpu_count minus two tries to fork 206 workers and the
    #: pool dies on the fork. This only affects how the profile extraction
    #: is split, not what it computes.
    ap.add_argument("--arms", nargs="+", default=list(ARM_SPECS),
                    choices=list(ARM_SPECS))
    ap.add_argument("--n-jobs", dest="n_jobs", type=int, default=32)
    ap.add_argument("--expect-code-hash", dest="expect_code_hash", default=None)
    ap.add_argument("--expect-config-hash", dest="expect_config_hash", default=None)
    ap.add_argument("--require-pool", dest="require_pool", type=int, default=None)
    #: The node is synced by rsync and has no .git, so the tree check is off
    #: there and the code hash carries the version guarantee instead.
    ap.add_argument("--allow-dirty-tree", dest="require_clean_tree",
                    action="store_false", default=True)
    args = ap.parse_args()

    if args.n is None:
        spec = SCALES[args.scale]
        spec.seed = args.seed
        label_scale = args.scale
    else:
        n = args.n
        spec = CorpusSpec(
            n_contaminated=int(n * 0.35), n_clean=int(n * 0.20),
            n_hard=int(n * 0.1125), n_rare_valid=int(n * 0.1125),
            n_changepoint=int(n * 0.1125), n_clean_ood=int(n * 0.1125),
            seed=args.seed,
        )
        label_scale = f"custom-{n}"
    # The default arm must be the one section 2.3 describes before anything is
    # toggled. This script is the only place in the repository that sets the
    # switch at all, so if it is ever false on entry the deployment is stale.
    if A.USE_DEPTH is not True:
        raise SystemExit(
            "agent.USE_DEPTH is False on entry, the deployed default does not "
            "match section 2.3, refusing to run a comparison against it")

    windows = build_corpus(spec, source="ett")
    models = make_pool(PRESETS[args.preset]["curation"], device=args.device)

    mon = Monitor(
        "fix_compare",
        expects=["results/fix_compare.json"],
        config={"scale": label_scale, "seed": args.seed, "tau": args.tau,
                "preset": args.preset, "decile": DECILE,
                "protected": ",".join(PROTECTED)},
        expect_config_hash=args.expect_config_hash,
        require_pool=args.require_pool,
        require_clean_tree=args.require_clean_tree,
        expect_code_hash=args.expect_code_hash,
    )
    mon.start(pool_size=len(models))
    print(f"{len(windows)} windows, scale {label_scale}, seed {args.seed}, "
          f"tau {args.tau}", flush=True)

    out = {}
    for label in args.arms:
        set_arm(label)
        agent = IntroActAgent(
            models, AgentConfig(verification=VerifyConfig(tau=args.tau),
                                n_jobs=args.n_jobs))
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

    print()
    print("probe layer hypotheses")
    for label in args.arms:
        print(f"  {label:11s} {out[label]['clean_ood_hypotheses']}")
    print()
    head = "".join(f"{lb:>12s}" for lb in args.arms)
    print(f"{'stratum':14s}{'n':>5s}{head}")
    first = out[args.arms[0]]
    for k in sorted(first["per_stratum"]):
        row = "".join(f"{out[lb]['per_stratum'][k]['mod']:12d}" for lb in args.arms)
        print(f"{k:14s}{first['per_stratum'][k]['n']:5d}{row}")
    print()
    print("rollback reasons, by condition")
    print(f"{'arm':11s}{'utility':>10s}{'structure':>11s}{'risk':>7s}{'accepted':>10s}")
    for label in args.arms:
        r = out[label]
        print(f"{label:11s}{r['utility_vetoes']:10d}{r['structure_vetoes']:11d}"
              f"{r['risk_vetoes']:7d}"
              f"{r['verdicts'].get('ACCEPTED', 0):10d}")

    print()
    print("selective execution on the hypothesis posterior")
    print(f"{'arm':11s}{'edits':>7s}{'head 10pct':>12s}{'overall':>9s}{'excess':>9s}")
    for label in args.arms:
        s = out[label]["selective"]
        if not s.get("n"):
            continue
        print(f"{label:11s}{s['n']:7d}{s['head_error_rate']:12.3f}"
              f"{s['overall_error_rate']:9.3f}{s['excess']:+9.3f}")
    print()
    print(f"{'coverage':>10s}" + "".join(f"{lb:>12s}" for lb in args.arms))
    for f in ("0.10", "0.25", "0.50", "0.75", "1.00"):
        vals = [out[lb]["selective"].get("coverage_curve", {}).get(f)
                for lb in args.arms]
        if any(v is None for v in vals):
            continue
        print(f"{f:>10s}" + "".join(f"{v:12.3f}" for v in vals))

    print()
    base = out[args.arms[0]]
    for lb in args.arms[1:]:
        r = out[lb]
        dd = 100 * (1 - r["mean_damage"] / max(base["mean_damage"], 1e-12))
        print(f"{args.arms[0]} to {lb}: damage {dd:+.1f} percent, repair change "
              f"{r['repair_reduction'] - base['repair_reduction']:+.4f}, "
              f"protected mis edits {base['protected_mis_edits']} to "
              f"{r['protected_mis_edits']}, risk vetoes "
              f"{base['risk_vetoes']} to {r['risk_vetoes']}")

    out["meta"] = {
        "scale": label_scale, "n_windows": len(windows), "seed": args.seed,
        "tau": args.tau, "preset": args.preset,
        "protected_strata": list(PROTECTED), "probe_layer": PROBE_LAYER,
        "decile": DECILE, "arms": list(args.arms),
        "arm_specs": {k: list(v) for k, v in ARM_SPECS.items()},
    }
    (ROOT / "results" / "fix_compare.json").write_text(
        json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("___FIX_COMPARE_DONE___", flush=True)


if __name__ == "__main__":
    main()
