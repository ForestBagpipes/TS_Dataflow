"""v3.6 Phase 1: PAIR (pairwise action-improvement ranking) fast probe.

Pre-registered in ``docs/v3_6_pair_preregistration.md`` §5–§6. CPU-only, no new
packages, no TSFM retraining, API 0. Runs the five pre-registered arms under
the same leave-one-real-dataset-out protocol and metric definitions as the
PICS incumbent (``experiments/v33_compare_arms.py`` / ``v32_compare_arms.py``):

  PICS_joint_relabel     frozen incumbent replay (results/v33_clean_rerun.json)
  pointwise_same_features  pointwise HGB on the SAME per-candidate feature
                           vector as PAIR_episode_relative, target
                           beneficial_and_safe; margin rule identical to PAIR
  PAIR_absolute          pairwise diff of absolute candidate features
  PAIR_episode_relative  formal candidate: within-episode relative features
  oracle_relabel         per-window max-gain beneficial_and_safe commit

Fixed rules (written down here, before any held-out result is seen):

* Pair score is symmetrised: p(i≻j) = 0.5*(f(φ_i−φ_j) + 1 − f(φ_j−φ_i)).
* KEEP is an implicit action with no feature row; its feature vector is fixed
  to the ZERO vector in every feature space (equivalently: every relative
  transform of KEEP is 0, and "candidate minus KEEP" equals the candidate's
  own value). This is the same convention in training and deployment.
* Tournament score (fixed aggregation):
      score(c) = p(c≻KEEP) + mean_{j ∈ eligible, j≠c} p(c≻j)
  where eligible = families in ELIGIBLE_FAMILIES (RESEGMENT closed). If c is
  the only eligible candidate the mean term is 0.
* Commit rule: KEEP is the default; a candidate commits only if
      family eligible AND v2_structure_ok(family, struct_distortion)
      AND p(c≻KEEP) >= 0.5 + margin.
  First-commit protocol: candidates are sorted by descending tournament
  score (ties broken by family, rung, params-json) and the FIRST candidate
  passing every gate is taken.
* Margin selection: on the calibration windows of the training fold only,
  choose the margin maximising beneficial_coverage subject to
  calibration CHR <= 0.10 (ties: lower CHR, then lower margin). If no margin
  is feasible, choose the point with the lowest calibration CHR and then the
  highest bcov, and flag ``calibration_degraded``. The same grid and rule is
  used for the pointwise arm (threshold on P(bns)).
* Source-balanced sample weight (train pairs or train candidates):
      w_p = 1 / (S_train * N_train(source(p)))
  so every training source carries the same total weight 1/S_train.
* Models, both run, HGB is the decision arm:
    HGB: HistGradientBoostingClassifier(max_depth=3, max_iter=100,
        learning_rate=0.05, l2_regularization=1.0, random_state=20260901)
        — identical to the frozen incumbent ShieldConfig.
    logistic: StandardScaler (fit on the fold's train pairs only) +
        LogisticRegression(penalty="l2", C=1.0, max_iter=5000,
        random_state=20260901).

Learning-metric convention (dataset property, verified in the integrity
block): the frozen pair table stores every unordered pair twice — ``forward``
records are canonical (winner = cand_i, label always 1) and ``reverse``
records are the swapped mirror (label always 0). Pairwise accuracy is the
winner-ranked-higher rate; under the exactly antisymmetric scoring above it
is identical whether computed on forward records only or on both directions.
AUROC/AUPRC require both classes, so they are computed on both directions
(score = p(cand_i ≻ cand_j), label as stored); for a symmetrised scorer this
AUROC is exactly P(winner's p > 0.5) with tie correction, i.e. the soft
version of the same ranking quality — it adds no extra information beyond
the accuracy but is reported for completeness.

Feature whitelist (§5): everything is derived from deployment-available
candidate features. No source ID, true_kind, clean series, held-out labels,
or sample_uid encoding enters any feature.
"""

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

from introact_ts.contextual_shield import (  # noqa: E402
    CATEGORICAL_FEATURES, EPISODE_FAMILY_ORDER,
)
from introact_ts.mast_pics import V2_FROZEN, v2_structure_ok  # noqa: E402
from introact_ts.pics import PICS_JOINT_FEATURES  # noqa: E402

PAIR_PATH = ROOT / "results" / "v36_pair_dataset.jsonl"
ROWS_PATH = ROOT / "results" / "v33_training_data.jsonl"
FROZEN_PATH = ROOT / "results" / "v33_clean_rerun.json"
FROZEN_COMMITS_PATH = ROOT / "results" / "v33_clean_rerun_harmful.json"
OUT_JSON = ROOT / "results" / "v36_pair_probe.json"
OUT_PRED = ROOT / "results" / "v36_pair_predictions.jsonl"

REAL_SOURCES = ("US Term Structure", "ETTh1", "ETTh2", "ETTm1",
                "Oil Price", "Crypto")
PROTECTED_STRATA = ("clean", "hard", "rare_valid", "changepoint")
SPLIT_SEED = 20260901  # same LODO split seed as the incumbent
HARM_LOSS = 0.03       # CHR threshold, same as incumbent

HGB_CFG = dict(max_depth=3, max_iter=100, learning_rate=0.05,
               l2_regularization=1.0, random_state=20260901)
LOGREG_CFG = dict(penalty="l2", C=1.0, max_iter=5000, random_state=20260901)

#: Numeric deployment-available base features (PICS joint set minus
#: categoricals). All relative transforms below are derived from these.
BASE_FEATURES = tuple(
    f for f in PICS_JOINT_FEATURES if f not in CATEGORICAL_FEATURES)
FAMILIES = ("DENOISE", "DESPIKE", "IMPUTE", "RESEGMENT")
ELIGIBLE = set(EPISODE_FAMILY_ORDER)  # RESEGMENT closed

#: Fixed relative transforms per base feature. ``rel_keep`` is the raw value
#: (KEEP's vector is zero, so candidate-minus-KEEP is the value itself).
TRANSFORMS = ("rel_keep", "rel_med", "rel_best", "rel_worst", "pct")

