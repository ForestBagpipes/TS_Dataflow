# Paper Card: TSRating

**arXiv:** 2506.01290
**Published:** ICLR 2026 (full paper)
**Status:** 已下载 e-print source (8.6MB tar.gz)

## Method Summary

TSRating uses LLMs (GPT-4o) as quality judges for time series data chunks across four evaluation dimensions: trend, frequency, amplitude, and pattern. LLM performs pairwise comparison of time series chunks, then Bradley-Terry MLE converts pairwise preferences into scalar scores. A lightweight TSRater (MOMENT encoder + 3-layer MLP) is trained via meta-learning (MAML with signSGD) to distill LLM judgments, enabling efficient inference on new domains. Meta-training across 9 domains with 22 data subsets from Time-300B corpus.

## Can It Be Our Baseline

No. Requires LLM API access + MAML training + TSRater scorer training. Orthogonal methodology to our training-free approach.

## What We Learn From It

- LLM-based TS quality assessment IS viable and IS publishable at ICLR (validates venue fit)
- Pairwise comparison is more stable than absolute scoring
- Bradley-Terry model provides principled scalar conversion
- Meta-learning is one path to cross-domain generalization

## Why We Are Better

1. Zero LLM API calls (TSRating requires GPT-4o for annotation + inference)
2. Zero training (TSRating needs MAML + TSRater training)
3. Domain confounding handling via peer calibration (TSRating does not address "hard vs dirty")
4. Single TSFM forward pass per sample vs. LLM API round-trips
5. Truly training-free: no MOMENT encoder, no MLP, no MAML

## Code

https://github.com/clsr1008/TSRating

## Reproduction Difficulty

High. Requires: GPT-4o API access, Time-300B corpus, MAML training infrastructure, MOMENT encoder.
