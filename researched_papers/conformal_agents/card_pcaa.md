# Proof carrying agent actions, model agnostic runtime governance

arXiv 2606.04104, first public 2026-06-02. Wang. **Prior work relative to a
2026-09-24 submission.**

## What it does

A runtime neutral governance model for heterogeneous agent systems, organised
around action certificates rather than vendor specific logs. A certificate
records what action was authorised, under whose authority, with what approval
semantics, and with what evidence after execution. Five checkpoints structure
the control: pre action admissibility, action open, assumption capture,
approval, and outcome closure. Approval uses explicit enforceability classes
rather than a single reviewed or unreviewed bit.

Reference implementation on a benchmark expanded from 24 executable seeds to 96
traces across four runtime families.

## What it shares with this work

The record. Our governance trace serves the same purpose: it captures what was
proposed, what the conditions evaluated to, what was committed and what was
rolled back, so that a curation run can be audited and replayed after the fact.
We verified replay reproduces every method to zero absolute error, which is the
same property their receipts are for.

Pre action admissibility is also our acceptance rule by another name, and
outcome closure is our rollback.

## Where it differs

**It governs authorisation, not correctness.** The certificate answers who
permitted this and on what basis. It does not answer whether the action was the
right one, and it does not need to, because in their setting the authority is
external and human.

Our problem has no external authority. Nobody can label two thousand windows,
which is why the verifier is a model, and the whole difficulty is that the
verifier is wrong in a specific direction. Their framework would faithfully
record a certificate for each of the ten edits that destroyed ninety six
percent of a window's variance, because each was properly authorised by the
rule in force.

**Consequence.** Their contribution is portability of the record across
runtimes. Ours is the content of the admissibility check itself, and
specifically that it cannot rest on the verifier alone. The two are compatible
rather than competing: a governance trace is the right substrate, and what
belongs inside the pre action check is what we study.
