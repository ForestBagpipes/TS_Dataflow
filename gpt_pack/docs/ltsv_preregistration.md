# LTSV adapter, the four decisions fixed before any score exists

Written 2026-08-23, before the adapter was written and before any value was
computed. `arXiv:2511.11648v2`, DASFAA 2026, describes its method at a level
that leaves four things unspecified for this corpus. Each is settled here so
that none of them can be settled later in whichever direction reads better.

Feasibility was tested first and is recorded in `docs/ltsv_feasibility.md`. The
pivotal fact, that a gradient can be taken through a frozen backend's
reconstruction loss, was measured rather than assumed.

## The method being implemented

    (9)  v(B_k) = L(D_ctx, theta) - L(D_ctx, theta - eta * grad_theta L(B_k, theta))
    (10) v(x_t) = mean over blocks containing x_t of v(B_k)
    (11) v(S_i) = mean over points of v(x_t)

with `eta = 1e-5`, a single gradient step, and the context loss an MSE on a held
out set. Those four values are the paper's and are not decisions.

## Decision 1, block length and stride

**128 points, non overlapping, so four blocks per 512 point window.** The paper
uses length 100 with stride 1.

The reason is not fidelity, it is that the other three valuation baselines
already run at this block scheme and a comparison among them requires one scheme.
`docs/valuation_family_protocol.md` fixed it with its own reason: this corpus is
2000 independent 512 point windows rather than one continuous series, and fully
overlapping blocks would give 770000 blocks, which the Data Shapley Monte Carlo
cannot run at.

The cost of the paper's scheme was measured rather than assumed. At 413 blocks
per window and about 80 ms per block, 2000 windows would take about 18 hours
against about 11 minutes at four blocks per window.

This is a declared deviation and it appears in the same table note as the
deviation the other three carry.

## Decision 2, backbone

**MOMENT, `AutonLab/MOMENT-1-large`, alone.** The paper reports Time-MoE,
Time-LLM and MOMENT.

MOMENT is one of the paper's own three, so this narrows coverage rather than
substituting a different model for the one they used. It is also the one of the
three whose native pretraining task is masked reconstruction, which makes its
MSE genuinely zero shot and therefore the right loss for equation 9 without any
head being trained first.

`backends/moment.py` excludes MOMENT from curation because its zero shot
forecast is twenty times worse than a seasonal naive reference. That objection
does not transfer: LTSV never asks it to forecast.

Reporting one backbone where the paper reports three is stated in the table, not
folded into a single number.

## Decision 3, the context set

**The validation split of the existing 7:2:1 window split**, the same split
`valuation_export.py` writes and the same one the other three baselines use.

The consequence that matters is that no window is ever in the context set used
to value it, so nothing scores itself. Blocks come from the training split and
the context loss is measured on the validation split.

## Decision 4, how the context loss is averaged

**Per point.** The loss is a mean squared error over all points of all context
windows, giving every point equal weight, rather than a mean over per window
losses which would give every window equal weight regardless of length.

This matches how the other three baselines aggregate here, and it matches
equations 10 and 11, which are themselves per point means. It also has the same
justification as the window score rule: RESEGMENT produces windows of unequal
length and a per window mean would weight a short window as heavily as a long
one.

## Two implementation facts that are not decisions

Both were measured and both would silently corrupt the result rather than raise
an error, so each carries an assertion in the adapter.

**The backbone must be unfrozen.** `MOMENTPipeline.init()` leaves the encoder
frozen and the gradient reaches only two tensors of the reconstruction head,
under 0.05M elements of 341M. Equation 2 differentiates with respect to theta,
the model parameters. The adapter unfreezes and asserts that the number of
parameters receiving a gradient exceeds a floor, so a future change that
refreezes the body fails loudly.

**The context loss must be read in eval mode.** Gradients require train mode,
where dropout is active, and the loss then varies between two reads of identical
parameters. Measured on the node, an exact parameter revert returned 1.0472
against 1.0591 after the step, a difference of the same order as the effect being
measured. The adapter takes the gradient in train mode and measures both context
losses in eval mode, and asserts that two consecutive eval reads of unchanged
parameters agree to within a tolerance, so a regression to train mode is caught
by the assertion rather than by a reviewer.

## What is not claimed

The estimation accuracy of LTSV is not re-verified. It is used as described, on
this corpus, and the comparison is at the level of the prepared corpus and its
downstream effect, exactly as for the other three. Whether its scores correlate
with any intrinsic notion of quality is its claim and not tested here.

## Reporting

Windows that cannot be blocked because they carry injected gaps are handled by
the rule already fixed in `docs/valuation_family_protocol.md`: they are carried
into the prepared corpus as not selected rather than dropped from the comparison,
and their count is reported next to the selection fraction.
