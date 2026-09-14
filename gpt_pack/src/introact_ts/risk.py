"""Data risk state: what kind of window is this, and how sure are we?

This is where IntroAct-TS separates the cases that a quality score conflates.
A high forecast error can mean the data is corrupted, or that it is simply
hard, or that it contains a rare-but-real event, or that it is clean data from
an unfamiliar distribution. Those four situations call for opposite responses,
so the agent forms an explicit hypothesis over them from two independent
evidence streams:

  * statistical evidence -- defects visible in the data itself (missingness,
    isolated spikes, high-frequency noise, level shifts);
  * behavioural evidence -- peer-calibrated deviation in how the frozen TSFM
    reacts (forecast error, reconstruction stability, representation dynamics,
    cross-model disagreement).

Corruption is the *conjunction* of the two. Behavioural difficulty without any
statistical defect is evidence for hard / rare-valid / out-of-distribution
data, all of which must be protected rather than repaired. Contradictory
evidence yields low confidence, which the policy turns into ABSTAIN.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import medfilt, savgol_filter

from .actions import (
    changepoints,
    robust_scale,
    dominant_period,
    hampel_outliers,
    isolated_spikes,
    missing_mask,
)

#: Repair switch, see experiments/fix_compare.py. True uses the scale free
#: degenerate test, False restores the unreachable absolute floor of 1e-3.
OOD_SCALE_FREE = True

HYPOTHESES = ("contaminated", "clean", "hard", "rare_valid", "clean_ood")

#: Defect indicators, and the floor below which a deviation is never treated as
#: evidence no matter how unusual it is for this corpus. The floors encode what
#: is physically negligible (a single flagged point in 512, high-frequency
#: energy well under a tenth of the window's spread); the corpus-adaptive part
#: on top of them is computed by :func:`corpus_reference`.
DEFECT_KEYS = ("missing", "spike", "noise", "shift")

#: These are sensitivity limits, and worth reading as such. On a 512-point
#: window they correspond to roughly 4 missing points, 4 isolated spikes,
#: high-frequency energy at a fifth of the window's spread, and a permanent
#: displacement of 0.42 spreads. Contamination below a floor is not detected --
#: the ``spike`` floor in particular was raised to this level because real ETT
#: windows with weak structure otherwise register a steady drizzle of false
#: spikes, and trading that sensitivity away was the better bargain.
DEFECT_FLOORS = {
    "missing": 0.008,
    "spike": 0.006,
    "noise": 0.20,
    "shift": 0.42,
}

#: How far corpus adaptation may raise each floor. Level shifts get no
#: adaptation at all: their indicator is bimodal by nature (a window either has
#: a displaced segment or it does not), so a MAD estimated across the mixture
#: tracks the contamination rate rather than the corpus, and raising the bar
#: with it would hide exactly the windows it was meant to find.
DEFECT_RELAX = {"missing": 2.0, "spike": 2.0, "noise": 2.0, "shift": 1.0}

#: Departure-and-recovery magnitude, relative to the window's spread, at which
#: an excursion counts as a real transient event rather than noise.
TRANSIENT_REFERENCE = 1.2

EVIDENCE_KEY = {
    "missing": "missing_frac",
    "spike": "spike_frac",
    "noise": "noise_ratio",
    "shift": "shift_strength",
}


@dataclass
class CorpusReference:
    """Corpus-level scales that turn raw indicators into units of evidence.

    Fixed thresholds do not survive contact with heterogeneous corpora: what
    counts as unusual noise in a smooth electricity series is unremarkable in a
    volatile exchange-rate one. Every scale here is estimated robustly
    (median + MAD), so it stays valid even when a large share of the corpus is
    contaminated, and is floored by :data:`DEFECT_FLOORS` so a uniformly clean
    corpus does not manufacture defects out of its own tiny variations.
    """

    defect_refs: dict = field(default_factory=lambda: dict(DEFECT_FLOORS))
    risk_center: float = 0.0
    risk_scale: float = 1.0
    ood_ref: float = 0.0
    ood_scale: float = 0.0

    def units(self, evidence: dict) -> dict:
        """Each defect indicator expressed in units of its reference level."""
        return {
            k: evidence.get(EVIDENCE_KEY[k], 0.0) / max(self.defect_refs[k], 1e-9)
            for k in DEFECT_KEYS
        }


def _robust_scale(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    mad = float(np.median(np.abs(x - np.median(x))))
    return 1.4826 * mad


def corpus_reference(
    evidences: list,
    risks: np.ndarray,
    oods: np.ndarray,
    n_mad: float = 2.0,
    max_relax: float = 2.0,
) -> CorpusReference:
    """Estimate the corpus-adaptive evidence scales.

    Adaptation may only *raise* a threshold, and by at most ``max_relax``x: a
    corpus that is genuinely volatile should not have every window flagged, but
    a corpus with a sizeable contaminated share must not talk itself into
    treating its own contamination as the norm.
    """
    refs = {}
    for key in DEFECT_KEYS:
        vals = np.asarray(
            [e.get(EVIDENCE_KEY[key], 0.0) for e in evidences], dtype=np.float64
        )
        adaptive = float(np.median(vals) + n_mad * _robust_scale(vals))
        floor = DEFECT_FLOORS[key]
        relax = DEFECT_RELAX.get(key, max_relax)
        refs[key] = float(np.clip(adaptive, floor, floor * relax))

    risks = np.asarray(risks, dtype=np.float64)
    risk_scale = max(_robust_scale(risks), 1e-3)
    oods = np.asarray(oods, dtype=np.float64)
    ood_spread = float(np.percentile(oods, 75) - np.percentile(oods, 25))
    ood_ref = float(np.percentile(oods, 85))

    return CorpusReference(
        defect_refs=refs,
        # The centre sits above the typical window, not at it: with the median
        # as the pivot half the corpus would read as behaviourally elevated by
        # construction, and ordinary clean windows would be filed as "hard".
        risk_center=float(np.median(risks)) + 1.5 * risk_scale,
        risk_scale=risk_scale,
        ood_ref=ood_ref,
        # A degenerate OOD distribution (every window equally typical) must
        # yield zero OOD evidence, not the 0.5 a zero-scale sigmoid would give.
        #
        # The test for degenerate has to be scale free. It used to be an
        # absolute floor, ood_ref > 1e-3, and that floor is unreachable: these
        # are mean cosine distances between L2 normalised profiles and on a
        # real ETT corpus the 85th percentile lands at 1.5e-04, six times below
        # the floor, so the OOD hypothesis was admitted zero times in 210
        # clean_ood windows. The scores were not the problem. Within the same
        # corpus the clean_ood stratum reaches 1.35e-03 at its own 85th
        # percentile against 7.3e-05 for clean windows, an 18 fold separation
        # that the floor discarded wholesale.
        #
        # Degenerate now means what it says: the spread is negligible relative
        # to the typical score, so no window is distinguishable from any other.
        ood_scale=(
            (ood_spread
             if (ood_spread > 1e-12
                 and ood_spread >= 0.05 * max(float(np.median(oods)), 1e-12))
             else 0.0)
            if OOD_SCALE_FREE else
            (ood_spread if (ood_spread > 1e-9 and ood_ref > 1e-3) else 0.0)
        ),
    )


@dataclass
class RiskState:
    """Everything the policy is allowed to condition on."""

    window_id: int
    profile: np.ndarray = field(repr=False, default=None)
    behavior: np.ndarray = field(repr=False, default=None)
    z: np.ndarray = field(repr=False, default=None)
    utility: float = 0.0
    behav_risk: float = 0.0
    ood: float = 0.0
    evidence: dict = field(default_factory=dict)
    posterior: dict = field(default_factory=dict)
    hypothesis: str = "clean"
    confidence: float = 0.0
    reference: CorpusReference = field(default_factory=CorpusReference, repr=False)

    @property
    def defect_units(self) -> dict:
        return self.reference.units(self.evidence)

    @property
    def dominant_defect(self) -> str:
        """Which statistical defect dominates, or "none"."""
        units = self.defect_units
        above = [k for k in DEFECT_KEYS if units[k] >= 1.0]
        if not above:
            return "none"
        return max(above, key=lambda k: units[k])

    @property
    def defect_strength(self) -> float:
        units = self.defect_units
        return max(units.values()) if units else 0.0


def _sigmoid(x: float, scale: float = 1.0) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(x / scale, -50.0, 50.0))))


def _shift_purity(series: np.ndarray, b: int, context: int = 160) -> float:
    """How much a break at ``b`` looks like a pure level translation, in [0, 1].

    Compares the two sides on everything *except* their level: short-range
    memory, variability, and spectral shape. A displaced copy of the same
    process scores near 1; a genuine change of regime -- different period,
    different amplitude -- scores low.

    The autocorrelation term carries most of the weight because it is the most
    stable of the three on the few-hundred-point windows available here; a
    periodogram from a 160-point segment is too coarse to be trusted alone.
    """
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    w = min(context, b, T - b)
    if w < 32:
        return 1.0
    left, right = x[b - w : b], x[b : b + w]

    def acf(seg, n_lags=16):
        c = seg - seg.mean()
        denom = float(np.dot(c, c)) + 1e-12
        return np.asarray(
            [np.dot(c[:-k], c[k:]) / denom for k in range(1, n_lags + 1)]
        )

    acf_sim = 1.0 - float(np.mean(np.abs(acf(left) - acf(right))) / 2.0)

    def spec(seg, n_bins=24):
        p = np.abs(np.fft.rfft(seg - seg.mean())) ** 2
        p = p[1:]
        if len(p) < n_bins:
            return np.ones(n_bins) / n_bins
        binned = np.asarray([b.sum() for b in np.array_split(p, n_bins)])
        total = binned.sum()
        return binned / total if total > 1e-12 else np.ones(n_bins) / n_bins

    spectral_sim = 1.0 - float(0.5 * np.abs(spec(left) - spec(right)).sum())

    vl, vr = float(np.std(left)), float(np.std(right))
    ratio = (vl + 1e-9) / (vr + 1e-9)
    var_sim = 1.0 - _sigmoid(abs(np.log(ratio)) - 0.3, 0.2)

    purity = 0.45 * acf_sim + 0.3 * var_sim + 0.25 * spectral_sim
    return float(np.clip(purity, 0.0, 1.0))


def statistical_evidence(series: np.ndarray) -> dict:
    """Defect indicators read straight off the series, with no model involved."""
    x = np.asarray(series, dtype=np.float64)
    T = len(x)
    ev = {}

    miss = missing_mask(x)
    ev["missing_frac"] = float(miss.mean())

    finite = x[np.isfinite(x)]
    if len(finite) < 16:
        ev.update(
            spike_frac=0.0, wide_outlier_frac=0.0, noise_ratio=0.0,
            shift_strength=0.0, transient_strength=0.0, n_changepoints=0,
            extreme_frac=0.0,
        )
        return ev

    filled = x.copy()
    if not np.isfinite(x).all():
        idx = np.arange(T)
        good = np.isfinite(x)
        filled[~good] = np.interp(idx[~good], idx[good], x[good])

    spikes = isolated_spikes(filled)
    all_out = hampel_outliers(filled)
    ev["spike_frac"] = float(spikes.mean())
    ev["wide_outlier_frac"] = float(max(0.0, all_out.mean() - spikes.mean()))

    # Broadband high-frequency energy relative to the window's robust spread.
    # Measured with a MAD rather than a standard deviation on purpose: a
    # handful of spikes would inflate an SD and make every spiked window look
    # like a noisy one, which then routes it to the wrong operator.
    win = min(11, T - 1 if (T - 1) % 2 else T - 2)
    if win >= 5:
        if win % 2 == 0:
            win += 1
        hf = filled - savgol_filter(filled, window_length=win, polyorder=2)
        spread = robust_scale(filled)
        hf_mad = 1.4826 * float(np.median(np.abs(hf - np.median(hf))))
        ev["noise_ratio"] = float(hf_mad / spread)
    else:
        ev["noise_ratio"] = 0.0

    cps = changepoints(filled)
    ev["n_changepoints"] = int(len(cps))
    spread = robust_scale(filled)

    # A permanent level shift and a transient excursion both produce
    # changepoints, but they are opposite cases: the first is a misalignment
    # worth resegmenting, the second is a real event worth protecting. They are
    # told apart by whether the series comes back.
    #
    # Step size is read off a median-filtered level curve rather than the raw
    # series. A median filter is edge-preserving, so a genuine step survives it
    # intact, while seasonality, noise and isolated spikes -- all of which would
    # otherwise masquerade as steps -- are removed.
    period = dominant_period(filled) or 24
    kernel = int(np.clip(period | 1, 5, max(5, (T // 4) | 1)))
    level = medfilt(filled, kernel_size=kernel)
    jump, purity = 0.0, 0.0
    for b in cps:
        w = min(kernel, b, T - b)
        if w < 4:
            continue
        size = abs(level[min(b + w, T - 1)] - level[b - w]) / spread
        if size > jump:
            jump = size
            purity = _shift_purity(filled, b)
    ev["jump_strength"] = float(jump)
    ev["shift_purity"] = float(purity)

    detr = filled - np.poly1d(np.polyfit(np.arange(T), filled, 1))(np.arange(T))
    transient = 0.0
    if len(cps) >= 2:
        edges = [0] + cps + [T]
        means = [np.mean(detr[edges[i] : edges[i + 1]]) for i in range(len(edges) - 1)]
        for i in range(1, len(means) - 1):
            depart = min(abs(means[i] - means[i - 1]), abs(means[i] - means[i + 1]))
            recover = abs(means[i - 1] - means[i + 1])
            if depart > recover:
                transient = max(transient, (depart - recover) / spread)
    ev["transient_strength"] = float(transient)

    # Net permanent displacement: a step the series never came back from,
    # weighted by how much it looks like a pure translation. A real regime
    # switch changes how the series *behaves*; a splice or a misalignment moves
    # the level and leaves the behaviour identical, and only the latter is a
    # defect worth resegmenting.
    ev["shift_strength"] = float(max(0.0, jump - transient) * purity)

    med = np.median(filled)
    ev["extreme_frac"] = float(np.mean(np.abs(filled - med) / spread > 3.0))
    return ev


def infer_hypothesis(
    evidence: dict,
    behav_risk: float,
    ood: float,
    reference: CorpusReference,
    z_named: dict,
    temperature: float = 0.5,
) -> tuple:
    """Soft posterior over what kind of window this is.

    Returns (label, confidence, posterior). Confidence is the posterior mass on
    the winning hypothesis; the policy refuses to act when it is low.
    """
    units = reference.units(evidence)
    defect = max(units.values()) if units else 0.0
    d_hi = _sigmoid(defect - 1.0, 0.4)
    d_lo = 1.0 - d_hi
    r_hi = _sigmoid(behav_risk - reference.risk_center, reference.risk_scale)
    r_lo = 1.0 - r_hi
    if reference.ood_scale > 0.0:
        ood_hi = _sigmoid(ood - reference.ood_ref, reference.ood_scale)
    else:
        ood_hi = 0.0

    repr_anom = _sigmoid(z_named.get("repr_jump_mean", 0.0) - 1.0, 0.8)
    disagree = _sigmoid(z_named.get("model_disagree", 0.0) - 1.0, 0.8)
    consensus = 1.0 - disagree
    # Evidence for a real rare event: wide excursions that the spike filter
    # refused to touch, or a departure the series recovered from.
    rare = max(
        _sigmoid(evidence.get("wide_outlier_frac", 0.0) / 0.01 - 1.0, 0.6),
        _sigmoid(evidence.get("transient_strength", 0.0) / TRANSIENT_REFERENCE - 1.0, 0.5),
    )
    # A stuck sensor also departs and returns, and would otherwise read as a
    # textbook transient event. Where the missingness evidence is strong, the
    # dull explanation is the right one.
    rare *= 1.0 - _sigmoid(units["missing"] - 1.0, 0.4)

    scores = {
        # Corruption needs both a visible defect and a model reaction, and is
        # argued against by evidence that the anomaly is a real event.
        "contaminated": 1.2 * d_hi + 1.0 * r_hi + 0.5 * repr_anom - 0.8 * rare,
        # Clean: nothing wrong, model unbothered.
        "clean": 1.2 * d_lo + 1.0 * r_lo,
        # Hard: no defect, model struggles but all models struggle alike.
        "hard": 1.2 * d_lo + 1.0 * r_hi + 0.6 * consensus - 0.4 * rare - 0.4 * ood_hi,
        # Rare-valid: model struggles and the window carries a real excursion.
        # Rare evidence also discounts corruption, so a genuine event is not
        # filed as a defect just because the model found it hard.
        "rare_valid": 0.6 * d_lo + 0.8 * r_hi + 1.6 * rare,
        # Clean OOD: no defect, structurally unlike the corpus. The absence of
        # a defect has to weigh as heavily here as elsewhere, or an unusual
        # profile alone would excuse a window that is plainly corrupted.
        "clean_ood": 1.2 * d_lo + 0.6 * r_hi + 1.0 * ood_hi,
    }

    keys = list(scores)
    vals = np.asarray([scores[k] for k in keys], dtype=np.float64)
    vals = vals - vals.max()
    p = np.exp(vals / max(temperature, 1e-6))
    p = p / p.sum()
    posterior = {k: float(v) for k, v in zip(keys, p)}
    label = keys[int(np.argmax(p))]
    return label, float(np.max(p)), posterior


def build_risk_state(
    window_id: int,
    series: np.ndarray,
    profile: np.ndarray,
    probe_result,
    z_row: np.ndarray,
    behav_risk: float,
    ood: float,
    reference: CorpusReference,
    signal_names: tuple,
    evidence: dict = None,
) -> RiskState:
    """Assemble the full risk state for one window."""
    evidence = dict(evidence) if evidence is not None else statistical_evidence(series)
    z_named = {n: float(z_row[i]) for i, n in enumerate(signal_names)}
    label, conf, posterior = infer_hypothesis(
        evidence, behav_risk, ood, reference, z_named
    )
    evidence["z"] = z_named
    return RiskState(
        window_id=window_id,
        profile=profile,
        behavior=probe_result.vector,
        z=z_row,
        utility=probe_result.utility,
        behav_risk=float(behav_risk),
        ood=float(ood),
        evidence=evidence,
        posterior=posterior,
        hypothesis=label,
        confidence=conf,
        reference=reference,
    )
