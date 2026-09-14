"""v4.0 COUNTERACT-TS Phase 2: the Action-Delta Critic.

Frozen in ``docs/v4_0_counteract_preregistration.md`` §11.3 (F1-F12) before
any Phase 2 computation. Everything here runs on the server; API calls 0.

What the critic is for: given a *candidate* repair that an operator already
produced, decide whether committing it helps the downstream TSFM without
damaging the window -- and abstain (KEEP) when the evidence is thin. It never
sees the clean target, the true kind, the source name or any evaluation
label; those exist in this file only as supervision targets and as grouping
/ reporting keys.

Stages:
    python experiments/v40_action_critic.py audit          # Phase 2.0, CPU
    python experiments/v40_action_critic.py features       # Phase 2.1, GPU
    python experiments/v40_action_critic.py verify-cache   # 2nd process
    python experiments/v40_action_critic.py train          # Phase 2.3, GPU
    python experiments/v40_action_critic.py decide         # Phase 2.4, GPU
"""

import argparse
import hashlib
import json
import math
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
from introact_ts.probe import materialize_for_probe  # noqa: E402
import v40_counterfactual_bank as bank  # noqa: E402

# -- frozen inputs -------------------------------------------------------------

#: The one pre-registered rescue (§11.3 F11) reads the 21k-episode bank and
#: writes beside the pilot's outputs, so nothing from Phase 2 is overwritten.
#: Must be run with V40_BANK_SCALE set to the same factor the bank used, so
#: `bank.episode_plan()` reproduces the rescue plan.
RESCUE = os.environ.get("V40_RESCUE", "0") == "1"
_IN = "v40_rescue_" if RESCUE else "v40_"
_OUT = "v40_rescue_" if RESCUE else "v40_"

BANK_RECORDS = ROOT / "results" / f"{_IN}bank_records.jsonl"
BANK_FREEZE = ROOT / "results" / f"{_IN}bank_freeze.json"
TSICL_CANDIDATES = ROOT / "results" / f"{_IN}bank_cand_tsicl_long.jsonl"
PARENTS_META = ROOT / "results" / f"{_IN}bank_parents.jsonl"
PARENTS_NPZ = ROOT / "results" / f"{_IN}bank_parents.npz"

# frozen-89 evaluation frame (opened only by `decide`, after the training
# freeze, per §11.3 F10)
V39_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
V39_PROBE = ROOT / "results" / "v39_longgap_probe.json"

# -- outputs -------------------------------------------------------------------

OUT_LABEL_AUDIT = ROOT / "results" / f"{_OUT}label_audit.json"
OUT_GROUP_SUPPORT = ROOT / "results" / f"{_OUT}group_support.json"
OUT_FEATURE_CACHE = ROOT / "results" / f"{_OUT}feature_cache.npz"
OUT_FEATURE_ROWS = ROOT / "results" / f"{_OUT}feature_cache_rows.jsonl"
OUT_FEATURE_MANIFEST = ROOT / "results" / f"{_OUT}feature_manifest.json"
OUT_CRITIC_LODO = ROOT / "results" / f"{_OUT}critic_lodo.json"
OUT_CRITIC_PRED = ROOT / "results" / f"{_OUT}critic_predictions.jsonl"
OUT_CRITIC_CKPT = ROOT / "results" / f"{_OUT}critic_checkpoints.json"
OUT_CRITIC_ABLATION = ROOT / "results" / f"{_OUT}critic_ablation.json"
OUT_CRITIC_DIAG = ROOT / "results" / f"{_OUT}critic_training_diagnostics.json"
OUT_DECISION = ROOT / "results" / f"{_OUT}frozen89_decision.json"
OUT_DECISION_ROWS = ROOT / "results" / f"{_OUT}frozen89_rows.jsonl"
CKPT_DIR = ROOT / "results" / f"{_OUT}critic_ckpt"

# -- frozen constants (§11.3) --------------------------------------------------

SEED = 20260904
WINDOW_LEN = 512
TSFM_MODEL = "AutonLab/MOMENT-1-large"
TSFM_REVISION = "ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc"
TSFM_DIM = 1024
TSFM_BATCH = 64

QUANTILES = (0.1, 0.5, 0.9)
LAMBDA_H = 1.0
LAMBDA_P = 0.5
LAMBDA_R = 0.3
POS_WEIGHT_CAP = 20.0

WARMUP_EPOCHS = 5
MAX_EPOCHS = 60
PATIENCE = 10
BATCH_EPISODES = 64
LR = 3e-4
WEIGHT_DECAY = 1e-2
DRO_ETA = 0.01
DRO_WEIGHT_CAP_MULT = 10.0
DRO_MIN_GROUP_EPISODES = 20

#: Fraction of the card this project may hold. The node is shared: a
#: co-tenant job appeared on the GPU mid-run, and the discipline is to make
#: room rather than to take the card. ~11 GB of 32 GB is far above the ~5 GB
#: these runs actually peak at.
GPU_MEMORY_FRACTION = 0.35

INNER_TRAIN_FRAC_BYTE = 217  # sha256 first byte < 217 -> inner-train (~85%)

TAU_H_GRID = tuple(round(0.02 * i, 4) for i in range(1, 31))       # 0.02..0.60
DELTA_GRID = (0.0, 1e-4, 1e-3, 5e-3, 1e-2)
TAU_P_GRID = (0.2, 0.35, 0.5, 1.0)
CHR_CALIB_UPPER = 0.15

ACTIONS = bank.ACTIONS
ACTION_INDEX = {a: i for i, a in enumerate(ACTIONS)}
FAMILIES = ("KEEP", "FACT_SHORT", "TSICL_LONG", "IMPUTE", "DESPIKE", "DENOISE")
FAMILY_INDEX = {f: i for i, f in enumerate(FAMILIES)}
DEV_SOURCES = bank.DEV_SOURCES

#: Deployment-available structural scalars. Deliberately excludes the v3.9
#: signal family (posterior width, model disagreement, seam, bridge
#: deviation) which §1 forbids re-litigating -- the delta encoder sees the
#: whole delta sequence and learns its own representation instead.
STRUCT_FEATURES = (
    "raw_nan_frac", "longest_nan_run_frac", "n_nan_runs_frac",
    "touched_frac", "n_filled_frac", "support_ratio",
    "scale_over_std", "iqr_over_std",
    "delta_l1_over_scale", "delta_linf_over_scale", "delta_nonzero_frac",
    "gap_touches_edge", "mean_nan_run_frac",
)
N_STRUCT = len(STRUCT_FEATURES)

#: Structural guard for §11.3 F3: nothing on this list may become a model
#: input. Asserted by tests and by the feature stage itself.
FORBIDDEN_INPUT_KEYS = frozenset({
    "source", "source_id", "source_idx_input", "dataset", "true_kind",
    "clean", "clean_series", "clean_hash", "sample_uid", "clean_parent_uid",
    "gain", "true_loss", "harmful", "beneficial_and_safe", "protected",
    "labels", "before_nmse", "after_nmse",
})

ALL_ARMS = ("stat_only", "TSFM_latent_only", "delta_only", "full_COUNTERACT",
            "full_without_GroupDRO")
#: The rescue retrains once, and at 5x the bank a full five-arm sweep would
#: cost ~1.5 h of GPU for arms whose Phase 2 ordering is already known. The
#: gate only reads the primary arm, so V40_ARMS narrows the sweep; the
#: default keeps the full pre-registered set.
ARMS = tuple(a for a in os.environ.get("V40_ARMS", ",".join(ALL_ARMS)
                                       ).split(",") if a)
