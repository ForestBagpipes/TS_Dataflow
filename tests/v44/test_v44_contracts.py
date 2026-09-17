"""v4.4 Phase-1 contracts (task book §18).

Fifteen checks that must all pass on the server before a single main-experiment
run is launched.  Each test names the contract it guards so a failure points at
a boundary rather than at a line number.
"""

from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pytest

from introact_ts.v44 import actions as A
from introact_ts.v44 import catalog as C
from introact_ts.v44 import masking as M
from introact_ts.v44 import matching as MT
from introact_ts.v44 import methods as MX
from introact_ts.v44 import metrics as ME
from introact_ts.v44 import protocol as P
from introact_ts.v44 import splits as S
from introact_ts.v44 import state as ST
from introact_ts.v44.hashing import array_hash
from introact_ts.v44.replay import ReplayBank, ReplayRecord, make_cache_key

L = P.CONTEXT


# -- helpers ----------------------------------------------------------------


class MeanImputer:
    """Deterministic stub imputer; never used outside the contract tests."""

    def __init__(self, offset: float = 0.0):
        self.offset = offset
        self.calls = 0

    def impute_single(self, target):
        self.calls += 1
        out = np.array(target, dtype=np.float64, copy=True)
        missing = ~np.isfinite(out)
        if missing.any():
            observed = np.isfinite(out)
            out[missing] = float(np.mean(out[observed])) + self.offset
        return out

    def impute_multi(self, target, covariates):
        self.calls += 1
        out = np.array(target, dtype=np.float64, copy=True)
        missing = ~np.isfinite(out)
        if missing.any():
            observed = np.isfinite(out)
            base = float(np.mean(out[observed]))
            cov = np.nan_to_num(covariates, nan=0.0).mean(axis=1)
            out[missing] = base + 0.001 * cov[missing] + self.offset
        return out


def panel(seed: int = 0, length: int = L, channels: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(length, dtype=np.float64)
    base = 5.0 * np.sin(2 * np.pi * t / 24.0) + 0.02 * t
    return np.column_stack([base + rng.normal(0, 0.2, length)
                            for _ in range(channels)])


def masked_panel(seed: int = 0, pattern: str = "P2_target_block",
                 severity: float = 0.10, channels: int = 3) -> np.ndarray:
    raw = panel(seed, channels=channels)
    mask = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, pattern, severity,
                        length=raw.shape[0], n_channels=channels)
    return M.apply_mask(raw, mask)


def record(*, action: str, utility: float, parent: str = "p1",
           source: str = "ETTh1", state: np.ndarray | None = None,
           scored: bool = True, **overrides) -> ReplayRecord:
    if state is None:
        state = np.zeros(22)
    payload = dict(
        source=source, parent=parent, origin=512, horizon=96,
        pattern="P2_target_block", severity=0.10, mask_hash="m" * 8,
        backbone="bolt", backbone_revision="r1", action=action,
        input_hash=f"in-{action}-{parent}", prediction_hash=f"pr-{action}-{parent}",
        mask_features=state[0:6], context_features=state[6:12],
        intervention_features=state[12:17],
        reference_forecast_features=state[17:22],
        mase_scale=1.0, mase_scale_id="scale-1",
        mase=1.0 - utility, mse=1.0, mae=1.0, rmsse=1.0,
        utility_vs_reference=utility if scored else None,
        failure=None if scored else "boom",
        code_sha="c" * 8, resolved_config_hash="cfg",
        forecast=np.zeros(96), target=np.zeros(96),
    )
    payload.update(overrides)
    return ReplayRecord(**payload)


