"""Contract tests for the v3.2 feature repairs and episode-replay calibration.

These pin the defects that invalidated v3-pre: the touched mask handling, the
seam computation, the outside-support drift, the three formerly constant
features, and the calibration's match to the deployed first-commit rule.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from introact_ts.actions import apply_action, robust_scale  # noqa: E402
from introact_ts.contextual_shield import (  # noqa: E402
    _mask_runs, _touched_mask, episode_replay, select_episode_thresholds,
)
from introact_ts.types import Action  # noqa: E402


def _series(T=128, seed=0):
    rng = np.random.RandomState(seed)
    t = np.arange(T, dtype=np.float64)
    return 3.0 * np.sin(2 * np.pi * t / 16.0) + rng.randn(T) * 0.2


# -- mask unification ---------------------------------------------------------


def test_touched_mask_from_bool_mask():
    m = np.zeros(10, dtype=bool)
    m[3:5] = True
    out = _touched_mask(m, 10)
    assert out.dtype == bool and out.sum() == 2


def test_touched_mask_from_indices():
    out = _touched_mask(np.array([2, 7]), 10)
    assert out.dtype == bool and out.sum() == 2 and out[2] and out[7]


def test_touched_mask_none_means_whole_window():
    assert _touched_mask(None, 10) is None
    # A mask of the wrong length (e.g. after a crop) is not a valid support.
    assert _touched_mask(np.ones(5, dtype=bool), 10) is None


def test_mask_runs():
    m = np.zeros(10, dtype=bool)
    m[2:4] = True
    m[7] = True
    assert _mask_runs(m) == [(2, 4), (7, 8)]


# -- feature extraction on real operators --------------------------------------


def _extract(window_series, action, **params):
    """Run one operator and extract features with stub probe/state objects."""
    from introact_ts.contextual_shield import (
        ALL_FEATURES, CATEGORICAL_FEATURES, ContextualShield,
    )

    class _W:
        series = window_series

    class _State:
        hypothesis = "contaminated"
        confidence = 0.8
        defect_strength = 0.5
        behav_risk = 0.4
        ood = 0.1
        dominant_defect = "spike"
        defect_units = {"spike": 3.0, "missing": 1.0}

    class _Probe:
        utility = -1.0
        vector = np.array([1.0, 2.0, 3.0])
        parts = {"forecast_nrmse": 0.5}

    class _Report:
        distortion = 0.01
        parts = {"trend": 0.01}

    outcome = apply_action(window_series, action, **params)
    if not outcome.applicable:
        return None, None
    before, after = _Probe(), _Probe()
    after.utility = -0.9
    feats = ContextualShield().extract(
        window=_W(), state=_State(), action=action, params=params,
        outcome=outcome, before=before, after=after, struct_report=_Report(),
        cost=outcome.cost, rung="default", route_source="primary",
        improvement_consistency=0.6, improvement_depth=0.4, action_risk=0.33)
    names = ALL_FEATURES
    vals = dict(zip(names, feats.values.tolist()))
    return outcome, vals


def test_features_all_finite_and_not_constant():
    x = _series()
    x[50] += 8.0  # spike
    outcome, vals = _extract(x, Action.DESPIKE, window=11, n_sigma=2.0)
    assert outcome is not None
    numeric = [v for k, v in vals.items()
               if k not in ("hypothesis", "dominant_defect", "secondary_defect",
                            "route_source", "action_family", "rung")]
    assert all(np.isfinite(v) for v in numeric), "every numeric feature finite"
    # The three formerly constant-zero features now carry their arguments.
    assert vals["improvement_consistency"] == 0.6
    assert vals["improvement_depth"] == 0.4
    assert vals["action_risk"] == 0.33


def test_touched_fraction_is_true_count_over_T():
    x = _series()
    x[50] += 8.0
    outcome, vals = _extract(x, Action.DESPIKE, window=11, n_sigma=2.0)
    assert outcome is not None
    true_frac = float(np.sum(outcome.touched) / len(x))
    assert abs(vals["touched_fraction"] - true_frac) < 1e-12
    assert vals["touched_fraction"] < 0.5  # a spike touches few points, not all


def test_seam_error_uses_real_indices_and_scale():
    # Constant series with one point lifted: despiking it back creates no seam,
    # while a manual edit to a wrong level would create one at index 50.
    x = np.ones(64)
    x[50] = 5.0
    outcome, vals = _extract(x, Action.DESPIKE, window=11, n_sigma=1.0)
    assert outcome is not None
    # The repair restores 1.0, so both boundaries are continuous.
    assert vals["seam_error"] < 1e-9


def test_outside_support_drift_detects_undeclared_changes():
    x = _series()
    x[50] += 8.0
    outcome, vals = _extract(x, Action.DESPIKE, window=11, n_sigma=2.0)
    assert outcome is not None
    # DESPIKE only rewrites declared spikes: drift outside support is zero.
    assert vals["outside_support_drift"] < 1e-12
    # DENOISE declares the whole window: drift is 0 by definition.
    outcome2, vals2 = _extract(x, Action.DENOISE, strength="light")
    assert outcome2 is not None
    assert vals2["outside_support_drift"] == 0.0
    assert vals2["touched_fraction"] == 1.0


def test_variance_sanity_of_normalised_features():
    x = _series()
    x[50] += 8.0
    _, vals = _extract(x, Action.DESPIKE, window=11, n_sigma=2.0)
    # delta_utility_rel = 0.1 / 1.0; probe scale std of [1,2,3] ~ 0.816.
    assert abs(vals["delta_utility_rel"] - 0.1) < 1e-9
    assert vals["probe_delta_max_rel"] == 0.0  # identical stub probes


# -- episode-replay calibration -----------------------------------------------

def _cand(family, bs, harm, loss, ben):
    return {"family": family, "score_bs": bs, "score_harm": harm,
            "true_loss": loss, "beneficial": ben}


def test_episode_replay_first_commit_only():
    # One window, two passing candidates: only the first may commit.
    windows = [[_cand("IMPUTE", 0.9, 0.1, 0.0, 1.0),
                _cand("IMPUTE", 0.8, 0.1, 1.0, 0.0)]]
    m = episode_replay(windows, {"IMPUTE": (0.5, 0.5)})
    assert m["committed"] == 1 and m["damage"] == 0.0


def test_episode_replay_closed_family_never_commits():
    windows = [[_cand("RESEGMENT", 1.0, 0.0, 1.0, 0.0)]]
    m = episode_replay(windows, {"IMPUTE": (0.1, 0.9)})
    assert m["committed"] == 0 and m["damage"] == 0.0


def test_episode_calibration_deterministic_and_safe():
    rng = np.random.RandomState(0)
    windows = []
    for _ in range(40):
        cands = []
        for fam in ("DENOISE", "DESPIKE", "IMPUTE"):
            cands.append(_cand(fam, rng.rand(), rng.rand(),
                               float(rng.rand() < 0.2), float(rng.rand() < 0.5)))
        windows.append(cands)
    thr1, m1 = select_episode_thresholds(windows, dual=True)
    thr2, m2 = select_episode_thresholds(windows, dual=True)
    assert thr1 == thr2 and m1 == m2  # deterministic
    assert m1["corrected_risk"] <= 0.03 + 1e-12
    # The chosen thresholds reproduce the reported metrics under replay.
    assert episode_replay(windows, thr1)["committed"] == m1["committed"]


def test_episode_calibration_global_mode():
    rng = np.random.RandomState(1)
    windows = [[_cand(f, rng.rand(), rng.rand(), float(rng.rand() < 0.1), 1.0)
                for f in ("DENOISE", "IMPUTE")] for _ in range(30)]
    thr, m = select_episode_thresholds(windows, dual=True, per_family=False)
    assert set(thr) <= {"DENOISE", "IMPUTE"}
    assert m["corrected_risk"] <= 0.03 + 1e-12
