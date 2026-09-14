#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
run=results/v431/20260914-sprint
log=logs/v431/20260914-sprint
date -Is
"$W2_CHRONOS_PY" scripts/v431_baselines/worker.py --request "$run/timesfm/request.json" > "$log/timesfm-worker.log" 2>&1
fixed_status=$?
echo "timesfm_worker_exit=$fixed_status"
if [ "$fixed_status" -eq 0 ]; then
  "$W2_CHRONOS_PY" scripts/v431_baselines/verify_and_score.py "$run/timesfm" > "$log/timesfm-verify.log" 2>&1
  echo "timesfm_verify_exit=$?"
fi
"$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --request "$run/timesfm_tato/request.json" > "$log/timesfm-tato-worker.log" 2>&1
tato_status=$?
echo "timesfm_tato_worker_exit=$tato_status"
if [ "$tato_status" -eq 0 ]; then
  "$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --verify "$run/timesfm_tato" > "$log/timesfm-tato-verify.log" 2>&1
  echo "timesfm_tato_verify_exit=$?"
fi
date -Is
