# Paper Card: LTSV

**arXiv:** 2511.11648
**Published:** arXiv preprint, 2025
**Authors:** Wu, Shunyu et al. (Sun Yat-Sen University + NUS)
**Status:** 已下载 e-print source (3.8MB tar.gz)

## Method Summary

Lightweight Time Series Data Valuation for TSFMs via in-context finetuning. Approximates classical influence functions without Hessian computation by performing one-step in-context finetuning and measuring context loss change. Temporal block aggregation preserves temporal dependencies across overlapping windows. Provides per-sample valuation scores indicating training contribution. Evaluated on 5 datasets, 3 TSFM architectures, showing generalization of valuations to diverse downstream models (DLinear, PatchTST, PAttn).

## Can It Be Our Baseline

No. Data valuation (measuring training impact of samples) is different from data quality assessment (measuring intrinsic quality of samples). Complementary problems.

## What We Learn From It

- In-context finetuning as an efficient approximation to influence functions
- Per-sample contribution scoring paradigm (similar ambition to per-sample quality scoring)
- Computational efficiency concern: traditional influence functions O(nP^2+P^3) vs. their O(nP)
- TSFM-aware approach (uses TSFM itself rather than external evaluator, similar philosophy)

## Why We Are Better

1. We assess intrinsic quality, not training impact (different but equally important problem)
2. We require ZERO finetuning steps (LTSV needs one in-context finetuning step per sample)
3. We handle domain confounding (LTSV valuation may be domain-biased)
4. Multi-signal behavioral probes vs. single loss-change metric
5. Computational cost: our O(N) forward-only vs. LTSV's O(N) forward+backward

## Code

https://github.com/b1302550313/LTSV

## Reproduction Difficulty

Medium. Requires: in-context finetuning implementation, temporal block aggregation, multiple TSFM backbones.
