# E  naming and manuscript equals source inventory

Inventory only. Nothing was changed this round.

The pivot is larger than a rename. The old claim was a training free scorer
that assigns per sample quality. The new claim is an agent that acts, verifies
the action against a frozen model and rolls it back when the evidence does not
hold. Anything written for the first claim has to be re examined for the
second, not just have its name substituted.

## Where each artefact currently stands

| artefact | current name or framing | aligned with IntroAct-TS agent | note |
|---|---|---|---|
| `src/introact_ts/` | IntroAct-TS | yes | renamed in the first session of the rebuild |
| `docs/code_overview.md` | IntroAct-TS agent | yes | written against the agent framing |
| `docs/HANDOFF.md` | IntroAct-TS agent | yes | |
| `experiments/`, `tests/` | IntroAct-TS | yes | no stale imports remain |
| `en/introspect_ts-20260609.tex` | IntroSpect-TS scorer | **no** | title, abstract, contributions all argue a scorer |
| `zh/introspect_ts_zh-20260609.tex` | IntroSpect-TS scorer | **no** | same |
| `en/introspect_ts-20260609.pdf` | IntroSpect-TS scorer | **no** | build artefact of the above |
| `work2_summary.md` | IntroSpect-TS scorer | **no** | predates the pivot |
| `research_brief_ts_dataflow.md` | dataflow, scorer era | **no** | predates the pivot |
| `researched_papers/*/card.md` | scorer | **no** | see below, this is the substantive one |

## The manuscript is not merely misnamed

The abstract of `en/introspect_ts-20260609.tex` states the contribution as a
training free method that extracts data quality signals from a frozen TSFM and
produces quality scores, validated by downstream fine tuning. Every element of
the current method that carries the argument is absent from it: the action
space, the sandbox, the post intervention re probe, the structural veto, the
rollback, the refusal path, and the protected strata. The contributions list
names IntroSpect-TS as the first behavioural introspection method for quality
assessment. That is a claim about scoring.

Rewriting the title is the smallest part of this. The gap analysis, the
positioning against prior work, and the experimental section all argue for a
scorer.

## The competitor cards need re judging, not renaming

All six cards frame our contribution as scalar per sample quality scoring, and
the accept or reject decision for each as a baseline was made on that basis.
Two of those decisions look wrong under the agent framing.

| card | current verdict | why it needs revisiting |
|---|---|---|
| `2606.03629` TSQAgent | not a baseline, because it is an agentic framework and we do scalar scoring | under the new framing this is the closest prior work, an agentic data quality framework for time series. The stated reason for excluding it is exactly what we now are. It has to become a discussed competitor, and its reported finding that LLMs struggle with evidence grounded quality comparison is a point our design can be positioned against |
| `2605.26161` TSRating | LLM judge plus trained meta scorer, expensive | still not the same problem, but it is the obvious learned baseline a reviewer will ask for. Whether it runs at all is an open question from the scorer era that was never settled |
| remaining four | assorted | verdicts rest on the scoring framing and should be re read, though none looks as directly affected as the two above |

## What this implies for the work order

The rename is cheap. The re argument is not, and it is on the critical path for
the paper rather than the code. Doing it before the next GPU batch would be
premature, because the experiment list from that batch, in particular the
contamination sweep and the cross model transfer, determines what the
contribution section can claim. Doing it after is fine as long as it is not
left until the week of the deadline.