def catalog(*, episode: str, parent: str, block: str,
            source: str = "ETTh1") -> C.EpisodeCatalog:
    """A minimal catalog with KEEP plus one usable alternative (FFILL).

    Every action of the pool is present because ``legal()`` indexes all of
    them; only KEEP and FFILL are applicable.
    """
    def entry(action: str, *, applicable: bool, mase: float | None,
              utility: float | None) -> C.ActionEntry:
        return C.ActionEntry(
            action=action, applicable=applicable,
            reason=None if applicable else "not applicable in this fixture",
            alias_of=None, input_hash=f"{action}-in", prediction_hash=f"{action}-pr",
            prediction=np.zeros(96) if applicable else None,
            state_vector=np.zeros(22) if applicable else None,
            mase=mase, mse=1.0 if mase is not None else None,
            mae=1.0 if mase is not None else None,
            rmsse=1.0 if mase is not None else None,
            utility=utility, runtime=0.0)

    actions = {
        P.REFERENCE_ACTION: entry(P.REFERENCE_ACTION, applicable=True, mase=1.0,
                                  utility=0.0),
        "FFILL": entry("FFILL", applicable=True, mase=0.8, utility=0.2),
    }
    for action in P.ACTIONS:
        actions.setdefault(action, entry(action, applicable=False, mase=None,
                                         utility=None))
    return C.EpisodeCatalog(
        episode=episode, source=source, parent=parent, origin=512, horizon=96,
        pattern="P2_target_block", severity=0.10, block=block, period=24,
        mase_scale=1.0, rmsse_scale=1.0, mase_scale_id="scale-1",
        future=np.zeros(96), reference_target=np.zeros(96), actions=actions)


# -- 1. mask hash determinism ----------------------------------------------


def test_mask_hash_is_deterministic_and_identity_bound():
    first = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P2_target_block", 0.10)
    second = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P2_target_block", 0.10)
    assert np.array_equal(first, second)
    assert array_hash(first) == array_hash(second)
    assert M.mask_identity("ETTh1", "ETTh1:0:704", 512, 96,
                           "P2_target_block", 0.10)["mask_hash"] == array_hash(first)

    # Every identity coordinate must move the mask.
    variants = [
        M.build_mask("ETTh2", "ETTh1:0:704", 512, 96, "P2_target_block", 0.10),
        M.build_mask("ETTh1", "ETTh1:704:1408", 512, 96, "P2_target_block", 0.10),
        M.build_mask("ETTh1", "ETTh1:0:704", 512, 192, "P2_target_block", 0.10),
        M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P1_point", 0.10),
        M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P2_target_block", 0.30),
    ]
    for other in variants:
        assert not np.array_equal(first, other)

    # The mask must not depend on the data at all.
    identity = M.mask_identity("ETTh1", "ETTh1:0:704", 512, 96,
                               "P2_target_block", 0.10)
    assert identity["missing_count"] == int(round(0.10 * L))


def test_severity_ladder_and_pattern_shapes():
    for pattern in P.PATTERNS:
        for severity in P.SEVERITIES:
            mask = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, pattern, severity)
            budget = int(round(severity * L))
            assert mask[:, 0].sum() == budget
            assert not mask[:, 1:].any(), "target-only patterns must not touch covariates"
    shared = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P3_shared_block", 0.10,
                          n_channels=4)
    assert shared.shape == (L, 4)
    assert np.array_equal(shared[:, 0], shared[:, 1])
    assert np.array_equal(shared[:, 0], shared[:, 3])
    tail = M.build_mask("ETTh1", "ETTh1:0:704", 512, 96, "P4_tail", 0.10)
    assert tail[-int(round(0.10 * L)):, 0].all()
    assert not tail[:-int(round(0.10 * L)), 0].any()


# -- 2. split blocks --------------------------------------------------------


def test_split_blocks_do_not_overlap_and_respect_purge():
    parents = []
    for source in ("ETTh1", "Exchange", "Weather"):
        count = 14 if source == "ETTh1" else (6 if source == "Exchange" else 44)
        for i in range(count):
            start = i * P.PARENT_STRIDE
            parents.append(S.ParentWindow(source, f"{source}:{start}:{start + 704}",
                                          start, start + P.CONTEXT, start + 704))
    assignment = S.assign_splits(parents)
    assert set(assignment) == {p.parent for p in parents}
    assert set(assignment.values()) <= set(P.SPLIT_NAMES)

    # Every parent appears exactly once, and blocks partition each source.
    summary = S.block_summary(parents, assignment)
    assert sum(v["parents"] for v in summary.values()) == len(parents)
    for name in P.SPLIT_NAMES:
        assert summary[name]["parents"] >= 1

    # Purge audit raises rather than warns.
    audit = S.audit_purge(parents, assignment)
    assert audit["boundary_pairs_checked"] > 0
    assert audit["purge"] == P.PURGE

    # All variants of a parent share one block by construction.
    grid = S.episode_grid(parents, assignment, block="gate")
    for episode in grid:
        assert assignment[episode["parent"]] == "gate"
    assert {e["severity"] for e in grid} == {P.MAIN_SEVERITY}

    # Replay-Fit mixes the severity ladder: exactly one hash-chosen severity per
    # (parent, horizon, pattern), never all three.
    replay = S.episode_grid(parents, assignment, block="replay_fit")
    keys = [(e["parent"], e["horizon"], e["pattern"]) for e in replay]
    assert len(keys) == len(set(keys))
    assert {e["severity"] for e in replay} <= set(P.SEVERITIES)
    assert {e["severity_source"] for e in replay} == {"hash_mixed"}


