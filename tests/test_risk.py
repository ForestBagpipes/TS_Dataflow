"""Risk evidence, hypothesis inference, and the policy that reads them."""

import numpy as np
from conftest import synth

from introact_ts.policy import PolicyConfig, propose_actions
from introact_ts.risk import (
    CorpusReference,
    RiskState,
    corpus_reference,
    infer_hypothesis,
    statistical_evidence,
)
from introact_ts.types import Action


def make(kind: str, seed: int = 0) -> np.ndarray:
    x = synth(seed)
    if kind == "spike":
        x[[80, 200, 350]] += 30.0
    elif kind == "missing":
        x[150:200] = np.nan
    elif kind == "flatline":
        x[200:250] = x[200]
    elif kind == "noise":
        x = x + np.random.RandomState(seed + 50).randn(len(x)) * 3.0
    elif kind == "shift":
        x[300:] += 25.0
    elif kind == "rare_event":
        x[220:250] += 22.0
    return x


def test_evidence_routes_each_defect_to_its_own_indicator():
    ev = {k: statistical_evidence(make(k)) for k in
          ("clean", "spike", "missing", "noise", "shift")}
    assert ev["missing"]["missing_frac"] > 0.05
    assert ev["clean"]["missing_frac"] == 0.0
    assert ev["spike"]["spike_frac"] > ev["clean"]["spike_frac"]
    assert ev["noise"]["noise_ratio"] > 2 * ev["clean"]["noise_ratio"]
    assert ev["shift"]["shift_strength"] > 0.6


def test_a_transient_event_is_not_a_level_shift():
    """The sharpest distinction in the method: did the series come back?"""
    shift = statistical_evidence(make("shift"))
    rare = statistical_evidence(make("rare_event"))
    assert shift["transient_strength"] < 0.2
    assert rare["transient_strength"] > 1.0
    # Net permanent displacement survives for the shift and cancels for the event.
    assert shift["shift_strength"] > 0.6
    assert rare["shift_strength"] < 0.2


def test_a_noisy_series_does_not_read_as_spiky():
    """Otherwise noise contamination gets routed to the despiker."""
    noise = statistical_evidence(make("noise"))
    spike = statistical_evidence(make("spike"))
    assert noise["spike_frac"] < spike["spike_frac"]


def test_corpus_reference_floors_and_caps_adaptation():
    evs = [statistical_evidence(synth(i)) for i in range(12)]
    ref = corpus_reference(evs, np.zeros(12), np.zeros(12))
    from introact_ts.risk import DEFECT_FLOORS, DEFECT_RELAX

    for key, floor in DEFECT_FLOORS.items():
        assert floor <= ref.defect_refs[key] <= floor * DEFECT_RELAX[key] + 1e-12


def test_degenerate_ood_distribution_yields_no_ood_evidence():
    """A zero-spread sigmoid would otherwise sit at 0.5 and invent OOD windows."""
    evs = [statistical_evidence(synth(i)) for i in range(12)]
    ref = corpus_reference(evs, np.zeros(12), np.zeros(12))
    assert ref.ood_scale == 0.0
    _, _, post = infer_hypothesis({}, 0.0, 0.0, ref, {})
    assert post["clean_ood"] < post["clean"]


def test_corruption_needs_both_evidence_streams():
    """A defect the model shrugs off, or a struggle with no defect, is not corruption."""
    ref = CorpusReference(risk_center=0.0, risk_scale=1.0)
    defect = {"spike_frac": 0.05}

    both, _, _ = infer_hypothesis(defect, 3.0, 0.0, ref, {})
    defect_only, _, _ = infer_hypothesis(defect, -3.0, 0.0, ref, {})
    risk_only, _, _ = infer_hypothesis({}, 3.0, 0.0, ref, {})

    assert both == "contaminated"
    assert defect_only != "contaminated" or risk_only != "contaminated"


def test_behavioural_struggle_without_a_defect_is_hard_not_corrupt():
    ref = CorpusReference(risk_center=0.0, risk_scale=1.0)
    label, _, _ = infer_hypothesis({}, 3.0, 0.0, ref, {"model_disagree": -1.0})
    assert label in ("hard", "rare_valid", "clean_ood")


def _state(hypothesis, evidence, confidence=0.8, ref=None):
    ref = ref or CorpusReference()
    return RiskState(
        window_id=0, hypothesis=hypothesis, confidence=confidence,
        evidence=evidence, reference=ref, behav_risk=1.0,
    )


def test_policy_keeps_clean_windows():
    actions = [a for a, _ in propose_actions(_state("clean", {}))]
    assert actions == [Action.KEEP]


def test_policy_abstains_on_low_confidence():
    actions = [a for a, _ in propose_actions(_state("clean", {}, confidence=0.05))]
    assert actions == [Action.ABSTAIN]


def test_policy_protects_rare_valid_windows():
    """A real event with a spike-shaped indicator must still not be despiked."""
    actions = [a for a, _ in propose_actions(_state("rare_valid", {"spike_frac": 0.05}))]
    assert Action.DESPIKE not in actions
    assert actions == [Action.KEEP]


def test_policy_allows_gap_filling_even_when_protected():
    """A gap holds no structure to destroy, so filling it stays admissible."""
    actions = [a for a, _ in propose_actions(_state("rare_valid", {"missing_frac": 0.1}))]
    assert Action.IMPUTE in actions


def test_policy_routes_each_defect_to_its_operator():
    cases = {
        "missing_frac": (0.1, Action.IMPUTE),
        "spike_frac": (0.05, Action.DESPIKE),
        "noise_ratio": (0.9, Action.DENOISE),
        "shift_strength": (2.0, Action.RESEGMENT),
    }
    for key, (value, expected) in cases.items():
        actions = [a for a, _ in propose_actions(_state("contaminated", {key: value}))]
        assert actions[0] is expected, f"{key} routed to {actions[0]}"


def test_policy_offers_competing_fill_methods():
    cands = propose_actions(_state("contaminated", {"missing_frac": 0.1}))
    methods = [p.get("method") for a, p in cands if a is Action.IMPUTE]
    assert set(methods) == {"linear", "seasonal"}


def test_policy_does_not_repeat_a_committed_operator():
    from introact_ts.types import ActionRecord, Verdict

    history = [
        ActionRecord(
            step=0, action=Action.IMPUTE, params={"method": "linear"},
            verdict=Verdict.ACCEPTED, delta_utility=1.0, struct_distortion=0.0,
            risk=0.0, utility_before=0.0, utility_after=1.0,
        )
    ]
    cands = propose_actions(_state("contaminated", {"missing_frac": 0.1}), history)
    assert Action.IMPUTE not in [a for a, _ in cands]
