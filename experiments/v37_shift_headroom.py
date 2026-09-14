"""v3.7 Phase 0: frozen-score reproduction + calibration headroom audit.

Pre-registered in ``docs/v3_7_shift_preregistration.md`` §3. CPU-only, API 0,
no GPU, no TSFM retraining, no new packages. Never touches src/. Reuses the
frozen v3.6 pipeline by importing ``experiments/v36_pair_ranker_probe.py``
(its feature/model/score/replay/metric functions are called, not rewritten).

Three blocks:

§3.1  Reproduce PAIR_absolute/logreg from the frozen v3.6 artifacts: per-fold
      pairwise AUROC/accuracy, p_vs_keep, calibration margin, candidate rank /
      selected commit, source/family commit distributions. Every float must
      match the frozen records within 1e-9, every integer/bool exactly. Any
      breach stops the audit (the caller must regress v3.6 code, not this
      script).

§3.2  Two target-label oracles (DIAGNOSTIC ONLY, never deployable). The v3.6
      PAIR_absolute/logreg candidate ordering is kept; held-out labels only
      choose calibration:
        oracle_target_threshold_global   per-family threshold on the frozen
                                         global score (score unchanged);
        oracle_target_expert_mixture     convex combination of training-source
                                         experts plus per-family threshold.
      Expert: one family-aware logistic regression per training source,
      fitted on that source's candidates (absolute feature vector + family
      one-hot + family x {delta_utility_rel, struct_distortion, action_risk}
      interactions, target = beneficial_and_safe). Mixture grid: simplex over
      the 5 training-source experts with step 0.25 (70 weight vectors,
      enumerated in descending lexicographic order). Threshold grid:
      per-family margin in {0.00, 0.05, ..., 0.40} on top of 0.5, first-commit
      replay preserved. Feasibility constraints per held-out fold:
      CHR <= 0.10, pme <= 0.0055, damage <= 0.0402 (incumbent damage).
      Objective: max bcov, ties -> max gain, min CHR, lowest margins, lowest
      weight index. Selection is deterministic.

§3.3  Calibration transfer matrix: for every ordered (train source s, target
      source t) pair, train PAIR_absolute/logreg on the pairs of s only,
      select the margin on s with the frozen v3.6 calibration rule, deploy on
      t. Entries: CHR, bcov, gain, pme, damage, commits, threshold, score
      quantile shift, B&S / harm separation AUROC, commit family. Diagonal is
      in-sample and flagged. Fingerprint distances between sources use only
      deployment-available quantities (robust per-feature quantiles, median
      episode candidate count, family proposal rates; median/IQR
      standardisation across the six sources). Correlation of fingerprint
      distance with transfer CHR/bcov answers "similar source calibration
      transfers better".

Metric definitions identical to ``experiments/v33_compare_arms.py`` (CHR =
share of commits with true_loss > 0.03; pme = protected-stratum edit rate;
bcov/gain = mean beneficial indicator / repair gain over contaminated
windows; damage = mean true_loss over all windows; first-commit replay;
RESEGMENT excluded; frozen v2 structural veto).
"""

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations_with_replacement
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v36_pair_ranker_probe as v36  # noqa: E402

OUT_HEADROOM = ROOT / "results" / "v37_shift_headroom.json"
OUT_TRANSFER = ROOT / "results" / "v37_calibration_transfer.json"

REAL_SOURCES = v36.REAL_SOURCES
ELIGIBLE_FAMILIES = ("DENOISE", "DESPIKE", "IMPUTE")  # RESEGMENT closed
FAM_INDEX = {g: k for k, g in enumerate(ELIGIBLE_FAMILIES)}

#: §3.2 grids (fixed here, before any held-out label is consulted).
ORACLE_MARGIN_GRID = tuple(round(0.05 * i, 2) for i in range(9))  # 0.00..0.40
SIMPLEX_STEP_DENOM = 4  # simplex weights on {0, 1/4, 2/4, 3/4, 1}

#: §3.2 feasibility constraints (per held-out fold).
CON_CHR = 0.10
CON_PME = 0.0055
CON_DAMAGE = 0.0402  # frozen incumbent pooled damage

#: §3.2 verdict thresholds (pre-registered).
TARGET_BCOV = 0.30
TARGET_GAIN = 0.10

TOL = 1e-9

#: Interaction features that make a source expert "family-aware".
EXPERT_INTERACT_FEATURES = ("delta_utility_rel", "struct_distortion",
                            "action_risk")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkey(params):
    return json.dumps(params, sort_keys=True)


def _ckey(uid, fam, rung, params):
    return (uid, fam, rung, _pkey(params))


# -- fold split (byte-identical logic to v36_pair_ranker_probe.main) ----------


def split_uids(eps, test_ds):
    rest = sorted(uid for uid, ep in eps.items()
                  if ep["dataset"] != test_ds
                  and not ep["dataset"].startswith("ood:"))
    rng = np.random.RandomState(v36.SPLIT_SEED)
    rng.shuffle(rest)
    n_train = int(0.8 * len(rest))
    return set(rest[:n_train]), set(rest[n_train:])


# -- §3.1 reproduction ---------------------------------------------------------


