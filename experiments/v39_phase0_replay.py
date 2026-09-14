"""v3.9 Phase 0: MIRAGE-TS fast integration replay and target-gap budget.

Pre-registered in ``docs/v3_9_mirage_preregistration.md`` §2. CPU-only,
API 0. Read-only against every frozen artifact.

FACT_SHORT (frozen in §2): raw-NaN runs of length 1-3 only, a finite anchor
on both sides, linear interpolation, observed finite support strictly
unchanged; raw NaN takes priority over materialised-shape DESPIKE/DENOISE
(arm D is FACT_SHORT-first, arm E is PICS_non_IMPUTE-first). FACT_SHORT
candidate labels are reused from ``results/v38_explicit_impute_records.jsonl``
(wide tier, cap 16); integrity gate 3 proves per-window, by output hash, that
FACT_SHORT (max run 3) and the wide tier are identical on this corpus because
every raw-NaN run length is in {1,2,3} u {25..63}.

Arms (frozen 771-window frame; removed actions stay in the frame as KEEP
placeholders, so the denominator never moves):

  A  PICS_joint_relabel  incumbent replay (must match the frozen record
     within 1e-9)
  B  PICS_non_IMPUTE  the same fitted PICS models as A, with every IMPUTE
     candidate removed from the decision pools; first-commit then continues
     to the next non-IMPUTE candidate, and windows left without candidates
     KEEP
  C  FACT_SHORT only  commit wherever the operator is applicable (>= 1
     certified run), KEEP elsewhere
  D  FACT_SHORT-first + PICS_non_IMPUTE
  E  PICS_non_IMPUTE-first + FACT_SHORT
  F  unrestricted oracle over (full existing pool + FACT_SHORT), RESEGMENT
     closed -- target-label headroom only, never a deployment rule

The five reported quantities per arm (v3.9 reporting contract, §1):
applicability/proposal coverage, action-conditional B&S precision,
action-conditional CHR, bcov, abstention rate -- plus gain/pme/damage and
commit counts.

Usage:
    python experiments/v39_phase0_replay.py --digest /tmp/v39_p0_a.json
    python experiments/v39_phase0_replay.py \
        --digest-a /tmp/v39_p0_a.json --digest-b /tmp/v39_p0_b.json
"""

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v33_compare_arms as v33  # noqa: E402
import v38_oracle_replay as v38replay  # noqa: E402
import v38_explicit_impute_probe as v38p  # noqa: E402
from v38_impute_mask_audit import (  # noqa: E402
    rebuild_corpus, verify_against_manifest, raw_nan_mask,
    finite_flatline_mask, window_layer,
)
from v33_labels import hash_array  # noqa: E402
from introact_ts.contextual_shield import EPISODE_FAMILY_ORDER  # noqa: E402
from introact_ts.pics import PICS_JOINT_FEATURES  # noqa: E402
from v32_compare_arms import PROTECTED_STRATA  # noqa: E402

ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
MANIFEST_PATH = ROOT / "results" / "p0_corpus_manifest_a.json"
FROZEN_V33 = ROOT / "results" / "v33_clean_rerun.json"
REPLAY_PATH = ROOT / "results" / "v38_oracle_replay.json"
MASK_RECORDS = ROOT / "results" / "v38_impute_mask_records.jsonl"
EXPLICIT_RECORDS = ROOT / "results" / "v38_explicit_impute_records.jsonl"
EXPLICIT_PROBE = ROOT / "results" / "v38_explicit_impute_probe.json"
OUT_JSON = ROOT / "results" / "v39_phase0_replay.json"
OUT_RECORDS = ROOT / "results" / "v39_phase0_records.jsonl"
OUT_BUDGET = ROOT / "results" / "v39_target_budget.json"
OUT_MANIFEST = ROOT / "results" / "v39_phase0_manifest.json"

TOL = 1e-9
HARM_LOSS = 0.03
GAIN_EPS = 1e-9
#: FACT_SHORT: certified raw-NaN runs of length 1-3 (§2, frozen).
FACT_SHORT_MAX_GAP = 3
FACT_FAMILY = "FACT_SHORT"
#: v3.8 actual-NaN layers (actual_nan_only + mixed).
ACTUAL_NAN_LAYERS = v38p.ACTUAL_NAN_LAYERS
#: Formal v3.9 targets (§6); the budget is computed against these.
TARGETS = {"bcov": 0.30, "gain": 0.10, "chr": 0.10, "pme": 0.0055,
           "damage": 0.0402}
#: Expected FACT_SHORT fill counts on this corpus (v3.8 wide tier, frozen
#: facts from the v3.8 probe: 88 filled windows, 76 B&S, 12 harmful).
EXPECTED_FILL = {"n_windows": 88, "n_bs": 76, "n_harmful": 12}

ARM_NAMES = ("A_pics_joint_relabel", "B_pics_non_impute", "C_fact_short_only",
             "D_fact_short_first", "E_pics_non_impute_first",
             "F_unrestricted_oracle")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkey(params):
    return json.dumps(params, sort_keys=True)


# -- pure helpers (unit-tested locally) -----------------------------------------


