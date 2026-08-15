# Execution time calibrated gating for agent actions

Four papers that place a calibrated gate between a proposer and its effects.
They are the closest neighbours to this work in mechanism and the furthest in
premise, which is what the cards below are for.

## Timing, against a submission date of 2026-09-24

| paper | venue or arXiv | first public | status |
|---|---|---|---|
| AgentSpec | ICSE 2026, arXiv 2503.18666 | 2025-03 | prior work, closest architectural precedent |
| CORA | 2604.09155 | 2026-04-10 | prior work, must be cited and discussed |
| Conformal Selective Acting | 2605.20270 | 2026-05-18 | prior work, must be cited and discussed |
| Proof-Carrying Agent Actions | 2606.04104 | 2026-06-02 | prior work, must be cited and discussed |
| Role-Stratified CRC for Tool Calls | 2607.24343 | 2026-07-27, rev 07-31 | concurrent, may be treated as such |

AgentSpec predates submission by well over a year. The next three predate it by five, four and nearly four months. They
are prior work by any reading and are discussed as such. The fourth is public
two months before submission, which falls inside the window where concurrent
treatment is customary, and it is still distinguished explicitly in one
sentence rather than left to the reader.

## Why no experimental comparison is run

**No shared platform exists.** These five operate on mobile GUI action traces,
on RLVR training rounds, on cross runtime agent execution records, and on tool
call arguments. Their corpora, their action spaces and their definitions of
harm do not overlap with a time series curation corpus, injected defect types
and an edit that damages a window. Constructing a common benchmark would mean
inventing one, and any number produced on it would measure the benchmark rather
than the methods.

**The comparison that does need numbers is a different one.** The sequential
curation system discussed in related work shares the data, ETT, and the task,
cleaning time series, so a controlled comparison there is both possible and
required. That is where the experimental effort goes. See
`researched_papers/aegists/`.

So these five are separated conceptually, not numerically, and the section says
so rather than leaving the absence unexplained.

## The single distinguishing sentence

These works assume the risk signal is a reasonable proxy for harm, and what
they calibrate or enforce is a signal taken to be reliable. We show that in data curation the most
natural verifier, model utility, is anti correlated with harm over a
characterisable region: it rewards the destruction of information. Calibrating
a single such signal is therefore not sufficient for safety.
