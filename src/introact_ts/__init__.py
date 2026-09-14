"""IntroAct-TS: an intervention-verified, reversible data curation agent for
time-series foundation models.

Every curation action is treated as a candidate intervention that must earn its
commit: it is applied to a sandbox copy, the frozen TSFM is re-probed on that
copy, and the edit survives only if model utility improved *and* temporal
structure was preserved *and* the decision risk is acceptable. Otherwise the
agent rolls back, tries another action, or refuses to act.

Pure method layer, zero file IO. Experiment shells live in ``experiments/``.
"""

from .actions import ActionOutcome, apply_action
from .agent import AgentConfig, IntroActAgent
from .calibration import PeerCalibration, calibrate, ood_scores, recalibrate_one
from .policy import PolicyConfig, propose_actions
from .probe import ProbeConfig, SIGNAL_NAMES, materialize_for_probe, probe_window, reference_scale
from .profiling import extract_statistical_profile
from .risk import RiskState, build_risk_state, statistical_evidence
from .structure import structure_distortion
from .tsfm import SurrogateTSFM, make_model_pool
from .types import (
    Action,
    ActionRecord,
    GovernanceTrace,
    ProbeResult,
    TSWindow,
    Verdict,
)
from .verify import VerifyConfig, action_risk, verify

__version__ = "0.2.0"

__all__ = [
    "Action",
    "ActionOutcome",
    "ActionRecord",
    "AgentConfig",
    "GovernanceTrace",
    "IntroActAgent",
    "PeerCalibration",
    "PolicyConfig",
    "ProbeConfig",
    "ProbeResult",
    "RiskState",
    "SIGNAL_NAMES",
    "SurrogateTSFM",
    "TSWindow",
    "Verdict",
    "VerifyConfig",
    "action_risk",
    "apply_action",
    "build_risk_state",
    "calibrate",
    "extract_statistical_profile",
    "make_model_pool",
    "materialize_for_probe",
    "ood_scores",
    "probe_window",
    "propose_actions",
    "recalibrate_one",
    "reference_scale",
    "statistical_evidence",
    "structure_distortion",
    "verify",
]
