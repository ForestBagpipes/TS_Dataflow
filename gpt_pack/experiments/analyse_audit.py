"""The two analyses that decide component three.

Protocol from `docs/veto_evaluation_protocol.md`, readings from
`docs/component3_verdict_criteria.md`, both committed before the data existed.

Analysis one is per proposer, merged over seeds: contaminated precision against
that proposer's own harm rate, and protected recall against its own overall
veto rate.

Analysis two pools by structural path and tests the path itself. That is the
question at issue and it doubles the sample on each side. Candidate quality is
already balanced across the pairs, so the path is close to the only variable
that differs.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, fisher_exact

ROOT = Path(__file__).resolve().parent.parent
PROT = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def precision_test(rows):
    """Veto precision on contaminated windows against the blind baseline."""
    rs = [r for r in rows if r["stratum"] == "contaminated"]
    if not rs:
        return None
    n = len(rs)
    harm = sum(r["harmful"] for r in rs)
    vet = [r for r in rs if r["vetoed"]]
    tp = sum(r["harmful"] for r in vet)
    base = harm / n
    prec = tp / max(len(vet), 1)
    p = (binomtest(tp, len(vet), base, alternative="greater").pvalue
         if vet else float("nan"))
    return {"n": n, "harmful": harm, "vetoed": len(vet), "tp": tp,
            "precision": prec, "baseline": base, "lift": prec - base, "p": p}


def recall_test(rows):
    """Veto recall on protected windows against the overall veto rate."""
    rs = [r for r in rows if r["stratum"] in PROT]
    if not rs:
        return None
    vet = sum(r["vetoed"] for r in rs)
    overall = sum(r["vetoed"] for r in rows) / max(len(rows), 1)
    rec = vet / len(rs)
    p = binomtest(vet, len(rs), overall, alternative="greater").pvalue
    return {"n": len(rs), "vetoed": vet, "recall": rec,
            "baseline": overall, "lift": rec - overall, "p": p}


def path_test(local_rows, global_rows):
    """Does the local path discriminate better than the global path?

    Compared on contaminated windows only, where there is discriminative room.
    Each side is scored as lift over its own harm rate, since the two paths face
    different candidate mixes, and the difference between the two lifts is what
    the path contributes. A Fisher exact test on the two by two of vetoed
    against harmful gives the significance for each side.
    """
    out = {}
    for label, rows in [("local", local_rows), ("global", global_rows)]:
        rs = [r for r in rows if r["stratum"] == "contaminated"]
        vh = sum(1 for r in rs if r["vetoed"] and r["harmful"])
        vn = sum(1 for r in rs if r["vetoed"] and not r["harmful"])
        ah = sum(1 for r in rs if not r["vetoed"] and r["harmful"])
        an = sum(1 for r in rs if not r["vetoed"] and not r["harmful"])
        odds, p = fisher_exact([[vh, vn], [ah, an]], alternative="greater")
        base = (vh + ah) / max(len(rs), 1)
        prec = vh / max(vh + vn, 1)
        out[label] = {"n": len(rs), "precision": prec, "baseline": base,
                      "lift": prec - base, "odds_ratio": float(odds),
                      "p_vs_blind": float(p),
                      "table": {"veto_harm": vh, "veto_benign": vn,
                                "accept_harm": ah, "accept_benign": an}}
    # Comparing the two paths means comparing their odds ratios, not their
    # rejected piles. The earlier version tested whether the two rejected sets
    # looked alike, which is a different question and answered it correctly
    # while being the wrong question to ask.
    lt, gt = out["local"]["table"], out["global"]["table"]
    out["local_vs_global"] = interaction_test(lt, gt)
    return out


def interaction_test(t_local, t_global):
    """Is the association between veto and harm different across the paths?

    Two routes, both reported. Breslow Day tests homogeneity of the odds ratios
    across the two strata directly. The log odds ratio difference gives an
    effect size with an interval, using the Woolf standard error. A half is
    added to every cell for the standard error only, which is the usual
    correction and matters when a cell is small.
    """
    from scipy.stats import chi2

    def cells(t):
        return (t["veto_harm"], t["veto_benign"],
                t["accept_harm"], t["accept_benign"])

    a1, b1, c1, d1 = cells(t_local)
    a2, b2, c2, d2 = cells(t_global)
    lor1 = np.log(((a1 + .5) * (d1 + .5)) / ((b1 + .5) * (c1 + .5)))
    lor2 = np.log(((a2 + .5) * (d2 + .5)) / ((b2 + .5) * (c2 + .5)))
    se1 = np.sqrt(1 / (a1 + .5) + 1 / (b1 + .5) + 1 / (c1 + .5) + 1 / (d1 + .5))
    se2 = np.sqrt(1 / (a2 + .5) + 1 / (b2 + .5) + 1 / (c2 + .5) + 1 / (d2 + .5))
    diff = lor1 - lor2
    se = float(np.sqrt(se1 ** 2 + se2 ** 2))
    z = diff / se
    from scipy.stats import norm
    p_wald = float(2 * norm.sf(abs(z)))

    # Breslow Day, homogeneity of odds ratios under a common estimate.
    n1, n2 = a1 + b1 + c1 + d1, a2 + b2 + c2 + d2
    num = (a1 + c1) * (a2 + c2)
    mh_num = (a1 * d1 / n1) + (a2 * d2 / n2)
    mh_den = (b1 * c1 / n1) + (b2 * c2 / n2)
    or_mh = mh_num / mh_den if mh_den > 0 else float("nan")
    bd = float("nan")
    if np.isfinite(or_mh) and or_mh > 0:
        stat = 0.0
        for (a, b, c, d, n) in [(a1, b1, c1, d1, n1), (a2, b2, c2, d2, n2)]:
            r1, r2 = a + b, c + d
            k1 = a + c
            A = or_mh - 1.0
            B = or_mh * (r1 + k1) + (r2 - k1)
            C = -or_mh * r1 * k1
            aa = ((-B + np.sqrt(B * B - 4 * A * C)) / (2 * A)) if abs(A) > 1e-12                 else (r1 * k1 / max(r1 + r2, 1))
            bb, cc, dd = r1 - aa, k1 - aa, r2 - k1 + aa
            var = 1.0 / max(1e-12, (1 / max(aa, 1e-9) + 1 / max(bb, 1e-9)
                                    + 1 / max(cc, 1e-9) + 1 / max(dd, 1e-9)))
            stat += (a - aa) ** 2 / max(var, 1e-12)
        bd = float(1 - chi2.cdf(stat, df=1))
    return {"log_odds_local": float(lor1), "log_odds_global": float(lor2),
            "log_odds_difference": float(diff), "se": se, "z": float(z),
            "p_wald": p_wald, "p_breslow_day": bd,
            "odds_ratio_local": float(np.exp(lor1)),
            "odds_ratio_global": float(np.exp(lor2)),
            "ci95_difference": [float(diff - 1.96 * se), float(diff + 1.96 * se)]}


def main():
    path = ROOT / "results" / "audit_seeds.json"
    if not path.exists():
        print("deferred, no audit_seeds.json")
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    rec, PATH = d["records"], d["path"]
    print(f"seeds {d['seeds']}, records "
          f"{ {k: len(v) for k, v in rec.items()} }\n")

    print("A. contaminated precision, per proposer, the discriminative test")
    print(f"{'proposer':16s}{'n':>6s}{'vetoed':>8s}{'precision':>11s}"
          f"{'baseline':>10s}{'lift':>8s}{'p':>11s}")
    for k in ["stat_only", "always_clean", "screen", "imr"]:
        r = precision_test(rec.get(k, []))
        if r:
            print(f"{k:16s}{r['n']:6d}{r['vetoed']:8d}{r['precision']:11.3f}"
                  f"{r['baseline']:10.3f}{r['lift']:+8.3f}{r['p']:11.2e}")

    print("\nB. protected recall, per proposer, the safety test")
    print(f"{'proposer':16s}{'n':>6s}{'vetoed':>8s}{'recall':>9s}"
          f"{'baseline':>10s}{'lift':>8s}{'p':>11s}")
    for k in ["stat_only", "always_clean", "screen", "imr"]:
        r = recall_test(rec.get(k, []))
        if r:
            print(f"{k:16s}{r['n']:6d}{r['vetoed']:8d}{r['recall']:9.3f}"
                  f"{r['baseline']:10.3f}{r['lift']:+8.3f}{r['p']:11.2e}")

    print("\nC. path stratified, the test of the variable at issue")
    loc = [r for k, v in rec.items() if PATH[k] == "local" for r in v]
    glo = [r for k, v in rec.items() if PATH[k] == "global" for r in v]
    pt = path_test(loc, glo)
    for label in ["local", "global"]:
        r = pt[label]
        print(f"  {label:8s} n {r['n']:5d}  precision {r['precision']:.3f}  "
              f"baseline {r['baseline']:.3f}  lift {r['lift']:+.3f}  "
              f"odds {r['odds_ratio']:.3f}  p vs blind {r['p_vs_blind']:.2e}")
        print(f"           table {r['table']}")
    lg = pt["local_vs_global"]
    print(f"  interaction, local against global")
    print(f"    odds ratio local {lg['odds_ratio_local']:.3f}, "
          f"global {lg['odds_ratio_global']:.3f}")
    print(f"    log odds difference {lg['log_odds_difference']:+.3f} "
          f"CI95 [{lg['ci95_difference'][0]:+.3f}, {lg['ci95_difference'][1]:+.3f}]")
    print(f"    Wald p {lg['p_wald']:.2e}, Breslow Day p {lg['p_breslow_day']:.2e}")

    beats_blind = pt["local"]["p_vs_blind"] < 0.05
    beats_global = min(lg["p_wald"], lg["p_breslow_day"]) < 0.05
    reading = ("one, local beats blind and the interaction is significant"
               if beats_blind and beats_global
               else "two, interaction significant but local does not beat blind"
               if beats_global
               else "four, local beats blind, interaction not significant"
               if beats_blind else "three, neither")
    print(f"\nreading: {reading}")

    (ROOT / "results" / "audit_analysis.json").write_text(
        json.dumps({"per_proposer": {
            k: {"precision": precision_test(rec.get(k, [])),
                "recall": recall_test(rec.get(k, []))}
            for k in PATH}, "path": pt, "reading": reading},
            indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
