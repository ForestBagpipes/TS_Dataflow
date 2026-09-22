#!/usr/bin/env bash
# The imputer stage, sharded by source.
#
# One fit is small and the device is far from full, so four shards of each mode
# finish sooner than one process walking the sources in turn.  Shards hold
# separate locks and write separate archives, and the merge joins them once the
# whole mode is done, which is what the forecast queue waits on.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python

MODE="${1:?mode required}"          # crossfit | full | merge
TAG="${2:-}"
LOG="logs/v47/saits_${MODE}${TAG:+_$TAG}.log"
mkdir -p logs/v47
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

case "$TAG" in
  s1) SOURCES="ETTm1" ;;
  s2) SOURCES="ETTm2" ;;
  s3) SOURCES="Weather,Exchange" ;;
  s4) SOURCES="Electricity,ETTh1,ETTh2,Traffic" ;;
  *)  SOURCES="" ;;
esac

if [ "$MODE" = "merge" ]; then
  say "waiting for every crossfit shard"
  for T in s1 s2 s3 s4; do
    while [ ! -f "results/v47/replay/saits/report_crossfit-$T.json" ]; do sleep 20; done
  done
  "$BASE_PY" -u scripts/v47_saits_merge.py --blocks bankx >> "$LOG" 2>&1
  say "bank archive merged"
  say "waiting for every full shard"
  for T in s1 s2 s3 s4; do
    while [ ! -f "results/v47/replay/saits/report_full-$T.json" ]; do sleep 20; done
  done
  "$BASE_PY" -u scripts/v47_saits_merge.py \
      --blocks test,test30,test50,train_eval,test_m2,test_m3 >> "$LOG" 2>&1
  say "evaluation archives merged"
  exit 0
fi

if [ "$MODE" = "crossfit" ]; then
  BLOCKS="bankx"
else
  BLOCKS="test,test30,test50,train_eval,test_m2,test_m3"
fi

MARKER="results/v47/replay/saits/report_${MODE}-${TAG}.json"
if [ -f "$MARKER" ]; then say "SKIP (exists) $MARKER"; exit 0; fi
say "START $MODE $TAG on $SOURCES"
if "$BASE_PY" -u scripts/v47_saits.py --mode "$MODE" --tag "$TAG" \
     --blocks "$BLOCKS" --sources "$SOURCES" >> "$LOG" 2>&1; then
  say "OK $MODE $TAG"
else
  say "FAIL $MODE $TAG"
fi