def train_fold_model(pairs_by_uid, eps, train_uids):
    """Retrain PAIR_absolute/logreg exactly as v3.6 main() does."""
    train_pairs = [p for uid in sorted(train_uids) for p in pairs_by_uid[uid]]
    dim = v36._dim("absolute")
    X = np.zeros((len(train_pairs), dim))
    vec_cache = {}
    for i, p in enumerate(train_pairs):
        vi, vj = v36._pair_vectors(p, eps, "absolute", vec_cache)
        X[i] = vi - vj
    y = np.array([int(p["label"]) for p in train_pairs])
    w = v36._src_weights([p["dataset"] for p in train_pairs])
    return v36._fit_logreg(X, y, w), X, y


def reproduce(pairs, eps):
    """§3.1: retrain per fold, rescore, compare against frozen v3.6 records."""
    pairs_by_uid = defaultdict(list)
    for p in pairs:
        pairs_by_uid[p["sample_uid"]].append(p)

    frozen_probe = json.load(
        (ROOT / "results" / "v36_pair_probe.json").open(encoding="utf-8"))
    frozen_preds = {}
    with (ROOT / "results" / "v36_pair_predictions.jsonl").open(
            encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["arm"] == "PAIR_absolute" and r["model"] == "logreg":
                frozen_preds.setdefault(r["fold"], {})[
                    _ckey(r["sample_uid"], r["family"], r["rung"],
                          r["params"])] = r

    per_fold = {}
    max_diff = 0.0
    fold_models = {}  # reused by §3.2 so nothing is fitted twice
    pooled_committed = {}
    for test_ds in REAL_SOURCES:
        train_uids, cal_uids = split_uids(eps, test_ds)
        cal_eps = [eps[uid] for uid in sorted(cal_uids)]
        test_eps = [ep for uid, ep in eps.items()
                    if ep["dataset"] == test_ds]
        model, X_train, y_train = train_fold_model(pairs_by_uid, eps,
                                                   train_uids)
        scored_cal = [(ep["sample_uid"],
                       v36._score_episode(model, ep, "absolute", True))
                      for ep in cal_eps]
        scored_test = [(ep["sample_uid"],
                        v36._score_episode(model, ep, "absolute", True))
                       for ep in test_eps]
        margin, degraded, cal_met = v36._select_margin(scored_cal)
        committed = v36._committed_from_scored(scored_test, margin)
        pooled_committed.update(committed)
        fmet = v36._episode_metrics(committed)
        test_pairs = [p for ep in test_eps
                      for p in pairs_by_uid[ep["sample_uid"]]]
        lm, _, _ = v36._learn_metrics(model, test_pairs, eps, "absolute",
                                      True)
        lm["train_pairwise_accuracy"] = v36._fit_check(model, X_train,
                                                       y_train)
        lm["pkeep_bns_auroc"] = v36._pkeep_auroc(scored_test)
        fold_models[test_ds] = {
            "model": model, "margin": margin, "scored_test": scored_test,
            "scored_cal": scored_cal, "committed": committed,
            "train_uids": train_uids, "cal_uids": cal_uids,
        }

        # -- compare against frozen records --
        ref_fold = frozen_probe["folds"]["PAIR_absolute"][test_ds]["logreg"]
        ref_cal = frozen_probe["calibration"]["PAIR_absolute"][test_ds][
            "logreg"]
        cmp_ = {"floats": {}, "exact": {}}

        def _fc(name, got, want):
            d = abs(float(got) - float(want))
            cmp_["floats"][name] = {"got": float(got), "ref": float(want),
                                    "abs_diff": d}
            return d

        diffs = [
            _fc("margin", margin, ref_cal["margin"]),
            _fc("cal_bcov", cal_met["beneficial_coverage"],
                ref_cal["cal_bcov"]),
            _fc("cal_chr", cal_met["conditional_harm_rate"],
                ref_cal["cal_chr"]),
            _fc("pairwise_accuracy", lm["pairwise_accuracy"],
                ref_fold["learning"]["pairwise_accuracy"]),
            _fc("auroc", lm["auroc"], ref_fold["learning"]["auroc"]),
            _fc("auprc", lm["auprc"], ref_fold["learning"]["auprc"]),
            _fc("train_pairwise_accuracy", lm["train_pairwise_accuracy"],
                ref_fold["learning"]["train_pairwise_accuracy"]),
            _fc("pkeep_bns_auroc", lm["pkeep_bns_auroc"],
                ref_fold["learning"]["pkeep_bns_auroc"]),
            _fc("bcov", fmet["beneficial_coverage"],
                ref_fold["beneficial_coverage"]),
            _fc("chr", fmet["conditional_harm_rate"],
                ref_fold["conditional_harm_rate"]),
            _fc("pme", fmet["protected_mis_edit_rate"],
                ref_fold["protected_mis_edit_rate"]),
            _fc("damage", fmet["damage"], ref_fold["damage"]),
            _fc("gain", fmet["mean_repair_gain_contaminated"],
                ref_fold["mean_repair_gain_contaminated"]),
        ]
        exact_ok = (
            degraded == ref_cal["calibration_degraded"]
            and cal_met["committed"] == ref_cal["cal_commits"]
            and fmet["committed"] == ref_fold["committed"]
            and fmet["harmful_commits"] == ref_fold["harmful_commits"]
            and fmet["beneficial_commits"] == ref_fold["beneficial_commits"]
            and fmet["commit_by_source"] == ref_fold["commit_by_source"]
            and fmet["commit_by_family"] == ref_fold["commit_by_family"]
            and fmet["bs_by_source"] == ref_fold["bs_by_source"])
        cmp_["exact"]["calibration_degraded"] = degraded
        cmp_["exact"]["int_and_distribution_match"] = bool(exact_ok)

        # per-candidate scores / selection against frozen predictions
        fp = frozen_preds[test_ds]
        pred_diff = 0.0
        n_pred = 0
        selected_repro, selected_frozen = set(), set()
        veto_mismatch = 0
        by_uid_scored = dict(scored_test)
        for ep in test_eps:
            uid = ep["sample_uid"]
            got = committed[uid]
            sel_key = (_ckey(uid, got[0]["family"], got[0]["rung"],
                             got[0]["params"]) if got else None)
            for sc in by_uid_scored[uid]:
                r = sc["row"]
                k = _ckey(uid, r["family"], r["rung"], r["params"])
                fr = fp[k]
                pred_diff = max(
                    pred_diff,
                    abs(sc["p_vs_keep"] - fr["p_vs_keep"]),
                    abs(sc["mean_p_vs_others"] - fr["mean_p_vs_others"]),
                    abs(sc["tournament_score"] - fr["tournament_score"]))
                n_pred += 1
                if bool(k == sel_key):
                    selected_repro.add(k)
                if fr["selected"]:
                    selected_frozen.add(k)
                if (r["family"] not in v36.ELIGIBLE) != fr["veto_resegment"]:
                    veto_mismatch += 1
                sd = float(r["features"].get(
                    "struct_distortion", r.get("struct_distortion", 0.0)))
                if (not v36.v2_structure_ok(r["family"], sd, v36.V2_FROZEN)
                        ) != fr["veto_structure"]:
                    veto_mismatch += 1
        cmp_["floats"]["per_candidate_max_abs_diff"] = {
            "got": pred_diff, "ref": 0.0, "abs_diff": pred_diff}
        cmp_["exact"]["n_candidates"] = n_pred
        cmp_["exact"]["selected_match"] = (
            selected_repro == selected_frozen)
        cmp_["exact"]["n_selected"] = len(selected_repro)
        cmp_["exact"]["veto_mismatch"] = veto_mismatch
        # deterministic per-value sample for test-side spot checks
        sample = []
        for k in sorted(fp)[:10]:
            fr = fp[k]
            got = committed.get(k[0])
            sc_row = next(
                s for s in by_uid_scored[k[0]]
                if _ckey(k[0], s["row"]["family"], s["row"]["rung"],
                         s["row"]["params"]) == k)
            sample.append({
                "candidate": list(k),
                "got_p_vs_keep": sc_row["p_vs_keep"],
                "ref_p_vs_keep": fr["p_vs_keep"],
                "got_tournament": sc_row["tournament_score"],
                "ref_tournament": fr["tournament_score"],
                "selected": bool(got and _ckey(
                    k[0], got[0]["family"], got[0]["rung"],
                    got[0]["params"]) == k)})
        cmp_["candidate_sample"] = sample
        diffs.append(pred_diff)
        fold_diff = max(diffs)
        max_diff = max(max_diff, fold_diff)
        cmp_["max_abs_diff"] = fold_diff
        cmp_["pass"] = bool(fold_diff < TOL and exact_ok
                            and cmp_["exact"]["selected_match"]
                            and veto_mismatch == 0)
        per_fold[test_ds] = cmp_
        print(f"[repro {test_ds}] max_abs_diff={fold_diff:.3e} "
              f"pass={cmp_['pass']}", flush=True)

    # pooled check
    pooled_met = v36._episode_metrics(pooled_committed)
    ref_pooled = frozen_probe["pooled"]["PAIR_absolute/logreg"]
    pooled_diffs = {}
    pooled_max = 0.0
    for name in ("beneficial_coverage", "conditional_harm_rate",
                 "protected_mis_edit_rate", "damage",
                 "mean_repair_gain_contaminated", "commit_rate"):
        d = abs(pooled_met[name] - ref_pooled[name])
        pooled_diffs[name] = d
        pooled_max = max(pooled_max, d)
    pooled_exact = (
        pooled_met["committed"] == ref_pooled["committed"]
        and pooled_met["commit_by_source"] == ref_pooled["commit_by_source"]
        and pooled_met["commit_by_family"] == ref_pooled["commit_by_family"])
    repro = {
        "tolerance": TOL,
        "max_abs_diff_overall": max(max_diff, pooled_max),
        "per_fold": per_fold,
        "pooled": {"float_abs_diffs": pooled_diffs,
                   "exact_match": bool(pooled_exact),
                   "max_abs_diff": pooled_max},
        "pass": bool(max(max_diff, pooled_max) < TOL and pooled_exact
                     and all(c["pass"] for c in per_fold.values())),
    }
    return repro, fold_models


# -- §3.2 oracle machinery -------------------------------------------------------


def simplex_grid(n_experts, denom=SIMPLEX_STEP_DENOM):
    """Weight vectors w >= 0, sum w = 1, on the grid with step 1/denom.

    Enumerated via combinations_with_replacement over unit-fraction positions
    (stars and bars), then each composition is counted in descending
    lexicographic order of the weight tuple -> fully deterministic.
    """
    comps = set()
    for bars in combinations_with_replacement(range(n_experts), denom):
        w = [0] * n_experts
        for b in bars:
            w[b] += 1
        comps.add(tuple(w))
    return [tuple(c / denom for c in w)
            for w in sorted(comps, reverse=True)]


def _scored_arrays(scored, gate_key, order_key):
    """Episode -> sorted deployable candidates as plain arrays.

    Vetoes applied here (RESEGMENT closed, frozen v2 structure veto): vetoed
    candidates can never commit and are dropped before replay.
    """
    fam, gate, order = [], [], []
    keys = []
    loss, gain, benef, bns = [], [], [], []
    for sc in scored:
        r = sc["row"]
        if r["family"] not in v36.ELIGIBLE:
            continue
        sd = float(r["features"].get("struct_distortion",
                                     r.get("struct_distortion", 0.0)))
        if not v36.v2_structure_ok(r["family"], sd, v36.V2_FROZEN):
            continue
        fam.append(FAM_INDEX[r["family"]])
        gate.append(float(sc[gate_key]))
        order.append(float(sc[order_key]))
        keys.append((r["family"], r["rung"], _pkey(r["params"])))
        loss.append(float(r["true_loss"]))
        gain.append(float(r["true_repair_gain"]))
        benef.append(float(bool(r["beneficial"])))
        bns.append(float(bool(r["beneficial_and_safe"])))
    idx = sorted(range(len(fam)), key=lambda i: (-order[i], keys[i]))
    return {
        "fam": np.array([fam[i] for i in idx], dtype=int),
        "gate": np.array([gate[i] for i in idx], dtype=np.float64),
        "order": np.array([order[i] for i in idx], dtype=np.float64),
        "keys": [keys[i] for i in idx],
        "loss": np.array([loss[i] for i in idx], dtype=np.float64),
        "gain": np.array([gain[i] for i in idx], dtype=np.float64),
        "benef": np.array([benef[i] for i in idx], dtype=np.float64),
        "bns": np.array([bns[i] for i in idx], dtype=np.float64),
    }


def sweep_margins(ep_blocks, ep_meta, margin_grid=ORACLE_MARGIN_GRID):
    """Vectorised per-family margin sweep over pre-sorted episode blocks.

    Returns metric arrays of shape (K, F, F, F) flattened in the fixed grid
    product order (itertools.product over margin_grid per eligible family).
    """
    from itertools import product
    combos = np.array(list(product(margin_grid, repeat=3)),
                      dtype=np.float64)  # (K, 3)
    K = len(combos)
    n_win = len(ep_blocks)
    prot_n = sum(1 for m in ep_meta if m["prot"])
    cont_n = sum(1 for m in ep_meta if m["cont"])
    commit = np.zeros(K)
    harm = np.zeros(K)
    loss_sum = np.zeros(K)
    pme_hit = np.zeros(K)
    benef_sum = np.zeros(K)
    gain_sum = np.zeros(K)
    sel_rows = []  # per episode: (K,) selected position or -1
    for blk, meta in zip(ep_blocks, ep_meta):
        m = len(blk["fam"])
        if m == 0:
            sel_rows.append(np.full(K, -1, dtype=int))
            continue
        thr = 0.5 + combos[:, blk["fam"]]  # (K, m)
        passm = blk["gate"][None, :] >= thr
        has = passm.any(axis=1)
        first = np.where(has, passm.argmax(axis=1), -1)
        sel_rows.append(first)
        valid = first >= 0
        li = np.where(valid, first, 0)
        commit += valid
        harm += valid & (blk["loss"][li] > v36.HARM_LOSS)
        loss_sum += np.where(valid, blk["loss"][li], 0.0)
        if meta["prot"]:
            pme_hit += valid
        if meta["cont"]:
            benef_sum += np.where(valid, blk["benef"][li], 0.0)
            gain_sum += np.where(valid, blk["gain"][li], 0.0)
    metrics = {
        "committed": commit,
        "chr": harm / np.maximum(commit, 1),
        "damage": loss_sum / max(n_win, 1),
        "pme": pme_hit / max(prot_n, 1),
        "bcov": benef_sum / max(cont_n, 1),
        "gain": gain_sum / max(cont_n, 1),
    }
    return combos, metrics, sel_rows


def _pick_best(combos, metrics):
    """Deterministic selection: feasible first, then max bcov, max gain,
    min CHR, then lowest config index. If nothing is feasible the same
    ordering degrades to min CHR / max bcov / lowest index and the result
    is flagged infeasible by the caller via the returned flag."""
    feas = ((metrics["chr"] <= CON_CHR + 1e-12)
            & (metrics["pme"] <= CON_PME + 1e-12)
            & (metrics["damage"] <= CON_DAMAGE + 1e-12))
    n = len(combos)
    keys = [(bool(feas[i]), float(metrics["bcov"][i]),
             float(metrics["gain"][i]), -float(metrics["chr"][i]), -i)
            for i in range(n)]
    best = max(range(n), key=lambda i: keys[i])
    return best, bool(feas[best])


def _exact_metrics(sel, ep_blocks, eps_list):
    """Exact v33/v36-口径 metrics for one per-episode selection, via
    v36._episode_metrics replay on the original rows."""
    committed = {}
    for ep, blk, s in zip(eps_list, ep_blocks, sel):
        uid = ep["sample_uid"]
        s = int(s)
        if s < 0:
            committed[uid] = None
            continue
        fam_k, rung_k, pk = blk["keys"][s]
        row = next(r for r in ep["cands"]
                   if r["family"] == fam_k and r["rung"] == rung_k
                   and _pkey(r["params"]) == pk)
        committed[uid] = (row, s)
    return v36._episode_metrics(committed), committed


def oracle_global(fold_models, eps):
    """§3.2 oracle_target_threshold_global: frozen global ranking/scores,
    held-out labels choose only the per-family margin."""
    out = {}
    pooled_committed = {}
    for test_ds in REAL_SOURCES:
        fm = fold_models[test_ds]
        test_eps = [ep for uid, ep in eps.items()
                    if ep["dataset"] == test_ds]
        blocks = [_scored_arrays(sc, "p_vs_keep", "tournament_score")
                  for _, sc in fm["scored_test"]]
        meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
                 "cont": ep["stratum"] == "contaminated"}
                for ep in test_eps]
        combos, metrics, sel_rows = sweep_margins(blocks, meta)
        best, feasible = _pick_best(combos, metrics)
        sel = np.array([r[best] for r in sel_rows])
        exact, committed = _exact_metrics(sel, blocks, test_eps)
        pooled_committed.update(committed)
        # cross-check vectorised vs exact replay (same 口径, two code paths)
        xcheck = {
            "bcov": abs(exact["beneficial_coverage"]
                        - metrics["bcov"][best]),
            "chr": abs(exact["conditional_harm_rate"]
                       - metrics["chr"][best]),
            "damage": abs(exact["damage"] - metrics["damage"][best]),
            "pme": abs(exact["protected_mis_edit_rate"]
                       - metrics["pme"][best]),
            "gain": abs(exact["mean_repair_gain_contaminated"]
                        - metrics["gain"][best]),
        }
        out[test_ds] = {
            "feasible": feasible,
            "margins": {g: float(combos[best][FAM_INDEX[g]])
                        for g in ELIGIBLE_FAMILIES},
            "metrics": _public_metrics(exact),
            "vectorised_vs_exact_max_abs_diff": max(xcheck.values()),
            "n_configs": int(len(combos)),
            "n_feasible": int(((metrics["chr"] <= CON_CHR + 1e-12)
                               & (metrics["pme"] <= CON_PME + 1e-12)
                               & (metrics["damage"]
                                   <= CON_DAMAGE + 1e-12)).sum()),
        }
        print(f"[oracle-global {test_ds}] feasible={feasible} "
              f"bcov={exact['beneficial_coverage']:.4f} "
              f"gain={exact['mean_repair_gain_contaminated']:.4f} "
              f"CHR={exact['conditional_harm_rate']:.3f}", flush=True)
    pooled = v36._episode_metrics(pooled_committed)
    return {"per_fold": out, "pooled": _public_metrics(pooled)}