#: Fixed family × relative-feature interaction list (pre-registered here;
#: recorded in the output JSON).
INTERACTIONS = tuple(
    (fam, feat, tf)
    for fam in ("DENOISE", "DESPIKE", "IMPUTE")
    for (feat, tf) in (("delta_utility_rel", "rel_keep"),
                       ("struct_distortion", "rel_med"),
                       ("action_risk", "pct")))

MARGIN_GRID = tuple(round(0.02 * i, 2) for i in range(0, 21))  # 0.00..0.40
CAL_CHR_CAP = 0.10


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


# -- data -----------------------------------------------------------------


def _load():
    pairs, rows = [], []
    with PAIR_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))
    with ROWS_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return pairs, rows


def _build_episodes(rows):
    """sample_uid -> episode dict with full v3.3 truth per candidate."""
    eps = {}
    for r in rows:
        uid = r["sample_uid"]
        ep = eps.setdefault(uid, {
            "sample_uid": uid, "dataset": r["dataset"],
            "stratum": r["stratum"], "true_kind": r["true_kind"],
            "cands": [],
        })
        ep["cands"].append(r)
    return eps


def _integrity(pairs, eps):
    """Phase-0-style checks on the frozen pair table against the relabel rows."""
    row_index = {}
    for uid, ep in eps.items():
        for r in ep["cands"]:
            row_index[_ckey(uid, r["family"], r["rung"], r["params"])] = r
    n_fwd = n_rev = 0
    dir_label = Counter()
    per_ep_cands = defaultdict(set)
    for p in pairs:
        assert p["sample_uid"] in eps, f"unknown episode {p['sample_uid']}"
        ep = eps[p["sample_uid"]]
        assert ep["dataset"] == p["dataset"], "dataset mismatch"
        for side in ("i", "j"):
            c = p["cand_" + side]
            if c["family"] == "KEEP":
                assert c["features"] == {}, "KEEP must stay implicit"
                continue
            k = _ckey(p["sample_uid"], c["family"], c["rung"], c["params"])
            assert k in row_index, f"pair candidate not in v33 rows: {k}"
            r = row_index[k]
            assert bool(p["eval_bns_" + side]) == bool(r["beneficial_and_safe"])
            assert abs(p["eval_true_loss_" + side] - r["true_loss"]) < 1e-9
            per_ep_cands[p["sample_uid"]].add(k)
        dir_label[(p["pair_direction"], p["label"])] += 1
        if p["pair_direction"] == "forward":
            n_fwd += 1
        else:
            n_rev += 1
    assert n_fwd == n_rev, "forward/reverse asymmetry"
    for uid, ks in per_ep_cands.items():
        assert len(ks) == len(eps[uid]["cands"]), (
            f"episode {uid}: pairs cover {len(ks)} of "
            f"{len(eps[uid]['cands'])} candidates")
    msgs = [f"pairs={len(pairs)} fwd={n_fwd} rev={n_rev} "
            f"episodes={len(per_ep_cands)} candidates_covered="
            f"{sum(len(v) for v in per_ep_cands.values())}",
            "label_by_direction=" + json.dumps(
                {f"{k[0]}/label{k[1]}": v for k, v in sorted(dir_label.items())}),
            "note: forward records are canonical winner-first (label always 1);"
            " reverse are the swapped mirror (label always 0)"]
    return row_index, msgs


# -- features ---------------------------------------------------------------


def _ep_stats(cands):
    """Per-base-feature episode statistics over non-KEEP candidates."""
    stats = {}
    for f in BASE_FEATURES:
        v = np.array([float(c["features"].get(f, c.get(f, 0.0)))
                      for c in cands], dtype=np.float64)
        v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
        stats[f] = (float(np.median(v)), float(v.max()), float(v.min()), v)
    return stats


def _dim(kind):
    if kind == "relative":
        return len(BASE_FEATURES) * len(TRANSFORMS) + 1 + len(FAMILIES) \
            + len(INTERACTIONS)
    return len(BASE_FEATURES) + 1 + len(FAMILIES)


def _vectors(ep, kind):
    """Per-candidate design matrix for one episode (non-KEEP rows only).

    relative: [rel_keep, rel_med, rel_best, rel_worst, pct] per base feature
              + n_cands + family one-hot + fixed interactions.
    absolute: raw base features + n_cands + family one-hot.
    """
    cands = ep["cands"]
    n = len(cands)
    dim = _dim(kind)
    if n == 0:
        return np.zeros((0, dim))
    if kind == "absolute":
        X = np.zeros((n, dim))
        for i, c in enumerate(cands):
            v = [float(c["features"].get(f, c.get(f, 0.0)))
                 for f in BASE_FEATURES]
            v = [0.0 if not np.isfinite(x) else x for x in v]
            X[i, :len(BASE_FEATURES)] = v
            X[i, len(BASE_FEATURES)] = float(n)
            for j, g in enumerate(FAMILIES):
                X[i, len(BASE_FEATURES) + 1 + j] = float(c["family"] == g)
        return X
    stats = _ep_stats(cands)
    nb = len(BASE_FEATURES)
    nt = len(TRANSFORMS)
    X = np.zeros((n, dim))
    fam_idx = {g: k for k, g in enumerate(FAMILIES)}
    for i, c in enumerate(cands):
        base = {}
        for j, f in enumerate(BASE_FEATURES):
            med, mx, mn, vals = stats[f]
            x = float(c["features"].get(f, c.get(f, 0.0)))
            if not np.isfinite(x):
                x = 0.0
            if len(vals) > 1:
                pct = float(np.mean(vals < x) + 0.5 * np.mean(vals == x))
            else:
                pct = 0.5
            t = (x, x - med, x - mx, x - mn, pct)  # TRANSFORMS order
            base[f] = dict(zip(TRANSFORMS, t))
            X[i, j * nt:(j + 1) * nt] = t
        X[i, nb * nt] = float(n)
        oh = nb * nt + 1
        for j, g in enumerate(FAMILIES):
            X[i, oh + j] = float(c["family"] == g)
        io = oh + len(FAMILIES)
        for k, (g, feat, tf) in enumerate(INTERACTIONS):
            X[i, io + k] = X[i, oh + fam_idx[g]] * base[feat][tf]
    return X


