"""v4.0 COUNTERACT-TS Phase 3: full-family integration, nine-arm comparison.

Pre-registered in ``docs/v4_0_counteract_preregistration.md`` §5. Runs only
after Phase 2 passes its frozen-89 gates. All computation on the server;
API 0.

The policy under test is the one the pre-registration fixes: for every
window, take the candidate with the largest ``q10(gain)`` whose harm and
protected-edit probabilities clear the fold's calibrated thresholds, and
KEEP when none does. The critic re-scores the incumbent arm's own commits,
so this is a replacement of the decision rule, not an addition of actions on
top of it.

Metric wiring is deliberately not new: every arm is handed to the canonical
``v33_compare_arms._episode_metrics`` with a different ``committed`` map.

Stages:
    python experiments/v40_compare_arms.py pool    # rebuild + features, GPU
    python experiments/v40_compare_arms.py score   # five critic arms, GPU
    python experiments/v40_compare_arms.py arms    # nine arms + gates, CPU
"""

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from v33_labels import compute_action_labels, hash_array  # noqa: E402
from v33_compare_arms import _episode_metrics  # noqa: E402
from v38_impute_mask_audit import rebuild_corpus, raw_nan_mask  # noqa: E402
import v38_explicit_impute_probe as v38p  # noqa: E402
from v39_bridge_probe import clopper_pearson_upper  # noqa: E402
from introact_ts.actions import Action, apply_action  # noqa: E402
from introact_ts.probe import materialize_for_probe  # noqa: E402
import v40_action_critic as critic  # noqa: E402
import v40_counterfactual_bank as bank  # noqa: E402

# -- frozen inputs -------------------------------------------------------------

V33_ROWS = ROOT / "results" / "v33_training_data.jsonl"
V38_EXPLICIT = ROOT / "results" / "v38_explicit_impute_records.jsonl"
V39_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
V39_RECORDS = ROOT / "results" / "v39_phase0_records.jsonl"
V39_BUDGET = ROOT / "results" / "v39_target_budget.json"
V40_BUDGET = ROOT / "results" / "v40_target_budget.json"
CRITIC_CKPT = ROOT / "results" / "v40_critic_checkpoints.json"
DECISION = ROOT / "results" / "v40_frozen89_decision.json"

# -- outputs -------------------------------------------------------------------

OUT_POOL = ROOT / "results" / "v40_phase3_pool.jsonl"
OUT_POOL_CACHE = ROOT / "results" / "v40_phase3_pool_cache.npz"
OUT_POOL_MANIFEST = ROOT / "results" / "v40_phase3_pool_manifest.json"
OUT_SCORES = ROOT / "results" / "v40_phase3_scores.jsonl"
OUT_ARMS = ROOT / "results" / "v40_arms_compare.json"
OUT_ARM_RECORDS = ROOT / "results" / "v40_arm_records.jsonl"
OUT_ATTRIB = ROOT / "results" / "v40_phase3_attribution.json"

#: v3.3 candidate params -> the bank action token they correspond to. The
#: match is exact for IMPUTE and for the default DESPIKE/DENOISE rungs.
IMPUTE_PARAM_ACTION = {
    ("seasonal", 8): "impute_seasonal",
    ("linear", 16): "impute_linear_default",
    ("linear", 32): "impute_linear_conservative",
}
DESPIKE_DEFAULT = {"window": 11, "n_sigma": 4.0, "max_width": 3}
DENOISE_DEFAULT = {"strength": "medium"}

#: Families the critic has no action token for. RESEGMENT was retired on the
#: merits in v2 Phase B (zero beneficial-and-safe candidates on this corpus);
#: it is excluded here rather than scored under a borrowed token.
EXCLUDED_FAMILIES = ("RESEGMENT",)

ARM_NAMES = ("COUNTERACT_full", "COUNTERACT_stat_only",
             "COUNTERACT_latent_only", "COUNTERACT_without_DRO",
             "COUNTERACT_longgap_only", "PICS_joint_relabel", "v39_D",
             "raw_TSICL", "oracle")
CRITIC_ARM_OF = {
    "COUNTERACT_full": "full_COUNTERACT",
    "COUNTERACT_stat_only": "stat_only",
    "COUNTERACT_latent_only": "TSFM_latent_only",
    "COUNTERACT_without_DRO": "full_without_GroupDRO",
    "COUNTERACT_longgap_only": "full_COUNTERACT",
}

V40_GATES = {"bcov_min": 0.30, "gain_min": 0.10, "chr_max": 0.10,
             "chr_cp95_upper_max": 0.15, "pme_max": 0.0055,
             "damage_max": 0.0402, "beneficial_commits_min": 10,
             "ood_edit_max": 0.05}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- pool construction ---------------------------------------------------------


