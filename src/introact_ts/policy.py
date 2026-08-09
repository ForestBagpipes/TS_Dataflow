"""Action policy: which intervention to try next, if any.

The policy proposes an *ordered* list of candidates rather than committing to
one. The agent tries them in order and stops at the first that survives
verification, so a rejected hypothesis costs one probe rather than the window.

Two design choices carry most of the paper's protective behaviour:

  * windows whose risk state says hard / rare-valid / clean-OOD are not
    repaired, because their high forecast error is a property of the data
    rather than a defect. The one exception is missing data, which is the only
    defect whose repair cannot destroy real structure -- there is no real
    structure in a gap;
  * when the posterior over hypotheses is flat, the policy returns ABSTAIN
    instead of picking the most likely action anyway.
"""

from dataclasses import dataclass, field

from .risk import RiskState
from .types import Action

#: Hypotheses whose windows must be protected from repair.
PROTECTED = ("hard", "rare_valid", "clean_ood")


@dataclass
class PolicyConfig:
    min_confidence: float = 0.32
    max_steps: int = 3
    quarantine_defect: float = 6.0
    quarantine_risk: float = 3.0
    protect: tuple = PROTECTED
    allow_impute_when_protected: bool = True
    #: How many mutating candidates the policy may offer in one step. The
    #: default is unlimited, which is what makes a rejection recoverable: the
    #: agent falls through to the next proposal instead of giving up. Setting
    #: it to 1 turns the loop into propose once and accept or abandon, which
    #: isolates the value of retrying from the value of vetoing.
    max_candidates: int = 0
    denoise_ladder: tuple = ("light", "medium")
    #: Ordered conservative-first. Linear interpolation is the safe fill;
    #: seasonal donation reconstructs more shape but goes badly wrong where
    #: the periodicity is weak, so it is offered second and has to earn it.
    impute_methods: tuple = ("linear", "seasonal")


def propose_actions(
    state: RiskState,
    history: list = None,
    cfg: PolicyConfig = None,
) -> list:
    """Ordered (action, params) candidates for the current step.

    ``history`` holds the :class:`~introact_ts.types.ActionRecord`s already
    attempted on this window, so the policy never re-proposes an action that
    was just rolled back.
    """
    cfg = cfg or PolicyConfig()
    history = history or []
    # Keyed on the action *and* its parameters: two fill methods, or two
    # denoise strengths, are different proposals and each deserves its own
    # chance to be verified.
    tried = {(r.action, _key(r.params)) for r in history}
    # Once an operator has been committed, it is done with this window. The
    # alternative variants were competing ways to fix the same defect, not a
    # queue to work through: running the second one over data the first already
    # repaired re-treats a fault that is no longer there.
    committed = {r.action for r in history if r.accepted}

    def fresh(cands):
        return [
            (a, p)
            for a, p in cands
            if a not in committed and (a, _key(p)) not in tried
        ]

    if len(history) >= cfg.max_steps:
        return [(Action.KEEP, {})]

    # Insufficient evidence -> refuse rather than guess.
    if state.confidence < cfg.min_confidence:
        return [(Action.ABSTAIN, {})]

    defect = state.dominant_defect
    strength = state.defect_strength

    if state.hypothesis in cfg.protect:
        # Protected windows: only gap filling is admissible, and only when the
        # gap evidence is unambiguous.
        if cfg.allow_impute_when_protected and defect == "missing":
            fills = fresh(_impute_candidates(cfg))
            if cfg.max_candidates > 0:
                fills = fills[: cfg.max_candidates]
            if fills:
                return fills + [(Action.KEEP, {})]
        return [(Action.KEEP, {})]

    if state.hypothesis == "clean":
        return [(Action.KEEP, {})]

    # hypothesis == "contaminated"
    candidates = {
        "missing": _impute_candidates(cfg),
        "spike": [(Action.DESPIKE, {})],
        "noise": [(Action.DENOISE, {"strength": s}) for s in cfg.denoise_ladder],
        "shift": [(Action.RESEGMENT, {})],
        "none": [],
    }[defect]

    # A secondary defect gets one shot after the primary one.
    secondary = _secondary_defect(state, defect)
    if secondary:
        candidates += {
            "missing": _impute_candidates(cfg)[:1],
            "spike": [(Action.DESPIKE, {})],
            "noise": [(Action.DENOISE, {"strength": cfg.denoise_ladder[0]})],
            "shift": [(Action.RESEGMENT, {})],
        }[secondary]

    candidates = fresh(candidates)
    if cfg.max_candidates > 0:
        candidates = candidates[: cfg.max_candidates]
    if not candidates:
        return [(Action.ABSTAIN, {})] if defect == "none" else [(Action.KEEP, {})]

    if strength >= cfg.quarantine_defect and state.behav_risk >= cfg.quarantine_risk:
        candidates.append((Action.QUARANTINE, {}))
    candidates.append((Action.KEEP, {}))
    return candidates


def _key(params: dict) -> tuple:
    """Hashable identity of a parameter set, ignoring operator-reported extras."""
    keep = ("method", "strength")
    return tuple(sorted((k, params[k]) for k in keep if k in params))


def _impute_candidates(cfg: PolicyConfig) -> list:
    return [(Action.IMPUTE, {"method": m}) for m in cfg.impute_methods]


def _secondary_defect(state: RiskState, primary: str, threshold: float = 1.6) -> str:
    """The strongest remaining defect, if its evidence is clearly above the bar.

    Held to a higher standard than the primary defect on purpose. A second edit
    compounds on data the first one already rewrote, and marginal evidence for
    a co-occurring defect is more often a side effect of the first repair than
    a real second fault.
    """
    units = dict(state.defect_units)
    units.pop(primary, None)
    if not units:
        return ""
    best = max(units, key=units.get)
    return best if units[best] >= threshold else ""
