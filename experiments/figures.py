"""Figures that do not need a GPU, built from cached runs.

Two of them, both arguing the same point from different angles.

The pareto view puts utility gained against collateral damage, because a
single net number cannot express a method whose selling point is what it
declines to do.

The risk coverage curve asks whether the agent knows when it is unsure. Order
windows by the confidence of the risk state, edit only the most confident
fraction, and plot the error rate of those edits against the fraction covered.
A method whose confidence is meaningful has an error rate that rises with
coverage. A flat curve means the confidence carries no information and the
refusal path is decoration.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from audit import _nmse, replay_method  # noqa: E402
from corpus import CorpusSpec, build_corpus  # noqa: E402

PARETO_METHODS = [
    "no_action", "always_clean", "stat_only", "quality_rank",
    "introact_full", "ablate_no_verify", "ablate_no_structure",
    "ablate_no_reprobe", "ablate_no_protection",
]


def pareto_points(summary: dict) -> list:
    rows = []
    for m, r in summary["results"].items():
        ce = r.get("corpus_effect", {})
        rows.append({
            "method": m,
            "gain": ce.get("net_reduction", 0.0),
            "worsened": ce.get("windows_worsened", 0),
            "damage": r["protection"]["mean_damage"],
            "over_clean": r["protection"]["over_clean_rate"],
        })
    return rows


def frontier(rows, x="worsened", y="gain") -> list:
    """Methods not strictly dominated on more gain with no more damage."""
    keep = []
    for r in rows:
        dominated = any(
            o[y] >= r[y] and o[x] <= r[x] and (o[y] > r[y] or o[x] < r[x])
            for o in rows if o["method"] != r["method"]
        )
        if not dominated:
            keep.append(r["method"])
    return sorted(keep)


def risk_coverage(traces: list, windows: list, method: str) -> dict:
    """Error rate among edited windows as a function of how many are edited.

    Windows are ordered by the confidence the risk state assigned them. An edit
    counts as an error if the window ended further from the truth than it
    started.
    """
    byid = {w.window_id: w for w in windows}
    replayed = replay_method(traces[method], windows, method)
    rows = []
    for t in traces[method]:
        wid = t["window_id"]
        w, rep = byid.get(wid), replayed.get(wid)
        if w is None or rep is None or w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before = _nmse(w.series, w.clean_series, ref_var)
        after = _nmse(rep["final_series"], w.clean_series[rep["crop_offset"]:], ref_var)
        edited = bool(t["modified"])
        if not edited:
            continue
        rows.append({
            "confidence": float(
                t.get("confidence")
                if t.get("confidence") is not None
                else (t.get("risk_state") or {}).get("confidence", 0.0)
            ),
            "error": bool(after > before + 1e-9),
        })
    if not rows:
        return {"n": 0}

    rows.sort(key=lambda r: -r["confidence"])
    n = len(rows)
    cov, err = [], []
    running = 0
    for i, r in enumerate(rows, start=1):
        running += int(r["error"])
        cov.append(i / n)
        err.append(running / i)
    return {"n": n, "coverage": cov, "error_rate": err,
            "confidence_spread": float(np.ptp([r["confidence"] for r in rows]))}


def main():
    runs = {
        "xl": ("results/xl/xl_ett_multi-family_seed42",
               CorpusSpec(n_contaminated=740, n_clean=420, n_hard=210,
                          n_rare_valid=210, n_changepoint=210, n_clean_ood=210)),
        "heavy": ("results/gpu/heavy_ett_multi-family_seed42",
                  CorpusSpec(n_contaminated=140, n_clean=20, n_hard=10,
                             n_rare_valid=20, n_changepoint=10, n_clean_ood=10)),
        "small": ("results/gpu/small_ett_multi-family_seed42",
                  CorpusSpec(n_contaminated=35, n_clean=20, n_hard=10,
                             n_rare_valid=10, n_changepoint=10, n_clean_ood=10)),
    }
    lines = ["# Figures from cached runs", ""]
    fig_data = {}

    for label, (stem, spec) in runs.items():
        sfile = ROOT / f"{stem}.json"
        tfile = ROOT / f"{stem}_traces.json"
        if not sfile.exists():
            lines += [f"## {label}", "", "deferred, no cached run", ""]
            continue
        summary = json.loads(sfile.read_text(encoding="utf-8"))
        rows = pareto_points(summary)
        front = frontier(rows)
        fig_data[label] = {"pareto": rows, "frontier": front}

        lines += [f"## {label} pareto, gain against damage", ""]
        lines.append("| method | net gain | windows worsened | over clean | damage | on frontier |")
        lines.append("|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: -r["gain"]):
            mark = "yes" if r["method"] in front else ""
            lines.append(
                f"| {r['method']} | {r['gain']:+.3f} | {r['worsened']} "
                f"| {r['over_clean']:.3f} | {r['damage']:.4f} | {mark} |"
            )
        lines.append("")

        if tfile.exists():
            traces = json.loads(tfile.read_text(encoding="utf-8"))
            windows = build_corpus(spec, source="ett")
            rc = risk_coverage(traces, windows, "introact_full")
            fig_data[label]["risk_coverage"] = rc
            lines += [f"## {label} risk coverage, introact_full", ""]
            if rc.get("n"):
                lines.append(
                    f"{rc['n']} edited windows ordered by risk state confidence. "
                    f"Confidence spread across them {rc['confidence_spread']:.3f}."
                )
                lines.append("")
                lines.append("| coverage | error rate among edits |")
                lines.append("|---|---|")
                for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
                    i = max(0, int(frac * rc["n"]) - 1)
                    lines.append(f"| {rc['coverage'][i]:.2f} | {rc['error_rate'][i]:.3f} |")
                lines.append("")
                if rc["confidence_spread"] < 1e-6:
                    lines.append(
                        "Confidence is constant across edited windows here, so the "
                        "curve carries no information. Cached traces store the risk "
                        "state only at window level and the field may be absent, "
                        "which the next run fixes."
                    )
                    lines.append("")
            else:
                lines.append("no edited windows with ground truth")
                lines.append("")

    (ROOT / "results" / "figures.json").write_text(
        json.dumps(fig_data, indent=2, default=float), encoding="utf-8")
    dest = ROOT / "results" / "figures.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written {dest}")


if __name__ == "__main__":
    main()
