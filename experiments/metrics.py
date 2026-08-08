"""Evaluation metrics for a curation run.

The metrics are organised around what the paper has to establish, not around
what is easy to compute. In particular, repair quality and over-cleaning are
reported separately and neither is allowed to stand in for the other: a policy
that repairs everything scores well on the first and terribly on the second,
which is exactly the failure mode a quality-score-only method cannot see.
"""

import numpy as np

from corpus import ORACLE_ACTION

PROTECTED_STRATA = ("clean", "hard", "rare_valid", "changepoint", "clean_ood")


def _align(a: np.ndarray, b: np.ndarray) -> tuple:
    n = min(len(a), len(b))
    return np.asarray(a)[:n], np.asarray(b)[:n]


def _mse_to_clean(
    series: np.ndarray, clean: np.ndarray, ref_var: float = None
) -> float:
    """Distance to the pristine reference, in units a TSFM would recognise.

    Two choices here decide whether the number means anything.

    Both series are centred before comparison, because a foundation model
    instance-normalises its input: a segment displaced by a constant is not
    degraded data as far as the model is concerned, it is the same data at a
    different offset. Scoring the raw values would report a correct RESEGMENT
    -- which keeps an internally consistent stretch that happens to sit at a
    shifted level -- as catastrophic damage.

    The normalising variance comes from the *full* reference window and is
    passed in unchanged for the before and after measurement. Using each
    series' own variance would shrink the denominator whenever a crop removed
    the most variable part, manufacturing a regression out of an improvement.
    """
    x, c = _align(series, clean)
    x = np.nan_to_num(x, nan=float(np.nanmedian(x)) if np.isfinite(x).any() else 0.0)
    x = x - np.median(x)
    c = c - np.median(c)
    var = float(ref_var if ref_var is not None else np.var(c))
    if var < 1e-12:
        return float(np.mean((x - c) ** 2))
    return float(np.mean((x - c) ** 2) / var)