def placeholder_row(uid, meta):
    """KEEP placeholder: keeps a candidate-less window in the 771 frame.
    Family KEEP is not in EPISODE_FAMILY_ORDER, so first-commit replay skips
    it and the window stays a no-commit."""
    return {"sample_uid": uid, "dataset": meta["dataset"],
            "stratum": meta["stratum"], "true_kind": meta["true_kind"],
            "corrupted_hash": meta["corrupted_hash"],
            "family": "KEEP", "rung": "keep", "params": {}}


def with_keep_placeholders(rows, uids, uid_meta):
    """rows + one KEEP placeholder per uncovered uid (sorted, deterministic)."""
    covered = {r["sample_uid"] for r in rows}
    return list(rows) + [placeholder_row(u, uid_meta[u])
                         for u in sorted(set(uids) - covered)]


def resolve_priority(fact_pick, pics_pick, order):
    """D/E priority resolution for one window.

    ``fact_pick``/``pics_pick`` are candidate-row dicts or None. Returns
    (winner, pick) with winner in {"FACT_SHORT", "PICS_non_IMPUTE", "KEEP"}.
    ``order`` is "fact_first" (arm D) or "pics_first" (arm E).
    """
    if order == "fact_first":
        if fact_pick is not None:
            return "FACT_SHORT", fact_pick
        if pics_pick is not None:
            return "PICS_non_IMPUTE", pics_pick
        return "KEEP", None
    if order == "pics_first":
        if pics_pick is not None:
            return "PICS_non_IMPUTE", pics_pick
        if fact_pick is not None:
            return "FACT_SHORT", fact_pick
        return "KEEP", None
    raise ValueError(f"unknown order {order!r}")


def oracle_committed(rows, allowed):
    """v3.3 unrestricted-oracle rule with per-uid picks kept: per window, max
    true_repair_gain among beneficial_and_safe rows whose family is allowed
    (RESEGMENT is never allowed). Mirrors v38p.unrestricted_oracle."""
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["sample_uid"]].append(r)
    out = {}
    for uid, rs in by_uid.items():
        bs = [r for r in rs
              if r["beneficial_and_safe"] and r["family"] in allowed]
        if bs:
            best = max(bs, key=lambda r: r["true_repair_gain"])
            out[uid] = (best, rs.index(best), "oracle", None)
        else:
            out[uid] = None
    return out


def harmful_of(pick_row):
    return bool(pick_row is not None and pick_row["true_loss"] > HARM_LOSS)


def _pick_id(pick):
    """Hashable identity of a committed pick (None for KEEP)."""
    if pick is None:
        return None
    row = pick[0]
    return (row["family"], row.get("rung"), _pkey(row["params"]))


def target_budget(stats, targets, n_cont, n_frame, prot_n):
    """Distance-to-target arithmetic from a baseline arm's pooled stats.

    stats: improved (B&S contaminated windows), gain_sum (summed repair gain
    over contaminated windows), committed, harmful, prot_edit, loss_sum.
    Pure function of its arguments; unit-tested locally.
    """
    b_req = max(0, int(math.ceil(targets["bcov"] * n_cont - GAIN_EPS))
                - stats["improved"])
    gain_deficit = max(0.0, targets["gain"] * n_cont - stats["gain_sum"])
    c0, h0 = stats["committed"], stats["harmful"]
    # adding b safe commits and h harmful ones keeps CHR <= target iff
    # (h0 + h) / (c0 + b + h) <= target  =>  h <= (t*(c0+b) - h0) / (1 - t)
    t = targets["chr"]
    h_max_at_b_req = int(math.floor((t * (c0 + b_req) - h0) / (1.0 - t)
                                    + GAIN_EPS))
    # safe commits needed to reach the CHR target with zero new harmful
    b_to_fix_chr_alone = (max(0, int(math.ceil(h0 / t - c0 - GAIN_EPS)))
                          if h0 else 0)
    pme_budget_edits = int(math.floor(targets["pme"] * prot_n + GAIN_EPS))
    return {
        "baseline": dict(stats),
        "n_contaminated": n_cont,
        "n_frame": n_frame,
        "n_protected": prot_n,
        "targets": dict(targets),
        "new_beneficial_commits_needed_for_bcov": b_req,
        "gain_deficit_sum": gain_deficit,
        "gain_deficit_mean_per_contaminated_window":
            gain_deficit / n_cont if n_cont else None,
        "required_mean_gain_per_new_beneficial_commit":
            (gain_deficit / b_req if b_req
             else (0.0 if gain_deficit <= GAIN_EPS else None)),
        "max_new_harmful_commits_at_required_beneficial": h_max_at_b_req,
        "new_safe_commits_needed_for_chr_with_zero_new_harmful":
            b_to_fix_chr_alone,
        "pme_protected_edit_budget": pme_budget_edits,
        "pme_headroom_edits": pme_budget_edits - stats["prot_edit"],
        "pme_note": ("negative headroom means the pme target cannot be met "
                     "by adding commits; protected edits must be removed"),
        "damage_loss_budget_sum": targets["damage"] * n_frame,
        "damage_headroom_sum": targets["damage"] * n_frame
                               - stats["loss_sum"],
    }


