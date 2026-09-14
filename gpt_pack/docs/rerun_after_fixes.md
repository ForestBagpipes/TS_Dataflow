# What has to be rerun after each pending fix

Three changes are specified and unapplied. Each one alters the acceptance rule,
so each invalidates a different set of results. This lists what falls over,
what survives, and what it costs to rebuild, so the decision to apply a fix is
made with the bill in view.

Current wall clock references, RTX 5090, multi-family preset: perception runs
at roughly 6.5 windows per second, curation at roughly 9 per second per pass.

## Fix 1, variance preservation in the structural distance

**What it changes.** Local operators are currently judged outside the footprint
they declare, so an edit that removes ninety six percent of a window's variance
inside its own footprint scores 0.037 against a threshold of 0.12. Adding a
whole window spread ratio term makes that visible.

**Evidence it will work.** The ten destructive edits have ratios from 0.032 to
below 0.5 and the three benign DESPIKE edits sit at 0.99 to 1.00. The
populations are completely separated in the run on hand, so the term will
separate them, and the open question is only what it does to edits nobody has
looked at yet.

**Invalidated.** Everything with an acceptance decision in it. The 2000 window
run, all six sweep points, all eight ablation rungs, both tau sweeps, the
downstream transfer numbers and the edit economics table.

**Survives.** Everything measured before or without curation: all behavioural
risk values, the controlled ladder, the 2x2, the cross model check, the
per stratum distributions, the predictability proxies.

**Cost.** The sweep is the expensive part at roughly 4600 seconds, the ablation
ladder 800, the 2000 window run about 900 including transfer. Call it two and a
half hours of GPU to rebuild the full result set.

## Fix 2, a reachable out of distribution threshold

**What it changes.** `corpus_reference` admits the OOD hypothesis only when the
85th percentile of the OOD score exceeds 1e-3. The score is a cosine distance
between normalised profiles and does not reach that on this corpus, so the
hypothesis fired 0 times in 210 clean_ood windows. The threshold has to come
from the corpus distribution of the score rather than from an absolute
constant.

**Invalidated.** Anything that depends on the hypothesis distribution, which
means detection accuracy, action accuracy, the confidence analysis and the
triple failure decomposition. Acceptance decisions change too wherever the
hypothesis changes the proposal order, so in practice the same list as fix 1.

**Survives.** The same set as fix 1, plus the protection numbers are likely to
move only slightly, since the hypothesis mostly changes which operator is tried
first rather than whether an edit is accepted.

**Cost.** Same as fix 1 if run together, which is the sensible order. These two
should land in one batch.

## Fix 3, action_risk should consume expected edit success

**What it changes.** `action_risk` weights the class posterior at 0.45, and the
posterior is anti correlated with edit quality: the most confident tenth of
windows is wrong 59.5 percent of the time against 48.4 percent overall. The
posterior answers which kind of window this is, not whether this edit will
work. The term should consume an estimate of edit success instead.

**Invalidated.** Every acceptance decision, so the same list again, plus the
risk coverage curve which should not be published until this lands.

**Not yet specified.** Unlike the other two, the replacement quantity does not
exist yet. An expected success estimate needs either a calibration set of edits
with known outcomes or a cheap proxy validated against one. This is a design
task, not a patch.

## The order to do this in

1. Fixes 1 and 2 together, since they invalidate the same results and cost one
   rebuild rather than two.
2. Rebuild the sweep, the ablation ladder and the 2000 window run from the same
   commit, roughly two and a half GPU hours.
3. Regenerate `docs/edit_economics.md` and `docs/triple_failure_analysis.md`
   from the new traces, keeping the current versions as the before column.
4. Fix 3 afterwards, on its own, once the replacement quantity is designed and
   validated.

## What is already independent of all three

The tau selection in `results/tau_holdout.json` chooses a threshold on a
separate seed with a rule fixed in code, so it is not invalidated by the fixes,
though the selected value should be reconfirmed on the same holdout once the
structural distance changes, since fix 1 changes what the distance measures.
