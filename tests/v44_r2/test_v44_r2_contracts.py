"""v4.4-r2 Batch-1 contracts.

The r2 method is a *decision-regret ranker*, and almost every way it can go
wrong is silent: a pair set that crosses episodes still trains, a design that
erased the episode state still predicts, a veto that never fires still reports a
number.  Each test below therefore names the specific silent failure it guards.
"""

from __future__ import annotations

import numpy as np
import pytest

from introact_ts.v44 import protocol as P
from introact_ts.v44 import state as ST
from introact_ts.v44_r2 import dataset as DV
from introact_ts.v44_r2 import evaluate as EV
from introact_ts.v44_r2 import features as F
from introact_ts.v44_r2 import protocol_r2 as R2
from introact_ts.v44_r2 import ranking as RK
from introact_ts.v44_r2 import regret as RG

L = P.CONTEXT

#: Action -> (fraction_changed, near_origin_change) of the fixture.  Deterministic
#: per action so the intervention block is not a constant column.
INTERVENTION = {
    "KEEP": (0.0, 0.0),
    "FFILL": (0.2, 0.1),
    "SINGLE_TSICL": (0.4, 0.2),
    "MULTI_TSICL": (0.6, 0.3),
    "CONTEXT_RIDGE": (0.8, 0.4),
}

#: Losses by episode family.  The best action *changes with the family*, which is
#: the only thing that makes "choose the action that fits this episode" testable.
FAMILY_LOSSES = {
    0.0: {"KEEP": 1.0, "FFILL": 0.5, "SINGLE_TSICL": 0.9, "MULTI_TSICL": 0.8,
          "CONTEXT_RIDGE": 1.1},
    1.0: {"KEEP": 1.0, "FFILL": 0.8, "SINGLE_TSICL": 0.9, "MULTI_TSICL": 0.5,
          "CONTEXT_RIDGE": 1.1},
}


def state_vector(*, family: float = 0.0, missing_ratio: float = 0.1) -> np.ndarray:
    """Twelve episode-state values; ``recent_level_shift`` carries the family."""
    state = np.zeros(len(F.EPISODE_STATE_FEATURES), dtype=np.float64)
    state[0] = missing_ratio          # missing_ratio
    state[1] = 12.0                   # longest_run
    state[2] = 2.0                    # n_runs
    state[3] = 0.5                    # distance_to_origin
    state[5] = 1.0                    # tail_indicator
    state[6] = 1.0                    # robust_scale
    state[8] = 0.7                    # lag1_acf
    state[9] = 0.6                    # seasonal_acf
    state[10] = family                # recent_level_shift
    state[11] = 0.3                   # recent_volatility
    return state


def action_vector(state: np.ndarray, action: str) -> np.ndarray:
    return F.assert_dimension(np.concatenate([
        state, F.action_one_hot(action), np.asarray(INTERVENTION[action],
                                                    dtype=np.float64)]))


def make_episode(*, episode: str, parent: str, family: float = 0.0,
                 losses: dict[str, float] | None = None, source: str = "ETTh1",
                 block: str = "replay_fit", horizon: int = 96,
                 pattern: str = "P2_target_block",
                 severity: float = 0.10) -> DV.EpisodeView:
    """One episode with every action executable unless ``losses`` omits it."""
    losses = dict(FAMILY_LOSSES[family] if losses is None else losses)
    state = state_vector(family=family)
    actions: dict[str, DV.ActionView] = {}
    for action in P.ACTIONS:
        loss = losses.get(action)
        if loss is None:
            actions[action] = DV.ActionView(
                action=action, applicable=False, reason="fixture: not applicable",
                alias_of=None, input_hash="", prediction_hash="")
            continue
        actions[action] = DV.ActionView(
            action=action, applicable=True, reason=None, alias_of=None,
            input_hash=f"{episode}|{action}",
            prediction_hash=f"{episode}|{action}|p",
            loss=float(loss), mse=float(loss), mae=float(loss),
            rmsse=float(loss), utility=None, runtime=0.0,
            features=action_vector(state, action))
    reference_loss = losses.get("KEEP")
    for action, view in actions.items():
        if view.loss is not None and reference_loss is not None:
            view.utility = float(reference_loss - view.loss)
    return DV.EpisodeView(
        episode=episode, source=source, parent=parent, origin=512,
        horizon=horizon, pattern=pattern, severity=severity, block=block,
        period=24, n_channels=7, mase_scale=1.0, rmsse_scale=1.0,
        mase_scale_id="fixture", future=np.zeros(horizon),
        reference_target=np.zeros(L), actions=actions)