def arm_report(met, picks, n_frame, n_proposed, n_applicable=None):
    """The v3.9 five-quantity report plus gain/pme/damage/commit counts."""
    committed = int(met["committed"])
    harmful = sum(1 for p in picks.values() if p and harmful_of(p[0]))
    return {
        "n_windows": int(met["n_windows"]),
        "proposal_coverage": n_proposed / n_frame,
        "applicability_coverage": (n_applicable if n_applicable is not None
                                   else n_proposed) / n_frame,
        "n_proposed_windows": int(n_proposed),
        "n_applicable_windows": int(n_applicable if n_applicable is not None
                                    else n_proposed),
        "action_conditional_bs_precision":
            (met["beneficial_commits"] / committed) if committed else None,
        "action_conditional_chr": float(met["conditional_harm_rate"]),
        "bcov": float(met["beneficial_coverage"]),
        "abstention_rate": 1.0 - float(met["commit_rate"]),
        "gain": float(met["mean_repair_gain_contaminated"]),
        "pme": float(met["protected_mis_edit_rate"]),
        "damage": float(met["damage"]),
        "conditional_mean_loss": float(met["conditional_mean_loss"]),
        "committed": committed,
        "commit_rate": float(met["commit_rate"]),
        "beneficial_commits": int(met["beneficial_commits"]),
        "harmful_commits": harmful,
        "commit_by_family": dict(Counter(
            p[0]["family"] for p in picks.values() if p)),
    }


def slim_decisions(picks_by_arm):
    """Deterministic slim decision table for the two-process digest."""
    slim = []
    for arm in sorted(picks_by_arm):
        for uid in sorted(picks_by_arm[arm]):
            got = picks_by_arm[arm][uid]
            row = got[0] if got else None
            slim.append({
                "arm": arm, "uid": uid,
                "family": row["family"] if row else "KEEP",
                "rung": row.get("rung") if row else "keep",
                "params_key": _pkey(row["params"]) if row else "{}",
                "gain": (round(float(row["true_repair_gain"]), 12)
                         if row else 0.0),
                "loss": round(float(row["true_loss"]), 12) if row else 0.0,
            })
    return slim


def digest_blob(slim):
    """sha256 over the canonical slim decision table."""
    blob = json.dumps(slim, sort_keys=True).encode("utf-8")
    return {"n_decisions": len(slim),
            "sha256": hashlib.sha256(blob).hexdigest()}


def decision_records(arm, picks, uids, uid_meta, uid_layer):
    """Per-window decision ledger rows for one arm."""
    out = []
    for uid in sorted(uids):
        got = picks.get(uid)
        row = got[0] if got else None
        meta = uid_meta[uid]
        out.append({
            "sample_uid": uid, "arm": arm,
            "dataset": meta["dataset"], "stratum": meta["stratum"],
            "true_kind": meta["true_kind"],
            "window_layer": uid_layer.get(uid),
            "committed": row is not None,
            "family": row["family"] if row else "KEEP",
            "rung": row.get("rung") if row else "keep",
            "params_key": _pkey(row["params"]) if row else "{}",
            "episode_position": int(got[1]) if got else None,
            "decision_reason": got[2] if got else "keep_placeholder",
            "beneficial": bool(row["beneficial"]) if row else False,
            "beneficial_and_safe": (bool(row["beneficial_and_safe"])
                                    if row else False),
            "harmful": harmful_of(row),
            "true_repair_gain": (float(row["true_repair_gain"])
                                 if row else 0.0),
            "true_loss": float(row["true_loss"]) if row else 0.0,
            "keep_placeholder": row is None,
        })
    return out


