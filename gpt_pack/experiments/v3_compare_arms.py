"""Phase 4 offline arm comparison for v3-pre.

Five arms on the same candidate table (results/v3_training_data.jsonl), the
same frozen corpus, and the same episode semantics: candidates are walked in
proposer order, the first candidate the arm accepts commits, the rest are
discarded; if none passes the window is KEEP. Multi-commit episodes cannot be
replayed offline (the table holds step-0 candidates on the original series
only), so every arm is evaluated under this identical first-commit rule.

Arms:
  v2_frozen        the shipped rule: verify(dU, distortion, risk) with the
                   smoke350 config (tau 0.02, per-family taus from
                   results/conformal_family.json, epsilon 0.005, eta 0.5)
  statistical_only ContextualShield trained on non-TSFM features
  TSFM_only        ContextualShield trained on TSFM-behaviour features
  joint_v3_pre     ContextualShield trained on the full whitelist
  oracle           per window the max-gain beneficial_and_safe candidate
                   commits; the headroom upper bound

Protocol: leave-one-real-dataset-out. The test dataset never enters training,
normalisation, or calibration. Synthetic OOD rows are excluded from training
and reported separately as a stress test. Deployed thresholds come from the
calibration fold only; test-fold sweeps are analysis, not selection.
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
    ALL_FEATURES, CATEGORICAL_FEATURES, NUMERICAL_FEATURES,
    CandidateFeatures, ContextualShield, ShieldConfig,
)
from introact_ts.verify import VerifyConfig, verify  # noqa: E402

PROTECTED_STRATA = ("clean", "hard", "rare_valid", "changepoint")

# v2 as shipped in smoke350.
V2_TAUS = {"DENOISE": 0.1, "DESPIKE": 0.0, "IMPUTE": 0.02, "RESEGMENT": 0.4}
V2_CFG = VerifyConfig(tau=0.02, tau_by_family=V2_TAUS)

# Feature partition. TSFM behaviour features are everything derived from the
# frozen-model probe: the behavioural risk score, utility readings and their
# deltas, probe vector deltas, and the per-signal dynamics deltas. Structure
# and seam measures are computed from the series itself, so they sit on the
# statistical side.
TSFM_NUMERIC = {
    "behav_risk", "delta_utility", "utility_before", "utility_after",
    "probe_delta_mean", "probe_delta_std", "probe_delta_max",
    "forecast_nrmse_delta", "recon_nrmse_med_delta", "recon_nrmse_iqr_delta",
    "multiview_disagree_delta", "perturb_output_sens_delta",
    "repr_jump_mean_delta", "repr_norm_drift_delta", "model_disagree_delta",
    "outside_support_drift",
}
STAT_NUMERIC = [n for n in NUMERICAL_FEATURES if n not in TSFM_NUMERIC]
STAT_FEATURES = CATEGORICAL_FEATURES + tuple(STAT_NUMERIC)
TSFM_FEATURES = tuple(sorted(TSFM_NUMERIC))

ALPHA = 0.03


def _load_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _features_from_row(row, names=ALL_FEATURES):
    feats = row["features"]
    values = [feats.get(name, 0.0) for name in names]
    return CandidateFeatures(
        values=np.array(values, dtype=object),
        feature_names=tuple(names),
    )


def _split_by_dataset(rows, test_dataset):
    """Train/cal/test split; OOD rows are excluded (stress test only)."""
    test = [r for r in rows if r["dataset"] == test_dataset]
    rest = [r for r in rows
            if r["dataset"] != test_dataset
            and not r["dataset"].startswith("ood:")]
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


def _fit_shield(train, cal, feature_names, dual=False):
    shield = ContextualShield(ShieldConfig())
    shield.feature_names = tuple(feature_names)
    X_train = shield.encode(
        [_features_from_row(r, feature_names) for r in train], fit=True)
    y_train = np.array([r["beneficial_and_safe"] for r in train], dtype=int)
    shield.train(X_train, y_train)
    X_cal = shield.encode([_features_from_row(r, feature_names) for r in cal])
    scores_cal = shield.predict_score(X_cal)
    damages_cal = np.array([r["true_loss"] for r in cal], dtype=float)
    families_cal = np.array([r["family"] for r in cal], dtype=str)
    if dual:
        y_harm = np.array([r["harmful"] for r in train], dtype=int)
        shield.train_harm(X_train, y_harm)
        harm_cal = shield.predict_harm(X_cal)
        shield.calibrate_dual(scores_cal, harm_cal, damages_cal, families_cal)
    else:
        shield.calibrate(scores_cal, damages_cal, families_cal)
    return shield


# -- per-candidate decisions -------------------------------------------------


def _v2_decide(row) -> bool:
    v = verify(float(row["delta_utility"]), float(row["struct_distortion"]),
               float(row["risk"]), V2_CFG, action=row["family"])
    return v.value == "ACCEPTED"


def _decisions(arm, rows, shield=None, feature_names=ALL_FEATURES):
    """Return {sample_uid: committed row or None} under first-commit order."""
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)
    committed = {}
    for uid, rs in by_window.items():
        pick = None
        if arm == "oracle":
            bs = [r for r in rs if r["beneficial_and_safe"]]
            if bs:
                pick = max(bs, key=lambda r: r["true_repair_gain"])
        else:
            for r in rs:  # rows are in proposer order within a window
                if arm == "v2_frozen":
                    acc = _v2_decide(r)
                elif arm == "v3_1_pre":
                    feats = _features_from_row(r, feature_names)
                    acc = shield.decide_dual(feats, r["family"]).value == "ACCEPTED"
                else:
                    feats = _features_from_row(r, feature_names)
                    acc = shield.decide(feats, r["family"]).value == "ACCEPTED"
                if acc:
                    pick = r
                    break
        committed[uid] = pick
    return committed


def _commit_diagnosis(committed):
    """Breakdown of committed candidates, for root-cause attribution."""
    from collections import Counter
    out = {}
    for layer, pred in (("protected", lambda r: r["stratum"] in PROTECTED_STRATA),
                        ("contaminated", lambda r: r["stratum"] == "contaminated")):
        picks = [r for r in committed.values() if r is not None and pred(r)]
        out[layer] = {
            "n": len(picks),
            "harmful": sum(1 for r in picks if r["true_loss"] > 0.03),
            "by_dataset": dict(Counter(r["dataset"] for r in picks)),
            "by_family": dict(Counter(r["family"] for r in picks)),
            "by_hypothesis": dict(Counter(r["features"]["hypothesis"] for r in picks)),
            "by_route_source": dict(Counter(r["features"]["route_source"] for r in picks)),
            "by_dominant_defect": dict(Counter(r["features"]["dominant_defect"] for r in picks)),
        }
    return out


# -- episode metrics ----------------------------------------------------------


def _episode_metrics(rows, committed):
    """Corpus metrics from per-window committed rows (None = KEEP)."""
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)

    n = len(by_window)
    losses, gains = [], []
    n_committed = 0
    n_harmful_commit = 0
    n_bs_commit = 0
    prot_n = prot_edit = prot_harm = 0
    cont_n = cont_edit = cont_improved = cont_bs = 0
    cont_gains = []
    per_dataset = defaultdict(lambda: {"bs_commits": 0, "windows": 0})
    family_funnel = defaultdict(lambda: defaultdict(int))

    for uid, rs in by_window.items():
        w = rs[0]
        pick = committed.get(uid)
        protected = w["stratum"] in PROTECTED_STRATA
        contaminated = w["stratum"] == "contaminated"
        per_dataset[w["dataset"]]["windows"] += 1
        for r in rs:
            fam = family_funnel[r["family"]]
            fam["candidates"] += 1
            if pick is r:
                fam["committed"] += 1
        loss = pick["true_loss"] if pick else 0.0
        gain = pick["true_repair_gain"] if pick else 0.0
        losses.append(loss)
        gains.append(gain)
        if pick is not None:
            n_committed += 1
            if pick["true_loss"] > 0.03:
                n_harmful_commit += 1
            if pick["beneficial_and_safe"]:
                n_bs_commit += 1
                per_dataset[w["dataset"]]["bs_commits"] += 1
        if protected:
            prot_n += 1
            if pick is not None:
                prot_edit += 1
                if pick["true_loss"] > 0.03:
                    prot_harm += 1
        if contaminated:
            cont_n += 1
            cont_gains.append(gain)
            if pick is not None:
                cont_edit += 1
                if pick["beneficial"]:
                    cont_improved += 1
                if pick["beneficial_and_safe"]:
                    cont_bs += 1

    total_bs = sum(v["bs_commits"] for v in per_dataset.values())
    max_share = max((v["bs_commits"] / total_bs
                     for v in per_dataset.values()), default=0.0) if total_bs else 0.0
    return {
        "n_windows": n,
        "committed": n_committed,
        "commit_rate": n_committed / max(n, 1),
        "damage": float(np.mean(losses)),
        "damage_per_commit": n_harmful_commit / max(n_committed, 1),
        "beneficial_commits": n_bs_commit,
        "protected_mis_edit_rate": prot_edit / max(prot_n, 1),
        "protected_harmful_rate": prot_harm / max(prot_n, 1),
        "coverage": cont_edit / max(cont_n, 1),
        "beneficial_coverage": cont_improved / max(cont_n, 1),
        "bs_coverage": cont_bs / max(cont_n, 1),
        "mean_repair_gain_contaminated": float(np.mean(cont_gains)) if cont_gains else 0.0,
        "max_dataset_bs_share": float(max_share),
        "family_funnel": {k: dict(v) for k, v in family_funnel.items()},
        # Per-window vectors for paired bootstrap.
        "_losses": losses,
        "_protected_edited": [
            1.0 if (rs[0]["stratum"] in PROTECTED_STRATA and committed.get(uid)) else 0.0
            for uid, rs in by_window.items()
        ],
        "_cont_improved": [
            1.0 if (rs[0]["stratum"] == "contaminated"
                    and committed.get(uid) and committed[uid]["beneficial"]) else 0.0
            for uid, rs in by_window.items()
        ],
    }


def _paired_bootstrap(a, b, n_boot=10000, seed=20260901):
    """Mean paired difference a - b with a percentile interval."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n = len(a)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, n, size=(n_boot, n))
    diffs = (a[idx] - b[idx]).mean(axis=1)
    return {
        "diff": float(a.mean() - b.mean()),
        "ci": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v3_training_data.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v3_arms_compare.json"))
    args = ap.parse_args()

    rows = _load_rows(Path(args.data))
    real_rows = [r for r in rows if not r["dataset"].startswith("ood:")]
    ood_rows = [r for r in rows if r["dataset"].startswith("ood:")]
    real_datasets = sorted({r["dataset"] for r in real_rows})
    print(f"{len(rows)} candidates, {len(real_rows)} real, "
          f"{len(ood_rows)} OOD stress, datasets {real_datasets}", flush=True)

    # -- v2_frozen and oracle: decision rules need no training ----------------
    arms = {}
    arms["v2_frozen"] = _episode_metrics(real_rows, _decisions("v2_frozen", real_rows))
    arms["oracle"] = _episode_metrics(real_rows, _decisions("oracle", real_rows))
    print(f"v2_frozen: commit={arms['v2_frozen']['commit_rate']:.4f} "
          f"damage={arms['v2_frozen']['damage']:.4f} "
          f"pme={arms['v2_frozen']['protected_mis_edit_rate']:.4f} "
          f"cov={arms['v2_frozen']['beneficial_coverage']:.4f}", flush=True)
    print(f"oracle:    commit={arms['oracle']['commit_rate']:.4f} "
          f"damage={arms['oracle']['damage']:.4f} "
          f"pme={arms['oracle']['protected_mis_edit_rate']:.4f} "
          f"cov={arms['oracle']['beneficial_coverage']:.4f}", flush=True)

    # -- learned arms: leave-one-dataset-out ----------------------------------
    learned = {
        "statistical_only": (STAT_FEATURES, False),
        "TSFM_only": (TSFM_FEATURES, False),
        "joint_v3_pre": (ALL_FEATURES, False),
        "v3_1_pre": (ALL_FEATURES, True),
    }
    # Pooled per-window outcome vectors across folds (each real window is
    # tested exactly once, by a model that never saw its dataset).
    pooled = {name: defaultdict(list) for name in learned}
    fold_reports = {name: {} for name in learned}
    pooled_committed = {}
    for name, (feats, dual) in learned.items():
        all_committed = {}
        for test_ds in real_datasets:
            train, cal, test = _split_by_dataset(real_rows, test_ds)
            shield = _fit_shield(train, cal, feats, dual=dual)
            committed = _decisions(name, test, shield=shield, feature_names=feats)
            all_committed.update(committed)
            m = _episode_metrics(test, committed)
            fold_reports[name][test_ds] = {
                k: v for k, v in m.items() if not k.startswith("_")
            }
            pooled[name]["loss"].extend(m["_losses"])
            pooled[name]["prot"].extend(m["_protected_edited"])
            pooled[name]["cov"].extend(m["_cont_improved"])
            print(f"  {name} test={test_ds}: commit={m['commit_rate']:.3f} "
                  f"damage={m['damage']:.4f} pme={m['protected_mis_edit_rate']:.4f} "
                  f"bcov={m['beneficial_coverage']:.4f}", flush=True)
        # Aggregate learned arm over folds, window-pooled.
        arms[name] = _episode_metrics(real_rows, all_committed)
        pooled_committed[name] = all_committed

    # -- paired bootstrap: joint vs statistical --------------------------------
    boot = {
        "coverage_joint_minus_stat": _paired_bootstrap(
            pooled["joint_v3_pre"]["cov"], pooled["statistical_only"]["cov"]),
        "damage_joint_minus_stat": _paired_bootstrap(
            pooled["joint_v3_pre"]["loss"], pooled["statistical_only"]["loss"]),
        "coverage_joint_minus_tsfm": _paired_bootstrap(
            pooled["joint_v3_pre"]["cov"], pooled["TSFM_only"]["cov"]),
        "coverage_tsfm_minus_stat": _paired_bootstrap(
            pooled["TSFM_only"]["cov"], pooled["statistical_only"]["cov"]),
        "coverage_v31_minus_joint": _paired_bootstrap(
            pooled["v3_1_pre"]["cov"], pooled["joint_v3_pre"]["cov"]),
        "damage_v31_minus_joint": _paired_bootstrap(
            pooled["v3_1_pre"]["loss"], pooled["joint_v3_pre"]["loss"]),
        "pme_v31_minus_joint": _paired_bootstrap(
            pooled["v3_1_pre"]["prot"], pooled["joint_v3_pre"]["prot"]),
        "coverage_v31_minus_stat": _paired_bootstrap(
            pooled["v3_1_pre"]["cov"], pooled["statistical_only"]["cov"]),
    }

    # -- root-cause attribution of the commits ---------------------------------
    diagnoses = {name: _commit_diagnosis(pooled_committed[name])
                 for name in ("joint_v3_pre", "v3_1_pre")}

    # -- OOD stress: decisions of the last joint fold model are not meaningful;
    #    report the joint arm's pooled behaviour on OOD via the model trained
    #    on all real data with an 80/20 split of it. ----------------------------
    train, cal, _ = _split_by_dataset(real_rows, "__none__")
    shield_ood = _fit_shield(train, cal, ALL_FEATURES)
    ood_committed = _decisions("joint_v3_pre", ood_rows, shield=shield_ood,
                               feature_names=ALL_FEATURES)
    ood_edit = sum(1 for v in ood_committed.values() if v is not None)
    ood_report = {"n_windows": len(ood_committed), "edited": ood_edit,
                  "edit_rate": ood_edit / max(len(ood_committed), 1)}

    # -- gates ------------------------------------------------------------------
    def _gates(arm_name):
        a = arms[arm_name]
        return {
            "protected_mis_edit<=0.0055": a["protected_mis_edit_rate"] <= 0.0055,
            "damage<=0.05": a["damage"] <= 0.05,
            "coverage>=0.08": a["beneficial_coverage"] >= 0.08,
            "beneficial_commits>=10": a["beneficial_commits"] >= 10,
            "coverage>v2_frozen": a["beneficial_coverage"] > v2["beneficial_coverage"],
            "joint>=stat+10pct_rel": (
                a["beneficial_coverage"] >= 1.10 * s["beneficial_coverage"]
                and a["damage"] <= s["damage"] + 1e-9
            ),
            "max_dataset_share<=0.60": a["max_dataset_bs_share"] <= 0.60,
        }

    v2 = arms["v2_frozen"]
    s = arms["statistical_only"]
    gates = {"joint_v3_pre": _gates("joint_v3_pre"),
             "v3_1_pre": _gates("v3_1_pre")}

    out = {
        "arms": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                 for k, v in arms.items()},
        "folds": fold_reports,
        "paired_bootstrap": boot,
        "commit_diagnosis": diagnoses,
        "ood_stress": ood_report,
        "gates": gates,
        "gates_pass": {k: all(v.values()) for k, v in gates.items()},
        "config": {"alpha": ALPHA, "model": vars(ShieldConfig()),
                   "v2_taus": V2_TAUS, "split": "leave-one-dataset-out",
                   "split_seed": 20260901},
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=float),
                              encoding="utf-8")
    print("\n=== pooled arm summary (window-level, all folds) ===")
    hdr = f"{'arm':18s}{'commit':>8s}{'damage':>8s}{'dmg/com':>9s}{'pme':>8s}{'bcov':>8s}{'bcom':>6s}{'gain':>8s}"
    print(hdr)
    for name, m in arms.items():
        print(f"{name:18s}{m['commit_rate']:8.4f}{m['damage']:8.4f}"
              f"{m['damage_per_commit']:9.4f}{m['protected_mis_edit_rate']:8.4f}"
              f"{m['beneficial_coverage']:8.4f}{m['beneficial_commits']:6.0f}"
              f"{m['mean_repair_gain_contaminated']:8.4f}")
    print("\ngates:", json.dumps(gates, indent=1))
    print("paired bootstrap:", json.dumps(boot, indent=1))
    print("ood stress:", json.dumps(ood_report))
    print(f"\n___V3_ARMS_DONE___ wrote {args.out}")


if __name__ == "__main__":
    main()
