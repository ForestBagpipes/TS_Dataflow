"""Context-only r3 probes with fixed original-time mask transplantation.

This module accepts Episode, which has no deployment-future target field.
Historical validation is sliced only from the current dirty observation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np

from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.schemas import Episode, array_hash, frozen_array, json_hash, require

PSI_NAMES = ('length_horizon_ratio_difference', 'gap_lag_horizon_difference',
             'longest_gap_horizon_difference', 'target_coverage_difference',
             'covariate_coverage_difference', 'observed_mad_difference_over_current_scale')


def canonical_view_hash(view):
    """Real worker payload identity, independent of parent/spec lineage aliases."""
    return json_hash(dict(horizon=view.horizon, raw_mask=array_hash(view.observed_mask),
                          **{k: array_hash(getattr(view, k)) for k in
                             ('target', 'covariates', 'timestamps', 'availability')}))


def visible_descriptor(episode):
    """Only directly observed values/masks; no source, condition or future."""
    x = episode.target;missing = ~np.isfinite(x);where = np.flatnonzero(missing)
    edges = np.diff(np.r_[False, missing, False].astype(int))
    lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
    observed = x[~missing]
    return dict(length=len(x), horizon=episode.horizon, length_horizon_ratio=len(x) / episode.horizon,
                gap_lag_horizon=float(np.mean(where - len(x)) / episode.horizon) if len(where) else 0.,
                longest_gap_horizon=float(max(lengths, default=0) / episode.horizon),
                target_coverage=float((~missing).mean()),
                covariate_coverage=float(np.isfinite(episode.covariates).mean()) if episode.covariates.size else 0.,
                observed_mad=float(np.median(np.abs(observed - np.median(observed)))) if len(observed) else None)


def proxy_mismatch(current, probe, current_scale):
    before, after = visible_descriptor(current), visible_descriptor(probe)
    require(before['observed_mad'] is not None and after['observed_mad'] is not None, 'No observed robust-scale support')
    fields = ('length_horizon_ratio', 'gap_lag_horizon', 'longest_gap_horizon', 'target_coverage', 'covariate_coverage')
    values = [after[f] - before[f] for f in fields]
    values.append((after['observed_mad'] - before['observed_mad']) / current_scale)
    return dict(zip(PSI_NAMES, values))


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    start: int
    origin: int
    horizon: int
    current_origin: int = 512

    def __post_init__(self):
        require(self.name in ('long', 'short', 'h32', 'second'), 'Unknown registered r3 probe')
        require(0 <= self.start < self.origin < self.current_origin, 'Invalid historical input interval')
        require(0 < self.horizon <= self.current_origin - self.origin, 'Historical validation crosses current origin')

    def to_dict(self):
        return dict(name=self.name, start=self.start, origin=self.origin,
                    horizon=self.horizon, current_origin=self.current_origin)

    @property
    def hash(self):
        return json_hash(self.to_dict())


def registered_specs(horizon: int):
    require(horizon in (96, 192), 'r3 task horizons are frozen to H96/H192')
    r = 512 - horizon
    return {'long': ProbeSpec('long', 0, r, horizon),
            'short': ProbeSpec('short', 64, r, horizon),
            'h32': ProbeSpec('h32', 0, 480, 32),
            'second': ProbeSpec('second', 0, r - 64, horizon)}


@dataclass(frozen=True)
class PreparedProbe:
    base_uid: str
    spec: ProbeSpec
    status: str
    reason: str | None
    view: Episode | None
    validation: np.ndarray
    scoring_mask: np.ndarray
    copied_mask: np.ndarray
    current_scale: float
    current_input_hash: str
    input_hash: str

    def __post_init__(self):
        for name in ('validation', 'scoring_mask', 'copied_mask'):
            object.__setattr__(self, name, frozen_array(getattr(self, name)))
        require(self.status in ('prepared', 'unsupported'), 'Invalid probe preparation status')
        require((self.view is not None) == (self.status == 'prepared'), 'Unsupported probe contains model input')
        require(self.status == 'prepared' or bool(self.reason), 'Unsupported probe must state a reason')

    def metadata(self):
        return dict(base_uid=self.base_uid, spec=self.spec.to_dict(), spec_hash=self.spec.hash,
                    status=self.status, reason=self.reason, view_uid=None if self.view is None else self.view.uid,
                    current_scale=self.current_scale, current_input_hash=self.current_input_hash,
                    input_hash=self.input_hash, scoring_mask_hash=array_hash(self.scoring_mask),
                    historical_validation_hash=array_hash(self.validation), copied_mask_hash=array_hash(self.copied_mask),
                    support_count=int(self.scoring_mask.sum()), coverage=float(self.scoring_mask.mean()),
                    future_labels_read=0)


def prepare_probe(episode: Episode, spec: ProbeSpec, current_scale: float):
    """Slice first, then copy the current visible gap at its origin-relative lag.

    No clipping or moving a gap is permitted. Original missing observations and
    historical as-of release masks remain missing in the sliced input.
    """
    require(episode.split in ('train', 'dev'), 'Probe refuses held-out episodes')
    require(len(episode.target) == spec.current_origin == 512, 'Probe requires current L512 context')
    require(np.isfinite(current_scale) and current_scale > 0, 'Frozen positive current-task MASE scale required')
    current = np.c_[episode.target, episode.covariates]
    scale = float(current_scale)
    current_hash = json_hash({name: array_hash(getattr(episode, name)) for name in
                             ('target', 'covariates', 'timestamps', 'availability')})
    y = episode.target[spec.origin:spec.origin + spec.horizon].copy()
    scoring = np.isfinite(y) & (episode.availability[spec.origin:spec.origin + spec.horizon, 0]
                               <= episode.timestamps[-1])
    copied = np.zeros((spec.origin - spec.start, current.shape[1]), dtype=bool)
    missing_row, missing_col = np.where(~np.isfinite(current))
    shifted = missing_row + spec.origin - spec.current_origin
    outside = (shifted < spec.start) | (shifted >= spec.origin)
    reason = 'copied_current_gap_outside_probe_prefix' if outside.any() else None
    if reason is None and int(scoring.sum()) < max(16, int(np.ceil(.5 * spec.horizon))):
        reason = 'insufficient_currently_observed_historical_validation'
    identity = dict(base_uid=episode.uid, current_input_hash=current_hash, spec=spec.to_dict(),
                    mask_policy='all_visible_channel_missing_at_fixed_origin_relative_lags')
    if reason is not None:
        identity.update(status='unsupported', reason=reason,
                        outside_gap_positions=[[int(r), int(c)] for r, c in zip(shifted[outside], missing_col[outside])])
        return PreparedProbe(episode.uid, spec, 'unsupported', reason, None, y, scoring, copied,
                             scale, current_hash, json_hash(identity))
    copied[shifted - spec.start, missing_col] = True
    t = episode.timestamps[spec.start:spec.origin]
    availability = episode.availability[spec.start:spec.origin]
    values = current[spec.start:spec.origin].copy()
    values[availability > t[-1]] = np.nan
    values[copied] = np.nan
    identity['fields'] = {'target': array_hash(values[:, 0]), 'covariates': array_hash(values[:, 1:]),
                          'timestamps': array_hash(t), 'availability': array_hash(availability),
                          'raw_mask': array_hash(np.isfinite(values[:, 0]))}
    digest = json_hash(identity)
    view = replace(episode, uid=f'{episode.uid}:r3:{spec.name}:{digest[:16]}',
                   raw_start=episode.raw_start + spec.start, context_end=episode.raw_start + spec.origin,
                   horizon=spec.horizon, target=values[:, 0], covariates=values[:, 1:],
                   timestamps=t, availability=availability)
    return PreparedProbe(episode.uid, spec, 'prepared', None, view, y, scoring, copied,
                         scale, current_hash, digest)


@dataclass(frozen=True)
class ProbeResult:
    base_uid: str
    probe: str
    family: str
    status: str
    reason: str | None
    input_hash: str
    model_identity_hash: str
    reference_arm: str
    spec: Mapping
    scoring_mask_hash: str
    current_scale: float
    raw_predictions: Mapping[str, np.ndarray]
    mae: Mapping[str, float]
    gain: Mapping[str, float]
    support_count: int
    coverage: float
    invoice: Mapping

    def to_dict(self):
        return dict(base_uid=self.base_uid, probe=self.probe, family=self.family, status=self.status,
                    reason=self.reason, input_hash=self.input_hash, model_identity_hash=self.model_identity_hash,
                    reference_arm=self.reference_arm, spec=dict(self.spec), scoring_mask_hash=self.scoring_mask_hash,
                    current_scale=self.current_scale,
                    raw_predictions={a: np.asarray(p).tolist() for a, p in self.raw_predictions.items()},
                    prediction_hashes={a: array_hash(p) for a, p in self.raw_predictions.items()},
                    mae=dict(self.mae), gain=dict(self.gain), support_count=self.support_count,
                    coverage=self.coverage, invoice=dict(self.invoice), future_labels_read=0)


def score_probe(prepared: PreparedProbe, family: str, predictions, model_identity_hash: str, invoice,
                *, reference_arm: str):
    require(family in ('bolt', 'timesfm'), 'Unknown actual backbone family')
    require(bool(model_identity_hash), 'Probe result requires actual model identity')
    require(reference_arm in POOL, 'Actual frozen family reference arm required')
    require(prepared.status == 'prepared', 'Unsupported probes cannot be scored or filled with zeros')
    require(set(predictions) == set(POOL), 'Missing actual five-arm prediction')
    errors = {}
    for arm, pred in predictions.items():
        p = np.asarray(pred)
        require(p.shape == (prepared.spec.horizon,) and np.isfinite(p).all(), 'Nonfinite or malformed actual prediction')
        errors[arm] = float(np.abs(p[prepared.scoring_mask] - prepared.validation[prepared.scoring_mask]).mean())
    gain = {a: (errors[reference_arm] - errors[a]) / prepared.current_scale for a in POOL}
    require(len({c['key'] for c in invoice['charges']}) == len(invoice['charges']), 'Duplicated probe computation charge')
    require(all(np.isfinite(c['seconds']) and c['seconds'] >= 0 for c in invoice['charges']), 'Invalid actual probe charge')
    require(np.isclose(sum(c['seconds'] for c in invoice['charges']), invoice['total_seconds'], rtol=0, atol=1e-12), 'Probe invoice sum mismatch')
    return ProbeResult(prepared.base_uid, prepared.spec.name, family, 'completed', None, prepared.input_hash,
                       model_identity_hash, reference_arm, prepared.spec.to_dict(), array_hash(prepared.scoring_mask),
                       prepared.current_scale, predictions, errors, gain,
                       int(prepared.scoring_mask.sum()), float(prepared.scoring_mask.mean()), invoice)


def paired_response(long: ProbeResult, short: ProbeResult):
    """Signed earlier-observation response, never a zero-filled missing result."""
    require(long.status == short.status == 'completed', 'Both measured probes are required for kappa')
    require((long.probe, short.probe) == ('long', 'short'), 'Response pair must be registered long/short')
    for name in ('base_uid', 'family', 'model_identity_hash', 'reference_arm', 'current_scale', 'scoring_mask_hash'):
        require(getattr(long, name) == getattr(short, name), 'Mismatched response pair ' + name)
    require(long.spec['origin'] == short.spec['origin'] and long.spec['horizon'] == short.spec['horizon']
            and short.spec['start'] - long.spec['start'] == 64, 'Response pair changed endpoint/H or length decrement')
    kappa = {a: long.gain[a] - short.gain[a] for a in POOL}
    Lq = long.spec['origin'] - long.spec['start']
    z = {a: (long.spec['current_origin'] - Lq) / 64 * kappa[a] for a in POOL}
    return dict(base_uid=long.base_uid, family=long.family, reference_arm=long.reference_arm,
                model_identity_hash=long.model_identity_hash, current_scale=long.current_scale,
                long_input_hash=long.input_hash, short_input_hash=short.input_hash,
                scoring_mask_hash=long.scoring_mask_hash, d_long=dict(long.gain), d_short=dict(short.gain),
                kappa=kappa, z=z, response_scope='signed_pipeline_response_not_market_causal_effect',
                future_labels_read=0)
