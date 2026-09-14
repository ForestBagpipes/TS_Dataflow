"""PICS: Pessimistic Invariant-Checked Shield (v3.2).

Pre-registered in ``docs/v3_2_pics_preregistration.md``. The v3-pre review
showed the binding failure is cross-source transfer: scores calibrated on seen
datasets admit harmful candidates on unseen ones. PICS answers with three
mechanisms, all fixed in advance:

  * per-family dual heads — one model for P(beneficial_and_safe), one for
    P(harmful), each trained per action family with a global fallback;
  * pessimistic cross-source bounds — each head is a leave-one-source-out
    ensemble over the training fold's source datasets; the deployed score is
    the MINIMUM for benefit and the MAXIMUM for harm, so a candidate that any
    source-exclusive model distrusts is treated by its worst reading;
  * a support gate — the harm ensemble's spread measures how much the sources
    disagree; above the calibration fold's 95th percentile the candidate is
    refused outright (OOD / low support defaults to KEEP).

Calibration replays whole episodes (first commit wins) on the calibration fold
and bounds corpus damage with the project's corrected risk; it never counts
candidates independently, because deployment never judges them independently.

RESEGMENT is closed in this round: its crop has zero oracle safe headroom, so
no threshold is ever issued for it. This is a pre-registered arm rule.

Blacklist honoured: no true_kind, no clean series, no source ID enters a
feature or a deployment decision; labels and sources are used only to train
and calibrate offline.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from .contextual_shield import (
    ALL_FEATURES, CATEGORICAL_FEATURES, CandidateFeatures, ContextualShield,
    ShieldConfig, episode_replay, select_episode_thresholds,
)
from .types import Verdict

#: Families eligible to commit this round. RESEGMENT is diagnosis-only.
ELIGIBLE_FAMILIES = ("DENOISE", "DESPIKE", "IMPUTE")

#: Source-invariant PICS feature sets: absolute-scale features are replaced by
#: their within-window normalised counterparts.
_DROPPED_SCALE_FEATURES = {
    "utility_before", "utility_after", "delta_utility",
    "probe_delta_mean", "probe_delta_std", "probe_delta_max",
}
_TSFM_RAW = {
    "behav_risk", "delta_utility", "utility_before", "utility_after",
    "probe_delta_mean", "probe_delta_std", "probe_delta_max",
    "forecast_nrmse_delta", "recon_nrmse_med_delta", "recon_nrmse_iqr_delta",
    "multiview_disagree_delta", "perturb_output_sens_delta",
    "repr_jump_mean_delta", "repr_norm_drift_delta", "model_disagree_delta",
    "outside_support_drift",
}
_TSFM_NORMALISED = {
    "delta_utility_rel", "probe_delta_mean_rel", "probe_delta_std_rel",
    "probe_delta_max_rel",
}
PICS_TSFM_FEATURES = tuple(sorted((_TSFM_RAW - _DROPPED_SCALE_FEATURES)
                                  | _TSFM_NORMALISED))
PICS_STAT_FEATURES = tuple(
    f for f in ALL_FEATURES
    if f not in _TSFM_RAW and f not in _TSFM_NORMALISED)
PICS_JOINT_FEATURES = tuple(
    f for f in ALL_FEATURES if f not in _DROPPED_SCALE_FEATURES)


class _EnsembleHead:
    """Leave-one-source-out HGB ensemble for one target.

    With a single training source the ensemble degenerates to one member and
    the pessimistic score is that member's score.
    """

    def __init__(self, cfg: ShieldConfig, feature_names, kind: str):
        assert kind in ("bs", "harm")
        self.cfg = cfg
        self.feature_names = tuple(feature_names)
        self.kind = kind
        self.members: List[ContextualShield] = []

    def fit(self, feats: List[CandidateFeatures], y: np.ndarray,
            sources: np.ndarray):
        uniq = sorted(set(sources.tolist()))
        if len(uniq) > 1:
            folds = [np.array([i for i, s in enumerate(sources) if s != u])
                     for u in uniq]
        else:
            folds = [np.arange(len(feats))]
        for idx in folds:
            sh = ContextualShield(self.cfg)
            sh.feature_names = self.feature_names
            X = sh.encode([feats[i] for i in idx], fit=True)
            sh.train(X, y[idx])
            self.members.append(sh)
        return self

    def member_scores(self, feats: List[CandidateFeatures]) -> np.ndarray:
        return np.array([m.predict_score(m.encode(feats))
                         for m in self.members])

    def pessimistic(self, feats: List[CandidateFeatures]) -> np.ndarray:
        S = self.member_scores(feats)
        return S.min(axis=0) if self.kind == "bs" else S.max(axis=0)

    def spread(self, feats: List[CandidateFeatures]) -> np.ndarray:
        S = self.member_scores(feats)
        return S.max(axis=0) - S.min(axis=0)


def _feats_of(row, feature_names) -> CandidateFeatures:
    feats = row["features"]
    return CandidateFeatures(
        values=np.array([feats.get(n, 0.0) for n in feature_names],
                        dtype=object),
        feature_names=tuple(feature_names),
    )


class PICS:
    """Per-family dual-head shield with pessimistic cross-source bounds."""

    def __init__(self, cfg: ShieldConfig = None,
                 feature_names=PICS_JOINT_FEATURES):
        self.cfg = cfg or ShieldConfig()
        self.feature_names = tuple(feature_names)
        self.heads: Dict[str, Tuple[_EnsembleHead, _EnsembleHead]] = {}
        self.global_heads: Optional[Tuple[_EnsembleHead, _EnsembleHead]] = None
        self.thresholds: Dict[str, Tuple[float, float]] = {}
        self.spread_cap: float = np.inf
        self.calibration_report: dict = {}

    # -- training -------------------------------------------------------------

    def fit(self, train_rows: List[dict], cal_rows: List[dict]):
        """Train heads on train_rows, then calibrate on cal_rows by replay."""
        fam_train: Dict[str, List[int]] = {}
        for i, r in enumerate(train_rows):
            fam_train.setdefault(r["family"], []).append(i)

        def build(rows_idx, target):
            feats = [_feats_of(train_rows[i], self.feature_names) for i in rows_idx]
            y = np.array([train_rows[i][target] for i in rows_idx], dtype=int)
            src = np.array([train_rows[i]["dataset"] for i in rows_idx], dtype=str)
            kind = "bs" if target == "beneficial_and_safe" else "harm"
            head = _EnsembleHead(self.cfg, self.feature_names, kind)
            return head.fit(feats, y, src)

        eligible = [f for f in ELIGIBLE_FAMILIES
                    if len(fam_train.get(f, [])) >= self.cfg.min_family_n]
        for fam in eligible:
            idx = fam_train[fam]
            self.heads[fam] = (build(idx, "beneficial_and_safe"),
                               build(idx, "harmful"))
        all_idx = list(range(len(train_rows)))
        self.global_heads = (build(all_idx, "beneficial_and_safe"),
                             build(all_idx, "harmful"))
        self._eligible = set(eligible)

        # -- calibration fold scoring -----------------------------------------
        cal = []
        for r in cal_rows:
            bs_h, harm_h = self.heads.get(r["family"], self.global_heads)
            f = [_feats_of(r, self.feature_names)]
            cal.append({
                "sample_uid": r["sample_uid"],
                "family": r["family"],
                "score_bs": float(bs_h.pessimistic(f)[0]),
                "score_harm": float(harm_h.pessimistic(f)[0]),
                "spread": float(harm_h.spread(f)[0]),
                "true_loss": r["true_loss"],
                "beneficial": r["beneficial"],
            })
        spreads = np.array([c["spread"] for c in cal]) if cal else np.array([0.0])
        self.spread_cap = float(np.percentile(spreads, 95))

        # Episode replay groups candidates by window, preserving proposer order.
        by_uid: Dict[str, List[dict]] = {}
        for c in cal:
            by_uid.setdefault(c["sample_uid"], []).append(c)
        windows = list(by_uid.values())
        self.thresholds, self.calibration_report = select_episode_thresholds(
            windows, dual=True, alpha=self.cfg.alpha,
            family_order=[f for f in ELIGIBLE_FAMILIES], per_family=True)
        return self

    # -- deployment decision ----------------------------------------------------

    def decide(self, feats: CandidateFeatures, family: str) -> Verdict:
        if family not in ELIGIBLE_FAMILIES:
            return Verdict.ROLLED_BACK_RISK  # RESEGMENT closed this round
        thr = self.thresholds.get(family)
        if thr is None:
            return Verdict.ROLLED_BACK_RISK  # family found no admissible pair
        if family not in self._eligible and not self.cfg.global_fallback:
            return Verdict.ROLLED_BACK_RISK
        bs_h, harm_h = self.heads.get(family, self.global_heads)
        f = [feats]
        if float(harm_h.spread(f)[0]) > self.spread_cap:
            return Verdict.ROLLED_BACK_RISK  # low support / OOD: default KEEP
        t_bs, t_h = thr
        if float(bs_h.pessimistic(f)[0]) >= t_bs \
                and float(harm_h.pessimistic(f)[0]) <= t_h:
            return Verdict.ACCEPTED
        return Verdict.ROLLED_BACK_RISK
