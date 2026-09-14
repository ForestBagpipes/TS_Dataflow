"""Action-Conditioned Conformal Governance Shield (v3-pre).

The shield replaces the fixed utility/structure/risk conjunction with a learned
model that predicts whether a candidate is both beneficial and safe, then
calibrates a per-family acceptance threshold under a bounded-damage guarantee.

The model is trained on candidates whose true labels are known from the clean
reference. At execution time the same features are computed without access to
the truth, so the shield stays deployment-realistic.

Feature and label contract
--------------------------
Whitelist (features):
    state hypothesis/confidence, dominant/secondary defect evidence, evidence
    ratio, route source, action family/params/rung/cost, applicable,
    touched fraction, output length ratio, discard share, structure aggregate
    and parts, probe vector before/after and delta, delta utility, forecast /
    reconstruction / sensitivity / representation dynamics delta, cross-model
    disagreement, seam error, outside-support drift, Phase C counterfactual
    signals.

Blacklist (labels only, never features):
    true_kind, stratum, clean series/hash, true before/after NMSE, true repair
    gain, v2 verdict.

Training target: beneficial_and_safe.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .actions import Action
from .risk import RiskState
from .types import ProbeResult, Verdict

#: Categorical features encoded as integers for HistGradientBoostingClassifier.
CATEGORICAL_FEATURES = (
    "hypothesis", "dominant_defect", "secondary_defect", "route_source",
    "action_family", "rung",
)

#: Numerical features in fixed order.
NUMERICAL_FEATURES = (
    "confidence", "defect_strength", "behav_risk", "ood",
    "dominant_units", "secondary_units", "evidence_ratio",
    "cost", "touched_fraction", "output_length_ratio", "discard_share",
    "struct_distortion", "struct_trend", "struct_period", "struct_spectrum",
    "struct_acf", "struct_changepoint", "struct_extremes", "struct_shape",
    "struct_patch", "struct_footprint", "struct_spread",
    "delta_utility", "utility_before", "utility_after",
    "improvement_consistency", "improvement_depth", "action_risk",
    "probe_delta_mean", "probe_delta_std", "probe_delta_max",
    "forecast_nrmse_delta", "recon_nrmse_med_delta", "recon_nrmse_iqr_delta",
    "multiview_disagree_delta", "perturb_output_sens_delta",
    "repr_jump_mean_delta", "repr_norm_drift_delta", "model_disagree_delta",
    "seam_error", "outside_support_drift",
    # v3.2: within-window normalised counterparts, the source-invariant set.
    "delta_utility_rel", "probe_delta_mean_rel", "probe_delta_std_rel",
    "probe_delta_max_rel",
)

ALL_FEATURES = CATEGORICAL_FEATURES + NUMERICAL_FEATURES

#: The feature list as v3.1-pre used it, kept so the bugfix-only arm isolates
#: the effect of the repairs from the effect of the new normalised features.
V31_FEATURES = tuple(f for f in ALL_FEATURES if not f.endswith("_rel"))


def _touched_mask(touched, T: int):
    """Unify the operator's touched declaration to a boolean mask or None.

    Operators declare ``touched`` either as a full-length boolean mask or as an
    index array. ``None`` (and a mask whose length no longer matches the input,
    as with a cropping operator) means the window as a whole is the declared
    support.
    """
    if touched is None:
        return None
    t = np.asarray(touched)
    if t.dtype == bool:
        return t if len(t) == T else None
    mask = np.zeros(T, dtype=bool)
    idx = t.astype(int).ravel()
    idx = idx[(idx >= 0) & (idx < T)]
    mask[idx] = True
    return mask


def _mask_runs(mask: np.ndarray):
    """Contiguous True runs as (lo, hi) half-open pairs."""
    runs, i, T = [], 0, len(mask)
    while i < T:
        if mask[i]:
            j = i
            while j < T and mask[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


@dataclass
class CandidateFeatures:
    """Feature vector for one candidate intervention."""
    values: np.ndarray
    feature_names: Tuple[str, ...] = field(default=ALL_FEATURES)


@dataclass
class ShieldConfig:
    """Fixed hyperparameters, as pre-registered."""
    max_depth: int = 3
    max_iter: int = 100
    learning_rate: float = 0.05
    l2_regularization: float = 1.0
    random_state: int = 20260901
    alpha: float = 0.03  # bounded damage risk target
    min_family_n: int = 30
    # Fallback when a family has too few calibration samples.
    global_fallback: bool = True
    # Fallback when the model cannot be trained or is unavailable.
    keep_fallback: bool = True


#: Fixed threshold grids and family order for episode-replay calibration.
#: RESEGMENT is absent: it has zero oracle safe headroom and is diagnosis-only
#: in the v3.2 line.
EPISODE_FAMILY_ORDER = ("DENOISE", "DESPIKE", "IMPUTE")
EPISODE_GRID = tuple(float(x) for x in np.round(np.arange(0.05, 1.0, 0.05), 2))


def episode_replay(windows, thresholds):
    """Replay first-commit episodes on calibration windows.

    ``windows`` is a list of candidate lists in proposer order; each candidate
    is a mapping with ``family``, ``score_bs``, ``score_harm`` (unused when the
    threshold's harm cap is None), ``true_loss`` and ``beneficial``. A family
    missing from ``thresholds`` never commits. Returns corpus-level metrics;
    the loss of a KEEP window is zero, matching the deployment rule.
    """
    losses, committed, cont, cont_ben = [], 0, 0, 0
    for cands in windows:
        pick = None
        for c in cands:
            thr = thresholds.get(c["family"])
            if thr is None:
                continue
            t_bs, t_h = thr
            if c["score_bs"] >= t_bs and (t_h is None or c["score_harm"] <= t_h):
                pick = c
                break
        losses.append(pick["true_loss"] if pick is not None else 0.0)
        if pick is not None:
            committed += 1
    n = max(len(windows), 1)
    damage = float(np.mean(losses)) if losses else 0.0
    corrected = (len(windows) * damage + 1.0) / (len(windows) + 1) if windows else 1.0
    return {"damage": damage, "corrected_risk": corrected,
            "committed": committed, "n_windows": len(windows)}


def select_episode_thresholds(windows, dual=True, alpha=0.03,
                              family_order=EPISODE_FAMILY_ORDER, per_family=True):
    """Choose acceptance thresholds by episode replay on the calibration fold.

    Per-family mode walks ``family_order`` once, greedily: when family F is
    being calibrated, already-calibrated families apply their thresholds and
    later families stay closed. At each grid pair the whole calibration fold is
    replayed, so the corpus damage risk that is bounded is exactly the quantity
    the deployed first-commit rule produces. Among grid pairs whose corrected
    risk clears alpha, the one with the most committed candidates wins; ties
    break toward the lower harm cap, then the higher benefit threshold (the
    more conservative corner). A family with no admissible pair stays closed. ``dual=False`` sweeps only the
    benefit threshold with no harm gate.
    """
    def admissible(thr):
        m = episode_replay(windows, thr)
        return m if m["corrected_risk"] <= alpha else None

    if not per_family:
        best, best_m = None, None
        for t_bs in EPISODE_GRID:
            caps = EPISODE_GRID if dual else (None,)
            for t_h in caps:
                thr = {f: (t_bs, t_h) for f in family_order}
                m = admissible(thr)
                if m is None:
                    continue
                key = (m["committed"], -(t_h if t_h is not None else 0.0), t_bs)
                if best is None or key > best[0]:
                    best, best_m = (key, (t_bs, t_h)), m
        if best is None:
            return {}, {"damage": 0.0, "corrected_risk": 0.0, "committed": 0,
                        "n_windows": len(windows)}
        return {f: best[1] for f in family_order}, best_m

    thresholds = {}
    final_m = {"damage": 0.0, "corrected_risk": 0.0, "committed": 0,
               "n_windows": len(windows)}
    for fam in family_order:
        best, best_m = None, None
        for t_bs in EPISODE_GRID:
            caps = EPISODE_GRID if dual else (None,)
            for t_h in caps:
                thr = dict(thresholds)
                thr[fam] = (t_bs, t_h)
                m = admissible(thr)
                if m is None:
                    continue
                key = (m["committed"], -(t_h if t_h is not None else 0.0), t_bs)
                if best is None or key > best[0]:
                    best, best_m = (key, (t_bs, t_h)), m
        if best is not None:
            thresholds[fam] = best[1]
            final_m = best_m
    return thresholds, final_m


class ContextualShield:
    """Learned shield that scores candidates for being beneficial and safe."""

    feature_names = ALL_FEATURES

    def __init__(self, cfg: ShieldConfig = None):
        self.cfg = cfg or ShieldConfig()
        self.model = None
        self.category_maps: Dict[str, Dict[str, int]] = {}
        self.thresholds: Dict[str, float] = {}
        self.global_threshold: float = 0.0
        self.trained = False

    # -- feature extraction ---------------------------------------------------

    def extract(self, window, state: RiskState, action: Action, params: dict,
                outcome, before: ProbeResult, after: ProbeResult,
                struct_report, cost: float, rung: str,
                route_source: str, *, improvement_consistency: float,
                improvement_depth: float, action_risk: float) -> CandidateFeatures:
        """Build the feature vector for one candidate.

        The three verification quantities are required keyword arguments: when
        they silently defaulted to zero in v3-pre the model saw three constant
        features and nobody noticed until the post-run review.
        """
        from .actions import robust_scale

        original = np.asarray(window.series, dtype=np.float64)
        y = np.asarray(outcome.series, dtype=np.float64)
        T = len(original)
        mask = _touched_mask(outcome.touched, T)
        # Whole-window declarations (mask is None) declare fraction 1.0.
        touched_fraction = float(mask.sum() / T) if (mask is not None and T) else (
            1.0 if T else 0.0)
        output_length_ratio = float(len(y) / T) if T else 1.0
        discard_share = 1.0 - output_length_ratio

        units = state.defect_units or {}
        dominant = state.dominant_defect or "none"
        dom_units = float(units.get(dominant, 0.0))
        # Secondary defect: the next-highest evidence above the threshold.
        other_units = {k: v for k, v in units.items() if k != dominant}
        if other_units:
            secondary = max(other_units, key=other_units.get)
            sec_units = float(other_units[secondary])
        else:
            secondary = "none"
            sec_units = 0.0
        evidence_ratio = sec_units / max(dom_units, 1e-12)

        struct_parts = struct_report.parts or {}
        probe_delta = after.vector - before.vector
        parts_delta = {k: after.parts.get(k, 0.0) - before.parts.get(k, 0.0)
                       for k in before.parts}

        scale = robust_scale(original)

        # Seam error: the largest discontinuity at a boundary of the edited
        # region, normalised by the window's robust scale. Only real touched
        # indices count; a whole-window operator has no seam by construction.
        seam_error = 0.0
        if mask is not None and mask.any() and len(y) == T:
            jumps = []
            for lo, hi in _mask_runs(mask):
                if lo > 0:
                    pair = (y[lo], y[lo - 1])
                    if np.isfinite(pair).all():
                        jumps.append(abs(pair[0] - pair[1]))
                if hi < T:
                    pair = (y[hi - 1], y[hi])
                    if np.isfinite(pair).all():
                        jumps.append(abs(pair[0] - pair[1]))
            if jumps:
                seam_error = float(max(jumps) / scale)

        # Outside-support drift: the real change on points the operator did NOT
        # declare, normalised by robust scale. This is the leak detector for an
        # operator that edits beyond its claim; a whole-window operator has no
        # outside support and scores 0 by definition.
        outside_support_drift = 0.0
        if mask is not None and len(y) == T and (~mask).any():
            d = np.abs(y[~mask] - original[~mask])
            d = d[np.isfinite(d)]
            if d.size:
                outside_support_drift = float(np.mean(d) / scale)

        eps = 1e-12
        probe_scale = float(np.std(before.vector)) if before.vector.size else 0.0
        cat = {
            "hypothesis": str(state.hypothesis),
            "dominant_defect": str(dominant),
            "secondary_defect": str(secondary),
            "route_source": str(route_source),
            "action_family": str(action.value),
            "rung": str(rung),
        }
        num = {
            "confidence": float(state.confidence),
            "defect_strength": float(state.defect_strength),
            "behav_risk": float(state.behav_risk),
            "ood": float(state.ood),
            "dominant_units": dom_units,
            "secondary_units": sec_units,
            "evidence_ratio": float(evidence_ratio),
            "cost": float(cost),
            "touched_fraction": float(touched_fraction),
            "output_length_ratio": float(output_length_ratio),
            "discard_share": float(discard_share),
            "struct_distortion": float(struct_report.distortion),
            "struct_trend": float(struct_parts.get("trend", 0.0)),
            "struct_period": float(struct_parts.get("period", 0.0)),
            "struct_spectrum": float(struct_parts.get("spectrum", 0.0)),
            "struct_acf": float(struct_parts.get("acf", 0.0)),
            "struct_changepoint": float(struct_parts.get("changepoint", 0.0)),
            "struct_extremes": float(struct_parts.get("extremes", 0.0)),
            "struct_shape": float(struct_parts.get("shape", 0.0)),
            "struct_patch": float(struct_parts.get("patch", 0.0)),
            "struct_footprint": float(struct_parts.get("footprint", 0.0)),
            "struct_spread": float(struct_parts.get("spread", 0.0)),
            "delta_utility": float(after.utility - before.utility),
            "utility_before": float(before.utility),
            "utility_after": float(after.utility),
            "improvement_consistency": float(improvement_consistency),
            "improvement_depth": float(improvement_depth),
            "action_risk": float(action_risk),
            "probe_delta_mean": float(np.mean(probe_delta)),
            "probe_delta_std": float(np.std(probe_delta)),
            "probe_delta_max": float(np.max(np.abs(probe_delta))),
            "forecast_nrmse_delta": float(parts_delta.get("forecast_nrmse", 0.0)),
            "recon_nrmse_med_delta": float(parts_delta.get("recon_nrmse_med", 0.0)),
            "recon_nrmse_iqr_delta": float(parts_delta.get("recon_nrmse_iqr", 0.0)),
            "multiview_disagree_delta": float(parts_delta.get("multiview_disagree", 0.0)),
            "perturb_output_sens_delta": float(parts_delta.get("perturb_output_sens", 0.0)),
            "repr_jump_mean_delta": float(parts_delta.get("repr_jump_mean", 0.0)),
            "repr_norm_drift_delta": float(parts_delta.get("repr_norm_drift", 0.0)),
            "model_disagree_delta": float(parts_delta.get("model_disagree", 0.0)),
            "seam_error": seam_error,
            "outside_support_drift": outside_support_drift,
            # Within-window normalised counterparts; source-invariant.
            "delta_utility_rel": float((after.utility - before.utility)
                                       / max(abs(before.utility), eps)),
            "probe_delta_mean_rel": float(np.mean(probe_delta) / max(probe_scale, eps)),
            "probe_delta_std_rel": float(np.std(probe_delta) / max(probe_scale, eps)),
            "probe_delta_max_rel": float(np.max(np.abs(probe_delta)) / max(probe_scale, eps)),
        }
        return CandidateFeatures(
            values=np.array([cat.get(f, "UNK") for f in CATEGORICAL_FEATURES]
                           + [num.get(f, 0.0) for f in NUMERICAL_FEATURES],
                           dtype=object),
        )

    def encode(self, feats: List[CandidateFeatures], fit: bool = False):
        """Encode categorical features and return the design matrix.

        Column order follows ``self.feature_names`` so feature subsets (the
        statistical-only and TSFM-only arms) share this code path.
        """
        names = list(self.feature_names)
        if fit:
            self.category_maps = {}
        X = np.zeros((len(feats), len(names)), dtype=np.float64)
        for j, name in enumerate(names):
            vals = [f.values[j] for f in feats]
            if name in CATEGORICAL_FEATURES:
                if fit:
                    uniques = sorted(set(vals))
                    # Reserve 0 for unknown categories seen only at deployment.
                    self.category_maps[name] = {"UNK": 0} | {
                        v: i + 1 for i, v in enumerate(uniques)}
                m = self.category_maps.get(name, {"UNK": 0})
                for i, v in enumerate(vals):
                    X[i, j] = float(m.get(v, 0))
            else:
                for i, v in enumerate(vals):
                    X[i, j] = float(v)
        return X

    # -- training -------------------------------------------------------------

    def train(self, X: np.ndarray, y: np.ndarray):
        """Train the fixed HistGradientBoostingClassifier."""
        from sklearn.ensemble import HistGradientBoostingClassifier

        categorical_mask = np.array(
            [n in CATEGORICAL_FEATURES for n in self.feature_names], dtype=bool)
        self.model = HistGradientBoostingClassifier(
            max_depth=self.cfg.max_depth,
            max_iter=self.cfg.max_iter,
            learning_rate=self.cfg.learning_rate,
            l2_regularization=self.cfg.l2_regularization,
            random_state=self.cfg.random_state,
            categorical_features=categorical_mask,
        )
        self.model.fit(X, y)
        self.trained = True

    # -- calibration -----------------------------------------------------------

    @staticmethod
    def _largest_safe_prefix(s_sorted: np.ndarray, d_sorted: np.ndarray,
                             alpha: float) -> int:
        """Largest score-prefix whose corrected corpus risk clears alpha.

        Reuses the project's conformal corrected risk from
        ``conformal.calibrate``: ``(n * R + B) / (n + 1) <= alpha`` with B=1.
        R is the corpus-level risk of the accept rule, i.e. rejected candidates
        contribute zero loss (KEEP is safe), so R = sum(d[:k]) / n, not the
        mean over the accepted prefix.
        """
        n = len(s_sorted)
        cum = np.cumsum(d_sorted)
        best_prefix = 0
        for k in range(1, n + 1):
            risk = float(cum[k - 1]) / n
            corrected = (n * risk + 1.0) / (n + 1)
            if corrected <= alpha:
                best_prefix = k
            else:
                break
        return best_prefix

    def calibrate(self, scores: np.ndarray, damages: np.ndarray,
                  families: np.ndarray):
        """Per-family threshold at bounded damage risk.

        For each family, sort candidates by descending score and find the
        largest prefix whose corrected damage risk clears the target alpha.
        """
        self.thresholds = {}
        for fam in np.unique(families):
            mask = families == fam
            s, d = scores[mask], damages[mask]
            if len(s) < self.cfg.min_family_n and self.cfg.global_fallback:
                continue  # use global threshold
            order = np.argsort(-s)
            best_prefix = self._largest_safe_prefix(
                s[order], d[order], self.cfg.alpha)
            if best_prefix > 0:
                self.thresholds[str(fam)] = float(s[order][best_prefix - 1])
            else:
                self.thresholds[str(fam)] = np.inf  # accept nothing
        # Global fallback.
        if self.cfg.global_fallback:
            order = np.argsort(-scores)
            best_prefix = self._largest_safe_prefix(
                scores[order], damages[order], self.cfg.alpha)
            if best_prefix > 0:
                self.global_threshold = float(scores[order][best_prefix - 1])
            else:
                self.global_threshold = np.inf

    def predict_score(self, X: np.ndarray) -> np.ndarray:
        """Probability of beneficial_and_safe."""
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict_proba(X)[:, 1]

    def decide(self, feats: CandidateFeatures, family: str) -> Verdict:
        """Accept or reject one candidate."""
        X = self.encode([feats])
        score = float(self.predict_score(X)[0])
        thr = self.thresholds.get(str(family), self.global_threshold)
        if score >= thr:
            return Verdict.ACCEPTED
        return Verdict.ROLLED_BACK_RISK

    # -- v3.1-pre dual gate ----------------------------------------------------
    #
    # Pre-registered failure branch: the single-score shield's dominant failure
    # is protected false accepts, i.e. harmful candidates the beneficial-and-
    # safe gate failed to block. v3.1-pre adds a second model of the same fixed
    # class predicting `harmful`, and accepts only when P(beneficial_and_safe)
    # clears the family threshold AND P(harmful) stays under a cap. Both cutoffs
    # are chosen on the calibration fold alone: for each harm cap on a fixed
    # grid, the largest prefix of the beneficial-and-safe score whose corrected
    # corpus risk clears alpha; the cap admitting the largest prefix wins, ties
    # break toward the lower cap. No test data participates.

    #: Fixed harm-cap grid, pre-registered, not tuned on any result.
    HARM_GRID = tuple(float(x) for x in np.round(np.arange(0.05, 1.0, 0.05), 2))

    def train_harm(self, X: np.ndarray, y_harm: np.ndarray):
        """Train the harmful model, same fixed class and hyperparameters."""
        from sklearn.ensemble import HistGradientBoostingClassifier

        categorical_mask = np.array(
            [n in CATEGORICAL_FEATURES for n in self.feature_names], dtype=bool)
        self.harm_model = HistGradientBoostingClassifier(
            max_depth=self.cfg.max_depth,
            max_iter=self.cfg.max_iter,
            learning_rate=self.cfg.learning_rate,
            l2_regularization=self.cfg.l2_regularization,
            random_state=self.cfg.random_state,
            categorical_features=categorical_mask,
        )
        self.harm_model.fit(X, y_harm)

    def predict_harm(self, X: np.ndarray) -> np.ndarray:
        """Probability of harmful (true_loss > 0.03)."""
        if getattr(self, "harm_model", None) is None:
            return np.ones(len(X))
        return self.harm_model.predict_proba(X)[:, 1]

    def _dual_select(self, s, h, d):
        """Best (threshold_bs, harm_cap) for one calibration slice.

        Returns (thr_bs, thr_h, prefix_len). (inf, inf, 0) admits nothing.
        Corpus denominator is the full slice: candidates the harm gate excludes
        are KEEPs and contribute zero loss.
        """
        n = len(s)
        best = (np.inf, np.inf, 0)
        for t_h in self.HARM_GRID:
            keep = h <= t_h
            if not keep.any():
                continue
            order = np.argsort(-s[keep])
            k = self._largest_safe_prefix(s[keep][order], d[keep][order],
                                          self.cfg.alpha)
            if k > best[2] or (k == best[2] and k > 0 and t_h < best[1]):
                best = (float(s[keep][order][k - 1]), float(t_h), k)
        return best

    def calibrate_dual(self, scores_bs, scores_harm, damages, families):
        """Per-family dual thresholds; global fallback under min_family_n."""
        self.dual_thresholds = {}
        for fam in np.unique(families):
            mask = families == fam
            if mask.sum() < self.cfg.min_family_n and self.cfg.global_fallback:
                continue
            thr_bs, thr_h, _ = self._dual_select(
                scores_bs[mask], scores_harm[mask], damages[mask])
            self.dual_thresholds[str(fam)] = (thr_bs, thr_h)
        if self.cfg.global_fallback:
            self.dual_global = self._dual_select(scores_bs, scores_harm, damages)[:2]

    def decide_dual(self, feats: CandidateFeatures, family: str) -> Verdict:
        """Accept only when both gates pass."""
        X = self.encode([feats])
        s = float(self.predict_score(X)[0])
        h = float(self.predict_harm(X)[0])
        thr_bs, thr_h = self.dual_thresholds.get(
            str(family), getattr(self, "dual_global", (np.inf, np.inf)))
        if s >= thr_bs and h <= thr_h:
            return Verdict.ACCEPTED
        return Verdict.ROLLED_BACK_RISK

    # -- persistence ----------------------------------------------------------
    def save(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path):
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