def test_mixed_severity_is_deterministic_and_registered():
    first = M.mixed_severity("ETTh1", "ETTh1:0:704", 512, 96, "P1_point")
    second = M.mixed_severity("ETTh1", "ETTh1:0:704", 512, 96, "P1_point")
    assert first == second
    assert M.is_registered_severity(first)
    observed = {M.mixed_severity("ETTh1", f"ETTh1:{i * 704}:{i * 704 + 704}",
                                 512, 96, "P2_target_block") for i in range(60)}
    assert observed <= set(P.SEVERITIES)
    assert len(observed) > 1, "mixed support must actually mix severities"


def test_split_rejects_non_train_parents():
    parents = [S.ParentWindow("ETTh1", f"ETTh1:{i}:{i + 704}", i, i + P.CONTEXT,
                              i + 704, role="dev") for i in range(0, 704 * 10, 704)]
    with pytest.raises(ValueError):
        S.assign_splits(parents)


# -- 3./4./5. feature lineage ----------------------------------------------


def test_state_entry_point_has_no_future_inputs():
    """The deployment entry point must not accept a future or a candidate forecast."""
    params = set(inspect.signature(ST.state_vector).parameters)
    assert params == {"masked_panel", "reference_target", "period",
                      "candidate_target", "reference_prediction"}

    forecast_params = list(inspect.signature(
        ST.reference_forecast_features).parameters)
    assert forecast_params == ["prediction", "reference_target"]

    intervention_params = list(inspect.signature(
        ST.intervention_features).parameters)
    assert intervention_params == ["candidate_target", "reference_target", "scale"]

    for name in ("future", "target_future", "y", "candidate_prediction",
                 "candidate_forecast", "future_loss"):
        assert name not in params


def test_future_values_never_reach_the_state():
    """Changing the future changes nothing: it is not an argument anywhere."""
    reference = panel(1)[:, 0]
    candidate = reference.copy()
    candidate[100:140] = np.nan
    candidate = A._fill_forward(candidate)
    prediction = np.linspace(1.0, 2.0, 96)

    first = ST.state_vector(masked_panel=masked_panel(1), reference_target=reference,
                            period=24, candidate_target=candidate,
                            reference_prediction=prediction)
    # The same call, with a wildly different (unused) future in scope.
    poisoned_future = np.full(96, 1e9)
    assert not np.array_equal(poisoned_future, prediction)
    second = ST.state_vector(masked_panel=masked_panel(1), reference_target=reference,
                             period=24, candidate_target=candidate,
                             reference_prediction=prediction)
    assert np.array_equal(first, second)
    assert first.size == 22


def test_forecast_block_is_a_function_of_the_reference_prediction_only():
    reference = panel(2)[:, 0]
    candidate = A._fill_forward(reference)
    base = ST.state_vector(masked_panel=masked_panel(2), reference_target=reference,
                           period=24, candidate_target=candidate,
                           reference_prediction=np.linspace(0.0, 1.0, 96))
    other = ST.state_vector(masked_panel=masked_panel(2), reference_target=reference,
                            period=24, candidate_target=candidate,
                            reference_prediction=np.linspace(10.0, 11.0, 96))
    assert not np.array_equal(base[17:22], other[17:22])
    assert np.array_equal(base[12:17], other[12:17]), "intervention block must not move"
    assert np.array_equal(base[0:12], other[0:12])