# -- models -----------------------------------------------------------------


def _fit_hgb(X, y, w):
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(**HGB_CFG)
    m.fit(X, y, sample_weight=w)
    return m


def _fit_logreg(X, y, w):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    m = make_pipeline(StandardScaler(), LogisticRegression(**LOGREG_CFG))
    m.fit(np.nan_to_num(X), y, logisticregression__sample_weight=w)
    return m


def _proba(model, X, is_logreg=False):
    if is_logreg:
        X = np.nan_to_num(X)
    return model.predict_proba(np.atleast_2d(X))[:, 1]


def _sym_pair_proba(model, VI, VJ, is_logreg=False):
    """Batched symmetrised p(i≻j) = 0.5*(f(φ_i−φ_j) + 1 − f(φ_j−φ_i))."""
    D1 = VI - VJ
    p1 = _proba(model, D1, is_logreg)
    p2 = _proba(model, -D1, is_logreg)
    return 0.5 * (p1 + 1.0 - p2)


def _src_weights(sources):
    """w_p = 1 / (S_train * N_train(source(p))); each source totals 1/S."""
    cnt = Counter(sources)
    s = len(cnt)
    return np.array([1.0 / (s * cnt[src]) for src in sources],
                    dtype=np.float64)


# -- episode scoring and replay ----------------------------------------------


def _score_episode(model, ep, kind, is_logreg):
    """Deployment-available per-candidate scores, batched.

    KEEP enters only through its fixed zero vector: p(c≻KEEP) is the pair
    model applied to (φ_c − 0).
    """
    cands = ep["cands"]
    n = len(cands)
    V = _vectors(ep, kind)
    zero = np.zeros((n, _dim(kind)))
    p_keep = _sym_pair_proba(model, V, zero, is_logreg) if n else np.zeros(0)
    elig = [i for i, c in enumerate(cands) if c["family"] in ELIGIBLE]
    p_oth = np.zeros(n)
    pairs_ab = [(a, b) for a in elig for b in elig if b != a]
    if pairs_ab:
        A = np.array([a for a, _ in pairs_ab])
        B = np.array([b for _, b in pairs_ab])
        ps = _sym_pair_proba(model, V[A], V[B], is_logreg)
        sums = defaultdict(float)
        cnts = defaultdict(int)
        for (a, _), s in zip(pairs_ab, ps):
            sums[a] += float(s)
            cnts[a] += 1
        for a in elig:
            if cnts[a]:
                p_oth[a] = sums[a] / cnts[a]
    out = []
    for i, c in enumerate(cands):
        out.append({"row": c, "p_vs_keep": float(p_keep[i]),
                    "mean_p_vs_others": float(p_oth[i]),
                    # Fixed aggregation: win prob vs KEEP + mean win prob vs
                    # the other eligible candidates.
                    "tournament_score": float(p_keep[i] + p_oth[i])})
    return out


def _score_episode_pointwise(model, ep, is_logreg):
    V = _vectors(ep, "relative")
    p = _proba(model, V, is_logreg) if len(V) else np.zeros(0)
    return [{"row": c, "p_bns": float(p[i]),
             "tournament_score": float(p[i])}
            for i, c in enumerate(ep["cands"])]


def _replay_scored(scored, margin, pointwise=False):
    """First-commit replay on precomputed scores: sort by tournament score,
    take the first candidate passing every gate. Returns (index, rank)."""
    order = sorted(
        range(len(scored)),
        key=lambda i: (-scored[i]["tournament_score"],
                       scored[i]["row"]["family"], scored[i]["row"]["rung"],
                       _pkey(scored[i]["row"]["params"])))
    for rank, i in enumerate(order):
        s = scored[i]
        r = s["row"]
        if r["family"] not in ELIGIBLE:
            continue  # RESEGMENT closed (hard exclusion)
        sd = float(r["features"].get("struct_distortion",
                                     r.get("struct_distortion", 0.0)))
        if not v2_structure_ok(r["family"], sd, V2_FROZEN):
            continue  # frozen v2 structural hard veto
        gate = s["p_bns"] if pointwise else s["p_vs_keep"]
        if gate < 0.5 + margin:
            continue  # margin gate vs KEEP / bns threshold
        return i, rank
    return None, None


def _committed_from_scored(eps_scored, margin, pointwise=False):
    committed = {}
    for uid, scored in eps_scored:
        idx, rank = _replay_scored(scored, margin, pointwise)
        committed[uid] = (scored[idx]["row"], rank) if idx is not None else None
    return committed


def _select_margin(eps_scored_cal, pointwise=False):
    """Maximise calibration bcov s.t. calibration CHR <= 0.10; fallback:
    lowest CHR then highest bcov, flagged calibration_degraded."""
    results = []
    for m in MARGIN_GRID:
        committed = _committed_from_scored(eps_scored_cal, m, pointwise)
        met = _episode_metrics(committed)
        results.append((m, met))
    feasible = [(m, met) for m, met in results
                if met["committed"] == 0
                or met["conditional_harm_rate"] <= CAL_CHR_CAP]
    if feasible:
        feasible.sort(key=lambda r: (-r[1]["beneficial_coverage"],
                                     r[1]["conditional_harm_rate"], r[0]))
        return feasible[0][0], False, feasible[0][1]
    results.sort(key=lambda r: (r[1]["conditional_harm_rate"],
                                -r[1]["beneficial_coverage"], r[0]))
    return results[0][0], True, results[0][1]


# -- deployment metrics (same definitions as v33_compare_arms) -----------------


