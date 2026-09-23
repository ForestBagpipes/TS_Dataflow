#!/usr/bin/env bash
# Forecast the PSW-I and T1 repaired contexts with the three frozen backbones,
# then re-run the v55 evaluation so the main table carries all four published
# repair methods.  TimesNet is already scored and is skipped by the marker
# check.  Nothing else on the GPU at this point except the finisher, which is
# waiting for exactly this.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
LOG=logs/v55/baseline_forecast.log
mkdir -p logs/v55
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
say "=== baseline forecast begins ==="
for M in pswi t1; do
  "$W2_CORE_PY" scripts/v54_new_baselines_prepare.py --method "$M" >> "$LOG" 2>&1 \
    && say "prepare $M ok" || say "prepare $M rc=$?"
  for BB in bolt timesfm chronos2; do
    for B in test test30 test50 train_eval; do
      MARK="results/v47/baselines/${M}_${B}_${BB}/records.json"
      [ -f "$MARK" ] && { say "skip $M $B $BB"; continue; }
      say "forecast $M $B $BB"
      "$W2_CHRONOS_PY" -u scripts/v47_baseline_forecast.py --method "$M" \
        --backbone "$BB" --block "$B" --allow-shared-gpu >> "$LOG" 2>&1 \
        && say "ok $M $B $BB" || say "FAIL $M $B $BB rc=$?"
    done
  done
done
say "=== re-evaluating the v55 roster ==="
for BB in bolt timesfm chronos2; do
  ( "$W2_CORE_PY" scripts/v55_evaluate.py --backbone "$BB" \
      > "logs/v55/eval_${BB}.log" 2>&1; say "evaluate $BB rc=$?" ) &
done
wait
say "=== baseline forecast queue done ==="
