#!/usr/bin/env bash
# Final stage: the sampled recomputation the hardware incident requires, then
# the end to end latency measurement, both on a GPU with nothing else on it.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/gpu_master.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
say "=== finisher waiting for every GPU job ==="
while pgrep -f 'v54_external_(t1|pswi|timesnet)\.py|v54_confirmatory_(saits|tsicl|forecast)\.py' > /dev/null; do
  sleep 120
done
sleep 60
say "=== finisher: sampled recomputation ==="
$BASE_PY -u scripts/v54_external_t1.py --sources ETTh1 --blocks test \
  --tag t1-etth1-verify > logs/v54/t1_verify.log 2>&1 || say "t1 verify rc=$?"
$BASE_PY -u scripts/v54_external_pswi.py --mode full --sources Exchange \
  --tag pswi-exchange-verify > logs/v54/pswi_verify.log 2>&1 || say "pswi verify rc=$?"
$BASE_PY -u scripts/v54_external_timesnet.py --mode full --sources ETTh1 \
  --blocks test --tag timesnet-etth1-verify > logs/v54/timesnet_verify.log 2>&1 \
  || say "timesnet verify rc=$?"
say "=== finisher: E3 end to end latency ==="
$W2_CORE_PY scripts/v54_latency_e2e.py --role tsicl --overwrite > logs/v54/cost_tsicl.log 2>&1 || say "E3 tsicl rc=$?"
$W2_CORE_PY scripts/v54_latency_e2e.py --role saits --overwrite > logs/v54/cost_saits.log 2>&1 || say "E3 saits rc=$?"
for bb in bolt timesfm chronos2; do
  $W2_CORE_PY scripts/v54_latency_e2e.py --role chain --backbone "$bb" --overwrite \
    > "logs/v54/cost_chain_${bb}.log" 2>&1 || say "E3 chain $bb rc=$?"
done
$W2_CORE_PY scripts/v54_latency_e2e.py --role merge --overwrite > logs/v54/cost_merge.log 2>&1 || say "E3 merge rc=$?"
say "=== finisher done ==="
