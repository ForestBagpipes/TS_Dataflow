"""IntroAct-TS: an intervention-verified, reversible data curation agent for
time-series foundation models.

Every curation action is treated as a candidate intervention that must earn its
commit: it is applied to a sandbox copy, the frozen TSFM is re-probed on that
copy, and the edit survives only if model utility improved *and* temporal
structure was preserved *and* the decision risk is acceptable. Otherwise the
agent rolls back, tries another action, or refuses to act.

Pure method layer, zero file IO. Experiment shells live in ``experiments/``.
"""

# Keep isolated model workers independent of the historical core stack.
from importlib import import_module
from .types import Action, ActionRecord, GovernanceTrace, ProbeResult, TSWindow, Verdict
# Eagerly bind this small NumPy-only module because its exported function has
# the same name as the submodule; lazy binding would change the legacy API.
from .verify import VerifyConfig, action_risk, verify

_LAZY_EXPORTS = {
    name: module
    for module, names in {
        "actions": ("ActionOutcome", "apply_action"),
        "agent": ("AgentConfig", "IntroActAgent"),
        "calibration": ("PeerCalibration", "calibrate", "ood_scores", "recalibrate_one"),
        "policy": ("PolicyConfig", "propose_actions"),
        "probe": ("ProbeConfig", "SIGNAL_NAMES", "materialize_for_probe", "probe_window", "reference_scale"),
        "profiling": ("extract_statistical_profile",),
        "risk": ("RiskState", "build_risk_state", "statistical_evidence"),
        "structure": ("structure_distortion",),
        "tsfm": ("SurrogateTSFM", "make_model_pool"),
    }.items()
    for name in names
}


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module("." + _LAZY_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


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
