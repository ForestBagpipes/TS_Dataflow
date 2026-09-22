#!/usr/bin/env bash
# v54 frozen protocol: TATO on the mask-repeat blocks test_m2/test_m3.
# Mirrors scripts/v47_tato_queue.sh; the per-backbone search cache
# (results/v47/baselines/tato_search_<bb>.json) is reused, never re-searched.
# Each run first takes locks/gpu.lock (heavy GPU tasks run one at a time).
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
mkdir -p logs/v47
for BB in bolt timesfm chronos2; do
  for B in test_m2 test_m3; do
    MARK="results/v47/baselines/tato_${B}_${BB}/records.json"
    LOG="logs/v47/tato_${BB}_${B}.log"
    if [ -f "$MARK" ]; then echo "=== [$(date +%F_%T)] SKIP $MARK" | tee -a "$LOG"; continue; fi
    echo "=== [$(date +%F_%T)] START tato $BB $B runner_pid=$$" | tee -a "$LOG"
    nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader >> "$LOG" 2>&1
    if flock locks/gpu.lock "$W2_CHRONOS_PY" -u scripts/v47_tato.py \
        --backbone "$BB" --block "$B" \
        --trials 48 --windows 8 --deadline-minutes 40 >> "$LOG" 2>&1; then
      echo "=== [$(date +%F_%T)] OK tato $BB $B" | tee -a "$LOG"
    else
      echo "=== [$(date +%F_%T)] FAIL tato $BB $B" | tee -a "$LOG"
    fi
  done
done
echo "=== [$(date +%F_%T)] v54 TATO m2/m3 queue ends"
