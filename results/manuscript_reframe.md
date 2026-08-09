# C  manuscript aligned to the agent framing

Positioning text only. No experimental section was touched and no number was
filled in. Terminology is taken from the existing handoff and code documents,
nothing new was coined, and no borrowed method is named in the prose.

## What changed, and why

| file | what changed | why |
|---|---|---|
| `en/introspect_ts-20260609.tex` | title, abstract, gap statement, problem statement, method paragraph, contributions | every one of these argued a training free scorer. none of them mentioned the action space, the sandbox, the re probe, the structural veto, the rollback, or the refusal path |
| `zh/introspect_ts_zh-20260609.tex` | same six, in both the English and Chinese abstracts | same |
| `work2_summary.md` | status banner at the top | 603 lines of scorer era planning. it is an accurate record of how the work got here and rewriting it would destroy that, so it is marked rather than revised |
| `research_brief_ts_dataflow.md` | status banner at the top | same, 1029 lines |

## The substantive edits

**Title.** From a training free data quality assessment method via behavioural
introspection, to an intervention verified and reversible data curation agent.

**Gap statement.** The old text claimed no prior work achieves per sample
quality assessment from the model's own behavioural signals. That is a claim
about scoring and it is no longer what separates this work. Replaced with the
claim that no prior work verifies a curation action after performing it and
reverses it when the verification fails.

**Problem statement.** The old three sub problems were signal collection,
domain confounding, and validating that scores improve downstream training.
Replaced with the three the agent actually faces: separating a defect from a
hard but faithful pattern, establishing that an edit helped the target model,
and guarding against edits that lower prediction error by destroying something
real.

**Method paragraph.** The old four phase pipeline ended at stratification and
downstream fine tuning. Replaced with the perceive, act, verify, roll back loop,
including the invariant that the working copy is only ever replaced by a
candidate that passed, which is what makes any prefix of a trace replayable.

**Contributions.** From three, all about scoring and its justification, to
four: the problem formulation as sequential decision making, the agent itself,
the dual verification rule with the structural term identified as what stops
error lowering damage, and the stratified evaluation that reports repair and
over cleaning separately.

## What was deliberately left alone

The related work section, the problem definition section, the method sections
past the introduction, and everything experimental. Those need the results from
the next GPU batch before they can be rewritten honestly, and several of them
describe machinery that still exists and still works, in particular the
statistical profile and the peer calibration, which became the perception layer
of the agent rather than being discarded.

The file names still read `introspect_ts`. Renaming them touches the build and
buys nothing until the rest of the manuscript is rewritten, so it is left for
the same pass.

## Punctuation check

Ran over the positioning span of both manuscripts, from the title to the
related work heading, and over both banners.

| file | em dash | en dash | curly quotes | semicolons |
|---|---|---|---|---|
| `en/introspect_ts-20260609.tex` | 0 | 0 | 0 | 0 |
| `zh/introspect_ts_zh-20260609.tex` | 0 | 0 | 0 | 0 |
| `work2_summary.md` banner | 0 | 0 | 0 | 0 |
| `research_brief_ts_dataflow.md` banner | 0 | 0 | 0 | 0 |

Five occurrences in text that was kept rather than rewritten also had to be
fixed, since they sat inside the same span. Four em dashes and one pair of
curly quotes, each replaced with wording that carries the same meaning.

`polish_check` does not exist in this environment. The counts above were
produced by direct search over the spans.