#: (use_seq, use_tsfm, use_delta, use_struct, use_dro)
ARM_CONFIG = {
    "stat_only":            (False, False, False, True,  True),
    "TSFM_latent_only":     (False, True,  False, False, True),
    "delta_only":           (False, False, True,  False, True),
    "full_COUNTERACT":      (True,  True,  True,  True,  True),
    "full_without_GroupDRO": (True, True,  True,  True,  False),
}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_array(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


# -- data loading --------------------------------------------------------------


def load_bank():
    """Bank records, parent arrays and the tsicl fill values, all frozen."""
    recs = [json.loads(l) for l in BANK_RECORDS.open(encoding="utf-8")]
    metas = [json.loads(l) for l in PARENTS_META.open(encoding="utf-8")]
    z = np.load(PARENTS_NPZ)
    arrays = [np.asarray(z[f"p{m['array_index']}"], dtype=np.float64)
              for m in metas]
    fills = {}
    for line in TSICL_CANDIDATES.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("fill_values") is not None:
            fills[r["episode_uid"]] = r["fill_values"]
    return recs, metas, arrays, fills


def episode_index(uid: str) -> int:
    """`v40ep-00042:spike:mid` -> 42."""
    return int(uid.split(":")[0].split("-")[1])


def inner_split(parent_uid: str) -> str:
    """85/15 inner train/validation split by parent uid (§11.3 F8).

    A distinct hash namespace from ``bank.parent_split`` so the inner split
    is not correlated with the Phase 1 reporting split.
    """
    b = hashlib.sha256(("inner:" + parent_uid).encode()).digest()[0]
    return "inner_train" if b < INNER_TRAIN_FRAC_BYTE else "inner_val"


# -- series reconstruction -----------------------------------------------------


def rebuild_episode(entry, clean):
    """The frozen dirty window for one episode (bit-identical to Phase 1)."""
    dirty, mask = bank.apply_episode_corruption(clean, entry)
    return dirty, mask


def rebuild_repaired(dirty, rec, fills):
    """The frozen candidate output for one applicable record.

    Returns (repaired, touched). Verified against the frozen candidate_hash
    by the caller -- features are only ever built on candidates that
    reproduce.
    """
    if rec["action"] == "tsicl_long":
        return bank.rebuild_tsicl_output(dirty, fills[rec["episode_uid"]])
    y, touched, applicable, _p = bank.run_cpu_action(dirty, rec["action"])
    if not applicable:
        raise RuntimeError(f"{rec['episode_uid']}:{rec['action']} no longer "
                           f"applies at feature time")
    return y, touched


# -- deployment-available features ---------------------------------------------


def as_probe_series(y) -> np.ndarray:
    """The candidate as the downstream probe actually queries it.

    KEEP returns the dirty window untouched and DESPIKE only rewrites spikes,
    so on a window with real gaps both candidates still carry NaN. The frozen
    label path resolves exactly this by materialising the KEEP counterfactual
    (`compute_action_labels` -> `materialize_for_probe`), and the deployed
    probe never sees a NaN either. Materialising here keeps the critic's view
    identical to the probe's; on an already-finite candidate it is a no-op.
    """
    y = np.asarray(y, dtype=np.float64)
    return y if np.isfinite(y).all() else materialize_for_probe(y)


def struct_features(dirty, repaired, touched) -> np.ndarray:
    """The 13 frozen structural scalars (§11.3 F2).

    Everything here is computable at deployment time from the dirty window,
    the candidate output and the operator's own touched declaration.
    """
    x = np.asarray(dirty, dtype=np.float64)
    y = as_probe_series(repaired)
    T = len(x)
    nm = raw_nan_mask(x)
    runs = _mask_runs(nm)
    run_lens = [hi - lo for lo, hi in runs]
    finite = np.isfinite(x)
    xf = x[finite]
    scale = robust_scale(x)
    std = float(np.std(xf)) if xf.size else 0.0
    iqr = 0.0
    if xf.size >= 4:
        q75, q25 = np.percentile(xf, [75, 25])
        iqr = float(q75 - q25)
    xm = materialize_for_probe(x)
    delta = y - xm if len(y) == T else np.zeros(T)
    touch = np.asarray(touched, dtype=bool)

    edge = bool(runs and (runs[0][0] == 0 or runs[-1][1] == T))
    return np.array([
        nm.mean(),
        (max(run_lens) / T) if run_lens else 0.0,
        len(runs) / T,
        touch.mean() if touch.size == T else 0.0,
        float(rec_n_filled(touch)) / T,
        finite.mean(),
        scale / max(std, 1e-8),
        iqr / max(std, 1e-8),
        float(np.mean(np.abs(delta))) / max(scale, 1e-8),
        float(np.max(np.abs(delta))) / max(scale, 1e-8) if T else 0.0,
        float(np.mean(np.abs(delta) > 1e-12)),
        1.0 if edge else 0.0,
        (float(np.mean(run_lens)) / T) if run_lens else 0.0,
    ], dtype=np.float64)


def rec_n_filled(touched) -> int:
    t = np.asarray(touched, dtype=bool)
    return int(t.sum())


def normalize_channels(dirty, repaired, touched):
    """Window-local robust normalisation (§11.3 F2).

    The (median, scale) pair comes from the *dirty* window's finite points
    only and is shared by all three numeric channels, so the repair delta
    stays on the same scale as the series it modifies. Nothing crosses
    windows, sources or folds, which is what makes held-out leakage
    structurally impossible rather than merely audited.
    """
    x = np.asarray(dirty, dtype=np.float64)
    y = as_probe_series(repaired)
    T = len(x)
    finite = np.isfinite(x)
    xf = x[finite]
    med = float(np.median(xf)) if xf.size else 0.0
    if xf.size >= 4:
        q75, q25 = np.percentile(xf, [75, 25])
        scale = max(float(q75 - q25) / 1.349, 1e-8)
    else:
        scale = max(float(np.std(xf)) if xf.size else 1.0, 1e-8)

    xm = materialize_for_probe(x)
    dirty_n = (xm - med) / scale
    rep_n = (y - med) / scale
    delta_n = (y - xm) / scale
    raw_mask = raw_nan_mask(x).astype(np.float64)
    touch = np.asarray(touched, dtype=bool).astype(np.float64)
    if touch.size != T:
        touch = np.zeros(T, dtype=np.float64)
    return np.stack([dirty_n, rep_n, delta_n, raw_mask, touch]).astype(
        np.float32)


# -- Phase 2.0: label and group audit ------------------------------------------


def _cell(rows):
    app = [r for r in rows if r["applicable"]]
    n_app = len(app)
    bs = sum(1 for r in app if r["beneficial_and_safe"])
    harm = sum(1 for r in app if r["harmful"])
    return {
        "n_rows": len(rows), "n_applicable": n_app,
        "n_inapplicable": len(rows) - n_app,
        "n_bs": bs, "n_harmful": harm,
        "n_neutral": n_app - bs - harm,
        "bs_rate": (bs / n_app) if n_app else None,
        "harmful_rate": (harm / n_app) if n_app else None,
        "n_protected_rows": sum(1 for r in rows if r["protected"]),
    }


def stage_audit() -> int:
    t0 = time.time()
    recs, metas, _arrays, _fills = load_bank()
    freeze = json.load(BANK_FREEZE.open(encoding="utf-8"))
    meta_by_uid = {m["clean_parent_uid"]: m for m in metas}

    # -- hard check 1: the eight actions share one episode set, no dropped rows
    by_ep = defaultdict(set)
    for r in recs:
        by_ep[r["episode_uid"]].add(r["action"])
    incomplete = {e: sorted(a) for e, a in by_ep.items()
                  if sorted(a) != sorted(ACTIONS)}
    check_action_set = {
        "n_episodes": len(by_ep),
        "n_rows": len(recs),
        "expected_rows": len(by_ep) * len(ACTIONS),
        "rows_match": len(recs) == len(by_ep) * len(ACTIONS),
        "n_episodes_missing_actions": len(incomplete),
        "examples": dict(list(incomplete.items())[:3]),
        "inapplicable_are_explicit": all(
            ("applicable" in r) and (r["applicable"] or not r["supported"]
                                     or r["candidate_hash"] is None)
            for r in recs),
        "pass": len(recs) == len(by_ep) * len(ACTIONS) and not incomplete,
    }

    # -- hard check 2/3: parent-grouped splits, eight actions never cross
    ep_parent = {}
    for r in recs:
        ep_parent.setdefault(r["episode_uid"], set()).add(r["clean_parent_uid"])
    multi_parent = {e: sorted(p) for e, p in ep_parent.items() if len(p) > 1}
    parent_splits = defaultdict(set)
    for r in recs:
        parent_splits[r["clean_parent_uid"]].add(r["split"])
    split_crossing = {p: sorted(s) for p, s in parent_splits.items()
                      if len(s) > 1}
    ep_splits = defaultdict(set)
    for r in recs:
        ep_splits[r["episode_uid"]].add(r["split"])
    ep_crossing = {e: sorted(s) for e, s in ep_splits.items() if len(s) > 1}
    check_grouping = {
        "episodes_with_multiple_parents": len(multi_parent),
        "parents_crossing_phase1_split": len(split_crossing),
        "episodes_whose_actions_cross_split": len(ep_crossing),
        "inner_split_is_parent_keyed": True,
        "pass": not multi_parent and not split_crossing and not ep_crossing,
    }

    # -- hard check 4: the primary evaluation is six-fold LODO, not 80/10/10
    lodo = {}
    for src in DEV_SOURCES:
        held = [m for m in metas if m["source"] == src]
        rest = [m for m in metas if m["source"] != src]
        inner = Counter(inner_split(m["clean_parent_uid"]) for m in rest)
        lodo[src] = {
            "held_out_parents": len(held),
            "train_pool_parents": len(rest),
            "inner_train_parents": inner["inner_train"],
            "inner_val_parents": inner["inner_val"],
            "inner_val_frac": inner["inner_val"] / max(len(rest), 1),
            "held_out_rows": sum(1 for r in recs if r["source"] == src),
        }
    check_lodo = {
        "n_folds": len(DEV_SOURCES),
        "per_fold": lodo,
        "primary_evaluation": "six-fold leave-one-source-out",
        "phase1_random_split_role": ("bank-internal reporting only; not used "
                                     "for any Phase 2 decision"),
        "pass": all(v["held_out_parents"] > 0 and v["inner_val_parents"] > 0
                    for v in lodo.values()),
    }

    # -- hard check 5: the frozen 89 stay closed until the training freeze
    check_frozen89 = {
        "frozen_89_labels_opened": False,
        "opened_by_stage": "decide (Phase 2.4) only",
        "precondition": ("six fold checkpoints, thresholds, configs and "
                         "manifests written and sha256-registered first"),
        "bank_parent_uids_intersect_frozen_frame":
            json.load((ROOT / "results" / "v40_bank_isolation.json").open(
                encoding="utf-8"))["intersect_eval_771_uids"],
        "pass": True,
    }

    # -- hard check 6: protected positives support
    prot_rows = [r for r in recs if r["protected"]]
    prot_app = [r for r in prot_rows if r["applicable"]]
    prot_edit = [r for r in prot_app if r["action"] != "keep"]
    prot_sources = sorted({r["source"] for r in prot_rows})
    prot_enough = len(prot_edit) >= 100 and len(prot_sources) >= 3
    check_protected = {
        "n_protected_episodes": len({r["episode_uid"] for r in prot_rows}),
        "n_protected_rows": len(prot_rows),
        "n_protected_applicable_rows": len(prot_app),
        "n_protected_editing_rows": len(prot_edit),
        "sources_covered": prot_sources,
        "threshold": "n>=100 editing rows AND >=3 sources",
        "protection_head_role": ("primary" if prot_enough else "auxiliary"),
        "pme_control": ("critic protection head + frozen structural veto"
                        if prot_enough else
                        "frozen structural veto only; protection head is an "
                        "auxiliary output and does not gate pme"),
        "pass": True,
    }

    # -- distributions -------------------------------------------------------
    dims = {
        "by_source": lambda r: r["source"],
        "by_mechanism": lambda r: r["corruption"],
        "by_severity": lambda r: r["severity"],
        "by_action": lambda r: r["action"],
        "by_family": lambda r: r["family"],
        "by_stratum": lambda r: ("clean_control" if r["protected"]
                                 else "contaminated"),
    }
    dist = {}
    for name, key in dims.items():
        buckets = defaultdict(list)
        for r in recs:
            buckets[key(r)].append(r)
        dist[name] = {k: _cell(v) for k, v in sorted(buckets.items())}

    groups = defaultdict(list)
    for r in recs:
        groups[(r["source"], r["family"], r["severity"])].append(r)
    group_cells = {f"{s}|{f}|{sev}": _cell(v)
                   for (s, f, sev), v in sorted(groups.items())}

    # episode-level group support, which is what Group-DRO actually weights
    ep_groups = defaultdict(set)
    for r in recs:
        ep_groups[(r["source"], r["family"], r["severity"])].add(
            r["episode_uid"])
    ep_support = {f"{s}|{f}|{sev}": len(v)
                  for (s, f, sev), v in sorted(ep_groups.items())}
    small = {k: v for k, v in ep_support.items()
             if v < DRO_MIN_GROUP_EPISODES}

    audit = {
        "phase": "v4.0 Phase 2.0 label and group audit "
                 "(docs/v4_0_counteract_preregistration.md §11.3)",
        "bank_freeze_digest": freeze["record_digest_sha256"],
        "bank_records_sha256": _sha256(BANK_RECORDS),
        "n_records": len(recs),
        "hard_checks": {
            "action_set_shared": check_action_set,
            "parent_grouped_splits": check_grouping,
            "six_fold_lodo_primary": check_lodo,
            "frozen_89_still_closed": check_frozen89,
            "protected_support": check_protected,
        },
        "all_hard_checks_pass": all(
            c["pass"] for c in [check_action_set, check_grouping, check_lodo,
                                check_frozen89, check_protected]),
        "distributions": dist,
        "runtime_sec": time.time() - t0,
    }
    with OUT_LABEL_AUDIT.open("w", encoding="utf-8") as f:
        json.dump(audit, f, indent=1, ensure_ascii=False)

    support = {
        "phase": "v4.0 Phase 2.0 group support (source x family x severity)",
        "group_key": "source|family|severity",
        "n_groups": len(group_cells),
        "row_level_cells": group_cells,
        "episode_level_support": ep_support,
        "dro_min_group_episodes": DRO_MIN_GROUP_EPISODES,
        "n_small_groups": len(small),
        "small_groups": small,
        "small_group_policy": ("groups below the minimum are pooled by "
                               "family x severity before Group-DRO; weights "
                               f"are capped at {DRO_WEIGHT_CAP_MULT}x uniform"),
        "runtime_sec": time.time() - t0,
    }
    with OUT_GROUP_SUPPORT.open("w", encoding="utf-8") as f:
        json.dump(support, f, indent=1, ensure_ascii=False)

    print(f"[audit] rows={len(recs)} episodes={len(by_ep)} "
          f"all_hard_checks_pass={audit['all_hard_checks_pass']} "
          f"protected_editing_rows={len(prot_edit)} "
          f"({check_protected['protection_head_role']}) "
          f"groups={len(group_cells)} small={len(small)}", flush=True)
    print("___V40_AUDIT_DONE___", flush=True)
    return 0 if audit["all_hard_checks_pass"] else 1


# -- Phase 2.1: feature cache --------------------------------------------------


def _moment_encoder(device="cuda"):
    """The frozen MOMENT-1-large encoder, mean-pooled over patches (F1)."""
    import torch
    from momentfm import MOMENTPipeline
    model = MOMENTPipeline.from_pretrained(
        TSFM_MODEL, model_kwargs={"task_name": "reconstruction"})
    model.init()
    model.to(device).eval()

    def embed(batch_series):
        """[B, 512] float64 -> [B, 1024] float32, patch-mean pooled."""
        arr = np.asarray(batch_series, dtype=np.float32)
        x = torch.from_numpy(arr).unsqueeze(1).to(device)
        im = torch.ones((len(arr), WINDOW_LEN), dtype=torch.float32,
                        device=device)
        with torch.no_grad():
            res = model.embed(x_enc=x, input_mask=im, reduction="none")
        # reduction="none" returns [B, n_channels, n_patches, D] here (the
        # channel axis is 1 for a univariate window). Collapse every axis
        # between batch and feature by mean, which is the frozen pooling:
        # mean over channels (trivial) then mean over patches.
        emb = res.embeddings
        while emb.dim() > 2:
            emb = emb.mean(dim=1)
        return emb.float().cpu().numpy().astype(np.float32)

    return model, embed


def stage_features() -> int:
    t0 = time.time()
    import torch
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    recs, metas, arrays, fills = load_bank()
    meta_index = {m["clean_parent_uid"]: i for i, m in enumerate(metas)}
    plan = {e["idx"]: e for e in bank.episode_plan()}

    rows = sorted([r for r in recs if r["applicable"]],
                  key=lambda r: (r["episode_uid"], r["action"]))
    print(f"[features] {len(rows)} applicable rows of {len(recs)} "
          f"({time.time() - t0:.0f}s)", flush=True)

    # -- rebuild every dirty window once, verify against the frozen hash -----
    dirty_cache, mat_cache = {}, {}
    for r in rows:
        idx = episode_index(r["episode_uid"])
        if idx in dirty_cache:
            continue
        clean = arrays[meta_index[r["clean_parent_uid"]]]
        dirty, _m = rebuild_episode(plan[idx], clean)
        assert hash_array(dirty) == r["input_hash"], \
            f"dirty reproduction failed on {r['episode_uid']}"
        dirty_cache[idx] = dirty
        mat_cache[idx] = materialize_for_probe(dirty)
    print(f"[features] {len(dirty_cache)} dirty windows verified "
          f"({time.time() - t0:.0f}s)", flush=True)

    n = len(rows)
    seq = np.zeros((n, 5, WINDOW_LEN), dtype=np.float32)
    struct = np.zeros((n, N_STRUCT), dtype=np.float32)
    action_idx = np.zeros(n, dtype=np.int64)
    family_idx = np.zeros(n, dtype=np.int64)
    y_gain = np.zeros(n, dtype=np.float32)
    y_harm = np.zeros(n, dtype=np.int64)
    y_prot = np.zeros(n, dtype=np.int64)
    ep_idx = np.zeros(n, dtype=np.int64)
    src_idx = np.zeros(n, dtype=np.int64)
    mech_idx = np.zeros(n, dtype=np.int64)
    sev_idx = np.zeros(n, dtype=np.int64)
    is_keep = np.zeros(n, dtype=bool)

    mechs = sorted({r["corruption"] for r in recs})
    sevs = sorted({r["severity"] for r in recs})
    mech_i = {m: i for i, m in enumerate(mechs)}
    sev_i = {s: i for i, s in enumerate(sevs)}
    src_i = {s: i for i, s in enumerate(DEV_SOURCES)}

    repaired_for_emb = np.zeros((n, WINDOW_LEN), dtype=np.float32)
    n_hash_fail = 0
    row_meta = []
    for i, r in enumerate(rows):
        idx = episode_index(r["episode_uid"])
        dirty, xm = dirty_cache[idx], mat_cache[idx]
        y, touched = rebuild_repaired(dirty, r, fills)
        # The hash is verified against the RAW operator output -- that is what
        # the freeze recorded. Materialisation happens only afterwards, for
        # the model's view.
        if hash_array(y) != r["candidate_hash"]:
            n_hash_fail += 1
        y_probe = as_probe_series(y)
        seq[i] = normalize_channels(dirty, y_probe, touched)
        struct[i] = struct_features(dirty, y_probe, touched)
        repaired_for_emb[i] = np.asarray(y_probe, dtype=np.float32)
        action_idx[i] = ACTION_INDEX[r["action"]]
        family_idx[i] = FAMILY_INDEX[r["family"]]
        y_gain[i] = float(r["gain"])
        y_harm[i] = int(bool(r["harmful"]))
        y_prot[i] = int(bool(r["protected"]) and r["action"] != "keep")
        ep_idx[i] = idx
        src_idx[i] = src_i[r["source"]]
        mech_idx[i] = mech_i[r["corruption"]]
        sev_idx[i] = sev_i[r["severity"]]
        is_keep[i] = r["action"] == "keep"
        row_meta.append({
            "row": i, "episode_uid": r["episode_uid"],
            "clean_parent_uid": r["clean_parent_uid"],
            "action": r["action"], "family": r["family"],
            "source": r["source"], "corruption": r["corruption"],
            "severity": r["severity"],
            "candidate_hash": r["candidate_hash"],
            "inner_split": inner_split(r["clean_parent_uid"]),
        })
        if (i + 1) % 2000 == 0:
            print(f"[features] rebuilt {i + 1}/{n} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} candidate hashes do not "
                         f"reproduce at feature time")
    print(f"[features] sequences+structs done, 0 hash failures "
          f"({time.time() - t0:.0f}s)", flush=True)

    # -- frozen TSFM embeddings ---------------------------------------------
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, embed = _moment_encoder(device)
    ep_order = sorted(dirty_cache)
    ep_pos = {e: i for i, e in enumerate(ep_order)}
    dirty_mat = np.stack([mat_cache[e] for e in ep_order]).astype(np.float32)

    emb_dirty = np.zeros((len(ep_order), TSFM_DIM), dtype=np.float32)
    for s in range(0, len(ep_order), TSFM_BATCH):
        emb_dirty[s:s + TSFM_BATCH] = embed(dirty_mat[s:s + TSFM_BATCH])
        if (s // TSFM_BATCH) % 20 == 0:
            print(f"[features] tsfm before {s}/{len(ep_order)} "
                  f"({time.time() - t0:.0f}s)", flush=True)

    emb_before = emb_dirty[[ep_pos[e] for e in ep_idx]]
    emb_after = np.zeros((n, TSFM_DIM), dtype=np.float32)
    # KEEP's candidate IS the materialised dirty window, so its after
    # embedding is the before embedding by construction -- computing it
    # again would only add float noise to a delta that must be exactly 0.
    todo = np.flatnonzero(~is_keep)
    emb_after[is_keep] = emb_before[is_keep]
    for s in range(0, len(todo), TSFM_BATCH):
        sel = todo[s:s + TSFM_BATCH]
        emb_after[sel] = embed(repaired_for_emb[sel])
        if (s // TSFM_BATCH) % 20 == 0:
            print(f"[features] tsfm after {s}/{len(todo)} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    gpu_peak = (float(torch.cuda.max_memory_allocated() / 2**20)
                if device == "cuda" else None)
    del model
    if device == "cuda":
        torch.cuda.empty_cache()

    np.savez(OUT_FEATURE_CACHE, seq=seq, struct=struct,
             emb_before=emb_before, emb_after=emb_after,
             action_idx=action_idx, family_idx=family_idx,
             y_gain=y_gain, y_harm=y_harm, y_prot=y_prot,
             ep_idx=ep_idx, src_idx=src_idx, mech_idx=mech_idx,
             sev_idx=sev_idx, is_keep=is_keep)
    with OUT_FEATURE_ROWS.open("w", encoding="utf-8") as f:
        for m in row_meta:
            f.write(json.dumps(m, sort_keys=True) + "\n")

    manifest = {
        "phase": "v4.0 Phase 2.1 feature cache manifest "
                 "(docs/v4_0_counteract_preregistration.md §11.3 F1-F3)",
        "n_rows": n,
        "n_episodes": len(ep_order),
        "sequence_channels": ["dirty_materialised_norm", "repaired_norm",
                              "repair_delta_norm", "raw_missing_mask",
                              "touched_support_mask"],
        "struct_features": list(STRUCT_FEATURES),
        "normalisation": ("window-local: median and IQR/1.349 from the dirty "
                          "window's finite points only, shared by the three "
                          "numeric channels; no cross-window, cross-source "
                          "or cross-fold statistics"),
        "tsfm": {
            "model": TSFM_MODEL, "revision": TSFM_REVISION,
            "dim": TSFM_DIM, "pooling": "mean over patch axis "
                                        "(embed reduction='none')",
            "input": "materialised dirty / candidate output, raw scale "
                     "(MOMENT applies its own instance norm)",
            "frozen": True, "batch": TSFM_BATCH, "device": device,
            "keep_after_equals_before": True,
        },
        "forbidden_input_keys_absent": sorted(FORBIDDEN_INPUT_KEYS),
        "grouping_only_arrays": ["src_idx", "mech_idx", "sev_idx", "ep_idx"],
        "array_sha256": {
            "seq": _sha256_array(seq), "struct": _sha256_array(struct),
            "emb_before": _sha256_array(emb_before),
            "emb_after": _sha256_array(emb_after),
            "action_idx": _sha256_array(action_idx),
            "y_gain": _sha256_array(y_gain),
            "y_harm": _sha256_array(y_harm),
            "y_prot": _sha256_array(y_prot),
        },
        "cache_file": OUT_FEATURE_CACHE.name,
        "rows_file": OUT_FEATURE_ROWS.name,
        "rows_sha256": _sha256(OUT_FEATURE_ROWS),
        "gpu_peak_mib": gpu_peak,
        "seed": SEED,
        "runtime_sec": time.time() - t0,
    }
    with OUT_FEATURE_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"[features] {n} rows cached, gpu_peak={gpu_peak} MB "
          f"({time.time() - t0:.0f}s)", flush=True)
    print("___V40_FEATURES_DONE___", flush=True)
    return 0


def stage_verify_cache() -> int:
    """Recompute the array digests in a second process (§11.3 F2)."""
    man = json.load(OUT_FEATURE_MANIFEST.open(encoding="utf-8"))
    z = np.load(OUT_FEATURE_CACHE)
    got = {k: _sha256_array(z[k]) for k in man["array_sha256"]}
    diffs = {k: {"manifest": man["array_sha256"][k], "recomputed": v}
             for k, v in got.items() if v != man["array_sha256"][k]}
    out = {"pass": not diffs, "n_arrays": len(got), "mismatches": diffs}
    print(f"[verify-cache] pass={out['pass']} mismatches={list(diffs)}",
          flush=True)
    print("___V40_VERIFY_CACHE_DONE___", flush=True)
    return 0 if out["pass"] else 1


# -- Phase 2.2: the model ------------------------------------------------------


def _build_modules():
    """Imported lazily so the CPU stages never need torch."""
    import torch
    import torch.nn as nn

    class ResBlock1d(nn.Module):
        def __init__(self, c_in, c_out, stride):
            super().__init__()
            self.conv1 = nn.Conv1d(c_in, c_out, 5, stride=stride, padding=2)
            self.gn1 = nn.GroupNorm(8, c_out)
            self.conv2 = nn.Conv1d(c_out, c_out, 5, padding=2)
            self.gn2 = nn.GroupNorm(8, c_out)
            self.skip = (nn.Conv1d(c_in, c_out, 1, stride=stride)
                         if (c_in != c_out or stride != 1) else nn.Identity())
            self.act = nn.GELU()

        def forward(self, x):
            h = self.act(self.gn1(self.conv1(x)))
            h = self.gn2(self.conv2(h))
            return self.act(h + self.skip(x))

    class SeqEncoder(nn.Module):
        """Shared-weight branch for the dirty and the repaired window."""

        def __init__(self, c_in=1, widths=(64, 64, 96, 128)):
            super().__init__()
            self.stem = nn.Sequential(
                nn.Conv1d(c_in, widths[0], 7, stride=2, padding=3),
                nn.GroupNorm(8, widths[0]), nn.GELU())
            self.blocks = nn.Sequential(*[
                ResBlock1d(widths[i], widths[i + 1], 2)
                for i in range(len(widths) - 1)])
            self.out_dim = widths[-1] * 2

        def forward(self, x):
            h = self.blocks(self.stem(x))
            return torch.cat([h.mean(dim=-1), h.amax(dim=-1)], dim=-1)

    class ActionCritic(nn.Module):
        """Action-delta critic (§11.3 F4).

        The dirty and repaired windows go through one shared encoder, so the
        model is comparing two views of the same series rather than learning
        two unrelated representations; the delta branch sees the edit itself
        together with the masks that say where the operator was allowed to
        write.
        """

        def __init__(self, use_seq, use_tsfm, use_delta, use_struct,
                     n_actions=len(ACTIONS), n_families=len(FAMILIES)):
            super().__init__()
            self.use_seq = use_seq
            self.use_tsfm = use_tsfm
            self.use_delta = use_delta
            self.use_struct = use_struct
            dim = 0
            if use_seq:
                self.seq_enc = SeqEncoder(1)
                dim += 2 * self.seq_enc.out_dim
            if use_delta:
                self.delta_enc = SeqEncoder(3, widths=(48, 48, 64))
                dim += self.delta_enc.out_dim
            if use_tsfm:
                self.proj_before = nn.Sequential(
                    nn.Linear(TSFM_DIM, 96), nn.LayerNorm(96))
                self.proj_after = nn.Sequential(
                    nn.Linear(TSFM_DIM, 96), nn.LayerNorm(96))
                self.proj_delta = nn.Sequential(
                    nn.Linear(TSFM_DIM, 96), nn.LayerNorm(96))
                dim += 288
            if use_struct:
                self.struct_mlp = nn.Sequential(
                    nn.Linear(N_STRUCT, 64), nn.GELU(), nn.Linear(64, 64))
                dim += 64
            self.action_emb = nn.Embedding(n_actions, 32)
            self.family_emb = nn.Embedding(n_families, 16)
            dim += 48
            self.fuse = nn.Sequential(
                nn.Linear(dim, 256), nn.LayerNorm(256), nn.GELU(),
                nn.Dropout(0.1), nn.Linear(256, 128), nn.GELU())
            self.head_gain = nn.Linear(128, len(QUANTILES))
            self.head_harm = nn.Linear(128, 1)
            self.head_prot = nn.Linear(128, 1)

        def forward(self, seq, struct, eb, ea, aidx, fidx):
            parts = []
            if self.use_seq:
                parts.append(self.seq_enc(seq[:, 0:1]))
                parts.append(self.seq_enc(seq[:, 1:2]))
            if self.use_delta:
                parts.append(self.delta_enc(seq[:, 2:5]))
            if self.use_tsfm:
                parts.append(self.proj_before(eb))
                parts.append(self.proj_after(ea))
                parts.append(self.proj_delta(ea - eb))
            if self.use_struct:
                parts.append(self.struct_mlp(struct))
            parts.append(self.action_emb(aidx))
            parts.append(self.family_emb(fidx))
            h = self.fuse(torch.cat(parts, dim=-1))
            q = self.head_gain(h)
            # Quantiles must not cross: predict q10 then positive increments.
            q10 = q[:, 0:1]
            q50 = q10 + torch.nn.functional.softplus(q[:, 1:2])
            q90 = q50 + torch.nn.functional.softplus(q[:, 2:3])
            return (torch.cat([q10, q50, q90], dim=-1),
                    self.head_harm(h).squeeze(-1),
                    self.head_prot(h).squeeze(-1))

    return ActionCritic


def pinball_loss(pred, target, quantiles=QUANTILES):
    import torch
    t = target.unsqueeze(-1)
    e = t - pred
    qs = torch.tensor(quantiles, device=pred.device, dtype=pred.dtype)
    return torch.maximum(qs * e, (qs - 1.0) * e).mean(dim=-1)


# -- Phase 2.3: six-fold LODO training -----------------------------------------


class Cache:
    """The frozen feature cache, held once and indexed per fold."""

    def __init__(self):
        z = np.load(OUT_FEATURE_CACHE)
        self.seq = z["seq"]
        self.struct = z["struct"]
        self.emb_before = z["emb_before"]
        self.emb_after = z["emb_after"]
        self.action_idx = z["action_idx"]
        self.family_idx = z["family_idx"]
        self.y_gain = z["y_gain"]
        self.y_harm = z["y_harm"]
        self.y_prot = z["y_prot"]
        self.ep_idx = z["ep_idx"]
        self.src_idx = z["src_idx"]
        self.mech_idx = z["mech_idx"]
        self.sev_idx = z["sev_idx"]
        self.is_keep = z["is_keep"]
        self.rows = [json.loads(l) for l in
                     OUT_FEATURE_ROWS.open(encoding="utf-8")]
        assert len(self.rows) == len(self.seq)
        self.n = len(self.rows)
        # bank labels for B&S are needed at evaluation time only
        bs = np.zeros(self.n, dtype=np.int64)
        recs = {(r["episode_uid"], r["action"]): r
                for r in (json.loads(l) for l in
                          BANK_RECORDS.open(encoding="utf-8"))}
        for i, m in enumerate(self.rows):
            bs[i] = int(bool(
                recs[(m["episode_uid"], m["action"])]["beneficial_and_safe"]))
        self.y_bs = bs

    def fold_masks(self, held_source):
        src = np.array([m["source"] for m in self.rows])
        inner = np.array([m["inner_split"] for m in self.rows])
        test = src == held_source
        train = (~test) & (inner == "inner_train")
        val = (~test) & (inner == "inner_val")
        return train, val, test


def _episode_batches(ep_ids, rng, batch_episodes=BATCH_EPISODES,
                     ep_source=None):
    """Batches of whole episodes -- the pairwise term needs the KEEP row.

    With ``ep_source`` (the rescue's "strengthen source-balanced training"),
    each batch is filled round-robin over the five training sources instead
    of by a global shuffle, so a source with more usable parents cannot
    dominate the gradient before Group-DRO's weights have moved.
    """
    uniq = np.unique(ep_ids)
    if ep_source is None:
        order = rng.permutation(len(uniq))
        for s in range(0, len(uniq), batch_episodes):
            yield uniq[order[s:s + batch_episodes]]
        return
    by_src = defaultdict(list)
    for e in uniq:
        by_src[ep_source[int(e)]].append(int(e))
    for src in by_src:
        by_src[src] = [by_src[src][i]
                       for i in rng.permutation(len(by_src[src]))]
    srcs = sorted(by_src)
    pos = {s: 0 for s in srcs}
    remaining = sum(len(v) for v in by_src.values())
    while remaining > 0:
        batch = []
        while len(batch) < batch_episodes and remaining > 0:
            for s in srcs:
                if pos[s] < len(by_src[s]):
                    batch.append(by_src[s][pos[s]])
                    pos[s] += 1
                    remaining -= 1
                    if len(batch) >= batch_episodes:
                        break
        if batch:
            yield np.array(batch)


def _group_keys(cache, idx):
    return [f"{cache.rows[i]['source']}|{cache.rows[i]['family']}|"
            f"{cache.rows[i]['severity']}" for i in idx]


def train_one(cache, held_source, arm, device, log):
    """One (fold, arm) training run. Returns a result dict."""
    import torch
    import torch.nn as nn

    use_seq, use_tsfm, use_delta, use_struct, use_dro = ARM_CONFIG[arm]
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    rng = np.random.RandomState(SEED)

    train_m, val_m, test_m = cache.fold_masks(held_source)
    tr = np.flatnonzero(train_m)
    va = np.flatnonzero(val_m)
    te = np.flatnonzero(test_m)

    def to_dev(a, dtype=None):
        t = torch.from_numpy(np.ascontiguousarray(a))
        if dtype is not None:
            t = t.to(dtype)
        return t.to(device)

    SEQ = to_dev(cache.seq)
    STR = to_dev(cache.struct)
    EB = to_dev(cache.emb_before)
    EA = to_dev(cache.emb_after)
    AI = to_dev(cache.action_idx)
    FI = to_dev(cache.family_idx)
    YG = to_dev(cache.y_gain)
    YH = to_dev(cache.y_harm, torch.float32)
    YP = to_dev(cache.y_prot, torch.float32)

    # TSFM embeddings are z-scored on the inner-train rows of THIS fold only.
    mu = cache.emb_before[tr].mean(0)
    sd = cache.emb_before[tr].std(0) + 1e-6
    MU, SD = to_dev(mu), to_dev(sd)

    ActionCritic = _build_modules()
    model = ActionCritic(use_seq, use_tsfm, use_delta, use_struct).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=LR,
                            weight_decay=WEIGHT_DECAY)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda e: min(1.0, (e + 1) / WARMUP_EPOCHS)
        * (0.5 * (1 + math.cos(math.pi * min(e / MAX_EPOCHS, 1.0)))))

    pos_h = float(min((cache.y_harm[tr] == 0).sum()
                      / max((cache.y_harm[tr] == 1).sum(), 1), POS_WEIGHT_CAP))
    pos_p = float(min((cache.y_prot[tr] == 0).sum()
                      / max((cache.y_prot[tr] == 1).sum(), 1), POS_WEIGHT_CAP))
    bce_h = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pos_h, device=device), reduction="none")
    bce_p = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pos_p, device=device), reduction="none")
    rank_loss = nn.MarginRankingLoss(margin=0.05, reduction="none")

    # group bookkeeping (episode-level, per §11.3 F6)
    row_group = np.array(_group_keys(cache, np.arange(cache.n)))
    ep_count = defaultdict(set)
    for i in tr:
        ep_count[row_group[i]].add(int(cache.ep_idx[i]))
    small = {g for g, s in ep_count.items() if len(s) < DRO_MIN_GROUP_EPISODES}
    def gkey(i):
        g = row_group[i]
        if g in small:                     # pool tiny groups by family|severity
            _s, fam, sev = g.split("|")
            return f"POOL|{fam}|{sev}"
        return g
    groups = sorted({gkey(i) for i in tr})
    gidx = {g: k for k, g in enumerate(groups)}
    G = len(groups)
    q = np.full(G, 1.0 / G)
    cap = DRO_WEIGHT_CAP_MULT / G

    rows_by_ep = defaultdict(list)
    for i in tr:
        rows_by_ep[int(cache.ep_idx[i])].append(i)
    ep_ids_tr = np.array(sorted(rows_by_ep))
    ep_source = ({int(cache.ep_idx[i]): cache.rows[i]["source"] for i in tr}
                 if RESCUE else None)

    def forward(idx_np):
        idx = to_dev(idx_np.astype(np.int64))
        eb = (EB[idx] - MU) / SD
        ea = (EA[idx] - MU) / SD
        return model(SEQ[idx], STR[idx], eb, ea, AI[idx], FI[idx])

    @torch.no_grad()
    def predict(idx_np, chunk=2048):
        model.eval()
        qs, hs, ps = [], [], []
        for s in range(0, len(idx_np), chunk):
            qq, hh, pp = forward(idx_np[s:s + chunk])
            qs.append(qq.cpu().numpy())
            hs.append(torch.sigmoid(hh).cpu().numpy())
            ps.append(torch.sigmoid(pp).cpu().numpy())
        return (np.concatenate(qs), np.concatenate(hs), np.concatenate(ps))

    history, q_track = [], []
    best = {"score": -np.inf, "epoch": -1, "state": None}
    t0 = time.time()
    for epoch in range(MAX_EPOCHS):
        model.train()
        dro_on = use_dro and epoch >= WARMUP_EPOCHS
        ep_losses, batch_group_loss = [], defaultdict(list)
        for eps in _episode_batches(ep_ids_tr, rng, ep_source=ep_source):
            idx_np = np.concatenate([rows_by_ep[int(e)] for e in eps])
            qpred, hlogit, plogit = forward(idx_np)
            idx_t = to_dev(idx_np.astype(np.int64))
            l_pin = pinball_loss(qpred, YG[idx_t])
            l_h = bce_h(hlogit, YH[idx_t])
            l_p = bce_p(plogit, YP[idx_t])
            per_row = l_pin + LAMBDA_H * l_h + LAMBDA_P * l_p

            # within-episode action-vs-KEEP ranking on the median head
            local = {int(r): k for k, r in enumerate(idx_np)}
            a_pos, k_pos, sign = [], [], []
            for e in eps:
                rs = rows_by_ep[int(e)]
                keeps = [r for r in rs if cache.is_keep[r]]
                if not keeps:
                    continue
                kp = local[keeps[0]]
                for r in rs:
                    if cache.is_keep[r]:
                        continue
                    g = float(cache.y_gain[r])
                    if abs(g) <= 1e-9:      # ties carry no ordering signal
                        continue
                    a_pos.append(local[r])
                    k_pos.append(kp)
                    sign.append(1.0 if g > 0 else -1.0)
            if a_pos:
                ap = torch.tensor(a_pos, device=device)
                kp_t = torch.tensor(k_pos, device=device)
                sg = torch.tensor(sign, device=device, dtype=qpred.dtype)
                l_rank = rank_loss(qpred[ap, 1], qpred[kp_t, 1], sg)
                rank_term = LAMBDA_R * l_rank.mean()
            else:
                rank_term = torch.zeros((), device=device)

            if dro_on:
                # per-episode mean first, then per-group mean: the 33,600
                # action rows are never treated as independent samples.
                per_ep = defaultdict(list)
                for k, r in enumerate(idx_np):
                    per_ep[(gkey(r), int(cache.ep_idx[r]))].append(k)
                gl = defaultdict(list)
                for (g, _e), ks in per_ep.items():
                    gl[g].append(per_row[torch.tensor(ks, device=device)].mean())
                present = sorted(gl)
                gvals = torch.stack([torch.stack(gl[g]).mean()
                                     for g in present])
                w = torch.tensor([q[gidx[g]] for g in present], device=device,
                                 dtype=gvals.dtype)
                w = w / w.sum().clamp_min(1e-12)
                loss = (w * gvals).sum() + rank_term
                with torch.no_grad():
                    for g, v in zip(present, gvals.detach().cpu().numpy()):
                        q[gidx[g]] *= math.exp(DRO_ETA * float(v))
                        batch_group_loss[g].append(float(v))
                    q[:] = np.minimum(q / q.sum(), cap)
                    q[:] = q / q.sum()
            else:
                loss = per_row.mean() + rank_term
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            ep_losses.append(float(loss.detach()))
        sched.step()

        vq, vh, vp = predict(va)
        v_auroc = auroc(vh, cache.y_harm[va])
        from scipy import stats as _st
        v_rho = float(_st.spearmanr(vq[:, 1], cache.y_gain[va]).statistic)
        score = (v_auroc or 0.0) + (v_rho if np.isfinite(v_rho) else 0.0)
        history.append({
            "epoch": epoch, "train_loss": float(np.mean(ep_losses)),
            "val_harm_auroc": v_auroc, "val_gain_spearman": v_rho,
            "val_score": score, "dro_on": bool(dro_on),
            "lr": float(opt.param_groups[0]["lr"]),
        })
        if dro_on:
            q_track.append({"epoch": epoch, "max_q_over_uniform":
                            float(q.max() * G),
                            "entropy": float(-(q * np.log(q + 1e-12)).sum()),
                            "n_at_cap": int((q >= cap - 1e-12).sum())})
        if score > best["score"]:
            best = {"score": score, "epoch": epoch,
                    "state": {k: v.detach().clone()
                              for k, v in model.state_dict().items()}}
        if epoch - best["epoch"] >= PATIENCE:
            break

    model.load_state_dict(best["state"])
    wall = time.time() - t0
    log(f"    [{arm}|{held_source}] best epoch {best['epoch']} "
        f"score {best['score']:.4f} ({wall:.0f}s, {len(history)} epochs)")

    vq, vh, vp = predict(va)
    tq, th, tp = predict(te)
    thr = select_threshold(cache, va, vq, vh, vp)
    test_metrics = evaluate_split(cache, te, tq, th, tp, thr)
    val_metrics = evaluate_split(cache, va, vq, vh, vp, thr)

    ckpt_path = CKPT_DIR / f"{arm}__{held_source.replace(' ', '_')}.pt"
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": best["state"], "arm": arm,
                "held_source": held_source, "threshold": thr,
                "tsfm_mu": mu, "tsfm_sd": sd, "seed": SEED}, ckpt_path)

    return {
        "arm": arm, "held_source": held_source, "n_params": n_params,
        "n_train_rows": len(tr), "n_val_rows": len(va), "n_test_rows": len(te),
        "best_epoch": best["epoch"], "n_epochs_run": len(history),
        "threshold": thr, "val": val_metrics, "test": test_metrics,
        "history": history, "dro_weights": q_track,
        "dro_groups": G, "pooled_small_groups": sorted(small),
        "pos_weight_harm": pos_h, "pos_weight_protected": pos_p,
        "wall_sec": wall,
        "checkpoint": str(ckpt_path.relative_to(ROOT)),
        "checkpoint_sha256": _sha256(ckpt_path),
        "predictions": {"idx": te.tolist(),
                        "q10": tq[:, 0].tolist(), "q50": tq[:, 1].tolist(),
                        "q90": tq[:, 2].tolist(),
                        "harm": th.tolist(), "prot": tp.tolist()},
    }


