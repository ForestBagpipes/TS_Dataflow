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

#: Parameter rungs per operator, from the operator's own default outwards.
#:
#: The diagnosis in `docs/number_selfchecks.md` is that the proposer routes one
#: dominant defect to one operator at one parameter setting, so 79.2 percent of
#: windows offer the policy nothing to rank and a refusal ends the episode with
#: no second attempt. This table is the second axis. The policy chooses among
#: operators at a fixed rung, and the shield's rejection reason moves the rung:
#: a structural veto means the edit reshaped too much, so the next attempt is
#: gentler; a utility veto means it did not change enough to register, so the
#: next attempt is stronger.
#:
#: The conservative rungs for DESPIKE and RESEGMENT are the ones
#: `spo.INJECT_PARAMS` already names as each operator's least aggressive
#: setting, so the two tables agree rather than each having its own idea of
#: conservative.
LADDER = {
    Action.DESPIKE: {
        "default": {"n_sigma": 4.0, "window": 11, "max_width": 3},
        "conservative": {"n_sigma": 6.0, "window": 11, "max_width": 1},
        "aggressive": {"n_sigma": 2.5, "window": 7, "max_width": 3},
    },
    Action.DENOISE: {
        "default": {"strength": "medium"},
        "conservative": {"strength": "light"},
        # The third rung `op_denoise` already implements and nothing offered.
        "aggressive": {"strength": "heavy"},
    },
    # Conservatism is carried by `penalty`, not by `min_keep_frac`. Measured on
    # 91 mixed windows, raising `min_keep_frac` does not make the cut gentler,
    # it makes the operator refuse to act: 0.5 leaves 30 windows executable,
    # 0.7 leaves 11 and 0.9 leaves 2. A rung that cannot run is not a
    # conservative rung, it is a missing one. `penalty` moves the right way and
    # gently, 8.0 leaves 26 executable and 20.0 leaves 37, because a higher
    # penalty admits only the clearest break.
    Action.RESEGMENT: {
        "default": {"penalty": 12.0, "min_size": 24, "min_keep_frac": 0.5},
        "conservative": {"penalty": 20.0, "min_size": 24, "min_keep_frac": 0.5},
        "aggressive": {"penalty": 8.0, "min_size": 24, "min_keep_frac": 0.4},
    },
    # `min_run` is what separates the two gentle rungs. It is the shortest
    # frozen stretch treated as a gap, so raising it fills less and leaves more
    # of the original alone. Without it `default` and `conservative` were the
    # same dictionary and `fresh` dropped one of them as already tried.
    Action.IMPUTE: {
        "default": {"method": "linear", "min_run": 16},
        "conservative": {"method": "linear", "min_run": 32},
        # Seasonal donation reconstructs more shape and goes badly wrong where
        # the periodicity is weak, which is the aggressive end of this operator.
        "aggressive": {"method": "seasonal", "min_run": 8},
    },
}

#: The routing the ladder path reuses, so the two paths cannot disagree about
#: which operator a defect calls for.
_DEFECT_OPERATOR = {
    "missing": Action.IMPUTE,
    "spike": Action.DESPIKE,
    "noise": Action.DENOISE,
    "shift": Action.RESEGMENT,
}

#: Order the rungs are offered in, conservative before aggressive so that the
#: fixed rule, which takes the first admissible candidate, prefers the gentler
#: setting. The learned policy reorders this; the fixed rule does not.
RUNG_ORDER = ("default", "conservative", "aggressive")

