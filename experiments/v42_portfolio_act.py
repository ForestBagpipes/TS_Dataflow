"""v4.2 PORTFOLIO-ACT: risk-budgeted counterfactual action portfolio.

Pre-registered in ``docs/v4_2_portfolio_act_preregistration.md`` before any
v4.2 computation. Everything runs on the server; API calls 0; Phase 0 is
pure CPU set arithmetic over frozen artifacts and invokes no TSFM.

v4.1 asked whether a single TSICL_LONG candidate should be accepted. v4.2
changes the degree of freedom: every window carries several applicable
repair actions, and the agent has to pick one under a risk budget. Phase 0
answers the only question worth spending compute on first -- whether the
portfolio actually contains the headroom the round would be chasing.

Stages:
    python experiments/v42_portfolio_act.py phase0a   # arm B integration
    python experiments/v42_portfolio_act.py phase0b   # portfolio oracle
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

from v33_compare_arms import _episode_metrics  # noqa: E402
from v39_bridge_probe import clopper_pearson_upper  # noqa: E402

# -- frozen inputs -------------------------------------------------------------

V39_RECORDS = ROOT / "results" / "v39_phase0_records.jsonl"
V39_CANDIDATES = ROOT / "results" / "v39_longgap_candidates.jsonl"
V39_PROBE = ROOT / "results" / "v39_longgap_probe.json"
V39_ORACLE = ROOT / "results" / "v39_longgap_oracle.json"
V39_BUDGET = ROOT / "results" / "v39_target_budget.json"
V40_POOL = ROOT / "results" / "v40_phase3_pool.jsonl"
V41_ROWS = ROOT / "results" / "v41_selector_rows.jsonl"

OUT_0A = ROOT / "results" / "v42_phase0a_integration.json"
OUT_0B = ROOT / "results" / "v42_phase0b_portfolio_oracle.json"

# -- frozen gates (§3.3, §4) ---------------------------------------------------

PHASE0_GATES = {
    "windows_with_bs_action_min": 80,
    "harmful_tsicl_with_safe_alt_min": 10,
    "portfolio_over_best_fixed_min": 10,
    "integrated_bcov_min": 0.30, "integrated_gain_min": 0.10,
    "integrated_chr_max": 0.10, "integrated_pme_max": 0.0055,
    "integrated_damage_max": 0.0402,
}
V42_GATES = {
    "new_bs_min": 15, "gain_sum_increase_min": 5.6319,
    "harmful_max": 14, "protected_edits_max": 1,
    "bcov_min": 0.30, "gain_min": 0.10, "chr_max": 0.10,
    "chr_cp95_upper_max": 0.15, "pme_max": 0.0055, "damage_max": 0.0195,
}

#: The nine long-gap proposers whose per-window labels the v3.9 probe froze.
#: `keep` is applicable nowhere in that table (it is the abstention, not a
#: repair) and is handled separately by the first-commit protocol.
PROPOSERS = ("tsicl", "linear_bridge", "impute_current_best",
             "impute_conservative", "impute_default", "fm_mean",
             "seasonal_existing", "moment", "openfim")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -- shared loaders ------------------------------------------------------------


def load_v39_arm(arm_name):
    """Rebuild a frozen v3.9 arm's per-window commit map."""
    committed, frame = {}, []
    for line in V39_RECORDS.open(encoding="utf-8"):
        r = json.loads(line)
        if r["arm"] != arm_name:
            continue
        frame.append(r)
        if r["committed"]:
            committed[r["sample_uid"]] = ({
                "sample_uid": r["sample_uid"], "dataset": r["dataset"],
                "stratum": r["stratum"], "true_kind": r["true_kind"],
                "family": r["family"], "rung": r["rung"],
                "params": json.loads(r["params_key"]),
                "true_loss": float(r["true_loss"]),
                "true_repair_gain": float(r["true_repair_gain"]),
                "beneficial": float(r["beneficial"]),
                "beneficial_and_safe": float(r["beneficial_and_safe"]),
                "source": "v39_" + arm_name,
            }, r["episode_position"], r["decision_reason"], None)
    metric_rows = [{"sample_uid": r["sample_uid"], "dataset": r["dataset"],
                    "stratum": r["stratum"], "true_kind": r["true_kind"],
                    "family": "KEEP", "rung": "keep", "params": {}}
                   for r in frame]
    return committed, metric_rows


