#!/usr/bin/env bash
# BRITS / CSDI external-imputer queue, same protocol as scripts/v47_saits_queue.sh.
#
# Every task takes the project-wide GPU lock before touching the device, so
# this queue serialises against the TATO run of the other agent instead of
# racing it.  Tasks are idempotent: a finished (mode, method) pair leaves a
# report file and is skipped on re-entry.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOCK=/home/vipuser/work/work2/locks/gpu.lock
mkdir -p logs/v54

run() { # method mode
  local METHOD="$1" MODE="$2"
  local LOWER
  LOWER=$(echo "$METHOD" | tr "A-Z" "a-z")
  local LOG="logs/v54/${LOWER}_${MODE}.log"
  local MARKER="results/v54/replay/external/${LOWER}/report_${MODE}.json"
  if [ -f "$MARKER" ]; then
    echo "=== [$(date +%H:%M:%S)] SKIP (exists) $MARKER" | tee -a "$LOG"
    return 0
  fi
  echo "=== [$(date +%H:%M:%S)] WAIT-LOCK $METHOD $MODE" | tee -a "$LOG"
  if flock "$LOCK" "$BASE_PY" -u scripts/v54_external_imputers.py \
       --method "$METHOD" --mode "$MODE" >> "$LOG" 2>&1; then
    echo "=== [$(date +%H:%M:%S)] OK $METHOD $MODE" | tee -a "$LOG"
  else
    echo "=== [$(date +%H:%M:%S)] FAIL $METHOD $MODE" | tee -a "$LOG"
  fi
}

nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
for METHOD in BRITS CSDI; do
  run "$METHOD" crossfit
  run "$METHOD" full
done
echo "=== [$(date +%H:%M:%S)] QUEUE DONE"
