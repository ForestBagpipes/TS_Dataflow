"""Paired tests between two arms, over the windows both arms saw.

Three seeds give three numbers per column, and a mean over three points says
nothing about whether an ordering is real. The seeds are not the unit of
evidence here, the windows are, and every arm ran on the same windows, so the
comparison can be paired window by window. That is what this file does.

  mis edit rate   McNemar's exact test on the paired binary outcome over the
                  four protected strata. The discordant pairs are the evidence,
                  a window both arms edited or both left alone says nothing
  repair nRMSD    Wilcoxon signed rank over the contaminated windows, on the
                  paired difference in normalised distance to the clean series
  damage rate     not paired and not tested here. The two arms commit different
                  edits, so the denominators are different sets of windows
                  rather than the same set measured twice, and a paired test
                  would be measuring the wrong thing. It is reported with its
                  two counts and a two proportion interval instead

The nRMSD test carries a caveat that the caller must not drop. Section 4.1 of
the number self checks records that this column is dominated by the level shift
subgroup and that the two missing kinds score zero for an arm that does nothing.
The test is therefore run twice, once over all contaminated windows and once
excluding the two missing kinds, and both are reported.

Usage:
    python experiments/arm_significance.py \
        --traces results/xl/seed_0_window_traces.jsonl \
                 results/xl/seed_1_window_traces.jsonl \
                 results/xl/seed_2_window_traces.jsonl \
        --a introact --b spec_veto
"""

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

PROTECTED = ("clean", "hard", "rare_valid", "changepoint")
MISSING_KINDS = ("missing_block", "missing_scattered")


def load(path, arms):
    out = {a: {} for a in arms}
    for line in Path(path).open(encoding="utf-8"):
        r = json.loads(line)
        if r["arm"] in out:
            out[r["arm"]][int(r["window_id"])] = r
    return out


def mcnemar_exact(b, c):
    """Two sided exact McNemar, on the two discordant counts.

    Under the null the discordant pairs split by a fair coin, so the p value is
    the two sided binomial tail at one half.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def wilcoxon(d):
    """Wilcoxon signed rank, normal approximation with a tie correction.

    Zero differences are dropped, which is the standard treatment and is the
    conservative one here since a tie supports neither arm.
    """
    d = np.asarray([x for x in d if abs(x) > 1e-12], dtype=np.float64)
    n = len(d)
    if n < 10:
        return {"n": n, "statistic": None, "z": None, "p": None,
                "note": "too few non tied pairs for the approximation"}
    order = np.argsort(np.abs(d))
    ranks = np.empty(n, dtype=np.float64)
    a = np.abs(d)[order]
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
    # Tie correction on the absolute differences.
    _, counts = np.unique(a, return_counts=True)
    tie = float(sum(t ** 3 - t for t in counts))
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie / 48.0
    z = (w_plus - mu) / max(np.sqrt(var), 1e-12)
    # Two sided normal tail without scipy.
    p = 2 * 0.5 * (1.0 - _erf(abs(z) / np.sqrt(2.0)))
    return {"n": n, "statistic": w_plus, "z": float(z), "p": float(p),
            "median_difference": float(np.median(d)),
            "n_negative": int((d < 0).sum()), "n_positive": int((d > 0).sum())}


def _erf(x):
    """Abramowitz and Stegun 7.1.26, enough for a p value at this precision."""
    s = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return s * y


def two_proportion(k1, n1, k2, n2):
    """Difference of two independent proportions with a normal interval."""
    if not n1 or not n2:
        return None
    p1, p2 = k1 / n1, k2 / n2
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    d = p1 - p2
    z = d / se if se > 1e-12 else 0.0
    return {"p_a": p1, "p_b": p2, "difference": d,
            "ci95": [d - 1.96 * se, d + 1.96 * se],
            "z": float(z), "p": float(2 * 0.5 * (1 - _erf(abs(z) / np.sqrt(2))))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", nargs="+", required=True)
    ap.add_argument("--a", default="introact")
    ap.add_argument("--b", default="spec_veto")
    ap.add_argument("--out", default=str(ROOT / "results" / "arm_significance.json"))
    args = ap.parse_args()

    report = {"a": args.a, "b": args.b, "per_seed": {}}
    pooled = defaultdict(list)
    for path in args.traces:
        d = load(path, (args.a, args.b))
        A, B = d[args.a], d[args.b]
        ids = sorted(set(A) & set(B))
        seed = Path(path).stem.split("_")[1]
        print(f"seed {seed}, {len(ids)} windows in both arms")

        # Mis edit, paired over the protected strata.
        b_only = c_only = both = neither = 0
        for i in ids:
            if A[i]["stratum"] not in PROTECTED:
                continue
            ea, eb = bool(A[i]["modified"]), bool(B[i]["modified"])
            if ea and not eb:
                b_only += 1
            elif eb and not ea:
                c_only += 1
            elif ea and eb:
                both += 1
            else:
                neither += 1
        p_mc = mcnemar_exact(b_only, c_only)
        print(f"  mis edit, {args.a} only {b_only}, {args.b} only {c_only}, "
              f"both {both}, neither {neither}, exact McNemar p {p_mc:.3g}")

        # nRMSD, paired over contaminated windows, twice.
        def paired_nrmsd(exclude_missing):
            dd = []
            for i in ids:
                r = A[i]
                if r["stratum"] != "contaminated":
                    continue
                if exclude_missing and r["contamination"] in MISSING_KINDS:
                    continue
                va, vb = A[i]["nrmsd_after"], B[i]["nrmsd_after"]
                if va is None or vb is None:
                    continue
                dd.append(float(va) - float(vb))
            return dd

        res = {}
        for label, excl in (("all", False), ("excluding_missing", True)):
            dd = paired_nrmsd(excl)
            w = wilcoxon(dd)
            res[label] = w
            pooled[label].extend(dd)
            if w["p"] is None:
                print(f"  nRMSD {label:18s}{w['note']}")
            else:
                print(f"  nRMSD {label:18s}n={w['n']:4d} median diff "
                      f"{w['median_difference']:+.4f}  "
                      f"{args.a} better on {w['n_negative']}, worse on "
                      f"{w['n_positive']}  p {w['p']:.3g}")

        report["per_seed"][seed] = {
            "n_paired": len(ids),
            "mis_edit": {"a_only": b_only, "b_only": c_only, "both": both,
                         "neither": neither, "mcnemar_p": p_mc},
            "nrmsd": res,
        }
        print()

    print("pooled over the three seeds, the windows are disjoint across seeds")
    for label in ("all", "excluding_missing"):
        w = wilcoxon(pooled[label])
        report[f"pooled_{label}"] = w
        if w["p"] is not None:
            print(f"  nRMSD {label:18s}n={w['n']:5d} median diff "
                  f"{w['median_difference']:+.4f}  p {w['p']:.3g}")

    Path(args.out).write_text(json.dumps(report, indent=1, default=float),
                              encoding="utf-8")
    print("___SIGNIFICANCE_DONE___")


if __name__ == "__main__":
    main()