def action_token_for(row):
    """The bank action token a frozen candidate row maps onto, or None."""
    fam = row["family"]
    p = row.get("params") or {}
    if fam == "IMPUTE":
        key = (p.get("method"), int(p.get("min_run", -1)))
        return IMPUTE_PARAM_ACTION.get(key)
    if fam == "DESPIKE":
        exact = all(abs(float(p.get(k, -1)) - float(v)) < 1e-9
                    for k, v in DESPIKE_DEFAULT.items())
        # Non-default rungs still belong to the DESPIKE family; they are
        # scored under the family token and flagged, because two of them are
        # live commits in the incumbent D arm and dropping them would make
        # the re-scoring incomplete.
        return "despike" if exact else "despike:offgrid"
    if fam == "DENOISE":
        exact = p.get("strength") == DENOISE_DEFAULT["strength"]
        return "denoise" if exact else "denoise:offgrid"
    if fam == "IMPUTE_EXPLICIT":
        return "fact_short"
    if fam == "BRIDGE_LONG":
        return "tsicl_long"
    return None


def execute_candidate(dirty, row, token):
    """Re-run the frozen candidate. Returns (repaired, touched)."""
    base = token.split(":")[0]
    p = row.get("params") or {}
    if base == "fact_short":
        res = v38p.impute_explicit_linear(dirty, max_gap=int(p["max_gap"]))
        return res["series"], np.asarray(res["touched"], dtype=bool)
    if base == "tsicl_long":
        return bank.rebuild_tsicl_output(dirty, row["fill_values"])
    if base.startswith("impute"):
        out = apply_action(dirty, Action.IMPUTE, method=p["method"],
                           min_run=int(p["min_run"]))
    elif base == "despike":
        out = apply_action(dirty, Action.DESPIKE, **p)
    elif base == "denoise":
        out = apply_action(dirty, Action.DENOISE, **p)
    else:
        raise ValueError(f"unknown token {token}")
    touched = (np.asarray(out.touched, dtype=bool) if out.touched is not None
               else np.zeros(len(dirty), dtype=bool))
    return out.series, touched


def load_pool_rows():
    """Every critic-scorable candidate on the frozen frame, plus OOD."""
    rows = []
    for line in V33_ROWS.open(encoding="utf-8"):
        r = json.loads(line)
        if r["family"] in EXCLUDED_FAMILIES:
            continue
        tok = action_token_for(r)
        if tok is None:
            continue
        rows.append({
            "sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "family": r["family"], "rung": r["rung"], "params": r["params"],
            "token": tok, "source_file": "v33_training_data.jsonl",
            "corrupted_hash": r["corrupted_hash"],
            "output_hash": r.get("output_hash"),
            "true_loss": r["true_loss"],
            "true_repair_gain": r["true_repair_gain"],
            "beneficial": r["beneficial"],
            "beneficial_and_safe": r["beneficial_and_safe"],
        })
    for line in V38_EXPLICIT.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("variant") != "wide" or not r.get("n_filled"):
            continue
        lab = r["labels"]
        rows.append({
            "sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "family": "FACT_SHORT", "rung": r["rung"], "params": r["params"],
            "token": "fact_short", "source_file":
                "v38_explicit_impute_records.jsonl",
            "corrupted_hash": r["corrupted_hash"],
            "output_hash": r["output_hash"],
            "true_loss": lab["true_loss"],
            "true_repair_gain": lab["true_repair_gain"],
            "beneficial": lab["beneficial"],
            "beneficial_and_safe": lab["beneficial_and_safe"],
        })
    for line in V39_CANDIDATES.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("proposer") != "tsicl" or not r.get("applicable"):
            continue
        rows.append({
            "sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "family": "TSICL_LONG", "rung": r["rung"], "params": r["params"],
            "token": "tsicl_long", "source_file":
                "v39_longgap_candidates.jsonl",
            "corrupted_hash": r["corrupted_hash"],
            "output_hash": r["output_hash"],
            "fill_values": r["fill_values"],
            "true_loss": None, "true_repair_gain": None,
            "beneficial": None, "beneficial_and_safe": None,
        })
    return rows


