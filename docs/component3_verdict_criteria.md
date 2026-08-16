# Criteria for judging component three, fixed before the data

The single seed join left two proposers at p 0.054 and p 0.092 on the
discriminative test, close to but not past 0.05, and the two whole series
rewriters at no lift or negative lift. Two analyses will settle it and both
their interpretations are fixed here first.

## What is being run

**Three seeds.** The same four proposers on seeds 42, 1 and 2, merged, then
contaminated precision and protected recall recomputed against each proposer's
own baseline.

**A path stratified test.** The two local operator proposers are pooled and the
two whole series rewriters are pooled, and the path itself is tested as the
variable. This is the question actually at issue, which is whether the
calibrated local path discriminates better than the uncalibrated global one,
rather than whether each proposer individually beats blind rejection. It also
doubles the sample on each side.

The candidate quality is already balanced across the pairs without anyone
arranging it: 0.702 for the speed constraint proposer against 0.707 for the
statistical rule, and 0.873 for iterative minimum repair against 0.864 for
unconditional cleaning. The paired structure is therefore clean and the path is
close to the only variable that differs.

## The three readings, fixed now

**Reading one. The local path significantly beats blind rejection AND
significantly beats the global path.** Component three has discriminative power
on the calibrated local path only. The global path is uncalibrated and that is
an implementation defect rather than a property of the method. Written that
way, and the global path is then repaired by having the whole series rewriters
declare their actual changed point set as a footprint so they travel the
calibrated path.

**Reading two. The local path does not significantly beat blind rejection but
does significantly beat the global path.** Written as: the structural condition
behaves differently on its two paths and local is better than global, while
neither reaches discriminative power above blind rejection in absolute terms.
No repair claim is made.

**Reading three. Neither is significant.** The full retreat. The value of the
acceptance layer is that it rejects enough, and that its rejections are
reversible and auditable, not that it rejects accurately. The two published
proposer columns come out of the main table, and the limitation says the
problem is not those two proposers but component three itself.

## What does not depend on this, recorded now so reading three does not overcorrect

These stand regardless of the outcome and are not to be softened if the answer
is reading three.

**The downstream defensive result.** Unconditional cleaning degrades downstream
MSE by up to 463 percent and the gated version returns to 1.8 percent, with
three independently trained models agreeing in direction. This depends on how
much is rejected, not on how accurately.

**The characterisation.** The behavioural signal measures predictability rather
than data quality, decomposed into 0.203 and 0.141, replicated on four
backends, surviving the removal of the two contestable generator forms at p
9.5e-13.

**The soft against hard comparison.** At matched safety the hard condition
retains more repair, and the controllability difference in the frontier stands
on its own.

**The conformal guarantee.** It holds at every reachable target under a same
pool split, with the degradation under shift measured at three levels.

**The problem statement.** More than half of what published repair methods
propose lands on data that should not be touched, 51.7 percent, while on the
windows that need repair the same method has a harm rate of 0.382. This is a
statement about coverage and does not depend on our layer at all.