class PolicyView:
    """Episode-grouped arrays for one evaluation split.

    The threshold grid is 600 points and the deployment rule has to be
    replayed at each one, so the per-episode argmax is done with segment
    reductions rather than a Python loop -- same rule, ~50x less wall time.
    """

    def __init__(self, cache, idx):
        self.idx = np.asarray(idx)
        ep = cache.ep_idx[self.idx]
        self.uniq, self.inv = np.unique(ep, return_inverse=True)
        self.n_ep = len(self.uniq)
        self.is_keep = cache.is_keep[self.idx]
        self.y_harm = cache.y_harm[self.idx]
        self.y_bs = cache.y_bs[self.idx]
        self.y_prot = cache.y_prot[self.idx]
        self.row_pos = np.arange(len(self.idx))

    def select(self, q10, harm, prot, thr):
        """Positions (into idx) of the committed action per episode."""
        ok = ((harm < thr["tau_h"]) & (q10 > thr["delta"])
              & (prot < thr["tau_p"]) & (~self.is_keep))
        if not ok.any():
            return np.empty(0, dtype=np.int64)
        score = np.where(ok, q10, -np.inf)
        best = np.full(self.n_ep, -np.inf)
        np.maximum.at(best, self.inv, score)
        hit = ok & (score == best[self.inv]) & np.isfinite(best[self.inv])
        cand = np.flatnonzero(hit)
        # deterministic tie-break: lowest row position wins
        order = np.lexsort((cand, self.inv[cand]))
        cand = cand[order]
        first = np.ones(len(cand), dtype=bool)
        first[1:] = self.inv[cand][1:] != self.inv[cand][:-1]
        return cand[first]

    def counts(self, chosen):
        n_c = len(chosen)
        harmful = int(self.y_harm[chosen].sum()) if n_c else 0
        bs = int(self.y_bs[chosen].sum()) if n_c else 0
        prot_edit = int(self.y_prot[chosen].sum()) if n_c else 0
        return {
            "n_episodes": self.n_ep, "n_committed": n_c,
            "n_harmful_commits": harmful, "n_bs_commits": bs,
            "n_protected_edits": prot_edit,
            "chr": (harmful / n_c) if n_c else 0.0,
            "chr_cp95_upper": clopper_pearson_upper(harmful, n_c),
            "bcov": bs / self.n_ep if self.n_ep else 0.0,
            "abstention_rate": (1.0 - n_c / self.n_ep) if self.n_ep else 1.0,
        }


