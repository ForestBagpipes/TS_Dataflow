"""Core exchange types for IntroAct-TS.

Every stage of the agent (perceive -> act -> verify -> commit/rollback)
passes these records around. They are plain dataclasses with no file IO
so the method layer stays pure and testable.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class Action(str, Enum):
    """The curation action space.

    KEEP        commit the window unchanged
    IMPUTE      fill missing / flatlined segments
    DESPIKE     remove isolated spikes, preserving the surrounding shape
    DENOISE     reduce additive high-frequency noise
    RESEGMENT   cut the window at a detected changepoint, keep the longer piece
    QUARANTINE  set aside a high-risk window that cannot be repaired reliably
    ABSTAIN     refuse to act because the evidence is insufficient
    """

    KEEP = "KEEP"
    IMPUTE = "IMPUTE"
    DESPIKE = "DESPIKE"
    DENOISE = "DENOISE"
    RESEGMENT = "RESEGMENT"
    QUARANTINE = "QUARANTINE"
    ABSTAIN = "ABSTAIN"


#: Actions that materially rewrite the series and therefore need verification.
MUTATING_ACTIONS = frozenset(
    {Action.IMPUTE, Action.DESPIKE, Action.DENOISE, Action.RESEGMENT}
)

#: Actions that terminate the episode without producing a repaired series.
TERMINAL_ACTIONS = frozenset({Action.KEEP, Action.QUARANTINE, Action.ABSTAIN})


class Verdict(str, Enum):
    """Outcome of verifying one candidate intervention."""

    ACCEPTED = "ACCEPTED"
    ROLLED_BACK_UTILITY = "ROLLED_BACK_UTILITY"
    ROLLED_BACK_STRUCTURE = "ROLLED_BACK_STRUCTURE"
    ROLLED_BACK_RISK = "ROLLED_BACK_RISK"
    NO_OP = "NO_OP"


ROLLBACK_VERDICTS = frozenset(
    {
        Verdict.ROLLED_BACK_UTILITY,
        Verdict.ROLLED_BACK_STRUCTURE,
        Verdict.ROLLED_BACK_RISK,
    }
)


@dataclass
class TSWindow:
    """A single time-series window plus its ground-truth annotations.

    ``series`` is the working copy the agent reads and rewrites; ``clean_series``
    is the pre-contamination reference used only by the evaluator, never by the
    agent. ``stratum`` records which evaluation layer the window came from
    (clean / contaminated / hard / rare_valid / changepoint / clean_ood).
    """

    window_id: int
    series: np.ndarray
    freq: str = "H"
    dataset: str = ""
    split: str = "train"
    stratum: str = "clean"
    contamination: Optional[str] = None
    clean_series: Optional[np.ndarray] = field(default=None, repr=False)
    corrupt_mask: Optional[np.ndarray] = field(default=None, repr=False)
    seed: int = 42

    @property
    def is_contaminated(self) -> bool:
        return self.contamination is not None

    def copy_with(self, series: np.ndarray) -> "TSWindow":
        """Return a sandboxed copy carrying the same annotations."""
        return TSWindow(
            window_id=self.window_id,
            series=np.asarray(series, dtype=np.float64).copy(),
            freq=self.freq,
            dataset=self.dataset,
            split=self.split,
            stratum=self.stratum,
            contamination=self.contamination,
            clean_series=self.clean_series,
            corrupt_mask=self.corrupt_mask,
            seed=self.seed,
        )


@dataclass
class ProbeResult:
    """Behavioural response of a frozen TSFM to one window.

    ``vector`` is the flat behaviour signature used for peer calibration.
    ``utility`` is the scalar model-utility score (higher is better); the agent
    compares it before and after an intervention. Raw hidden states and
    attention maps are aggregated here and never retained.
    """

    vector: np.ndarray
    utility: float
    parts: dict = field(default_factory=dict)

    @property
    def dim(self) -> int:
        return int(self.vector.shape[0])


@dataclass
class ActionRecord:
    """One candidate intervention and everything needed to audit or undo it."""

    step: int
    action: Action
    params: dict
    verdict: Verdict
    delta_utility: float
    struct_distortion: float
    risk: float
    utility_before: float
    utility_after: float
    struct_parts: dict = field(default_factory=dict)
    cost: float = 0.0
    note: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict is Verdict.ACCEPTED


@dataclass
class GovernanceTrace:
    """The full, replayable curation record for one window."""

    window_id: int
    stratum: str
    contamination: Optional[str]
    initial_series: np.ndarray = field(repr=False)
    final_series: np.ndarray = field(repr=False)
    records: list = field(default_factory=list)
    final_state: str = "KEEP"
    initial_utility: float = 0.0
    final_utility: float = 0.0
    risk_state: dict = field(default_factory=dict)
    probe_calls: int = 0
    #: Index in the original window where the final series begins. Non-zero
    #: only after a RESEGMENT that kept a later segment; evaluation needs it to
    #: line the curated series up against its pristine reference.
    crop_offset: int = 0

    @property
    def accepted_actions(self) -> list:
        return [r.action for r in self.records if r.accepted]

    @property
    def n_rollbacks(self) -> int:
        return sum(1 for r in self.records if r.verdict in ROLLBACK_VERDICTS)

    @property
    def modified(self) -> bool:
        """True if any mutating action was committed.

        **This is the permissive reading and it is not the one to report.** An
        operator can be admitted and leave the series unchanged, for instance an
        imputation on a window that turned out to have nothing to fill, and this
        property counts that as modified.

        Two measurements of the same run disagreed because of it, 71 windows by
        this reading against 62 by the strict one, and 62 is correct for any
        statement of the form "the method edited N windows". Use
        :func:`content_modified` for that. This property is kept because the
        governance trace needs to know whether the loop committed anything,
        which is a different question.
        """
        return any(r.accepted and r.action in MUTATING_ACTIONS for r in self.records)

    def content_modified(self, original) -> bool:
        """True if the series content actually changed, the strict reading.

        ``original`` is the window's input series. A crop counts as a change.
        This is the definition every reported edit count uses.
        """
        import numpy as np

        cur = np.asarray(self.final_series, dtype=np.float64)
        src = np.asarray(original, dtype=np.float64)
        if self.crop_offset:
            return True
        if len(cur) != len(src):
            return True
        return not np.allclose(np.nan_to_num(cur), np.nan_to_num(src),
                               rtol=0, atol=1e-12)

    def summary(self) -> dict:
        """Flat, JSON friendly record of the episode.

        ``steps`` carries the per candidate quantities the acceptance rule
        actually saw. Without them an offline audit can tell that a candidate
        was refused but not by how much it missed, so it cannot separate a
        decision that was close from one that was not, and it has to
        reconstruct operator parameters by inference rather than reading them.
        """
        return {
            "window_id": self.window_id,
            "stratum": self.stratum,
            "contamination": self.contamination,
            "final_state": self.final_state,
            "modified": self.modified,
            "n_steps": len(self.records),
            "n_rollbacks": self.n_rollbacks,
            "accepted": [a.value for a in self.accepted_actions],
            "attempted": [r.action.value for r in self.records],
            "verdicts": [r.verdict.value for r in self.records],
            "initial_utility": self.initial_utility,
            "final_utility": self.final_utility,
            "delta_utility": self.final_utility - self.initial_utility,
            "probe_calls": self.probe_calls,
            "crop_offset": self.crop_offset,
            # The state the policy conditioned on. Without it an offline audit
            # cannot ask whether the agent knew when it was unsure, which is
            # what a risk coverage curve measures.
            "hypothesis": self.risk_state.get("hypothesis"),
            "confidence": self.risk_state.get("confidence"),
            "behav_risk": self.risk_state.get("behav_risk"),
            "dominant_defect": self.risk_state.get("dominant_defect"),
            "defect_strength": self.risk_state.get("defect_strength"),
            "steps": [
                {
                    "action": r.action.value,
                    "params": {
                        k: v for k, v in r.params.items()
                        if isinstance(v, (int, float, str, bool))
                    },
                    "verdict": r.verdict.value,
                    "delta_utility": r.delta_utility,
                    "struct_distortion": r.struct_distortion,
                    "risk": r.risk,
                    "utility_before": r.utility_before,
                    "utility_after": r.utility_after,
                    "cost": r.cost,
                }
                for r in self.records
            ],
        }