def load_proposer_labels():
    """Per-window B&S / harmful labels for every frozen long-gap proposer."""
    probe = json.load(V39_PROBE.open(encoding="utf-8"))["proposer_tables"]
    out = {}
    for p in PROPOSERS:
        t = probe[p]
        out[p] = {"bs": set(t["bs_uids"]), "harmful": set(t["harmful_uids"]),
                  "n_applicable": t["n_applicable"],
                  "n_bs": t["n_bs"], "n_harmful": t["n_harmful"]}
    return out


def load_longgap_candidates():
    """The 89 windows x their applicable proposers, with per-record gain."""
    rows = [json.loads(l) for l in V39_CANDIDATES.open(encoding="utf-8")]
    by_uid = defaultdict(dict)
    meta = {}
    for r in rows:
        p = r["proposer"]
        if p not in PROPOSERS:
            continue
        by_uid[r["sample_uid"]][p] = r
        meta[r["sample_uid"]] = {"dataset": r["dataset"],
                                 "stratum": r["stratum"],
                                 "true_kind": r["true_kind"]}
    return by_uid, meta


def gain_lookup():
    """Per (window, proposer) realised gain and loss from the v4.0 pool.

    The pool recomputed TS-ICL's labels on the canonical path and reproduced
    the frozen 75/14 exactly, so its gain column is the one to use where it
    exists; proposers absent from the pool fall back to the probe's
    aggregate labels only.
    """
    g = {}
    if V40_POOL.exists():
        for line in V40_POOL.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("family") == "TSICL_LONG":
                g[(r["sample_uid"], "tsicl")] = {
                    "gain": float(r["true_repair_gain"]),
                    "loss": float(r["true_loss"]),
                    "bs": float(r["beneficial_and_safe"]),
                    "params": r.get("params", {}), "rung": r.get("rung")}
    return g


# -- Phase 0-A -----------------------------------------------------------------


