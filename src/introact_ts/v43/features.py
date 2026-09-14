"""Policy views contain only acquired evidence; no reference to hidden cache."""
from dataclasses import dataclass
from .schemas import require

TOOLS = ("residual", "tsicl_cov", "history_probe")


@dataclass(frozen=True)
class VisibleState:
    history: tuple = ()
    evidence: tuple = ()  # ordered (tool, bounded scalar evidence) pairs

    def acquire(self, tool, value):
        import math
        require(tool in TOOLS and tool not in self.history, "invalid/repeated tool")
        require(math.isfinite(value), "invalid evidence")
        return VisibleState(self.history+(tool,), self.evidence+((tool, float(value)),))


def extract_available_features(state):
    evidence = dict(state.evidence)
    require(tuple(evidence) == state.history, "state/evidence mismatch")
    return tuple((evidence.get(t), t not in evidence) for t in TOOLS)
