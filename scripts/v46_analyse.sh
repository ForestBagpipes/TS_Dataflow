#!/usr/bin/env bash
# Runs the CPU analysis of each backbone as soon as its forecasts land.
# Idempotent: a stage whose output exists is skipped, so the loop can restart.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 02:18" +%s)
LOG=logs/v46/analyse.log
mkdir -p logs/v46 results/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
step() {
  local marker="$1"; shift
  [ -f "$marker" ] && return 0
  say "RUN $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; fi
}
say "analysis watcher begins"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  for BB in bolt timesfm chronos2; do
    if [ -f "results/v46/replay/forecast/bank/$BB/status.json" ]; then
      step "results/v46/protocol/selection_$BB.json" "$W2_CORE_PY" -u scripts/v46_select.py --backbone "$BB"
    fi
    if [ -f "results/v46/replay/forecast/test/$BB/status.json" ] && [ -f "results/v46/protocol/selection_$BB.json" ]; then
      step "results/v46/evaluation/test_$BB.json" "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block test
      step "results/v46/diagnostics/reconstruction_test_$BB.json" "$W2_CORE_PY" -u scripts/v46_reconstruction.py --backbone "$BB" --block test
    fi
    if [ -f "results/v46/replay/forecast/train_eval/$BB/status.json" ] && [ -f "results/v46/protocol/selection_$BB.json" ]; then
      step "results/v46/evaluation/train_eval_$BB.json" "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block train_eval
    fi
    for SEV in test30 test50; do
      if [ -f "results/v46/replay/forecast/$SEV/$BB/status.json" ] && [ -f "results/v46/protocol/selection_$BB.json" ]; then
        step "results/v46/evaluation/${SEV}_$BB.json" "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block "$SEV"
      fi
    done
  done
  sleep 25
done
say "analysis watcher ends"