def stage_phase0a() -> int:
    t0 = time.time()
    d_committed, metric_rows = load_v39_arm("D_fact_short_first")
    base_met = _episode_metrics(metric_rows, d_committed)
    base_picks = [v[0] for v in d_committed.values()]
    base = {
        "n_committed": len(base_picks),
        "beneficial_commits": sum(1 for p in base_picks
                                  if p["beneficial_and_safe"] >= 1.0),
        "harmful_commits": sum(1 for p in base_picks
                               if p["true_loss"] > 0.03),
        "gain_sum": float(sum(p["true_repair_gain"] for p in base_picks)),
        "bcov": base_met["beneficial_coverage"],
        "gain": base_met["mean_repair_gain_contaminated"],
        "chr": base_met["conditional_harm_rate"],
        "pme": base_met["protected_mis_edit_rate"],
        "damage": base_met["damage"],
    }
    base["chr_cp95_upper"] = clopper_pearson_upper(
        base["harmful_commits"], base["n_committed"])
    print(f"[0A] v3.9 D baseline: commits={base['n_committed']} "
          f"bs={base['beneficial_commits']} harm={base['harmful_commits']} "
          f"bcov={base['bcov']:.4f} gain={base['gain']:.4f} "
          f"chr={base['chr']:.4f} pme={base['pme']:.4f} "
          f"damage={base['damage']:.4f}", flush=True)

    # -- arm B's long-gap commits, thresholds untouched --------------------
    armb = [json.loads(l) for l in V41_ROWS.open(encoding="utf-8")]
    armb_commit = [r for r in armb if r.get("commit_B")]
    gains = gain_lookup()
    added, conflicts, skipped = {}, [], []
    for r in armb_commit:
        uid = r["sample_uid"]
        g = gains.get((uid, "tsicl"))
        if g is None:
            skipped.append({"sample_uid": uid, "why": "no pooled gain record"})
            continue
        pick = {
            "sample_uid": uid, "dataset": r["source"],
            "stratum": r.get("stratum", "contaminated"),
            "true_kind": r.get("true_kind"),
            "family": "TSICL_LONG", "rung": g.get("rung") or "tsicl_median",
            "params": g.get("params") or {},
            "true_loss": g["loss"], "true_repair_gain": g["gain"],
            "beneficial": 1.0 if g["gain"] > 1e-9 else 0.0,
            "beneficial_and_safe": g["bs"], "source": "v41_arm_B",
        }
        if uid in d_committed:
            # first-commit protocol: D already acted on this window, so the
            # incumbent action stands and the long-gap candidate is dropped.
            conflicts.append({
                "sample_uid": uid,
                "kept_family": d_committed[uid][0]["family"],
                "kept_rung": d_committed[uid][0]["rung"],
                "kept_gain": d_committed[uid][0]["true_repair_gain"],
                "dropped_family": "TSICL_LONG",
                "dropped_gain": g["gain"]})
            continue
        added[uid] = (pick, None, "v41_arm_B_longgap", None)

    merged = dict(d_committed)
    merged.update(added)
    met = _episode_metrics(metric_rows, merged)
    picks = [v[0] for v in merged.values()]
    integ = {
        "n_committed": len(picks),
        "beneficial_commits": sum(1 for p in picks
                                  if p["beneficial_and_safe"] >= 1.0),
        "harmful_commits": sum(1 for p in picks if p["true_loss"] > 0.03),
        "gain_sum": float(sum(p["true_repair_gain"] for p in picks)),
        "bcov": met["beneficial_coverage"],
        "gain": met["mean_repair_gain_contaminated"],
        "chr": met["conditional_harm_rate"],
        "pme": met["protected_mis_edit_rate"],
        "damage": met["damage"],
    }
    integ["chr_cp95_upper"] = clopper_pearson_upper(
        integ["harmful_commits"], integ["n_committed"])
    added_picks = [v[0] for v in added.values()]
    delta = {
        "new_bs": integ["beneficial_commits"] - base["beneficial_commits"],
        "gain_sum_increase": integ["gain_sum"] - base["gain_sum"],
        "harmful_delta": integ["harmful_commits"] - base["harmful_commits"],
        "armB_added_windows": len(added),
        "armB_added_gain_sum": float(
            sum(p["true_repair_gain"] for p in added_picks)),
        "armB_added_bs": sum(1 for p in added_picks
                             if p["beneficial_and_safe"] >= 1.0),
        "armB_added_harmful": sum(1 for p in added_picks
                                  if p["true_loss"] > 0.03),
        "conflicts_first_commit": len(conflicts),
    }
    remaining = {
        "new_bs_needed": max(0, V42_GATES["new_bs_min"] - delta["new_bs"]),
        "gain_sum_increase_needed": max(
            0.0, V42_GATES["gain_sum_increase_min"]
            - delta["gain_sum_increase"]),
        "harmful_must_reach": V42_GATES["harmful_max"],
        "harmful_now": integ["harmful_commits"],
        "bcov_gap": V42_GATES["bcov_min"] - integ["bcov"],
        "gain_gap": V42_GATES["gain_min"] - integ["gain"],
        "chr_excess": integ["chr"] - V42_GATES["chr_max"],
        "pme_excess": integ["pme"] - V42_GATES["pme_max"],
        "damage_excess": integ["damage"] - V42_GATES["damage_max"],
    }
    out = {
        "phase": "v4.2 Phase 0-A arm-B integration replay "
                 "(docs/v4_2_portfolio_act_preregistration.md §3.1)",
        "role": "diagnostic arm; forms no version even if positive",
        "v39_D_baseline": base,
        "integrated": integ,
        "delta_vs_v39_D": delta,
        "remaining_gap_to_v42_gates": remaining,
        "v42_gates": V42_GATES,
        "conflicts": conflicts,
        "skipped": skipped,
        "input_sha256": {p.name: _sha256(p) for p in
                         (V39_RECORDS, V41_ROWS, V40_POOL)},
        "runtime_sec": time.time() - t0,
    }
    json.dump(out, OUT_0A.open("w", encoding="utf-8"), indent=1,
              ensure_ascii=False, default=str)
    print(f"[0A] integrated: commits={integ['n_committed']} "
          f"bs={integ['beneficial_commits']} harm={integ['harmful_commits']} "
          f"bcov={integ['bcov']:.4f} gain={integ['gain']:.4f} "
          f"chr={integ['chr']:.4f} cp95={integ['chr_cp95_upper']:.4f} "
          f"pme={integ['pme']:.4f} damage={integ['damage']:.4f}", flush=True)
    print(f"[0A] delta: +{delta['new_bs']} B&S, "
          f"+{delta['gain_sum_increase']:.4f} gain-sum, "
          f"harmful {delta['harmful_delta']:+d}, "
          f"{delta['conflicts_first_commit']} first-commit conflicts",
          flush=True)
    print("___V42_PHASE0A_DONE___", flush=True)
    return 0


# -- Phase 0-B -----------------------------------------------------------------


