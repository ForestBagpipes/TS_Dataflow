"""Behavioural risk by stratum, the distribution behind the headline figure.

The single most consequential number from the 2000 window run is that clean out
of distribution windows carry seven times the behavioural risk of contaminated
ones. A median is not enough to put in a paper, so this produces the full
distribution per stratum, the same for the statistical profile as a control,
and a significance test for each protected stratum against the contaminated one.

The control matters. If the statistical profile showed the same inversion, the
finding would be about the corpus rather than about model behaviour.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

TRACES = ROOT / "results" / "xl" / "xl_ett_multi-family_seed42_traces.json"
ORDER = ["contaminated", "clean", "hard", "rare_valid", "changepoint",
         "clean_ood", "real_ood"]


def mann_whitney(a, b):
    """Two sided rank sum test with a normal approximation, plus the effect size.

    The effect size is the common language statistic, the probability that a
    random draw from a exceeds a random draw from b, which is also the AUROC of
    a against b, so it reads on the same scale as everything else here.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return {"n1": n1, "n2": n2, "auc": float("nan"), "z": float("nan"),
                "p": float("nan")}
    both = np.concatenate([a, b])
    order = np.argsort(both)
    ranks = np.empty(len(both), float)
    ranks[order] = np.arange(1, len(both) + 1)
    vals, inv, cnt = np.unique(both, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]

    r1 = ranks[:n1].sum()
    u1 = r1 - n1 * (n1 + 1) / 2.0
    auc = u1 / (n1 * n2)
    mu = n1 * n2 / 2.0
    tie = np.sum(cnt**3 - cnt)
    n = n1 + n2
    sigma2 = n1 * n2 / 12.0 * ((n + 1) - tie / (n * (n - 1)))
    sigma = float(np.sqrt(max(sigma2, 1e-12)))
    z = (u1 - mu) / sigma
    from math import erfc, sqrt

    p = erfc(abs(z) / sqrt(2.0))
    return {"n1": n1, "n2": n2, "auc": float(auc), "z": float(z), "p": float(p)}


def describe(values):
    v = np.asarray(values, float)
    q = np.percentile(v, [5, 25, 50, 75, 95])
    return {
        "n": int(len(v)),
        "mean": float(v.mean()),
        "p05": float(q[0]), "p25": float(q[1]), "median": float(q[2]),
        "p75": float(q[3]), "p95": float(q[4]),
        "min": float(v.min()), "max": float(v.max()),
    }


def main():
    if not TRACES.exists():
        print(f"deferred, no traces at {TRACES}")
        return
    traces = json.loads(TRACES.read_text(encoding="utf-8"))["introact_full"]

    by = {}
    for t in traces:
        by.setdefault(t["stratum"], {"behav": [], "stat": []})
        by[t["stratum"]]["behav"].append(t["behav_risk"])
        by[t["stratum"]]["stat"].append(t["defect_strength"])

    present = [s for s in ORDER if s in by] + [s for s in by if s not in ORDER]
    payload = {"strata": {}, "tests": {}}
    for s in present:
        payload["strata"][s] = {
            "behavioural_risk": describe(by[s]["behav"]),
            "statistical_risk": describe(by[s]["stat"]),
            "raw_behavioural": [float(x) for x in by[s]["behav"]],
        }

    ref = by.get("contaminated")
    for s in present:
        if s == "contaminated" or ref is None:
            continue
        payload["tests"][s] = {
            "behavioural": mann_whitney(by[s]["behav"], ref["behav"]),
            "statistical": mann_whitney(by[s]["stat"], ref["stat"]),
        }

    lines = ["# Behavioural risk by stratum", ""]
    lines.append("From the 2000 window run with real TSFMs. Behavioural risk is the")
    lines.append("peer calibrated quantity the policy conditions on. The statistical")
    lines.append("column is the control: if it showed the same inversion the finding")
    lines.append("would be about the corpus rather than about model behaviour.")
    lines.append("")
    lines.append("| stratum | n | p05 | p25 | median | p75 | p95 | statistical median |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in present:
        d = payload["strata"][s]["behavioural_risk"]
        sd = payload["strata"][s]["statistical_risk"]
        lines.append(
            f"| {s} | {d['n']} | {d['p05']:+.3f} | {d['p25']:+.3f} "
            f"| **{d['median']:+.3f}** | {d['p75']:+.3f} | {d['p95']:+.3f} "
            f"| {sd['median']:.3f} |"
        )
    lines.append("")

    lines.append("## Each protected stratum against the contaminated one")
    lines.append("")
    lines.append("`auc` is the probability that a window from this stratum scores higher")
    lines.append("than a contaminated one. Above 0.5 means the protected stratum alarms")
    lines.append("the model more than actual contamination does.")
    lines.append("")
    lines.append("| stratum | behaviour auc | z | p | statistics auc | p |")
    lines.append("|---|---|---|---|---|---|")
    for s, t in payload["tests"].items():
        b, st = t["behavioural"], t["statistical"]
        lines.append(
            f"| {s} | **{b['auc']:.3f}** | {b['z']:+.1f} | {b['p']:.2e} "
            f"| {st['auc']:.3f} | {st['p']:.2e} |"
        )
    lines.append("")

    inverted = [s for s, t in payload["tests"].items()
                if t["behavioural"]["auc"] > 0.5 and t["behavioural"]["p"] < 0.05]
    lines.append(
        f"Strata that alarm the model significantly more than contamination does: "
        f"{', '.join(inverted) if inverted else 'none'}."
    )
    lines.append("")
    stat_inverted = [s for s, t in payload["tests"].items()
                     if t["statistical"]["auc"] > 0.5 and t["statistical"]["p"] < 0.05]
    lines.append(
        f"Same question for the statistical profile: "
        f"{', '.join(stat_inverted) if stat_inverted else 'none'}."
    )
    lines.append("")

    (ROOT / "results" / "behavior_risk_by_stratum.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    dest = ROOT / "docs" / "behavior_risk_by_stratum.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written {dest}")


if __name__ == "__main__":
    main()