# -- experts --------------------------------------------------------------------


def expert_features(ep):
    """Family-aware per-candidate design matrix for a source expert:
    v3.6 absolute vector + family x {delta_utility_rel, struct_distortion,
    action_risk} interactions (all deployment-available)."""
    X = v36._vectors(ep, "absolute")
    n = X.shape[0]
    if n == 0:
        return np.zeros((0, v36._dim("absolute") + 9))
    nb1 = len(v36.BASE_FEATURES)
    oh = X[:, nb1 + 1: nb1 + 1 + len(v36.FAMILIES)]
    extra = np.zeros((n, 9))
    k = 0
    for gi, g in enumerate(v36.FAMILIES[:3]):
        for feat in EXPERT_INTERACT_FEATURES:
            fi = v36.BASE_FEATURES.index(feat)
            extra[:, k] = oh[:, gi] * X[:, fi]
            k += 1
    return np.hstack([X, extra])


def fit_source_experts(eps, sources):
    """One family-aware logreg per source on all of that source's candidates
    (target = beneficial_and_safe, frozen logreg config)."""
    experts = {}
    for s in sources:
        feats, ys = [], []
        for uid in sorted(eps):
            ep = eps[uid]
            if ep["dataset"] != s:
                continue
            Xe = expert_features(ep)
            feats.append(Xe)
            ys.extend(int(bool(r["beneficial_and_safe"]))
                      for r in ep["cands"])
        X = np.vstack(feats)
        y = np.array(ys, dtype=int)
        if len(set(y.tolist())) < 2:
            experts[s] = ("constant", float(y.mean()) if len(y) else 0.0)
        else:
            w = np.full(len(y), 1.0 / max(len(y), 1))
            experts[s] = ("logreg", v36._fit_logreg(X, y, w))
    return experts


