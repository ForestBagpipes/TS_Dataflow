# Behavioural risk by stratum

From the 2000 window run with real TSFMs. Behavioural risk is the
peer calibrated quantity the policy conditions on. The statistical
column is the control: if it showed the same inversion the finding
would be about the corpus rather than about model behaviour.

| stratum | n | p05 | p25 | median | p75 | p95 | statistical median |
|---|---|---|---|---|---|---|---|
| contaminated | 740 | -0.386 | -0.142 | **+0.063** | +0.368 | +0.958 | 5.134 |
| clean | 420 | -0.437 | -0.202 | **+0.020** | +0.307 | +0.946 | 1.876 |
| hard | 210 | -0.340 | -0.134 | **+0.044** | +0.324 | +0.951 | 2.253 |
| rare_valid | 210 | -0.369 | -0.131 | **+0.108** | +0.417 | +1.201 | 0.849 |
| changepoint | 210 | -0.351 | -0.085 | **+0.071** | +0.351 | +0.778 | 1.144 |
| clean_ood | 210 | -0.247 | +0.114 | **+0.473** | +3.815 | +12.179 | 3.410 |

## Each protected stratum against the contaminated one

`auc` is the probability that a window from this stratum scores higher
than a contaminated one. Above 0.5 means the protected stratum alarms
the model more than actual contamination does.

| stratum | behaviour auc | z | p | statistics auc | p |
|---|---|---|---|---|---|
| clean | **0.460** | -2.3 | 2.31e-02 | 0.322 | 4.78e-24 |
| hard | **0.497** | -0.1 | 8.87e-01 | 0.344 | 5.51e-12 |
| rare_valid | **0.534** | +1.5 | 1.30e-01 | 0.263 | 1.08e-25 |
| changepoint | **0.515** | +0.7 | 5.13e-01 | 0.238 | 4.14e-31 |
| clean_ood | **0.726** | +10.0 | 1.27e-23 | 0.482 | 4.18e-01 |

Strata that alarm the model significantly more than contamination does: clean_ood.

Same question for the statistical profile: none.