def stage_phase0b() -> int:
    t0 = time.time()
    labels = load_proposer_labels()
    cands, meta = load_longgap_candidates()
    uids = sorted(cands)
    assert len(uids) == 89, len(uids)

    per_window = {}
    for uid in uids:
        applicable, bs_actions, harmful_actions, neutral = [], [], [], []
        for p in PROPOSERS:
            if p not in cands[uid]:
                continue
            rec = cands[uid][p]
            if not rec.get("applicable"):
                continue
            applicable.append(p)
            if uid in labels[p]["bs"]:
                bs_actions.append(p)
            elif uid in labels[p]["harmful"]:
                harmful_actions.append(p)
            else:
                neutral.append(p)
        per_window[uid] = {
            "dataset": meta[uid]["dataset"], "applicable": applicable,
            "bs_actions": bs_actions, "harmful_actions": harmful_actions,
            "neutral_actions": neutral,
        }

    n_with_bs = sum(1 for v in per_window.values() if v["bs_actions"])
    tsicl_harm = [u for u in uids if u in labels["tsicl"]["harmful"]]
    tsicl_bs = [u for u in uids if u in labels["tsicl"]["bs"]]
    harm_with_alt = [u for u in tsicl_harm if per_window[u]["bs_actions"]]
    bs_lost_if_switch = [u for u in tsicl_bs if not per_window[u]["bs_actions"]]

    best_fixed = max(PROPOSERS, key=lambda p: labels[p]["n_bs"])
    portfolio_bs = n_with_bs
    over_best_fixed = portfolio_bs - labels[best_fixed]["n_bs"]

    # oracle action choice per window: any B&S action, preferring TS-ICL when
    # it is safe so the comparison against the incumbent stays conservative
    oracle_pick, pick_counts = {}, Counter()
    for uid in uids:
        v = per_window[uid]
        if not v["bs_actions"]:
            continue
        pick = ("tsicl" if "tsicl" in v["bs_actions"]
                else sorted(v["bs_actions"])[0])
        oracle_pick[uid] = pick
        pick_counts[pick] += 1

    gains = gain_lookup()
    oracle_gain_sum = float(sum(
        gains[(u, p)]["gain"] for u, p in oracle_pick.items()
        if (u, p) in gains))
    tsicl_only_gain = float(sum(
        gains[(u, "tsicl")]["gain"] for u in tsicl_bs if (u, "tsicl") in gains))

    # -- integrated: v3.9 D + portfolio oracle -----------------------------
    d_committed, metric_rows = load_v39_arm("D_fact_short_first")
    merged = dict(d_committed)
    n_added, added_no_gain = 0, 0
    for uid, p in oracle_pick.items():
        if uid in merged:
            continue
        g = gains.get((uid, p))
        if g is None:
            added_no_gain += 1
            continue
        merged[uid] = ({
            "sample_uid": uid, "dataset": meta[uid]["dataset"],
            "stratum": meta[uid]["stratum"], "true_kind": meta[uid]["true_kind"],
            "family": "TSICL_LONG" if p == "tsicl" else "BRIDGE_LONG",
            "rung": p, "params": {},
            "true_loss": g["loss"], "true_repair_gain": g["gain"],
            "beneficial": 1.0 if g["gain"] > 1e-9 else 0.0,
            "beneficial_and_safe": g["bs"], "source": "portfolio_oracle",
        }, None, "portfolio_oracle", None)
        n_added += 1
    met = _episode_metrics(metric_rows, merged)
    picks = [v[0] for v in merged.values()]
    integ = {
        "n_committed": len(picks),
        "beneficial_commits": sum(1 for x in picks
                                  if x["beneficial_and_safe"] >= 1.0),
        "harmful_commits": sum(1 for x in picks if x["true_loss"] > 0.03),
        "gain_sum": float(sum(x["true_repair_gain"] for x in picks)),
        "bcov": met["beneficial_coverage"],
        "gain": met["mean_repair_gain_contaminated"],
        "chr": met["conditional_harm_rate"],
        "pme": met["protected_mis_edit_rate"],
        "damage": met["damage"],
        "n_added_from_portfolio": n_added,
        "added_without_gain_record": added_no_gain,
    }
    integ["chr_cp95_upper"] = clopper_pearson_upper(
        integ["harmful_commits"], integ["n_committed"])

    gates = {
        "g1_windows_with_bs_action": {
            "value": n_with_bs, "min": PHASE0_GATES["windows_with_bs_action_min"],
            "pass": n_with_bs >= PHASE0_GATES["windows_with_bs_action_min"]},
        "g2_harmful_tsicl_with_safe_alt": {
            "value": len(harm_with_alt), "of": len(tsicl_harm),
            "min": PHASE0_GATES["harmful_tsicl_with_safe_alt_min"],
            "pass": len(harm_with_alt) >= PHASE0_GATES[
                "harmful_tsicl_with_safe_alt_min"]},
        "g3_portfolio_over_best_fixed": {
            "value": over_best_fixed, "best_fixed": best_fixed,
            "best_fixed_bs": labels[best_fixed]["n_bs"],
            "portfolio_bs": portfolio_bs,
            "min": PHASE0_GATES["portfolio_over_best_fixed_min"],
            "pass": over_best_fixed >= PHASE0_GATES[
                "portfolio_over_best_fixed_min"]},
        "g4_integrated_oracle": {
            "bcov": integ["bcov"], "gain": integ["gain"], "chr": integ["chr"],
            "pme": integ["pme"], "damage": integ["damage"],
            "pass": bool(
                integ["bcov"] >= PHASE0_GATES["integrated_bcov_min"]
                and integ["gain"] >= PHASE0_GATES["integrated_gain_min"]
                and integ["chr"] <= PHASE0_GATES["integrated_chr_max"]
                and integ["pme"] <= PHASE0_GATES["integrated_pme_max"]
                and integ["damage"] <= PHASE0_GATES["integrated_damage_max"])},
    }
    gates["all_pass"] = all(g["pass"] for g in gates.values()
                            if isinstance(g, dict))

    out = {
        "phase": "v4.2 Phase 0-B portfolio oracle headroom "
                 "(docs/v4_2_portfolio_act_preregistration.md §3.2)",
        "role": ("development-label headroom only; the oracle must not select "
                 "any deployed rule"),
        "n_windows": len(uids),
        "per_proposer": {p: {"n_applicable": labels[p]["n_applicable"],
                             "n_bs": labels[p]["n_bs"],
                             "n_harmful": labels[p]["n_harmful"]}
                         for p in PROPOSERS},
        "applicable_action_counts": dict(Counter(
            len(v["applicable"]) for v in per_window.values())),
        "windows_with_at_least_one_bs_action": n_with_bs,
        "windows_with_no_bs_action": [u for u in uids
                                      if not per_window[u]["bs_actions"]],
        "tsicl_harmful_windows": len(tsicl_harm),
        "tsicl_harmful_with_safe_alternative": len(harm_with_alt),
        "tsicl_bs_windows": len(tsicl_bs),
        "tsicl_bs_lost_if_no_action_available": len(bs_lost_if_switch),
        "best_fixed_action": best_fixed,
        "best_fixed_bs": labels[best_fixed]["n_bs"],
        "portfolio_oracle_bs": portfolio_bs,
        "portfolio_over_best_fixed": over_best_fixed,
        "oracle_pick_counts": dict(pick_counts),
        "oracle_gain_sum": oracle_gain_sum,
        "tsicl_only_gain_sum": tsicl_only_gain,
        "integrated_with_v39_D": integ,
        "gates": gates,
        "input_sha256": {p.name: _sha256(p) for p in
                         (V39_CANDIDATES, V39_PROBE, V39_RECORDS)},
        "runtime_sec": time.time() - t0,
    }
    json.dump(out, OUT_0B.open("w", encoding="utf-8"), indent=1,
              ensure_ascii=False, default=str)
    print(f"[0B] windows with >=1 B&S action: {n_with_bs}/89", flush=True)
    print(f"[0B] harmful TS-ICL with safe alternative: "
          f"{len(harm_with_alt)}/{len(tsicl_harm)}", flush=True)
    print(f"[0B] best fixed = {best_fixed} ({labels[best_fixed]['n_bs']} B&S); "
          f"portfolio {portfolio_bs} (+{over_best_fixed})", flush=True)
    print(f"[0B] integrated oracle: bcov={integ['bcov']:.4f} "
          f"gain={integ['gain']:.4f} chr={integ['chr']:.4f} "
          f"pme={integ['pme']:.4f} damage={integ['damage']:.4f}", flush=True)
    print(f"[0B] gates all_pass={gates['all_pass']}", flush=True)
    print("___V42_PHASE0B_DONE___", flush=True)
    return 0


STAGES = {"phase0a": stage_phase0a, "phase0b": stage_phase0b}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    return STAGES[ap.parse_args().stage]()


if __name__ == "__main__":
    sys.exit(main())