def test_intervention_features_read_inputs_only():
    reference = panel(3)[:, 0]
    masked = A._fill_forward(reference)
    scale = ST.robust_scale(reference)
    a = ST.intervention_features(masked, reference, scale)
    b = ST.intervention_features(masked.copy(), reference.copy(), scale)
    assert np.array_equal(a, b)
    # KEEP must be exactly zero-intervention.
    zero = ST.intervention_features(reference.copy(), reference, scale)
    assert np.allclose(zero, 0.0)
    # A larger edit must move the magnitude features upward.
    bigger = masked.copy()
    bigger[:200] += 5.0 * scale
    c = ST.intervention_features(bigger, reference, scale)
    assert c[0] > a[0] and c[1] > a[1]


# -- 6. repeated input hash -------------------------------------------------


def test_repeated_input_hash_is_identical():
    raw = masked_panel(4)
    first = A.apply_action("FFILL", raw, imputer=MeanImputer())
    second = A.apply_action("FFILL", raw, imputer=MeanImputer())
    assert first.input_hash == second.input_hash
    assert np.array_equal(first.target, second.target)
    imputer = MeanImputer()
    third = A.apply_action("SINGLE_TSICL", raw, imputer=imputer)
    fourth = A.apply_action("SINGLE_TSICL", raw, imputer=imputer)
    assert third.input_hash == fourth.input_hash


def test_actions_never_rewrite_observed_values():
    raw = masked_panel(5, pattern="P3_shared_block", severity=0.30)
    for name in P.ACTIONS:
        outcome = A.apply_action(name, raw, imputer=MeanImputer())
        observed = np.isfinite(raw[:, 0])
        if outcome.applicable:
            assert np.array_equal(outcome.target[observed], raw[observed, 0]), name
        else:
            assert outcome.reason


# -- 7. replay lookup stays inside its block --------------------------------


def test_replay_lookup_never_crosses_blocks():
    bank = ReplayBank("bolt")
    block_of = {"p1": "replay_fit", "p2": "replay_fit", "p3": "gate"}
    for parent in ("p1", "p2", "p3"):
        bank.add(record(action="FFILL", utility=0.1, parent=parent,
                        input_hash=f"in-{parent}"))
    fit_only = bank.by_action("FFILL", block="replay_fit", block_of=block_of)
    assert {r.parent for r in fit_only} == {"p1", "p2"}
    gate_only = bank.by_action("FFILL", block="gate", block_of=block_of)
    assert {r.parent for r in gate_only} == {"p3"}
    with pytest.raises(ValueError):
        bank.by_action("FFILL", block="gate")
    # Leave-one-parent-out retrieval is exact.
    left_out = bank.by_action("FFILL", exclude_parent="p1", block="replay_fit",
                              block_of=block_of)
    assert {r.parent for r in left_out} == {"p2"}


def test_retrieval_guard_names_the_bank_block_not_the_request_block():
    """Regression: a request on Gate / TRAIN-Eval must still reach the bank.

    The bank is only ever built from Replay-Fit, so guarding retrieval with the
    *request's* block filters it down to nothing.  That made every one of the
    nine ``K x beta`` configurations abstain on every request, which left the
    gate with nothing to choose between and would have frozen an arbitrary
    configuration.
    """
    bank = ReplayBank("bolt")
    block_of = {"p1": "replay_fit", "p2": "replay_fit",
                "p3": "gate", "p4": "train_eval"}
    rng = np.random.default_rng(11)
    for parent in ("p1", "p2"):
        for i in range(12):
            bank.add(record(action="FFILL", utility=0.3, parent=parent,
                            state=rng.normal(size=22),
                            input_hash=f"in-{parent}-{i}"))

    # A request that lives in the Gate block is scored against Replay-Fit.
    catalogs = [catalog(episode="e-gate", parent="p3", block="gate")]
    selector = MX.full_selector(bank, k=8, beta=0.0, block_of=block_of)
    run = MX.select_with(selector, bank, catalogs, block_of=block_of)
    assert run.selected["e-gate"] == "FFILL"

    # The same holds for a TRAIN-Eval request, and the evidence is the full
    # Replay-Fit support rather than an empty bank.
    selection = selector.select(np.zeros(22), bank, block_of=block_of,
                                block=MX.BANK_BLOCK)
    assert selection.scores["FFILL"].available
    assert selection.scores["FFILL"].support == 24

    # Passing the request's own block is exactly the bug: the bank empties and
    # every action becomes unavailable.
    emptied = selector.select(np.zeros(22), bank, block_of=block_of,
                              block="gate")
    assert not emptied.scores["FFILL"].available
    assert emptied.action == P.REFERENCE_ACTION


