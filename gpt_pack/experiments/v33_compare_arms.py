"""v3.3 offline arm comparison (Phase 5), pre-registered in
``docs/v3_3_mast_pics_design.md``.

All eight arms are computed under the v3.3 action-semantic labels
(``results/v33_training_data.jsonl``); v3.2 label-dependent numbers are not a
baseline. Same candidate pool, same RESEGMENT closure, same fixed HGB, same
leave-one-real-dataset-out split (seed 20260901), first-commit episode replay,
sample_uid-paired bootstrap (10000), every fold reported.

Arms:
  v2_frozen_relabel         shipped verify() conjunction
  v3_2_bugfix_relabel       v3.1 method on repaired features (relabelled)
  PICS_joint_relabel        v3.2 PICS, joint features (relabelled)
  PICS_TSFM_relabel         v3.2 PICS, TSFM features (relabelled)
  MAST_no_support           MAST-PICS, certificate off
  MAST_support_consequence  the formal v3.3 arm
  MAST_v2_hard_structure    formal arm + frozen v2 conjunction as a hard gate
  oracle_relabel            per-window max-gain beneficial_and_safe commit

The formal OOD stress set is the frozen seed-313 corpus
(``results/v33_ood_candidates.jsonl``); the 56 OOD windows inside the
seed-101 corpus are reported as historical/development stress only.

Metric naming: ``conditional_harm_rate`` (CHR) is the share of commits with
true_loss > 0.03 -- what the v3.2 script misleadingly called
``n_harm / n_committed`` / ``cond_damage``. ``cond_damage`` is kept here as a
documented alias only.
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

from metrics_common import conditional_loss_metrics  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402
from introact_ts.mast_pics import (  # noqa: E402
    GATE_MODES, MASTPICS, v2_hard_gate_ok, v2_structure_ok,
)
from introact_ts.pics import PICS_JOINT_FEATURES, PICS_TSFM_FEATURES  # noqa: E402
from v32_compare_arms import (  # noqa: E402
    _BugfixShield, _PICSArm, _load_rows, _paired_boot, _ratio_boot, _split,
    _v2_accept, PROTECTED_STRATA,
)

FORMAL_ARM = "MAST_support_consequence"
COLLISION_FREE = ("ood:random_walk", "ood:pulse_train")


# -- arms -----------------------------------------------------------------------


class _MASTArm:
    def __init__(self, gate_mode):
        self.model = MASTPICS(gate_mode=gate_mode)
        self.last_reason = ""

    def fit(self, train, cal):
        self.model.fit(train, cal)

    def accept(self, row) -> bool:
        ok, self.last_reason = self.model.decide(row)
        return ok

    def explain(self, row) -> dict:
        s_bs, s_h, spread = self.model._scores(row)
        sd = self.model._support_distance(row)
        thr = self.model.thresholds.get(row["family"])
        return {
            "benefit_score": s_bs, "harm_score": s_h, "harm_spread": spread,
            "support_distance": sd, "support_q95": self.model.support_q95,
            "selected_threshold": list(thr) if thr else None,
            "v2_structure_ok": v2_structure_ok(
                row["family"], row["struct_distortion"]),
            "ood_hazard": self.model._hazard(row, spread, sd),
        }


class _PICSArmX(_PICSArm):
    """_PICSArm plus per-decision explainability for the commit records."""

    def explain(self, row) -> dict:
        from v32_compare_arms import _feats
        f = [_feats(row, self.names)]
        bs_h, harm_h = self.pics.heads.get(row["family"], self.pics.global_heads)
        thr = self.pics.thresholds.get(row["family"])
        return {
            "benefit_score": float(bs_h.pessimistic(f)[0]),
            "harm_score": float(harm_h.pessimistic(f)[0]),
            "harm_spread": float(harm_h.spread(f)[0]),
            "spread_cap": float(self.pics.spread_cap),
            "selected_threshold": list(thr) if thr else None,
        }


def _decisions(rows, arm):
    """First-commit episode replay.

    Returns uid -> (row, position, reason, explain) or None. ``explain`` is a
    per-decision score dump from arms that implement it; it is computed fresh
    at decision time so no state is shared between arms.
    """
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
                best = max(bs, key=lambda r: r["true_repair_gain"])
                pick = (best, rs.index(best), "oracle", None)
        else:
            for pos, r in enumerate(rs):
                if r["family"] not in EPISODE_FAMILY_ORDER and arm != "v2_frozen":
                    continue  # RESEGMENT closed in every learned arm
                if arm == "v2_frozen":
                    acc, reason = _v2_accept(r), "v2_verify"
                else:
                    acc, reason = arm.accept(r), getattr(arm, "last_reason", "")
                if acc:
                    explain = arm.explain(r) if hasattr(arm, "explain") else None
                    pick = (r, pos, reason, explain)
                    break
        committed[uid] = pick
    return committed


# -- metrics ----------------------------------------------------------------------


def _episode_metrics(rows, committed, keep_records=False):
    by_window = defaultdict(list)
    for r in rows:
        by_window[r["sample_uid"]].append(r)
    out = {"_loss": [], "_prot_edit": [], "_cont_improved": [],
           "_committed": [], "_harmful_commit": [], "_cont_gain": [],
           "_cond_losses": []}
    n_committed = n_bs = 0
    prot_n = prot_edit = cont_n = cont_edit = cont_imp = 0
    per_ds = defaultdict(lambda: [0, 0])
    per_prot_stratum = defaultdict(lambda: [0, 0])
    records = []
    for uid, rs in by_window.items():
        w = rs[0]
        got = committed.get(uid)
        pick = got[0] if got else None
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
        if prot:
            per_prot_stratum[w["stratum"]][1] += 1
            if pick is not None:
                per_prot_stratum[w["stratum"]][0] += 1
        if pick is not None:
            n_committed += 1
            n_bs += int(bool(pick["beneficial_and_safe"]))
            out["_cond_losses"].append(pick["true_loss"])
            if pick["beneficial_and_safe"]:
                per_ds[w["dataset"]][0] += 1
            if keep_records:
                rec = {
                    "sample_uid": uid, "dataset": w["dataset"],
                    "stratum": w["stratum"], "true_kind": w["true_kind"],
                    "family": pick["family"], "rung": pick["rung"],
                    "params": pick["params"],
                    "episode_position": got[1],
                    "n_episode_candidates": len(rs),
                    "verdict_reason": got[2],
                    "decision_detail": got[3],
                    "corrupted_hash": pick["corrupted_hash"],
                    "clean_hash": pick["clean_hash"],
                    "output_hash": pick.get("output_hash"),
                    "forward_fill_baseline_hash": pick.get(
                        "forward_fill_baseline_hash"),
                    "before_nmse": pick["before_nmse"],
                    "after_nmse": pick["after_nmse"],
                    "true_loss": pick["true_loss"],
                    "true_repair_gain": pick["true_repair_gain"],
                    "harmful": harmful,
                    "target_mask_gain": pick.get("target_mask_gain"),
                    "observed_support_drift": pick.get("observed_support_drift"),
                    "delta_utility": pick["delta_utility"],
                    "struct_distortion": pick["struct_distortion"],
                    "risk": pick["risk"],
                }
                records.append(rec)
        per_ds[w["dataset"]][1] += 1
        prot_n += int(prot)
        prot_edit += int(prot and pick is not None)
        cont_n += int(cont)
        cont_edit += int(cont and pick is not None)
        cont_imp += int(cont and improved)
    n = max(len(by_window), 1)
    total_bs = sum(v[0] for v in per_ds.values())
    cond = conditional_loss_metrics(out["_cond_losses"])
    out.update({
        "n_windows": len(by_window),
        "committed": n_committed,
        "commit_rate": n_committed / n,
        "damage": float(np.mean(out["_loss"])),
        # CHR, correctly named; cond_damage kept as a documented alias.
        "conditional_harm_rate": cond["conditional_harm_rate"],
        "cond_damage": cond["conditional_harm_rate"],
        "conditional_mean_loss": cond["conditional_mean_loss"],
        "conditional_loss_p90": cond["conditional_loss_p90"],
        "conditional_loss_p95": cond["conditional_loss_p95"],
        "beneficial_commits": n_bs,
        "protected_mis_edit_rate": prot_edit / max(prot_n, 1),
        "protected_stratum_edit": {
            k: v[0] / max(v[1], 1) for k, v in per_prot_stratum.items()},
        "coverage": cont_edit / max(cont_n, 1),
        "beneficial_coverage": cont_imp / max(cont_n, 1),
        "mean_repair_gain_contaminated": float(np.mean(out["_cont_gain"])) if cont_n else 0.0,
        "max_dataset_bs_share": max((v[0] / total_bs for v in per_ds.values()),
                                    default=0.0) if total_bs else 0.0,
    })
    if keep_records:
        out["records"] = records
    return out


# -- OOD stress ------------------------------------------------------------------


def _ood_replay(ood_rows, model_or_rule, manifest_windows=None):
    """Replay OOD episodes. ``manifest_windows`` (records with sample_uid and
    dataset) adds the zero-candidate windows to the denominators, so a form
    the proposer never touches still counts against the edit rate."""
    committed = _decisions(ood_rows, model_or_rule)
    by_window = defaultdict(list)
    for r in ood_rows:
        by_window[r["sample_uid"]].append(r)
    if manifest_windows is not None:
        for w in manifest_windows:
            by_window.setdefault(w["sample_uid"], [])
            if not by_window[w["sample_uid"]]:
                by_window[w["sample_uid"]] = [
                    {"dataset": w["dataset"], "sample_uid": w["sample_uid"],
                     "stratum": w.get("stratum"), "_stub": True}]
    # NOTE: cross-domain windows are named "ood:exchange"/"ood:solar", so the
    # synthetic/real split must key on stratum, never on the dataset prefix.
    forms = defaultdict(lambda: {"n_windows": 0, "proposed": 0, "edited": 0,
                                 "families": Counter(), "var_ratios": [],
                                 "stratum": None})
    edits = []
    for uid, rs in by_window.items():
        form = rs[0]["dataset"]
        real_rs = [r for r in rs if not r.get("_stub")]
        f = forms[form]
        f["n_windows"] += 1
        f["stratum"] = rs[0].get("stratum")
        if real_rs:
            f["proposed"] += 1
        got = committed.get(uid)
        if got:
            pick, pos, _reason, _explain = got
            f["edited"] += 1
            f["families"][pick["family"]] += 1
            if pick.get("var_ratio") is not None:
                f["var_ratios"].append(pick["var_ratio"])
            edits.append({
                "sample_uid": uid, "dataset": form, "family": pick["family"],
                "rung": pick["rung"], "episode_position": pos,
                "n_episode_candidates": len(rs),
                "output_hash": pick.get("output_hash"),
                "before_nmse": pick["before_nmse"],
                "after_nmse": pick["after_nmse"],
                "true_loss": pick["true_loss"],
                "delta_utility": pick["delta_utility"],
                "struct_distortion": pick["struct_distortion"],
                "var_ratio": pick.get("var_ratio"),
            })
    report = {}
    for form, f in sorted(forms.items()):
        report[form] = {
            "stratum": f["stratum"],
            "n_windows": f["n_windows"],
            "proposal_rate": f["proposed"] / f["n_windows"],
            "edited": f["edited"],
            "edit_rate": f["edited"] / f["n_windows"],
            "accept_given_proposal": f["edited"] / max(f["proposed"], 1),
            "edit_families": dict(f["families"]),
            "mean_var_ratio_of_edits": float(np.mean(f["var_ratios"]))
            if f["var_ratios"] else None,
        }
    return report, edits


def _synthetic_forms(report):
    return [f for f, r in report.items() if r.get("stratum") == "clean_ood"]


def _real_forms(report):
    return [f for f, r in report.items() if r.get("stratum") == "real_ood"]


def _subset_edit_rate(report, forms):
    n = sum(report[f]["n_windows"] for f in forms if f in report)
    e = sum(report[f]["edited"] for f in forms if f in report)
    return {"n_windows": n, "edited": e, "edit_rate": e / max(n, 1)}


# -- main -------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--ood", default=str(ROOT / "results" / "v33_ood_candidates.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v33_arms_compare.json"))
    ap.add_argument("--harmful-out", default=str(ROOT / "results" / "v33_harmful_commits.json"))
    ap.add_argument("--ood-out", default=str(ROOT / "results" / "v33_ood_attribution.json"))
    ap.add_argument("--frontier-out", default=str(ROOT / "results" / "v33_risk_coverage.json"))
    ap.add_argument("--support-out", default=str(ROOT / "results" / "v33_support_audit.json"))
    args = ap.parse_args()

    rows = _load_rows(args.data)
    real = [r for r in rows if not r["dataset"].startswith("ood:")]
    ood_hist = [r for r in rows if r["dataset"].startswith("ood:")]
    ood_formal = _load_rows(args.ood)
    datasets = sorted({r["dataset"] for r in real})
    print(f"{len(rows)} calibration candidates ({len(real)} real, "
          f"{len(ood_hist)} historical OOD), {len(ood_formal)} formal-OOD "
          f"candidates, {len(datasets)} real datasets", flush=True)

    learned = {
        "v3_2_bugfix_relabel": lambda: _BugfixShield(),
        "PICS_joint_relabel": lambda: _PICSArmX(PICS_JOINT_FEATURES),
        "PICS_TSFM_relabel": lambda: _PICSArmX(PICS_TSFM_FEATURES),
        "MAST_no_support": lambda: _MASTArm("none"),
        FORMAL_ARM: lambda: _MASTArm("support_and_consequence"),
        "MAST_v2_hard_structure": lambda: _MASTArm("support_and_consequence_hard"),
    }

    arms, folds, fitted_by_fold = {}, {}, defaultdict(dict)
    arms["v2_frozen_relabel"] = _episode_metrics(real, _decisions(real, "v2_frozen"))
    arms["oracle_relabel"] = _episode_metrics(real, _decisions(real, "oracle"))
    print("v2_frozen_relabel and oracle_relabel done", flush=True)

    for name, make in learned.items():
        all_committed = {}
        folds[name] = {}
        for test_ds in datasets:
            train, cal, test = _split(real, test_ds)
            model = make()
            model.fit(train, cal)
            fitted_by_fold[name][test_ds] = model
            committed = _decisions(test, model)
            all_committed.update(committed)
            m = _episode_metrics(test, committed)
            folds[name][test_ds] = {k: v for k, v in m.items()
                                    if not k.startswith("_")}
            print(f"  {name} test={test_ds}: commit={m['commit_rate']:.3f} "
                  f"damage={m['damage']:.4f} CHR={m['conditional_harm_rate']:.3f} "
                  f"pme={m['protected_mis_edit_rate']:.4f} "
                  f"bcov={m['beneficial_coverage']:.4f}", flush=True)
        keep = name in (FORMAL_ARM, "PICS_joint_relabel")
        arms[name] = _episode_metrics(real, all_committed, keep_records=keep)

    # -- formal + historical OOD stress -----------------------------------------
    ood_manifest_path = ROOT / "results" / "v33_ood_manifest.json"
    ood_manifest_windows = None
    if ood_manifest_path.exists():
        ood_manifest_windows = json.loads(
            ood_manifest_path.read_text(encoding="utf-8"))["records"]
    train_all, cal_all, _ = _split(real, "__none__")
    ood_report, ood_edits, support_audit = {}, {}, {}
    ood_arms = dict(learned)
    for name, make in ood_arms.items():
        model = make()
        model.fit(train_all, cal_all)
        rep_f, edits_f = _ood_replay(ood_formal, model, ood_manifest_windows)
        rep_h, _ = _ood_replay(ood_hist, model)
        ood_report[name] = {
            "formal": rep_f,
            "synthetic_overall": _subset_edit_rate(rep_f, _synthetic_forms(rep_f)),
            "collision_free": _subset_edit_rate(rep_f, list(COLLISION_FREE)),
            "real_ood": _subset_edit_rate(rep_f, _real_forms(rep_f)),
            "historical_dev": rep_h,
        }
        ood_edits[name] = edits_f
        if isinstance(model, _MASTArm):
            per_form = {}
            by_form = defaultdict(list)
            for r in ood_formal:
                by_form[r["dataset"]].append(r)
            for form, frs in sorted(by_form.items()):
                seen, rows_u = set(), []
                for r in frs:
                    if r["sample_uid"] not in seen:
                        seen.add(r["sample_uid"])
                        rows_u.append(r)
                dists = model.model.support.score(
                    [r["profile"] for r in rows_u])
                low = dists > model.model.support_q95
                unstable = np.array([
                    not v2_structure_ok(r["family"], r["struct_distortion"])
                    for r in frs])
                sd_fr = model.model.support.score([r["profile"] for r in frs])
                per_form[form] = {
                    "mean_support_distance": float(np.mean(dists)),
                    "frac_low_support_windows": float(np.mean(low)),
                    "frac_unstable_candidates": float(np.mean(unstable)),
                    "frac_hazard_candidates": float(np.mean(
                        (sd_fr > model.model.support_q95) & unstable)),
                }
            support_audit[name] = {
                "support_q95": model.model.support_q95,
                "K": model.model.K, "per_form": per_form,
            }
        print(f"  ood {name}: synthetic edit "
              f"{ood_report[name]['synthetic_overall']['edit_rate']:.3f}, "
              f"real {ood_report[name]['real_ood']['edit_rate']:.3f}",
              flush=True)
    # v2_frozen on the formal OOD set, the hard-rule reference.
    rep_v2, _ = _ood_replay(ood_formal, "v2_frozen", ood_manifest_windows)
    ood_report["v2_frozen_relabel"] = {
        "formal": rep_v2,
        "synthetic_overall": _subset_edit_rate(rep_v2, _synthetic_forms(rep_v2)),
        "collision_free": _subset_edit_rate(rep_v2, list(COLLISION_FREE)),
        "real_ood": _subset_edit_rate(rep_v2, _real_forms(rep_v2)),
    }

    # -- paired bootstrap ---------------------------------------------------------
    pj = arms["PICS_joint_relabel"]
    fo = arms[FORMAL_ARM]
    boot = {
        "bcov_formal_minus_pics": _paired_boot(fo["_cont_improved"], pj["_cont_improved"]),
        "damage_formal_minus_pics": _paired_boot(fo["_loss"], pj["_loss"]),
        "pme_formal_minus_pics": _paired_boot(fo["_prot_edit"], pj["_prot_edit"]),
        "bcov_formal_minus_v2": _paired_boot(fo["_cont_improved"], arms["v2_frozen_relabel"]["_cont_improved"]),
        "bcov_pics_minus_v2": _paired_boot(pj["_cont_improved"], arms["v2_frozen_relabel"]["_cont_improved"]),
    }
    chr_ci = _ratio_boot(fo["_harmful_commit"], fo["_committed"])

    # Conditional mean loss bootstrap: committed losses aligned by window,
    # KEEP windows marked with a -1 sentinel and excluded from the mean.
    def _cond_mean_boot(a_rows, b_rows, n_boot=10000, seed=20260901):
        a, b = np.asarray(a_rows), np.asarray(b_rows)
        rng = np.random.RandomState(seed)
        idx = rng.randint(0, len(a), size=(n_boot, len(a)))
        diffs = []
        for bi in idx:
            ca, cb = a[bi], b[bi]
            ca, cb = ca[ca > -1], cb[cb > -1]
            if len(ca) and len(cb):
                diffs.append(ca.mean() - cb.mean())
        d = np.asarray(diffs)
        return {"diff_ci": [float(np.percentile(d, 2.5)),
                            float(np.percentile(d, 97.5))]}
    cml_boot = _cond_mean_boot(
        np.where(np.asarray(fo["_committed"], dtype=bool), fo["_loss"], -1.0),
        np.where(np.asarray(pj["_committed"], dtype=bool), pj["_loss"], -1.0))

    # -- gates (pre-registered, docs/v3_3_mast_pics_design.md §6) ------------------
    pics_prot = pj["protected_stratum_edit"]
    stratum_ok = all(
        fo["protected_stratum_edit"].get(s, 0.0) <= pics_prot.get(s, 0.0) + 1e-12
        for s in PROTECTED_STRATA)
    syn_forms_ok = sum(
        1 for f, r in ood_report[FORMAL_ARM]["formal"].items()
        if r.get("stratum") == "clean_ood" and r["edit_rate"] <= 0.05)
    gates = {
        # safety
        "pme<=0.0055": fo["protected_mis_edit_rate"] <= 0.0055,
        "synthetic_ood_edit<=0.05":
            ood_report[FORMAL_ARM]["synthetic_overall"]["edit_rate"] <= 0.05,
        "real_ood_edit<=0.05":
            ood_report[FORMAL_ARM]["real_ood"]["edit_rate"] <= 0.05,
        "CHR<=0.10": fo["conditional_harm_rate"] <= 0.10,
        "cond_mean_loss<pics":
            fo["conditional_mean_loss"] < pj["conditional_mean_loss"],
        "max_dataset_bs_share<=0.50": fo["max_dataset_bs_share"] <= 0.50,
        "protected_strata_not_worse": stratum_ok,
        # liveness
        "bcov>=1.10*pics":
            fo["beneficial_coverage"] >= 1.10 * pj["beneficial_coverage"],
        "beneficial_commits>=10": fo["beneficial_commits"] >= 10,
        "cont_mean_gain>=pics":
            fo["mean_repair_gain_contaminated"]
            >= pj["mean_repair_gain_contaminated"],
        "coverage>v2_frozen":
            fo["beneficial_coverage"]
            > arms["v2_frozen_relabel"]["beneficial_coverage"],
        # Pareto: at least one strict improvement supported by the 95% CI
        "pareto_strict_improvement": (
            (boot["bcov_formal_minus_pics"]["ci"][0] > 0
             and fo["damage"] <= pj["damage"])
            or (cml_boot["diff_ci"][1] < 0
                and fo["beneficial_coverage"] >= pj["beneficial_coverage"])),
        # OOD detail
        "three_synthetic_forms<=0.05": syn_forms_ok >= 3,
        "collision_free<=0.05":
            ood_report[FORMAL_ARM]["collision_free"]["edit_rate"] <= 0.05,
    }
    gates_pass = all(gates.values())

    # -- risk-coverage frontier ------------------------------------------------------
    # Sweep a global benefit threshold over the episode grid, harm caps held at
    # their calibrated per-family values, replayed per held-out fold and pooled.
    from introact_ts.contextual_shield import EPISODE_GRID

    def _frontier(name, model_by_fold, is_mast):
        points = []
        for g in EPISODE_GRID:
            pooled = {}
            for test_ds in datasets:
                model = model_by_fold[test_ds]
                m = model.model if is_mast else model.pics
                saved = dict(m.thresholds)
                m.thresholds = {f: (float(g), t[1])
                                for f, t in saved.items()}
                pooled.update(_decisions(
                    [r for r in real if r["dataset"] == test_ds], model))
                m.thresholds = saved
            met = _episode_metrics(real, pooled)
            points.append({
                "benefit_threshold": float(g),
                "damage": met["damage"],
                "conditional_harm_rate": met["conditional_harm_rate"],
                "conditional_mean_loss": met["conditional_mean_loss"],
                "beneficial_coverage": met["beneficial_coverage"],
                "protected_mis_edit_rate": met["protected_mis_edit_rate"],
            })
        return points

    frontier = {
        FORMAL_ARM: _frontier(FORMAL_ARM, fitted_by_fold[FORMAL_ARM], True),
        "PICS_joint_relabel": _frontier(
            "PICS_joint_relabel", fitted_by_fold["PICS_joint_relabel"], False),
    }

    # -- outputs ---------------------------------------------------------------------
    def strip(m):
        return {k: v for k, v in m.items()
                if not k.startswith("_") and k != "records"}

    out = {
        "arms": {k: strip(v) for k, v in arms.items()},
        "folds": folds,
        "ood_stress": ood_report,
        "paired_bootstrap": boot,
        "cond_mean_loss_bootstrap": cml_boot,
        "chr_ci_formal": chr_ci,
        "gates": gates,
        "gates_pass": gates_pass,
        "config": {
            "alpha": 0.03, "split": "leave-one-dataset-out",
            "split_seed": 20260901, "bootstrap": 10000,
            "labels": "v3.3 action-semantic (IMPUTE materialised KEEP)",
            "alias_note": "cond_damage is the v3.2 name for "
                          "conditional_harm_rate",
            "eligible_families": list(EPISODE_FAMILY_ORDER),
            "mast_benefit_target": "beneficial",
            "mast_harm_target": "harmful",
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=float),
                              encoding="utf-8")

    harm = {}
    for name in (FORMAL_ARM, "PICS_joint_relabel"):
        recs = arms[name].get("records", [])
        bad = [r for r in recs if r["harmful"]]
        harm[name] = {
            "harmful_commits": bad,
            "n_committed": len(recs),
            "attribution": {
                "by_family": dict(Counter(c["family"] for c in bad)),
                "by_source": dict(Counter(c["dataset"] for c in bad)),
                "by_stratum": dict(Counter(c["stratum"] for c in bad)),
                "by_true_kind": dict(Counter(c["true_kind"] for c in bad)),
            },
            "all_commits": recs,
        }
    Path(args.harmful_out).write_text(json.dumps(harm, indent=1, default=float),
                                      encoding="utf-8")
    Path(args.ood_out).write_text(json.dumps(
        {"per_arm_formal_ood": ood_report, "edits": ood_edits,
         "historical_dev_note": "seed-101 ood: windows are development stress "
                                "only; the formal set is frozen seed 313"},
        indent=1, default=float), encoding="utf-8")
    Path(args.frontier_out).write_text(json.dumps(frontier, indent=1, default=float),
                                       encoding="utf-8")
    Path(args.support_out).write_text(json.dumps(
        {"support_audit": support_audit,
         "definition": "cosine kNN K=20 on training-fold pre-action profiles; "
                       "q95 from ID calibration; hazard = low_support AND "
                       "unstable_action (frozen v2 family structural "
                       "threshold)"},
        indent=1, default=float), encoding="utf-8")

    print("\n=== pooled arm summary (v3.3 labels) ===")
    print(f"{'arm':26s}{'commit':>8s}{'damage':>8s}{'CHR':>7s}{'cml':>7s}"
          f"{'pme':>8s}{'bcov':>8s}{'bcom':>6s}{'gain':>8s}")
    for name, m in arms.items():
        print(f"{name:26s}{m['commit_rate']:8.4f}{m['damage']:8.4f}"
              f"{m['conditional_harm_rate']:7.3f}{m['conditional_mean_loss']:7.3f}"
              f"{m['protected_mis_edit_rate']:8.4f}{m['beneficial_coverage']:8.4f}"
              f"{m['beneficial_commits']:6.0f}{m['mean_repair_gain_contaminated']:8.4f}")
    print("\ngates:", json.dumps(gates, indent=1))
    print("gates_pass:", gates_pass)
    print(f"\n___V33_ARMS_DONE___ wrote {args.out}")


if __name__ == "__main__":
    main()