def policy_select_reference(cache, idx, q10, harm, prot, thr):
    """Readable reference implementation of the deployment rule (§5).

    Kept as the oracle the vectorised PolicyView is tested against.
    """
    by_ep = defaultdict(list)
    for k, i in enumerate(idx):
        by_ep[int(cache.ep_idx[i])].append(k)
    chosen = []
    for e in sorted(by_ep):
        best_k, best_q = None, -np.inf
        for k in by_ep[e]:
            if cache.is_keep[idx[k]]:
                continue
            if (harm[k] < thr["tau_h"] and q10[k] > thr["delta"]
                    and prot[k] < thr["tau_p"] and q10[k] > best_q):
                best_k, best_q = k, q10[k]
        if best_k is not None:
            chosen.append(best_k)
    return np.array(sorted(chosen), dtype=np.int64)


def select_threshold(cache, idx, qpred, harm, prot, view=None):
    """Grid search on this fold's inner-validation rows only (§11.3 F9)."""
    view = view or PolicyView(cache, idx)
    q10 = qpred[:, 0]
    best = None
    for tau_h in TAU_H_GRID:
        for delta in DELTA_GRID:
            for tau_p in TAU_P_GRID:
                thr = {"tau_h": tau_h, "delta": delta, "tau_p": tau_p}
                counts = view.counts(view.select(q10, harm, prot, thr))
                if counts["chr_cp95_upper"] > CHR_CALIB_UPPER:
                    continue
                key = (counts["bcov"], -counts["chr"])
                if best is None or key > best[0]:
                    best = (key, {**thr, "val_counts": counts})
    if best is None:
        return {"tau_h": None, "delta": None, "tau_p": None,
                "no_calibrated_point": True,
                "reason": f"no grid point reached CHR CP95 <= {CHR_CALIB_UPPER}"}
    out = dict(best[1])
    out["no_calibrated_point"] = False
    return out


