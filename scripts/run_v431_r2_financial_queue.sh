#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
run=results/v431-r2/financial-observation-index-r1
date -Is
for batch in timesfm timesfm-history tato; do
  "$W2_CHRONOS_PY" scripts/v431_baselines/worker.py --request "$run/$batch/request.json" > "logs/v431-r2/financial-$batch.log" 2>&1
  result=$?
  echo "$batch exit=$result"
  if [ "$result" -ne 0 ]; then exit "$result"; fi
done
"$W2_CHRONOS_PY" scripts/v431_baselines/timesfm_tato_worker.py --request "$run/timesfm-tato/request.json" > logs/v431-r2/financial-timesfm-tato.log 2>&1
echo "timesfm-tato exit=$?"
date -Is
