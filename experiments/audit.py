"""Offline audit of curation decisions against ground truth.

The agent decides with no access to the truth. The evaluator has it. This
module exploits that asymmetry to ask the question the acceptance rule cannot
ask of itself: when a candidate edit was rejected, would applying it actually
have moved the window closer to the pristine reference?

That splits every rejection into two very different things:

  correctly refused   the edit would have left the window no better or worse,
                      so the veto preserved data that a less careful pipeline
                      would have damaged
  wrongly refused     the edit would have improved the window, so the veto
                      threw away real utility

The ratio between them decides whether a low repair rate is a defensible
operating point or a mis calibrated threshold, and it has to be measured before
anyone touches epsilon.

Everything here runs on CPU from cached run artefacts plus the corpus, which is
rebuilt deterministically from its seed. No model is loaded and no forward pass
is issued.

Replay and its one approximation
--------------------------------
Trace summaries record which actions were attempted and how each was judged,
but not the parameters each was called with. Those are recovered from the
policy proposal order, which is fixed: IMPUTE is offered linear before
seasonal, DENOISE light before medium. The nth occurrence of an operator in a
window therefore takes the nth parameter set. This is exact for the operators
that carry no parameters and for the first occurrence of every operator, and it
is an inference for later repeats.

The replay is self checking. Reconstructing each final series from the accepted
actions must reproduce the repair numbers already recorded in the run summary.
:func:`verify_replay` reports that agreement, and a large disagreement means
the audit below should not be trusted.
"""

import numpy as np

from introact_ts.actions import apply_action
from introact_ts.types import Action, MUTATING_ACTIONS

#: Parameter sequences the policy offers, in the order it offers them.
#: Mirrors PolicyConfig.impute_methods and PolicyConfig.denoise_ladder.
PARAM_ORDER = {
    "IMPUTE": [{"method": "linear"}, {"method": "seasonal"}],
    "DENOISE": [{"strength": "light"}, {"strength": "medium"}],
}

#: The baselines in experiments.baselines do not consult the policy. They run a
#: fixed plan, so their operators take the module defaults, which differ from
#: the policy's first proposal. Replaying them with the policy order is what
#: made always_clean miss its recorded repair number by 0.023.
BASELINE_PARAMS = {
    "IMPUTE": [{}],
    "DENOISE": [{"strength": "medium"}],
}

BASELINE_METHODS = ("no_action", "always_clean", "stat_only", "quality_rank")

ROLLBACK_VERDICTS = (
    "ROLLED_BACK_UTILITY",
    "ROLLED_BACK_STRUCTURE",
    "ROLLED_BACK_RISK",
)


def _nmse(series, clean, ref_var):
    """Normalised distance to truth, matching experiments.metrics._mse_to_clean."""
    n = min(len(series), len(clean))
    x = np.asarray(series, dtype=np.float64)[:n]
    c = np.asarray(clean, dtype=np.float64)[:n]
    if n == 0:
        return float("nan")
    x = np.nan_to_num(x, nan=float(np.nanmedian(x)) if np.isfinite(x).any() else 0.0)
    x = x - np.median(x)
    c = c - np.median(c)
    if ref_var < 1e-12:
        return float(np.mean((x - c) ** 2))
    return float(np.mean((x - c) ** 2) / ref_var)


