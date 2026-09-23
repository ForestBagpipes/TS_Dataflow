#!/usr/bin/env bash
# v54 GPU queue v3 (healthy replacement card, 2026-09-23 11:00).
# The card is clean (ECC 0/0, no remapped rows), so the one-at-a-time rule
# of v2 is dropped: T1 fits are memory-light (2.3 GiB) and do not saturate an
# A100 at batch 16, so the three missing T1 sources run concurrently while the
# PSW-I sources run as a serial chain (their workers are the heavy consumer).
# A finisher waits for everything, runs the sampled recomputation that the
# hardware incident requires, then E3 on an idle GPU.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/gpu_master.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

t1_run() {  # $1 source  $2 tag  $3 blocks
  local lower; lower=$(echo "$1" | tr 'A-Z' 'a-z')
  say "T1 $1 start tag=$2"
  $BASE_PY -u scripts/v54_external_t1.py --sources "$1" --blocks "$3" \
    --tag "$2" > "logs/v54/t1_${2}.log" 2>&1
  say "T1 $1 exit rc=$? tag=$2"
}
pswi_run() {
  local lower; lower=$(echo "$1" | tr 'A-Z' 'a-z')
  say "PSWI $1 start tag=$2"
  $BASE_PY -u scripts/v54_external_pswi.py --mode full --sources "$1" \
    --tag "$2" > "logs/v54/pswi_${2}.log" 2>&1
  say "PSWI $1 exit rc=$? tag=$2"
}

say "MASTER v3 START (replacement GPU)"
t1_run Electricity t1-electricity-full train_eval,test,test30,test50 &
sleep 30
t1_run Traffic     t1-traffic-full     train_eval,test,test30,test50 &
sleep 30
t1_run Weather     t1-weather-full     train_eval,test,test30,test50 &
(
  pswi_run ETTm1   pswi-ettm1-full
  pswi_run Traffic pswi-traffic-full
  pswi_run Weather pswi-weather-full
  say "PSWI CHAIN DONE"
) &
wait
say "EXTERNALS DONE"

# ---- sampled recomputation (hardware incident, user decision 2026-09-23) ---
# Re-fit three cheap cells on the healthy card under fresh tags; the check
# script compares them with the archived shards produced on the faulty card.
say "VERIFY start"
t1_run ETTh1 t1-etth1-verify test
pswi_run Exchange pswi-exchange-verify
$BASE_PY -u scripts/v54_external_timesnet.py --sources ETTh1 \
  --tag timesnet-etth1-verify > logs/v54/timesnet_verify.log 2>&1 \
  || say "timesnet verify rc=$?"
say "VERIFY done"

# ---- E3 re-measurement on the idle GPU --------------------------------------
say "E3 tsicl start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role tsicl --overwrite > logs/v54/cost_tsicl.log 2>&1 || say "E3 tsicl rc=$?"
say "E3 saits start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role saits --overwrite > logs/v54/cost_saits.log 2>&1 || say "E3 saits rc=$?"
for bb in bolt timesfm chronos2; do
  say "E3 chain $bb start"
  $W2_CORE_PY scripts/v54_latency_e2e.py --role chain --backbone "$bb" --overwrite > "logs/v54/cost_chain_${bb}.log" 2>&1 || say "E3 chain $bb rc=$?"
done
say "E3 merge start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role merge --overwrite > logs/v54/cost_merge.log 2>&1 || say "E3 merge rc=$?"
say "MASTER v3 FINISHED"