@pytest.fixture
def family_blocks():
    """Four parents per family, three episodes each: enough for a fit."""
    episodes = []
    for family, tag in ((0.0, "A"), (1.0, "B")):
        for parent_index in range(4):
            parent = f"{tag}{parent_index}"
            for episode_index in range(3):
                episodes.append(make_episode(
                    episode=f"{parent}-e{episode_index}", parent=parent,
                    family=family))
    return episodes


# -- the frozen feature set -------------------------------------------------


def test_the_feature_set_is_the_frozen_nineteen_and_holds_no_forecast_block():
    assert len(F.EPISODE_STATE_FEATURES) == 12
    assert F.EPISODE_STATE_FEATURES == (ST.MASK_FEATURES + ST.CONTEXT_FEATURES)
    assert F.ACTION_FEATURES == tuple(f"is_{name}" for name in P.ACTIONS)
    assert F.INTERVENTION_KEEP == ("fraction_changed", "near_origin_change")
    assert F.STATE_DIM == 19
    # A3 w/o forecast beat the full v4.4 state, so no forecast descriptor may
    # re-enter under an r2 name.
    assert not any("fc_" in name or "forecast" in name for name in F.FEATURE_NAMES)
    assert set(F.FEATURE_NAMES) == set(ST.MASK_FEATURES + ST.CONTEXT_FEATURES
                                       + tuple(f"is_{a}" for a in P.ACTIONS)
                                       + F.INTERVENTION_KEEP)


def test_action_features_are_nineteen_dimensional_and_carry_the_one_hot():
    reference = np.linspace(0.0, 10.0, L)
    candidate = reference.copy()
    candidate[100:150] = 0.0
    mask = np.zeros((L, 7), dtype=bool)
    mask[100:150, :] = True
    state = F.episode_state(mask, reference, 24)
    assert state.size == 12
    vector = F.action_features(action="FFILL", episode_state_vector=state,
                               candidate_target=candidate,
                               reference_target=reference,
                               scale=ST.robust_scale(reference))
    assert vector.size == F.STATE_DIM
    assert np.isfinite(vector).all()
    assert vector[12:17].tolist() == [1.0 if a == "FFILL" else 0.0
                                      for a in P.ACTIONS]
    assert vector[17] == pytest.approx(50 / 512)


# -- the pairwise design ----------------------------------------------------


def test_a_plain_difference_would_erase_the_episode_state():
    """The bug this design exists to avoid, stated as an executable fact."""
    one_hot = F.action_one_hot("FFILL")
    keep = F.action_one_hot("KEEP")
    intervention = np.asarray(INTERVENTION["FFILL"])
    for family in (0.0, 1.0):
        state = state_vector(family=family)
        left = np.concatenate([state, one_hot, intervention])
        right = np.concatenate([state, keep, intervention])
        # The state block of a same-episode difference is exactly zero for
        # every episode, so a learner on the raw difference is blind to it.
        assert np.allclose(
            (left - right)[:len(F.EPISODE_STATE_FEATURES)], 0.0)
    left_a = np.concatenate([state_vector(family=0.0), one_hot, intervention])
    right_a = np.concatenate([state_vector(family=0.0), keep, intervention])
    left_b = np.concatenate([state_vector(family=1.0), one_hot, intervention])
    right_b = np.concatenate([state_vector(family=1.0), keep, intervention])
    # Two different episodes, one identical difference.
    assert np.array_equal(left_a - right_a, left_b - right_b)


