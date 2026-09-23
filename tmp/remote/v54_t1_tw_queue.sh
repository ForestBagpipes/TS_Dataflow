#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
PY=/home/vipuser/work2-envs/w2-baseline/bin/python
run_one() {
  s="$1"; lower=$(echo "$s" | tr 'A-Z' 'a-z'); tag="t1-${lower}-full"
  marker="results/v54/replay/external/t1/test__${tag}.npz"
  for attempt in 1 2 3; do
    if [ -f "$marker" ]; then echo "[$(date +%H:%M:%S)] $tag already present"; return 0; fi
    echo "[$(date +%H:%M:%S)] start $tag attempt=$attempt"
    $PY -u scripts/v54_external_t1.py --sources "$s" \
        --blocks train_eval,test,test30,test50 --tag "$tag" \
        > "logs/v54/t1_${tag}.a${attempt}.log" 2>&1
    rc=$?
    if [ -f "$marker" ]; then echo "[$(date +%H:%M:%S)] done $tag attempt=$attempt rc=$rc"; return 0; fi
    echo "[$(date +%H:%M:%S)] FAILED $tag attempt=$attempt rc=$rc; backoff 300s"
    sleep 300
  done
  echo "[$(date +%H:%M:%S)] GAVE UP $tag"
  return 1
}
run_one Weather &
sleep 60
run_one Traffic &
wait
echo "[$(date)] T1_TW_QUEUE_FINISHED"