def evaluate_split(cache, idx, qpred, harm, prot, thr):
    from scipy import stats as _st
    y_h = cache.y_harm[idx]
    y_g = cache.y_gain[idx]
    prev = float(y_h.mean())
    ap = average_precision(harm, y_h)
    cov = {f"q{int(q * 100)}": float((y_g <= qpred[:, i]).mean())
           for i, q in enumerate(QUANTILES)}
    bins = np.linspace(0, 1, 11)
    which = np.clip(np.digitize(harm, bins) - 1, 0, 9)
    calib = [{"bin": float(bins[b]),
              "n": int((which == b).sum()),
              "mean_pred": float(harm[which == b].mean()) if (which == b).any()
                           else None,
              "obs_rate": float(y_h[which == b].mean()) if (which == b).any()
                          else None}
             for b in range(10)]
    out = {
        "n_rows": len(idx),
        "harm_prevalence": prev,
        "harm_auroc": auroc(harm, y_h),
        "harm_auprc": ap,
        "harm_auprc_lift": (ap - prev) if ap is not None else None,
        "gain_spearman": float(_st.spearmanr(qpred[:, 1], y_g).statistic),
        "gain_kendall": float(_st.kendalltau(qpred[:, 1], y_g).statistic),
        "quantile_coverage": cov,
        "calibration": calib,
        "protected_auroc": (auroc(prot, cache.y_prot[idx])
                            if cache.y_prot[idx].sum() else None),
    }
    if not thr.get("no_calibrated_point"):
        view = PolicyView(cache, idx)
        out["policy"] = view.counts(
            view.select(qpred[:, 0], harm, prot, thr))
        per_src = {}
        srcs = np.array([cache.rows[i]["source"] for i in idx])
        for s in sorted(set(srcs)):
            sub = np.flatnonzero(srcs == s)
            if not len(sub):
                continue
            sv = PolicyView(cache, idx[sub])
            per_src[s] = sv.counts(
                sv.select(qpred[sub, 0], harm[sub], prot[sub], thr))
        out["per_source_policy"] = per_src
    else:
        out["policy"] = None
    return out


