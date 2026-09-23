#!/usr/bin/env bash
# Re-measure E3 in the correct isolated environments after the existing finisher.
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
PAUSED_PID=18482
mkdir -p logs/v55 results/v55 locks
START="$(date --iso-8601=seconds)"
STATUS=results/v55/e3_repair_status.json
printf '{"status":"running","started":"%s","pid":%s}\n' "$START" "$$" > "$STATUS"
finish() {
  rc=$?
  if [ "$rc" -eq 0 ]; then state=completed; else state=failed; fi
  printf '{"status":"%s","started":"%s","finished":"%s","pid":%s,"exit_code":%s}\n' \
    "$state" "$START" "$(date --iso-8601=seconds)" "$$" "$rc" > "$STATUS"
}
trap finish EXIT
exec >> logs/v55/e3_repair.log 2>&1
echo "[$START] waiting for existing finisher"
while ! grep -q '=== finisher done ===' logs/v54/gpu_master.log 2>/dev/null; do
  sleep 120
done
if ! ps -o stat= -p "$PAUSED_PID" | grep -q '^T'; then
  echo 'external validation queue is not paused; refusing competing GPU work'
  exit 1
fi
while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits)" ]; do
  echo "[$(date --iso-8601=seconds)] waiting for idle GPU"
  sleep 120
done
exec 9>>locks/gpu.lock
flock -x 9
if [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits)" ]; then
  echo 'GPU became busy after lock acquisition'; exit 1
fi

echo "[$(date --iso-8601=seconds)] E3 TS-ICL"
"$W2_TSICL_PY" -u scripts/v54_latency_e2e.py --role tsicl --overwrite
echo "[$(date --iso-8601=seconds)] E3 SAITS"
"$BASE_PY" -u scripts/v54_latency_e2e.py --role saits --overwrite
for backbone in bolt timesfm chronos2; do
  echo "[$(date --iso-8601=seconds)] E3 $backbone"
  "$W2_CHRONOS_PY" -u scripts/v54_latency_e2e.py --role chain \
    --backbone "$backbone" --overwrite
done
"$W2_CORE_PY" scripts/v54_latency_e2e.py --role merge --overwrite
"$W2_CORE_PY" scripts/v55_e3_validate.py > results/v55/e3_validation.json
flock -u 9
echo "[$(date --iso-8601=seconds)] E3 validated; resuming external grid"
kill -CONT "$PAUSED_PID"