def _episode_metrics(committed):
    """committed: uid -> (row, rank) or None. Window metadata read from the
    episode registry passed via the module-level _EPS (set in main)."""
    loss, prot_edit, cont_imp, cont_gain = [], [], [], []
    cond_losses = []
    n_commit = n_bs = 0
    prot_n = cont_n = cont_edit = 0
    per_ds_commit = Counter()
    per_fam_commit = Counter()
    per_ds_bs = Counter()
    for uid, got in committed.items():
        ep = _EPS[uid]
        pick = got[0] if got else None
        prot = ep["stratum"] in PROTECTED_STRATA
        cont = ep["stratum"] == "contaminated"
        loss.append(pick["true_loss"] if pick else 0.0)
        prot_edit.append(float(prot and pick is not None))
        if cont:
            cont_n += 1
            cont_gain.append(pick["true_repair_gain"] if pick else 0.0)
            cont_imp.append(float(bool(pick and pick["beneficial"])))
            cont_edit += int(pick is not None)
        if prot:
            prot_n += 1
        if pick is not None:
            n_commit += 1
            n_bs += int(bool(pick["beneficial_and_safe"]))
            cond_losses.append(pick["true_loss"])
            per_ds_commit[ep["dataset"]] += 1
            per_fam_commit[pick["family"]] += 1
            if pick["beneficial_and_safe"]:
                per_ds_bs[ep["dataset"]] += 1
    n = max(len(committed), 1)
    harmful = sum(1 for l in cond_losses if l > HARM_LOSS)
    return {
        "n_windows": len(committed),
        "committed": n_commit,
        "commit_rate": n_commit / n,
        "damage": float(np.mean(loss)) if loss else 0.0,
        "conditional_harm_rate": harmful / n_commit if n_commit else 0.0,
        "harmful_commits": harmful,
        "beneficial_commits": n_bs,
        "protected_mis_edit_rate": sum(prot_edit) / max(prot_n, 1),
        "coverage": cont_edit / max(cont_n, 1),
        "beneficial_coverage": float(np.mean(cont_imp)) if cont_imp else 0.0,
        "mean_repair_gain_contaminated":
            float(np.mean(cont_gain)) if cont_gain else 0.0,
        "commit_by_source": dict(per_ds_commit),
        "commit_by_family": dict(per_fam_commit),
        "bs_by_source": dict(per_ds_bs),
    }


def _oracle_committed(eps_list):
    committed = {}
    for ep in eps_list:
        bs = [r for r in ep["cands"]
              if r["beneficial_and_safe"] and r["family"] in ELIGIBLE]
        pick = max(bs, key=lambda r: r["true_repair_gain"]) if bs else None
        committed[ep["sample_uid"]] = (pick, None) if pick else None
    return committed


# -- learning metrics -----------------------------------------------------------


def _pair_vectors(p, eps, kind, vec_cache):
    dim = _dim(kind)
    uid = p["sample_uid"]
    if uid not in vec_cache:
        V = _vectors(eps[uid], kind)
        vec_cache[uid] = {_ckey(uid, c["family"], c["rung"], c["params"]): V[k]
                          for k, c in enumerate(eps[uid]["cands"])}
    cmap = vec_cache[uid]
    zero = np.zeros(dim)
    vi = cmap.get(_ckey(uid, p["cand_i"]["family"], p["cand_i"]["rung"],
                        p["cand_i"]["params"]), zero)
    vj = cmap.get(_ckey(uid, p["cand_j"]["family"], p["cand_j"]["rung"],
                        p["cand_j"]["params"]), zero)
    return vi, vj


def _learn_metrics(model, test_pairs, eps, kind, is_logreg):
    """Pairwise metrics on the held-out fold, both directions (see the
    module docstring for why both directions are used for AUROC/AUPRC)."""
    from sklearn.metrics import (accuracy_score, average_precision_score,
                                 roc_auc_score)
    if not test_pairs:
        return {"n_pairs": 0}, np.zeros(0, dtype=int), np.zeros(0)
    dim = _dim(kind)
    VI = np.zeros((len(test_pairs), dim))
    VJ = np.zeros((len(test_pairs), dim))
    y = np.zeros(len(test_pairs), dtype=int)
    vec_cache = {}
    for i, p in enumerate(test_pairs):
        VI[i], VJ[i] = _pair_vectors(p, eps, kind, vec_cache)
        y[i] = int(p["label"])
    s = _sym_pair_proba(model, VI, VJ, is_logreg)
    out = {"n_pairs": int(len(y)),
           "pairwise_accuracy": float(accuracy_score(y, s > 0.5))}
    if len(set(y.tolist())) > 1:
        out["auroc"] = float(roc_auc_score(y, s))
        out["auprc"] = float(average_precision_score(y, s))
    else:
        out["auroc"] = out["auprc"] = None
    return out, y, s


def _fit_check(model, X, y):
    """In-sample pairwise accuracy on the model's own train pairs: separates
    'features cannot fit the labels' from 'features fit but do not transfer'."""
    p1 = _proba(model, X)
    p2 = _proba(model, -X)
    s = 0.5 * (p1 + 1.0 - p2)
    return float(np.mean((s > 0.5) == y))


def _pkeep_auroc(scored_eps):
    """AUROC of p(c≻KEEP) against eval beneficial_and_safe over all scored
    candidates — a per-fold deployment-facing discrimination check."""
    from sklearn.metrics import roc_auc_score
    ys, ss = [], []
    for uid, scored in scored_eps:
        for s in scored:
            ys.append(int(bool(s["row"]["beneficial_and_safe"])))
            ss.append(s["p_vs_keep"])
    if len(set(ys)) < 2:
        return None
    return float(roc_auc_score(ys, ss))


def _top1_rows(eps_scored):
    """Top-1 by tournament score among eligible candidates (gates off)."""
    rows = []
    for uid, scored in eps_scored:
        ep = _EPS[uid]
        elig = [s for s in scored if s["row"]["family"] in ELIGIBLE]
        if not elig:
            continue
        top = max(elig, key=lambda s: s["tournament_score"])
        r = top["row"]
        rows.append({"sample_uid": uid, "dataset": ep["dataset"],
                     "stratum": ep["stratum"], "true_kind": ep["true_kind"],
                     "family": r["family"],
                     "bns": bool(r["beneficial_and_safe"]),
                     "harmful": bool(r["true_loss"] > HARM_LOSS),
                     "gain": r["true_repair_gain"]})
    return rows


