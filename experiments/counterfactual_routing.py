"""Counterfactual routing replay on the per-family calibration pool.

Uses already-scored candidates (`results/family_scores.jsonl`) and recomputes
the evidence that the policy actually conditions on, so source attribution
(primary/secondary/fallback/retry) matches `policy.propose_actions` rather than
a separate diagnostic run with a different reference.

Source datasets are held out one at a time for an honest dev/test split; the
held-out source never enters threshold selection.

Rules compared:
  current              what `propose_actions` emitted under enable_param_ladder
  primary_only         keep only the operator matched to the dominant defect
  missing_primary      drop DESPIKE candidates when the dominant defect is missing
                       (i.e. DESPIKE arrived through the secondary slot)
  ratio_gate_t         include a secondary operator only when its evidence
                       strength is at least t times the primary strength

Ground-truth contamination kind is used only for evaluation, never for deciding
which candidates to keep.

Usage:
    python -u experiments/counterfactual_routing.py \
        --scores results/family_scores.jsonl \
        --out results/counterfactual_routing.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from build_calibration import build as build_calibration  # noqa: E402
from introact_ts.risk import (  # noqa: E402
    DEFECT_KEYS,
    CorpusReference,
    corpus_reference,
    statistical_evidence,
)

# Ledger definition of protected strata (the four that must not be edited).
PROTECTED_LEDGER = {"clean", "hard", "rare_valid", "changepoint"}

# The policy's own protected set, reported for reference.
POLICY_PROTECTED = {"hard", "rare_valid", "clean_ood"}

DEFECT_OPERATOR = {
    "missing": "IMPUTE",
    "spike": "DESPIKE",
    "noise": "DENOISE",
    "shift": "RESEGMENT",
    "none": None,
}

FAMILY_TARGET_KINDS = {
    "DESPIKE": {"spike"},
    "DENOISE": {"noise"},
    "IMPUTE": {"missing_block", "missing_scattered"},
    "RESEGMENT": {"level_shift"},
}

# Per-family thresholds from the formal calibration (results/conformal_family.json).
LAMBDA_STAR = {
    "DENOISE": 0.10,
    "DESPIKE": 0.00,
    "IMPUTE": 0.02,
    "RESEGMENT": 0.40,
}

ALPHA = 0.03
SECONDARY_THRESHOLD = 1.6


def dominant_and_secondary(evidence, reference, sec_thr=SECONDARY_THRESHOLD):
    """Return (dominant defect, secondary defect) exactly as the policy sees them.

    The policy's `RiskState.dominant_defect` requires units >= 1.0; its
    `_secondary_defect` requires units >= `secondary_threshold`.
    """
    units = reference.units(evidence)
    above = [k for k in DEFECT_KEYS if units[k] >= 1.0]
    if not above:
        dominant = "none"
    else:
        dominant = max(above, key=lambda k: units[k])

    secondary = ""
    if dominant != "none":
        remaining = {k: v for k, v in units.items() if k != dominant}
        if remaining:
            best = max(remaining, key=remaining.get)
            if remaining[best] >= sec_thr:
                secondary = best
    return dominant, secondary, units


def label_source(candidate, dominant, secondary, fallback=False):
    """Why the policy offered this operator: primary, secondary, fallback, retry.

    The calibration run uses `enable_param_ladder=True` and emits every rung of
    every routed operator in one step, so historical retries are not present in
    this file.  Fallback is also off in that run, but the label is kept for
    counterfactual rules that may turn it on.
    """
    family = candidate["family"]
    if family == DEFECT_OPERATOR.get(dominant):
        return "primary"
    if family == DEFECT_OPERATOR.get(secondary):
        return "secondary"
    if fallback and family == "DENOISE":
        return "fallback"
    return "other"


def compute_reference_and_evidence(windows):
    """Recompute the corpus-adaptive evidence reference from the calibration pool."""
    evidences = {}
    for w in windows:
        ev = statistical_evidence(np.asarray(w.series, dtype=np.float64))
        evidences[int(w.window_id)] = ev
    n = len(windows)
    ref = corpus_reference(
        list(evidences.values()),
        np.zeros(n, dtype=np.float64),
        np.zeros(n, dtype=np.float64),
    )
    return ref, evidences


def load_scores(path):
    """List of {window_id, candidates[]} from family_scores.jsonl."""
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            out.append(json.loads(line))
    return out


def compute_metrics(candidates, windows_in_split, lam_star=LAMBDA_STAR):
    """Aggregate metrics for one candidate set and one data split."""
    if not candidates:
        return {"n_candidates": 0}

    n_total = len(candidates)
    by_family = Counter(c["family"] for c in candidates)
    by_source = Counter(c.get("source", "unknown") for c in candidates)

    def _stratum(w):
        return w.stratum if hasattr(w, "stratum") else w["stratum"]

    def _contamination(w):
        return w.contamination if hasattr(w, "contamination") else w["contamination"]

    protected = [c for c in candidates if c["stratum"] in PROTECTED_LEDGER]
    policy_protected = [c for c in candidates if c["stratum"] in POLICY_PROTECTED]
    ledger_protected_rate = len(protected) / n_total
    policy_protected_rate = len(policy_protected) / n_total

    n_windows = len(windows_in_split)
    n_contaminated = sum(1 for w in windows_in_split if _stratum(w) == "contaminated")
    by_true_kind = Counter(_contamination(w) for w in windows_in_split)

    family_metrics = {}
    overall_admitted_on_contaminated = 0
    for fam in sorted(by_family):
        fam_rows = [c for c in candidates if c["family"] == fam]
        lam = lam_star.get(fam, 0.0)
        d = np.array([r["distortion"] for r in fam_rows])
        L = np.array([r["loss"] for r in fam_rows])
        admitted = d < lam
        admitted_rows = [r for r, ok in zip(fam_rows, admitted) if ok]

        target_kinds = FAMILY_TARGET_KINDS[fam]
        on_target = [c for c in fam_rows if c["contamination"] in target_kinds]
        target_denominator = sum(by_true_kind.get(k, 0) for k in target_kinds)

        fam_protected = [c for c in fam_rows if c["stratum"] in PROTECTED_LEDGER]
        admitted_protected = [c for c in admitted_rows if c["stratum"] in PROTECTED_LEDGER]
        admitted_on_contaminated = [c for c in admitted_rows if c["stratum"] == "contaminated"]
        admitted_on_target = [c for c in admitted_rows if c["contamination"] in target_kinds]

        overall_admitted_on_contaminated += len(admitted_on_contaminated)

        family_metrics[fam] = {
            "n_candidates": len(fam_rows),
            "ledger_protected_rate": len(fam_protected) / len(fam_rows),
            "policy_protected_rate": sum(1 for c in fam_rows if c["stratum"] in POLICY_PROTECTED) / len(fam_rows),
            "on_target_purity": len(on_target) / len(fam_rows),
            "mean_loss": float(L.mean()),
            "lambda": lam,
            "structural_admitted": int(admitted.sum()),
            "admitted_rate": float(admitted.mean()),
            "admitted_mean_loss": float(np.mean([r["loss"] for r in admitted_rows])) if admitted_rows else None,
            "admitted_ledger_protected_rate": len(admitted_protected) / len(admitted_rows) if admitted_rows else None,
            "risk_at_lambda": float((L * admitted).sum() / max(len(fam_rows), 1)),
            "coverage_upper_bound_total": int(admitted.sum()) / max(n_windows, 1),
            "coverage_upper_bound_contaminated": len(admitted_on_contaminated) / max(n_contaminated, 1),
            "coverage_upper_bound_target": len(admitted_on_target) / max(target_denominator, 1),
            "by_source": dict(Counter(c.get("source", "unknown") for c in fam_rows)),
        }

    return {
        "n_candidates": n_total,
        "n_windows": n_windows,
        "n_contaminated_windows": n_contaminated,
        "by_family_counts": dict(by_family),
        "by_source_counts": dict(by_source),
        "ledger_protected_rate": ledger_protected_rate,
        "policy_protected_rate": policy_protected_rate,
        "overall_coverage_upper_bound": overall_admitted_on_contaminated / max(n_contaminated, 1),
        "family_metrics": family_metrics,
    }


def apply_rule(candidates, rule, param=None):
    """Return the candidate subset under a counterfactual routing rule."""
    if rule == "current":
        return candidates

    out = []
    for c in candidates:
        src = c.get("source", "other")
        fam = c["family"]
        units = c.get("_units", {})
        dominant = c.get("_dominant", "none")

        if rule == "primary_only":
            if src == "primary":
                out.append(c)
            continue

        if rule == "missing_primary":
            # Drop DESPIKE whenever the dominant defect is missing
            # (i.e. DESPIKE arrived through the secondary slot on a gap window).
            if fam == "DESPIKE" and dominant == "missing":
                continue
            out.append(c)
            continue

        if rule == "ratio_gate":
            threshold = param if param is not None else SECONDARY_THRESHOLD
            if src == "primary":
                out.append(c)
            elif src == "secondary":
                sec = c.get("_secondary", "")
                if sec and dominant in units and sec in units:
                    denom = units[dominant] if units[dominant] > 0 else 1e-12
                    if units[sec] / denom >= threshold:
                        out.append(c)
            else:
                # fallback / retry / other are kept unchanged; they are rare
                # and not the object of this gate.
                out.append(c)
            continue

        raise ValueError(f"unknown rule {rule}")
    return out


def select_ratio_threshold(dev_candidates, min_coverage_frac=0.5):
    """Choose a ratio-gate threshold on dev that minimizes protected rate
    while keeping at least `min_coverage_frac` of the current-rule coverage."""
    current = compute_metrics(dev_candidates, [])
    target_cov = current.get("overall_coverage_upper_bound", 0.0) * min_coverage_frac

    best = None
    best_score = float("inf")
    for t in [0.5, 0.8, 1.0, 1.3, 1.6, 2.0, 3.0, 5.0]:
        filtered = apply_rule(dev_candidates, "ratio_gate", t)
        m = compute_metrics(filtered, [])
        cov = m.get("overall_coverage_upper_bound", 0.0)
        prot = m.get("ledger_protected_rate", 1.0)
        score = prot + max(0.0, target_cov - cov) * 10.0
        if score < best_score:
            best_score = score
            best = t
    return best if best is not None else SECONDARY_THRESHOLD


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=str(ROOT / "results" / "family_scores.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "counterfactual_routing.json"))
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--source", default="mixed")
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--secondary-threshold", dest="secondary_threshold",
                    type=float, default=SECONDARY_THRESHOLD)
    args = ap.parse_args()

    print("loading scores", flush=True)
    scores = load_scores(args.scores)
    print(f"  {len(scores)} windows scored")

    print("building calibration windows and recomputing evidence reference",
          flush=True)
    windows, _ = build_calibration(n=args.n, seed=args.seed,
                                   source=args.source, verbose=False)
    byid = {int(w.window_id): w for w in windows}
    reference, evidences = compute_reference_and_evidence(windows)
    print(f"  {len(windows)} windows, reference defect floors:")
    for k in DEFECT_KEYS:
        print(f"    {k}: {reference.defect_refs[k]:.4f}")

    # Flatten and annotate all candidates with policy-consistent source labels.
    all_candidates = []
    windows_for_split = []
    for row in scores:
        wid = int(row["window_id"])
        w = byid.get(wid)
        if w is None:
            continue
        ev = evidences.get(wid, {})
        dom, sec, units = dominant_and_secondary(ev, reference,
                                                  sec_thr=args.secondary_threshold)
        for cand in row["candidates"]:
            cand = dict(cand)
            cand["window_id"] = wid
            cand["dataset"] = w.dataset
            cand["_evidence"] = ev
            cand["_units"] = units
            cand["_dominant"] = dom
            cand["_secondary"] = sec
            cand["source"] = label_source(cand, dom, sec, fallback=False)
            all_candidates.append(cand)
        windows_for_split.append({
            "window_id": wid,
            "dataset": w.dataset,
            "stratum": row["candidates"][0]["stratum"] if row["candidates"] else w.stratum,
            "contamination": row["candidates"][0]["contamination"] if row["candidates"] else w.contamination,
        })

    print(f"  {len(all_candidates)} candidates total")

    datasets = sorted(set(w.dataset for w in windows))
    print(f"source datasets: {datasets}", flush=True)

    # DESPIKE source attribution summary (off-target candidates).
    despike_all = [c for c in all_candidates if c["family"] == "DESPIKE"]
    despike_offtarget = [c for c in despike_all if c["contamination"] != "spike"]
    despike_summary = {
        "n_despike_total": len(despike_all),
        "n_despike_offtarget": len(despike_offtarget),
        "offtarget_by_source": dict(Counter(c["source"] for c in despike_offtarget)),
        "offtarget_by_true_kind": dict(Counter(c["contamination"] for c in despike_offtarget)),
        "offtarget_by_dominant": dict(Counter(c["_dominant"] for c in despike_offtarget)),
        "offtarget_examples": [
            {
                "window_id": c["window_id"],
                "dataset": c["dataset"],
                "true_kind": c["contamination"],
                "source": c["source"],
                "dominant": c["_dominant"],
                "secondary": c["_secondary"],
                "missing_frac": c["_evidence"].get("missing_frac", 0.0),
                "spike_frac": c["_evidence"].get("spike_frac", 0.0),
                "loss": c["loss"],
                "distortion": c["distortion"],
            }
            for c in despike_offtarget[:200]
        ],
    }

    # Aggregate across all data (no split).
    aggregate = {}
    base_rules = ["current", "primary_only", "missing_primary"]
    for rule in base_rules:
        filtered = apply_rule(all_candidates, rule)
        aggregate[rule] = compute_metrics(filtered, windows_for_split)

    ratio_thresholds = [0.5, 0.8, 1.0, 1.3, 1.6, 2.0, 3.0, 5.0]
    for t in ratio_thresholds:
        filtered = apply_rule(all_candidates, "ratio_gate", t)
        aggregate[f"ratio_gate_{t}"] = compute_metrics(filtered, windows_for_split)

    # Leave-one-source-out dev/test.
    loo = []
    for held in datasets:
        dev_cand = [c for c in all_candidates if c["dataset"] != held]
        test_cand = [c for c in all_candidates if c["dataset"] == held]
        dev_windows = [w for w in windows_for_split if w["dataset"] != held]
        test_windows = [w for w in windows_for_split if w["dataset"] == held]

        best_t = select_ratio_threshold(dev_cand)
        fold = {
            "held_out": held,
            "n_dev": len(dev_cand),
            "n_test": len(test_cand),
            "rules": {},
            "selected_ratio_threshold": best_t,
        }
        for rule in base_rules:
            fold["rules"][rule] = {
                "dev": compute_metrics(apply_rule(dev_cand, rule), dev_windows),
                "test": compute_metrics(apply_rule(test_cand, rule), test_windows),
            }
        for t in [1.0, SECONDARY_THRESHOLD, best_t]:
            key = f"ratio_gate_{t}"
            if key == f"ratio_gate_{best_t}":
                key = "ratio_gate_selected"
            fold["rules"][key] = {
                "dev": compute_metrics(apply_rule(dev_cand, "ratio_gate", t), dev_windows),
                "test": compute_metrics(apply_rule(test_cand, "ratio_gate", t), test_windows),
            }
        loo.append(fold)

    out = {
        "alpha": args.alpha,
        "lambda_star": LAMBDA_STAR,
        "secondary_threshold": args.secondary_threshold,
        "n_windows": len(scores),
        "n_candidates_total": len(all_candidates),
        "datasets": datasets,
        "despike_source_attribution": despike_summary,
        "aggregate": aggregate,
        "leave_one_source_out": loo,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"wrote {args.out}", flush=True)

    # Print a compact table for the log.
    print("\nAGGREGATE COMPARISON (current lambdas)")
    print(f"{'rule':20s}{'n cand':>8s}{'prot rate':>10s}{'cov UB':>10s}"
          f"{'DESPIKE n':>10s}{'DESPIKE prot':>13s}{'DESPIKE admit':>14s}")
    for rule in base_rules + [f"ratio_gate_{t}" for t in (1.0, SECONDARY_THRESHOLD, 2.0)]:
        m = aggregate[rule]
        d = m["family_metrics"].get("DESPIKE", {})
        print(f"{rule:20s}{m['n_candidates']:8d}{m['ledger_protected_rate']:10.4f}"
              f"{m['overall_coverage_upper_bound']:10.4f}{d.get('n_candidates', 0):10d}"
              f"{d.get('ledger_protected_rate', 0.0):13.4f}{d.get('structural_admitted', 0):14d}")

    print("\nPER-FAMILY CURRENT")
    for fam, m in aggregate["current"]["family_metrics"].items():
        print(f"{fam:12s} n={m['n_candidates']:4d} protected={m['ledger_protected_rate']:.3f} "
              f"purity={m['on_target_purity']:.3f} mean_loss={m['mean_loss']:.3f} "
              f"lambda={m['lambda']:.2f} admitted={m['structural_admitted']:4d} "
              f"covUB_contam={m['coverage_upper_bound_contaminated']:.4f} "
              f"risk={m['risk_at_lambda']:.4f}")
    print("\n___COUNTERFACTUAL_ROUTING_DONE___", flush=True)


if __name__ == "__main__":
    main()