# -- main -------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", default=None,
                    help="digest-only mode: run everything, write the slim "
                         "decision digest here, do not touch results/")
    ap.add_argument("--digest-a", default=None)
    ap.add_argument("--digest-b", default=None)
    args = ap.parse_args()

    t0 = time.time()

    # Gate 0: the v3.8 replay this phase builds on must have passed.
    rep = json.load(REPLAY_PATH.open(encoding="utf-8"))
    gate0 = {"pass": bool(rep.get("all_replays_pass")),
             "source": REPLAY_PATH.name}
    print(f"[gate0 v38 replay] pass={gate0['pass']}", flush=True)
    if not gate0["pass"]:
        print("[FATAL] v3.8 replay gate failed; v3.9 Phase 0 void", flush=True)
        return 1

    rows = v33._load_rows(str(ROWS_PATH))
    real = [r for r in rows if not r["dataset"].startswith("ood:")]
    real_uids = sorted({r["sample_uid"] for r in real})
    uid_meta = {}
    for r in real:
        uid_meta.setdefault(r["sample_uid"], {
            "dataset": r["dataset"], "stratum": r["stratum"],
            "true_kind": r["true_kind"],
            "corrupted_hash": r["corrupted_hash"]})
    n_frame = len(real_uids)
    print(f"{len(real)} real candidates, {n_frame} windows", flush=True)
    assert n_frame == 771, "frozen frame must be 771 real windows"

    # Rebuild + verify the raw corpus (same discipline as v3.8).
    t1 = time.time()
    recs, _dropped = rebuild_corpus()
    manifest = json.load(MANIFEST_PATH.open(encoding="utf-8"))
    uid_gate = verify_against_manifest(recs, manifest)
    print(f"[gate corpus] pass={uid_gate['pass']} "
          f"({len(recs)} rebuilt in {time.time() - t1:.1f}s)", flush=True)
    if not uid_gate["pass"]:
        return 1
    rebuilt = {r["sample_uid"]: r for r in recs}
    uid_layer = {uid: window_layer(raw_nan_mask(r["series"]),
                                   finite_flatline_mask(r["series"]))
                 for uid, r in rebuilt.items()}

    # v3.8 artifacts.
    mask_recs = [json.loads(l) for l in MASK_RECORDS.open(encoding="utf-8")]
    explicit = [json.loads(l) for l in EXPLICIT_RECORDS.open(encoding="utf-8")]
    wide_by_uid = {r["sample_uid"]: r for r in explicit
                   if r["variant"] == "wide"}
    probe = json.load(EXPLICIT_PROBE.open(encoding="utf-8"))
    p0_uids = sorted(wide_by_uid)
    print(f"[v38 artifacts] {len(mask_recs)} mask records, "
          f"{len(p0_uids)} explicit-probe windows", flush=True)

    # Gate 3: FACT_SHORT (max run 3) recomputed from the RAW corpus must be
    # bit-identical to the v3.8 wide tier (cap 16) on every probe window, and
    # the filled-window set must reproduce 88/76/12 exactly.
    t2 = time.time()
    hash_mismatch, layer_mismatch = [], []
    fact_applicable = {}
    for uid in p0_uids:
        x = np.asarray(rebuilt[uid]["series"], dtype=np.float64)
        res3 = v38p.impute_explicit_linear(x, max_gap=FACT_SHORT_MAX_GAP)
        fact_applicable[uid] = bool(res3["applicable"])
        if hash_array(res3["series"]) != wide_by_uid[uid]["output_hash"]:
            hash_mismatch.append(uid)
        if wide_by_uid[uid]["layer"] != uid_layer[uid]:
            layer_mismatch.append(uid)
    actual_nan_uids = sorted(u for u in p0_uids
                             if uid_layer[u] in ACTUAL_NAN_LAYERS)
    ref_filled = {u for u in actual_nan_uids if wide_by_uid[u]["n_filled"] > 0}
    got_filled = {u for u in actual_nan_uids if fact_applicable[u]}
    bs_uids = {u for u in got_filled
               if wide_by_uid[u]["labels"]["beneficial_and_safe"]}
    harm_uids = {u for u in got_filled
                 if wide_by_uid[u]["labels"]["true_loss"] > HARM_LOSS}
    wl = probe["abstain_reasons"]["wide"]["window_level"]
    gate3 = {
        "n_windows_checked": len(p0_uids),
        "n_output_hash_mismatch_vs_wide": len(hash_mismatch),
        "hash_mismatch_uids": hash_mismatch[:20],
        "n_layer_mismatch_vs_v38": len(layer_mismatch),
        "n_actual_nan_windows": len(actual_nan_uids),
        "n_filled": len(got_filled), "n_bs": len(bs_uids),
        "n_harmful": len(harm_uids),
        "filled_set_matches_v38_wide": got_filled == ref_filled,
        "v38_probe_window_level": wl,
        "expected": dict(EXPECTED_FILL),
        "gap_length_note": ("corpus raw-NaN run lengths are {1,2,3} u "
                            "{25..63}, so max_gap=3 and max_gap=16 certify "
                            "exactly the same runs; any hash mismatch above "
                            "would falsify that distributional claim"),
        "pass": bool(not hash_mismatch and not layer_mismatch
                     and got_filled == ref_filled
                     and len(got_filled) == EXPECTED_FILL["n_windows"]
                     and len(bs_uids) == EXPECTED_FILL["n_bs"]
                     and len(harm_uids) == EXPECTED_FILL["n_harmful"]
                     and wl.get("full_fill") == EXPECTED_FILL["n_windows"]),
    }
    print(f"[gate3 FACT_SHORT==wide] pass={gate3['pass']} filled="
          f"{len(got_filled)} bs={len(bs_uids)} harm={len(harm_uids)} "
          f"({time.time() - t2:.1f}s)", flush=True)

    # FACT_SHORT candidate rows (labels reused from the hash-verified wide
    # tier; family renamed, max_gap recorded as 3).
    fact_rows = []
    for uid in actual_nan_uids:
        w = wide_by_uid[uid]
        lab = w["labels"]
        fact_rows.append({
            "sample_uid": uid, "dataset": w["dataset"],
            "stratum": w["stratum"], "true_kind": w["true_kind"],
            "corrupted_hash": w["corrupted_hash"],
            "family": FACT_FAMILY, "rung": "fact_short",
            "params": {"method": "explicit_linear",
                       "max_gap": FACT_SHORT_MAX_GAP},
            "true_loss": float(lab["true_loss"]),
            "true_repair_gain": float(lab["true_repair_gain"]),
            "beneficial": float(lab["beneficial"]),
            "beneficial_and_safe": float(lab["beneficial_and_safe"]),
            "output_hash": w["output_hash"],
        })
    fact_by_uid = {r["sample_uid"]: r for r in fact_rows}

    # Arms A and B: one PICS fit per LODO fold, two decision pools.
    frozen_v33 = json.load(FROZEN_V33.open(encoding="utf-8"))
    frozen_arm = frozen_v33["arms"]["PICS_joint_relabel"]
    datasets = sorted({r["dataset"] for r in real})
    committed_A, committed_B = {}, {}
    t3 = time.time()
    for test_ds in datasets:
        train, cal, test = v33._split(real, test_ds)
        model = v33._PICSArmX(PICS_JOINT_FEATURES)
        model.fit(train, cal)
        committed_A.update(v33._decisions(test, model))
        test_b = [r for r in test if r["family"] != "IMPUTE"]
        committed_B.update(v33._decisions(test_b, model))
        print(f"[fold {test_ds}] A commits="
              f"{sum(1 for u, p in committed_A.items() if p and uid_meta[u]['dataset'] == test_ds)} "
              f"B commits="
              f"{sum(1 for u, p in committed_B.items() if p and uid_meta[u]['dataset'] == test_ds)}",
              flush=True)
    print(f"[arms A/B] fitted 6 folds in {time.time() - t3:.1f}s", flush=True)

    metA = v33._episode_metrics(real, committed_A)
    gate1 = v38replay.compare_arm_metrics(metA, frozen_arm)
    print(f"[gate1 incumbent replay] pass={gate1['pass']} "
          f"max_abs_diff={gate1['max_abs_diff']:.3e}", flush=True)

    real_nonimpute = [r for r in real if r["family"] != "IMPUTE"]
    rows_B = with_keep_placeholders(real_nonimpute, real_uids, uid_meta)
    metB = v33._episode_metrics(rows_B, committed_B)

    # Arm C: FACT_SHORT only.
    picks_C = {uid: ((fact_by_uid[uid], 0, "fact_short_applicable", None)
                     if uid in fact_by_uid and fact_applicable.get(uid)
                     else None)
               for uid in real_uids}
    rows_C = with_keep_placeholders(fact_rows, real_uids, uid_meta)
    metC = v33._episode_metrics(rows_C, picks_C)

    # Arms D/E: priority composition over (PICS_non_IMPUTE + FACT_SHORT).
    rows_DE = rows_B + fact_rows
    picks_D, picks_E = {}, {}
    for uid in real_uids:
        fact_pick = (fact_by_uid[uid]
                     if uid in fact_by_uid and fact_applicable.get(uid)
                     else None)
        b = committed_B.get(uid)
        pics_pick = b[0] if b else None
        win_d, pick_d = resolve_priority(fact_pick, pics_pick, "fact_first")
        win_e, pick_e = resolve_priority(fact_pick, pics_pick, "pics_first")
        picks_D[uid] = ((pick_d, 0, f"priority_{win_d.lower()}", None)
                        if pick_d is not None else None)
        picks_E[uid] = ((pick_e, 0, f"priority_{win_e.lower()}", None)
                        if pick_e is not None else None)
    metD = v33._episode_metrics(rows_DE, picks_D)
    metE = v33._episode_metrics(rows_DE, picks_E)

    # Arm F: unrestricted oracle over the full pool + FACT_SHORT.
    allowed_F = tuple(EPISODE_FAMILY_ORDER) + (FACT_FAMILY,)
    rows_F = list(real) + fact_rows
    metF = v38p.unrestricted_oracle(rows_F, allowed_F)
    picks_F = oracle_committed(rows_F, allowed_F)
    metF_xcheck = v33._episode_metrics(rows_F, picks_F)
    f_xcheck_ok = all(
        abs(float(metF_xcheck[k]) - float(metF[k])) < TOL
        for k in ("beneficial_coverage", "mean_repair_gain_contaminated",
                  "conditional_harm_rate", "protected_mis_edit_rate",
                  "damage"))
    print(f"[arm F] bcov={metF['beneficial_coverage']:.4f} "
          f"xcheck={f_xcheck_ok}", flush=True)

    picks_by_arm = {"A_pics_joint_relabel": committed_A,
                    "B_pics_non_impute": committed_B,
                    "C_fact_short_only": picks_C,
                    "D_fact_short_first": picks_D,
                    "E_pics_non_impute_first": picks_E,
                    "F_unrestricted_oracle": picks_F}
    mets = {"A_pics_joint_relabel": metA, "B_pics_non_impute": metB,
            "C_fact_short_only": metC, "D_fact_short_first": metD,
            "E_pics_non_impute_first": metE, "F_unrestricted_oracle": metF}

    # Gate 2: every arm keeps the frozen 771-window denominator.
    gate2 = {"n_frame": n_frame,
             "per_arm_n_windows": {a: int(mets[a]["n_windows"])
                                   for a in ARM_NAMES},
             "n_keep_placeholder_rows": {
                 "B": len(rows_B) - len(real_nonimpute),
                 "C": len(rows_C) - len(fact_rows),
                 "D_E": len(rows_DE) - len(real_nonimpute) - len(fact_rows),
                 "F": 0},
             "pass": bool(all(int(mets[a]["n_windows"]) == n_frame
                              for a in ARM_NAMES))}
    print(f"[gate2 frame 771] pass={gate2['pass']}", flush=True)

    # Per-arm reports.
    uids_with_episode_candidate = len({r["sample_uid"] for r in real
                                       if r["family"] in EPISODE_FAMILY_ORDER})
    uids_with_nonimpute = len({r["sample_uid"] for r in real_nonimpute})
    uids_pool_DE = len({r["sample_uid"] for r in real_nonimpute}
                       | set(fact_by_uid))
    n_prop = {"A_pics_joint_relabel": uids_with_episode_candidate,
              "B_pics_non_impute": uids_with_nonimpute,
              "C_fact_short_only": len(actual_nan_uids),
              "D_fact_short_first": uids_pool_DE,
              "E_pics_non_impute_first": uids_pool_DE,
              "F_unrestricted_oracle": len(real_uids)}
    n_app = {"C_fact_short_only": len(got_filled)}
    reports = {a: arm_report(mets[a], picks_by_arm[a], n_frame, n_prop[a],
                             n_app.get(a)) for a in ARM_NAMES}
    reports["F_unrestricted_oracle"]["two_path_xcheck_pass"] = \
        bool(f_xcheck_ok)
    for a in ARM_NAMES:
        r = reports[a]
        print(f"  {a:26s} prop={r['proposal_coverage']:.3f} "
              f"bs_prec={r['action_conditional_bs_precision']} "
              f"CHR={r['action_conditional_chr']:.4f} "
              f"bcov={r['bcov']:.4f} abst={r['abstention_rate']:.4f} "
              f"gain={r['gain']:.4f} commits={r['committed']}", flush=True)

    # Decomposition of the incumbent's commits.
    rec_index = {(r["sample_uid"], r["rung"], r["params_key"]): r
                 for r in mask_recs}
    a_rows = [p[0] for p in committed_A.values() if p]
    a_impute = [r for r in a_rows if r["family"] == "IMPUTE"]
    decomposition = {
        "A_pics_commits": {
            "n_commits": len(a_rows),
            "by_family": dict(Counter(r["family"] for r in a_rows)),
            "by_source": dict(Counter(r["dataset"] for r in a_rows)),
            "by_window_layer": dict(Counter(
                uid_layer.get(r["sample_uid"], "not_rebuilt")
                for r in a_rows)),
            "impute_by_mask_origin": dict(Counter(
                (rec_index.get((r["sample_uid"], r["rung"], _pkey(r["params"])))
                 or {}).get("mask_origin", "unmatched") for r in a_impute)),
            "harmful_by_family": dict(Counter(
                r["family"] for r in a_rows if harmful_of(r))),
            "harmful_by_source": dict(Counter(
                r["dataset"] for r in a_rows if harmful_of(r))),
            "harmful_impute_by_mask_origin": dict(Counter(
                (rec_index.get((r["sample_uid"], r["rung"], _pkey(r["params"])))
                 or {}).get("mask_origin", "unmatched")
                for r in a_impute if harmful_of(r))),
        },
        "B_pics_non_impute": {
            "committed": reports["B_pics_non_impute"]["committed"],
            "beneficial_commits":
                reports["B_pics_non_impute"]["beneficial_commits"],
            "harmful_commits": reports["B_pics_non_impute"]["harmful_commits"],
            "gain": reports["B_pics_non_impute"]["gain"],
            "bcov": reports["B_pics_non_impute"]["bcov"],
            "chr": reports["B_pics_non_impute"]["action_conditional_chr"],
            "by_family":
                reports["B_pics_non_impute"]["commit_by_family"],
            "n_impute_commits_removed_vs_A":
                sum(1 for r in a_rows if r["family"] == "IMPUTE"),
        },
    }

    # FACT_SHORT <-> PICS overlap and first-commit conflicts.
    conflicts, overlap_a_impute, overlap_a_any = [], [], []
    for uid in sorted(got_filled):
        fact = fact_by_uid[uid]
        a = committed_A.get(uid)
        b = committed_B.get(uid)
        if a and a[0]["family"] == "IMPUTE":
            overlap_a_impute.append(uid)
        if a:
            overlap_a_any.append(uid)
        if b:
            prow = b[0]
            conflicts.append({
                "sample_uid": uid, "dataset": fact["dataset"],
                "stratum": fact["stratum"],
                "fact_short": {
                    "gain": float(fact["true_repair_gain"]),
                    "loss": float(fact["true_loss"]),
                    "beneficial_and_safe": bool(fact["beneficial_and_safe"]),
                    "harmful": harmful_of(fact)},
                "pics_non_impute": {
                    "family": prow["family"], "rung": prow["rung"],
                    "params_key": _pkey(prow["params"]),
                    "gain": float(prow["true_repair_gain"]),
                    "loss": float(prow["true_loss"]),
                    "beneficial_and_safe": bool(prow["beneficial_and_safe"]),
                    "harmful": harmful_of(prow)},
                "winner_D_fact_first": FACT_FAMILY,
                "winner_E_pics_first": "PICS_non_IMPUTE",
            })
    conflict_summary = {
        "n_fact_applicable": len(got_filled),
        "n_overlap_with_A_any_commit": len(overlap_a_any),
        "n_overlap_with_A_IMPUTE_commit": len(overlap_a_impute),
        "n_conflict_with_B_commit": len(conflicts),
        "conflict_fact_bs": sum(1 for c in conflicts
                                if c["fact_short"]["beneficial_and_safe"]),
        "conflict_fact_harmful": sum(1 for c in conflicts
                                     if c["fact_short"]["harmful"]),
        "conflict_pics_bs": sum(1 for c in conflicts
                                if c["pics_non_impute"]["beneficial_and_safe"]),
        "conflict_pics_harmful": sum(1 for c in conflicts
                                     if c["pics_non_impute"]["harmful"]),
        "conflicts": conflicts,
        "overlap_A_impute_uids": overlap_a_impute,
    }

    # D vs E comparison.
    d_vs_e = {"D": reports["D_fact_short_first"],
              "E": reports["E_pics_non_impute_first"],
              "delta_D_minus_E": {
                  k: (reports["D_fact_short_first"][k]
                      - reports["E_pics_non_impute_first"][k])
                  for k in ("bcov", "gain", "action_conditional_chr",
                            "pme", "damage", "committed",
                            "beneficial_commits", "harmful_commits")},
              "n_windows_differ": sum(
                  1 for uid in real_uids
                  if _pick_id(picks_D[uid]) != _pick_id(picks_E[uid]))}

    # Target budget from the better of D/E (bcov, then gain, then lower CHR).
    key_d = (reports["D_fact_short_first"]["bcov"],
             reports["D_fact_short_first"]["gain"],
             -reports["D_fact_short_first"]["action_conditional_chr"])
    key_e = (reports["E_pics_non_impute_first"]["bcov"],
             reports["E_pics_non_impute_first"]["gain"],
             -reports["E_pics_non_impute_first"]["action_conditional_chr"])
    baseline_arm = "D_fact_short_first" if key_d >= key_e \
        else "E_pics_non_impute_first"
    base_picks = picks_by_arm[baseline_arm]
    base_met = mets[baseline_arm]
    n_cont = sum(1 for u in real_uids
                 if uid_meta[u]["stratum"] == "contaminated")
    prot_n = sum(1 for u in real_uids
                 if uid_meta[u]["stratum"] in PROTECTED_STRATA)
    base_stats = {
        "improved": sum(1 for u, p in base_picks.items()
                        if p and uid_meta[u]["stratum"] == "contaminated"
                        and p[0]["beneficial"]),
        "gain_sum": float(base_met["mean_repair_gain_contaminated"]) * n_cont,
        "committed": int(base_met["committed"]),
        "harmful": sum(1 for p in base_picks.values()
                       if p and harmful_of(p[0])),
        "prot_edit": int(round(float(base_met["protected_mis_edit_rate"])
                               * prot_n)),
        "loss_sum": float(base_met["damage"]) * n_frame,
    }
    budget = target_budget(base_stats, TARGETS, n_cont, n_frame, prot_n)
    budget.update({
        "baseline_arm": baseline_arm,
        "baseline_selection_rule": ("higher bcov, then higher gain, then "
                                    "lower action-conditional CHR"),
        "baseline_report": reports[baseline_arm],
        "oracle_headroom_F": {
            "report": reports["F_unrestricted_oracle"],
            "note": ("target-label oracle: headroom measurement only, never "
                     "a deployment rule (§2)"),
        },
    })

    # Integrity gates 1-4.
    slim = slim_decisions(picks_by_arm)
    dig = digest_blob(slim)
    gate4 = {"in_process_sha256": dig["sha256"], "pass": False}
    if args.digest_a and args.digest_b:
        da = json.load(open(args.digest_a, encoding="utf-8"))
        db = json.load(open(args.digest_b, encoding="utf-8"))
        gate4.update({
            "process_a_sha256": da["sha256"],
            "process_b_sha256": db["sha256"],
            "a_equals_b": da["records"] == db["records"],
            "a_equals_in_process": da["records"] == slim,
            "pass": bool(da["records"] == db["records"] == slim
                         and da["sha256"] == db["sha256"] == dig["sha256"]),
        })
    else:
        gate4["note"] = ("digest files not supplied; pass stays False until "
                         "two independent process digests are compared")
    print(f"[gate4 two-process digest] pass={gate4['pass']}", flush=True)

    gates = {
        "gate0_v38_replay_passed": gate0,
        "gate1_incumbent_replay_1e-9": {
            "pass": bool(gate1["pass"]),
            "max_abs_diff": gate1["max_abs_diff"],
            "detail": gate1},
        "gate2_frame_771_fixed": gate2,
        "gate3_fact_short_equals_v38_88_76_12": gate3,
        "gate4_two_process_digest_identical": gate4,
    }
    all_pass = all(g["pass"] for g in gates.values())

    if args.digest:
        payload = {"phase": "v3.9 Phase 0 digest", "n_decisions": len(slim),
                   "sha256": dig["sha256"], "records": slim,
                   "runtime_sec": time.time() - t0}
        with open(args.digest, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
        print(f"[digest] sha256={dig['sha256']} -> {args.digest}", flush=True)
        print("___V39_PHASE0_DIGEST_DONE___", flush=True)
        return 0

    with OUT_RECORDS.open("w", encoding="utf-8") as f:
        for a in ARM_NAMES:
            for rec in decision_records(a, picks_by_arm[a], real_uids,
                                        uid_meta, uid_layer):
                f.write(json.dumps(rec, sort_keys=True) + "\n")
    print(f"[records] {n_frame * len(ARM_NAMES)} -> {OUT_RECORDS.name}",
          flush=True)

    with OUT_BUDGET.open("w", encoding="utf-8") as f:
        json.dump(budget, f, indent=1, ensure_ascii=False, default=str)

    out = {
        "phase": "v3.9 Phase 0: MIRAGE-TS fast integration replay and "
                 "target-gap budget (docs/v3_9_mirage_preregistration.md §2)",
        "definitions": {
            "fact_short": ("raw-NaN runs of length 1-3 only, finite anchors "
                           "on both sides, linear interpolation, observed "
                           "finite support strictly unchanged; labels reused "
                           "from the v3.8 wide tier after the per-window "
                           "output-hash equivalence proof (gate 3)"),
            "arm_B": ("the same fitted PICS models as arm A with every "
                      "IMPUTE candidate removed from the decision pools; "
                      "first-commit continues to the next non-IMPUTE "
                      "candidate; windows left without candidates KEEP"),
            "five_quantities": ("proposal/applicability coverage, "
                                "action-conditional B&S precision "
                                "(beneficial_commits/committed), "
                                "action-conditional CHR, bcov, abstention "
                                "rate (1 - commit_rate)"),
            "harmful": f"true_loss > {HARM_LOSS}",
            "frame": ("frozen 771 real windows; removed actions stay as "
                      "KEEP placeholders, the denominator never moves"),
            "arm_F": ("unrestricted per-window max-gain beneficial_and_safe "
                      "oracle over (full existing pool + FACT_SHORT), "
                      "RESEGMENT closed; target-label headroom only"),
        },
        "integrity_gates": gates,
        "all_gates_pass": bool(all_pass),
        "arms": reports,
        "decomposition": decomposition,
        "conflict_analysis": conflict_summary,
        "d_vs_e": d_vs_e,
        "target_budget_file": OUT_BUDGET.name,
        "input_hashes": {
            "v33_training_data": _sha256(ROWS_PATH),
            "v33_clean_rerun": _sha256(FROZEN_V33),
            "v38_oracle_replay": _sha256(REPLAY_PATH),
            "v38_impute_mask_records": _sha256(MASK_RECORDS),
            "v38_explicit_impute_records": _sha256(EXPLICIT_RECORDS),
            "v38_explicit_impute_probe": _sha256(EXPLICIT_PROBE),
            "p0_corpus_manifest_a": _sha256(MANIFEST_PATH),
        },
        "code_hashes": {
            "experiments/v39_phase0_replay.py": _sha256(
                Path(__file__).resolve()),
            "experiments/v33_compare_arms.py": _sha256(
                ROOT / "experiments" / "v33_compare_arms.py"),
            "experiments/v38_oracle_replay.py": _sha256(
                ROOT / "experiments" / "v38_oracle_replay.py"),
            "experiments/v38_explicit_impute_probe.py": _sha256(
                ROOT / "experiments" / "v38_explicit_impute_probe.py"),
            "experiments/v38_impute_mask_audit.py": _sha256(
                ROOT / "experiments" / "v38_impute_mask_audit.py"),
            "experiments/v33_labels.py": _sha256(
                ROOT / "experiments" / "v33_labels.py"),
            "src/introact_ts/actions.py": _sha256(
                ROOT / "src" / "introact_ts" / "actions.py"),
            "src/introact_ts/probe.py": _sha256(
                ROOT / "src" / "introact_ts" / "probe.py"),
        },
        "decision_digest_sha256": dig["sha256"],
        "runtime_sec": time.time() - t0,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    manifest = {
        "phase": "v3.9 Phase 0 integrity manifest",
        "preregistration": "docs/v3_9_mirage_preregistration.md §2 "
                           "(Phase-0 完整性门)",
        "gates": gates,
        "all_pass": bool(all_pass),
        "input_hashes": out["input_hashes"],
        "code_hashes": out["code_hashes"],
        "decision_digest_sha256": dig["sha256"],
        "output_sha256": {
            "results/v39_phase0_replay.json": _sha256(OUT_JSON),
            "results/v39_phase0_records.jsonl": _sha256(OUT_RECORDS),
            "results/v39_target_budget.json": _sha256(OUT_BUDGET),
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_MANIFEST.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, default=str)
    print(f"[manifest] all_pass={all_pass} -> {OUT_MANIFEST.name}", flush=True)
    print(f"[done] runtime={time.time() - t0:.1f}s", flush=True)
    print("___V39_PHASE0_DONE___", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
