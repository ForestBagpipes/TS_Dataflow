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


def test_resegment_distortion_counts_what_the_crop_discarded():
    """A crop is judged on what it threw away, not only on what it kept.

    This test asserted the opposite until 2026-08-27. The old form read "a crop
    leaves what it keeps untouched, so distortion must be near zero", which is
    true of the retained span and false of the operation: `align_for_action`
    slices the original down to that same span, so the comparison saw two
    identical arrays and returned zero for every crop ever attempted. Measured
    on the xl corpus, 2766 attempts all reported exactly 0.000000 and the
    structural condition refused none of them, while 180 crops discarding a
    median 40 percent of their window were committed inside protected strata.

    The test had encoded the defect as the specification, which is why it did
    not fail when the defect was present. It now pins the corrected behaviour
    from both ends: a crop that discards a large share is distorted, and an
    operation that discards nothing is unaffected by the new term.
    """
    x = synth(8)
    x[300:] += 25.0
    out = apply_action(x, Action.RESEGMENT)
    assert out.applicable
    r = structure_distortion(x, out.series, Action.RESEGMENT, out.params, out.touched)
    discarded = 1.0 - len(out.series) / len(x)
    assert discarded > 0.1, "the fixture stopped exercising a real crop"
    assert r.distortion > 0.1, (
        f"a crop discarding {discarded:.2f} of the window reported "
        f"{r.distortion:.6f}")
    assert "discarded" in r.parts


def test_distortion_unchanged_when_nothing_is_discarded():
    """The new term must vanish for every operator that preserves length."""
    x = synth(8)
    x[100:104] += 40.0
    out = apply_action(x, Action.DESPIKE)
    assert out.applicable
    assert len(out.series) == len(x)
    r = structure_distortion(x, out.series, Action.DESPIKE, out.params, out.touched)
    assert "discarded" not in r.parts
