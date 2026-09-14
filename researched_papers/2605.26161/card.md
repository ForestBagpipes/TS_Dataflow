# Paper Card: TSFMAudit

**arXiv:** 2605.26161
**Published:** arXiv preprint, May 2026
**Authors:** Li, Hongkai et al. (Zhejiang University)
**Status:** 已下载 e-print source (225KB tar.gz)

## Method Summary

First systematic study of pretraining contamination auditing for TSFMs. Core signal: probe-time adaptation dynamics (loss reduction rate + parameter displacement during fine-tuning probes). Reference-based debiasing: candidate model behavior is compared against reference models (ScratchCNN, ScratchTransformer, Stat, VisionTS) via difference and ratio features. Logistic regression scorer aggregates debiased features into contamination risk score. Evaluated on 6 TSFMs and 187 datasets against 10 baselines.

## Can It Be Our Baseline

Partially. Uses similar probe-time behavioral dynamics signals but for a different problem (contamination detection, not quality assessment). Requires probe fine-tuning and reference models.

## What We Learn From It

- Adaptation dynamics (loss reduction + parameter movement) as behavioral evidence of model-data relationship
- Reference-based debiasing mirrors our peer calibration concept
- Confirms that "static loss alone is unreliable" for TS (same insight we use for quality confounding)
- Dataset difficulty can bias behavioral signals (same domain confounding problem)

## Why We Are Better

1. We do NOT need probe fine-tuning (zero training vs. T_probe epochs)
2. We do NOT need reference models (ScratchCNN, Stat, etc.)
3. Our peer calibration is lighter (KNN on profile space vs. training+inference on references)
4. We target quality assessment (more general) vs. contamination auditing (narrower)
5. Single forward pass per sample vs. full fine-tuning probe

## Code

https://github.com/kkevin117/TSFMAudit

## Reproduction Difficulty

Medium-High. Requires: 4 reference models, probe fine-tuning protocol, logistic scorer fitting, FP-0 calibration.
