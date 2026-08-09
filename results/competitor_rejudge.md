# B  competitor cards re judged against the agent framing

Inventory and re judgement. The cards themselves were not edited this round.

Every existing verdict was written when the contribution was a training free
scorer producing a scalar per sample quality value. The contribution is now an
agent that proposes an edit, applies it to a sandbox copy, re probes a frozen
model, and commits or rolls back. Several verdicts turn on the old framing and
one of them now argues the opposite of what it should.

## Old verdict against new

| card | old verdict | new verdict | why it changes |
|---|---|---|---|
| **TSQAgent** `2606.03629` | not a baseline, because it is an agentic framework while we do scalar per sample scoring | **closest prior work. discuss in detail, and the reproduction candidate if any is** | the stated ground for exclusion is now a description of us. an agentic framework for time series data quality is the same family, and a reviewer looking for our nearest neighbour will land here first |
| **TSRating** `2506.01290` | not a baseline, needs LLM API plus MAML plus scorer training, orthogonal to training free | **the scorer representative, and the baseline a reviewer will ask for by name** | orthogonality was an argument between two scorers. against an agent it is the natural stand in for the whole score and select family, which is what `quality_rank` currently approximates with a much weaker proxy |
| **TSFMAudit** `2605.26161` | partially, similar probe time dynamics for contamination detection | **unchanged as a baseline, promoted as prior art for the probe** | it already shares the probe time behavioural signal. under the agent framing it becomes the closest thing to our perception layer, so it belongs in the method related work rather than only in the quality section |
| **LTSV** `2511.11648` | not a baseline, valuation rather than quality | **unchanged** | valuation scores a sample's training impact. neither scoring nor acting on individual windows. the distinction survives the pivot |
| **IGDS** `2604.25167` | not a baseline, needs SAE access, LLM only | **unchanged** | still LLM only and still needs SAE access. relevant as the introspection precedent we borrow the idea of internal signals from, which the pivot does not alter |
| **Wen et al.** `wen2024_neuripsws` | not a baseline, dataset level, contrastive pretraining | **unchanged** | dataset level rather than per window. the pivot does not close that gap |

## What actually moved

Two of six. The other four were rejected for reasons that hold under either
framing, which is worth stating plainly rather than manufacturing changes.

The TSQAgent reversal is the substantive one. Its own reported finding, that
current LLMs struggle with both dimension identification and evidence grounded
quality comparison for time series, is now a point our design answers rather
than a curiosity: we do not ask a language model to judge a series, we ask the
target model to react to it and we verify the reaction against a structural
constraint. That is a positioning argument the paper can make only under the
agent framing.

The TSRating promotion changes what the next GPU batch has to contain. The
current learned baseline stand in is `quality_rank`, which ranks by our own
peer calibrated behavioural risk and then cleans the worst quarter wholesale.
That is a strawman built from our own machinery. A reviewer will want the
comparison against a published scorer.

## Consequences for the next GPU batch

1. **TSQAgent as a discussed competitor at minimum.** Whether it can be run at
   all is unresolved. It needs LLM API access, which is a cost and dependency
   decision, not a technical one. If it cannot be run, the paper needs a
   written positioning argument against it, and that argument is stronger under
   the agent framing than it would have been under the scorer framing.
2. **TSRating as the learned scorer baseline.** Also unresolved since the
   scorer era. Needs LLM API plus MAML training plus a trained TSRater. Decide
   run or do not run before the batch, because if it runs it needs a slot in
   the same corpus and the same seeds.
3. **TSFMAudit as prior art for the perception layer**, cited rather than run.
   No experiment implied.

Neither of the two runnable questions is settled by anything on disk. Both are
marked deferred until the API and cost decision is made.