def replay_window(summary: dict, window, param_mode: str = "policy") -> dict:
    """Re-run one window's recorded action sequence and score every candidate.

    ``param_mode`` selects how operator parameters are recovered, either the
    policy proposal order or the fixed baseline defaults.

    Returns the reconstructed final series plus one record per attempted action
    carrying what the edit would have done to the distance from truth.
    """
    table = BASELINE_PARAMS if param_mode == "baseline" else PARAM_ORDER
    clean = window.clean_series
    has_truth = clean is not None
    ref_var = (
        float(np.var(np.asarray(clean) - np.median(clean))) if has_truth else 1.0
    )

    work = np.asarray(window.series, dtype=np.float64).copy()
    offset = 0
    seen = {}
    records = []

    for action_name, verdict in zip(summary["attempted"], summary["verdicts"]):
        idx = seen.get(action_name, 0)
        seen[action_name] = idx + 1
        params_list = table.get(action_name, [{}])
        params = params_list[min(idx, len(params_list) - 1)]

        action = Action(action_name)
        rec = {
            "window_id": summary["window_id"],
            "stratum": summary["stratum"],
            "contamination": summary["contamination"],
            "action": action_name,
            "params": dict(params),
            "verdict": verdict,
            "param_inferred": idx > 0 and action_name in table,
        }

        if action not in MUTATING_ACTIONS or verdict == "NO_OP":
            rec.update(applicable=False, nmse_before=None, nmse_after=None,
                       would_improve=None, delta_nmse=None)
            records.append(rec)
            continue

        outcome = apply_action(work, action, **params)
        if not outcome.applicable:
            rec.update(applicable=False, nmse_before=None, nmse_after=None,
                       would_improve=None, delta_nmse=None)
            records.append(rec)
            continue

        crop = int(outcome.params.get("lo", 0)) if action is Action.RESEGMENT else 0
        if has_truth:
            before = _nmse(work, clean[offset:], ref_var)
            after = _nmse(outcome.series, clean[offset + crop :], ref_var)
            rec.update(
                applicable=True,
                nmse_before=before,
                nmse_after=after,
                delta_nmse=before - after,
                would_improve=bool(after < before - 1e-12),
            )
        else:
            rec.update(applicable=True, nmse_before=None, nmse_after=None,
                       would_improve=None, delta_nmse=None)

        if verdict == "ACCEPTED":
            work = outcome.series
            offset += crop
        records.append(rec)

    return {"final_series": work, "crop_offset": offset, "records": records}


def replay_method(traces: list, windows: list, method: str = "") -> dict:
    """Replay every window of one method."""
    mode = "baseline" if method in BASELINE_METHODS else "policy"
    byid = {w.window_id: w for w in windows}
    out = {}
    for t in traces:
        w = byid.get(t["window_id"])
        if w is None:
            continue
        out[t["window_id"]] = replay_window(t, w, param_mode=mode)
    return out


def verify_replay(replayed: dict, windows: list, reported: dict) -> dict:
    """Check the replay against the repair numbers the run already recorded.

    If these disagree, the parameter inference or the replay order is wrong and
    nothing downstream should be believed.
    """
    byid = {w.window_id: w for w in windows}
    before, after = [], []
    for wid, r in replayed.items():
        w = byid[wid]
        if w.stratum != "contaminated" or w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before.append(_nmse(w.series, w.clean_series, ref_var))
        after.append(_nmse(r["final_series"], w.clean_series[r["crop_offset"] :], ref_var))
    if not before:
        return {"n": 0}
    b, a = float(np.mean(before)), float(np.mean(after))
    replay_reduction = 1.0 - a / max(b, 1e-12)
    reported_reduction = reported.get("repair", {}).get("reduction", float("nan"))
    return {
        "n": len(before),
        "replay_reduction": replay_reduction,
        "reported_reduction": reported_reduction,
        "abs_error": abs(replay_reduction - reported_reduction),
    }