def expert_scores(experts, sources, ep):
    Xe = expert_features(ep)
    if Xe.shape[0] == 0:
        return np.zeros((0, len(sources)))
    cols = []
    for s in sources:
        kind, obj = experts[s]
        if kind == "constant":
            cols.append(np.full(Xe.shape[0], obj))
        else:
            cols.append(v36._proba(obj, Xe, is_logreg=True))
    return np.vstack(cols).T  # (n_cands, len(sources))


def oracle_expert_mixture(fold_models, eps):
    """§3.2 oracle_target_expert_mixture: held-out labels choose the convex
    combination of training-source experts AND the per-family threshold."""
    out = {}
    pooled_committed = {}
    weights_grid = simplex_grid(5)
    for test_ds in REAL_SOURCES:
        train_sources = [s for s in REAL_SOURCES if s != test_ds]
        experts = fit_source_experts(eps, train_sources)
        test_eps = [ep for uid, ep in eps.items()
                    if ep["dataset"] == test_ds]
        pmat = [expert_scores(experts, train_sources, ep)
                for ep in test_eps]  # per episode
        meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
                 "cont": ep["stratum"] == "contaminated"}
                for ep in test_eps]
        best_rec = None
        for wi, w in enumerate(weights_grid):
            wv = np.array(w)
            blocks = []
            for ep, P in zip(test_eps, pmat):
                sc = [{"row": r, "mix": float(P[i] @ wv)}
                      for i, r in enumerate(ep["cands"])]
                blocks.append(_scored_arrays(sc, "mix", "mix"))
            combos, metrics, sel_rows = sweep_margins(blocks, meta)
            best, feasible = _pick_best(combos, metrics)
            rec_key = (feasible, metrics["bcov"][best], metrics["gain"][best],
                       -metrics["chr"][best], -wi)
            if best_rec is None or rec_key > best_rec[0]:
                best_rec = (rec_key, wi, w, best, feasible, blocks, combos,
                            metrics, sel_rows)
        _, wi, w, best, feasible, blocks, combos, metrics, sel_rows = best_rec
        sel = np.array([r[best] for r in sel_rows])
        exact, committed = _exact_metrics(sel, blocks, test_eps)
        pooled_committed.update(committed)
        out[test_ds] = {
            "feasible": feasible,
            "weights": {s: float(wi_)
                        for s, wi_ in zip(train_sources, w)},
            "margins": {g: float(combos[best][FAM_INDEX[g]])
                        for g in ELIGIBLE_FAMILIES},
            "metrics": _public_metrics(exact),
            "n_weight_vectors": len(weights_grid),
            "n_configs": int(len(combos)) * len(weights_grid),
        }
        print(f"[oracle-mix {test_ds}] feasible={feasible} "
              f"bcov={exact['beneficial_coverage']:.4f} "
              f"gain={exact['mean_repair_gain_contaminated']:.4f} "
              f"CHR={exact['conditional_harm_rate']:.3f} w={w}", flush=True)
    pooled = v36._episode_metrics(pooled_committed)
    return {"per_fold": out, "pooled": _public_metrics(pooled),
            "train_sources_by_fold": {
                ds: [s for s in REAL_SOURCES if s != ds]
                for ds in REAL_SOURCES}}