# -- 8./9./10. retrieval numerics ------------------------------------------


def _fitted_selector(bank: ReplayBank, **flags) -> MT.ConservativeSelector:
    selector = MT.ConservativeSelector(**flags)
    selector.fit(bank)
    return selector


def test_k_larger_than_support_falls_back_to_available_neighbours():
    bank = ReplayBank("bolt")
    for i in range(3):
        state = np.zeros(22)
        state[0] = 0.1 * i
        bank.add(record(action="FFILL", utility=0.5 - 0.1 * i, parent=f"p{i}",
                        state=state, input_hash=f"in{i}"))
    selector = _fitted_selector(bank, k=32)
    selection = selector.select(np.zeros(22), bank)
    score = selection.scores["FFILL"]
    assert score.available
    assert score.neighbours == 3
    assert score.support == 3
    assert 1.0 <= score.n_eff <= 3.0


def test_effective_sample_size_is_always_legal():
    bank = ReplayBank("bolt")
    rng = np.random.default_rng(0)
    for i in range(24):
        state = rng.normal(size=22)
        bank.add(record(action="FFILL", utility=float(rng.normal(0, 0.2)),
                        parent=f"p{i}", state=state, input_hash=f"in{i}"))
    for k in P.K_GRID:
        selector = _fitted_selector(bank, k=k)
        score = selector.select(rng.normal(size=22), bank).scores["FFILL"]
        assert 1.0 <= score.n_eff <= float(min(k, 24))
        assert np.isfinite(score.mu) and np.isfinite(score.sigma)
        assert np.isfinite(score.score)


def test_zero_variance_utility_yields_no_nan():
    bank = ReplayBank("bolt")
    for i in range(12):
        state = np.zeros(22)
        state[0] = 0.05 * i
        bank.add(record(action="FFILL", utility=0.25, parent=f"p{i}",
                        state=state, input_hash=f"in{i}"))
    selector = _fitted_selector(bank, k=8, beta=1.64)
    selection = selector.select(np.zeros(22), bank)
    score = selection.scores["FFILL"]
    assert score.sigma == pytest.approx(0.0, abs=1e-15)
    assert np.isfinite(score.score)
    assert not np.isnan(score.mu)


# -- 11./12./13. gate behaviour --------------------------------------------


def test_all_negative_scores_abstain_to_reference():
    bank = ReplayBank("bolt")
    for action in ("FFILL", "SINGLE_TSICL"):
        for i in range(10):
            state = np.zeros(22)
            state[0] = 0.02 * i
            bank.add(record(action=action, utility=-0.5 - 0.01 * i,
                            parent=f"{action}-p{i}", state=state,
                            input_hash=f"in-{action}-{i}"))
    selector = _fitted_selector(bank, k=8, beta=1.0)
    selection = selector.select(np.zeros(22), bank)
    assert selection.action == P.REFERENCE_ACTION
    assert selection.intervened is False


def test_unsupported_actions_never_enter_the_argmax():
    bank = ReplayBank("bolt")
    for i in range(10):
        state = np.zeros(22)
        state[0] = 0.02 * i
        bank.add(record(action="FFILL", utility=0.5, parent=f"p{i}",
                        state=state, input_hash=f"in{i}"))
    selector = _fitted_selector(bank, k=8)
    legal = ("KEEP", "FFILL")
    selection = selector.select(np.zeros(22), bank, legal=legal)
    assert selection.action in legal
    for action in P.ACTIONS:
        if action not in legal:
            assert not selection.scores[action].available
            assert selection.scores[action].score == float("-inf")
    # An action with no bank support at all is equally excluded.
    assert not selection.scores["CONTEXT_RIDGE"].available
    assert selection.action == "FFILL"