def _top1_agg(rows):
    n = max(len(rows), 1)
    agg = {"n": len(rows),
           "top1_bs_precision": sum(r["bns"] for r in rows) / n,
           "top1_harmful_rate": sum(r["harmful"] for r in rows) / n}

    def _strata(key):
        out = {}
        for k in sorted({str(r[key]) for r in rows}):
            sub = [r for r in rows if str(r[key]) == k]
            m = max(len(sub), 1)
            out[k] = {"n": len(sub),
                      "top1_bs_precision": sum(r["bns"] for r in sub) / m,
                      "top1_harmful_rate": sum(r["harmful"] for r in sub) / m}
        return out
    agg["by_family"] = _strata("family")
    agg["by_stratum"] = _strata("stratum")
    agg["by_true_kind"] = _strata("true_kind")
    return agg


def _regret(committed):
    """Selected-action regret vs oracle-best (max-gain B&S, KEEP=0 floor)."""
    vals = []
    by_kind = defaultdict(list)
    for uid, got in committed.items():
        ep = _EPS[uid]
        bs = [r for r in ep["cands"]
              if r["beneficial_and_safe"] and r["family"] in ELIGIBLE]
        oracle_gain = max([r["true_repair_gain"] for r in bs], default=0.0)
        gain = got[0]["true_repair_gain"] if got else 0.0
        reg = oracle_gain - gain
        vals.append(reg)
        by_kind[ep["true_kind"]].append(reg)
    return {"mean_regret": float(np.mean(vals)) if vals else 0.0,
            "mean_regret_by_true_kind": {
                str(k): float(np.mean(v)) for k, v in sorted(by_kind.items())}}


_EPS = {}  # episode registry for metric functions


# -- main ---------------------------------------------------------------------


