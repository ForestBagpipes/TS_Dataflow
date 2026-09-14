"""What evidence actually triggered the off target candidates.

The routing purity table showed DESPIKE landing on 23 windows whose true
contamination is a gap, and IMPUTE landing on 52 whose true contamination is a
duplicate or a spike. A mechanism was proposed for the first of those, that the
probe's forward fill turns a gap into a plateau whose edges read as spikes, and
that mechanism is wrong: `risk.statistical_evidence` reads the raw series and
`missing_mask` does not fill anything. The forward fill lives in
`probe._naive_fill`, downstream of the evidence.

So the real trigger is unknown and this measures it. Each off target candidate
is reconnected to its window by id, the statistical evidence is recomputed from
the series, and the four indicators the router reads are reported next to the
true contamination kind.

**Ground truth appears here and nowhere else.** This is a diagnosis. Any routing
change may only use the evidence dictionary, which is available at deployment.
A deployment path that consulted the true contamination kind would be the sixth
instance of calibrating on a population that does not exist at run time.

Usage:
    python experiments/reconnect_misroute.py
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402

from introact_ts.risk import (CorpusReference, DEFECT_KEYS,  # noqa: E402
                              EVIDENCE_KEY, statistical_evidence)

INTENDED = {
    "DESPIKE": ("spike",),
    "IMPUTE": ("missing_block", "missing_scattered", "flatline"),
    "DENOISE": ("noise",),
    "RESEGMENT": ("level_shift",),
}
IND = ("missing_frac", "spike_frac", "noise_ratio", "shift_strength")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--corpus-seed", dest="corpus_seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--out", default=str(ROOT / "results" / "misroute_evidence.json"))
    args = ap.parse_args()

    windows, _ = build_calibration(n=args.n, seed=args.corpus_seed,
                                   source=args.source, verbose=True)
    byid = {int(w.window_id): w for w in windows}

    rows = []
    for line in Path(args.scores).open(encoding="utf-8"):
        rec = json.loads(line)
        for c in rec["candidates"]:
            c["window_id"] = int(rec["window_id"])
            rows.append(c)

    # Evidence is a pure statistic of the series, so it is recomputed here
    # rather than requiring a perception pass.
    ref = CorpusReference()
    ev_cache = {}
    for wid, w in byid.items():
        ev = statistical_evidence(np.asarray(w.series, dtype=np.float64))
        units = ref.units(ev)
        ev_cache[wid] = (ev, units)

    con = [r for r in rows if r["stratum"] == "contaminated"]
    print(f"{len(con)} candidates on contaminated windows")

    print()
    print("off target candidates, the evidence that routed them")
    print(f"{'family':10s}{'true kind':20s}{'n':>5s}" +
          "".join(f"{k[:12]:>14s}" for k in IND) +
          f"{'dominant':>14s}{'2nd':>12s}")
    detail = defaultdict(list)
    for fam in sorted(INTENDED):
        want = INTENDED[fam]
        sub = [r for r in con if r["family"] == fam
               and str(r["contamination"]) not in want]
        by_kind = defaultdict(list)
        for r in sub:
            by_kind[str(r["contamination"])].append(r)
        for kind, group in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
            meds = {}
            doms, seconds = [], []
            for r in group:
                ev, units = ev_cache[r["window_id"]]
                for k in IND:
                    meds.setdefault(k, []).append(float(ev.get(k, 0.0)))
                order = sorted(DEFECT_KEYS, key=lambda d: -units[d])
                doms.append(order[0])
                seconds.append(order[1] if len(order) > 1 else "")
                detail[fam].append({
                    "window_id": r["window_id"], "true_kind": kind,
                    "loss": r["loss"], "rung": r.get("rung"),
                    **{k: float(ev.get(k, 0.0)) for k in IND},
                    "dominant": order[0], "second": order[1],
                    "dominant_units": float(units[order[0]]),
                })
            from collections import Counter
            dc, sc = Counter(doms).most_common(1)[0], Counter(seconds).most_common(1)[0]
            print(f"{fam:10s}{kind:20s}{len(group):5d}" +
                  "".join(f"{np.median(meds[k]):14.4f}" for k in IND) +
                  f"{dc[0] + ' ' + str(dc[1]):>14s}{sc[0] + ' ' + str(sc[1]):>12s}")

    # The two specific questions.
    print()
    print("question 1: is DESPIKE on a gap window triggered by missing evidence")
    ds = [d for d in detail["DESPIKE"] if d["true_kind"].startswith("missing")]
    if ds:
        dom = defaultdict(int)
        for d in ds:
            dom[d["dominant"]] += 1
        print(f"  {len(ds)} such candidates, dominant defect: {dict(dom)}")
        print(f"  median missing_frac {np.median([d['missing_frac'] for d in ds]):.4f}, "
              f"median spike_frac {np.median([d['spike_frac'] for d in ds]):.4f}")
        print(f"  candidates whose dominant defect is 'spike': "
              f"{sum(1 for d in ds if d['dominant'] == 'spike')}")
        print(f"  candidates whose dominant defect is 'missing': "
              f"{sum(1 for d in ds if d['dominant'] == 'missing')}")
        print("  if the dominant defect is spike while missing_frac is high, a "
              "missing aware suppression has something to act on; if the "
              "dominant defect is already missing, the candidate came from the "
              "secondary slot and the fix is different")
    else:
        print("  none")

    print()
    print("question 2: do IMPUTE's off target windows carry real gaps anyway")
    isub = [d for d in detail["IMPUTE"]
            if d["true_kind"] in ("duplicate", "spike", "level_shift")]
    if isub:
        withgap = [d for d in isub if d["missing_frac"] > 1e-9]
        print(f"  {len(isub)} off target candidates, "
              f"{len(withgap)} on windows with a non zero missing fraction")
        if withgap:
            print(f"  their median missing_frac "
                  f"{np.median([d['missing_frac'] for d in withgap]):.4f}, "
                  f"median loss {np.median([d['loss'] for d in withgap]):.4f}")
        nogap = [d for d in isub if d["missing_frac"] <= 1e-9]
        if nogap:
            print(f"  {len(nogap)} on windows with no gap at all, "
                  f"median loss {np.median([d['loss'] for d in nogap]):.4f}")
        print("  IMPUTE only rewrites genuinely missing positions, so a "
              "candidate on a window with no gap can only be a NO_OP or a "
              "flatline rewrite; that distinction decides whether a routing "
              "rule would change anything")
    else:
        print("  none")

    Path(args.out).write_text(json.dumps(
        {"detail": {k: v for k, v in detail.items()}}, indent=1,
        default=float), encoding="utf-8")
    print()
    print("___MISROUTE_EVIDENCE_DONE___")


if __name__ == "__main__":
    main()
