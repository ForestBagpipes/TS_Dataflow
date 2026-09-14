"""Repair nRMSD split by contamination kind, which is how this column reads.

The single mean over the injected layer is dominated by one subgroup. Level
shift is 14 percent of the windows and carries 62 percent of the mean, so an
arm's position in that column is mostly its level shift behaviour reported
under a general name. The ruling is to report the column by kind rather than to
change the metric, and to build the headline number from the kinds that are
sound.

Two kinds are not sound and are excluded from the headline with the reason
attached rather than dropped quietly. `missing_block` and `missing_scattered`
are measured by a distance that discards non finite differences, so a window
with a hole in it sits at distance zero from the truth and any imputation can
only move it away. An arm that fills nothing scores perfectly on them. Their
numbers are still printed, they are just not ranked and not averaged into the
headline.

The headline is therefore a **window count weighted mean over the non missing
kinds**, which is the same quantity as the plain mean over those windows, and
it is written that way so the weighting is visible rather than implied.

Every ordering carries a paired test. Three seeds are three points and cannot
support an ordering on their own; the windows are the unit of evidence and
every arm saw the same ones, so the arms are compared window by window with a
Wilcoxon signed rank over the paired difference.

No GPU, no model, no rerun. Reads the JSONL the main runs already flushed.

Usage:
    python experiments/nrmsd_by_contamination.py \
        --traces results/xl/seed_0_window_traces.jsonl \
                 results/xl/seed_1_window_traces.jsonl \
                 results/xl/seed_2_window_traces.jsonl
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

#: Excluded from the headline mean, and never ranked. See the module docstring.
UNSOUND_KINDS = ("missing_block", "missing_scattered")

#: Arm order for the printed tables, the frozen matrix's order.
ARMS = ("L0_no_action", "L1_screen", "L2_imr", "L3_mtcsc", "L7_learn2clean",
        "utility_only", "spec_veto", "introact", "oracle")


def _erf(x):
    """Abramowitz and Stegun 7.1.26, sufficient for a p value at this precision."""
    s = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return s * y


def wilcoxon(d):
    """Wilcoxon signed rank, normal approximation with a tie correction."""
    d = np.asarray([x for x in d if abs(x) > 1e-12], dtype=np.float64)
    n = len(d)
    if n < 10:
        return {"n": n, "p": None, "note": "too few non tied pairs"}
    order = np.argsort(np.abs(d))
    a = np.abs(d)[order]
    ranks = np.empty(n, dtype=np.float64)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and a[j + 1] == a[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    signs = np.sign(d)[order]
    w_plus = float(ranks[signs > 0].sum())
    mu = n * (n + 1) / 4.0
    _, counts = np.unique(a, return_counts=True)
    var = n * (n + 1) * (2 * n + 1) / 24.0 - float(
        sum(t ** 3 - t for t in counts)) / 48.0
    z = (w_plus - mu) / max(np.sqrt(var), 1e-12)
    # The series approximation to erf saturates, so a large z returns exactly
    # zero. A p value of zero cannot be written in a paper, it is reported as
    # below the floor the approximation can resolve.
    p = float(1.0 - _erf(abs(z) / np.sqrt(2.0)))
    return {"n": n, "z": float(z),
            "p": p, "p_floored": p < 1e-15,
            "median_difference": float(np.median(d)),
            "n_negative": int((d < 0).sum()), "n_positive": int((d > 0).sum())}


def load_seed(path):
    """Per arm, per contamination kind, the window id to nRMSD map.

    Only the injected layer carries a contamination kind, and only it is scored
    for repair, so everything else is dropped here.
    """
    out = defaultdict(lambda: defaultdict(dict))
    kinds = set()
    for line in Path(path).open(encoding="utf-8"):
        r = json.loads(line)
        if r["stratum"] != "contaminated":
            continue
        kind = r["contamination"]
        if kind is None or r["nrmsd_after"] is None:
            continue
        kinds.add(kind)
        out[r["arm"]][kind][int(r["window_id"])] = float(r["nrmsd_after"])
    return out, kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", nargs="+", required=True)
    ap.add_argument("--out", default=str(ROOT / "results" / "nrmsd_by_contamination.json"))
    args = ap.parse_args()

    seeds = []
    all_kinds = set()
    for p in args.traces:
        d, k = load_seed(p)
        seeds.append((Path(p).stem, d))
        all_kinds |= k
    kinds = sorted(all_kinds)
    arms = [a for a in ARMS if a in seeds[0][1]]
    extra = sorted(set(seeds[0][1]) - set(ARMS))
    if extra:
        print(f"arms present in the traces but not in the printed order: {extra}")

    print(f"{len(seeds)} seeds, {len(kinds)} contamination kinds, "
          f"{len(arms)} arms")
    print(f"kinds found in the traces: {kinds}")
    print()

    # Per kind, per arm, the mean over that seed's windows, then mean and std
    # over the seeds. The seed is the replicate for the spread, the window is
    # the replicate inside a seed.
    table = {}
    counts = {}
    for kind in kinds:
        table[kind] = {}
        for arm in arms:
            vals = [float(np.mean(list(d[arm][kind].values())))
                    for _, d in seeds if d[arm][kind]]
            if not vals:
                continue
            table[kind][arm] = {"mean": float(np.mean(vals)),
                                "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
                                "per_seed": vals}
        per_seed_n = [len(d[arms[0]][kind]) for _, d in seeds]
        counts[kind] = {"per_seed": per_seed_n, "total": int(sum(per_seed_n))}

    width = 15
    print("nRMSD by contamination kind, mean over seeds plus or minus the "
          "sample standard deviation")
    print(f"{'kind':22s}{'n':>6s}" + "".join(f"{a[:13]:>{width}s}" for a in arms))
    for kind in kinds:
        mark = " *" if kind in UNSOUND_KINDS else ""
        row = f"{kind + mark:22s}{counts[kind]['total']:6d}"
        for arm in arms:
            c = table[kind].get(arm)
            row += (f"{c['mean']:9.4f}+-{c['std']:.3f}" if c
                    else f"{'n/a':>{width}s}")
        print(row)
    print("* excluded from the headline and never ranked, see the docstring")

    # The headline. A window count weighted mean over the sound kinds is the
    # plain mean over those windows, computed that way so it cannot drift from
    # the per kind table above.
    print()
    print("headline, the sound kinds only, window count weighted")
    sound = [k for k in kinds if k not in UNSOUND_KINDS]
    headline = {}
    for arm in arms:
        per_seed = []
        for _, d in seeds:
            vals = [v for k in sound for v in d[arm][k].values()]
            if vals:
                per_seed.append(float(np.mean(vals)))
        if not per_seed:
            continue
        headline[arm] = {"mean": float(np.mean(per_seed)),
                         "std": float(np.std(per_seed, ddof=1)) if len(per_seed) > 1 else 0.0,
                         "per_seed": per_seed,
                         "n_windows_per_seed": [
                             sum(len(d[arm][k]) for k in sound) for _, d in seeds]}
        h = headline[arm]
        print(f"  {arm:16s}{h['mean']:8.4f} +- {h['std']:.4f}   "
              f"n per seed {h['n_windows_per_seed']}")

    # Every ordering that will be stated gets a paired test behind it.
    print()
    print("introact against spec_veto, paired by window, per kind, pooled over "
          "seeds")
    print("n discordant counts only the windows where the two arms produced a "
          "different result, since a window neither arm touched carries no "
          "evidence either way")
    print(f"{'kind':22s}{'n paired':>10s}{'n discordant':>14s}"
          f"{'median diff':>14s}{'introact better':>18s}{'p':>12s}")
    tests = {}
    for kind in kinds + ["ALL_SOUND"]:
        ks = sound if kind == "ALL_SOUND" else [kind]
        diffs = []
        for _, d in seeds:
            a, b = d["introact"], d["spec_veto"]
            for k in ks:
                for wid, va in a[k].items():
                    if wid in b[k]:
                        diffs.append(va - b[k][wid])
        w = wilcoxon(diffs)
        w["n_paired"] = len(diffs)
        tests[kind] = w
        mark = " *" if kind in UNSOUND_KINDS else ""
        if w.get("p") is None:
            print(f"{kind + mark:22s}{len(diffs):10d}{w['n']:14d}"
                  f"{'':>14s}{'':>18s}{w.get('note', ''):>12s}")
        else:
            ps = "<1e-15" if w["p_floored"] else f"{w['p']:.3g}"
            print(f"{kind + mark:22s}{len(diffs):10d}{w['n']:14d}"
                  f"{w['median_difference']:+14.4f}"
                  f"{w['n_negative']:11d} of {w['n_negative'] + w['n_positive']:4d}"
                  f"{ps:>12s}")

    blob = {"traces": [str(p) for p in args.traces],
            "unsound_kinds": list(UNSOUND_KINDS),
            "counts": counts, "by_kind": table, "headline": headline,
            "introact_vs_spec_veto": tests}
    Path(args.out).write_text(json.dumps(blob, indent=1, default=float),
                              encoding="utf-8")
    print()
    print("___NRMSD_BY_KIND_DONE___")


if __name__ == "__main__":
    main()