def _public_metrics(met):
    return {
        "n_windows": met["n_windows"],
        "committed": met["committed"],
        "commit_rate": met["commit_rate"],
        "bcov": met["beneficial_coverage"],
        "gain": met["mean_repair_gain_contaminated"],
        "chr": met["conditional_harm_rate"],
        "pme": met["protected_mis_edit_rate"],
        "damage": met["damage"],
        "harmful_commits": met["harmful_commits"],
        "beneficial_commits": met["beneficial_commits"],
        "commit_by_family": met["commit_by_family"],
        "commit_by_source": met["commit_by_source"],
    }


def verdict(oracle_global_res, oracle_mix_res):
    g = oracle_global_res["pooled"]
    e = oracle_mix_res["pooled"]
    g_ok = g["bcov"] >= TARGET_BCOV and g["gain"] >= TARGET_GAIN
    e_ok = e["bcov"] >= TARGET_BCOV and e["gain"] >= TARGET_GAIN
    if not g_ok and not e_ok:
        light, arm = "RED", None
        rationale = ("neither oracle reaches pooled bcov>=%.2f and "
                     "gain>=%.2f under the constraints -> SHIFT red light"
                     % (TARGET_BCOV, TARGET_GAIN))
    elif g_ok:
        light, arm = "GREEN", "SHIFT_global_IW"
        rationale = ("global-threshold oracle meets the targets -> main "
                     "problem is target calibration; Phase 1 primary arm "
                     "SHIFT_global_IW")
    else:
        light, arm = "GREEN", "SHIFT_expert_IW"
        rationale = ("global oracle misses but expert-mixture oracle meets "
                     "the targets -> specialist router required; Phase 1 "
                     "primary arm SHIFT_expert_IW")
    return {"target": {"bcov": TARGET_BCOV, "gain": TARGET_GAIN},
            "constraints": {"chr": CON_CHR, "pme": CON_PME,
                            "damage": CON_DAMAGE},
            "global_oracle_ok": bool(g_ok),
            "expert_mixture_oracle_ok": bool(e_ok),
            "global_pooled": {"bcov": g["bcov"], "gain": g["gain"],
                              "chr": g["chr"], "pme": g["pme"],
                              "damage": g["damage"]},
            "expert_mixture_pooled": {"bcov": e["bcov"], "gain": e["gain"],
                                      "chr": e["chr"], "pme": e["pme"],
                                      "damage": e["damage"]},
            "light": light, "phase1_primary_arm": arm,
            "rationale": rationale}


