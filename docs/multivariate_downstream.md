# The multivariate downstream evaluation, and what it does not deliver

## The design, stated as a choice

**Curation operates per channel. Evaluation operates on multivariate
forecasting.** Data quality problems in this setting are within channel sensor
faults: a stuck reading, a dropout, a spike, a splice at a mismatched level.
Treating each channel separately is the right granularity for the intervention.
The downstream task these corpora exist to serve is multivariate, so that is the
granularity for the evaluation.

This is a design choice with a reason, not a limitation being managed.

## What this change delivers

Training pairs come from aligned positions, meaning the channels in a block
share a file and a start index, rather than from unrelated positions in
unrelated channels. Error is reported over multivariate blocks rather than over
isolated windows. The evaluation can therefore be described as multivariate
forecasting under a channel independent setting, which is the standard setting
for the model families used.

## What it does not deliver, recorded because the expectation was wrong

**It does not change the model.** Channel independent modelling unrolls each
channel separately and shares one set of weights across all of them, which the
previous univariate evaluation already did. The tensors carry a channel axis so
the interface matches the standard setting, and that axis is folded into the
batch before any parameter sees it.

**It does not raise the fraction of the corpus that curation touched.** The
downstream effects for the conservative methods sit inside a paired noise floor
of 0.27 to 2.99 percent because our method edits 62 of 800 windows and leaves 92
percent of the corpus byte identical. Nothing here changes that ratio.

**An earlier expectation is withdrawn.** It was suggested that a multivariate
evaluation would raise the affected fraction and make the small effects
decidable. That does not follow and is not what this delivers. No experiment is
designed against it and no claim in the paper rests on it.

## The setting, in the three parts that must be reported

### Channel count per block

Blocks do not all have seven channels and the distribution is part of the
setting. At the 800 window scale, seed 42:

| channels per block | blocks |
|---|---|
| 3 | 28 |
| 4 | 47 |
| 5 | 44 |
| 6 | 25 |
| 7 | 6 |

150 blocks, 684 channel series in total, median 4.5 channels, range 3 to 7.

Reporting only that the evaluation is multivariate would let a reader assume
seven channels throughout. It is not, and the table goes with the result.

### Why the groups are incomplete

This is inherent to how the stratified corpus is built, not an implementation
defect. The builder over samples a pool so the hard stratum can be selected by
difficulty rather than constructed, then shuffles the remainder and draws only
what each stratum needs. At the 800 window scale that means 270 base windows are
drawn and 190 are used, so most positions contribute some of their channels and
not all. Requiring seven of seven would discard almost everything, and under
channel independent modelling a block of four aligned channels is as usable as a
block of seven. The floor is three.

### Why the clean out of distribution stratum is absent

Those windows are generated rather than drawn from the data, so they have no
channel siblings. Placing them in a multivariate block would mean inventing
companion channels that never existed. They are excluded from the reassembly by
construction and remain in the curation stage evaluation, where they carry the
characterisation results.

## Main table protocol, fixed before the runs

Once the grouped corpus curation completes there will be two sets of results,
one on the original corpus and one on the grouped corpus. **The main table uses
the grouped corpus. The original corpus is reported as a consistency check.**

If the two disagree materially, both are reported and the difference is
diagnosed. Neither is selected on the basis of which is more favourable. This
is recorded here before the grouped runs execute.

The grouped corpus changes the composition, since the default sampler draws
positions and channels independently, so curation results are not comparable
across the two and must be recomputed rather than reused. That cost is real and
is the reason this protocol is being fixed now rather than after the numbers
arrive.