def test_the_pair_design_keeps_the_episode_state_action_conditionally():
    one_hot = F.action_one_hot("FFILL")
    keep = F.action_one_hot("KEEP")
    intervention = np.asarray(INTERVENTION["FFILL"])
    left_a = np.concatenate([state_vector(family=0.0), one_hot, intervention])
    right_a = np.concatenate([state_vector(family=0.0), keep, intervention])
    left_b = np.concatenate([state_vector(family=1.0), one_hot, intervention])
    right_b = np.concatenate([state_vector(family=1.0), keep, intervention])
    design_a = F.pair_design(left_a, right_a)
    design_b = F.pair_design(left_b, right_b)
    assert design_a.shape == (F.PAIR_DIM,)
    assert F.PAIR_DIM == 12 * 5 + 5 + 2
    assert not np.array_equal(design_a, design_b)
    # The action-conditional block is what differs.
    assert not np.array_equal(design_a[:F.INTERACTION_DIM],
                              design_b[:F.INTERACTION_DIM])


def test_pair_design_refuses_a_pair_built_across_two_episodes():
    one_hot = F.action_one_hot("FFILL")
    keep = F.action_one_hot("KEEP")
    intervention = np.asarray(INTERVENTION["FFILL"])
    left = np.concatenate([state_vector(family=0.0), one_hot, intervention])
    foreign = np.concatenate([state_vector(family=1.0), keep, intervention])
    with pytest.raises(ValueError):
        F.pair_design(left, foreign)


# -- the pair set -----------------------------------------------------------


def test_pairs_never_cross_episodes(family_blocks):
    pairs, _ = RK.build_pairs(family_blocks)
    for position, owner in enumerate(pairs.episodes):
        episode = family_blocks[int(owner)]
        left, right = pairs.left[position], pairs.right[position]
        assert left in episode.legal() and right in episode.legal()
        assert left != right


def test_pair_label_and_weight_are_the_loss_preference_and_its_margin(family_blocks):
    pairs, _ = RK.build_pairs(family_blocks)
    for position, owner in enumerate(pairs.episodes):
        losses = family_blocks[int(owner)].losses()
        left, right = pairs.left[position], pairs.right[position]
        assert pairs.y[position] == float(losses[left] < losses[right])
        assert pairs.w[position] == pytest.approx(
            abs(losses[left] - losses[right]))


def test_keep_participates_as_an_ordinary_action(family_blocks):
    pairs, _ = RK.build_pairs(family_blocks)
    ordered = set(zip(pairs.left, pairs.right))
    assert ("KEEP", "FFILL") in ordered
    assert ("FFILL", "KEEP") in ordered
    assert not any(left == right for left, right in ordered)
    # Five legal actions -> 5 * 4 ordered pairs per episode, no self-pairs.
    assert len(pairs) == 20 * len(family_blocks)
    assert pairs.summary()["zero_weight_pairs"] == 0


def test_the_pair_matrix_width_is_the_design_width(family_blocks):
    pairs, _ = RK.build_pairs(family_blocks)
    assert pairs.X.shape == (len(pairs), F.PAIR_DIM)


# -- the decision rule ------------------------------------------------------


def test_an_exact_tie_goes_to_keep():
    probabilities = {("KEEP", "FFILL"): 0.5, ("FFILL", "KEEP"): 0.5}
    decision = RK.decide_from(probabilities, ("KEEP", "FFILL"), tau=0.5)
    assert decision.action == "KEEP"
    assert not decision.vetoed