def test_failed_action_records_are_not_usable_support():
    bank = ReplayBank("bolt")
    for i in range(6):
        state = np.zeros(22)
        state[0] = 0.02 * i
        bank.add(record(action="FFILL", utility=0.5, parent=f"ok{i}",
                        state=state, input_hash=f"ok{i}"))
        bank.add(record(action="SINGLE_TSICL", utility=0.9, parent=f"bad{i}",
                        state=state, input_hash=f"bad{i}", scored=False))
    selector = _fitted_selector(bank, k=8)
    selection = selector.select(np.zeros(22), bank)
    assert not selection.scores["SINGLE_TSICL"].available
    assert selection.scores["SINGLE_TSICL"].reason == "no replay support"
    assert selection.action == "FFILL"
    support = bank.support()
    assert support["failure_ratio"] > 0.0
    assert support["scored"] == 6


# -- 14./15. execution identity and the complete-input contract -------------


def test_selected_prediction_matches_the_executed_version():
    """Whatever the selector picks, the executed artifact is the one it recorded."""
    raw = masked_panel(6)
    imputer = MeanImputer()
    reference_target = raw[:, 0].copy()
    reference_prediction = np.linspace(0.5, 1.5, 96)

    # Build the replay bank from observable state only, then run the full
    # deployment path: catalog -> per-action state -> selection -> execution.
    catalog = A.execute_catalog(raw, imputer=imputer)
    bank = ReplayBank("bolt")
    for i, action in enumerate(P.ACTIONS):
        state = ST.state_vector(
            masked_panel=raw, reference_target=reference_target, period=24,
            candidate_target=catalog[action].target,
            reference_prediction=reference_prediction)
        bank.add(record(action=action, utility=0.4 - 0.05 * i,
                        parent=f"p{i}", state=state, input_hash=f"in{i}"))
    selector = _fitted_selector(bank, k=8)

    query = ST.state_vector(
        masked_panel=raw, reference_target=reference_target, period=24,
        candidate_target=catalog["FFILL"].target,
        reference_prediction=reference_prediction)
    selection = selector.select(query, bank)

    executed = A.apply_action(selection.action, raw, imputer=MeanImputer())
    assert executed.name == selection.action
    assert executed.input_hash == array_hash(executed.target)
    assert executed.input_hash == catalog[selection.action].input_hash
    # And the recorded action is the one whose input actually gets forecast.
    assert selection.action in P.ACTIONS
    if selection.intervened:
        assert executed.changed
    else:
        assert not executed.changed or selection.action == P.REFERENCE_ACTION


def test_full_observed_input_contract_keeps():
    raw = panel(7)
    assert np.isfinite(raw[:, 0]).all()
    assert A.legal_actions(raw) == (P.REFERENCE_ACTION,)
    catalog = A.execute_catalog(raw)
    assert not catalog["FFILL"].changed
    assert not catalog["CONTEXT_RIDGE"].changed
    assert catalog["KEEP"].input_hash == catalog["FFILL"].input_hash

    bank = ReplayBank("bolt")
    for i in range(10):
        state = np.zeros(22)
        state[0] = 0.02 * i
        bank.add(record(action="FFILL", utility=0.9, parent=f"p{i}",
                        state=state, input_hash=f"in{i}"))
    selector = _fitted_selector(bank, k=8)
    selection = selector.select(np.zeros(22), bank, legal=A.legal_actions(raw))
    assert selection.action == P.REFERENCE_ACTION


# -- supporting contracts: metrics, aggregation, cache identity -------------


