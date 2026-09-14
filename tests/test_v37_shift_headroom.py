"""Tests for v3.7 Phase 0 (docs/v3_7_shift_preregistration.md §3).

Covers: reproduction consistency vs frozen v3.6 records (sampled folds,
per-value, <1e-9); oracle grid determinism; constraint/metric logic
cross-checked against the v33/v36 口径 (``v36_pair_ranker_probe._episode_metrics``
and hand-computed values); transfer matrix shape/symmetry.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

import v36_pair_ranker_probe as v36  # noqa: E402
import v37_shift_headroom as v37  # noqa: E402

HEADROOM = ROOT / "results" / "v37_shift_headroom.json"
TRANSFER = ROOT / "results" / "v37_calibration_transfer.json"


@pytest.fixture(scope="module")
def headroom():
    if not HEADROOM.exists():
        pytest.skip("run experiments/v37_shift_headroom.py first")
    return json.load(HEADROOM.open(encoding="utf-8"))


@pytest.fixture(scope="module")
def transfer():
    if not TRANSFER.exists():
        pytest.skip("run experiments/v37_shift_headroom.py first")
    return json.load(TRANSFER.open(encoding="utf-8"))


# -- §3.1 reproduction ---------------------------------------------------------


def test_reproduction_within_tolerance(headroom):
    repro = headroom["reproduction"]
    assert repro["pass"], "reproduction breached 1e-9; see per_fold block"
    assert repro["max_abs_diff_overall"] < 1e-9
    for fold, cmp_ in repro["per_fold"].items():
        assert cmp_["pass"], fold
        assert cmp_["max_abs_diff"] < 1e-9, fold
        assert cmp_["exact"]["int_and_distribution_match"], fold
        assert cmp_["exact"]["selected_match"], fold
        assert cmp_["exact"]["veto_mismatch"] == 0, fold


def test_reproduction_candidate_samples_per_value(headroom):
    """Sampled folds, per candidate value: got vs frozen v3.6 predictions."""
    repro = headroom["reproduction"]
    sampled = 0
    for fold, cmp_ in repro["per_fold"].items():
        for s in cmp_["candidate_sample"]:
            assert abs(s["got_p_vs_keep"] - s["ref_p_vs_keep"]) < 1e-9, (
                fold, s["candidate"])
            assert abs(s["got_tournament"] - s["ref_tournament"]) < 1e-9, (
                fold, s["candidate"])
            sampled += 1
    assert sampled >= 6 * 10  # 6 folds x 10 deterministic samples


def test_reproduction_hashes_recorded(headroom):
    hashes = headroom["hashes"]
    for key in ("v36_pair_probe", "v36_pair_predictions", "v36_pair_dataset",
                "v33_training_data", "v33_clean_rerun", "v36_code", "code"):
        assert len(hashes[key]) == 64, key


# -- §3.2 grid determinism -------------------------------------------------------


def test_simplex_grid_deterministic():
    g1 = v37.simplex_grid(5)
    g2 = v37.simplex_grid(5)
    assert g1 == g2
    assert len(g1) == 70  # C(4+5-1, 5-1) compositions at step 1/4
    for w in g1:
        assert len(w) == 5
        assert abs(sum(w) - 1.0) < 1e-12
        for x in w:
            assert abs(x * 4 - round(x * 4)) < 1e-12  # on the 1/4 grid
    # descending lexicographic enumeration
    assert g1 == sorted(g1, reverse=True)


def test_margin_grid_fixed():
    assert v37.ORACLE_MARGIN_GRID == tuple(
        round(0.05 * i, 2) for i in range(9))


# -- §3.2 constraint/metric logic vs v33 口径 -------------------------------------


def _fake_ep(uid, stratum, cands):
    return {"sample_uid": uid, "dataset": "T", "stratum": stratum,
            "true_kind": "noise", "cands": cands}


def _fake_row(fam, rung, loss, gain, benef, bns, sd=0.0):
    return {"family": fam, "rung": rung, "params": {"p": rung},
            "features": {"struct_distortion": sd},
            "true_loss": loss, "true_repair_gain": gain,
            "beneficial": benef, "beneficial_and_safe": bns}


def _synthetic_fixture():
    """4 windows: 2 contaminated (one harmful candidate, one beneficial),
    1 protected clean, 1 protected hard. Scores chosen so the first-commit
    order is c0 > c1 in every episode."""
    eps = [
        _fake_ep("u1", "contaminated", [
            _fake_row("DENOISE", "default", 0.5, 0.0, False, False),
            _fake_row("IMPUTE", "default", 0.0, 0.3, True, True)]),
        _fake_ep("u2", "contaminated", [
            _fake_row("DENOISE", "default", 0.0, 0.4, True, True),
            _fake_row("IMPUTE", "default", 0.2, 0.1, True, False)]),
        _fake_ep("u3", "clean", [
            _fake_row("DENOISE", "default", 0.0, 0.0, False, True),
            _fake_row("IMPUTE", "default", 0.0, 0.0, False, False)]),
        _fake_ep("u4", "hard", [
            _fake_row("DENOISE", "default", 0.6, 0.0, False, False),
            _fake_row("IMPUTE", "default", 0.0, 0.0, False, True)]),
    ]
    scores = {"u1": [0.90, 0.70], "u2": [0.85, 0.65],
              "u3": [0.80, 0.60], "u4": [0.95, 0.55]}
    scored = []
    for ep in eps:
        scored.append([
            {"row": r, "p_vs_keep": p, "tournament_score": p}
            for r, p in zip(ep["cands"], scores[ep["sample_uid"]])])
    return eps, scored


def test_sweep_matches_v36_episode_metrics():
    eps, scored = _synthetic_fixture()
    v36._EPS = {ep["sample_uid"]: ep for ep in eps}
    blocks = [v37._scored_arrays(sc, "p_vs_keep", "tournament_score")
              for sc in scored]
    meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
             "cont": ep["stratum"] == "contaminated"} for ep in eps]
    combos, metrics, sel_rows = v37.sweep_margins(blocks, meta)
    # probe several grid points, including all-pass and all-blocked margins
    for k in (0, 40, len(combos) - 1):
        sel = np.array([r[k] for r in sel_rows])
        exact, _ = v37._exact_metrics(sel, blocks, eps)
        assert abs(exact["conditional_harm_rate"]
                   - metrics["chr"][k]) < 1e-12
        assert abs(exact["protected_mis_edit_rate"]
                   - metrics["pme"][k]) < 1e-12
        assert abs(exact["beneficial_coverage"]
                   - metrics["bcov"][k]) < 1e-12
        assert abs(exact["mean_repair_gain_contaminated"]
                   - metrics["gain"][k]) < 1e-12
        assert abs(exact["damage"] - metrics["damage"][k]) < 1e-12
        assert exact["committed"] == int(metrics["committed"][k])


def test_constraint_formulas_hand_computed():
    """Hand-check the v33 口径: CHR = share of commits with true_loss>0.03;
    pme = protected edits / protected windows; bcov/gain averaged over
    contaminated windows only; damage = mean true_loss over all windows."""
    eps, scored = _synthetic_fixture()
    v36._EPS = {ep["sample_uid"]: ep for ep in eps}
    blocks = [v37._scored_arrays(sc, "p_vs_keep", "tournament_score")
              for sc in scored]
    meta = [{"prot": ep["stratum"] in v36.PROTECTED_STRATA,
             "cont": ep["stratum"] == "contaminated"} for ep in eps]
    # margin 0 everywhere -> every episode commits its top candidate (c0)
    combos, metrics, _ = v37.sweep_margins(
        blocks, meta, margin_grid=(0.0,))
    # commits: u1 harmful DENOISE (0.5), u2 bns DENOISE (0.0/0.4),
    #          u3 clean edit (0.0), u4 harmful DENOISE (0.6)
    assert metrics["committed"][0] == 4
    assert metrics["chr"][0] == pytest.approx(2 / 4)
    assert metrics["pme"][0] == pytest.approx(2 / 2)
    assert metrics["bcov"][0] == pytest.approx((0 + 1) / 2)
    assert metrics["gain"][0] == pytest.approx((0.0 + 0.4) / 2)
    assert metrics["damage"][0] == pytest.approx((0.5 + 0.0 + 0.0 + 0.6) / 4)
    # per-family blocking: margin 0.5 on DENOISE only (grid index of
    # (0.5, 0.0, 0.0) in product((0.0, 0.5), repeat=3) is 4). Every episode
    # then falls through to its IMPUTE candidate.
    combos2, metrics2, _ = v37.sweep_margins(
        blocks, meta, margin_grid=(0.0, 0.5))
    assert combos2.shape[1] == 3  # per-family margins
    k = 4  # margins (DENOISE=0.5, DESPIKE=0.0, IMPUTE=0.0)
    assert tuple(combos2[k]) == (0.5, 0.0, 0.0)
    # commits: u1 IMPUTE bns (0.0/0.3), u2 IMPUTE harmful (0.2/0.1),
    #          u3 IMPUTE protected edit, u4 IMPUTE protected edit
    assert metrics2["committed"][k] == 4
    assert metrics2["chr"][k] == pytest.approx(1 / 4)
    assert metrics2["pme"][k] == pytest.approx(1.0)
    assert metrics2["bcov"][k] == pytest.approx(1.0)
    assert metrics2["gain"][k] == pytest.approx((0.3 + 0.1) / 2)
    assert metrics2["damage"][k] == pytest.approx(0.2 / 4)


def test_pick_best_deterministic_and_constraint_aware():
    metrics = {
        "chr": np.array([0.20, 0.05, 0.05, 0.09]),
        "pme": np.array([0.0, 0.0, 0.0, 0.0]),
        "damage": np.array([0.01, 0.01, 0.05, 0.01]),
        "bcov": np.array([0.50, 0.30, 0.40, 0.30]),
        "gain": np.array([0.20, 0.10, 0.15, 0.12]),
        "committed": np.array([5, 5, 5, 5]),
    }
    combos = np.zeros((4, 3))
    # idx0 infeasible (CHR), idx2 infeasible (damage); idx1 vs idx3 tie on
    # bcov -> higher gain wins (idx3)
    b1, f1 = v37._pick_best(combos, metrics)
    b2, f2 = v37._pick_best(combos, metrics)
    assert b1 == b2 == 3 and f1 and f2
    # nothing feasible -> fallback flags infeasible, deterministic
    metrics["chr"][:] = 0.5
    b3, f3 = v37._pick_best(combos, metrics)
    b4, f4 = v37._pick_best(combos, metrics)
    assert not f3 and b3 == b4


def test_oracle_verdict_block_consistent(headroom):
    oracle = headroom["oracle"]
    assert oracle is not None
    v = oracle["verdict"]
    g, e = v["global_pooled"], v["expert_mixture_pooled"]
    g_ok = g["bcov"] >= 0.30 and g["gain"] >= 0.10
    e_ok = e["bcov"] >= 0.30 and e["gain"] >= 0.10
    assert v["global_oracle_ok"] == g_ok
    assert v["expert_mixture_oracle_ok"] == e_ok
    if not g_ok and not e_ok:
        assert v["light"] == "RED" and v["phase1_primary_arm"] is None
    elif g_ok:
        assert v["phase1_primary_arm"] == "SHIFT_global_IW"
    else:
        assert v["phase1_primary_arm"] == "SHIFT_expert_IW"
    for name in ("oracle_target_threshold_global",
                 "oracle_target_expert_mixture"):
        per_fold = oracle[name]["per_fold"]
        assert set(per_fold) == set(v36.REAL_SOURCES)
        for fold, rec in per_fold.items():
            m = rec["metrics"]
            for k in ("bcov", "gain", "chr", "pme", "damage"):
                assert np.isfinite(m[k]), (name, fold, k)


# -- §3.3 transfer matrix ---------------------------------------------------------


def test_transfer_matrix_shape_and_symmetry(transfer):
    srcs = transfer["sources"]
    assert list(srcs) == list(v36.REAL_SOURCES)
    mat = transfer["matrix"]
    for s in srcs:
        assert set(mat[s]) == set(srcs)
        for t in srcs:
            entry = mat[s][t]
            for k in ("chr", "bcov", "gain", "pme", "damage", "threshold",
                      "score_quantile_shift", "bns_separation_auroc",
                      "commit_by_family"):
                assert k in entry, (s, t, k)
            assert entry["in_sample"] == (s == t)
    dist = transfer["fingerprint"]["distance"]
    for s in srcs:
        assert dist[s][s] == pytest.approx(0.0)
        for t in srcs:
            assert dist[s][t] == pytest.approx(dist[t][s])
            assert dist[s][t] >= 0.0


def test_transfer_correlation_block(transfer):
    corr = transfer["correlation"]
    assert corr["n_ordered_pairs"] == 30
    for key in ("distance_vs_chr", "distance_vs_bcov", "distance_vs_gain"):
        assert -1.0 <= corr[key]["pearson_r"] <= 1.0
        assert -1.0 <= corr[key]["spearman_r"] <= 1.0
