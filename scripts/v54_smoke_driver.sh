#!/usr/bin/env bash
# Smoke driver for the v54 external imputers: wait for the BRITS smoke
# archive, check it against the SAITS archive, then run and check the CSDI
# smoke on the same single source and block.  The full queue is executed by
# the parallel schedulers (tmux v54-par*), so this driver deliberately does
# NOT enqueue production shards -- it only validates format and guards before
# CSDI commits hours of GPU time.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOCK=/home/vipuser/work/work2/locks/gpu.lock
mkdir -p logs/v54

say() { echo "=== [$(date +%H:%M:%S)] $*"; }

say "waiting for BRITS smoke report"
while [ ! -f results/v54/replay/external/brits/report_full-smoke.json ]; do
  sleep 60
done
say "BRITS smoke finished; checking against SAITS"
"$W2_CORE_PY" scripts/v54_smoke_check.py \
    --method BRITS --block test --tag smoke --source ETTh1 \
    | tee logs/v54/smoke_check_brits.json

say "WAIT-LOCK CSDI smoke ETTh1 test"
if flock "$LOCK" "$BASE_PY" -u scripts/v54_external_imputers.py \
     --method CSDI --mode full --blocks test --sources ETTh1 --tag smoke \
     > logs/v54/smoke_csdi_etth1_test.log 2>&1; then
  say "CSDI smoke finished; checking against SAITS"
  "$W2_CORE_PY" scripts/v54_smoke_check.py \
      --method CSDI --block test --tag smoke --source ETTh1 \
      | tee logs/v54/smoke_check_csdi.json
else
  say "CSDI smoke FAILED; see logs/v54/smoke_csdi_etth1_test.log"
fi
say "DRIVER DONE"
