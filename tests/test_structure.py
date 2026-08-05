"""Structure fidelity: what it must catch, and what it must not punish."""

import numpy as np
from conftest import synth

from introact_ts.actions import apply_action
from introact_ts.structure import structure_distortion
from introact_ts.types import Action


def test_identity_edit_is_zero_distortion(clean_series):
    r = structure_distortion(clean_series, clean_series.copy())
    assert r.distortion == 0.0


def test_distortion_is_bounded():
    x = synth(1)
    destroyed = np.full_like(x, float(np.median(x)))
    r = structure_distortion(x, destroyed, Action.DENOISE)
    assert 0.0 <= r.distortion <= 1.0
    assert r.distortion > 0.5


def test_denoise_distortion_grows_with_strength():
    x = synth(2, noise=1.0)
    ds = []
    for strength in ("light", "medium", "heavy"):
        out = apply_action(x, Action.DENOISE, strength=strength)
        ds.append(structure_distortion(x, out.series, Action.DENOISE).distortion)
    assert ds[0] < ds[1] < ds[2]


def test_flattening_the_tails_is_caught():
    """The failure mode the whole module exists for: peaks smoothed away."""
    x = synth(3)
    x[100:110] += 30.0
    x[300:310] -= 30.0
    clipped = np.clip(x, np.percentile(x, 2), np.percentile(x, 98))
    r = structure_distortion(x, clipped, Action.DENOISE)
    assert r.parts["extremes"] > 0.2


def test_local_repair_outside_footprint_is_cheap():
    """Removing injected spikes must not read as structural damage."""
    x = synth(4)
    x[[80, 200, 350]] += 30.0
    out = apply_action(x, Action.DESPIKE)
    r = structure_distortion(x, out.series, Action.DESPIKE, out.params, out.touched)
    assert r.parts["shape"] == 0.0
    assert r.parts["extremes"] == 0.0
    assert r.distortion < 0.12


def test_edits_outside_the_declared_footprint_are_caught():
    """Claiming to touch three points while rewriting the window must not pass."""
    x = synth(5)
    x[[80, 200, 350]] += 30.0
    out = apply_action(x, Action.DESPIKE)
    sneaky = out.series.copy()
    sneaky += np.random.RandomState(0).randn(len(sneaky)) * np.std(x)
    r = structure_distortion(x, sneaky, Action.DESPIKE, out.params, out.touched)
    assert r.parts["shape"] > 0.2
    assert r.distortion > 0.12


def test_flat_fill_is_penalised_as_an_implausible_patch():
    """A straight line through a gap passes every global descriptor but this."""
    x = synth(6)
    touched = np.zeros(len(x), dtype=bool)
    touched[200:250] = True
    flat = x.copy()
    flat[200:250] = x[199]
    r = structure_distortion(x, flat, Action.IMPUTE, {}, touched)
    from introact_ts.verify import VerifyConfig

    assert r.parts["patch"] > 0.4
    assert r.distortion > VerifyConfig().tau  # enough on its own to veto


def test_plausible_fill_is_not_penalised():
    x = synth(7)
    gapped = x.copy()
    gapped[200:250] = np.nan
    out = apply_action(gapped, Action.IMPUTE, method="seasonal")
    r = structure_distortion(gapped, out.series, Action.IMPUTE, out.params, out.touched)
    assert r.parts["patch"] < 0.5


def test_resegment_compares_only_the_retained_span():
    """A crop leaves what it keeps untouched, so distortion must be ~zero."""
    x = synth(8)
    x[300:] += 25.0
    out = apply_action(x, Action.RESEGMENT)
    assert out.applicable
    r = structure_distortion(x, out.series, Action.RESEGMENT, out.params, out.touched)
    assert r.distortion < 0.05
