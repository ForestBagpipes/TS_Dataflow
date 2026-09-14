"""Do the two utility definitions disagree, and where.

The method optimises model utility, the change in how a frozen TSFM behaves on
a window. The evaluation so far has scored fidelity, the distance from a
pristine reference. Those are different objectives and the audit suggests they
part company on defects a strong model is robust to.

This measures both on the runs already on disk, so it costs nothing and it
tells the contamination sweep where to put its points.

  model utility   final_utility minus initial_utility, as recorded by the run.
                  Real TSFM numbers, already cached
  fidelity        reduction in normalised distance to the pristine reference,
                  recomputed offline from the replayed final series

Both are reported per contamination, never as a corpus mean, because one
stratum carries 78 percent of the corpus error and a mean is that stratum under
another name.
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

RUNS = {
    "small, 37 percent contaminated": {
        "traces": "results/gpu/small_ett_multi-family_seed42_traces.json",
        "spec": CorpusSpec(n_contaminated=35, n_clean=20, n_hard=10,
                           n_rare_valid=10, n_changepoint=10, n_clean_ood=10),
    },
    "heavy, 67 percent contaminated": {
        "traces": "results/gpu/heavy_ett_multi-family_seed42_traces.json",
        "spec": CorpusSpec(n_contaminated=140, n_clean=20, n_hard=10,
                           n_rare_valid=20, n_changepoint=10, n_clean_ood=10),
    },
}

METHODS = ["introact_full", "stat_only", "always_clean"]


def both_rulers(traces, windows, method):
    replayed = replay_method(traces[method], windows, method)
    byid = {w.window_id: w for w in windows}
    util = {t["window_id"]: t["delta_utility"] for t in traces[method]}

    groups = {}
    for wid, rep in replayed.items():
        w = byid[wid]
        if w.clean_series is None:
            continue
        key = w.contamination or w.stratum
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before = _nmse(w.series, w.clean_series, ref_var)
        after = _nmse(rep["final_series"], w.clean_series[rep["crop_offset"] :], ref_var)
        d = groups.setdefault(key, {"n": 0, "before": [], "after": [], "du": []})
        d["n"] += 1
        d["before"].append(before)
        d["after"].append(after)
        d["du"].append(util.get(wid, 0.0))

    out = {}
    for k, d in sorted(groups.items()):
        b, a = float(np.mean(d["before"])), float(np.mean(d["after"]))
        # A stratum that starts at zero distance has no error to remove, so a
        # relative gain is a division by nothing. What matters there is the
        # absolute distance the pipeline introduced.
        repairable = b > 1e-6
        out[k] = {
            "n": d["n"],
            "repairable": repairable,
            "fidelity_gain": (1.0 - a / b) if repairable else None,
            "damage": None if repairable else a,
            "model_utility_gain": float(np.mean(d["du"])),
            "nmse_before": b,
        }
    return out


def main():
    lines = ["# Two rulers, model utility against fidelity", ""]
    lines.append("Model utility is the change a frozen TSFM registers, as recorded by")
    lines.append("the run. Fidelity is the reduction in distance to the pristine")
    lines.append("reference, recomputed offline. A positive fidelity gain with a flat")
    lines.append("model utility is a repair the target model did not need.")
    lines.append("")

    for label, run in RUNS.items():
        path = ROOT / run["traces"]
        if not path.exists():
            lines.append(f"## {label}")
            lines.append("")
            lines.append("deferred, no cached traces")
            lines.append("")
            continue
        traces = json.loads(path.read_text(encoding="utf-8"))
        windows = build_corpus(run["spec"], source="ett")

        lines.append(f"## {label}")
        lines.append("")
        for m in METHODS:
            if m not in traces:
                continue
            res = both_rulers(traces, windows, m)
            lines.append(f"### {m}")
            lines.append("")
            lines.append("| stratum | n | nmse before | fidelity gain | damage introduced | model utility gain |")
            lines.append("|---|---|---|---|---|---|")
            for k, v in res.items():
                gain = f"{v['fidelity_gain']:+.3f}" if v["repairable"] else "n/a"
                dmg = "n/a" if v["repairable"] else f"{v['damage']:.4f}"
                lines.append(
                    f"| {k} | {v['n']} | {v['nmse_before']:.4f} "
                    f"| {gain} | {dmg} | {v['model_utility_gain']:+.4f} |"
                )
            lines.append("")
    dest = ROOT / "results" / "two_rulers.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written {dest}")


if __name__ == "__main__":
    main()
