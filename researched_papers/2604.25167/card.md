# Paper Card: IGDS (Interpretability-Guided Data Selection)

**arXiv:** 2604.25167
**Published:** NeurIPS 2026 (inferred from booktitle)
**Authors:** Shi, Ling et al. (Tianjin University + Alibaba Group)
**Status:** 已下载 e-print source (2.1MB tar.gz)

## Method Summary

First framework to bridge mechanistic interpretability insights to practical data selection for LLMs. Stage 1: SAE features are extracted from LLM internals. High-frequency recall filters candidate features. Causal intervention filtering validates features by amplifying each and measuring performance gain (Delta metric). Stage 2: Feature-Resonant Score (FRS) sums activations of validated task features on candidate data points. Top-K data by FRS is selected for fine-tuning. Results: 50% data surpasses full-data fine-tuning by 17.4% on Math task (Gemma-2-2B). Validated on Math, Summarization, Translation across Gemma-2, LLaMA-3.1, Qwen3.

## Can It Be Our Baseline

No. Requires SAE training or access (currently available for few LLM architectures). LLM domain only.

## What We Learn From It

- Core paradigm: "model-internal signals guide data decisions" -- our primary conceptual alignment
- Causal validation of features via intervention experiments (Delta metric)
- Feature-Resonant Score as a principled data utility function
- Demonstrates that model introspection yields actionable data curation signals
- Strong results validate the introspection-to-action paradigm

## Why We Are Better

1. TSFM domain first (IGDS is LLM-only, no TSFM application exists)
2. Zero auxiliary model training (IGDS requires SAE training or pre-trained SAE access)
3. Training-free (IGDS requires feature identification phase with interventions)
4. Domain confounding handling via peer calibration (IGDS does not address)
5. Simpler deployment: one forward pass vs. SAE training + feature search + intervention

## Code

Not publicly available (as of search)

## Reproduction Difficulty

Extremely High. Requires: SAE training for target LLM (or access to pre-trained SAEs like Gemma-Scope), causal intervention experiments, feature search pipeline. For TSFMs there are no pre-trained SAEs.