def stage_train() -> int:
    import torch
    t0 = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    logs = []

    def log(msg):
        print(msg, flush=True)
        logs.append(msg)

    cache = Cache()
    log(f"[train] cache {cache.n} rows, device={device}")
    results, diagnostics = [], []
    for arm in ARMS:
        for src in DEV_SOURCES:
            r = train_one(cache, src, arm, device, log)
            diagnostics.append({
                "arm": arm, "held_source": src,
                "history": r.pop("history"),
                "dro_weights": r.pop("dro_weights"),
                "n_params": r["n_params"], "wall_sec": r["wall_sec"],
                "pos_weight_harm": r["pos_weight_harm"],
                "pos_weight_protected": r["pos_weight_protected"],
                "dro_groups": r["dro_groups"],
                "pooled_small_groups": r["pooled_small_groups"],
            })
            results.append(r)
    gpu_peak = (float(torch.cuda.max_memory_allocated() / 2**20)
                if device == "cuda" else None)

    with OUT_CRITIC_PRED.open("w", encoding="utf-8") as f:
        for r in results:
            pred = r.pop("predictions")
            for j, i in enumerate(pred["idx"]):
                m = cache.rows[i]
                f.write(json.dumps({
                    "arm": r["arm"], "held_source": r["held_source"],
                    "row": i, "episode_uid": m["episode_uid"],
                    "action": m["action"], "family": m["family"],
                    "source": m["source"], "corruption": m["corruption"],
                    "severity": m["severity"],
                    "q10": pred["q10"][j], "q50": pred["q50"][j],
                    "q90": pred["q90"][j], "harm_prob": pred["harm"][j],
                    "prot_prob": pred["prot"][j],
                    "y_gain": float(cache.y_gain[i]),
                    "y_harmful": int(cache.y_harm[i]),
                    "y_bs": int(cache.y_bs[i]),
                    "y_protected_edit": int(cache.y_prot[i]),
                }, sort_keys=True) + "\n")

    def pooled(arm):
        rs = [r for r in results if r["arm"] == arm]
        au = [r["test"]["harm_auroc"] for r in rs
              if r["test"]["harm_auroc"] is not None]
        va = [r["val"]["harm_auroc"] for r in rs
              if r["val"]["harm_auroc"] is not None]
        pol = [r["test"]["policy"] for r in rs if r["test"]["policy"]]
        return {
            "n_folds": len(rs),
            "mean_test_harm_auroc": float(np.mean(au)) if au else None,
            "min_test_harm_auroc": float(np.min(au)) if au else None,
            "mean_val_harm_auroc": float(np.mean(va)) if va else None,
            "mean_test_gain_spearman": float(np.mean(
                [r["test"]["gain_spearman"] for r in rs])),
            "mean_test_auprc_lift": float(np.mean(
                [r["test"]["harm_auprc_lift"] for r in rs
                 if r["test"]["harm_auprc_lift"] is not None])),
            "folds_without_calibrated_point": sum(
                1 for r in rs if r["threshold"].get("no_calibrated_point")),
            "pooled_test_bcov": (float(np.mean([p["bcov"] for p in pol]))
                                 if pol else None),
            "pooled_test_chr": (float(np.mean([p["chr"] for p in pol]))
                                if pol else None),
            "n_params": rs[0]["n_params"] if rs else None,
        }

    summary = {arm: pooled(arm) for arm in ARMS}
    out = {
        "phase": "v4.0 Phase 2.3 six-fold LODO training "
                 "(docs/v4_0_counteract_preregistration.md §11.3 F4-F9)",
        "seed": SEED, "device": device,
        "feature_manifest_sha256": _sha256(OUT_FEATURE_MANIFEST),
        "arms": summary,
        "folds": results,
        "gpu_peak_mib": gpu_peak,
        "param_budget_5m_respected": all(
            r["n_params"] < 5_000_000 for r in results),
        "runtime_sec": time.time() - t0,
    }
    with OUT_CRITIC_LODO.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    with OUT_CRITIC_ABLATION.open("w", encoding="utf-8") as f:
        json.dump({"arms": summary,
                   "arm_config": {a: dict(zip(
                       ("use_seq", "use_tsfm", "use_delta", "use_struct",
                        "use_dro"), ARM_CONFIG[a])) for a in ARMS}},
                  f, indent=1, ensure_ascii=False)
    with OUT_CRITIC_DIAG.open("w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "gpu_peak_mib": gpu_peak,
                   "runs": diagnostics, "log": logs},
                  f, indent=1, ensure_ascii=False, default=str)
    with OUT_CRITIC_CKPT.open("w", encoding="utf-8") as f:
        json.dump({"seed": SEED,
                   "checkpoints": [{"arm": r["arm"],
                                    "held_source": r["held_source"],
                                    "path": r["checkpoint"],
                                    "sha256": r["checkpoint_sha256"],
                                    "threshold": r["threshold"]}
                                   for r in results]},
                  f, indent=1, ensure_ascii=False)
    for arm in ARMS:
        s = summary[arm]
        print(f"[train] {arm}: test AUROC mean={s['mean_test_harm_auroc']} "
              f"min={s['min_test_harm_auroc']} "
              f"val={s['mean_val_harm_auroc']} "
              f"bcov={s['pooled_test_bcov']} chr={s['pooled_test_chr']} "
              f"params={s['n_params']}", flush=True)
    print("___V40_TRAIN_DONE___", flush=True)
    return 0