# -- §3.3 calibration transfer matrix -------------------------------------------


def transfer_matrix(pairs, eps):
    pairs_by_uid = defaultdict(list)
    for p in pairs:
        pairs_by_uid[p["sample_uid"]].append(p)
    matrix = {s: {} for s in REAL_SOURCES}
    for s in REAL_SOURCES:
        src_pairs = [p for uid in sorted(eps) if eps[uid]["dataset"] == s
                     for p in pairs_by_uid[uid]]
        dim = v36._dim("absolute")
        X = np.zeros((len(src_pairs), dim))
        vec_cache = {}
        for i, p in enumerate(src_pairs):
            vi, vj = v36._pair_vectors(p, eps, "absolute", vec_cache)
            X[i] = vi - vj
        y = np.array([int(p["label"]) for p in src_pairs])
        w = v36._src_weights([p["dataset"] for p in src_pairs])
        model = v36._fit_logreg(X, y, w)
        src_eps = [eps[uid] for uid in sorted(eps)
                   if eps[uid]["dataset"] == s]
        scored_s = [(ep["sample_uid"],
                     v36._score_episode(model, ep, "absolute", True))
                    for ep in src_eps]
        margin, degraded, cal_met = v36._select_margin(scored_s)
        thr = 0.5 + margin
        q_src = _quantile_at(scored_s, thr)
        for t in REAL_SOURCES:
            tgt_eps = [eps[uid] for uid in sorted(eps)
                       if eps[uid]["dataset"] == t]
            scored_t = [(ep["sample_uid"],
                         v36._score_episode(model, ep, "absolute", True))
                        for ep in tgt_eps]
            committed = v36._committed_from_scored(scored_t, margin)
            met = v36._episode_metrics(committed)
            q_tgt = _quantile_at(scored_t, thr)
            matrix[s][t] = {
                "in_sample": bool(s == t),
                "threshold": thr,
                "margin": margin,
                "calibration_degraded_on_source": degraded,
                "chr": met["conditional_harm_rate"],
                "bcov": met["beneficial_coverage"],
                "gain": met["mean_repair_gain_contaminated"],
                "pme": met["protected_mis_edit_rate"],
                "damage": met["damage"],
                "committed": met["committed"],
                "harmful_commits": met["harmful_commits"],
                "commit_by_family": met["commit_by_family"],
                "score_quantile_at_threshold_source": q_src,
                "score_quantile_at_threshold_target": q_tgt,
                "score_quantile_shift": (None if q_tgt is None
                                         or q_src is None
                                         else q_tgt - q_src),
                "bns_separation_auroc": v36._pkeep_auroc(scored_t),
                "harm_separation_auroc": _harm_auroc(scored_t),
            }
        print(f"[transfer] calibrated on {s}", flush=True)
    return matrix