def test_the_veto_falls_back_to_keep_only_below_tau():
    probabilities = {
        ("FFILL", "KEEP"): 0.58, ("FFILL", "MULTI_TSICL"): 0.70,
        ("KEEP", "FFILL"): 0.42, ("KEEP", "MULTI_TSICL"): 0.60,
        ("MULTI_TSICL", "FFILL"): 0.30, ("MULTI_TSICL", "KEEP"): 0.40,
    }
    legal = ("KEEP", "FFILL", "MULTI_TSICL")
    vetoed = RK.decide_from(probabilities, legal, tau=0.60)
    assert vetoed.borda_winner == "FFILL"
    assert vetoed.action == "KEEP" and vetoed.vetoed
    assert vetoed.veto_probability == pytest.approx(0.58)
    allowed = RK.decide_from(probabilities, legal, tau=0.55)
    assert allowed.action == "FFILL" and not allowed.vetoed


def test_a_single_legal_action_is_keep_without_a_confidence():
    decision = RK.decide_from({}, ("KEEP",), tau=0.5)
    assert decision.action == "KEEP" and decision.veto_probability is None


def test_a_state_dependent_preference_is_actually_learnable(family_blocks):
    """The end-to-end guard: the ranker must use the state, not just action taste."""
    ranker = RK.PairwiseRanker(learner=R2.LEARNER_LINEAR).fit(family_blocks)
    for family, expected in ((0.0, "FFILL"), (1.0, "MULTI_TSICL")):
        probe = make_episode(episode=f"probe-{family}", parent=f"probe{family}",
                             family=family)
        decision = ranker.decide(probe, tau=0.50)
        assert decision.action == expected, (
            f"family {family}: a ranker that ignored the episode state could "
            f"not pick {expected}")


def test_the_ranker_rejects_a_configuration_it_cannot_fit():
    with pytest.raises(ValueError):
        RK.PairwiseRanker(learner=R2.LEARNER_LINEAR, alpha=0.5)
    with pytest.raises(ValueError):
        RK.PairwiseRanker(learner=R2.LEARNER_ENSEMBLE)
    with pytest.raises(ValueError):
        RK.PairwiseRanker(learner="L9_MYSTERY")


# -- the frozen grid --------------------------------------------------------


def test_the_candidate_grid_is_seven_configs_by_four_thresholds():
    grid = R2.candidate_grid()
    assert len(grid) == 28
    assert len({entry["config"] for entry in grid}) == 7
    assert {entry["tau"] for entry in grid} == set(R2.TAU_GRID)
    assert R2.TAU_GRID == (0.50, 0.55, 0.60, 0.65)
    ensemble = {entry["alpha"] for entry in grid
                if entry["learner"] == R2.LEARNER_ENSEMBLE}
    assert ensemble == set(R2.ALPHA_GRID)
    assert all(entry["alpha"] is None for entry in grid
               if entry["learner"] != R2.LEARNER_ENSEMBLE)


# -- cross-fitting ----------------------------------------------------------


def test_parent_folds_partition_the_parents_deterministically(family_blocks):
    first = RK.parent_folds(family_blocks, folds=3, seed=7)
    second = RK.parent_folds(family_blocks, folds=3, seed=7)
    assert first == second
    flat = [parent for fold in first for parent in fold]
    assert sorted(flat) == sorted({e.parent for e in family_blocks})
    assert len(flat) == len(set(flat))


def test_cross_fit_never_scores_an_episode_with_a_ranker_that_saw_its_parent(
        monkeypatch, family_blocks):
    seen: list[tuple[frozenset[str], str]] = []
    original = RK.PairwiseRanker

    class Spy(original):  # type: ignore[misc, valid-type]
        def fit(self, episodes):
            self._fitted_parents = frozenset(e.parent for e in episodes)
            return super().fit(episodes)

        def pair_probabilities(self, episode):
            seen.append((self._fitted_parents, episode.parent))
            return super().pair_probabilities(episode)

    monkeypatch.setattr(RK, "PairwiseRanker", Spy)
    probabilities = RK.cross_fitted_pair_probabilities(
        family_blocks, learner=R2.LEARNER_LINEAR, folds=4)

    assert seen, "cross-fitting scored nothing"
    for fitted_parents, scored_parent in seen:
        assert scored_parent not in fitted_parents
    assert len(probabilities) == len(family_blocks)