def main():
    global _EPS
    t0 = time.time()
    pairs, rows = _load()
    eps = _build_episodes(rows)
    _EPS = eps
    row_index, integrity_msgs = _integrity(pairs, eps)
    for m in integrity_msgs:
        print("[integrity]", m, flush=True)

    frozen = json.load(FROZEN_PATH.open(encoding="utf-8"))
    frozen_commits = json.load(FROZEN_COMMITS_PATH.open(encoding="utf-8"))
    pics_frozen = {k: v for k, v in frozen["arms"]["PICS_joint_relabel"].items()
                   if not k.startswith("_")}

    # Split helper identical to v32_compare_arms._split, on episode ids.
    def split_uids(test_ds):
        rest = sorted(uid for uid, ep in eps.items()
                      if ep["dataset"] != test_ds
                      and not ep["dataset"].startswith("ood:"))
        rng = np.random.RandomState(SPLIT_SEED)
        rng.shuffle(rest)
        n_train = int(0.8 * len(rest))
        return set(rest[:n_train]), set(rest[n_train:])

    # Training uses both (i,j) and (j,i) symmetric pairs as frozen.
    pairs_by_uid = defaultdict(list)
    for p in pairs:
        pairs_by_uid[p["sample_uid"]].append(p)

    pair_arms = (("PAIR_episode_relative", "relative"),
                 ("PAIR_absolute", "absolute"))
    model_kinds = ("hgb", "logreg")
    arm_keys = [(a, k) for a, _ in pair_arms for k in model_kinds]
    arm_keys += [("pointwise_same_features", k) for k in model_kinds]

    real_eps = [ep for uid, ep in eps.items()
                if not ep["dataset"].startswith("ood:")]
    ood_eps = [ep for uid, ep in eps.items()
               if ep["dataset"].startswith("ood:")]

    folds = {a: {} for a, _ in pair_arms}
    folds["pointwise_same_features"] = {}
    cal_report = {}
    pooled_committed = {k: {} for k in arm_keys}
    pooled_learn_parts = {k: ([], []) for k in arm_keys[:4]}
    pooled_top1 = {k: [] for k in arm_keys}
    ood_edits = {k: [] for k in arm_keys}
    pred_lines = []
    scored_decision_by_uid = {}  # for the harmful-commit ledger

    for test_ds in REAL_SOURCES:
        test_eps = [ep for uid, ep in eps.items() if ep["dataset"] == test_ds]
        train_uids, cal_uids = split_uids(test_ds)
        cal_eps = [eps[uid] for uid in sorted(cal_uids)]
        train_pairs = [p for uid in sorted(train_uids)
                       for p in pairs_by_uid[uid]]
        test_pairs_all = [p for ep in test_eps
                          for p in pairs_by_uid[ep["sample_uid"]]]
        w_pairs = _src_weights([p["dataset"] for p in train_pairs])
        y_pairs = np.array([int(p["label"]) for p in train_pairs])

        for arm, kind in pair_arms:
            dim = _dim(kind)
            X = np.zeros((len(train_pairs), dim))
            vec_cache = {}
            for i, p in enumerate(train_pairs):
                vi, vj = _pair_vectors(p, eps, kind, vec_cache)
                X[i] = vi - vj
            for mk in model_kinds:
                key = (arm, mk)
                is_lr = mk == "logreg"
                model = (_fit_logreg(X, y_pairs, w_pairs) if is_lr
                         else _fit_hgb(X, y_pairs, w_pairs))
                train_acc = _fit_check(model, X, y_pairs)
                scored_cal = [(ep["sample_uid"],
                               _score_episode(model, ep, kind, is_lr))
                              for ep in cal_eps]
                scored_test = [(ep["sample_uid"],
                                _score_episode(model, ep, kind, is_lr))
                               for ep in test_eps]
                scored_ood = [(ep["sample_uid"],
                               _score_episode(model, ep, kind, is_lr))
                              for ep in ood_eps]
                margin, degraded, cal_met = _select_margin(scored_cal)
                cal_report.setdefault(arm, {}).setdefault(test_ds, {})[mk] = {
                    "margin": margin, "calibration_degraded": degraded,
                    "cal_bcov": cal_met["beneficial_coverage"],
                    "cal_chr": cal_met["conditional_harm_rate"],
                    "cal_commits": cal_met["committed"]}
                committed = _committed_from_scored(scored_test, margin)
                pooled_committed[key].update(committed)
                if key == ("PAIR_episode_relative", "hgb"):
                    scored_decision_by_uid.update(dict(scored_test))
                fmet = _episode_metrics(committed)
                fmet["top1"] = _top1_agg(_top1_rows(scored_test))
                fmet["regret"] = _regret(committed)
                lm, y, s = _learn_metrics(model, test_pairs_all, eps, kind,
                                          is_lr)
                lm["train_pairwise_accuracy"] = train_acc
                lm["pkeep_bns_auroc"] = _pkeep_auroc(scored_test)
                fmet["learning"] = lm
                folds[arm].setdefault(test_ds, {})[mk] = fmet
                pooled_learn_parts[key][0].append(y)
                pooled_learn_parts[key][1].append(s)
                pooled_top1[key].extend(_top1_rows(scored_test))
                oc = _committed_from_scored(scored_ood, margin)
                ood_edits[key].append(
                    sum(1 for v in oc.values() if v) / max(len(oc), 1))
                by_uid_scored = dict(scored_test)
                for ep in test_eps:
                    scored = by_uid_scored[ep["sample_uid"]]
                    got = committed[ep["sample_uid"]]
                    for sc in scored:
                        r = sc["row"]
                        pred_lines.append({
                            "fold": test_ds, "arm": arm, "model": mk,
                            "sample_uid": ep["sample_uid"],
                            "dataset": ep["dataset"],
                            "stratum": ep["stratum"],
                            "true_kind": ep["true_kind"],
                            "family": r["family"], "rung": r["rung"],
                            "params": r["params"],
                            "p_vs_keep": sc["p_vs_keep"],
                            "mean_p_vs_others": sc["mean_p_vs_others"],
                            "tournament_score": sc["tournament_score"],
                            "margin": margin,
                            "veto_resegment": r["family"] not in ELIGIBLE,
                            "veto_structure": not v2_structure_ok(
                                r["family"],
                                float(r["features"].get(
                                    "struct_distortion",
                                    r.get("struct_distortion", 0.0))),
                                V2_FROZEN),
                            "selected": bool(got and got[0] is r),
                            "eval_bns": bool(r["beneficial_and_safe"]),
                            "eval_beneficial": bool(r["beneficial"]),
                            "eval_true_loss": r["true_loss"],
                            "eval_true_gain": r["true_repair_gain"]})

        # pointwise arm: same per-candidate feature vector as
        # PAIR_episode_relative, direct P(beneficial_and_safe).
        train_cands = [(uid, k) for uid in sorted(train_uids)
                       for k in range(len(eps[uid]["cands"]))]
        Xp = np.zeros((len(train_cands), _dim("relative")))
        yp = np.zeros(len(train_cands), dtype=int)
        srcs = []
        vecs_rel = {}
        for i, (uid, k) in enumerate(train_cands):
            if uid not in vecs_rel:
                vecs_rel[uid] = _vectors(eps[uid], "relative")
            Xp[i] = vecs_rel[uid][k]
            r = eps[uid]["cands"][k]
            yp[i] = int(bool(r["beneficial_and_safe"]))
            srcs.append(r["dataset"])
        wp = _src_weights(srcs)
        for mk in model_kinds:
            key = ("pointwise_same_features", mk)
            is_lr = mk == "logreg"
            model = (_fit_logreg(Xp, yp, wp) if is_lr
                     else _fit_hgb(Xp, yp, wp))
            scored_cal = [(ep["sample_uid"],
                           _score_episode_pointwise(model, ep, is_lr))
                          for ep in cal_eps]
            scored_test = [(ep["sample_uid"],
                            _score_episode_pointwise(model, ep, is_lr))
                           for ep in test_eps]
            scored_ood = [(ep["sample_uid"],
                           _score_episode_pointwise(model, ep, is_lr))
                          for ep in ood_eps]
            margin, degraded, cal_met = _select_margin(
                scored_cal, pointwise=True)
            cal_report.setdefault("pointwise_same_features", {}).setdefault(
                test_ds, {})[mk] = {
                "margin": margin, "calibration_degraded": degraded,
                "cal_bcov": cal_met["beneficial_coverage"],
                "cal_chr": cal_met["conditional_harm_rate"],
                "cal_commits": cal_met["committed"]}
            committed = _committed_from_scored(scored_test, margin,
                                               pointwise=True)
            pooled_committed[key].update(committed)
            fmet = _episode_metrics(committed)
            fmet["top1"] = _top1_agg(_top1_rows(scored_test))
            fmet["regret"] = _regret(committed)
            folds["pointwise_same_features"].setdefault(
                test_ds, {})[mk] = fmet
            pooled_top1[key].extend(_top1_rows(scored_test))
            oc = _committed_from_scored(scored_ood, margin, pointwise=True)
            ood_edits[key].append(
                sum(1 for v in oc.values() if v) / max(len(oc), 1))
            by_uid_scored = dict(scored_test)
            for ep in test_eps:
                scored = by_uid_scored[ep["sample_uid"]]
                got = committed[ep["sample_uid"]]
                for sc in scored:
                    r = sc["row"]
                    pred_lines.append({
                        "fold": test_ds,
                        "arm": "pointwise_same_features", "model": mk,
                        "sample_uid": ep["sample_uid"],
                        "dataset": ep["dataset"], "stratum": ep["stratum"],
                        "true_kind": ep["true_kind"],
                        "family": r["family"], "rung": r["rung"],
                        "params": r["params"],
                        "p_bns": sc["p_bns"],
                        "tournament_score": sc["tournament_score"],
                        "margin": margin,
                        "veto_resegment": r["family"] not in ELIGIBLE,
                        "veto_structure": not v2_structure_ok(
                            r["family"],
                            float(r["features"].get(
                                "struct_distortion",
                                r.get("struct_distortion", 0.0))),
                            V2_FROZEN),
                        "selected": bool(got and got[0] is r),
                        "eval_bns": bool(r["beneficial_and_safe"]),
                        "eval_beneficial": bool(r["beneficial"]),
                        "eval_true_loss": r["true_loss"],
                        "eval_true_gain": r["true_repair_gain"]})
        mh = folds["PAIR_episode_relative"][test_ds]["hgb"]
        print(f"[fold {test_ds}] PAIR_rel/hgb bcov="
              f"{mh['beneficial_coverage']:.4f} "
              f"CHR={mh['conditional_harm_rate']:.3f} "
              f"acc={mh['learning']['pairwise_accuracy']:.3f} "
              f"train_acc={mh['learning']['train_pairwise_accuracy']:.3f}",
              flush=True)

    # -- pooled metrics ---------------------------------------------------------
    from sklearn.metrics import (accuracy_score, average_precision_score,
                                 roc_auc_score)
    pooled = {}
    for key in arm_keys:
        name = f"{key[0]}/{key[1]}"
        pooled[name] = _episode_metrics(pooled_committed[key])
        pooled[name]["regret"] = _regret(pooled_committed[key])
        pooled[name]["top1"] = _top1_agg(pooled_top1[key])
        if key in pooled_learn_parts:
            y = np.concatenate(pooled_learn_parts[key][0])
            s = np.concatenate(pooled_learn_parts[key][1])
            pooled[name]["learning"] = {
                "n_pairs": int(len(y)),
                "pairwise_accuracy": float(accuracy_score(y, s > 0.5)),
                "auroc": float(roc_auc_score(y, s)),
                "auprc": float(average_precision_score(y, s)),
            }
    oracle_comm = _oracle_committed(real_eps)
    pooled["oracle_relabel"] = _episode_metrics(oracle_comm)
    pooled["oracle_relabel"]["regret"] = _regret(oracle_comm)
    pooled["PICS_joint_relabel"] = pics_frozen

    # -- §10 attribution diagnostics (decision arm) ------------------------------
    dec_key = ("PAIR_episode_relative", "hgb")
    dec_committed = pooled_committed[dec_key]
    harmful_ledger = []
    for uid, got in sorted(dec_committed.items()):
        if not got:
            continue
        r, rank = got
        if r["true_loss"] <= HARM_LOSS:
            continue
        ep = eps[uid]
        sc = scored_decision_by_uid.get(uid, [])
        srow = next((s for s in sc if s["row"] is r), {})
        harmful_ledger.append({
            "sample_uid": uid, "dataset": ep["dataset"],
            "stratum": ep["stratum"], "true_kind": ep["true_kind"],
            "family": r["family"], "rung": r["rung"], "params": r["params"],
            "true_loss": r["true_loss"],
            "true_repair_gain": r["true_repair_gain"],
            "episode_rank": rank,
            "p_vs_keep": srow.get("p_vs_keep"),
            "mean_p_vs_others": srow.get("mean_p_vs_others"),
            "tournament_score": srow.get("tournament_score"),
        })
    # PICS-vs-PAIR commit divergence against the frozen incumbent records
    pics_keys = {_ckey(c["sample_uid"], c["family"], c["rung"], c["params"])
                 for c in frozen_commits["PICS_joint_relabel"]["all_commits"]}
    pair_keys = {_ckey(uid, got[0]["family"], got[0]["rung"],
                       got[0]["params"])
                 for uid, got in dec_committed.items() if got}
    both = pics_keys & pair_keys
    pics_only = sorted(pics_keys - pair_keys)
    pair_only = sorted(pair_keys - pics_keys)

    def _truth(k):
        r = row_index.get(k)
        if r is None:
            return {}
        return {"bns": bool(r["beneficial_and_safe"]),
                "harmful": bool(r["true_loss"] > HARM_LOSS),
                "true_loss": r["true_loss"],
                "true_repair_gain": r["true_repair_gain"]}

    divergence = {
        "pics_commits": len(pics_keys), "pair_commits": len(pair_keys),
        "both": len(both),
        "pics_only": len(pics_only),
        "pair_only": len(pair_only),
        "pics_only_truth": Counter(
            ("bns" if _truth(k).get("bns")
             else "harmful" if _truth(k).get("harmful") else "neutral")
            for k in pics_only),
        "pair_only_truth": Counter(
            ("bns" if _truth(k).get("bns")
             else "harmful" if _truth(k).get("harmful") else "neutral")
            for k in pair_only),
    }
    # cross-source transfer: per-fold held-out vs in-sample gap
    transfer = {d: {
        "heldout_pair_acc":
            folds["PAIR_episode_relative"][d]["hgb"]["learning"]
            ["pairwise_accuracy"],
        "train_pair_acc":
            folds["PAIR_episode_relative"][d]["hgb"]["learning"]
            ["train_pairwise_accuracy"],
        "pkeep_bns_auroc":
            folds["PAIR_episode_relative"][d]["hgb"]["learning"]
            ["pkeep_bns_auroc"],
    } for d in REAL_SOURCES}

    # -- gates (decision arm: PAIR_episode_relative / hgb) ----------------------
    dec = pooled["PAIR_episode_relative/hgb"]
    pics = pics_frozen
    accs = {d: folds["PAIR_episode_relative"][d]["hgb"]["learning"]
            ["pairwise_accuracy"] for d in REAL_SOURCES}
    frontier_green = (
        (dec["beneficial_coverage"] >= pics["beneficial_coverage"]
         and dec["conditional_harm_rate"] <= 0.144)
        or (dec["conditional_harm_rate"] <= pics["conditional_harm_rate"]
            and dec["beneficial_coverage"]
            >= pics["beneficial_coverage"] + 0.03))
    fams_with_bs = set()
    for uid, got in dec_committed.items():
        if got and got[0]["beneficial_and_safe"]:
            fams_with_bs.add(got[0]["family"])
    imp_sources = 0
    for d in REAL_SOURCES:
        m = folds["PAIR_episode_relative"][d]["hgb"]
        p = frozen["folds"]["PICS_joint_relabel"][d]
        if (m["beneficial_coverage"] > p["beneficial_coverage"]
                or m["conditional_harm_rate"] < p["conditional_harm_rate"]):
            imp_sources += 1
    pw = pooled["pointwise_same_features/hgb"]

    def _dominates(a, b):
        cov_a, chr_a = a["beneficial_coverage"], a["conditional_harm_rate"]
        cov_b, chr_b = b["beneficial_coverage"], b["conditional_harm_rate"]
        return (cov_a >= cov_b and chr_a < chr_b) or (
            chr_a <= chr_b and cov_a > cov_b)

    frontier_vs_controls = _dominates(dec, pics) and _dominates(dec, pw)
    gates = {
        "decision_arm": "PAIR_episode_relative/hgb",
        "items": {
            "pooled_pairwise_accuracy>=0.70": {
                "value": dec["learning"]["pairwise_accuracy"],
                "pass": dec["learning"]["pairwise_accuracy"] >= 0.70},
            "sources>=5/6_with_acc>=0.60": {
                "value": {"n_ge_0.60": int(sum(a >= 0.60
                                               for a in accs.values())),
                          "by_source": accs},
                "pass": int(sum(a >= 0.60 for a in accs.values())) >= 5},
            "frontier_green": {
                "rule": "(bcov>=0.2727 and CHR<=0.144) or "
                        "(CHR<=PICS and bcov>=PICS+0.03)",
                "value": {"bcov": dec["beneficial_coverage"],
                          "chr": dec["conditional_harm_rate"]},
                "pass": bool(frontier_green)},
            "gain>=0.0919": {
                "value": dec["mean_repair_gain_contaminated"],
                "pass": dec["mean_repair_gain_contaminated"]
                >= pics["mean_repair_gain_contaminated"]},
            "damage<=0.0402": {
                "value": dec["damage"],
                "pass": dec["damage"] <= pics["damage"]},
            ">=2_families_with_beneficial_commit": {
                "value": sorted(fams_with_bs),
                "pass": len(fams_with_bs) >= 2},
        },
        "diagnostics": {
            "frontier_better_than_pics_and_pointwise":
                bool(frontier_vs_controls),
            "sources_improved_vs_pics": imp_sources,
        },
    }
    all_green = all(v["pass"] for v in gates["items"].values())
    acc = dec["learning"]["pairwise_accuracy"]
    if all_green:
        light = "GREEN"
    elif acc < 0.60 or not frontier_vs_controls or imp_sources <= 1:
        light = "RED"
    elif acc >= 0.65:
        light = "YELLOW"
    else:
        light = "RED"
    gates["light"] = light

    # -- write outputs ----------------------------------------------------------
    out = {
        "phase": "v3.6 Phase 1 PAIR probe",
        "preregistration": "docs/v3_6_pair_preregistration.md §5–§6",
        "integrity": integrity_msgs,
        "config": {
            "hgb": HGB_CFG,
            "logreg": LOGREG_CFG,
            "margin_grid": list(MARGIN_GRID),
            "cal_chr_cap": CAL_CHR_CAP,
            "split": "leave-one-real-dataset-out, 80/20 train/cal by "
                     "sample_uid, seed 20260901 (same as incumbent)",
            "sample_weight": "w_p = 1 / (S_train * N_train(source(p))); "
                             "every training source totals 1/S_train",
            "tournament_score": "p(c≻KEEP) + mean p(c≻j) over eligible j!=c; "
                                "KEEP vector fixed to zeros; score symmetrised"
                                " as 0.5*(f(d)+1-f(-d))",
            "base_features": list(BASE_FEATURES),
            "transforms": list(TRANSFORMS),
            "interactions": [list(t) for t in INTERACTIONS],
            "families": list(FAMILIES),
            "eligible_families": list(EPISODE_FAMILY_ORDER),
            "keep_convention": "implicit action, zero feature vector",
            "hard_veto": "v2_structure_ok (V2_FROZEN taus); RESEGMENT closed",
            "harm_loss_threshold": HARM_LOSS,
            "learning_metric_convention":
                "forward pairs canonical winner-first (label always 1); "
                "accuracy identical under exact antisymmetry; AUROC/AUPRC "
                "computed on both directions",
        },
        "hashes": {
            "pair_dataset": _sha256(PAIR_PATH),
            "training_rows": _sha256(ROWS_PATH),
            "frozen_incumbent": _sha256(FROZEN_PATH),
            "frozen_incumbent_commits": _sha256(FROZEN_COMMITS_PATH),
            "code": _sha256(Path(__file__).resolve()),
        },
        "environment": {"sklearn": __import__("sklearn").__version__,
                        "numpy": np.__version__, "device": "CPU"},
        "pooled": pooled,
        "folds": folds,
        "calibration": cal_report,
        "attribution": {
            "harmful_commit_ledger": harmful_ledger,
            "pics_vs_pair_divergence": {
                k: (dict(v) if isinstance(v, Counter) else v)
                for k, v in divergence.items()},
            "cross_source_transfer": transfer,
        },
        "ood_stress_dev_only": {
            f"{a}/{k}": {"ood_edit_rate_mean_over_folds":
                         float(np.mean(ood_edits[(a, k)]))}
            for (a, k) in ood_edits},
        "pics_frozen_replay": {
            "pooled": pics_frozen,
            "folds": frozen["folds"]["PICS_joint_relabel"]},
        "gates": gates,
        "runtime_sec": time.time() - t0,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    with OUT_PRED.open("w", encoding="utf-8") as f:
        for line in pred_lines:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    print(f"[done] light={light} runtime={time.time() - t0:.1f}s -> "
          f"{OUT_JSON.name}, {OUT_PRED.name} ({len(pred_lines)} lines)",
          flush=True)


if __name__ == "__main__":
    main()
