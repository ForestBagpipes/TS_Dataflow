# Method

## Setting

A corpus is a set of windows. Each window is a real valued series of fixed
length. A proposer is any procedure that, given a window, emits an ordered
sequence of candidate edits, where an edit is an operator together with its
parameters. The proposer is not part of the contribution and is treated as a
black box throughout, which is what allows the same acceptance layer to be
placed around different ones.

The acceptance layer receives that sequence and decides, one edit at a time,
what is committed. It never proposes and never reorders.

## M1, the behavioural probe and what it measures

A frozen forecaster is used as a verifier rather than as an object of curation.
Given a window, the probe returns a vector of fourteen signals covering
forecast error at several horizons, reconstruction stability under masking,
sensitivity to input perturbation, the dynamics of internal representations
across layers, and disagreement between backends. The signals are computed
against a reference scale fixed before any edit, so that a smoothing edit
cannot shrink its own denominator.

Peer calibration converts the raw vector into a comparable score. For window i
with statistical profile p_i, a peer group is drawn by nearest neighbours in
profile space, and the calibrated deviation is

    z_i = (b_i - c_i) / s_i

with c_i and s_i the robust centre and spread of the peer group. The scalar
behavioural risk is a fixed weighted sum, r_i = z_i dot w.

**What this quantity measures is established empirically rather than assumed,
and the answer is not data quality.** It measures predictability, and it
decomposes into two roughly additive factors, level positioning uncertainty and
local shape unpredictability. Section E4 gives the design and the numbers. The
consequence for the method is that r_i cannot be the sole basis for acceptance,
which motivates the conjunction in M2.

## M2, the acceptance rule at execution time

Let x be the working copy and a an edit. The edit is applied to a sandbox copy,
giving a candidate a(x), and three quantities are computed.

    delta U (a)     model utility after minus before, from the probe
    D (x, a(x))     structural distance, defined below
    R (a)           risk of committing, from evidence about this edit

The edit is committed if and only if

    Accept(a) = 1[ delta U (a) > epsilon AND D(x, a(x)) < tau AND R(a) < eta ]

and rolled back otherwise, leaving x unchanged. The layer holds two properties.

**Non blocking.** In every state at least one action is admissible. The
identity action returns the working copy unchanged, so its utility delta is
zero, its structural distance is zero and its cost is zero. It is therefore
never rejected by the structural or risk conditions, and the utility condition
applies only to mutating actions. The admissible set is never empty, so the
layer cannot deadlock. This is why a window can always be returned untouched.

**Minimal interference, partially.** Of the edits vetoed on our corpus, 26.3
percent would have improved the window when judged offline against the pristine
series. This is reported with its number rather than claimed as a property. The
two conditions differ: the utility condition misfires on 29.7 percent of what
it blocks and the structural condition on 19.7 percent.

### Structural distance

D is a bounded aggregate of component terms, weighted by whether the operator
is local or global. A local operator declares the region it touches and is
judged outside that region on point wise shape, extremes, patch coherence and
footprint size, plus a spread term described next. A global operator rewrites
every point by construction, so it is judged on the signal band of the
spectrum, the trend, the seasonality, the memory and the tails.

The spread term exists because of a measured failure. Judging a local operator
only outside its declared footprint allows it to delete whatever it declares.
Ten clean windows were edited at nine percent of their points, lost ninety six
percent of their variance, and scored a structural distance of 0.037 against a
threshold of 0.12, because outside the declared footprint nothing had moved.
The term is a log ratio of the blockwise robust scale before and after,
symmetric so that inflating the variance costs the same as removing it, and
computed on the whole window, which is the one quantity the footprint exemption
cannot hide.

### Calibrating tau with a finite sample guarantee

The threshold is not chosen by hand. Fix a target level alpha and a loss

    L_i(tau) = 1 if window i comes out measurably worse than it went in, else 0

measured as normalised error against the pristine series. The loss is bounded
in the unit interval, which the guarantee requires, and it has no free
parameter to select.

Given a calibration set of n windows drawn exchangeably with the deployment
data, and an ordered grid of candidate thresholds, the procedure returns the
largest threshold whose corrected empirical risk clears the target,

    ( n R_hat(tau) + B ) / ( n + 1 ) <= alpha

with B the loss bound. The correction is what turns an average over n
calibration points into a bound on the expectation at a fresh point. The
resulting threshold satisfies E[ R(tau) ] <= alpha.

The derivation assumes the thresholds form a nested family, which appears
empirically as a monotone risk curve. **We verify this rather than assume it.**
Where the calibration risk curve is not monotone, the procedure falls back to
fixed sequence testing with Bentkus p values, walking the ordered grid from the
most conservative threshold and stopping at the first hypothesis it cannot
reject. That controls the family wise error rate without splitting it across
the grid, and it requires only that the ordering be fixed in advance.

Two properties of the procedure are worth stating because they bound what it
delivers. There is a floor: the most conservative threshold in the grid already
realises some non zero damage rate, so targets below that floor have no
solution and the procedure correctly returns the most conservative threshold
available. And the guarantee is conditional on exchangeability, whose violation
we measure rather than assume away.

## M3, invariant specification

Not developed in this work. The component weights inside the structural
distance are set by hand, informed by the failure analysis in the experiments
but not derived from a specification of what must be preserved. This is stated
in the limitations rather than presented as a design choice.

## M4, predictability decorrelation

Since M1 establishes that behavioural risk measures predictability, the obvious
correction is to estimate predictability and remove it. Six proxies are
computed from the series alone with no model call: spectral entropy, spectral
flatness, out of sample linear autoregression fit, persistence error, first
difference autocorrelation and sample entropy. Behavioural risk is regressed on
these and the residual is taken. The regression uses no labels.

The correction works and does not suffice. It raises corpus AUROC from 0.468 to
0.551, a paired improvement of 0.083 with interval 0.060 to 0.108, and it
removes the false alarm on all four generator forms of clean unpredictable
data, from between 0.705 and 0.760 down to between 0.504 and 0.527. It also
reduces detection of level displacement from 0.495 to 0.375, of flatline from
0.576 to 0.463 and of duplication from 0.573 to 0.501.

Those two directions are one fact. Unpredictability from a displaced level and
unpredictability from the structure of the series are the same quantity to this
signal, so removing the confound converts a false alarm on clean data into a
missed detection on displaced data. **No operation on the signal alone removes
both errors, which is the argument for a second evidence source that never
consults the model.**

The module is therefore diagnostic. Whether the residual enters the acceptance
path is decided by an integration test with a criterion fixed in advance:
protected stratum edits must fall and repair must not degrade by more than ten
percent relative.

## What the four modules compose into

M1 says the verification signal is unreliable and says precisely how. M4
quantifies the reliable part and shows that correcting it trades one error for
another. M2 is the response: a condition that does not consult the model at
all, applied at execution time to each edit, with a threshold that carries a
stated guarantee. M3 is what would replace the hand set weights inside that
condition and is left open.