def detection_metrics(traces: list) -> dict:
    """How well the risk state identifies which windows are actually corrupted."""
    y_true = np.asarray([t.stratum == "contaminated" for t in traces])
    y_pred = np.asarray([t.risk_state["hypothesis"] == "contaminated" for t in traces])
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    scores = np.asarray([t.risk_state["behav_risk"] for t in traces])
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "behav_risk_auroc": auroc(scores, y_true),
    }


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUROC; 0.5 when one class is absent."""
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=bool)
    n_pos, n_neg = int(labels.sum()), int((~labels).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=np.float64)
    # Average ranks within ties.
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def action_metrics(traces: list) -> dict:
    """Did the agent pick the operator the contamination actually calls for?"""
    hits, total, per_kind = 0, 0, {}
    for t in traces:
        if t.stratum != "contaminated":
            continue
        oracle = ORACLE_ACTION.get(t.contamination)
        accepted = [a.value for a in t.accepted_actions]
        total += 1
        ok = oracle in accepted
        hits += int(ok)
        d = per_kind.setdefault(t.contamination, {"n": 0, "hit": 0, "repaired": 0})
        d["n"] += 1
        d["hit"] += int(ok)
        d["repaired"] += int(bool(accepted))
    return {
        "action_accuracy": hits / max(total, 1),
        "n_contaminated": total,
        "per_contamination": per_kind,
    }


def repair_metrics(traces: list, windows: list) -> dict:
    """Normalised distance to the pristine reference, before and after."""
    byid = {w.window_id: w for w in windows}
    before, after, per_kind = [], [], {}
    for t in traces:
        if t.stratum != "contaminated":
            continue
        w = byid.get(t.window_id)
        if w is None or w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        b = _mse_to_clean(t.initial_series, w.clean_series, ref_var)
        a = _mse_to_clean(t.final_series, w.clean_series[t.crop_offset :], ref_var)
        before.append(b)
        after.append(a)
        d = per_kind.setdefault(t.contamination, {"before": [], "after": []})
        d["before"].append(b)
        d["after"].append(a)

    if not before:
        return {"n": 0}
    before_m, after_m = float(np.mean(before)), float(np.mean(after))
    return {
        "n": len(before),
        "nmse_before": before_m,
        "nmse_after": after_m,
        "reduction": 1.0 - after_m / max(before_m, 1e-12),
        "worsened_frac": float(np.mean(np.asarray(after) > np.asarray(before) + 1e-9)),
        "per_contamination": {
            k: {
                "before": float(np.mean(v["before"])),
                "after": float(np.mean(v["after"])),
                "reduction": 1.0 - float(np.mean(v["after"]))
                / max(float(np.mean(v["before"])), 1e-12),
            }
            for k, v in per_kind.items()
        },
    }


def protection_metrics(traces: list, windows: list) -> dict:
    """Over-cleaning: how much of the data that needed nothing was edited.

    ``damage`` is the normalised distance the agent introduced into windows
    that were already correct -- it should be zero, and any value above it is
    harm the pipeline caused rather than repaired.
    """
    byid = {w.window_id: w for w in windows}
    per_stratum, damages = {}, []
    for t in traces:
        if t.stratum not in PROTECTED_STRATA:
            continue
        d = per_stratum.setdefault(t.stratum, {"n": 0, "modified": 0, "damage": []})
        d["n"] += 1
        d["modified"] += int(t.modified)
        w = byid.get(t.window_id)
        if w is not None and w.clean_series is not None:
            ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
            harm = _mse_to_clean(
                t.final_series, w.clean_series[t.crop_offset :], ref_var
            )
            d["damage"].append(harm)
            damages.append(harm)

    total_n = sum(v["n"] for v in per_stratum.values())
    total_mod = sum(v["modified"] for v in per_stratum.values())
    return {
        "n_protected": total_n,
        "over_clean_rate": total_mod / max(total_n, 1),
        "mean_damage": float(np.mean(damages)) if damages else 0.0,
        "per_stratum": {
            k: {
                "n": v["n"],
                "modified": v["modified"],
                "over_clean_rate": v["modified"] / max(v["n"], 1),
                "mean_damage": float(np.mean(v["damage"])) if v["damage"] else 0.0,
            }
            for k, v in per_stratum.items()
        },
    }


def corpus_effect(traces: list, windows: list) -> dict:
    """Net effect on the whole corpus, repairs and damage on one scale.

    Repair and protection are reported separately because they are different
    questions, but separate reporting cannot settle the trade-off between them:
    at a high contamination rate an indiscriminate cleaner posts a large repair
    number *and* a large damage number, and nothing in either column says
    whether the corpus ended up better or worse overall.

    This averages the normalised distance to truth across every window that has
    a pristine reference -- contaminated and protected alike, weighted as the
    corpus weights them. It is the number that answers "should I have run this
    pipeline at all".
    """
    byid = {w.window_id: w for w in windows}
    before, after, per_stratum = [], [], {}
    for t in traces:
        w = byid.get(t.window_id)
        if w is None or w.clean_series is None:
            continue
        ref_var = float(np.var(w.clean_series - np.median(w.clean_series)))
        b = _mse_to_clean(t.initial_series, w.clean_series, ref_var)
        a = _mse_to_clean(t.final_series, w.clean_series[t.crop_offset :], ref_var)
        before.append(b)
        after.append(a)
        d = per_stratum.setdefault(t.stratum, {"before": [], "after": []})
        d["before"].append(b)
        d["after"].append(a)

    if not before:
        return {"n": 0}
    b_m, a_m = float(np.mean(before)), float(np.mean(after))
    before_arr, after_arr = np.asarray(before), np.asarray(after)
    return {
        "n": len(before),
        "nmse_before": b_m,
        "nmse_after": a_m,
        "net_reduction": 1.0 - a_m / max(b_m, 1e-12),
        "windows_improved": int(np.sum(after_arr < before_arr - 1e-9)),
        "windows_worsened": int(np.sum(after_arr > before_arr + 1e-9)),
        "per_stratum": {
            k: {
                "n": len(v["before"]),
                "before": float(np.mean(v["before"])),
                "after": float(np.mean(v["after"])),
            }
            for k, v in sorted(per_stratum.items())
        },
    }


def rollback_metrics(traces: list) -> dict:
    """Rollback and refusal behaviour."""
    from introact_ts.types import ROLLBACK_VERDICTS

    attempted = [r for t in traces for r in t.records if r.verdict.value != "NO_OP"]
    rolled = [r for r in attempted if r.verdict in ROLLBACK_VERDICTS]
    by_reason = {}
    for r in rolled:
        by_reason[r.verdict.value] = by_reason.get(r.verdict.value, 0) + 1

    # Which strata the rollbacks protected.
    protected_rollbacks = sum(
        1 for t in traces if t.stratum in PROTECTED_STRATA and t.n_rollbacks > 0
    )
    abstain = [t for t in traces if t.final_state == "ABSTAIN"]
    quarantine = [t for t in traces if t.final_state == "QUARANTINE"]
    return {
        "n_attempted": len(attempted),
        "n_rolled_back": len(rolled),
        "rollback_rate": len(rolled) / max(len(attempted), 1),
        "by_reason": by_reason,
        "protected_windows_with_rollback": protected_rollbacks,
        "abstain_rate": len(abstain) / max(len(traces), 1),
        "quarantine_rate": len(quarantine) / max(len(traces), 1),
        "abstain_on_protected": sum(
            1 for t in abstain if t.stratum in PROTECTED_STRATA
        ),
        "mean_probe_calls": float(np.mean([t.probe_calls for t in traces])),
    }


def utility_metrics(traces: list) -> dict:
    """Judge-model utility change, split by whether the window was edited."""
    edited = [t for t in traces if t.modified]
    delta = [t.final_utility - t.initial_utility for t in edited]
    return {
        "n_edited": len(edited),
        "mean_delta_utility": float(np.mean(delta)) if delta else 0.0,
        "min_delta_utility": float(np.min(delta)) if delta else 0.0,
    }


def transfer_metrics(
    traces: list, windows: list, models: list, horizon: int = 32
) -> dict:
    """Forecast error on models that took no part in curation.

    The judge model is guaranteed to like the curated data -- it is what the
    acceptance rule optimised against. The question that matters is whether
    other models, never consulted during curation, also do better on it.

    The forecast target is the *pristine* continuation, not the curated one.
    That distinction decides what this metric rewards. Scoring against the
    curated series would hand the prize to whichever method smoothed hardest:
    a flattened series is trivially easy to predict from itself, and a pipeline
    that destroyed the signal would post the best number in the table. Held
    against the truth, smoothing only helps to the extent it removed something
    that was not signal.
    """
    from introact_ts.probe import reference_scale

    byid = {w.window_id: w for w in windows}
    results = {}
    for model in models:
        before, after = [], []
        for t in traces:
            w = byid.get(t.window_id)
            if w is None or w.clean_series is None:
                continue
            scale = reference_scale(t.initial_series)
            b = _truth_nrmse(model, t.initial_series, w.clean_series, 0, horizon, scale)
            a = _truth_nrmse(
                model, t.final_series, w.clean_series, t.crop_offset, horizon, scale
            )
            if b is None or a is None:
                continue
            before.append(b)
            after.append(a)
        b, a = float(np.mean(before)), float(np.mean(after))
        results[getattr(model, "name", "model")] = {
            "nrmse_before": b,
            "nrmse_after": a,
            "improvement": 1.0 - a / max(b, 1e-12),
            "n": len(before),
        }
    return results


def _truth_nrmse(
    model, curated: np.ndarray, clean: np.ndarray, offset: int,
    horizon: int, scale: float,
):
    """Forecast the pristine continuation from the curated context."""
    from introact_ts.probe import _nan_safe

    x = _nan_safe(curated)
    n = len(x)
    truth = np.asarray(clean, dtype=np.float64)[offset : offset + n]
    if len(truth) < n or n < 32:
        return None
    H = int(min(horizon, max(8, n // 4)))
    ctx = x[: n - H]
    tgt = truth[n - H :]
    pred = model.forecast(ctx, H)
    return float(np.sqrt(np.mean((tgt - pred) ** 2)) / max(scale, 1e-9))


def summarise(traces: list, windows: list, models: list = None) -> dict:
    """All metric families for one run."""
    out = {
        "n_windows": len(traces),
        "detection": detection_metrics(traces),
        "action": action_metrics(traces),
        "repair": repair_metrics(traces, windows),
        "corpus_effect": corpus_effect(traces, windows),
        "protection": protection_metrics(traces, windows),
        "rollback": rollback_metrics(traces),
        "utility": utility_metrics(traces),
    }
    if models:
        out["transfer"] = transfer_metrics(traces, windows, models)
    return out