def stage_pool() -> int:
    t0 = time.time()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(critic.GPU_MEMORY_FRACTION)

    rows = load_pool_rows()
    print(f"[pool] {len(rows)} candidate rows "
          f"({Counter(r['family'] for r in rows)})", flush=True)

    recs, _dropped = rebuild_corpus()
    by_uid = {r["sample_uid"]: r for r in recs}

    keep = []
    n_hash_fail, n_missing = 0, 0
    seqs, structs, dirty_mats, rep_mats = [], [], [], []
    for i, r in enumerate(rows):
        src = by_uid.get(r["sample_uid"])
        if src is None:
            n_missing += 1
            continue
        dirty = np.asarray(src["series"], dtype=np.float64)
        if hash_array(dirty) != r["corrupted_hash"]:
            n_hash_fail += 1
            continue
        try:
            y, touched = execute_candidate(dirty, r, r["token"])
        except Exception as exc:
            r["exec_error"] = f"{type(exc).__name__}: {exc}"
            n_hash_fail += 1
            continue
        if r["output_hash"] and hash_array(y) != r["output_hash"]:
            n_hash_fail += 1
            continue
        # TS-ICL rows carry no frozen labels: recompute them on the canonical
        # path now that Phase 2's decision is closed.
        if r["true_loss"] is None:
            clean = np.asarray(src["window"].clean_series, dtype=np.float64)
            lab = compute_action_labels("IMPUTE", dirty, y, clean,
                                        touched=touched, params=r["params"])
            r["true_loss"] = float(lab["true_loss"])
            r["true_repair_gain"] = float(lab["true_repair_gain"])
            r["beneficial"] = float(lab["beneficial"])
            r["beneficial_and_safe"] = float(lab["beneficial_and_safe"])
        y_probe = critic.as_probe_series(y)
        seqs.append(critic.normalize_channels(dirty, y_probe, touched))
        structs.append(critic.struct_features(dirty, y_probe, touched))
        dirty_mats.append(materialize_for_probe(dirty).astype(np.float32))
        rep_mats.append(y_probe.astype(np.float32))
        r.pop("fill_values", None)
        r["row"] = len(keep)
        keep.append(r)
        if (i + 1) % 500 == 0:
            print(f"[pool] rebuilt {i + 1}/{len(rows)} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} candidates failed hash "
                         f"re-verification")
    print(f"[pool] {len(keep)} rebuilt, {n_missing} uids absent from the "
          f"corpus ({time.time() - t0:.0f}s)", flush=True)

    seq = np.stack(seqs).astype(np.float32)
    struct = np.stack(structs).astype(np.float32)
    dm = np.stack(dirty_mats)
    rm = np.stack(rep_mats)
    _model, embed = critic._moment_encoder(device)
    B = critic.TSFM_BATCH
    eb = np.concatenate([embed(dm[s:s + B]) for s in range(0, len(dm), B)])
    ea = np.concatenate([embed(rm[s:s + B]) for s in range(0, len(rm), B)])
    del _model
    if device == "cuda":
        torch.cuda.empty_cache()

    aidx = np.array([critic.ACTION_INDEX[r["token"].split(":")[0]]
                     for r in keep], dtype=np.int64)
    fam_of = {"IMPUTE": "IMPUTE", "DESPIKE": "DESPIKE", "DENOISE": "DENOISE",
              "FACT_SHORT": "FACT_SHORT", "TSICL_LONG": "TSICL_LONG"}
    fidx = np.array([critic.FAMILY_INDEX[fam_of[r["family"]]] for r in keep],
                    dtype=np.int64)

    np.savez(OUT_POOL_CACHE, seq=seq, struct=struct, emb_before=eb,
             emb_after=ea, action_idx=aidx, family_idx=fidx)
    with OUT_POOL.open("w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    manifest = {
        "phase": "v4.0 Phase 3 candidate pool",
        "n_rows": len(keep),
        "per_family": dict(Counter(r["family"] for r in keep)),
        "per_token": dict(Counter(r["token"] for r in keep)),
        "excluded_families": list(EXCLUDED_FAMILIES),
        "offgrid_rungs_scored_under_family_token": dict(Counter(
            r["token"] for r in keep if ":offgrid" in r["token"])),
        "fact_short_semantics_note": (
            "the deployed FACT_SHORT is the v3.8 'wide' variant (max_gap 16) "
            "while the bank trained the fact_short token on 1-3 point gaps "
            "(FACT_SHORT_MAX_GAP=3); the critic still sees the real "
            "candidate's series, delta and masks, only the action token is "
            "coarser than the operator"),
        "tsicl_labels": ("recomputed on the canonical compute_action_labels "
                         "path at pool time (the frozen candidates carry no "
                         "labels); cross-checked against the frozen 75/14"),
        "array_sha256": {
            "seq": critic._sha256_array(seq),
            "struct": critic._sha256_array(struct),
            "emb_before": critic._sha256_array(eb),
            "emb_after": critic._sha256_array(ea)},
        "runtime_sec": time.time() - t0,
    }
    with OUT_POOL_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"[pool] cached {len(keep)} rows ({time.time() - t0:.0f}s)",
          flush=True)
    print("___V40_POOL_DONE___", flush=True)
    return 0


# -- scoring -------------------------------------------------------------------


