"""Is the clean_ood stratum one phenomenon or a bag of unrelated shapes?

The central characterisation rests on this stratum, and it is built from four
generators that have nothing in common except being synthetic. Two of them
collide with contamination types by construction: a staircase is a series of
discrete level jumps and the injected level_shift defect is a discrete level
jump, a sawtooth is a repeating sharp transition and an injected spike is a
sharp transition. If the elevation comes from those two, the stratum is not
measuring unfamiliarity, it is measuring undeclared contamination, and the
right response is to fix the evaluation set rather than the detector.

Two readings, and they are mutually exclusive:

  one   the elevation is carried by random_walk, whose unpredictability is
        mathematically intrinsic and has no corresponding injected defect. The
        characterisation is clean and the claim can be finalised.
  two   the elevation is carried by staircase and sawtooth. The stratum is ill
        defined and should be scoped out or rebuilt by form.

This also asks whether shift_strength could tell a staircase from an injected
level_shift even in principle, by counting jumps in each.

CPU only, no TSFM needed: behavioural risk is read from the traces of the run
that measured it.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, OOD_KINDS, build_corpus  # noqa: E402
from stratum_risk import mann_whitney  # noqa: E402

from introact_ts.actions import changepoints, robust_scale  # noqa: E402

TRACES = ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"


def jump_profile(x: np.ndarray) -> dict:
    """How many level jumps, and how regularly spaced.

    Regularity is the coefficient of variation of the gaps between jumps. A
    generated staircase places its edges at random, so its gaps are irregular
    too, which is the point of measuring it rather than assuming.
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 32:
        return {"n_jumps": 0, "gap_cv": float("nan"), "max_step": 0.0}
    cps = changepoints(x)
    scale = max(robust_scale(x), 1e-9)
    steps = []
    edges = [0] + list(cps) + [len(x)]
    for i in range(len(edges) - 2):
        a = x[edges[i]:edges[i + 1]]
        b = x[edges[i + 1]:edges[i + 2]]
        if len(a) >= 4 and len(b) >= 4:
            steps.append(abs(float(np.median(b)) - float(np.median(a))) / scale)
    gaps = np.diff(cps) if len(cps) >= 2 else np.array([])
    return {
        "n_jumps": int(len(cps)),
        "gap_cv": float(np.std(gaps) / max(np.mean(gaps), 1e-9)) if len(gaps) else float("nan"),
        "max_step": float(max(steps)) if steps else 0.0,
    }


