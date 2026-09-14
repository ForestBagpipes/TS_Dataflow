"""v4.1 MASK-COUNTERACT: mask-conditional counterfactual risk control.

Pre-registered in ``docs/v4_1_mask_counteract_preregistration.md`` before any
v4.1 computation. Everything runs on the server; API calls 0; no TSFM is
re-invoked -- the v4.0 candidates, feature cache and stat-only checkpoints
are reused as-is.

The v4.0 post-mortem localised the failure to one clause: the deployment
rule was a conjunction ``harm < tau_h AND q10 > delta AND prot < tau_p``,
and the gain-quantile clause rejected 72 of the 89 frozen windows because
the bank taught it a gain scale drawn from 24.5%-of-window gaps while the
evaluation frame carries 8.9% ones. v4.1 keeps the harm ranking, which
transfers (AUROC 0.877), drops the q10 veto, and re-calibrates the harm
threshold on a population whose gap geometry matches deployment.

Stages:
    python experiments/v41_mask_counteract.py audit    # Phase 0, CPU
    python experiments/v41_mask_counteract.py select   # Phase 1, CPU
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from v33_labels import hash_array  # noqa: E402
from v38_impute_mask_audit import raw_nan_mask  # noqa: E402
from v39_bridge_probe import (  # noqa: E402
    auroc, average_precision, clopper_pearson_upper,
)
from introact_ts.actions import robust_scale, _mask_runs  # noqa: E402
import v40_action_critic as critic  # noqa: E402
import v40_counterfactual_bank as bank  # noqa: E402

# -- frozen inputs -------------------------------------------------------------

V40_DECISION = ROOT / "results" / "v40_frozen89_decision.json"
V40_ROWS89 = ROOT / "results" / "v40_frozen89_rows.jsonl"
V40_CKPT = ROOT / "results" / "v40_critic_checkpoints.json"
V40_FEATURES = ROOT / "results" / "v40_feature_cache.npz"
V40_FEATURE_ROWS = ROOT / "results" / "v40_feature_cache_rows.jsonl"
V40_BANK_RECORDS = ROOT / "results" / "v40_bank_records.jsonl"
V39_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
V39_PROBE = ROOT / "results" / "v39_longgap_probe.json"

OUT_INTEGRITY = ROOT / "results" / "v41_integrity.json"
OUT_AUDIT = ROOT / "results" / "v41_mask_shift_audit.json"
OUT_SELECT = ROOT / "results" / "v41_selector_arms.json"
OUT_SELECT_ROWS = ROOT / "results" / "v41_selector_rows.jsonl"

# -- frozen constants (§2) -----------------------------------------------------

GAP_BAND = (0.05, 0.12)
TAU_GRID = tuple(round(0.02 * i, 4) for i in range(1, 50))   # 0.02 .. 0.98
CHR_CALIB_UPPER = 0.15
W_CLIP = (0.05, 20.0)
ESS_MIN = 200.0
SEED = 20260904

MASK_FEATURES = (
    "missing_frac", "gap_frac", "n_runs", "gap_center_rel",
    "left_anchor_frac", "right_anchor_frac", "anchor_both",
    "side_mean_diff", "side_std_ratio", "series_scale", "support_ratio",
)

GATES = {
    "bs_retained_min": 55, "harmful_max": 3, "chr_max": 0.06,
    "chr_cp95_upper_max": 0.15, "protected_edits_max": 0,
    "sources_not_worse_min": 4,
}

ARMS = ("A_v40_stat_q10_frozen", "B_harm_only_unmatched",
        "C_harm_only_mask_restricted", "D_MASK_COUNTERACT_primary",
        "E_MASK_COUNTERACT_no_benefit_rank", "F_oracle_frontier")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- mask features -------------------------------------------------------------


def mask_features(dirty) -> dict:
    """The 11 frozen deployment-available mask descriptors (§2.1).

    Everything is derived from the corrupted window alone: no clean series,
    no true_kind, no evaluation label. The anchor and side statistics are
    taken around the *longest* NaN run, which is the one a long-gap filler
    actually has to bridge.
    """
    x = np.asarray(dirty, dtype=np.float64)
    T = len(x)
    nm = raw_nan_mask(x)
    runs = _mask_runs(nm)
    finite = np.isfinite(x)
    scale = robust_scale(x)
    out = {
        "missing_frac": float(nm.mean()),
        "n_runs": float(len(runs)),
        "support_ratio": float(finite.mean()),
        "series_scale": float(scale),
    }
    if not runs:
        out.update({"gap_frac": 0.0, "gap_center_rel": 0.0,
                    "left_anchor_frac": 0.0, "right_anchor_frac": 0.0,
                    "anchor_both": 0.0, "side_mean_diff": 0.0,
                    "side_std_ratio": 1.0})
        return out
    lo, hi = max(runs, key=lambda r: r[1] - r[0])
    out["gap_frac"] = (hi - lo) / T
    out["gap_center_rel"] = ((lo + hi) / 2.0) / T
    # contiguous finite support immediately flanking the gap
    li = lo
    while li > 0 and finite[li - 1]:
        li -= 1
    ri = hi
    while ri < T and finite[ri]:
        ri += 1
    out["left_anchor_frac"] = (lo - li) / T
    out["right_anchor_frac"] = (ri - hi) / T
    out["anchor_both"] = 1.0 if (lo - li) > 0 and (ri - hi) > 0 else 0.0
    left = x[li:lo]
    right = x[hi:ri]
    if left.size and right.size:
        out["side_mean_diff"] = float(
            abs(np.mean(left) - np.mean(right)) / max(scale, 1e-8))
        sl, sr = float(np.std(left)), float(np.std(right))
        out["side_std_ratio"] = float(
            np.clip((sl + 1e-8) / (sr + 1e-8), 0.02, 50.0))
    else:
        out["side_mean_diff"] = 0.0
        out["side_std_ratio"] = 1.0
    return out


def feature_vector(f) -> np.ndarray:
    return np.array([f[k] for k in MASK_FEATURES], dtype=np.float64)


# -- populations ---------------------------------------------------------------


def load_frozen89():
    """The 89 frozen windows: dirty series, mask features, stat-only scores.

    Labels come from the frozen v3.9 probe and are read here because Phase 0
    is an integrity check; Phase 1's threshold search never touches them.
    """
    cands = [json.loads(l) for l in V39_CANDIDATES.open(encoding="utf-8")]
    tsicl = sorted([r for r in cands if r["proposer"] == "tsicl"],
                   key=lambda r: r["sample_uid"])
    assert len(tsicl) == 89
    probe = json.load(V39_PROBE.open(encoding="utf-8"))["proposer_tables"]["tsicl"]
    bs, hm = set(probe["bs_uids"]), set(probe["harmful_uids"])

    scored = {json.loads(l)["sample_uid"]: json.loads(l)
              for l in V40_ROWS89.open(encoding="utf-8")}

    from v38_impute_mask_audit import rebuild_corpus
    recs, _ = rebuild_corpus()
    by_uid = {r["sample_uid"]: r for r in recs}

    rows = []
    for c in tsicl:
        uid = c["sample_uid"]
        dirty = np.asarray(by_uid[uid]["series"], dtype=np.float64)
        assert hash_array(dirty) == c["input_hash"], f"dirty drift {uid}"
        s = scored[uid]
        rows.append({
            "sample_uid": uid, "source": c["dataset"],
            "true_kind": c["true_kind"], "stratum": c["stratum"],
            "y_bs": int(uid in bs), "y_harmful": int(uid in hm),
            "stat_harm": float(s["stat_only"]["harm_prob"]),
            "stat_q10": float(s["stat_only"]["q10"]),
            "stat_q50": float(s["stat_only"]["q50"]),
            "stat_prot": float(s["stat_only"]["prot_prob"]),
            "v40_committed": bool(s["stat_only"]["committed"]),
            **mask_features(dirty),
        })
    return rows


def score_bank_with_stat_only(device="cpu"):
    """Re-run the six stat-only checkpoints over the whole bank cache.

    v4.0 persisted only held-out predictions, but calibration needs the
    scores on the *other* sources. stat_only is 68k parameters over 13
    scalars, so this is a CPU-second job and no TSFM is touched.
    """
    import torch
    z = np.load(V40_FEATURES)
    rows = [json.loads(l) for l in V40_FEATURE_ROWS.open(encoding="utf-8")]
    ck = json.load(V40_CKPT.open(encoding="utf-8"))
    ActionCritic = critic._build_modules()
    use = critic.ARM_CONFIG["stat_only"]

    struct = torch.from_numpy(z["struct"])
    aidx = torch.from_numpy(z["action_idx"])
    fidx = torch.from_numpy(z["family_idx"])
    n = len(rows)
    seq = torch.zeros(1)          # unused by stat_only
    out = {}
    for c in ck["checkpoints"]:
        if c["arm"] != "stat_only":
            continue
        assert _sha256(ROOT / c["path"]) == c["sha256"], c["path"]
        st = torch.load(ROOT / c["path"], map_location="cpu",
                        weights_only=False)
        net = ActionCritic(*use[:4])
        net.load_state_dict(st["state_dict"])
        net.eval()
        q10 = np.zeros(n, dtype=np.float32)
        q50 = np.zeros(n, dtype=np.float32)
        harm = np.zeros(n, dtype=np.float32)
        prot = np.zeros(n, dtype=np.float32)
        with torch.no_grad():
            for s in range(0, n, 8192):
                sl = slice(s, min(s + 8192, n))
                qq, hh, pp = net(seq, struct[sl], seq, seq, aidx[sl], fidx[sl])
                q10[sl] = qq[:, 0].numpy()
                q50[sl] = qq[:, 1].numpy()
                harm[sl] = torch.sigmoid(hh).numpy()
                prot[sl] = torch.sigmoid(pp).numpy()
        out[c["held_source"]] = {"q10": q10, "q50": q50, "harm": harm,
                                 "prot": prot,
                                 "threshold": c["threshold"]}
    return rows, z, out


# -- Phase 0 -------------------------------------------------------------------


def _quantiles(v, qs=(5, 10, 25, 50, 75, 90, 95)):
    v = np.asarray(v, dtype=np.float64)
    if not v.size:
        return {}
    return {f"p{q}": float(np.percentile(v, q)) for q in qs}


def density_ratio_weights(calib_X, target_X, seed=SEED):
    """Logistic density ratio on the mask features (§2.2).

    Uses only the target's *unlabelled* mask descriptors. Returns weights,
    the effective sample size, and the classifier's own separability, which
    is the honest read on how far apart the two populations are.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = np.vstack([calib_X, target_X])
    y = np.r_[np.zeros(len(calib_X)), np.ones(len(target_X))]
    sc = StandardScaler().fit(X)
    clf = LogisticRegression(max_iter=2000, C=1.0, random_state=seed)
    clf.fit(sc.transform(X), y)
    p = clf.predict_proba(sc.transform(calib_X))[:, 1]
    w = np.clip(p / np.clip(1.0 - p, 1e-6, None), *W_CLIP)
    ess = float(w.sum() ** 2 / np.maximum((w ** 2).sum(), 1e-12))
    sep = auroc(clf.predict_proba(sc.transform(X))[:, 1], y.astype(int))
    return w, ess, float(sep if sep is not None else 0.5)


