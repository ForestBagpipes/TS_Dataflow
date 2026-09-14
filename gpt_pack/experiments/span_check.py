"""Does aligning the scored span rescue the utility signal for RESEGMENT?

The audit found the whole of the negative return on refusals sitting in one
operator: twelve RESEGMENT rejections, eight of them wrong, a net of -37.64
against +27.75 for IMPUTE. The proposed cause is mechanical rather than a
threshold. RESEGMENT is the only operator that changes the length of the
window, so the post edit probe scores a different segment than the pre edit
probe did, and their difference is not a measurement of anything.

This tests that directly and offline. For every window where RESEGMENT applies:

  delta_u_current   utility after minus before, each scored on the last H
                    points of whatever series it was handed, which is what the
                    agent used
  delta_u_aligned   both scored on the same absolute segment, the tail of the
                    retained span, so the only difference between them is
                    whether the discarded stretch was still in the context
  delta_nmse        what actually happened to the distance from truth, which
                    neither the agent nor the probe can see

If the alignment is the problem, delta_u_aligned should agree with delta_nmse
where delta_u_current does not.

Run with the offline surrogate. It is a mechanism test, not a claim about what
a pretrained checkpoint does, and the confirming numbers have to come from the
next GPU session.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from corpus import CorpusSpec, build_corpus  # noqa: E402

from introact_ts.actions import apply_action  # noqa: E402
from introact_ts.probe import ProbeConfig, probe_window, reference_scale  # noqa: E402
from introact_ts.tsfm import make_model_pool  # noqa: E402
from introact_ts.types import Action  # noqa: E402
from introact_ts.verify import VerifyConfig  # noqa: E402


def nmse(series, clean, ref_var):
    n = min(len(series), len(clean))
    x = np.nan_to_num(np.asarray(series, dtype=np.float64)[:n])
    c = np.asarray(clean, dtype=np.float64)[:n]
    x = x - np.median(x)
    c = c - np.median(c)
    if ref_var < 1e-12:
        return float(np.mean((x - c) ** 2))
    return float(np.mean((x - c) ** 2) / ref_var)


def collect(windows, models, cfg):
    rows = []
    for w in windows:
        if w.clean_series is None:
            continue
        outcome = apply_action(w.series, Action.RESEGMENT)
        if not outcome.applicable:
            continue
        lo, hi = int(outcome.params["lo"]), int(outcome.params["hi"])
        scale = reference_scale(w.series)
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))

        u_before_free = probe_window(w.series, models, scale, cfg).utility
        u_after = probe_window(outcome.series, models, scale, cfg).utility
        # Same absolute segment on both sides. The cropped series scored over
        # its whole length already is that segment, so only the before side
        # needs pinning.
        u_before_aligned = probe_window(w.series, models, scale, cfg, region=(lo, hi)).utility

        rows.append(
            {
                "window_id": w.window_id,
                "contamination": w.contamination or w.stratum,
                "keep_frac": float(outcome.params["keep_frac"]),
                "delta_u_current": u_after - u_before_free,
                "delta_u_aligned": u_after - u_before_aligned,
                "delta_nmse": nmse(w.series, w.clean_series, ref_var)
                - nmse(outcome.series, w.clean_series[lo:], ref_var),
            }
        )
    return rows


def report(rows, eps):
    cur = np.array([r["delta_u_current"] for r in rows])
    ali = np.array([r["delta_u_aligned"] for r in rows])
    truth = np.array([r["delta_nmse"] for r in rows])
    helps = truth > 1e-12

    def agreement(du):
        accept = du > eps
        return {
            "accept_rate": float(np.mean(accept)),
            "agree": float(np.mean(accept == helps)),
            "wrongly_refused": int(np.sum(helps & ~accept)),
            "wrongly_accepted": int(np.sum(~helps & accept)),
            "forgone": float(np.sum(truth[helps & ~accept])),
            "corr": float(np.corrcoef(du, truth)[0, 1]) if len(du) > 2 else float("nan"),
        }

    out = ["# RESEGMENT span alignment check", ""]
    out.append(f"Offline surrogate. {len(rows)} windows where RESEGMENT applies, "
               f"of which {int(helps.sum())} would move the window toward truth.")
    out.append(f"Acceptance threshold epsilon {eps}.")
    out.append("")
    out.append("| utility definition | accepts | agrees with truth | wrongly refused | wrongly accepted | gain forgone | corr with truth |")
    out.append("|---|---|---|---|---|---|---|")
    for name, du in (("current, free span", cur), ("aligned span", ali)):
        a = agreement(du)
        out.append(
            f"| {name} | {a['accept_rate']:.2f} | {a['agree']:.2f} "
            f"| {a['wrongly_refused']} | {a['wrongly_accepted']} "
            f"| {a['forgone']:.2f} | {a['corr']:+.3f} |"
        )
    out.append("")

    out.append("Per window, sorted by how much truth improvement was available.")
    out.append("")
    out.append("| window | contamination | keep frac | delta nmse | delta u current | delta u aligned |")
    out.append("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -r["delta_nmse"])[:20]:
        out.append(
            f"| {r['window_id']} | {r['contamination']} | {r['keep_frac']:.2f} "
            f"| {r['delta_nmse']:+.3f} | {r['delta_u_current']:+.4f} "
            f"| {r['delta_u_aligned']:+.4f} |"
        )
    out.append("")
    return "\n".join(out) + "\n", agreement(cur), agreement(ali)


def main():
    spec = CorpusSpec(n_contaminated=140, n_clean=20, n_hard=10,
                      n_rare_valid=20, n_changepoint=10, n_clean_ood=10, seed=42)
    windows = build_corpus(spec, source="ett")
    models = make_model_pool((0, 1, 2))
    cfg = ProbeConfig()
    rows = collect(windows, models, cfg)
    text, cur, ali = report(rows, VerifyConfig().epsilon)
    dest = ROOT / "results" / "span_check.md"
    dest.write_text(text, encoding="utf-8")
    print(text)
    print(f"written {dest}")


if __name__ == "__main__":
    main()