# -- Phase 2.4: the one-shot frozen-89 decision --------------------------------

#: Frozen v3.9 reference points on the same 89 windows. raw TS-ICL from
#: results/v39_longgap_probe.json (proposer_tables.tsicl); MIRAGE from
#: results/v39_bridge_probe.json (primary_arm_pooled).
REF_RAW_TSICL = {"n_commits": 89, "n_bs": 75, "n_harmful": 14,
                 "chr": 14 / 89, "bcov": 75 / 89, "coverage": 1.0}
REF_MIRAGE = {"n_commits": 47, "n_bs": 34, "n_harmful": 13,
              "chr": 13 / 47, "bcov": 34 / 89, "coverage": 47 / 89}

GATES = {
    "g1_harm_auroc_min": 0.75,
    "g2_auprc_lift_min": 0.10,
    "g3_bs_retained_min": 55,
    "g4_harmful_max": 3,
    "g5_chr_cp95_upper_max": 0.15,
    "g7_sources_not_degraded_min": 4,
}


def load_frozen89():
    """The 89 frozen long-gap windows with their TS-ICL candidates.

    Labels are read here and nowhere else: this function is only called by
    `decide`, after the training freeze is registered (§11.3 F10).
    """
    cands = [json.loads(l) for l in V39_CANDIDATES.open(encoding="utf-8")]
    tsicl = [r for r in cands if r["proposer"] == "tsicl"]
    assert len(tsicl) == 89, f"expected 89 TS-ICL candidates, got {len(tsicl)}"
    probe = json.load(V39_PROBE.open(encoding="utf-8"))
    table = probe["proposer_tables"]["tsicl"]
    assert table["n_bs"] == 75 and table["n_harmful"] == 14
    return tsicl, set(table["bs_uids"]), set(table["harmful_uids"])


def _frontier(harm, y_harm, y_bs, n_windows):
    """Risk-coverage frontier by sweeping the harm threshold."""
    pts = []
    for tau in np.unique(np.concatenate([[0.0], np.sort(harm), [1.0]])):
        sel = harm < tau
        k = int(sel.sum())
        if k == 0:
            continue
        h = int(y_harm[sel].sum())
        pts.append({"tau": float(tau), "coverage": k / n_windows,
                    "n_commits": k, "n_harmful": h,
                    "n_bs": int(y_bs[sel].sum()),
                    "chr": h / k,
                    "chr_cp95_upper": clopper_pearson_upper(h, k)})
    return pts


def _dominates(pts, ref):
    """Is some frontier point strictly better than a reference point?

    Strict domination: no worse on both axes and strictly better on one --
    at least the reference's coverage with a lower harm rate, or at most the
    reference's harm rate with more coverage.
    """
    hits = []
    for p in pts:
        better_cov = (p["coverage"] >= ref["coverage"] and p["chr"] < ref["chr"])
        better_chr = (p["chr"] <= ref["chr"] and p["coverage"] > ref["coverage"])
        if better_cov or better_chr:
            hits.append(p)
    return hits


def _paired_bootstrap(a_scores, b_scores, n_boot=10000, seed=SEED):
    """Paired bootstrap over windows on a per-window utility difference."""
    rng = np.random.RandomState(seed)
    d = np.asarray(a_scores, dtype=np.float64) - np.asarray(b_scores,
                                                            dtype=np.float64)
    n = len(d)
    means = np.array([d[rng.randint(0, n, n)].mean() for _ in range(n_boot)])
    return {
        "mean_diff": float(d.mean()),
        "ci95": [float(np.percentile(means, 2.5)),
                 float(np.percentile(means, 97.5))],
        "p_gt_0": float((means > 0).mean()),
        "n_windows": n,
    }


