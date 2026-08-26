# Diagnostic playbook

What to do when a number comes back and does not look like it should. Written
after the fourth time the same three mistakes were made in a different costume.
Every tree below is a real investigation from this project, with the number it
started from and the number it ended at, so the tree can be checked rather than
believed.

The order matters and is the whole point.

    1. is it a configuration fault      did the run measure what you think
    2. is it an artefact                units, denominator, aggregation
    3. only then, is it the method      the interesting case, and the rarest

Every time this order was violated on this project it cost a GPU pass. Every
time it was followed the cause was found before any compute was spent.

## Step 0, before anything, go back to the code that produced the number

Not the result file, not the log line, the function. A result file records what
a function returned, and the question is almost always what the function meant.
Three of the four cases below were settled inside the function body and needed
no rerun at all.

The specific reading that pays: find the denominator, find what is excluded
from it, and find the aggregation. Those three lines carry most of the errors.

## Tree one, a column ranks the arms in an order that makes no sense

**The case.** Repair distance put SCREEN at 2109 against no action at 1382, so
a repair method looked worse than doing nothing.

    is the corpus of mixed provenance?
        yes -> is the quantity carrying units?
                   yes -> STOP. It is a units artefact, not a method result.
                          Normalise inside the homogeneous unit before
                          aggregating, then re read the column
        no  -> is one subgroup much larger in magnitude than the others?
                   yes -> STOP. It is a subgroup domination artefact.
                          Report by subgroup, and build any headline from a
                          weighted mean over the comparable ones

**How it was found.** The smoke test ran on `--source ett`, where every window
is transformer telemetry and the units are uniform, so the column looked fine.
The paper's corpus is `mixed` and spans a bitcoin price near 26000 beside a rate
near 3.4.

**The rule this produced.** A口径 change must be smoked on the corpus it will
run on, never on the convenient one.

**It recurred.** The same tree caught the repair nRMSD column three weeks later,
where level shift was 14 percent of the windows and 62 percent of the mean.
Same shape, different costume: the first was units across datasets, the second
was magnitude across contamination kinds. Both were fixed by refusing to
aggregate across the inhomogeneous axis.

## Tree two, two independent computations of the same column disagree

**The case.** The damage rate recomputed from the flushed traces disagreed with
the table by up to 0.32 on one arm, while every other column agreed to floating
point.

    do the two agree on the denominator?
        no  -> find which windows one includes and the other does not
        yes -> do the two use the same distance or loss function?
                   no -> read both function bodies side by side and list every
                         difference, then test each one separately
                   yes -> is one reading a stale file?

    for each difference found, ask: on which windows does it change the sign
    of the comparison? Group those windows and look at what they have in common.

**How it was found.** Both functions were read side by side. `audit._nmse`
subtracts each series' median and replaces a non finite point with the median.
`run_main._dist` does neither, it drops the non finite difference. Grouping the
disagreeing windows by contamination kind put 212 of them in the two missing
kinds, and measuring those on the untouched corpus gave a distance of exactly
zero: a window with a hole is at distance zero from the truth when the only
points that differ are the ones being dropped.

**Which one was right, and how that was settled without a GPU.** `L1_screen` is
deterministic and needs no model pool, so it was re run offline and reproduced
the table exactly, 329 edits and damage 0.6657. The table was right and the
trace field was the broken one.

**The rule this produced.** When two sources disagree, find a third that can be
computed cheaply and independently. Do not adjudicate between two by argument.

## Tree three, an ablation rung equals the reference row exactly

**The case.** Three of seven rungs came back identical to the full method in
every column, to the digit.

    is the switched component reaching the call site at all?
        Do not answer this by reading the call site alone. Get three
        independent readings:
          a. the code path, is the callback invoked and is the feedback closed
          b. the run's own instrumentation, does it report the component acting
             (counters, decision counts, injection counts)
          c. the per window traces, does the intermediate behaviour differ

        all three say it is running -> the component acts but does not change
                                       the outcome. Go find where its effect is
                                       absorbed
        any one says it is not      -> wiring fault, fix and rerun

    where an effect is absorbed:
        is there a downstream gate that is deterministic given the state?
            yes -> the component can only change the path, not the endpoint.
                   This is a property of the design, and it may be exactly what
                   a safety theorem claims. Measure the path difference and the
                   endpoint difference separately and report both

**How it was found.** The policy rungs reported `n_decisions_with_choice` of
423 and the traces differed from the fixed rule on 265 of 1986 windows in
action order, while final state was identical on all 1986. So the policy ran,
reordered, and the shield converged to the same acceptance set regardless.

**What it turned into.** Not a bug and not a failure of the run, but a fact that
had to change a claim: the policy cannot be sold as a quality gain on this
corpus, and the same measurement is direct evidence for the exploration safety
theorem.

**The rule this produced.** An identical number is a finding, not an error. The
question is never only whether the component ran, it is where its effect went.

## Tree four, a rate is out of range or the wrong side of a prediction

**The case.** Protected stratum retention was reported at 0.57 to 0.67 against a
predicted 0.52, and the pre registration was recorded as failing.

    write down the numerator and the denominator as sentences, not symbols
        "windows in stratum S that survived selection"
        "windows in stratum S that this method was able to score"
    are they over the same set?
        no -> that is the whole error. Two denominators that answer different
              questions must both be reported and never divided into each other
    are they over the same set, and the rate still looks wrong?
        -> is the baseline the nominal rate or the realised one?

**How it was found.** The numerator counted scored windows, the denominator
counted all windows, and the result was then divided by the pool rate. The
effective pool rate was 0.803, not 0.5. Split into a corpus level rate and a
pool level rate, both reported, neither divided into the other.

**The rule this produced.** State the numerator and denominator in words before
computing any ratio. A ratio whose two halves cannot be said in one sentence
each is wrong more often than not.

## The four checks every paper number passes

Kept here as well as in `number_selfchecks.md`, because this file is the one
that gets opened when something looks wrong.

1. **What is the denominator**, what is excluded from it, and is the exclusion
   correlated with the effect being measured
2. **Is it dominated by a subgroup**, and would it survive being reported by
   subgroup
3. **Is there another explanation** that produces the same number, and has it
   been ruled out by measurement rather than by argument
4. **Cross reconcile** against an independently computed source, and when the
   two disagree find a cheap third

## Things that are never the first hypothesis

Ranked by how often each was wrong on this project.

- the model is bad
- the method does not work
- the data is unusual

Each of these was proposed at least once and was wrong every time. The cause
was a hard coded corpus, a units mismatch, an aggregation over an inhomogeneous
axis, a denominator over the wrong set, and a metric that dropped the points it
was supposed to measure.