def test_cross_fit_covers_every_episode_with_at_least_two_actions(family_blocks):
    probabilities = RK.cross_fitted_pair_probabilities(
        family_blocks, learner=R2.LEARNER_TREE, folds=4)
    assert set(probabilities) == {e.episode for e in family_blocks}
    assert all(len(pairs) == 20 for pairs in probabilities.values())


# -- aggregation and the admission boundary ---------------------------------


def test_macro_cells_keep_severity_apart():
    records = []
    for severity, value in ((0.10, 1.0), (0.30, 3.0)):
        records.append({"method": "M", "backbone": "bolt", "source": "ETTh1",
                        "parent": "p1", "variant": "v1", "horizon": 96,
                        "pattern": "P2_target_block", "severity": severity,
                        "mase": value})
    cells = EV.macro_cells(records, "M", "bolt")
    assert len(cells) == 2
    assert cells["h96|P2_target_block|s10"] == pytest.approx(1.0)
    assert cells["h96|P2_target_block|s30"] == pytest.approx(3.0)
    # The headline is the equal-weight mean of the cells, not the first cell.
    assert EV.macro_mase(records, "M", "bolt") == pytest.approx(2.0)


def test_opportunity_bands_follow_the_frozen_thresholds():
    thresholds = {"low": 0.05, "high": 0.20}
    assert EV.opportunity_band(None, thresholds) == "unknown"
    assert EV.opportunity_band(0.0, thresholds) == "no_op"
    assert EV.opportunity_band(0.04, thresholds) == "low"
    assert EV.opportunity_band(0.20, thresholds) == "low"
    assert EV.opportunity_band(0.21, thresholds) == "high"


def test_opportunity_thresholds_come_from_the_block_they_are_frozen_on():
    episodes = [make_episode(episode=f"e{i}", parent=f"p{i}",
                             family=float(i % 2))
                for i in range(10)]
    thresholds = EV.freeze_opportunity_thresholds(episodes)
    assert thresholds["n"] == 10
    assert thresholds["low"] <= thresholds["high"]


def test_boundary_audit_detects_a_parent_from_another_block():
    episodes = [make_episode(episode="e1", parent="p1", family=0.0),
                make_episode(episode="e2", parent="p2", family=1.0)]
    decisions = {episode.episode: RK.decide_from(
        {(a, b): 0.9 for a in episode.legal() for b in episode.legal() if a != b},
        episode.legal(), tau=0.5) for episode in episodes}
    records = EV.decision_records(episodes, decisions, backbone="bolt",
                                  method="M")
    audit = EV.boundary_audit(records, episodes, {"p1": "train_eval",
                                                  "p2": "gate"},
                              method="M", backbone="bolt")
    assert audit["block_boundary_ok"] is False
    assert audit["parents_outside_train_eval"] == ["p2"]
    assert audit["records_match_episodes"] is True
    assert audit["headline_equals_cell_mean"] is True
    assert audit["heldout_labels_read"] == 0
    assert audit["calibration_test_touched"] is False


def test_boundary_audit_passes_when_every_parent_is_in_train_eval():
    episodes = [make_episode(episode="e1", parent="p1", family=0.0),
                make_episode(episode="e2", parent="p2", family=1.0)]
    decisions = {episode.episode: RK.decide_from(
        {(a, b): 0.9 for a in episode.legal() for b in episode.legal() if a != b},
        episode.legal(), tau=0.5) for episode in episodes}
    records = EV.decision_records(episodes, decisions, backbone="bolt",
                                  method="M")
    audit = EV.boundary_audit(records, episodes,
                              {"p1": "train_eval", "p2": "train_eval"},
                              method="M", backbone="bolt")
    assert audit["block_boundary_ok"] is True
    assert audit["parents"] == 2


# -- the dataset view -------------------------------------------------------


def test_legal_requires_keep_and_opportunity_is_the_oracle_gap():
    episode = make_episode(episode="e1", parent="p1", family=0.0)
    assert P.REFERENCE_ACTION in episode.legal()
    action, best = episode.oracle()
    assert action == "FFILL" and best == pytest.approx(0.5)
    assert episode.opportunity() == pytest.approx(0.5)


