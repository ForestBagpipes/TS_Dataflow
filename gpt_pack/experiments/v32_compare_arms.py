"""v3.2 offline arm comparison, pre-registered in docs/v3_2_pics_preregistration.md.

Arms on the rebuilt candidate table (results/v32_training_data.jsonl), same
leave-one-real-dataset-out split, same first-commit episode rule:

  v2_frozen            shipped verify() conjunction
  v3_2_bugfix_only     v3.1 method (single dual-gate model, family as a
                       categorical) on the repaired features, calibrated by
                       episode replay
  PICS_stat_only       PICS on the statistical feature set
  PICS_TSFM_only       PICS on the TSFM feature set
  PICS_joint           PICS on the full source-invariant set
  oracle               per-window max-gain beneficial_and_safe commit

RESEGMENT never commits in any v3.2 arm (zero oracle safe headroom). OOD rows
are excluded from training and used only as the stress set. Statistics are
paired bootstrap by sample_uid (window), 10k resamples.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from introact_ts.contextual_shield import (  # noqa: E402
    ALL_FEATURES, CATEGORICAL_FEATURES, NUMERICAL_FEATURES, V31_FEATURES,
    CandidateFeatures, ContextualShield, ShieldConfig,
    EPISODE_FAMILY_ORDER, select_episode_thresholds,
)
from introact_ts.pics import (  # noqa: E402
    PICS, PICS_JOINT_FEATURES, PICS_STAT_FEATURES, PICS_TSFM_FEATURES,
)
from introact_ts.verify import VerifyConfig, verify  # noqa: E402

PROTECTED_STRATA = ("clean", "hard", "rare_valid", "changepoint")
V2_TAUS = {"DENOISE": 0.1, "DESPIKE": 0.0, "IMPUTE": 0.02, "RESEGMENT": 0.4}
V2_CFG = VerifyConfig(tau=0.02, tau_by_family=V2_TAUS)

GATES = {
    "protected_mis_edit<0.0181": 0.0181,
    "damage<=0.0506": 0.0506,
    "beneficial_coverage>=0.1455": 0.1455,
    "cont_mean_gain>=0.083": 0.083,
    "ood_edit<=0.05": 0.05,
    "cond_damage_ci_upper<0.379": 0.379,
}


def _load_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _feats(row, names):
    return CandidateFeatures(
        values=np.array([row["features"].get(n, 0.0) for n in names],
                        dtype=object),
        feature_names=tuple(names))


def _split(rows, test_dataset):
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
    train_uids, cal_uids = set(uids[:n_train]), set(uids[n_train:])
    train = [r for uid in train_uids for r in by_uid[uid]]
    cal = [r for uid in cal_uids for r in by_uid[uid]]
    return train, cal, test


# -- arm models -----------------------------------------------------------------


class _BugfixShield:
    """v3.1 method on repaired features with episode-replay calibration."""

    def __init__(self):
        self.sh = ContextualShield(ShieldConfig())
        self.sh.feature_names = V31_FEATURES
        self.thresholds = {}

    def fit(self, train, cal):
        X = self.sh.encode([_feats(r, V31_FEATURES) for r in train], fit=True)
        y_bs = np.array([r["beneficial_and_safe"] for r in train], dtype=int)
        y_h = np.array([r["harmful"] for r in train], dtype=int)
        self.sh.train(X, y_bs)
        self.sh.train_harm(X, y_h)
        windows = defaultdict(list)
        for r in cal:
            f = [_feats(r, V31_FEATURES)]
            windows[r["sample_uid"]].append({
                "family": r["family"],
                "score_bs": float(self.sh.predict_score(self.sh.encode(f))[0]),
                "score_harm": float(self.sh.predict_harm(self.sh.encode(f))[0]),
                "true_loss": r["true_loss"], "beneficial": r["beneficial"],
            })
        self.thresholds, self.calibration_report = select_episode_thresholds(
            list(windows.values()), dual=True, per_family=False)

    def accept(self, row) -> bool:
        thr = self.thresholds.get(row["family"])
        if thr is None:
            return False
        f = [_feats(row, V31_FEATURES)]
        s = float(self.sh.predict_score(self.sh.encode(f))[0])
        h = float(self.sh.predict_harm(self.sh.encode(f))[0])
        return s >= thr[0] and h <= thr[1]


class _PICSArm:
    def __init__(self, feature_names):
        self.pics = PICS(ShieldConfig(), feature_names)
        self.names = feature_names

    def fit(self, train, cal):
        self.pics.fit(train, cal)

    def accept(self, row) -> bool:
        return self.pics.decide(_feats(row, self.names),
                                row["family"]).value == "ACCEPTED"


def _v2_accept(row) -> bool:
    return verify(float(row["delta_utility"]), float(row["struct_distortion"]),
                  float(row["risk"]), V2_CFG, action=row["family"]
                  ).value == "ACCEPTED"


def _decisions(rows, arm):
    """arm: 'v2_frozen' | 'oracle' | fitted model with .accept(row)."""
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)
    committed = {}
    for uid, rs in by_window.items():
        pick = None
        if arm == "oracle":
            bs = [r for r in rs
                  if r["beneficial_and_safe"] and r["family"] in EPISODE_FAMILY_ORDER]
            if bs:
                pick = max(bs, key=lambda r: r["true_repair_gain"])
        else:
            for r in rs:
                if r["family"] not in EPISODE_FAMILY_ORDER and arm != "v2_frozen":
                    continue  # RESEGMENT closed in every v3.2 arm
                acc = _v2_accept(r) if arm == "v2_frozen" else arm.accept(r)
                if acc:
                    pick = r
                    break
        committed[uid] = pick
    return committed


# -- metrics ---------------------------------------------------------------------


def _episode_metrics(rows, committed):
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)
    out = {"_loss": [], "_prot_edit": [], "_cont_improved": [],
           "_committed": [], "_harmful_commit": [], "_cont_gain": []}
    n_committed = n_harm = n_bs = 0
    prot_n = prot_edit = cont_n = cont_edit = cont_imp = 0
    per_ds = defaultdict(lambda: [0, 0])
    harmful_commits = []
    for uid, rs in by_window.items():
        w = rs[0]
        pick = committed.get(uid)
        prot = w["stratum"] in PROTECTED_STRATA
        cont = w["stratum"] == "contaminated"
        loss = pick["true_loss"] if pick else 0.0
        gain = pick["true_repair_gain"] if pick else 0.0
        harmful = bool(pick and pick["true_loss"] > 0.03)
        improved = bool(pick and pick["beneficial"])
        out["_loss"].append(loss)
        out["_prot_edit"].append(float(prot and pick is not None))
        out["_cont_improved"].append(float(cont and improved))
        out["_committed"].append(float(pick is not None))
        out["_harmful_commit"].append(float(harmful))
        if cont:
            out["_cont_gain"].append(gain)
        if pick is not None:
            n_committed += 1
            n_harm += int(harmful)
            n_bs += int(bool(pick["beneficial_and_safe"]))
            if pick["beneficial_and_safe"]:
                per_ds[w["dataset"]][0] += 1
            if harmful:
                harmful_commits.append({
                    "sample_uid": uid, "dataset": w["dataset"],
                    "stratum": w["stratum"], "true_kind": w["true_kind"],
                    "family": pick["family"], "rung": pick["rung"],
                    "route_source": pick["features"]["route_source"],
                    "hypothesis": pick["features"]["hypothesis"],
                    "before_nmse": pick["before_nmse"],
                    "after_nmse": pick["after_nmse"],
                    "true_loss": pick["true_loss"],
                    "true_repair_gain": pick["true_repair_gain"],
                    "features": {k: pick["features"][k] for k in (
                        "confidence", "behav_risk", "delta_utility",
                        "delta_utility_rel", "struct_distortion", "seam_error",
                        "outside_support_drift", "improvement_consistency",
                        "improvement_depth", "action_risk", "touched_fraction",
                        "discard_share")},
                })
        per_ds[w["dataset"]][1] += 1
        prot_n += int(prot)
        prot_edit += int(prot and pick is not None)
        cont_n += int(cont)
        cont_edit += int(cont and pick is not None)
        cont_imp += int(cont and improved)
    n = max(len(by_window), 1)
    total_bs = sum(v[0] for v in per_ds.values())
    out.update({
        "n_windows": len(by_window),
        "committed": n_committed,
        "commit_rate": n_committed / n,
        "damage": float(np.mean(out["_loss"])),
        "cond_damage": n_harm / max(n_committed, 1),
        "beneficial_commits": n_bs,
        "protected_mis_edit_rate": prot_edit / max(prot_n, 1),
        "coverage": cont_edit / max(cont_n, 1),
        "beneficial_coverage": cont_imp / max(cont_n, 1),
        "mean_repair_gain_contaminated": float(np.mean(out["_cont_gain"])) if cont_n else 0.0,
        "max_dataset_bs_share": max((v[0] / total_bs for v in per_ds.values()),
                                    default=0.0) if total_bs else 0.0,
        "harmful_commits": harmful_commits,
    })
    return out


def _paired_boot(a, b, n_boot=10000, seed=20260901):
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(a), size=(n_boot, len(a)))
    d = (a[idx] - b[idx]).mean(axis=1)
    return {"diff": float(a.mean() - b.mean()),
            "ci": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}


def _ratio_boot(harmful, committed, n_boot=10000, seed=20260901):
    """CI for harmful/committed resampled by window."""
    h, c = np.asarray(harmful, float), np.asarray(committed, float)
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, len(h), size=(n_boot, len(h)))
    denom = c[idx].sum(axis=1)
    ok = denom > 0
    ratios = h[idx][ok].sum(axis=1) / denom[ok]
    return [float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v32_training_data.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v32_arms_compare.json"))
    ap.add_argument("--harmful-out", default=str(ROOT / "results" / "v32_harmful_commits.json"))
    args = ap.parse_args()

    rows = _load_rows(args.data)
    real = [r for r in rows if not r["dataset"].startswith("ood:")]
    ood = [r for r in rows if r["dataset"].startswith("ood:")]
    datasets = sorted({r["dataset"] for r in real})
    print(f"{len(rows)} candidates ({len(real)} real, {len(ood)} OOD), "
          f"{len(datasets)} datasets", flush=True)

    arms, pooled, folds = {}, {}, {}
    arms["v2_frozen"] = _episode_metrics(real, _decisions(real, "v2_frozen"))
    arms["oracle"] = _episode_metrics(real, _decisions(real, "oracle"))
    print("v2_frozen and oracle done", flush=True)

    learned = {
        "v3_2_bugfix_only": lambda: _BugfixShield(),
        "PICS_stat_only": lambda: _PICSArm(PICS_STAT_FEATURES),
        "PICS_TSFM_only": lambda: _PICSArm(PICS_TSFM_FEATURES),
        "PICS_joint": lambda: _PICSArm(PICS_JOINT_FEATURES),
    }
    for name, make in learned.items():
        all_committed = {}
        folds[name] = {}
        for test_ds in datasets:
            train, cal, test = _split(real, test_ds)
            model = make()
            model.fit(train, cal)
            committed = _decisions(test, model)
            all_committed.update(committed)
            m = _episode_metrics(test, committed)
            folds[name][test_ds] = {k: v for k, v in m.items()
                                    if not k.startswith("_") and k != "harmful_commits"}
            print(f"  {name} test={test_ds}: commit={m['commit_rate']:.3f} "
                  f"damage={m['damage']:.4f} pme={m['protected_mis_edit_rate']:.4f} "
                  f"bcov={m['beneficial_coverage']:.4f}", flush=True)
        arms[name] = _episode_metrics(real, all_committed)
        pooled[name] = arms[name]

    # OOD stress per learned arm: train on all real data (80/20 split), replay OOD.
    ood_report = {}
    train, cal, _ = _split(real, "__none__")
    for name, make in learned.items():
        model = make()
        model.fit(train, cal)
        committed = _decisions(ood, model)
        edited = sum(1 for v in committed.values() if v is not None)
        ood_report[name] = {"n_windows": len(committed), "edited": edited,
                            "edit_rate": edited / max(len(committed), 1)}
    print("ood stress done", flush=True)

    # Paired bootstrap by sample_uid (window) against the key controls.
    pj = pooled["PICS_joint"]
    boot = {
        "coverage_pics_minus_bugfix": _paired_boot(
            pj["_cont_improved"], pooled["v3_2_bugfix_only"]["_cont_improved"]),
        "damage_pics_minus_bugfix": _paired_boot(
            pj["_loss"], pooled["v3_2_bugfix_only"]["_loss"]),
        "pme_pics_minus_bugfix": _paired_boot(
            pj["_prot_edit"], pooled["v3_2_bugfix_only"]["_prot_edit"]),
        "coverage_pics_minus_stat": _paired_boot(
            pj["_cont_improved"], pooled["PICS_stat_only"]["_cont_improved"]),
        "coverage_pics_minus_tsfm": _paired_boot(
            pj["_cont_improved"], pooled["PICS_TSFM_only"]["_cont_improved"]),
        "coverage_pics_minus_v2": _paired_boot(
            pj["_cont_improved"], arms["v2_frozen"]["_cont_improved"]),
    }
    cond_ci = _ratio_boot(pj["_harmful_commit"], pj["_committed"])

    gates = {
        "protected_mis_edit<0.0181": pj["protected_mis_edit_rate"] < 0.0181,
        "damage<=0.0506": pj["damage"] <= 0.0506,
        "beneficial_coverage>=0.1455": pj["beneficial_coverage"] >= 0.1455,
        "cont_mean_gain>=0.083": pj["mean_repair_gain_contaminated"] >= 0.083,
        "ood_edit<=0.05": ood_report["PICS_joint"]["edit_rate"] <= 0.05,
        "cond_damage_ci_upper<0.379": cond_ci[1] < 0.379,
        "coverage>v2_frozen": pj["beneficial_coverage"] > arms["v2_frozen"]["beneficial_coverage"],
        "beneficial_commits>=10": pj["beneficial_commits"] >= 10,
        "max_dataset_share<=0.60": pj["max_dataset_bs_share"] <= 0.60,
    }

    def strip(m):
        return {k: v for k, v in m.items()
                if not k.startswith("_") and k != "harmful_commits"}

    out = {
        "arms": {k: strip(v) for k, v in arms.items()},
        "folds": folds,
        "ood_stress": ood_report,
        "paired_bootstrap": boot,
        "cond_damage_ci": cond_ci,
        "gates": gates,
        "gates_pass": all(gates.values()),
        "config": {"alpha": 0.03, "model": vars(ShieldConfig()),
                   "split": "leave-one-dataset-out", "split_seed": 20260901,
                   "eligible_families": list(EPISODE_FAMILY_ORDER)},
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=float),
                              encoding="utf-8")
    Path(args.harmful_out).write_text(json.dumps(
        {"PICS_joint": pj["harmful_commits"],
         "attribution": {
             "by_family": dict(Counter(c["family"] for c in pj["harmful_commits"])),
             "by_source": dict(Counter(c["dataset"] for c in pj["harmful_commits"])),
             "by_stratum": dict(Counter(c["stratum"] for c in pj["harmful_commits"])),
         }}, indent=1, default=float), encoding="utf-8")

    print("\n=== pooled arm summary ===")
    print(f"{'arm':18s}{'commit':>8s}{'damage':>8s}{'cond':>7s}{'pme':>8s}"
          f"{'bcov':>8s}{'bcom':>6s}{'gain':>8s}")
    for name, m in arms.items():
        print(f"{name:18s}{m['commit_rate']:8.4f}{m['damage']:8.4f}"
              f"{m['cond_damage']:7.3f}{m['protected_mis_edit_rate']:8.4f}"
              f"{m['beneficial_coverage']:8.4f}{m['beneficial_commits']:6.0f}"
              f"{m['mean_repair_gain_contaminated']:8.4f}")
    print("\ngates:", json.dumps(gates, indent=1))
    print("cond damage CI:", cond_ci)
    print("bootstrap:", json.dumps(boot, indent=1))
    print("ood:", json.dumps(ood_report, indent=1))
    print(f"\n___V32_ARMS_DONE___ wrote {args.out}")


if __name__ == "__main__":
    main()
