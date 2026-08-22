# The post 2025 baseline gap, assessment before any implementation

Written 2026-08-22. Nothing here has been run. Every claim about a repository is
from reading that repository, and every venue claim is from the paper's own
metadata, both quoted below so they can be rechecked.

## The gap, confirmed

The requirement is at least two baselines formally published in 2025 or later.
Reading the bibliography of the 0821 document:

| ref | work | venue as cited | counts |
|---|---|---|---|
| [11] | TimeInf | The Thirteenth ICLR, so ICLR 2025 | yes |
| [12] | TSRating | The Fourteenth ICLR, so ICLR 2026 | yes, at risk |
| [13] | AegisTS | `arXiv preprint, EB/OL` | **no** |
| [5] [6] [8] | SCREEN, IMR, MTCSC | 2015 to 2024 | no |
| [9] [10] | Data Shapley, Data-OOB | ICML 2019, ICML 2023 | no |

So the count is two, and one of them is the one at risk of deferral. If TSRating
defers on 8-25 the count falls to one and the requirement is not met. AegisTS is
still a preprint at v5 dated 2026-08-05, checked today, so it cannot be counted
even though it is the closest work to ours in spirit.

## Line one, TSRating, what the repository actually provides

From `github.com/clsr1008/TSRating`.

| stage | file | what it needs |
|---|---|---|
| pairwise judgment | `prompting/run_score_pairwise.py` | an LLM, `--model gpt-4o-mini`, `--generations 20` |
| single rater | `scoring/train_rater.py` | the judgments from the stage above |
| meta rater | `meta_rater/meta_main.py` | the same |
| apply to a corpus | `scoring/annotate.py` | a trained rater |

Four quality dimensions, trend, frequency, amplitude and pattern.
Python 3.11 with torch 2.1.2. There is no run script, parameters live in each
file's `__main__` block.

Two facts decide the route.

**No rater checkpoint is released.** The repository ships no trained weights.

**No annotations are released.** The README states that due to storage limits
the intermediate files have not been uploaded, and tells the user to organise
their own.

### The scorer only path is closed, not merely expensive

Reproducing only the rater and skipping the LLM was one of the two routes named.
It is not available. The rater has no existence independent of the judgments,
it is defined as a distillation of them, and neither the judgments nor a trained
rater is published. There is nothing for the scorer to be trained on. This is a
fact about what was released, not a judgment about effort.

### The backend substitution path is viable, with two blockers

Substituting the judgment backend is mechanically easy, the model is passed as
`--model` and DeepSeek exposes an OpenAI compatible API, so the call site does
not change. Two blockers are real.

**The node cannot reach GitHub.** `curl` to the repository returns 000 from the
GPU node, checked today. The mirror route that works for weights does not cover
source repositories. The repository has to be cloned on the workstation and
copied across, which is a step rather than an obstacle.

**Annotation cost is unmeasured.** Twenty generations per pairwise comparison
across four dimensions, over a corpus of 800 to 2000 windows. The number of
pairs per dimension is set inside `score_pairwise.py`, which the repository
invokes by subprocess, so it cannot be read off the launcher.

### Recommended shape, a capped pilot

Clone locally, copy across, substitute the backend, and run the annotation stage
on **a 100 window subset at all four dimensions**. That measures the two unknowns
that matter, tokens per window and wall clock per window, at a cost that is
bounded before it is spent. The full corpus is committed to only if the pilot
says it is affordable. If the pilot has not completed by 8-25, TSRating is
marked deferred as agreed, and line two carries the requirement alone.

## Line two, candidates published 2025 or later

Searched arXiv metadata for time series data selection, valuation, curation,
cleaning, pruning and coreset work, filtered to entries whose own
`journal_ref` or comment names a venue.

| candidate | venue, from its own metadata | family | code | fits our setting |
|---|---|---|---|---|
| **TimeLAVA** | `journal_ref: ICML2026` | valuation | none found | segments map to our 512 point windows, learning agnostic so no retraining |
| LTSV | `Accepted as a full paper at DASFAA 2026` | valuation on TSFMs | none found | in context finetuning on a TSFM plus block aggregation |
| Temporal-Decay Shapley | none | valuation | none found | yes |
| Channel Matters | `Accepted by Neurips 2025` | channel influence | none found | **no**, it estimates per channel influence and we curate one channel at a time |
| Optimizing the Training Diet | `Accepted ACM SAC 2026` | data mixture | none found | mixture search over sources, not per window |
| AegisTS | preprint | cleaning by RL | repository is missing its `Datasets` package | multivariate only |

### The recommendation, and the risk attached to it

**TimeLAVA, ICML 2026.** It is the only candidate that is both in a venue of the
required class and in a family the paper already compares against, so it slots
into `docs/valuation_family_protocol.md` without changing a rule: the same window
score aggregation, the same two selection fractions, the same protected stratum
retention metric. Being learning agnostic it needs no model training, which makes
it cheap and which strengthens rather than muddies the computational cost column
that A3 keeps in the main table.

The risk is that **no code was found**, not on arXiv, not on OpenReview. A
faithful reimplementation has to reproduce a Selective Wavelet based Wasserstein
discrepancy, an unbalanced optimal transport step, and a sensitivity analysis
value computation, from a 34 page paper. That is exactly the situation
`docs/valuation_family_protocol.md` avoided when it chose to run TSRating's own
baseline file rather than rewrite four methods from their papers, on the grounds
that a comparison against our reading of a method is not a comparison against the
method.

So if TimeLAVA is implemented here it is labelled in every table as our
reimplementation, with the approximated components named. That is weaker than a
published implementation and it is stated rather than hidden.

**LTSV is the first fallback, revised 2026-08-22.** The venue objection is
withdrawn: DASFAA is a formally published database conference and a full paper
there carries proper review, so it is not excluded. Fidelity is the deciding
axis rather than venue prominence, and on that axis LTSV wins. Its method is
close to machinery this paper already has, and its feasibility has now been
tested rather than guessed, see `docs/ltsv_feasibility.md`. TimeLAVA drops to
third choice.

### Sequencing, cheapest first

The two lines are alternatives rather than additions. If the TSRating pilot
succeeds the count is two and no new baseline is required. The pilot costs hours.
If it fails, LTSV is implemented, at an estimated two and a half days with the
pivotal risk already retired. TimeLAVA is third and is committed to only if both
of the first two fall through, and if it is used it is labelled in every table as
this paper's reimplementation with the approximated components named.

## Where a new baseline has to appear

Whatever is added goes into table 1 of the introduction and into the matching
subsection of chapter 1, so that every baseline in chapter 4 has been surveyed in
chapter 1. TimeLAVA and LTSV both belong in 1.2, the data valuation and sample
selection subsection, alongside TimeInf and TSRating.