def test_metrics_use_one_denominator_for_every_method():
    target = np.arange(96, dtype=np.float64)
    prediction = target + 1.0
    scale = 2.0
    result = ME.forecast_metrics(target, prediction, mase_scale=scale,
                                 rmsse_scale=4.0)
    assert result["mae"] == pytest.approx(1.0)
    assert result["mse"] == pytest.approx(1.0)
    assert result["mase"] == pytest.approx(0.5)
    assert result["rmsse"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        ME.forecast_metrics(target, np.full(96, np.nan), mase_scale=scale,
                            rmsse_scale=4.0)


def test_aggregation_never_treats_variants_as_independent_samples():
    rows = []
    for parent, values in (("p1", [1.0, 3.0]), ("p2", [5.0])):
        for i, value in enumerate(values):
            rows.append({"method": "m", "backbone": "bolt", "horizon": 96,
                         "pattern": "P1_point", "severity": 0.1,
                         "source": "ETTh1", "parent": parent,
                         "variant": f"{parent}-v{i}", "mase": value})
    ladder = ME.hierarchical_aggregate(rows, "mase")
    parent_rows = {(r["source"], r["parent"]): r["mase"] for r in ladder["parent"]}
    assert parent_rows[("ETTh1", "p1")] == pytest.approx(2.0)
    assert parent_rows[("ETTh1", "p2")] == pytest.approx(5.0)
    source_rows = {r["source"]: r["mase"] for r in ladder["source"]}
    assert source_rows["ETTh1"] == pytest.approx(3.5)
    macro_rows = {r["method"]: r["mase"] for r in ladder["macro"]}
    assert macro_rows["m"] == pytest.approx(3.5)


def test_macro_headline_averages_condition_cells_not_the_first_one():
    """Regression: the headline is the mean over the condition cells.

    ``hierarchical_aggregate`` returns one macro row per ``(horizon, pattern)``
    cell and orders them by their condition keys.  Quoting ``macro[0]`` as the
    table's headline therefore reported a single horizon/pattern combination --
    here H192/P1_point -- as if it summarised both horizons and all four
    patterns, which also made the K/beta gate optimise one arbitrary cell.
    """
    rows = []
    for source in ("ETTh1", "ETTh2"):
        for index, parent in enumerate(("a", "b")):
            for horizon in (96, 192):
                for pattern in ("P1_point", "P2_target_block"):
                    rows.append({
                        "method": "FULL", "backbone": "bolt", "horizon": horizon,
                        "pattern": pattern, "severity": 0.1, "source": source,
                        "parent": f"{source}-{parent}",
                        "variant": f"{source}-{parent}-{horizon}-{pattern}",
                        "mase": 1.0 + 0.1 * (horizon // 96) + 0.01 * len(pattern),
                    })
    cells = ME.macro_cells(rows, "mase")
    assert len(cells) == 4
    headline = ME.macro_headline(rows, "mase")
    assert headline == pytest.approx(float(np.mean([c["mase"] for c in cells])))
    assert headline != pytest.approx(cells[0]["mase"])


def test_cache_identity_binds_every_required_field():
    base = dict(source="ETTh1", parent="p1", origin=512, context_length=512,
                horizon=96, pattern="P1_point", severity=0.1, mask_hash="m",
                input_hash="i", action="FFILL", model_family="bolt",
                checkpoint="ckpt", revision="rev", dtype="float32",
                generation_config={"quantile": 0.5})
    key = make_cache_key(**base)
    assert key == make_cache_key(**base)
    for field, value in (("severity", 0.3), ("pattern", "P4_tail"),
                         ("horizon", 192), ("dtype", "bfloat16"),
                         ("mask_hash", "other"), ("input_hash", "other"),
                         ("revision", "rev2")):
        assert make_cache_key(**{**base, field: value}) != key
    assert make_cache_key(**{**base, "generation_config": {"quantile": 0.9}}) != key


def test_replay_bank_round_trip(tmp_path):
    bank = ReplayBank("bolt", code_sha="abc", resolved_config_hash="cfg")
    for i in range(5):
        bank.add(record(action="FFILL", utility=0.1 * i, parent=f"p{i}",
                        input_hash=f"in{i}", forecast=np.full(96, float(i)),
                        target=np.arange(96, dtype=np.float64)))
    info = bank.save(tmp_path, name="replay_bank_bolt")
    assert info["records"] == 5
    reloaded = ReplayBank.load(tmp_path, name="replay_bank_bolt")
    assert len(reloaded) == 5
    assert reloaded.records[2].utility_vs_reference == pytest.approx(0.2)
    assert np.array_equal(reloaded.records[2].forecast, np.full(96, 2.0))
    assert reloaded.records[2].cache_key() == bank.records[2].cache_key()
    assert reloaded.support()["per_action"] == {"FFILL": 5}


def test_required_record_schema_is_present():
    item = record(action="KEEP", utility=0.0)
    assert item.missing_fields() == []
    for name in ("mase_scale_id", "prediction_hash", "utility_vs_reference",
                 "resolved_config_hash", "unsupported", "alias"):
        assert hasattr(item, name)
