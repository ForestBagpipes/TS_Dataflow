# Paper Card: TSQAgent

**arXiv:** 2606.03629
**Published:** arXiv preprint, June 2026
**Status:** 已下载 e-print source (3.7MB tar.gz)

## Method Summary

TSQAgent proposes an agentic reasoning framework for time series data quality assessment. Three collaborative roles: (1) Perceiver builds understanding of input pair and selects relevant quality dimensions, (2) dimension-specific analyzers perform evidence-grounded comparison, (3) aggregator produces final quality rating. Key finding: current LLMs "consistently struggle with both dimension identification and evidence-grounded quality comparison" for time series data.

## Can It Be Our Baseline

No. Agentic framework targeting dimension identification + pairwise comparison. Different problem formulation from our scalar per-sample quality scoring.

## What We Learn From It

- Core finding supports our thesis: LLMs are unreliable for direct TS quality assessment
- Validates our decision NOT to use LLM-as-judge approach
- Provides empirical evidence to cite when arguing against LLM-centric approaches

## Why We Are Better

1. We bypass the LLM reliability problem entirely (TSFM introspection, not LLM-as-judge)
2. Zero LLM API calls
3. Per-sample scalar scores vs. agentic pairwise comparison
4. Domain confounding handling

## Code

Unknown (paper references github.com/b1302550313/TSQAgent but unconfirmed)

## Reproduction Difficulty

Medium. Requires: LLM API, agentic framework setup, quality dimension definitions.
