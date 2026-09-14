"""v3.5 Phase 1: ACV signal-gate evaluation (runs ONLY on frozen records).

Pre-registered in ``docs/v3_5_acv_preregistration.md`` §5. This script is the
first point where evaluation fields meet the probe: it reads the frozen
``results/v35_acv_records.jsonl`` (deployment-only features, sha256 logged),
joins the v3.3 candidate-table outcome fields and the PICS_joint_relabel
commit list, and evaluates the four signal gates A/B/C/D exactly as
pre-registered. Nothing here flows back into the records.

Frozen rules (written before any number was seen):

- Scores: A = prequential lcb (primary), B = support-conformity lcb,
  C = min(A, B). Records lacking a score are EXCLUDED from that score's
  statistics (never zero-filled); every gate reports its n.
- Harm prediction direction: higher score = action more likely to help, so
  the harm score is ``-A`` (resp. ``-B``, ``-C``).
- AUROC: Mann-Whitney with average ranks for ties. AUPRC: average
  precision. Both computed only when both classes are present.
- Gate B working point: tau_B = the 20th percentile of A among PICS-accepted
  beneficial_and_safe commits (numpy 'linear' quantile), i.e. the point that
  falsely rejects at most 20% of accepted b&s. A commit counts as flagged
  (would-be-rejected) when A < tau_B.
- Gate C threshold (LODO): for held-out dataset d, tau_d is the LOWEST score
  threshold on the training folds (all candidates of the other datasets with
  a defined A) such that the harm rate among {A >= tau} is <= 0.10 AND at
  least 20 training candidates sit above it; if no threshold qualifies,
  tau_d = +inf (ACV accepts nothing new on fold d). Newly accepted =
  PICS-rejected candidates of fold d with A >= tau_d. New beneficial
  coverage = #(newly accepted AND beneficial_and_safe AND contaminated
  window) / 440, where 440 is the contaminated-window count among candidate
  windows -- the exact denominator of the incumbent bcov 120/440 = 0.2727
  (verified in this script). CHR of newly accepted = share with
  true_loss > 0.03 (the standing ALPHA).
- Gate D: share of all 2414 candidates with prequential OR conformity
  support >= 0.90.
- Verdict: green = A&B&C&D; red = A and B both fail (stop); otherwise
  yellow -- "veto-only" when A&B pass, "proposal-only" when C passes but A
  or B fails; a D failure is reported explicitly either way.

Usage:
    python experiments/v35_acv_evaluate.py
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

ALPHA = 0.03  # standing damage threshold (metrics_common.conditional_loss_metrics)
GATE_A_AUROC = 0.75
GATE_A_AUPRC_LIFT = 0.05
GATE_B_MAX_FALSE_REJECT = 0.20
GATE_B_HARM_RECALL = 0.70
GATE_B_SOURCE_RECALL = 0.50
GATE_B_MIN_SOURCE_HARM = 5
GATE_C_MIN_BCOV = 0.05
GATE_C_MAX_CHR = 0.10
GATE_C_TRAIN_HARM_RATE = 0.10
GATE_C_MIN_TRAIN_ABOVE = 20
GATE_D_MIN_COVERAGE = 0.90

SCORES = ("score_a_prequential", "score_b_support", "score_c_joint")


# -- ranking metrics -------------------------------------------------------------


def auroc(labels, scores):
    """Mann-Whitney AUROC, average ranks for ties; None if one class empty."""
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    n1 = float(y.sum())
    n0 = float(len(y)) - n1
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    ranks = np.empty(len(s), dtype=np.float64)
    r = np.empty(len(s), dtype=np.float64)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        r[i:j + 1] = (i + 1 + j + 1) / 2.0
        i = j + 1
    ranks[order] = r
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def auprc(labels, scores):
    """Average precision; None when no positives."""
    y = np.asarray(labels, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    if y.sum() == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    ys = y[order]
    tp = np.cumsum(ys)
    prec = tp / np.arange(1, len(ys) + 1)
    return float((prec * ys).sum() / ys.sum())


def _quantile(vals, q):
    return float(np.quantile(np.asarray(vals, dtype=np.float64), q))


# -- population assembly -----------------------------------------------------------


def _cand_key(r) -> tuple:
    """Exact candidate identity: uid + family + rung + params.

    The output hash alone is NOT unique across rows (different rungs and even
    different families can land on byte-identical outputs), so joining on it
    inflates every population. This is the same identity the Phase 0 audit
    used for deterministic ordering.
    """
    return (r["sample_uid"], r["family"], r["rung"],
            json.dumps(r["params"], sort_keys=True))


def load_populations(records_path, table_path, commits_path):
    recs = [json.loads(l) for l in open(records_path, encoding="utf-8")]
    table = [json.loads(l) for l in open(table_path, encoding="utf-8")]
    by_key = {}
    for r in table:
        k = _cand_key(r)
        assert k not in by_key, f"duplicate candidate row identity {k}"
        by_key[k] = r
    n_unmatched = 0
    for rec in recs:
        row = by_key.get(_cand_key(rec))
        if row is None:
            n_unmatched += 1
            rec["_ev"] = None
            continue
        rec["_ev"] = {k: row[k] for k in
                      ("harmful", "beneficial", "beneficial_and_safe",
                       "true_loss", "true_kind", "true_repair_gain",
                       "before_nmse", "after_nmse")}

    pics = json.loads(Path(commits_path).read_text(encoding="utf-8"))[
        "PICS_joint_relabel"]
    commits = pics["all_commits"]
    commit_keys = {_cand_key(c) for c in commits}
    harm_by_key = {_cand_key(c): c["decision_detail"]["harm_score"]
                   for c in commits}
    if len(commit_keys) != len(commits):
        raise SystemExit("commit list identity collision")

    for rec in recs:
        key = _cand_key(rec)
        rec["_accepted"] = key in commit_keys
        rec["_pics_harm_score"] = harm_by_key.get(key)

    # incumbent-consistency check: recompute PICS bcov with the
    # v33_compare_arms formula (contaminated candidate windows denominator)
    uid_stratum = {}
    for r in table:
        uid_stratum[r["sample_uid"]] = r["stratum"]
    cont_uids = {u for u, s in uid_stratum.items() if s == "contaminated"}
    n_bs_cont = sum(
        1 for c in commits
        if c["sample_uid"] in cont_uids and not c["harmful"]
        and c["true_repair_gain"] > 1e-9)
    bcov_check = {"cont_windows": len(cont_uids),
                  "pics_beneficial_contaminated_commits": n_bs_cont,
                  "pics_bcov": n_bs_cont / max(len(cont_uids), 1),
                  "incumbent_bcov_reference": 0.2727}
    return recs, commits, n_unmatched, bcov_check


def _scored(recs, score_key):
    """(rec, harm-score) pairs where the ACV score is defined."""
    out = []
    for r in recs:
        v = r.get(score_key)
        if v is not None and r.get("_ev") is not None:
            out.append((r, -float(v)))
    return out


def harm_metrics(recs, score_key):
    """AUROC/AUPRC of the ACV score for the harmful outcome, plus counts."""
    sc = _scored(recs, score_key)
    labels = [float(r["_ev"]["harmful"]) for r, _ in sc]
    scores = [s for _, s in sc]
    return {
        "score": score_key,
        "n_total": len(recs),
        "n_scored": len(sc),
        "n_harmful_scored": int(sum(labels)),
        "auroc_harmful": auroc(labels, scores),
        "auprc_harmful": auprc(labels, scores),
    }


# -- gates ---------------------------------------------------------------------


def gate_a(accepted, score_key="score_a_prequential"):
    """§5 gate A on the PICS-accepted commits. Primary: score A."""
    out = {}
    for key in SCORES:
        m = harm_metrics(accepted, key)
        sc = _scored(accepted, key)
        pics = [(float(r["_ev"]["harmful"]), r["_pics_harm_score"])
                for r, _ in sc if r["_pics_harm_score"] is not None]
        if pics:
            m["auprc_pics_harm_score"] = auprc([p[0] for p in pics],
                                               [p[1] for p in pics])
            m["auprc_lift_vs_pics"] = (
                None if m["auprc_harmful"] is None
                else m["auprc_harmful"] - m["auprc_pics_harm_score"])
        out[key] = m
    prim = out[score_key]
    out["primary"] = score_key
    out["pass"] = bool(
        prim["auroc_harmful"] is not None
        and prim["auroc_harmful"] >= GATE_A_AUROC
        and prim.get("auprc_lift_vs_pics") is not None
        and prim["auprc_lift_vs_pics"] >= GATE_A_AUPRC_LIFT)
    out["thresholds"] = {"auroc": GATE_A_AUROC,
                         "auprc_lift": GATE_A_AUPRC_LIFT}
    return out


def gate_b(accepted, score_key="score_a_prequential"):
    """§5 gate B: working point with <=20% false rejection of accepted b&s."""
    sc = [r for r, _ in _scored(accepted, score_key)]
    bs = [r for r in sc if r["_ev"]["beneficial_and_safe"] == 1.0]
    harm = [r for r in sc if r["_ev"]["harmful"] == 1.0]
    if not bs:
        return {"pass": False, "reason": "no scored accepted b&s"}
    # tau on the raw score: flag (would-reject) when score < tau. tau is the
    # 20th percentile over accepted b&s, so false rejection is <= 20% up to
    # ties (reported exactly).
    tau = _quantile([float(r[score_key]) for r in bs],
                    GATE_B_MAX_FALSE_REJECT)

    def flagged(r):
        return float(r[score_key]) < tau

    fr = float(np.mean([flagged(r) for r in bs])) if bs else None
    rec = float(np.mean([flagged(r) for r in harm])) if harm else None
    imp = [r for r in harm if r["family"] == "IMPUTE"]
    imp_rec = float(np.mean([flagged(r) for r in imp])) if imp else None
    by_source = {}
    for src in sorted({r["dataset"] for r in harm}):
        sub = [r for r in harm if r["dataset"] == src]
        if len(sub) >= GATE_B_MIN_SOURCE_HARM:
            by_source[src] = {
                "n_harmful": len(sub),
                "recall": float(np.mean([flagged(r) for r in sub])),
            }
    source_pass = all(v["recall"] >= GATE_B_SOURCE_RECALL
                      for v in by_source.values())
    out = {
        "pass": bool(rec is not None and rec >= GATE_B_HARM_RECALL
                     and (imp_rec is None or imp_rec >= GATE_B_HARM_RECALL)
                     and source_pass),
        "working_point": {
            "rule": "tau = 20th percentile of score A over PICS-accepted "
                    "beneficial_and_safe commits; flag when A < tau",
            "tau_on_score": tau,
            "false_reject_rate_accepted_bs": fr,
            "n_accepted_scored": len(sc),
            "n_accepted_bs_scored": len(bs),
        },
        "harmful_recall": rec,
        "n_harmful_scored": len(harm),
        "impute_harmful_recall": imp_rec,
        "n_impute_harmful": len(imp),
        "per_source_recall": by_source,
        "thresholds": {"harmful_recall": GATE_B_HARM_RECALL,
                       "source_recall": GATE_B_SOURCE_RECALL,
                       "min_source_harmful": GATE_B_MIN_SOURCE_HARM},
    }
    return out


def gate_c(rejected, score_key="score_a_prequential", n_cont_windows=440):
    """§5 gate C: LODO thresholds, PICS-rejected population."""
    by_ds = defaultdict(list)
    for r in rejected:
        if r.get("_ev") is not None and r.get(score_key) is not None:
            by_ds[r["dataset"]].append(r)
    datasets = sorted(by_ds)
    folds, newly_all = {}, []
    for d in datasets:
        train = [r for o in datasets if o != d for r in by_ds[o]]
        scores = np.asarray([float(r[score_key]) for r in train])
        harms = np.asarray([r["_ev"]["harmful"] for r in train])
        tau = np.inf
        for t in np.unique(scores):
            above = scores >= t
            if above.sum() < GATE_C_MIN_TRAIN_ABOVE:
                continue
            if harms[above].mean() <= GATE_C_TRAIN_HARM_RATE:
                tau = float(t)
                break
        newly = [r for r in by_ds[d] if float(r[score_key]) >= tau]
        folds[d] = {"tau": (None if np.isinf(tau) else tau),
                    "n_train": len(train), "n_newly_accepted": len(newly)}
        newly_all.extend(newly)
    n_new = len(newly_all)
    n_new_harm = sum(1 for r in newly_all if r["_ev"]["true_loss"] > ALPHA)
    n_new_bs_cont = sum(1 for r in newly_all
                        if r["_ev"]["beneficial_and_safe"] == 1.0
                        and r["stratum"] == "contaminated")
    new_bcov = n_new_bs_cont / max(n_cont_windows, 1)
    chr_new = n_new_harm / n_new if n_new else 0.0
    return {
        "pass": bool(new_bcov >= GATE_C_MIN_BCOV
                     and chr_new <= GATE_C_MAX_CHR and n_new > 0),
        "rule": "LODO: tau_d = lowest threshold with harm rate <= "
                f"{GATE_C_TRAIN_HARM_RATE} and >= {GATE_C_MIN_TRAIN_ABOVE} "
                "training candidates above it on the other datasets; "
                "tau=+inf when none qualifies",
        "folds": folds,
        "n_rejected_scored": sum(len(v) for v in by_ds.values()),
        "n_newly_accepted": n_new,
        "n_newly_accepted_harmful": n_new_harm,
        "chr_newly_accepted": chr_new,
        "new_beneficial_contaminated": n_new_bs_cont,
        "new_bcov": new_bcov,
        "bcov_denominator_contaminated_windows": n_cont_windows,
        "thresholds": {"min_new_bcov": GATE_C_MIN_BCOV,
                       "max_chr": GATE_C_MAX_CHR},
    }


def gate_d(recs):
    n = len(recs)
    n_either = sum(1 for r in recs
                   if r["prequential"]["supported"]
                   or r["support_conformity"]["supported"])
    return {
        "pass": bool(n_either / max(n, 1) >= GATE_D_MIN_COVERAGE),
        "n_candidates": n,
        "n_prequential_supported": sum(r["prequential"]["supported"]
                                       for r in recs),
        "n_conformity_supported": sum(r["support_conformity"]["supported"]
                                      for r in recs),
        "n_either_supported": n_either,
        "share_either": n_either / max(n, 1),
        "threshold": GATE_D_MIN_COVERAGE,
    }


# -- stratification (offline analysis layer) ----------------------------------------


def stratify(recs):
    def _block(group):
        out = {"n": len(group)}
        for key in SCORES[:2]:
            m = harm_metrics(group, key)
            out[key] = {"n_scored": m["n_scored"],
                        "auroc_harmful": m["auroc_harmful"]}
        sc = _scored(group, "score_a_prequential")
        pos = [-s for r, s in sc if r["_ev"]["harmful"] == 1.0]
        neg = [-s for r, s in sc if r["_ev"]["harmful"] == 0.0]
        out["score_a_mean_harmful"] = float(np.mean(pos)) if pos else None
        out["score_a_mean_other"] = float(np.mean(neg)) if neg else None
        return out

    dims = {
        "family": lambda r: r["family"],
        "source": lambda r: r["dataset"],
        "geometry": lambda r: r["geometry"],
        "operator": lambda r: f"{r['family']}/{r['rung']}",
        "anchor_coverage": lambda r: str(r["prequential"]["valid_anchors"]),
        "true_kind": lambda r: (r["_ev"]["true_kind"]
                                if r.get("_ev") else "unknown"),
    }
    out = {}
    for name, fn in dims.items():
        groups = defaultdict(list)
        for r in recs:
            groups[fn(r)].append(r)
        out[name] = {k: _block(v) for k, v in sorted(groups.items())}
    return out


def population_stats(recs, name):
    out = {"population": name, "n": len(recs)}
    for key in SCORES:
        m = harm_metrics(recs, key)
        vals = [float(r[key]) for r in recs
                if r.get(key) is not None and r.get("_ev") is not None]
        out[key] = {**m, "mean": float(np.mean(vals)) if vals else None,
                    "median": float(np.median(vals)) if vals else None}
    if recs and recs[0].get("_ev") is not None:
        out["n_harmful"] = int(sum(r["_ev"]["harmful"] for r in recs
                                   if r.get("_ev") is not None))
        out["n_beneficial_and_safe"] = int(sum(
            r["_ev"]["beneficial_and_safe"] for r in recs
            if r.get("_ev") is not None))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records",
                    default=str(ROOT / "results" / "v35_acv_records.jsonl"))
    ap.add_argument("--data",
                    default=str(ROOT / "results" / "v33_training_data.jsonl"))
    ap.add_argument("--commits",
                    default=str(ROOT / "results" / "v33_clean_rerun_harmful.json"))
    ap.add_argument("--out",
                    default=str(ROOT / "results" / "v35_acv_probe.json"))
    args = ap.parse_args()

    t0 = time.time()
    recs, commits, n_unmatched, bcov_check = load_populations(
        args.records, args.data, args.commits)
    if n_unmatched:
        raise SystemExit(f"{n_unmatched} records did not match the "
                         f"candidate table; refusing to evaluate")

    accepted = [r for r in recs if r["_accepted"]]
    rejected = [r for r in recs if not r["_accepted"]]
    rejected_bs = [r for r in rejected
                   if r["_ev"]["beneficial_and_safe"] == 1.0]

    ga = gate_a(accepted)
    gb = gate_b(accepted)
    gc = gate_c(rejected, n_cont_windows=bcov_check["cont_windows"])
    gd = gate_d(recs)

    if ga["pass"] and gb["pass"] and gc["pass"] and gd["pass"]:
        verdict = "green"
    elif not ga["pass"] and not gb["pass"]:
        verdict = "red"
    else:
        verdict = "yellow"
    yellow_role = None
    if verdict == "yellow":
        if ga["pass"] and gb["pass"]:
            yellow_role = "veto-only (A/B pass, C fails)"
        elif gc["pass"]:
            yellow_role = "proposal-only (C passes, A or B fails)"
        else:
            yellow_role = "undetermined (mixed gate failures)"

    summary = {
        "phase": "v3.5 Phase 1 ACV signal-gate evaluation",
        "preregistration": "docs/v3_5_acv_preregistration.md §5",
        "records_file": args.records,
        "records_sha256": hashlib.sha256(
            Path(args.records).read_bytes()).hexdigest(),
        "n_records": len(recs),
        "n_unmatched_to_table": n_unmatched,
        "model": recs[0]["model"] if recs else None,
        "config_hash": recs[0]["config_hash"] if recs else None,
        "incumbent_consistency": bcov_check,
        "populations": {
            "all_candidates": population_stats(recs, "all_2414"),
            "pics_accepted": population_stats(accepted, "pics_accepted_151"),
            "pics_rejected_bs": population_stats(
                rejected_bs, "pics_rejected_beneficial_and_safe"),
        },
        "gates": {"A": ga, "B": gb, "C": gc, "D": gd},
        "verdict": verdict,
        "yellow_role": yellow_role,
        "stratification": stratify(recs),
        "elapsed_seconds": time.time() - t0,
    }
    Path(args.out).write_text(json.dumps(summary, indent=1, default=float),
                              encoding="utf-8")
    out_hash = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(json.dumps({
        "gate_A": ga["pass"], "gate_B": gb["pass"], "gate_C": gc["pass"],
        "gate_D": gd["pass"], "verdict": verdict, "yellow_role": yellow_role,
        "probe_json_sha256": out_hash,
    }, indent=1))
    print(f"___V35_ACV_EVALUATE_DONE___ wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
