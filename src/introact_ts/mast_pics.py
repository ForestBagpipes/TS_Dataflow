"""MAST-PICS: Metric-Aware Support-Tested PICS (v3.3).

Pre-registered in ``docs/v3_3_mast_pics_design.md``. Three changes against
v3.2 PICS, all fixed in advance:

  * asymmetric heads — the benefit head uses the joint feature set and
    predicts P(beneficial); the harm head uses only the TSFM counterfactual
    and structure-consequence features and predicts P(harmful). Statistical
    features cannot bypass the harm gate;
  * a support–consequence certificate replaces the ensemble-spread OOD gate.
    Spread measures source disagreement; on unseen OOD forms the members agree
    with each other, which is not support. The support index is a cosine kNN
    (K=20) over the training fold's pre-action statistical profiles, the same
    space ``calibration.ood_scores`` measures; the consequence check is the
    frozen v2 family structural threshold. Only ``low_support AND
    unstable_action`` forces KEEP, so unfamiliar-but-valid data with a tame
    action is not refused;
  * labels come from the v3.3 action-semantic definition (IMPUTE's KEEP
    counterfactual is the probe-materialised series), so this module is only
    meaningful against ``results/v33_training_data.jsonl``.

RESEGMENT stays closed: diagnosis and oracle tables only, never committed.

Blacklist honoured: no true_kind, stratum, clean series/hash, true NMSE, true
repair gain, source ID, or v2 verdict enters a feature or a decision.
``pics.py`` is untouched, so v3.2 remains replayable.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize as sk_normalize

from .contextual_shield import (
    CandidateFeatures, ShieldConfig, select_episode_thresholds,
)
from .pics import (
    ELIGIBLE_FAMILIES, PICS_JOINT_FEATURES, PICS_TSFM_FEATURES, _EnsembleHead,
)
from .verify import VerifyConfig, tau_for

#: The frozen v2 verification configuration, the structural reference.
V2_FROZEN = VerifyConfig(
    tau=0.02, epsilon=0.005, eta=0.5,
    tau_by_family={"DENOISE": 0.1, "DESPIKE": 0.0, "IMPUTE": 0.02,
                   "RESEGMENT": 0.4})

#: Deployable addition to the joint set: the missing share of the input
#: window, measured on the corrupted series alone.
MAST_BENEFIT_FEATURES = PICS_JOINT_FEATURES + ("missing_fraction",)
MAST_HARM_FEATURES = PICS_TSFM_FEATURES

GATE_MODES = ("none", "spread", "support", "structure",
              "support_and_consequence", "support_and_consequence_hard")


def v2_structure_ok(family: str, struct_distortion: float,
                    cfg: VerifyConfig = V2_FROZEN) -> bool:
    """The frozen v2 family structural condition on its own."""
    return float(struct_distortion) < tau_for(family, cfg)


def v2_hard_gate_ok(row: dict, cfg: VerifyConfig = V2_FROZEN) -> bool:
    """The full frozen v2 conjunction on one candidate row."""
    return (float(row["delta_utility"]) > cfg.epsilon
            and v2_structure_ok(row["family"], row["struct_distortion"], cfg)
            and float(row["risk"]) < cfg.eta)


def _feats_of(row, feature_names) -> CandidateFeatures:
    """Features dict first, then deployable top-level row fields."""
    feats = row["features"]
    return CandidateFeatures(
        values=np.array([feats.get(n, row.get(n, 0.0)) for n in feature_names],
                        dtype=object),
        feature_names=tuple(feature_names),
    )


class _ConstantHead:
    """Degenerate ensemble for a fold whose target has a single class."""

    def __init__(self, value: float):
        self.value = float(value)

    def pessimistic(self, feats):
        return np.full(len(feats), self.value)

    def spread(self, feats):
        return np.zeros(len(feats))


class SupportIndex:
    """Cosine kNN support index over pre-action statistical profiles.

    Fit only on the current fold's training windows. ``score`` is the mean
    cosine distance to the K nearest training profiles; ``exclude_self`` is
    for scoring the index's own windows (ID calibration), where the nearest
    neighbour is the query itself.
    """

    def __init__(self, K: int = 20):
        self.K = int(K)
        self._knn: Optional[NearestNeighbors] = None
        self._k_fit = 0

    def fit(self, profiles: np.ndarray):
        P = sk_normalize(np.nan_to_num(np.asarray(profiles, dtype=np.float64)))
        self._k_fit = int(min(self.K + 1, len(P)))
        self._knn = NearestNeighbors(
            n_neighbors=self._k_fit, metric="cosine").fit(P)
        return self

    def score(self, profiles: np.ndarray, exclude_self: bool = False) -> np.ndarray:
        Q = sk_normalize(np.nan_to_num(np.asarray(profiles, dtype=np.float64)))
        d, _ = self._knn.kneighbors(Q)
        if exclude_self:
            rest = d[:, 1:]
            return rest.mean(axis=1) if rest.shape[1] else np.zeros(len(Q))
        k = min(self.K, d.shape[1])
        return d[:, :k].mean(axis=1) if k else np.zeros(len(Q))


class MASTPICS:
    """Asymmetric dual-head shield with a support–consequence certificate."""

    def __init__(self, cfg: ShieldConfig = None,
                 gate_mode: str = "support_and_consequence", K: int = 20):
        assert gate_mode in GATE_MODES
        self.cfg = cfg or ShieldConfig()
        self.gate_mode = gate_mode
        self.K = int(K)
        self.heads: Dict[str, Tuple[object, object]] = {}
        self.global_heads: Optional[Tuple[object, object]] = None
        self.thresholds: Dict[str, Tuple[float, float]] = {}
        self.support = SupportIndex(K)
        self.support_q95: float = np.inf
        self.spread_cap: float = np.inf
        self.calibration_report: dict = {}

    # -- pieces ---------------------------------------------------------------

    def _build(self, rows, target, feature_names, kind):
        feats = [_feats_of(r, feature_names) for r in rows]
        y = np.array([r[target] for r in rows], dtype=int)
        if len(set(y.tolist())) < 2:
            return _ConstantHead(y[0] if len(y) else 0.0)
        src = np.array([r["dataset"] for r in rows], dtype=str)
        head = _EnsembleHead(self.cfg, feature_names, kind)
        return head.fit(feats, y, src)

    def _heads_for(self, family: str):
        return self.heads.get(family, self.global_heads)

    def _scores(self, row) -> Tuple[float, float, float]:
        bs_h, harm_h = self._heads_for(row["family"])
        fb = [_feats_of(row, MAST_BENEFIT_FEATURES)]
        fh = [_feats_of(row, MAST_HARM_FEATURES)]
        return (float(bs_h.pessimistic(fb)[0]),
                float(harm_h.pessimistic(fh)[0]),
                float(harm_h.spread(fh)[0]))

    def _support_distance(self, row) -> float:
        return float(self.support.score([row["profile"]])[0])

    def _hazard(self, row, spread: float, support_distance: float) -> bool:
        mode = self.gate_mode
        if mode == "none":
            return False
        if mode == "spread":
            return spread > self.spread_cap
        low_support = support_distance > self.support_q95
        if mode == "support":
            return low_support
        unstable = not v2_structure_ok(row["family"], row["struct_distortion"])
        if mode == "structure":
            return unstable
        return low_support and unstable  # support_and_consequence(+_hard)

    # -- training + calibration -------------------------------------------------

    def fit(self, train_rows: List[dict], cal_rows: List[dict]):
        fam_train: Dict[str, List[int]] = {}
        for i, r in enumerate(train_rows):
            fam_train.setdefault(r["family"], []).append(i)

        eligible = [f for f in ELIGIBLE_FAMILIES
                    if len(fam_train.get(f, [])) >= self.cfg.min_family_n]
        for fam in eligible:
            rows = [train_rows[i] for i in fam_train[fam]]
            self.heads[fam] = (
                self._build(rows, "beneficial", MAST_BENEFIT_FEATURES, "bs"),
                self._build(rows, "harmful", MAST_HARM_FEATURES, "harm"))
        self.global_heads = (
            self._build(train_rows, "beneficial", MAST_BENEFIT_FEATURES, "bs"),
            self._build(train_rows, "harmful", MAST_HARM_FEATURES, "harm"))
        self._eligible = set(eligible)

        # Support index on the fold's training windows, one row per window.
        seen, profiles = set(), []
        for r in train_rows:
            if r["sample_uid"] not in seen:
                seen.add(r["sample_uid"])
                profiles.append(r["profile"])
        self.support.fit(np.asarray(profiles, dtype=np.float64))

        # Calibration fold scoring: scores and support distances first, then
        # the ID-calibrated thresholds (q95, spread cap), then hazards against
        # those thresholds -- support distances do not depend on the
        # thresholds, so this is a relabelling pass, not a second look.
        cal = []
        cal_distances = {}
        for r in cal_rows:
            s_bs, s_h, spread = self._scores(r)
            sd = self._support_distance(r)
            cal_distances[r["sample_uid"]] = sd
            cal.append({
                "row": r, "sample_uid": r["sample_uid"], "family": r["family"],
                "score_bs": s_bs, "score_harm": s_h, "spread": spread,
                "support_distance": sd,
                "true_loss": r["true_loss"], "beneficial": r["beneficial"],
            })
        dvals = sorted(cal_distances.values())
        self.support_q95 = float(np.percentile(dvals, 95)) if dvals else np.inf
        spreads = [c["spread"] for c in cal]
        self.spread_cap = float(np.percentile(spreads, 95)) if spreads else np.inf
        for c in cal:
            r = c.pop("row")
            c["_hazard"] = self._hazard(r, c["spread"], c["support_distance"])
            c["_hard_fail"] = not v2_hard_gate_ok(r)

        # Episode replay: hazard (and in the hard arm, v2-hard-gate failures)
        # are candidate-level rollbacks, so they leave the replay list.
        hard = self.gate_mode == "support_and_consequence_hard"
        by_uid: Dict[str, List[dict]] = {}
        for c in cal:
            if c["_hazard"] or (hard and c["_hard_fail"]):
                continue
            c = {k: v for k, v in c.items() if not k.startswith("_")}
            by_uid.setdefault(c["sample_uid"], []).append(c)
        self.thresholds, self.calibration_report = select_episode_thresholds(
            list(by_uid.values()), dual=True, alpha=self.cfg.alpha,
            family_order=[f for f in ELIGIBLE_FAMILIES], per_family=True)
        return self

    # -- deployment decision ----------------------------------------------------

    def decide(self, row: dict) -> Tuple[bool, str]:
        family = row["family"]
        if family not in ELIGIBLE_FAMILIES:
            return False, "family_closed"
        thr = self.thresholds.get(family)
        if thr is None:
            return False, "no_threshold"
        if family not in self._eligible and not self.cfg.global_fallback:
            return False, "family_ineligible"
        s_bs, s_h, spread = self._scores(row)
        if self._hazard(row, spread, self._support_distance(row)):
            return False, "ood_hazard"
        if self.gate_mode == "support_and_consequence_hard" \
                and not v2_hard_gate_ok(row):
            return False, "v2_hard_gate"
        if s_h > thr[1]:
            return False, "harm_cap"
        if s_bs < thr[0]:
            return False, "benefit_threshold"
        return True, "accepted"