def audit_rejections(replayed: dict) -> dict:
    """Classify every rejected edit as correctly or wrongly refused."""
    rows = [
        r
        for rep in replayed.values()
        for r in rep["records"]
        if r["verdict"] in ROLLBACK_VERDICTS and r.get("applicable")
    ]
    if not rows:
        return {"n_rejections": 0}

    wrong = [r for r in rows if r["would_improve"]]
    right = [r for r in rows if not r["would_improve"]]

    def group(rows_in, key):
        out = {}
        for r in rows_in:
            k = r[key] or "none"
            d = out.setdefault(k, {"n": 0, "wrong": 0, "forgone": [], "avoided": []})
            d["n"] += 1
            if r["would_improve"]:
                d["wrong"] += 1
                d["forgone"].append(r["delta_nmse"])
            else:
                d["avoided"].append(-r["delta_nmse"])
        for d in out.values():
            d["wrong_rate"] = d["wrong"] / max(d["n"], 1)
            d["mean_forgone_gain"] = float(np.mean(d["forgone"])) if d["forgone"] else 0.0
            d["mean_avoided_harm"] = float(np.mean(d["avoided"])) if d["avoided"] else 0.0
            # Totals matter more than means here. One stratum carries an error
            # five times any other, so a mean hides whether the refusals cost
            # more in aggregate than they saved.
            d["total_forgone_gain"] = float(np.sum(d["forgone"])) if d["forgone"] else 0.0
            d["total_avoided_harm"] = float(np.sum(d["avoided"])) if d["avoided"] else 0.0
            d["median_forgone_gain"] = float(np.median(d["forgone"])) if d["forgone"] else 0.0
            d["net"] = d["total_avoided_harm"] - d["total_forgone_gain"]
            d.pop("forgone"), d.pop("avoided")
        return dict(sorted(out.items()))

    by_verdict = {}
    for r in rows:
        d = by_verdict.setdefault(r["verdict"], {"n": 0, "wrong": 0})
        d["n"] += 1
        d["wrong"] += int(r["would_improve"])
    for d in by_verdict.values():
        d["wrong_rate"] = d["wrong"] / max(d["n"], 1)

    forgone = [r["delta_nmse"] for r in wrong]
    avoided = [-r["delta_nmse"] for r in right]
    return {
        "median_forgone_gain": float(np.median(forgone)) if forgone else 0.0,
        "median_avoided_harm": float(np.median(avoided)) if avoided else 0.0,
        "net_of_refusing": (float(np.sum(avoided)) if avoided else 0.0)
        - (float(np.sum(forgone)) if forgone else 0.0),
        "n_rejections": len(rows),
        "n_wrongly_refused": len(wrong),
        "wrong_rate": len(wrong) / len(rows),
        "mean_forgone_gain": float(np.mean(forgone)) if forgone else 0.0,
        "total_forgone_gain": float(np.sum(forgone)) if forgone else 0.0,
        "mean_avoided_harm": float(np.mean(avoided)) if avoided else 0.0,
        "total_avoided_harm": float(np.sum(avoided)) if avoided else 0.0,
        "by_action": group(rows, "action"),
        "by_contamination": group(rows, "contamination"),
        "by_verdict": by_verdict,
        "n_param_inferred": sum(1 for r in rows if r["param_inferred"]),
    }


def audit_acceptances(replayed: dict) -> dict:
    """The mirror question: of the edits committed, how many actually helped?"""
    rows = [
        r
        for rep in replayed.values()
        for r in rep["records"]
        if r["verdict"] == "ACCEPTED" and r.get("applicable")
    ]
    if not rows:
        return {"n_acceptances": 0}
    good = [r for r in rows if r["would_improve"]]
    return {
        "n_acceptances": len(rows),
        "n_helpful": len(good),
        "precision": len(good) / len(rows),
        "mean_gain": float(np.mean([r["delta_nmse"] for r in good])) if good else 0.0,
        "mean_loss": float(
            np.mean([-r["delta_nmse"] for r in rows if not r["would_improve"]])
        )
        if len(good) < len(rows)
        else 0.0,
    }


def ledger_by_contamination(replayed: dict, windows: list) -> dict:
    """Full per contamination ledger for one method.

    Reported per contamination rather than as a corpus mean because the mean is
    dominated by whichever stratum carries the largest absolute error, and on
    this corpus that is level_shift by a factor of five.
    """
    byid = {w.window_id: w for w in windows}
    groups = {}
    for wid, rep in replayed.items():
        w = byid[wid]
        if w.clean_series is None:
            continue
        key = w.contamination or w.stratum
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        before = _nmse(w.series, w.clean_series, ref_var)
        after = _nmse(rep["final_series"], w.clean_series[rep["crop_offset"] :], ref_var)
        edited = any(
            r["verdict"] == "ACCEPTED" and Action(r["action"]) in MUTATING_ACTIONS
            for r in rep["records"]
        )
        d = groups.setdefault(
            key,
            {"n": 0, "before": [], "after": [], "edited": 0, "improved": 0, "worsened": 0},
        )
        d["n"] += 1
        d["before"].append(before)
        d["after"].append(after)
        d["edited"] += int(edited)
        if after < before - 1e-9:
            d["improved"] += 1
        elif after > before + 1e-9:
            d["worsened"] += 1

    out = {}
    for k, d in sorted(groups.items()):
        b, a = float(np.mean(d["before"])), float(np.mean(d["after"]))
        touched = d["improved"] + d["worsened"]
        out[k] = {
            "n": d["n"],
            "nmse_before": b,
            "nmse_after": a,
            "reduction": 1.0 - a / max(b, 1e-12),
            "abs_gain_total": float(np.sum(d["before"]) - np.sum(d["after"])),
            "edited": d["edited"],
            "edit_rate": d["edited"] / max(d["n"], 1),
            "improved": d["improved"],
            "worsened": d["worsened"],
            "edit_precision": d["improved"] / touched if touched else float("nan"),
        }
    return out