def _quantile_at(scored_eps, thr):
    """Fraction of deployable (eligible, non-vetoed) candidate p_vs_keep
    scores below the threshold — the quantile of the threshold in that
    score distribution."""
    vals = []
    for _, scored in scored_eps:
        for sc in scored:
            r = sc["row"]
            if r["family"] not in v36.ELIGIBLE:
                continue
            sd = float(r["features"].get(
                "struct_distortion", r.get("struct_distortion", 0.0)))
            if not v36.v2_structure_ok(r["family"], sd, v36.V2_FROZEN):
                continue
            vals.append(sc["p_vs_keep"])
    if not vals:
        return None
    return float(np.mean(np.array(vals) < thr))


def _harm_auroc(scored_eps):
    from sklearn.metrics import roc_auc_score
    ys, ss = [], []
    for _, scored in scored_eps:
        for sc in scored:
            ys.append(int(sc["row"]["true_loss"] > v36.HARM_LOSS))
            ss.append(sc["p_vs_keep"])
    if len(set(ys)) < 2:
        return None
    return float(roc_auc_score(ys, ss))


# -- fingerprints ---------------------------------------------------------------


def source_fingerprints(eps):
    """Per-source robust fingerprint, deployment-available only: per base
    feature the 10/25/50/75/90% quantiles over that source's candidates,
    median per-episode candidate count, family proposal rates."""
    fp = {}
    for s in REAL_SOURCES:
        rows = [r for uid in sorted(eps) if eps[uid]["dataset"] == s
                for r in eps[uid]["cands"]]
        vec = []
        for f in v36.BASE_FEATURES:
            v = np.array([float(r["features"].get(f, r.get(f, 0.0)))
                          for r in rows], dtype=np.float64)
            v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
            vec.extend(np.quantile(v, [0.1, 0.25, 0.5, 0.75, 0.9]).tolist())
        n_cands = [len(eps[uid]["cands"]) for uid in sorted(eps)
                   if eps[uid]["dataset"] == s]
        vec.append(float(np.median(n_cands)))
        fam_cnt = Counter(r["family"] for r in rows)
        vec.extend(fam_cnt.get(g, 0) / max(len(rows), 1)
                   for g in v36.FAMILIES)
        fp[s] = np.array(vec, dtype=np.float64)
    # robust standardisation per dimension across the six sources
    M = np.vstack([fp[s] for s in REAL_SOURCES])
    med = np.median(M, axis=0)
    iqr = np.quantile(M, 0.75, axis=0) - np.quantile(M, 0.25, axis=0)
    iqr = np.where(iqr > 0, iqr, 1.0)
    Z = (M - med) / iqr
    zfp = {s: Z[i] for i, s in enumerate(REAL_SOURCES)}
    dist = {s: {t: float(np.linalg.norm(zfp[s] - zfp[t]))
                for t in REAL_SOURCES} for s in REAL_SOURCES}
    return {"vectors_raw": {s: fp[s].tolist() for s in REAL_SOURCES},
            "standardization": "median-centred, IQR-scaled across the 6 "
                               "sources per dimension",
            "distance": dist}


