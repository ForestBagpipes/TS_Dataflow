# Paper Card: Wen et al. (TS Data Quality)

**arXiv:** NOT FOUND (no arXiv preprint)
**Published:** NeurIPS 2024 Workshop on Time Series in the Age of Large Models (TSALM)
**Authors:** Wen, Songkang; Feofanov, Vasilii; Zhang, Jianfeng
**OpenReview:** https://openreview.net/forum?id=nBtV1A3PrR
**Status:** OpenReview only, no downloadable source found

## Method Summary

"Measuring Pre-training Data Quality without Labels for Time Series Foundation Models" -- the title most similar to ours. Uses contrastive learning-based foundation model and proposes "contrastive accuracy" as an unsupervised quality metric for pretraining data. Evaluates at the dataset level (not per-sample). Experiments show positive correlation between contrastive accuracy and downstream task performance, suggesting it can serve as a criterion to search for high-quality TS datasets.

## Can It Be Our Baseline

No. Dataset-level evaluation (we do per-sample). Requires contrastive pretraining framework. Workshop paper with limited scope.

## What We Learn From It

- Nearly identical title: critical to cite and differentiate from in our Related Work
- First attempt at "data quality without labels for TSFMs" -- validates problem importance
- Dataset-level approach (contrastive accuracy) is complementary to our per-sample approach
- Confirms that quality assessment without labels is a recognized research gap

## Why We Are Better

1. Per-sample granularity (they evaluate entire datasets)
2. No contrastive pretraining required
3. Training-free behavioral introspection (their method requires training contrastive models)
4. Domain confounding handling via peer calibration
5. We use the TSFM itself as oracle (they use external contrastive learning)

## Code

Unknown (workshop paper, no public repo found)

## Reproduction Difficulty

Medium. Requires: contrastive learning framework for TSFMs, downstream task evaluation suite.