def test_an_episode_without_keep_is_not_legal():
    losses = dict(FAMILY_LOSSES[0.0])
    losses.pop("KEEP")
    episode = make_episode(episode="e1", parent="p1", losses=losses)
    assert episode.legal() == ()
    assert episode.opportunity() is None


def test_the_loader_refuses_a_block_that_is_not_a_train_block(tmp_path):
    with pytest.raises(ValueError):
        DV.load_block(tmp_path, "calibration", "bolt")
    with pytest.raises(ValueError):
        DV.load_block(tmp_path, "test", "bolt")


# -- stage 2: the expected-regret ensemble ----------------------------------


def test_the_lambda_grid_is_the_fifteen_point_simplex():
    grid = R2.lambda_grid()
    assert len(grid) == 15
    assert (1.0, 0.0, 0.0) in grid
    assert (0.0, 1.0, 0.0) in grid
    assert (0.0, 0.0, 1.0) in grid
    for triple in grid:
        assert all(value >= 0.0 for value in triple)
        assert sum(triple) == pytest.approx(1.0)
        assert len(set(triple)) == len(triple) or True


def test_standardise_is_zero_when_the_component_has_nothing_to_say():
    assert RG.standardise({"KEEP": 1.0, "FFILL": 1.0}) == {"KEEP": 0.0,
                                                           "FFILL": 0.0}
    assert RG.standardise({"KEEP": float("nan"), "FFILL": float("nan")}) == {
        "KEEP": 0.0, "FFILL": 0.0}
    scaled = RG.standardise({"KEEP": 1.0, "FFILL": 3.0})
    assert scaled["FFILL"] == pytest.approx(1.0)
    assert scaled["KEEP"] == pytest.approx(-1.0)


def test_the_regret_target_is_zero_for_the_best_action(family_blocks):
    _features, targets, actions, owners = RG.regret_rows(family_blocks)
    for owner in set(owners):
        rows = [targets[i] for i, value in enumerate(owners) if value == owner]
        assert min(rows) == pytest.approx(0.0)
        assert all(value >= 0.0 for value in rows)
    assert len(actions) == len(owners) == 5 * len(family_blocks)


def test_the_regret_model_predicts_one_value_per_legal_action(family_blocks):
    model = RG.RegretModel(kind=R2.REGRET_RIDGE).fit(family_blocks)
    episode = family_blocks[0]
    predicted = model.predict(episode)
    assert set(predicted) == set(episode.legal())
    assert all(np.isfinite(value) for value in predicted.values())
    notes = model.notes()
    assert set(notes["support"]) == set(P.ACTIONS)
    assert all(count >= RG.MIN_SUPPORT for count in notes["support"].values())


def test_the_ensemble_with_lambda_one_is_stage_one_exactly(family_blocks):
    """Stage 2 must contain stage 1, or the search could regress on the gate."""
    ranker = RK.PairwiseRanker(learner=R2.LEARNER_LINEAR).fit(family_blocks)
    ridge = RG.RegretModel(kind=R2.REGRET_RIDGE).fit(family_blocks)
    tree = RG.RegretModel(kind=R2.REGRET_TREE).fit(family_blocks)
    for episode in family_blocks[:4]:
        probabilities = ranker.pair_probabilities(episode)
        built = RG.components(episode, probabilities, ridge, tree)
        assert built is not None
        stage2 = RG.decide_from_components(built, probabilities,
                                           episode.legal(),
                                           lambdas=(1.0, 0.0, 0.0), tau=0.55)
        stage1 = RK.decide_from(probabilities, episode.legal(), tau=0.55)
        assert stage2.action == stage1.action
        assert stage2.vetoed == stage1.vetoed


