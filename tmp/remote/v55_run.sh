#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
LOG=logs/v55/run.log
mkdir -p logs/v55
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
say "=== v55 run begins ==="
for bb in bolt timesfm chronos2; do
  $W2_CORE_PY scripts/v55_conformal.py --backbone "$bb" > "logs/v55/conformal_$bb.log" 2>&1
  say "conformal $bb rc=$?"
done
for bb in bolt timesfm chronos2; do
  ( $W2_CORE_PY scripts/v55_evaluate.py --backbone "$bb" > "logs/v55/eval_$bb.log" 2>&1
    say "evaluate $bb rc=$?" ) &
done
wait
say "=== v55 run done ==="