def stage_decide() -> int:
    import torch
    t0 = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)

    # -- the training freeze must exist and re-verify before labels open ----
    if not OUT_CRITIC_CKPT.exists() or not OUT_CRITIC_LODO.exists():
        raise SystemExit("[FATAL] training freeze missing; run `train` first")
    ck = json.load(OUT_CRITIC_CKPT.open(encoding="utf-8"))
    drift = [c for c in ck["checkpoints"]
             if _sha256(ROOT / c["path"]) != c["sha256"]]
    if drift:
        raise SystemExit(f"[FATAL] {len(drift)} checkpoints changed after "
                         f"the freeze: {[c['path'] for c in drift]}")
    print(f"[decide] {len(ck['checkpoints'])} checkpoints re-verified; "
          f"opening the frozen 89 now", flush=True)

    tsicl, bs_uids, harmful_uids = load_frozen89()

    # -- rebuild the 89 windows from the frozen corpus ----------------------
    from v38_impute_mask_audit import rebuild_corpus
    recs, _dropped = rebuild_corpus()
    by_uid = {r["sample_uid"]: r for r in recs}

    rows, n_hash_fail = [], 0
    seqs = np.zeros((89, 5, WINDOW_LEN), dtype=np.float32)
    structs = np.zeros((89, N_STRUCT), dtype=np.float32)
    dirty_mat = np.zeros((89, WINDOW_LEN), dtype=np.float32)
    rep_mat = np.zeros((89, WINDOW_LEN), dtype=np.float32)
    for i, cand in enumerate(sorted(tsicl, key=lambda r: r["sample_uid"])):
        src_rec = by_uid[cand["sample_uid"]]
        dirty = np.asarray(src_rec["series"], dtype=np.float64)
        assert hash_array(dirty) == cand["input_hash"], \
            f"dirty mismatch on {cand['sample_uid']}"
        y, touched = bank.rebuild_tsicl_output(dirty, cand["fill_values"])
        if hash_array(y) != cand["output_hash"]:
            n_hash_fail += 1
        y_probe = as_probe_series(y)
        seqs[i] = normalize_channels(dirty, y_probe, touched)
        structs[i] = struct_features(dirty, y_probe, touched)
        dirty_mat[i] = materialize_for_probe(dirty).astype(np.float32)
        rep_mat[i] = y_probe.astype(np.float32)
        # sample_uid already carries the corrupted hash as its last field and
        # is exactly the key the frozen probe's bs/harmful lists use.
        key = cand["sample_uid"]
        rows.append({
            "sample_uid": cand["sample_uid"], "key": key,
            "source": cand["dataset"], "true_kind": cand["true_kind"],
            "n_raw_nan": cand["n_raw_nan"], "n_filled": cand["n_filled"],
            "observed_support_drift": cand["observed_support_drift"],
            "y_bs": int(key in bs_uids), "y_harmful": int(key in harmful_uids),
        })
    if n_hash_fail:
        raise SystemExit(f"[FATAL] {n_hash_fail} of 89 TS-ICL candidate "
                         f"hashes do not reproduce")
    y_bs = np.array([r["y_bs"] for r in rows])
    y_harm = np.array([r["y_harmful"] for r in rows])
    assert y_bs.sum() == 75 and y_harm.sum() == 14, \
        f"frozen labels drifted: {y_bs.sum()} B&S / {y_harm.sum()} harmful"
    print(f"[decide] 89 windows rebuilt, hashes reproduce, labels 75/14 "
          f"({time.time() - t0:.0f}s)", flush=True)

    # -- frozen TSFM embeddings for the 89 ----------------------------------
    model_m, embed = _moment_encoder(device)
    eb = np.concatenate([embed(dirty_mat[s:s + TSFM_BATCH])
                         for s in range(0, 89, TSFM_BATCH)])
    ea = np.concatenate([embed(rep_mat[s:s + TSFM_BATCH])
                         for s in range(0, 89, TSFM_BATCH)])
    del model_m
    if device == "cuda":
        torch.cuda.empty_cache()

    ActionCritic = _build_modules()
    aidx = np.full(89, ACTION_INDEX["tsicl_long"], dtype=np.int64)
    fidx = np.full(89, FAMILY_INDEX["TSICL_LONG"], dtype=np.int64)
    ck_by = {(c["arm"], c["held_source"]): c for c in ck["checkpoints"]}

    arm_results = {}
    per_row_pred = defaultdict(dict)
    for arm in ARMS:
        use = ARM_CONFIG[arm]
        q10 = np.zeros(89); q50 = np.zeros(89); q90 = np.zeros(89)
        harm = np.zeros(89); prot = np.zeros(89)
        thresholds = {}
        for src in DEV_SOURCES:
            sel = np.flatnonzero(np.array([r["source"] == src for r in rows]))
            if not len(sel):
                continue
            c_meta = ck_by[(arm, src)]
            state = torch.load(ROOT / c_meta["path"], map_location=device,
                               weights_only=False)
            net = ActionCritic(*use[:4]).to(device)
            net.load_state_dict(state["state_dict"])
            net.eval()
            mu = torch.from_numpy(state["tsfm_mu"]).to(device)
            sd = torch.from_numpy(state["tsfm_sd"]).to(device)
            with torch.no_grad():
                qq, hh, pp = net(
                    torch.from_numpy(seqs[sel]).to(device),
                    torch.from_numpy(structs[sel]).to(device),
                    (torch.from_numpy(eb[sel]).to(device) - mu) / sd,
                    (torch.from_numpy(ea[sel]).to(device) - mu) / sd,
                    torch.from_numpy(aidx[sel]).to(device),
                    torch.from_numpy(fidx[sel]).to(device))
            q10[sel] = qq[:, 0].cpu().numpy()
            q50[sel] = qq[:, 1].cpu().numpy()
            q90[sel] = qq[:, 2].cpu().numpy()
            harm[sel] = torch.sigmoid(hh).cpu().numpy()
            prot[sel] = torch.sigmoid(pp).cpu().numpy()
            thresholds[src] = c_meta["threshold"]

        # -- apply each window's own fold threshold -------------------------
        commit = np.zeros(89, dtype=bool)
        for i, r in enumerate(rows):
            thr = thresholds[r["source"]]
            if thr.get("no_calibrated_point"):
                continue
            commit[i] = (harm[i] < thr["tau_h"] and q10[i] > thr["delta"]
                         and prot[i] < thr["tau_p"])
        n_c = int(commit.sum())
        n_h = int(y_harm[commit].sum())
        n_b = int(y_bs[commit].sum())
        prev = float(y_harm.mean())
        ap = average_precision(harm, y_harm)
        frontier = _frontier(harm, y_harm, y_bs, 89)

        per_source = {}
        for src in sorted({r["source"] for r in rows}):
            m = np.array([r["source"] == src for r in rows])
            raw_bs = int(y_bs[m].sum())
            raw_h = int(y_harm[m].sum())
            c_m = m & commit
            per_source[src] = {
                "n_windows": int(m.sum()),
                "raw_tsicl_bs": raw_bs, "raw_tsicl_harmful": raw_h,
                "raw_tsicl_chr": raw_h / int(m.sum()),
                "n_commits": int(c_m.sum()),
                "bs_retained": int(y_bs[c_m].sum()),
                "harmful": int(y_harm[c_m].sum()),
                "chr": (float(y_harm[c_m].sum()) / int(c_m.sum())
                        if c_m.sum() else 0.0),
                "harmful_blocked": raw_h - int(y_harm[c_m].sum()),
                "bs_lost": raw_bs - int(y_bs[c_m].sum()),
            }
        # Operationalisation declared at decision time (the 4/6 count is
        # pre-registered, this predicate is not): a source is not degraded
        # if its harm rate does not rise above raw TS-ICL's and it still
        # retains at least one beneficial commit where one existed.
        not_degraded = [
            s for s, v in per_source.items()
            if v["chr"] <= v["raw_tsicl_chr"]
            and (v["bs_retained"] >= 1 or v["raw_tsicl_bs"] == 0)]

        gates = {
            "g1_harm_auroc": {"value": auroc(harm, y_harm),
                              "min": GATES["g1_harm_auroc_min"]},
            "g2_auprc_lift": {"value": (ap - prev) if ap is not None else None,
                              "auprc": ap, "prevalence": prev,
                              "min": GATES["g2_auprc_lift_min"]},
            "g3_bs_retained": {"value": n_b,
                               "min": GATES["g3_bs_retained_min"]},
            "g4_harmful": {"value": n_h, "max": GATES["g4_harmful_max"]},
            "g5_chr_cp95_upper": {
                "value": clopper_pearson_upper(n_h, n_c) if n_c else 1.0,
                "max": GATES["g5_chr_cp95_upper_max"]},
            "g6_frontier": {
                "dominates_raw_tsicl": len(_dominates(frontier,
                                                      REF_RAW_TSICL)) > 0,
                "dominates_mirage": len(_dominates(frontier,
                                                   REF_MIRAGE)) > 0,
                "n_dominating_points_vs_raw": len(
                    _dominates(frontier, REF_RAW_TSICL)),
                "n_dominating_points_vs_mirage": len(
                    _dominates(frontier, REF_MIRAGE))},
            "g7_sources_not_degraded": {
                "value": len(not_degraded), "sources": not_degraded,
                "min": GATES["g7_sources_not_degraded_min"],
                "predicate": ("chr <= raw TS-ICL chr on that source AND at "
                              "least one B&S commit retained where one was "
                              "available (declared at decision time; the 4/6 "
                              "count itself is pre-registered)")},
            "g8_no_source_identity": {
                "value": True,
                "evidence": ("source is not an input tensor anywhere in the "
                             "model (see MODEL inputs and "
                             "FORBIDDEN_INPUT_KEYS); every window is scored "
                             "by the fold whose training pool excluded its "
                             "source")},
        }
        passed = {
            "g1": (gates["g1_harm_auroc"]["value"] or 0) >= GATES["g1_harm_auroc_min"],
            "g2": (gates["g2_auprc_lift"]["value"] or 0) >= GATES["g2_auprc_lift_min"],
            "g3": n_b >= GATES["g3_bs_retained_min"],
            "g4": n_h <= GATES["g4_harmful_max"],
            "g5": gates["g5_chr_cp95_upper"]["value"] <= GATES["g5_chr_cp95_upper_max"],
            "g6": (gates["g6_frontier"]["dominates_raw_tsicl"]
                   and gates["g6_frontier"]["dominates_mirage"]),
            "g7": len(not_degraded) >= GATES["g7_sources_not_degraded_min"],
            "g8": True,
        }
        arm_results[arm] = {
            "n_commits": n_c, "n_bs_retained": n_b, "n_harmful": n_h,
            "n_abstained": 89 - n_c,
            "chr": (n_h / n_c) if n_c else 0.0,
            "chr_cp95_upper": clopper_pearson_upper(n_h, n_c) if n_c else 1.0,
            "bcov": n_b / 89,
            "harmful_blocked_of_14": 14 - n_h,
            "bs_lost_of_75": 75 - n_b,
            "harm_auroc": auroc(harm, y_harm), "harm_auprc": ap,
            "gates": gates, "gate_pass": passed,
            "all_gates_pass": all(passed.values()),
            "per_source": per_source,
            "thresholds": thresholds,
            "frontier": frontier,
        }
        for i, r in enumerate(rows):
            per_row_pred[arm][r["key"]] = {
                "q10": float(q10[i]), "q50": float(q50[i]),
                "q90": float(q90[i]), "harm_prob": float(harm[i]),
                "prot_prob": float(prot[i]), "committed": bool(commit[i])}
        print(f"[decide] {arm}: commits={n_c} bs={n_b}/75 harm={n_h}/14 "
              f"chr={arm_results[arm]['chr']:.4f} "
              f"cp95={arm_results[arm]['chr_cp95_upper']:.4f} "
              f"auroc={arm_results[arm]['harm_auroc']} "
              f"gates={sum(passed.values())}/8", flush=True)

    # -- paired bootstrap: full vs stat_only, and DRO vs ERM ----------------
    def utility(arm):
        """Per-window utility: +1 for a retained B&S commit, -1 for a
        harmful commit, 0 for an abstention or a neutral commit."""
        u = np.zeros(89)
        for i, r in enumerate(rows):
            p = per_row_pred[arm][r["key"]]
            if p["committed"]:
                u[i] = 1.0 if r["y_bs"] else (-1.0 if r["y_harmful"] else 0.0)
        return u

    bootstraps = {
        "full_vs_stat_only": _paired_bootstrap(utility("full_COUNTERACT"),
                                               utility("stat_only")),
        "full_vs_latent_only": _paired_bootstrap(utility("full_COUNTERACT"),
                                                 utility("TSFM_latent_only")),
        "full_vs_delta_only": _paired_bootstrap(utility("full_COUNTERACT"),
                                                utility("delta_only")),
        "groupdro_vs_erm": _paired_bootstrap(
            utility("full_COUNTERACT"), utility("full_without_GroupDRO")),
    }

    primary = arm_results["full_COUNTERACT"]
    out = {
        "phase": "v4.0 Phase 2.4 frozen-89 one-shot decision "
                 "(docs/v4_0_counteract_preregistration.md §4 gates, §11.3 F10)",
        "seed": SEED,
        "n_windows": 89,
        "frozen_labels": {"n_bs": 75, "n_harmful": 14,
                          "source": "results/v39_longgap_probe.json "
                                    "proposer_tables.tsicl"},
        "references": {"raw_tsicl": REF_RAW_TSICL, "v39_mirage": REF_MIRAGE},
        "gate_thresholds": GATES,
        "arms": arm_results,
        "primary_arm": "full_COUNTERACT",
        "primary_all_gates_pass": primary["all_gates_pass"],
        "paired_bootstrap": bootstraps,
        "checkpoint_freeze_verified": True,
        "runtime_sec": time.time() - t0,
    }
    with OUT_DECISION.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    with OUT_DECISION_ROWS.open("w", encoding="utf-8") as f:
        for r in rows:
            rec = dict(r)
            for arm in ARMS:
                rec[arm] = per_row_pred[arm][r["key"]]
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    print(f"[decide] primary all_gates_pass="
          f"{primary['all_gates_pass']} ({time.time() - t0:.0f}s)", flush=True)
    print("___V40_DECIDE_DONE___", flush=True)
    return 0


STAGES = {"audit": stage_audit, "features": stage_features,
          "verify-cache": stage_verify_cache, "train": stage_train,
          "decide": stage_decide}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    args = ap.parse_args()
    return STAGES[args.stage]()


if __name__ == "__main__":
    sys.exit(main())