#: Which rung the previous verdict sends the next attempt to. Keyed on the
#: verdict's string value so this module does not import the shield's enum.
RUNG_AFTER = {
    "ROLLED_BACK_STRUCTURE": "conservative",
    "ROLLED_BACK_UTILITY": "aggressive",
    "ROLLED_BACK_RISK": "conservative",
}


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
    #: Evidence a co-occurring defect must carry before its operator joins the
    #: candidate list. Held above the primary defect's bar on purpose, see
    #: `_secondary_defect`. Exposed here rather than hard coded because it is
    #: the single number that decides how often the policy faces a choice at
    #: all: measured on the xl corpus at the default, 79.2 percent of windows
    #: offer the policy zero or one operator, so the upper confidence bound has
    #: nothing to rank. `experiments/probe_candidate_pool.py` sweeps it.
    secondary_threshold: float = 1.6
    #: Turns on the parameter ladder and the retry loop it feeds. Off by
    #: default so every result produced before it is unaffected. With it on,
    #: `propose_actions` offers every admissible operator at the rung the last
    #: verdict selected, and `Agent.curate_window` no longer ends the episode
    #: when a whole candidate list is refused.
    enable_param_ladder: bool = False
    #: When set, a low strength DENOISE joins the candidate list on any window
    #: the proposer would otherwise route to a single operator. It is the
    #: cheapest way to give the policy a second arm to compare against, and it
    #: is off by default because it changes what every arm proposes, not just
    #: the learning ones.
    add_fallback: bool = False


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
    if cfg.enable_param_ladder:
        # Every admissible operator at one rung, so the policy chooses across
        # operators while the rung moves with the shield's reason. The two axes
        # are separate on purpose: mixing them would let a refusal on one
        # operator change which operators are on offer, and then a rejection
        # would be doing the proposer's job.
        wanted = []
        for d in (defect, _secondary_defect(state, defect,
                                            cfg.secondary_threshold)):
            if not d or d == "none":
                continue
            act = _DEFECT_OPERATOR.get(d)
            if act is not None and act not in wanted:
                wanted.append(act)
        # Every rung of every routed operator, conservative first so the fixed
        # rule keeps the gentler setting's precedence. The rungs are offered
        # together rather than one per round because that is what gives the
        # policy something to rank: three settings of one operator have three
        # different chances of clearing the shield, and which one to try first
        # is a decision with consequences. `fresh` still removes a setting
        # already judged, so a later round proposes only what is left.
        #
        # This is also the candidate set the calibration sees. Calibrating on
        # one candidate distribution and deploying on another is the same
        # mistake as calibrating on one corpus and deploying on another, which
        # is recorded in docs/diagnostic-playbook.md as tree nine.
        cands = [(a, _at_rung(a, r)) for a in wanted for r in RUNG_ORDER]
        # An operator the routing did not reach is still worth one attempt at
        # the gentle end, which is what gives the policy something to compare
        # the routed choice against on a window with a single clear defect.
        if cfg.add_fallback:
            fb = Action.DENOISE
            if fb not in wanted:
                cands.append((fb, _at_rung(fb, "conservative")))
        cands = fresh(cands)
        if cfg.max_candidates > 0:
            cands = cands[: cfg.max_candidates]
        if not cands:
            return [(Action.ABSTAIN, {})] if defect == "none" else [(Action.KEEP, {})]
        if (strength >= cfg.quarantine_defect
                and state.behav_risk >= cfg.quarantine_risk):
            cands.append((Action.QUARANTINE, {}))
        cands.append((Action.KEEP, {}))
        return cands

    candidates = {
        "missing": _impute_candidates(cfg),
        "spike": [(Action.DESPIKE, {})],
        "noise": [(Action.DENOISE, {"strength": s}) for s in cfg.denoise_ladder],
        "shift": [(Action.RESEGMENT, {})],
        "none": [],
    }[defect]

    # A secondary defect gets one shot after the primary one.
    secondary = _secondary_defect(state, defect, cfg.secondary_threshold)
    if secondary:
        candidates += {
            "missing": _impute_candidates(cfg)[:1],
            "spike": [(Action.DESPIKE, {})],
            "noise": [(Action.DENOISE, {"strength": cfg.denoise_ladder[0]})],
            "shift": [(Action.RESEGMENT, {})],
        }[secondary]

    # A second arm to compare the routed one against. Without it the proposer
    # is a deterministic router and the policy has nothing to choose between on
    # most windows. Appended rather than prepended so the routed operator keeps
    # its position under the fixed rule, which is what makes the comparison
    # between the fixed rule and the learned one a comparison of ordering
    # rather than of what was offered.
    if cfg.add_fallback and defect != "none":
        fb = (Action.DENOISE, {"strength": cfg.denoise_ladder[0]})
        if not any(a is fb[0] and _key(p) == _key(fb[1]) for a, p in candidates):
            candidates = candidates + [fb]

    candidates = fresh(candidates)
    if cfg.max_candidates > 0:
        candidates = candidates[: cfg.max_candidates]
    if not candidates:
        return [(Action.ABSTAIN, {})] if defect == "none" else [(Action.KEEP, {})]

    if strength >= cfg.quarantine_defect and state.behav_risk >= cfg.quarantine_risk:
        candidates.append((Action.QUARANTINE, {}))
    candidates.append((Action.KEEP, {}))
    return candidates


#: Parameters that make two proposals of the same operator different attempts.
#: The ladder's keys are all here: without `n_sigma` and `min_keep_frac` two
#: rungs of DESPIKE or RESEGMENT would hash to the same identity and `fresh`
#: would drop the retry as something already tried, which is the exact bug the
#: ladder exists to avoid.
IDENTITY_KEYS = ("method", "strength", "n_sigma", "window", "max_width",
                 "penalty", "min_size", "min_keep_frac", "min_run")


def _key(params: dict) -> tuple:
    """Hashable identity of a parameter set, ignoring operator-reported extras."""
    return tuple(sorted((k, params[k]) for k in IDENTITY_KEYS if k in params))


def _rung(history: list) -> str:
    """Which parameter rung the last verdict sends this attempt to.

    The first attempt on a window uses the operator's default. After that the
    shield's reason decides: too much reshaping means go gentler, too little
    change to register means go stronger. This is the same routing
    `spo.table_for` uses to pick a value table, so the policy's estimate for a
    rung and the rung itself always refer to the same situation.
    """
    for r in reversed(history or []):
        name = getattr(getattr(r, "verdict", None), "value", None)
        if name in RUNG_AFTER:
            return RUNG_AFTER[name]
        if name == "ACCEPTED":
            return "default"
    return "default"


def rung_of(action, params) -> str:
    """Which rung a parameter dict came from.

    Falls back to `default` for anything the ladder does not describe, which is
    what every candidate looks like when the ladder is switched off. That makes
    the value table's rung dimension collapse onto one slot per operator in the
    off case, so the off case ranks exactly as it did before the dimension
    existed.
    """
    table = LADDER.get(action)
    if not table:
        return "default"
    k = _key(params or {})
    for name in RUNG_ORDER:
        if name in table and _key(table[name]) == k:
            return name
    return "default"


def _at_rung(action, rung: str) -> dict:
    """The operator's parameters at one rung, falling back to its default."""
    table = LADDER.get(action)
    if not table:
        return {}
    return dict(table.get(rung, table["default"]))


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
