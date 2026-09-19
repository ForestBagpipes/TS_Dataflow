#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
LOG=logs/v46/rerun.log
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
say "evaluation rerun with the opportunity strata"
for BB in bolt timesfm chronos2; do
  for B in test test30 test50 train_eval; do
    if "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block "$B" >> "$LOG" 2>&1; then
      say "OK $BB $B"
    else
      say "FAIL $BB $B"
    fi
  done
done
say "rerun ends"