def main():
    if not TRACES.exists():
        print("deferred, no xl traces on disk")
        return
    spec = CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                      n_rare_valid=210, n_changepoint=210, n_clean_ood=210,
                      seed=42)
    allw = build_corpus(spec, source="ett")
    wins = {w.window_id: w for w in allw}
    oodw = [w for w in allw if w.stratum == "clean_ood"]
    form = {w.window_id: OOD_KINDS[i % len(OOD_KINDS)] for i, w in enumerate(oodw)}

    traces = json.loads(TRACES.read_text(encoding="utf-8"))["introact_full"]
    by_form = {k: [] for k in OOD_KINDS}
    contam = [t for t in traces if t["stratum"] == "contaminated"]
    for t in traces:
        if t["stratum"] == "clean_ood":
            by_form[form[t["window_id"]]].append(t)

    ref = [t["behav_risk"] for t in contam]
    print(f"{'form':14s}{'n':>4s}{'p25':>9s}{'median':>9s}{'p75':>9s}{'IQR':>8s}"
          f"{'auc vs contam':>15s}{'p':>10s}{'edited':>8s}{'destr':>7s}")
    rows = {}
    for k in OOD_KINDS:
        g = by_form[k]
        br = [t["behav_risk"] for t in g]
        q = np.percentile(br, [25, 50, 75])
        mw = mann_whitney(br, ref)
        mod = [t for t in g if t.get("modified")]
        destr = 0
        for t in mod:
            w = wins[t["window_id"]]
            src = w.series[t["crop_offset"]:]
            if len(src) >= 8 and np.isfinite(w.series).all():
                # compare against the span the operator kept, so a crop is not
                # counted as destruction
                pass
            destr += 1 if any(s["action"] == "DESPIKE" for s in t["steps"]
                              if s["verdict"] == "ACCEPTED") else 0
        rows[k] = {"n": len(g), "median": q[1], "auc": mw["auc"], "p": mw["p"],
                   "edited": len(mod), "despike": destr}
        print(f"{k:14s}{len(g):4d}{q[0]:+9.3f}{q[1]:+9.3f}{q[2]:+9.3f}{q[2]-q[0]:8.3f}"
              f"{mw['auc']:15.3f}{mw['p']:10.2e}{len(mod):8d}{destr:7d}")

    print(f"\ncontaminated reference median {np.median(ref):+.3f}, n {len(ref)}")

    print("\ndominant_defect by form, the statistical profile's verdict")
    print(f"{'form':14s}{'shift':>7s}{'noise':>7s}{'spike':>7s}{'missing':>9s}{'none':>7s}")
    for k in OOD_KINDS:
        c = Counter(t["dominant_defect"] for t in by_form[k])
        print(f"{k:14s}{c.get('shift',0):7d}{c.get('noise',0):7d}{c.get('spike',0):7d}"
              f"{c.get('missing',0):9d}{c.get('none',0):7d}")

    print("\nhypothesis by form")
    for k in OOD_KINDS:
        c = Counter(t["hypothesis"] for t in by_form[k])
        print(f"  {k:14s}{dict(c)}")

    # The decisive split: drop the two colliding forms and see what is left.
    print("\nthe elevation with each form removed")
    all_ood = [t["behav_risk"] for t in traces if t["stratum"] == "clean_ood"]
    print(f"  all four forms      median {np.median(all_ood):+.3f}  "
          f"auc {mann_whitney(all_ood, ref)['auc']:.3f}")
    keep = [t["behav_risk"] for k in ("random_walk", "pulse_train") for t in by_form[k]]
    mw = mann_whitney(keep, ref)
    print(f"  random_walk+pulse   median {np.median(keep):+.3f}  "
          f"auc {mw['auc']:.3f}  p {mw['p']:.2e}")
    coll = [t["behav_risk"] for k in ("staircase", "sawtooth") for t in by_form[k]]
    mw2 = mann_whitney(coll, ref)
    print(f"  staircase+sawtooth  median {np.median(coll):+.3f}  "
          f"auc {mw2['auc']:.3f}  p {mw2['p']:.2e}")

    # Can shift_strength separate a staircase from an injected level_shift?
    print("\njump structure, staircase against injected level_shift")
    ls = [t for t in contam if t.get("contamination") == "level_shift"]
    groups = {
        "staircase": [wins[t["window_id"]].series for t in by_form["staircase"]],
        "sawtooth": [wins[t["window_id"]].series for t in by_form["sawtooth"]],
        "random_walk": [wins[t["window_id"]].series for t in by_form["random_walk"]],
        "level_shift(inj)": [wins[t["window_id"]].series for t in ls],
    }
    print(f"{'group':18s}{'n':>4s}{'jumps p25':>11s}{'median':>9s}{'p75':>9s}{'max_step med':>14s}")
    prof = {}
    for name, series in groups.items():
        p = [jump_profile(s) for s in series]
        nj = np.array([x["n_jumps"] for x in p], float)
        ms = np.array([x["max_step"] for x in p], float)
        q = np.percentile(nj, [25, 50, 75])
        prof[name] = nj
        print(f"{name:18s}{len(p):4d}{q[0]:11.1f}{q[1]:9.1f}{q[2]:9.1f}"
              f"{np.median(ms):14.2f}")
    sep = mann_whitney(prof["staircase"], prof["level_shift(inj)"])
    print(f"\n  staircase against injected level_shift on jump count: "
          f"auc {sep['auc']:.3f}, p {sep['p']:.2e}")
    separable = sep["auc"] > 0.75 or sep["auc"] < 0.25

    rw, sc, sw = rows["random_walk"], rows["staircase"], rows["sawtooth"]
    colliding_higher = max(sc["median"], sw["median"]) > rw["median"]
    verdict = ("two, the elevation is carried by the colliding forms"
               if colliding_higher else
               "one, the elevation is carried by random_walk")
    print(f"\nverdict: reading {verdict}")
    print(f"shift_strength separable in principle: {separable} "
          f"(auc {sep['auc']:.3f}, needs to clear 0.75 or fall below 0.25)")


if __name__ == "__main__":
    main()
