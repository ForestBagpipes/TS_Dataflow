"""Train and calibrate the v3-pre ContextualShield.

Data split: leave-one-real-dataset-out. All candidates from one window stay in
the same split. Within each outer fold, the remaining windows are split 80/20
into train and calibration folds. The test dataset never participates in
training, normalisation, or calibration.

For each outer fold a model is trained, calibrated, and evaluated. The final
report aggregates the per-fold metrics.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from introact_ts.contextual_shield import (  # noqa: E402
    ALL_FEATURES, CandidateFeatures, ContextualShield, ShieldConfig,
)


def _load_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _features_from_row(row):
    feats = row["features"]
    values = [feats.get(name, 0.0) for name in ALL_FEATURES]
    return CandidateFeatures(values=np.array(values, dtype=object))


def _split_by_dataset(rows, test_dataset):
    test = [r for r in rows if r["dataset"] == test_dataset]
    rest = [r for r in rows if r["dataset"] != test_dataset]
    # Split rest into train (80%) and calibration (20%) by window, so all
    # candidates from one window stay together.
    by_uid = defaultdict(list)
    for r in rest:
        by_uid[r["sample_uid"]].append(r)
    uids = sorted(by_uid.keys())
    rng = np.random.RandomState(20260901)
    rng.shuffle(uids)
    n_train = int(0.8 * len(uids))
    train_uids = set(uids[:n_train])
    cal_uids = set(uids[n_train:])
    train = [r for uid in train_uids for r in by_uid[uid]]
    cal = [r for uid in cal_uids for r in by_uid[uid]]
    return train, cal, test


PROTECTED_STRATA = ("clean", "hard", "rare_valid", "changepoint")


def _evaluate(shield, rows):
    """Episode-level metrics under real execution semantics.

    The agent walks candidates in proposer order, commits the first candidate
    the shield accepts, and stops; if none passes, the window is KEEP.
    Damage is the corpus-level mean window loss (a KEEP window contributes 0),
    the same quantity the conformal calibration bounds. Per-commit damage is
    reported alongside.
    """
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)

    ep = defaultdict(list)
    cand = defaultdict(list)
    for uid, rs in by_window.items():
        committed = None
        for r in rs:  # rows are written in proposer order per window
            feats = _features_from_row(r)
            accepted = shield.decide(feats, r["family"]).value == "ACCEPTED"
            cand["n"].append(1.0)
            cand["accepted"].append(float(accepted))
            cand["accepted_bs"].append(float(accepted and r["beneficial_and_safe"]))
            cand["accepted_harmful"].append(float(accepted and r["harmful"]))
            if accepted and committed is None:
                committed = r

        w = rs[0]
        protected = w["stratum"] in PROTECTED_STRATA
        contaminated = w["stratum"] == "contaminated"
        loss = committed["true_loss"] if committed else 0.0
        gain = committed["true_repair_gain"] if committed else 0.0
        bs = bool(committed and committed["beneficial_and_safe"])
        ep["n_windows"].append(1.0)
        ep["committed"].append(float(committed is not None))
        ep["window_loss"].append(loss)
        ep["window_gain"].append(gain)
        ep["beneficial_commit"].append(float(bs))
        ep["protected"].append(float(protected))
        ep["protected_mis_edit"].append(float(protected and committed is not None))
        ep["protected_harmful"].append(float(protected and committed is not None and loss > 0.0))
        ep["contaminated"].append(float(contaminated))
        ep["contaminated_commit"].append(float(contaminated and committed is not None))
        ep["contaminated_bs_commit"].append(float(contaminated and bs))

    out = {k: float(np.sum(v)) for k, v in ep.items()}
    n_w = max(out["n_windows"], 1.0)
    n_committed = max(out["committed"], 1.0)
    out["damage"] = float(np.mean(ep["window_loss"]))
    out["damage_per_commit"] = (
        float(np.mean([l for l, c in zip(ep["window_loss"], ep["committed"]) if c]))
        if out["committed"] else 0.0
    )
    out["protected_mis_edit_rate"] = out["protected_mis_edit"] / max(out["protected"], 1.0)
    out["protected_harmful_rate"] = out["protected_harmful"] / max(out["protected"], 1.0)
    out["coverage"] = out["contaminated_commit"] / max(out["contaminated"], 1.0)
    out["beneficial_coverage"] = out["contaminated_bs_commit"] / max(out["contaminated"], 1.0)
    out["mean_repair_gain_contaminated"] = (
        float(np.mean([g for g, c in zip(ep["window_gain"], ep["contaminated"]) if c]))
        if out["contaminated"] else 0.0
    )
    out["commit_rate"] = out["committed"] / n_w
    # Candidate-level diagnostics.
    out["cand_n"] = float(np.sum(cand["n"]))
    out["cand_accept_rate"] = float(np.mean(cand["accepted"]))
    out["cand_accept_harmful_rate"] = (
        float(np.sum(cand["accepted_harmful"]) / max(np.sum(cand["accepted"]), 1.0))
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v3_training_data.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v3_trained_shield.json"))
    args = ap.parse_args()

    rows = _load_rows(Path(args.data))
    print(f"loaded {len(rows)} candidates")

    real_datasets = sorted({r["dataset"] for r in rows if not r["dataset"].startswith("ood:")})
    print(f"real datasets: {real_datasets}")

    results = {}
    for test_ds in real_datasets:
        print(f"\n=== outer fold: test={test_ds} ===", flush=True)
        train, cal, test = _split_by_dataset(rows, test_ds)
        print(f"train={len(train)} cal={len(cal)} test={len(test)}")

        shield = ContextualShield(ShieldConfig())
        X_train = shield.encode([_features_from_row(r) for r in train], fit=True)
        y_train = np.array([r["beneficial_and_safe"] for r in train], dtype=int)
        shield.train(X_train, y_train)

        X_cal = shield.encode([_features_from_row(r) for r in cal])
        scores_cal = shield.predict_score(X_cal)
        damages_cal = np.array([r["true_loss"] for r in cal], dtype=float)
        families_cal = np.array([r["family"] for r in cal], dtype=str)
        shield.calibrate(scores_cal, damages_cal, families_cal)

        test_metrics = _evaluate(shield, test)
        results[test_ds] = {
            "n_train": len(train), "n_cal": len(cal), "n_test": len(test),
            "thresholds": shield.thresholds,
            "global_threshold": shield.global_threshold,
            "test_metrics": test_metrics,
        }
        print(json.dumps(test_metrics, indent=2))

    out = {
        "folds": results,
        "aggregate": {
            "protected_mis_edit_rate": float(np.mean([
                f["test_metrics"]["protected_mis_edit_rate"] for f in results.values()
            ])),
            "damage": float(np.mean([
                f["test_metrics"]["damage"] for f in results.values()
            ])),
            "coverage": float(np.mean([
                f["test_metrics"]["coverage"] for f in results.values()
            ])),
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"\n___V3_TRAIN_DONE___ wrote {args.out}")


if __name__ == "__main__":
    main()