def transfer_correlations(matrix, dist):
    from scipy.stats import pearsonr, spearmanr
    xs, chr_, bcov, gain = [], [], [], []
    for s in REAL_SOURCES:
        for t in REAL_SOURCES:
            if s == t:
                continue
            xs.append(dist[s][t])
            chr_.append(matrix[s][t]["chr"])
            bcov.append(matrix[s][t]["bcov"])
            gain.append(matrix[s][t]["gain"])

    def _corr(y):
        return {"pearson_r": float(pearsonr(xs, y)[0]),
                "pearson_p": float(pearsonr(xs, y)[1]),
                "spearman_r": float(spearmanr(xs, y)[0]),
                "spearman_p": float(spearmanr(xs, y)[1])}

    return {"n_ordered_pairs": len(xs),
            "note": "distance is symmetric; ordered pairs duplicate each "
                    "unordered pair",
            "distance_vs_chr": _corr(chr_),
            "distance_vs_bcov": _corr(bcov),
            "distance_vs_gain": _corr(gain)}


# -- main -------------------------------------------------------------------------


def main():
    t0 = time.time()
    pairs, rows = v36._load()
    eps = v36._build_episodes(rows)
    v36._EPS = eps  # episode registry required by v36 metric functions
    row_index, integrity = v36._integrity(pairs, eps)
    for m in integrity:
        print("[integrity]", m, flush=True)

    repro, fold_models = reproduce(pairs, eps)
    if not repro["pass"]:
        print("[FATAL] reproduction breach >= 1e-9; stopping per §3.1. "
              "Regress v3.6 score/margin/replay code before continuing.",
              flush=True)
    else:
        print("[repro] all folds within 1e-9", flush=True)

    og = om = verd = None
    if repro["pass"]:
        og = oracle_global(fold_models, eps)
        om = oracle_expert_mixture(fold_models, eps)
        verd = verdict(og, om)
        print(f"[verdict] light={verd['light']} arm="
              f"{verd['phase1_primary_arm']} :: {verd['rationale']}",
              flush=True)

        matrix = transfer_matrix(pairs, eps)
        fp = source_fingerprints(eps)
        corr = transfer_correlations(matrix, fp["distance"])
        transfer_out = {
            "phase": "v3.7 Phase 0 §3.3 calibration transfer matrix",
            "preregistration": "docs/v3_7_shift_preregistration.md §3.3",
            "protocol": "train PAIR_absolute/logreg on pairs of source s "
                        "only; margin selected on s with the frozen v3.6 "
                        "calibration rule; deploy on t. Diagonal is "
                        "in-sample (flagged). Diagnostic only.",
            "sources": list(REAL_SOURCES),
            "matrix": matrix,
            "fingerprint": fp,
            "correlation": corr,
            "hashes": _input_hashes(),
            "runtime_sec": time.time() - t0,
        }
        with OUT_TRANSFER.open("w", encoding="utf-8") as f:
            json.dump(transfer_out, f, indent=2, ensure_ascii=False,
                      default=str)
        print(f"[done] -> {OUT_TRANSFER.name}", flush=True)

    headroom = {
        "phase": "v3.7 Phase 0 §3.1–§3.2 reproduction + oracle headroom",
        "preregistration": "docs/v3_7_shift_preregistration.md §3",
        "hashes": _input_hashes(),
        "environment": {"sklearn": __import__("sklearn").__version__,
                        "numpy": np.__version__, "device": "CPU"},
        "reproduction": repro,
        "oracle": None if og is None else {
            "note": "target-label oracles; DIAGNOSTIC ONLY, not deployable",
            "constraints": {"chr": CON_CHR, "pme": CON_PME,
                            "damage": CON_DAMAGE},
            "margin_grid": list(ORACLE_MARGIN_GRID),
            "simplex_step": 1.0 / SIMPLEX_STEP_DENOM,
            "n_simplex_weight_vectors": len(simplex_grid(5)),
            "selection_rule": "feasible first; then max bcov, max gain, "
                              "min CHR, lowest margin grid index, lowest "
                              "weight vector index",
            "oracle_target_threshold_global": og,
            "oracle_target_expert_mixture": om,
            "verdict": verd,
        },
        "runtime_sec": time.time() - t0,
    }
    with OUT_HEADROOM.open("w", encoding="utf-8") as f:
        json.dump(headroom, f, indent=2, ensure_ascii=False, default=str)
    print(f"[done] runtime={time.time() - t0:.1f}s -> {OUT_HEADROOM.name}",
          flush=True)
    return 0 if repro["pass"] else 1


def _input_hashes():
    return {
        "v36_pair_probe": _sha256(ROOT / "results" / "v36_pair_probe.json"),
        "v36_pair_predictions": _sha256(
            ROOT / "results" / "v36_pair_predictions.jsonl"),
        "v36_pair_dataset": _sha256(
            ROOT / "results" / "v36_pair_dataset.jsonl"),
        "v33_training_data": _sha256(
            ROOT / "results" / "v33_training_data.jsonl"),
        "v33_clean_rerun": _sha256(
            ROOT / "results" / "v33_clean_rerun.json"),
        "v33_clean_rerun_harmful": _sha256(
            ROOT / "results" / "v33_clean_rerun_harmful.json"),
        "v36_code": _sha256(
            ROOT / "experiments" / "v36_pair_ranker_probe.py"),
        "code": _sha256(Path(__file__).resolve()),
    }


if __name__ == "__main__":
    sys.exit(main())