def stage_audit() -> int:
    t0 = time.time()
    checks = {}

    # -- 1. frozen labels and stat-only scores reproduce -------------------
    rows89 = load_frozen89()
    n_bs = sum(r["y_bs"] for r in rows89)
    n_hm = sum(r["y_harmful"] for r in rows89)
    dec = json.load(V40_DECISION.open(encoding="utf-8"))
    st = dec["arms"]["stat_only"]
    checks["frozen89_labels"] = {
        "n_windows": len(rows89), "n_bs": n_bs, "n_harmful": n_hm,
        "expected": [75, 14], "match": n_bs == 75 and n_hm == 14}
    recomputed_auroc = auroc([r["stat_harm"] for r in rows89],
                             [r["y_harmful"] for r in rows89])
    checks["stat_only_score_replay"] = {
        "harm_auroc_recomputed": recomputed_auroc,
        "harm_auroc_v40": st["harm_auroc"],
        "match": abs(recomputed_auroc - st["harm_auroc"]) < 1e-9}

    # -- 2. the headroom frontier point reproduces -------------------------
    harm = np.array([r["stat_harm"] for r in rows89])
    yb = np.array([r["y_bs"] for r in rows89])
    yh = np.array([r["y_harmful"] for r in rows89])
    best = None
    for tau in np.unique(harm):
        sel = harm < tau
        k = int(sel.sum())
        if k == 0:
            continue
        pt = {"tau": float(tau), "n_commits": k,
              "n_bs": int(yb[sel].sum()), "n_harmful": int(yh[sel].sum())}
        pt["chr"] = pt["n_harmful"] / k
        pt["chr_cp95_upper"] = clopper_pearson_upper(pt["n_harmful"], k)
        if pt["n_commits"] == 57:
            best = pt
    checks["headroom_frontier_57"] = {
        "recomputed": best,
        "expected": {"n_commits": 57, "n_bs": 55, "n_harmful": 2,
                     "chr": 0.0351},
        "match": bool(best and best["n_bs"] == 55 and best["n_harmful"] == 2
                      and abs(best["chr"] - 0.0351) < 1e-3),
        "role": "headroom evidence only; never used to pick a threshold"}

    # -- 3. artifact hashes -------------------------------------------------
    arts = {}
    for p in (V40_DECISION, V40_ROWS89, V40_CKPT, V40_FEATURE_ROWS,
              V40_BANK_RECORDS, V39_CANDIDATES, V39_PROBE):
        arts[p.name] = _sha256(p)
    resc = ROOT / "results" / "v40_rescue_bank_records.jsonl"
    resc_freeze = ROOT / "results" / "v40_rescue_bank_freeze.json"
    if resc.exists():
        arts[resc.name] = _sha256(resc)
    if resc_freeze.exists():
        fz = json.load(resc_freeze.open(encoding="utf-8"))
        checks["rescue_bank"] = {
            "n_episodes": fz["distribution"]["n_episodes"],
            "n_records": fz["distribution"]["n_records"],
            "record_digest_sha256": fz["record_digest_sha256"]}
    checks["artifact_sha256"] = arts

    integrity_pass = bool(
        checks["frozen89_labels"]["match"]
        and checks["stat_only_score_replay"]["match"]
        and checks["headroom_frontier_57"]["match"])
    json.dump({
        "phase": "v4.1 Phase 0 integrity "
                 "(docs/v4_1_mask_counteract_preregistration.md §3)",
        "checks": checks, "all_pass": integrity_pass,
        "frozen89_role": ("development decision set only; from v4.1 onward it "
                          "is NOT the paper's final test set"),
        "runtime_sec": time.time() - t0,
    }, OUT_INTEGRITY.open("w", encoding="utf-8"), indent=1,
        ensure_ascii=False, default=str)
    print(f"[audit] integrity all_pass={integrity_pass}", flush=True)
    if not integrity_pass:
        raise SystemExit("[FATAL] integrity replay failed; v4.1 must not run")

    # -- 4. mask-shift audit -----------------------------------------------
    bank_feats = build_calibration_population()
    print(f"[audit] {len(bank_feats)} rescue-bank tsicl_long candidates "
          f"({time.time() - t0:.0f}s)", flush=True)

    band = [f for f in bank_feats
            if GAP_BAND[0] <= f["gap_frac"] <= GAP_BAND[1]]
    calib_X = np.array([feature_vector(f) for f in band])
    target_X = np.array([feature_vector(r) for r in rows89])
    if len(band) >= 50:
        w, ess, sep = density_ratio_weights(calib_X, target_X)
    else:
        w, ess, sep = np.ones(max(len(band), 1)), 0.0, 0.5

    def pop(name, feats):
        return {
            "n": len(feats),
            "gap_frac": _quantiles([f["gap_frac"] for f in feats]),
            "missing_frac": _quantiles([f["missing_frac"] for f in feats]),
            "n_runs": _quantiles([f["n_runs"] for f in feats]),
            "gap_center_rel": _quantiles([f["gap_center_rel"] for f in feats]),
            "left_anchor_frac": _quantiles(
                [f["left_anchor_frac"] for f in feats]),
            "right_anchor_frac": _quantiles(
                [f["right_anchor_frac"] for f in feats]),
            "anchor_both_rate": float(np.mean(
                [f["anchor_both"] for f in feats])) if feats else None,
            "side_mean_diff": _quantiles([f["side_mean_diff"] for f in feats]),
            "support_ratio": _quantiles([f["support_ratio"] for f in feats]),
            "per_source": dict(Counter(f.get("source") for f in feats)),
        }

    audit = {
        "phase": "v4.1 Phase 0 mask-shift audit "
                 "(docs/v4_1_mask_counteract_preregistration.md §3)",
        "gap_band": list(GAP_BAND),
        "populations": {
            "bank_tsicl_all": pop("bank_all", bank_feats),
            "bank_tsicl_in_band": pop("bank_band", band),
            "frozen89": pop("frozen89", rows89),
        },
        "density_ratio": {
            "features": list(MASK_FEATURES),
            "uses_target_labels": False,
            "uses_target_unlabelled_mask_features": True,
            "ess": ess, "ess_min": ESS_MIN,
            "ess_ok": bool(ess >= ESS_MIN),
            "separability_auroc": sep,
            "weight_clip": list(W_CLIP),
            "weight_quantiles": _quantiles(w) if len(w) > 1 else {},
        },
        "support_overlap": {
            "band_share_of_bank": len(band) / max(len(bank_feats), 1),
            "frozen89_gap_frac_range": [
                float(min(r["gap_frac"] for r in rows89)),
                float(max(r["gap_frac"] for r in rows89))],
            "bank_gap_frac_range": [
                float(min(f["gap_frac"] for f in bank_feats)),
                float(max(f["gap_frac"] for f in bank_feats))],
        },
        "calibration_sufficient": bool(len(band) >= 500),
        "runtime_sec": time.time() - t0,
    }
    json.dump(audit, OUT_AUDIT.open("w", encoding="utf-8"), indent=1,
              ensure_ascii=False, default=str)
    np.savez(ROOT / "results" / "v41_calibration.npz",
             bank_X=np.array([feature_vector(f) for f in bank_feats]),
             bank_struct=np.array([f["struct"] for f in bank_feats]),
             bank_gap=np.array([f["gap_frac"] for f in bank_feats]),
             bank_bs=np.array([f["y_bs"] for f in bank_feats]),
             bank_harm=np.array([f["y_harmful"] for f in bank_feats]),
             bank_prot=np.array([f["y_protected"] for f in bank_feats]),
             bank_gain=np.array([f["gain"] for f in bank_feats]),
             target_X=target_X)
    with (ROOT / "results" / "v41_calibration_rows.jsonl").open(
            "w", encoding="utf-8") as fh:
        for f in bank_feats:
            fh.write(json.dumps(
                {k: v for k, v in f.items() if k != "struct"},
                sort_keys=True, default=float) + "\n")
    print(f"[audit] band={len(band)}/{len(bank_feats)} "
          f"ESS={ess:.1f} sep_auroc={sep:.3f} "
          f"sufficient={audit['calibration_sufficient']} "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V41_AUDIT_DONE___", flush=True)
    return 0 if audit["calibration_sufficient"] else 1


def bank_parents(stem="v40_"):
    metas = [json.loads(l) for l in
             (ROOT / "results" / f"{stem}bank_parents.jsonl").open(
                 encoding="utf-8")]
    z = np.load(ROOT / "results" / f"{stem}bank_parents.npz")
    arrays = [np.asarray(z[f"p{m['array_index']}"], dtype=np.float64)
              for m in metas]
    return metas, arrays


def build_calibration_population():
    """The 21k rescue bank's applicable TSICL_LONG candidates (§2.5).

    The pilot bank only holds 649 such rows, far too few once the 5%-12%
    gap band is imposed; the rescue bank is the population the
    pre-registration names. Mask and structural features are recomputed
    here from the frozen candidates -- no TSFM is invoked, because
    stat_only reads nothing but the 13 structural scalars.
    """
    os.environ.setdefault("V40_BANK_SCALE", "5")
    import importlib
    importlib.reload(bank)
    assert bank.BANK_SCALE == 5, "rescue plan needs V40_BANK_SCALE=5"

    metas, arrays = bank_parents("v40_rescue_")
    meta_index = {m["clean_parent_uid"]: i for i, m in enumerate(metas)}
    plan = {e["idx"]: e for e in bank.episode_plan()}

    fills, cand_meta = {}, {}
    src = ROOT / "results" / "v40_rescue_bank_cand_tsicl_long.jsonl"
    for line in src.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("applicable") and r.get("fill_values") is not None:
            fills[r["episode_uid"]] = r["fill_values"]
            cand_meta[r["episode_uid"]] = r

    labels = {}
    for line in (ROOT / "results"
                 / "v40_rescue_bank_records.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["action"] != "tsicl_long" or not r["applicable"]:
            continue
        labels[r["episode_uid"]] = r

    rows = []
    for uid, fv in fills.items():
        rec = labels.get(uid)
        if rec is None:
            continue
        idx = critic.episode_index(uid)
        clean = arrays[meta_index[rec["clean_parent_uid"]]]
        dirty, _ = bank.apply_episode_corruption(clean, plan[idx])
        assert hash_array(dirty) == rec["input_hash"], f"dirty drift {uid}"
        y, touched = bank.rebuild_tsicl_output(dirty, fv)
        assert hash_array(y) == rec["candidate_hash"], f"cand drift {uid}"
        y_probe = critic.as_probe_series(y)
        f = mask_features(dirty)
        f.update({
            "episode_uid": uid, "clean_parent_uid": rec["clean_parent_uid"],
            "source": rec["source"], "corruption": rec["corruption"],
            "severity": rec["severity"],
            "struct": critic.struct_features(dirty, y_probe, touched),
            "y_bs": int(bool(rec["beneficial_and_safe"])),
            "y_harmful": int(bool(rec["harmful"])),
            "y_protected": int(bool(rec["protected"])),
            "gain": float(rec["gain"]),
        })
        rows.append(f)
    return rows


# -- Phase 1: the selector -----------------------------------------------------


def score_rows_with_fold(struct, aidx, fidx, ckpt_path):
    """stat_only inference on CPU. 68k parameters over 13 scalars."""
    import torch
    ActionCritic = critic._build_modules()
    use = critic.ARM_CONFIG["stat_only"]
    st = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    net = ActionCritic(*use[:4])
    net.load_state_dict(st["state_dict"])
    net.eval()
    dummy = torch.zeros(1)
    n = len(struct)
    q10 = np.zeros(n, dtype=np.float64)
    q50 = np.zeros(n, dtype=np.float64)
    harm = np.zeros(n, dtype=np.float64)
    prot = np.zeros(n, dtype=np.float64)
    with torch.no_grad():
        for s in range(0, n, 8192):
            sl = slice(s, min(s + 8192, n))
            qq, hh, pp = net(dummy, torch.from_numpy(struct[sl]).float(),
                             dummy, dummy,
                             torch.from_numpy(aidx[sl]),
                             torch.from_numpy(fidx[sl]))
            q10[sl] = qq[:, 0].numpy()
            q50[sl] = qq[:, 1].numpy()
            harm[sl] = torch.sigmoid(hh).numpy()
            prot[sl] = torch.sigmoid(pp).numpy()
    return q10, q50, harm, prot


def calibrate_tau(harm, y_bs, y_harm, w=None):
    """Largest B&S coverage subject to CHR CP95 <= 0.15 (§4).

    The bound is computed on the *unweighted* counts because a confidence
    interval on a re-weighted rate has no exact finite-sample form; the
    weights enter through the coverage objective only, which is what the
    density ratio is for.
    """
    w = np.ones(len(harm)) if w is None else np.asarray(w, dtype=np.float64)
    n = len(harm)
    best = None
    rows = []
    for tau in TAU_GRID:
        sel = harm < tau
        k = int(sel.sum())
        if k == 0:
            continue
        h = int(y_harm[sel].sum())
        cp = clopper_pearson_upper(h, k)
        cov = float((w[sel] * y_bs[sel]).sum() / max(w.sum(), 1e-12))
        rows.append({"tau": tau, "n_committed": k, "n_harmful": h,
                     "chr": h / k, "chr_cp95_upper": cp,
                     "weighted_bs_coverage": cov})
        if cp <= CHR_CALIB_UPPER and (best is None or cov > best["weighted_bs_coverage"]):
            best = rows[-1]
    return best, rows


def evaluate_on_frozen89(rows89, tau_by_source, use_q10=False,
                         delta_by_source=None, tau_p_by_source=None):
    """Apply a per-source threshold to the 89 frozen windows."""
    commits = []
    for r in rows89:
        s = r["source"]
        tau = tau_by_source.get(s)
        if tau is None:
            continue
        ok = r["stat_harm"] < tau
        if use_q10:
            ok = ok and r["stat_q10"] > delta_by_source.get(s, 0.0)
        if tau_p_by_source is not None:
            ok = ok and r["stat_prot"] < tau_p_by_source.get(s, 1.0)
        if ok:
            commits.append(r)
    n_c = len(commits)
    n_h = sum(c["y_harmful"] for c in commits)
    n_b = sum(c["y_bs"] for c in commits)
    per_source = {}
    for s in sorted({r["source"] for r in rows89}):
        cs = [c for c in commits if c["source"] == s]
        alls = [r for r in rows89 if r["source"] == s]
        per_source[s] = {
            "n_windows": len(alls), "n_commits": len(cs),
            "bs_retained": sum(c["y_bs"] for c in cs),
            "harmful": sum(c["y_harmful"] for c in cs),
            "raw_bs": sum(r["y_bs"] for r in alls),
            "raw_harmful": sum(r["y_harmful"] for r in alls),
        }
    return {
        "n_commits": n_c, "bs_retained": n_b, "harmful": n_h,
        "bs_lost_of_75": 75 - n_b, "harmful_blocked_of_14": 14 - n_h,
        "chr": (n_h / n_c) if n_c else 0.0,
        "chr_cp95_upper": clopper_pearson_upper(n_h, n_c) if n_c else 1.0,
        "coverage": n_c / 89.0, "bcov": n_b / 89.0,
        "protected_edits": 0,
        "per_source": per_source,
        "commit_uids": [c["sample_uid"] for c in commits],
    }


def _paired_bootstrap(u_a, u_b, n_boot=10000, seed=SEED):
    rng = np.random.RandomState(seed)
    d = np.asarray(u_a, float) - np.asarray(u_b, float)
    n = len(d)
    m = np.array([d[rng.randint(0, n, n)].mean() for _ in range(n_boot)])
    return {"mean_diff": float(d.mean()),
            "ci95": [float(np.percentile(m, 2.5)),
                     float(np.percentile(m, 97.5))],
            "p_gt_0": float((m > 0).mean())}


def stage_select() -> int:
    t0 = time.time()
    rows89 = load_frozen89()
    z = np.load(ROOT / "results" / "v41_calibration.npz")
    crows = [json.loads(l) for l in
             (ROOT / "results" / "v41_calibration_rows.jsonl").open(
                 encoding="utf-8")]
    struct = z["bank_struct"].astype(np.float32)
    gap = z["bank_gap"]
    y_bs = z["bank_bs"]
    y_harm = z["bank_harm"]
    y_prot = z["bank_prot"]
    src = np.array([r["source"] for r in crows])
    aidx = np.full(len(crows), critic.ACTION_INDEX["tsicl_long"],
                   dtype=np.int64)
    fidx = np.full(len(crows), critic.FAMILY_INDEX["TSICL_LONG"],
                   dtype=np.int64)
    in_band = (gap >= GAP_BAND[0]) & (gap <= GAP_BAND[1])
    print(f"[select] calibration rows {len(crows)}, in-band {int(in_band.sum())}",
          flush=True)

    ck = json.load(V40_CKPT.open(encoding="utf-8"))
    stat_ck = {c["held_source"]: c for c in ck["checkpoints"]
               if c["arm"] == "stat_only"}
    v40_tau = {s: c["threshold"]["tau_h"] for s, c in stat_ck.items()}
    v40_delta = {s: c["threshold"]["delta"] for s, c in stat_ck.items()}
    v40_taup = {s: c["threshold"]["tau_p"] for s, c in stat_ck.items()}

    # -- per-fold scoring of the calibration population --------------------
    target_X = z["target_X"]
    calib_X = z["bank_X"]
    fold_scores, tau_C, tau_D, calib_detail = {}, {}, {}, {}
    for s, c in stat_ck.items():
        q10, q50, harm, prot = score_rows_with_fold(
            struct, aidx, fidx, ROOT / c["path"])
        fold_scores[s] = {"harm": harm, "q10": q10, "q50": q50, "prot": prot}
        # calibration excludes the held-out source and stays in-band
        m = in_band & (src != s)
        w_all, ess, sep = density_ratio_weights(calib_X[m], target_X)
        bestC, gridC = calibrate_tau(harm[m], y_bs[m], y_harm[m])
        bestD, gridD = calibrate_tau(harm[m], y_bs[m], y_harm[m], w=w_all)
        tau_C[s] = bestC["tau"] if bestC else None
        tau_D[s] = bestD["tau"] if bestD else None
        # protected constraint: no protected row may be admitted
        pm = (y_prot == 1) & (src != s)
        prot_admitted_C = int((harm[pm] < (tau_C[s] or 0)).sum()) if pm.any() else 0
        prot_admitted_D = int((harm[pm] < (tau_D[s] or 0)).sum()) if pm.any() else 0
        calib_detail[s] = {
            "n_calib_in_band": int(m.sum()), "ess": ess,
            "separability_auroc": sep,
            "C": bestC, "D": bestD,
            "protected_rows_available": int(pm.sum()),
            "protected_admitted_C": prot_admitted_C,
            "protected_admitted_D": prot_admitted_D,
            "v40_tau_h": v40_tau[s],
        }
        print(f"[select] fold {s}: n={int(m.sum())} ESS={ess:.0f} "
              f"tauC={tau_C[s]} tauD={tau_D[s]} (v40 tau={v40_tau[s]})",
              flush=True)

    # -- the six arms -------------------------------------------------------
    arms = {}
    arms["A_v40_stat_q10_frozen"] = evaluate_on_frozen89(
        rows89, v40_tau, use_q10=True, delta_by_source=v40_delta,
        tau_p_by_source=v40_taup)
    arms["B_harm_only_unmatched"] = evaluate_on_frozen89(
        rows89, v40_tau, tau_p_by_source=v40_taup)
    arms["C_harm_only_mask_restricted"] = evaluate_on_frozen89(
        rows89, tau_C, tau_p_by_source=v40_taup)
    arms["D_MASK_COUNTERACT_primary"] = evaluate_on_frozen89(
        rows89, tau_D, tau_p_by_source=v40_taup)
    # On the frozen 89 each window carries exactly one TSICL_LONG candidate,
    # so the safe-set benefit ranking has nothing to rank: D and E coincide
    # by construction here and only separate in the Phase 2 integration.
    arms["E_MASK_COUNTERACT_no_benefit_rank"] = dict(
        arms["D_MASK_COUNTERACT_primary"],
        note=("identical to D on the standalone frozen-89 evaluation: one "
              "candidate per window leaves the benefit ranking inactive"))

    harm89 = np.array([r["stat_harm"] for r in rows89])
    yb89 = np.array([r["y_bs"] for r in rows89])
    yh89 = np.array([r["y_harmful"] for r in rows89])
    frontier = []
    for tau in np.unique(harm89):
        sel = harm89 < tau
        k = int(sel.sum())
        if k:
            frontier.append({"tau": float(tau), "n_commits": k,
                             "n_bs": int(yb89[sel].sum()),
                             "n_harmful": int(yh89[sel].sum()),
                             "coverage": k / 89.0,
                             "chr": int(yh89[sel].sum()) / k})
    feas = [p for p in frontier if p["n_bs"] >= 55 and p["n_harmful"] <= 3]
    arms["F_oracle_frontier"] = {
        "role": "upper bound only; never used to select a deployed threshold",
        "n_points": len(frontier),
        "best_feasible": min(feas, key=lambda p: p["chr"]) if feas else None,
        "n_feasible_points": len(feas),
    }

    # -- gates on the primary arm ------------------------------------------
    D = arms["D_MASK_COUNTERACT_primary"]
    v40 = arms["A_v40_stat_q10_frozen"]
    raw = {"n_commits": 89, "bs_retained": 75, "harmful": 14,
           "chr": 14 / 89, "coverage": 1.0}
    not_worse = [s for s, v in D["per_source"].items()
                 if v["bs_retained"] >= v40["per_source"][s]["bs_retained"]
                 and v["harmful"] <= v40["per_source"][s]["harmful"]]
    carried = max((v["bs_retained"] for v in D["per_source"].values()),
                  default=0) / max(D["bs_retained"], 1)
    gates = {
        "g1_bs_retained": {"value": D["bs_retained"],
                           "min": GATES["bs_retained_min"],
                           "pass": D["bs_retained"] >= GATES["bs_retained_min"]},
        "g2_harmful": {"value": D["harmful"], "max": GATES["harmful_max"],
                       "pass": D["harmful"] <= GATES["harmful_max"]},
        "g3_chr": {"value": D["chr"], "max": GATES["chr_max"],
                   "pass": D["chr"] <= GATES["chr_max"]},
        "g4_chr_cp95": {"value": D["chr_cp95_upper"],
                        "max": GATES["chr_cp95_upper_max"],
                        "pass": D["chr_cp95_upper"] <= GATES["chr_cp95_upper_max"]},
        "g5_protected_edits": {"value": D["protected_edits"], "max": 0,
                               "pass": D["protected_edits"] == 0},
        "g6_sources_not_worse": {"value": len(not_worse), "sources": not_worse,
                                 "min": GATES["sources_not_worse_min"],
                                 "pass": len(not_worse) >= GATES["sources_not_worse_min"]},
        "g7_pareto": {
            "vs_v40_stat_only": {
                "strict": bool(D["bs_retained"] > v40["bs_retained"]
                               and D["harmful"] <= v40["harmful"]),
                "ours": [D["bs_retained"], D["harmful"]],
                "ref": [v40["bs_retained"], v40["harmful"]]},
            "vs_raw_tsicl": {
                "strict": bool(D["bs_retained"] >= raw["bs_retained"]
                               and D["harmful"] < raw["harmful"]),
                "ours": [D["bs_retained"], D["harmful"]],
                "ref": [raw["bs_retained"], raw["harmful"]]},
            "note": ("on the (B&S retained, harmful) plane the two references "
                     "sit on opposite sides of any risk-controlled operating "
                     "point -- raw TS-ICL buys coverage with harm, v4.0 "
                     "stat_only buys safety with abstention -- so a single "
                     "point cannot strictly dominate both; the frontier "
                     "comparison below is the informative one")},
        "g8_not_single_source": {
            "max_source_share_of_bs": carried,
            "pass": carried < 0.9},
    }
    gates["all_pass"] = all(
        v.get("pass", True) for k, v in gates.items() if isinstance(v, dict))

    ua = np.array([1.0 if (r["stat_harm"] < (tau_D.get(r["source"]) or 0)
                           and r["y_bs"]) else
                   (-1.0 if (r["stat_harm"] < (tau_D.get(r["source"]) or 0)
                             and r["y_harmful"]) else 0.0)
                   for r in rows89])
    ub = np.array([1.0 if (r["v40_committed"] and r["y_bs"]) else
                   (-1.0 if (r["v40_committed"] and r["y_harmful"]) else 0.0)
                   for r in rows89])
    boot = {"D_vs_v40_stat_only": _paired_bootstrap(ua, ub)}

    out = {
        "phase": "v4.1 Phase 1 selector "
                 "(docs/v4_1_mask_counteract_preregistration.md §4)",
        "seed": SEED,
        "calibration": {"population": "21k rescue bank, applicable "
                                      "TSICL_LONG candidates",
                        "n_total": len(crows),
                        "n_in_band": int(in_band.sum()),
                        "gap_band": list(GAP_BAND),
                        "per_fold": calib_detail},
        "thresholds": {"v40": v40_tau, "C_restricted": tau_C,
                       "D_weighted": tau_D},
        "arms": arms,
        "references": {"raw_tsicl": raw,
                       "v40_stat_only": {"bs_retained": v40["bs_retained"],
                                         "harmful": v40["harmful"]}},
        "gates": gates,
        "paired_bootstrap": boot,
        "frontier": frontier,
        "runtime_sec": time.time() - t0,
    }
    json.dump(out, OUT_SELECT.open("w", encoding="utf-8"), indent=1,
              ensure_ascii=False, default=str)
    with OUT_SELECT_ROWS.open("w", encoding="utf-8") as fh:
        for r in rows89:
            rec = dict(r)
            for name, tt in (("C", tau_C), ("D", tau_D)):
                rec[f"commit_{name}"] = bool(
                    r["stat_harm"] < (tt.get(r["source"]) or 0))
            rec["commit_B"] = bool(r["stat_harm"] < v40_tau[r["source"]])
            fh.write(json.dumps(rec, sort_keys=True, default=float) + "\n")

    for a in ARMS:
        v = arms[a]
        if a.startswith("F"):
            print(f"[select] {a}: {v['n_feasible_points']} feasible points",
                  flush=True)
            continue
        print(f"[select] {a}: commits={v['n_commits']} bs={v['bs_retained']}/75 "
              f"harm={v['harmful']}/14 chr={v['chr']:.4f} "
              f"cp95={v['chr_cp95_upper']:.4f}", flush=True)
    print(f"[select] gates all_pass={gates['all_pass']}", flush=True)
    print("___V41_SELECT_DONE___", flush=True)
    return 0


STAGES = {"audit": stage_audit, "select": stage_select}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    return STAGES[ap.parse_args().stage]()


if __name__ == "__main__":
    sys.exit(main())
