#!/usr/bin/env bash
# BRITS / CSDI external-imputer queue, same protocol as scripts/v47_saits_queue.sh.
#
# Every shard takes the project-wide GPU lock only for its own fit, so this
# queue interleaves with the TATO run of the other agent instead of holding
# the device for hours.  Shards are idempotent: a finished (method, mode,
# source) leaves a report file and is skipped on re-entry; the merge joins the
# shards once every source of a (method, mode) is done.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOCK=/home/vipuser/work/work2/locks/gpu.lock
mkdir -p logs/v54

SOURCES="ETTh1 ETTh2 ETTm1 ETTm2 Electricity Exchange Traffic Weather"
METHODS="${V54_METHODS:-BRITS CSDI}"

run_shard() { # method mode source
  local METHOD="$1" MODE="$2" SOURCE="$3"
  local LOWER
  LOWER=$(echo "$METHOD" | tr "A-Z" "a-z")
  local LOG="logs/v54/${LOWER}_${MODE}_${SOURCE}.log"
  local MARKER="results/v54/replay/external/${LOWER}/report_${MODE}-${SOURCE}.json"
  if [ -f "$MARKER" ]; then
    echo "=== [$(date +%H:%M:%S)] SKIP (exists) $MARKER"
    return 0
  fi
  echo "=== [$(date +%H:%M:%S)] WAIT-LOCK $METHOD $MODE $SOURCE" | tee -a "$LOG"
  if flock "$LOCK" "$BASE_PY" -u scripts/v54_external_imputers.py \
       --method "$METHOD" --mode "$MODE" --sources "$SOURCE" \
       --tag "$SOURCE" >> "$LOG" 2>&1; then
    echo "=== [$(date +%H:%M:%S)] OK $METHOD $MODE $SOURCE" | tee -a "$LOG"
    return 0
  fi
  echo "=== [$(date +%H:%M:%S)] FAIL $METHOD $MODE $SOURCE" | tee -a "$LOG"
  return 1
}

merge_mode() { # method mode blocks
  local METHOD="$1" MODE="$2" BLOCKS="$3"
  local LOWER
  LOWER=$(echo "$METHOD" | tr "A-Z" "a-z")
  local LOG="logs/v54/${LOWER}_${MODE}_merge.log"
  for SOURCE in $SOURCES; do
    if [ ! -f "results/v54/replay/external/${LOWER}/report_${MODE}-${SOURCE}.json" ]; then
      echo "=== [$(date +%H:%M:%S)] merge $METHOD $MODE deferred: $SOURCE missing"
      return 1
    fi
  done
  "$BASE_PY" -u scripts/v54_external_merge.py \
      --method "$METHOD" --blocks "$BLOCKS" >> "$LOG" 2>&1 \
    && echo "=== [$(date +%H:%M:%S)] MERGED $METHOD $MODE"
}

nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
for METHOD in $METHODS; do
  for SOURCE in $SOURCES; do
    run_shard "$METHOD" crossfit "$SOURCE"
  done
  merge_mode "$METHOD" crossfit bankx
  for SOURCE in $SOURCES; do
    run_shard "$METHOD" full "$SOURCE"
  done
  merge_mode "$METHOD" full train_eval,test,test30,test50,test_m2,test_m3
done
echo "=== [$(date +%H:%M:%S)] QUEUE DONE"
