# LTSV implementability, assessed before writing any adapter

Written 2026-08-22. No adapter exists. The timings and the gradient facts below
were measured on the GPU node today by `.tmp/ltsv_probe.py`, the log is at
`/root/autodl-tmp/ltsv_probe.log`. Everything not measured is labelled as an
estimate.

## The method, from the paper

`arXiv:2511.11648v2`, accepted as a full paper at DASFAA 2026.

A block's value is the drop in a held out context loss after **one** gradient
step taken on that block.

    (9)  v(B_k) = L(D_context, theta) - L(D_context, theta_finetuned(B_k))
    (2)  theta_finetuned = theta - eta * grad_theta L(x, y, theta),  eta = 1e-5
    (10) v(x_t)  = mean over blocks containing x_t of v(B_k)
    (11) v(S_i)  = mean over points of v(x_t)

| item | paper's value |
|---|---|
| block length | 100 |
| block stride | 1, so blocks overlap |
| context loss | MSE on a held out context set |
| finetune | a single gradient step |
| backbones | Time-MoE, Time-LLM, MOMENT |
| datasets | Electricity, Exchange Rate, Weather, ETT-m2, Illness |
| complexity claim | O(nP) against O(nP^2 + P^3) for influence functions |

Equations 10 and 11 are arithmetic means. That matters here: the window score
rule already fixed in `docs/valuation_family_protocol.md` is also the arithmetic
mean, chosen so that RESEGMENT's unequal window lengths do not rank a long
window above a short one. LTSV therefore needs no new aggregation rule.

## The pivotal fact, and it holds

Every other part of the method is arithmetic. The question that decides
feasibility is whether this repository can produce `grad_theta L` at all, since
the probe path is forward only by design and section 2.1 sells that as the cost
advantage over influence function methods.

Measured on the node against `AutonLab/MOMENT-1-large`, which is **one of
LTSV's own three backbones**, so no substitution is needed:

| check | result |
|---|---|
| model loads | 5.4 s, 341.2M parameters |
| reconstruction loss carries a gradient | yes, `requires_grad = True` |
| apply one step then revert | parameters restored with **max deviation 0.000e+00** |
| context forward, batch of 8 | **18.3 ms** |
| block forward plus backward | **18.7 ms** |
| peak memory | **2.97 GiB** |

MOMENT is the right backbone for a second reason beyond being in their list. Its
pretraining task is masked reconstruction, so its MSE is genuinely zero shot,
which is exactly the loss equation 9 wants. `backends/moment.py` excludes it from
curation because its zero shot *forecast* is 20x naive, and that objection does
not apply here: LTSV never asks it to forecast.

Its fixed 512 point input is this corpus's window length, so a window is one
model input with no cropping.

## Two findings that change the implementation

**The backbone is frozen by default.** The gradient reached only **2 tensors**
holding under 0.05M elements, which is the reconstruction head, not the 341M
parameter body. `MOMENTPipeline.init()` leaves the encoder frozen. Equation 2
takes the gradient with respect to theta, the model parameters, so a faithful
implementation has to unfreeze the body. That is one line, `p.requires_grad_(True)`,
and the consequence is a larger memory and time footprint than the numbers above,
which were measured head only. Estimated, not measured: parameters plus gradient
plus snapshot at 341M by 4 bytes is about 4.1 GiB, comfortable on a 32 GiB card,
and the forward plus backward should land in the 40 to 60 ms range rather than
18.7 ms.

**The loss must be read in eval mode.** The probe ran the model in `train()` so
that gradients flow, and the context loss then moves between two reads of the
same parameters because dropout is active. In the probe this showed up as 1.0591
after the step against 1.0472 after an exact revert, a difference of the same
order as the effect being measured. The adapter therefore takes the gradient in
train mode and measures both context losses in eval mode, otherwise equation 9
returns dropout noise.

That second point is a real trap rather than a detail. It would not have
produced an error, only a value score made of noise.

## Cost, at this corpus's scale

Per block: one forward plus backward on the block, apply the step, one forward on
the context set, revert. Call it about 80 ms with the body unfrozen, which is an
estimate built on the two measured numbers above.

| block scheme | blocks per 512 point window | blocks at 2000 windows | estimated wall clock |
|---|---|---|---|
| paper's, length 100 stride 1 | 413 | 826000 | about 18 hours |
| this repository's, length 128 non overlapping | 4 | 8000 | about 11 minutes |

The second row is the scheme `docs/valuation_family_protocol.md` already fixed,
and it already carries the reason: the corpus is 2000 independent 512 point
windows rather than one continuous series, fully overlapping blocks would give
770000 blocks, and the Monte Carlo in Data Shapley cannot run at that size. The
same deviation applied to LTSV keeps all four valuation baselines on one block
scheme, which is what makes them comparable to each other. It is a declared
deviation from the paper, in the same sentence as the others, not a quiet one.

## Fidelity risks, ranked

| # | risk | severity | handling |
|---|---|---|---|
| 1 | block length 128 non overlapping against the paper's 100 with stride 1 | medium | declared, and identical to the deviation the other three baselines already carry |
| 2 | one backbone, MOMENT, where the paper reports three | medium | declared. MOMENT is one of theirs, so this narrows coverage rather than substituting a method |
| 3 | the context set is not defined in the abstract level description available | medium | fixed in advance as the validation split of the existing 7:2:1 window split, so no window scores itself |
| 4 | whether the loss is averaged per point or per series | low | per point, matching how the other three baselines are aggregated here |
| 5 | whether blocks and context come from the same series | low | different windows, following the split above |

Four decisions have to be pre registered before the first score exists. That is
fewer than a TimeLAVA reimplementation would need, where the wavelet basis, the
selection rule, the unbalanced optimal transport regularisation and the
sensitivity approximation are all unspecified at the abstract level, which is why
LTSV is the first fallback and TimeLAVA the third choice.

## Effort

Estimates, not measurements.

| step | estimate |
|---|---|
| unfreeze the body, add a gradient enabled loss path to `backends/moment.py` without disturbing the forward only path the agent uses | half a day |
| the one step apply, measure, revert loop with an exact parameter snapshot | half a day, the probe already shows the revert is exact |
| block and window aggregation, reusing the existing rule | a quarter day |
| wire into the corpus layer protocol beside the other three | a quarter day |
| pre register the four decisions, then a smoke run on 100 windows | half a day |
| full run and validation | half a day, plus about 11 minutes of GPU |

About two and a half days of work. The pivotal risk that would have made this
much worse, no gradient path, is retired.

## What this does not settle

Whether LTSV is needed at all depends on the TSRating pilot. If that pilot
succeeds the post 2025 count is two and neither LTSV nor TimeLAVA is required.
This assessment exists so that a failed pilot can be followed by implementation
on the same day rather than by another round of investigation.