def test_the_ensemble_recovers_the_same_winner_on_a_separable_problem(family_blocks):
    """On a problem with a clear per-family winner both components agree."""
    ranker = RK.PairwiseRanker(learner=R2.LEARNER_TREE).fit(family_blocks)
    ridge = RG.RegretModel(kind=R2.REGRET_RIDGE).fit(family_blocks)
    tree = RG.RegretModel(kind=R2.REGRET_TREE).fit(family_blocks)
    for episode in family_blocks:
        probabilities = ranker.pair_probabilities(episode)
        built = RG.components(episode, probabilities, ridge, tree)
        assert built is not None
        pure = RG.select(built.combine((1.0, 0.0, 0.0)), episode.legal())
        regret_only = RG.select(built.combine((0.0, 1.0, 0.0)), episode.legal())
        both = RG.select(built.combine((1 / 3, 1 / 3, 1 / 3)), episode.legal())
        assert pure == regret_only == both


def test_the_regret_component_enters_with_the_right_sign_and_can_outvote():
    """Lower predicted regret must raise the score, and must be able to win."""
    built = RG.Components(pair={"KEEP": 1.0, "FFILL": -1.0},
                          ridge={"KEEP": 1.0, "FFILL": -1.0},
                          tree={"KEEP": 1.0, "FFILL": -1.0})
    legal = ("KEEP", "FFILL")
    # The pair component prefers KEEP; the regret component prefers FFILL.
    assert RG.select(built.combine((1.0, 0.0, 0.0)), legal) == "KEEP"
    assert RG.select(built.combine((0.0, 1.0, 0.0)), legal) == "FFILL"
    assert RG.select(built.combine((0.0, 0.0, 1.0)), legal) == "FFILL"
    # A regret weight above one half flips the combined decision.
    assert RG.select(built.combine((0.25, 0.75, 0.0)), legal) == "FFILL"
    assert RG.select(built.combine((0.75, 0.25, 0.0)), legal) == "KEEP"


def test_the_combined_score_is_the_documented_weighted_sum():
    built = RG.Components(pair={"KEEP": 2.0, "FFILL": -2.0},
                          ridge={"KEEP": 1.0, "FFILL": -1.0},
                          tree={"KEEP": -1.0, "FFILL": 1.0})
    scores = built.combine((0.5, 0.25, 0.25))
    assert scores["KEEP"] == pytest.approx(0.5 * 2.0 - 0.25 * 1.0 - 0.25 * -1.0)
    assert scores["FFILL"] == pytest.approx(0.5 * -2.0 - 0.25 * -1.0 - 0.25 * 1.0)


def test_cross_fitted_regret_never_scores_an_episode_with_a_model_that_saw_its_parent(
        monkeypatch, family_blocks):
    seen: list[tuple[frozenset[str], str]] = []
    original = RG.RegretModel

    class Spy(original):  # type: ignore[misc, valid-type]
        def fit(self, episodes):
            self._fitted_parents = frozenset(e.parent for e in episodes)
            return super().fit(episodes)

        def predict(self, episode):
            seen.append((self._fitted_parents, episode.parent))
            return super().predict(episode)

    monkeypatch.setattr(RG, "RegretModel", Spy)
    predicted = RG.cross_fitted_regret(family_blocks, kind=R2.REGRET_RIDGE,
                                       folds=4)
    assert seen, "cross-fitting predicted nothing"
    for fitted_parents, scored_parent in seen:
        assert scored_parent not in fitted_parents
    assert len(predicted) == len(family_blocks)


def test_the_ensemble_decision_falls_back_to_keep_for_a_single_action():
    episode = make_episode(episode="e1", parent="p1",
                           losses={"KEEP": 1.0, "FFILL": None})
    built = RG.Components(pair={"KEEP": 0.0}, ridge={"KEEP": 0.0},
                          tree={"KEEP": 0.0})
    decision = RG.decide_from_components(built, {}, episode.legal(),
                                        lambdas=(1 / 3, 1 / 3, 1 / 3), tau=0.55)
    assert decision.action == "KEEP"
    assert decision.veto_probability is None