def stage_score() -> int:
    t0 = time.time()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(critic.GPU_MEMORY_FRACTION)

    rows = [json.loads(l) for l in OUT_POOL.open(encoding="utf-8")]
    z = np.load(OUT_POOL_CACHE)
    ck = json.load(CRITIC_CKPT.open(encoding="utf-8"))
    drift = [c for c in ck["checkpoints"]
             if _sha256(ROOT / c["path"]) != c["sha256"]]
    if drift:
        raise SystemExit(f"[FATAL] checkpoints changed since the freeze: "
                         f"{[c['path'] for c in drift]}")
    ck_by = {(c["arm"], c["held_source"]): c for c in ck["checkpoints"]}
    ActionCritic = critic._build_modules()

    ds = np.array([r["dataset"] for r in rows])
    is_ood = np.array([d.startswith("ood:") for d in ds])
    out = {arm: {k: np.zeros(len(rows)) for k in
                 ("q10", "q50", "q90", "harm", "prot")}
           for arm in critic.ARMS}
    thresholds = defaultdict(dict)

    for arm in critic.ARMS:
        use = critic.ARM_CONFIG[arm]
        ood_acc = {k: np.zeros(int(is_ood.sum())) for k in
                   ("q10", "q50", "q90", "harm", "prot")}
        for src in critic.DEV_SOURCES:
            c_meta = ck_by[(arm, src)]
            state = torch.load(ROOT / c_meta["path"], map_location=device,
                               weights_only=False)
            net = ActionCritic(*use[:4]).to(device)
            net.load_state_dict(state["state_dict"])
            net.eval()
            mu = torch.from_numpy(state["tsfm_mu"]).to(device)
            sd = torch.from_numpy(state["tsfm_sd"]).to(device)
            thresholds[arm][src] = c_meta["threshold"]

            # in-distribution rows: only the fold that never saw this source
            own = np.flatnonzero(ds == src)
            targets = [("own", own)]
            if is_ood.any():
                targets.append(("ood", np.flatnonzero(is_ood)))
            for kind, sel in targets:
                if not len(sel):
                    continue
                preds = {k: [] for k in ("q10", "q50", "q90", "harm", "prot")}
                for s in range(0, len(sel), 1024):
                    sub = sel[s:s + 1024]
                    with torch.no_grad():
                        qq, hh, pp = net(
                            torch.from_numpy(z["seq"][sub]).to(device),
                            torch.from_numpy(z["struct"][sub]).to(device),
                            (torch.from_numpy(z["emb_before"][sub]).to(device)
                             - mu) / sd,
                            (torch.from_numpy(z["emb_after"][sub]).to(device)
                             - mu) / sd,
                            torch.from_numpy(z["action_idx"][sub]).to(device),
                            torch.from_numpy(z["family_idx"][sub]).to(device))
                    preds["q10"].append(qq[:, 0].cpu().numpy())
                    preds["q50"].append(qq[:, 1].cpu().numpy())
                    preds["q90"].append(qq[:, 2].cpu().numpy())
                    preds["harm"].append(torch.sigmoid(hh).cpu().numpy())
                    preds["prot"].append(torch.sigmoid(pp).cpu().numpy())
                cat = {k: np.concatenate(v) for k, v in preds.items()}
                if kind == "own":
                    for k in cat:
                        out[arm][k][sel] = cat[k]
                else:
                    # No fold excludes an OOD source by construction, so the
                    # six folds are averaged rather than one being privileged.
                    for k in cat:
                        ood_acc[k] += cat[k] / len(critic.DEV_SOURCES)
        if is_ood.any():
            sel = np.flatnonzero(is_ood)
            for k in ood_acc:
                out[arm][k][sel] = ood_acc[k]
        print(f"[score] {arm} done ({time.time() - t0:.0f}s)", flush=True)

    with OUT_SCORES.open("w", encoding="utf-8") as f:
        for i, r in enumerate(rows):
            rec = {"row": i, "sample_uid": r["sample_uid"],
                   "dataset": r["dataset"], "family": r["family"],
                   "token": r["token"], "rung": r["rung"],
                   "is_ood": bool(is_ood[i])}
            for arm in critic.ARMS:
                rec[arm] = {k: float(out[arm][k][i])
                            for k in ("q10", "q50", "q90", "harm", "prot")}
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    with (ROOT / "results" / "v40_phase3_thresholds.json").open(
            "w", encoding="utf-8") as f:
        json.dump({a: dict(t) for a, t in thresholds.items()}, f, indent=1,
                  ensure_ascii=False)
    print(f"[score] {len(rows)} rows x {len(critic.ARMS)} arms "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V40_SCORE_DONE___", flush=True)
    return 0


# -- nine-arm comparison -------------------------------------------------------


def _pick_from_pool(r):
    """A pool row in the shape `_episode_metrics` expects for a commit."""
    return {"sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "family": r["family"], "rung": r["rung"], "params": r["params"],
            "true_loss": float(r["true_loss"]),
            "true_repair_gain": float(r["true_repair_gain"]),
            "beneficial": float(r["beneficial"]),
            "beneficial_and_safe": float(r["beneficial_and_safe"]),
            "corrupted_hash": r["corrupted_hash"],
            "output_hash": r.get("output_hash"), "token": r["token"]}


def frozen_arm(records, arm_name):
    """Rebuild a frozen v3.9 arm's committed map from its replay records."""
    committed = {}
    for r in records:
        if r["arm"] != arm_name or not r["committed"]:
            continue
        committed[r["sample_uid"]] = ({
            "sample_uid": r["sample_uid"], "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "family": r["family"], "rung": r["rung"],
            "params": json.loads(r["params_key"]),
            "true_loss": float(r["true_loss"]),
            "true_repair_gain": float(r["true_repair_gain"]),
            "beneficial": float(r["beneficial"]),
            "beneficial_and_safe": float(r["beneficial_and_safe"]),
            "corrupted_hash": None, "output_hash": None,
            "token": f"{r['family']}|{r['rung']}",
        }, r["episode_position"], r["decision_reason"], None)
    return committed


def critic_policy(pool, scores, thresholds, critic_arm, uids):
    """The pre-registered rule: per window, the passing candidate with the
    largest q10(gain); KEEP when none passes (§5)."""
    by_uid = defaultdict(list)
    for r, s in zip(pool, scores):
        by_uid[r["sample_uid"]].append((r, s[critic_arm]))
    committed, detail = {}, {}
    for uid in uids:
        best, best_q = None, -np.inf
        n_pass = 0
        for r, sc in by_uid.get(uid, []):
            thr = thresholds[critic_arm].get(r["dataset"])
            if thr is None or thr.get("no_calibrated_point"):
                continue
            if (sc["harm"] < thr["tau_h"] and sc["q10"] > thr["delta"]
                    and sc["prot"] < thr["tau_p"]):
                n_pass += 1
                if sc["q10"] > best_q:
                    best, best_q = (r, sc), sc["q10"]
        detail[uid] = {"n_candidates": len(by_uid.get(uid, [])),
                       "n_passing": n_pass}
        if best is not None:
            r, sc = best
            committed[uid] = (_pick_from_pool(r), None,
                              f"critic:{critic_arm}",
                              {"q10": sc["q10"], "q50": sc["q50"],
                               "harm": sc["harm"], "prot": sc["prot"]})
    return committed, detail


def ood_edit_rate(pool, scores, thresholds, critic_arm):
    """Fraction of OOD windows the policy would edit (gate: <=0.05).

    OOD sources are outside every fold's training pool, so no fold is
    privileged and the thresholds of all six are required to agree that a
    candidate passes before it counts as an edit.
    """
    by_uid = defaultdict(list)
    for r, s in zip(pool, scores):
        if r["dataset"].startswith("ood:"):
            by_uid[r["sample_uid"]].append((r, s[critic_arm]))
    if not by_uid:
        return {"n_ood_windows": 0, "n_edited": 0, "rate": 0.0}
    edited = 0
    for uid, items in by_uid.items():
        for r, sc in items:
            passes = []
            for src, thr in thresholds[critic_arm].items():
                if thr.get("no_calibrated_point"):
                    passes.append(False)
                    continue
                passes.append(sc["harm"] < thr["tau_h"]
                              and sc["q10"] > thr["delta"]
                              and sc["prot"] < thr["tau_p"])
            if all(passes):
                edited += 1
                break
    return {"n_ood_windows": len(by_uid), "n_edited": edited,
            "rate": edited / len(by_uid)}


def arm_summary(met, committed):
    picks = [v[0] for v in committed.values()]
    n_h = sum(1 for p in picks if p["true_loss"] > 0.03)
    return {
        "n_committed": len(picks),
        "beneficial_commits": sum(1 for p in picks
                                  if p["beneficial_and_safe"] >= 1.0),
        "harmful_commits": n_h,
        "gain_sum": float(sum(p["true_repair_gain"] for p in picks)),
        "bcov": met["beneficial_coverage"],
        "gain": met["mean_repair_gain_contaminated"],
        "chr": met["conditional_harm_rate"],
        "chr_cp95_upper": clopper_pearson_upper(n_h, len(picks)),
        "pme": met["protected_mis_edit_rate"],
        "damage": met["damage"],
        "per_family": dict(Counter(p["family"] for p in picks)),
        "per_source_bs": dict(Counter(
            p["dataset"] for p in picks if p["beneficial_and_safe"] >= 1.0)),
        "per_source_harmful": dict(Counter(
            p["dataset"] for p in picks if p["true_loss"] > 0.03)),
    }


def paired_bootstrap_arms(uids, a_committed, b_committed, n_boot=10000,
                          seed=critic.SEED):
    """Per-window paired bootstrap on the beneficial/harmful utility."""
    def util(c):
        u = np.zeros(len(uids))
        for i, uid in enumerate(uids):
            got = c.get(uid)
            if not got:
                continue
            p = got[0]
            u[i] = (1.0 if p["beneficial_and_safe"] >= 1.0
                    else (-1.0 if p["true_loss"] > 0.03 else 0.0))
        return u

    def gain(c):
        g = np.zeros(len(uids))
        for i, uid in enumerate(uids):
            got = c.get(uid)
            if got:
                g[i] = got[0]["true_repair_gain"]
        return g

    rng = np.random.RandomState(seed)
    du = util(a_committed) - util(b_committed)
    dg = gain(a_committed) - gain(b_committed)
    n = len(uids)
    idx = [rng.randint(0, n, n) for _ in range(n_boot)]
    mu = np.array([du[i].mean() for i in idx])
    mg = np.array([dg[i].mean() for i in idx])
    return {
        "utility": {"mean_diff": float(du.mean()),
                    "ci95": [float(np.percentile(mu, 2.5)),
                             float(np.percentile(mu, 97.5))],
                    "p_gt_0": float((mu > 0).mean())},
        "gain": {"mean_diff": float(dg.mean()),
                 "ci95": [float(np.percentile(mg, 2.5)),
                          float(np.percentile(mg, 97.5))],
                 "p_gt_0": float((mg > 0).mean())},
        "n_windows": n,
    }


def stage_arms() -> int:
    t0 = time.time()
    import v39_phase0_replay as p0

    decision = json.load(DECISION.open(encoding="utf-8"))
    if not decision["primary_all_gates_pass"]:
        raise SystemExit("[FATAL] Phase 2 did not pass; Phase 3 must not run "
                         "(docs/v4_0_counteract_preregistration.md §5)")

    pool = [json.loads(l) for l in OUT_POOL.open(encoding="utf-8")]
    scores = [json.loads(l) for l in OUT_SCORES.open(encoding="utf-8")]
    assert len(pool) == len(scores)
    thresholds = json.load(
        (ROOT / "results" / "v40_phase3_thresholds.json").open(
            encoding="utf-8"))
    v39_records = [json.loads(l) for l in V39_RECORDS.open(encoding="utf-8")]

    frame_rows = [r for r in v39_records if r["arm"] == "D_fact_short_first"]
    uids = [r["sample_uid"] for r in frame_rows]
    uid_meta = {r["sample_uid"]: r for r in frame_rows}
    metric_rows = [{"sample_uid": r["sample_uid"], "dataset": r["dataset"],
                    "stratum": r["stratum"], "true_kind": r["true_kind"],
                    "family": "KEEP", "rung": "keep", "params": {}}
                   for r in frame_rows]
    print(f"[arms] frame {len(uids)} windows, pool {len(pool)} candidates",
          flush=True)

    committed_by_arm = {
        "PICS_joint_relabel": frozen_arm(v39_records, "A_pics_joint_relabel"),
        "v39_D": frozen_arm(v39_records, "D_fact_short_first"),
        "oracle": frozen_arm(v39_records, "F_unrestricted_oracle"),
    }

    # raw TS-ICL: the D arm with every applicable TS-ICL candidate committed,
    # ungated -- the reference the long-gap route has to beat.
    raw = dict(committed_by_arm["v39_D"])
    for r in pool:
        if r["family"] == "TSICL_LONG":
            raw[r["sample_uid"]] = (_pick_from_pool(r), None, "raw_tsicl",
                                    None)
    committed_by_arm["raw_TSICL"] = raw

    details = {}
    for arm, critic_arm in CRITIC_ARM_OF.items():
        if arm == "COUNTERACT_longgap_only":
            continue
        c, d = critic_policy(pool, scores, thresholds, critic_arm, uids)
        committed_by_arm[arm] = c
        details[arm] = d

    # long-gap-only: the incumbent D arm, plus critic-approved TS-ICL where D
    # itself committed nothing -- isolates the long-gap contribution.
    lg = dict(committed_by_arm["v39_D"])
    full_c, _ = critic_policy(
        [r for r in pool if r["family"] == "TSICL_LONG"],
        [s for r, s in zip(pool, scores) if r["family"] == "TSICL_LONG"],
        thresholds, "full_COUNTERACT", uids)
    n_added = 0
    for uid, got in full_c.items():
        if uid not in lg:
            lg[uid] = got
            n_added += 1
    committed_by_arm["COUNTERACT_longgap_only"] = lg

    results = {}
    for arm in ARM_NAMES:
        c = committed_by_arm[arm]
        met = _episode_metrics(metric_rows, c)
        s = arm_summary(met, c)
        if arm in CRITIC_ARM_OF:
            s["ood_edit"] = ood_edit_rate(pool, scores, thresholds,
                                          CRITIC_ARM_OF[arm])
        results[arm] = s
        print(f"[arms] {arm}: commits={s['n_committed']} "
              f"bs={s['beneficial_commits']} harm={s['harmful_commits']} "
              f"bcov={s['bcov']:.4f} gain={s['gain']:.4f} "
              f"chr={s['chr']:.4f} pme={s['pme']:.4f} "
              f"damage={s['damage']:.4f}", flush=True)

    inc = results["PICS_joint_relabel"]
    primary = results["COUNTERACT_full"]
    boot = {
        "full_vs_incumbent": paired_bootstrap_arms(
            uids, committed_by_arm["COUNTERACT_full"],
            committed_by_arm["PICS_joint_relabel"]),
        "full_vs_v39_D": paired_bootstrap_arms(
            uids, committed_by_arm["COUNTERACT_full"],
            committed_by_arm["v39_D"]),
        "full_vs_raw_tsicl": paired_bootstrap_arms(
            uids, committed_by_arm["COUNTERACT_full"],
            committed_by_arm["raw_TSICL"]),
        "full_vs_stat_only": paired_bootstrap_arms(
            uids, committed_by_arm["COUNTERACT_full"],
            committed_by_arm["COUNTERACT_stat_only"]),
        "dro_vs_erm": paired_bootstrap_arms(
            uids, committed_by_arm["COUNTERACT_full"],
            committed_by_arm["COUNTERACT_without_DRO"]),
    }

    budget = json.load(V40_BUDGET.open(encoding="utf-8"))["v40_targets"]
    d_arm = results["v39_D"]
    budget_check = {
        "new_bs_windows": primary["beneficial_commits"]
                          - d_arm["beneficial_commits"],
        "new_bs_windows_required": budget[
            "new_beneficial_and_safe_windows_min"],
        "gain_sum_increase": primary["gain_sum"] - d_arm["gain_sum"],
        "gain_sum_increase_required": budget["gain_sum_increase_min"],
        "harmful_vs_D": primary["harmful_commits"] - d_arm["harmful_commits"],
        "harmful_must_decrease_below": budget[
            "harmful_commits_must_decrease_below"],
    }
    budget_check["pass"] = bool(
        budget_check["new_bs_windows"] >= budget[
            "new_beneficial_and_safe_windows_min"]
        and budget_check["gain_sum_increase"] >= budget[
            "gain_sum_increase_min"]
        and primary["harmful_commits"] < budget[
            "harmful_commits_must_decrease_below"])

    pre_gates = {
        "bcov_or_gain_significant_vs_incumbent": bool(
            boot["full_vs_incumbent"]["utility"]["p_gt_0"] > 0.975
            or boot["full_vs_incumbent"]["gain"]["p_gt_0"] > 0.975),
        "chr_decreases": primary["chr"] < inc["chr"],
        "pme_not_worse": primary["pme"] <= inc["pme"],
        "damage_not_worse": primary["damage"] <= inc["damage"],
        "ood_edit_ok": primary.get("ood_edit", {}).get("rate", 1.0) <= 0.05,
    }
    pre_gates["all_pass"] = all(pre_gates.values())

    formal = {
        "bcov": {"value": primary["bcov"], "min": V40_GATES["bcov_min"],
                 "pass": primary["bcov"] >= V40_GATES["bcov_min"]},
        "gain": {"value": primary["gain"], "min": V40_GATES["gain_min"],
                 "pass": primary["gain"] >= V40_GATES["gain_min"]},
        "chr": {"value": primary["chr"], "max": V40_GATES["chr_max"],
                "pass": primary["chr"] <= V40_GATES["chr_max"]},
        "chr_cp95_upper": {"value": primary["chr_cp95_upper"],
                           "max": V40_GATES["chr_cp95_upper_max"],
                           "pass": primary["chr_cp95_upper"]
                                   <= V40_GATES["chr_cp95_upper_max"]},
        "pme": {"value": primary["pme"], "max": V40_GATES["pme_max"],
                "pass": primary["pme"] <= V40_GATES["pme_max"]},
        "damage": {"value": primary["damage"], "max": V40_GATES["damage_max"],
                   "pass": primary["damage"] <= V40_GATES["damage_max"]},
        "beneficial_commits": {
            "value": primary["beneficial_commits"],
            "min": V40_GATES["beneficial_commits_min"],
            "pass": primary["beneficial_commits"]
                    >= V40_GATES["beneficial_commits_min"]},
        "ood_edit": {"value": primary.get("ood_edit", {}).get("rate"),
                     "max": V40_GATES["ood_edit_max"],
                     "pass": primary.get("ood_edit", {}).get("rate", 1.0)
                             <= V40_GATES["ood_edit_max"]},
    }
    formal["all_pass"] = all(v["pass"] for k, v in formal.items()
                             if isinstance(v, dict))

    out = {
        "phase": "v4.0 Phase 3 nine-arm comparison "
                 "(docs/v4_0_counteract_preregistration.md §5)",
        "seed": critic.SEED,
        "n_frame_windows": len(uids),
        "n_pool_candidates": len(pool),
        "arms": results,
        "incumbent": "PICS_joint_relabel",
        "primary_arm": "COUNTERACT_full",
        "target_budget_check": budget_check,
        "v40_pre_gates": pre_gates,
        "v40_formal_gates": formal,
        "paired_bootstrap": boot,
        "longgap_only_added_windows": n_added,
        "policy_detail_sample": {a: dict(list(d.items())[:3])
                                 for a, d in details.items()},
        "runtime_sec": time.time() - t0,
    }
    with OUT_ARMS.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    with OUT_ARM_RECORDS.open("w", encoding="utf-8") as f:
        for arm in ARM_NAMES:
            for uid, got in sorted(committed_by_arm[arm].items()):
                p = got[0]
                f.write(json.dumps({
                    "arm": arm, "sample_uid": uid, "dataset": p["dataset"],
                    "stratum": p["stratum"], "true_kind": p["true_kind"],
                    "family": p["family"], "rung": p["rung"],
                    "token": p.get("token"),
                    "true_loss": p["true_loss"],
                    "true_repair_gain": p["true_repair_gain"],
                    "beneficial_and_safe": p["beneficial_and_safe"],
                    "harmful": bool(p["true_loss"] > 0.03),
                    "critic": got[3],
                }, sort_keys=True) + "\n")

    print(f"[arms] pre_gates={pre_gates['all_pass']} "
          f"formal={formal['all_pass']} budget={budget_check['pass']} "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V40_ARMS_DONE___", flush=True)
    return 0


def stage_attribute() -> int:
    """Full ledger for every harmful commit, rejected beneficial candidate
    and protected edit, plus the concentration checks §6 requires."""
    t0 = time.time()
    pool = [json.loads(l) for l in OUT_POOL.open(encoding="utf-8")]
    scores = [json.loads(l) for l in OUT_SCORES.open(encoding="utf-8")]
    arms = json.load(OUT_ARMS.open(encoding="utf-8"))
    recs = [json.loads(l) for l in OUT_ARM_RECORDS.open(encoding="utf-8")]
    thresholds = json.load(
        (ROOT / "results" / "v40_phase3_thresholds.json").open(
            encoding="utf-8"))
    score_by_row = {i: s for i, s in enumerate(scores)}
    pool_by_uid = defaultdict(list)
    for i, r in enumerate(pool):
        pool_by_uid[r["sample_uid"]].append((i, r))

    primary = "COUNTERACT_full"
    carm = CRITIC_ARM_OF[primary]
    committed = {r["sample_uid"]: r for r in recs if r["arm"] == primary}
    inc = {r["sample_uid"]: r for r in recs if r["arm"] == "PICS_joint_relabel"}

    harmful, rejected_bs, protected_edits = [], [], []
    for uid, r in committed.items():
        if r["harmful"]:
            harmful.append({
                "sample_uid": uid, "dataset": r["dataset"],
                "stratum": r["stratum"], "true_kind": r["true_kind"],
                "family": r["family"], "token": r["token"], "rung": r["rung"],
                "critic": r["critic"], "true_loss": r["true_loss"],
                "gain": r["true_repair_gain"],
                "threshold": thresholds[carm].get(r["dataset"]),
                "code_path": ("v40_action_critic.ActionCritic.head_harm -> "
                              "sigmoid -> v40_compare_arms.critic_policy "
                              "gate `sc['harm'] < thr['tau_h']`"),
            })
        if r["stratum"] in ("protected", "clean", "protected_clean"):
            protected_edits.append({"sample_uid": uid, **r})

    for uid, items in pool_by_uid.items():
        got = committed.get(uid)
        for i, r in items:
            if r["beneficial_and_safe"] < 1.0:
                continue
            if got is not None and got["true_repair_gain"] >= \
                    float(r["true_repair_gain"]):
                continue
            sc = score_by_row[i][carm]
            thr = thresholds[carm].get(r["dataset"], {})
            why = []
            if thr.get("no_calibrated_point"):
                why.append("fold has no calibrated point")
            else:
                if not sc["harm"] < thr["tau_h"]:
                    why.append(f"harm {sc['harm']:.3f} >= tau_h {thr['tau_h']}")
                if not sc["q10"] > thr["delta"]:
                    why.append(f"q10 {sc['q10']:.4f} <= delta {thr['delta']}")
                if not sc["prot"] < thr["tau_p"]:
                    why.append(f"prot {sc['prot']:.3f} >= tau_p {thr['tau_p']}")
            if not why:
                why.append("passed the gate but lost the q10 argmax")
            rejected_bs.append({
                "sample_uid": uid, "dataset": r["dataset"],
                "stratum": r["stratum"], "true_kind": r["true_kind"],
                "family": r["family"], "token": r["token"], "rung": r["rung"],
                "critic": sc, "threshold": thr,
                "true_repair_gain": r["true_repair_gain"],
                "true_loss": r["true_loss"],
                "reason": "; ".join(why),
                "code_path": ("v40_compare_arms.critic_policy -> per-window "
                              "q10 argmax over gate-passing candidates"),
            })

    # -- is the improvement carried by one source, family or a few uids? ----
    d_recs = {r["sample_uid"]: r for r in recs if r["arm"] == "v39_D"}
    gain_delta = []
    for uid in set(committed) | set(d_recs):
        a = committed.get(uid, {}).get("true_repair_gain", 0.0)
        b = d_recs.get(uid, {}).get("true_repair_gain", 0.0)
        if abs(a - b) > 1e-12:
            gain_delta.append({
                "sample_uid": uid,
                "dataset": (committed.get(uid) or d_recs[uid])["dataset"],
                "family_new": committed.get(uid, {}).get("family"),
                "family_old": d_recs.get(uid, {}).get("family"),
                "delta_gain": a - b})
    gain_delta.sort(key=lambda r: -abs(r["delta_gain"]))
    total = sum(r["delta_gain"] for r in gain_delta) or 1e-12
    by_source = defaultdict(float)
    by_family = defaultdict(float)
    for r in gain_delta:
        by_source[r["dataset"]] += r["delta_gain"]
        by_family[r["family_new"] or "KEEP"] += r["delta_gain"]
    top5 = sum(r["delta_gain"] for r in gain_delta[:5])

    concentration = {
        "total_gain_delta_vs_v39_D": total,
        "share_by_source": {k: v / total for k, v in sorted(by_source.items())},
        "share_by_family": {k: v / total for k, v in sorted(by_family.items())},
        "top5_uid_share": top5 / total,
        "n_windows_changed": len(gain_delta),
        "single_source_carries_all": max(
            (v / total for v in by_source.values()), default=0.0) > 0.9,
    }

    out = {
        "phase": "v4.0 Phase 3 attribution ledger "
                 "(docs/v4_0_counteract_preregistration.md §6)",
        "primary_arm": primary,
        "n_harmful_commits": len(harmful),
        "harmful_commits": harmful,
        "n_rejected_beneficial": len(rejected_bs),
        "rejected_beneficial": rejected_bs[:500],
        "rejected_beneficial_truncated": len(rejected_bs) > 500,
        "rejected_reason_counts": dict(Counter(
            r["reason"].split(";")[0] for r in rejected_bs)),
        "n_protected_edits": len(protected_edits),
        "protected_edits": protected_edits,
        "improvement_concentration": concentration,
        "top_gain_windows": gain_delta[:20],
        "runtime_sec": time.time() - t0,
    }
    with OUT_ATTRIB.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    print(f"[attribute] harmful={len(harmful)} rejected_bs={len(rejected_bs)} "
          f"protected_edits={len(protected_edits)} "
          f"top5_share={concentration['top5_uid_share']:.3f}", flush=True)
    print("___V40_ATTRIBUTE_DONE___", flush=True)
    return 0


STAGES = {"pool": stage_pool, "score": stage_score, "arms": stage_arms,
          "attribute": stage_attribute}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    args = ap.parse_args()
    return STAGES[args.stage]()


if __name__ == "__main__":
    sys.exit(main())
