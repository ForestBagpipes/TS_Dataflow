"""IntroAct-TS v4.4-r2 -- the decision-regret ranking revision.

This package is strictly additive.  It reads the v4.4 replay artifacts (the
frozen masks, the candidate inputs, the frozen TSFM predictions and the
realised losses) but never writes to them, and it imports ``introact_ts.v44``
read-only.  The v4.4 negative result, its banks, its gate, its ablation table
and its commit chain stay exactly as they are.

What changes is only *how the action is chosen*: the KNN gain average plus a
fixed beta lower-confidence bound is replaced by a pairwise decision-regret
ranker with a single lightweight confidence veto.
"""

from __future__ import annotations

from . import dataset, evaluate, features, ranking, regret  # noqa: F401

__all__ = ["dataset", "evaluate", "features", "ranking", "regret"]
