#!/usr/bin/env bash
# Final GPU stage, run when nothing else is on the card.
#
# Two things happen here and both need an idle GPU for different reasons.  The
# sampled recomputation re-fits three cheap cells on the replacement card so
# they can be compared with the archives the faulty card produced, and the end
# to end latency measurement times a served request, which any other process on
# the card would inflate.  Each role runs under the interpreter that owns its
# model: TS-ICL in the tsicl environment, SAITS in the baseline environment and
# the backbone chain in the chronos environment.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v55/finish2.log
mkdir -p logs/v55
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

say "=== waiting for the external and evaluation queues ==="
while pgrep -f 'v47_baseline_forecast\.py|v55_evaluate\.py|v54_external_(t1|pswi|timesnet)\.py|v54_confirmatory_(saits|tsicl|forecast)\.py' > /dev/null; do
  sleep 60
done
sleep 30
busy=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)
say "GPU compute processes before E3: $busy"

say "=== sampled recomputation on the replacement card ==="
for spec in "t1:ETTh1:t1-etth1-verify" "timesnet:ETTh1:timesnet-etth1-verify"; do
  m=${spec%%:*}; rest=${spec#*:}; src=${rest%%:*}; tag=${rest#*:}
  if [ -f "results/v54/replay/external/$m/test__$tag.npz" ]; then
    say "verify $m present"; continue
  fi
  say "verify $m $src"
  $BASE_PY -u "scripts/v54_external_${m}.py" --sources "$src" --blocks test \
    --tag "$tag" > "logs/v55/verify_${m}.log" 2>&1 || say "verify $m rc=$?"
done
if [ ! -f results/v54/replay/external/pswi/test__pswi-exchange-verify.npz ]; then
  say "verify pswi Exchange"
  $BASE_PY -u scripts/v54_external_pswi.py --mode full --sources Exchange \
    --tag pswi-exchange-verify > logs/v55/verify_pswi.log 2>&1 || say "verify pswi rc=$?"
fi

say "=== E3 end to end latency, idle card, each role in its own environment ==="
$W2_TSICL_PY -u scripts/v54_latency_e2e.py --role tsicl --overwrite \
  > logs/v55/cost_tsicl.log 2>&1 || say "E3 tsicl rc=$?"
$BASE_PY -u scripts/v54_latency_e2e.py --role saits --overwrite \
  > logs/v55/cost_saits.log 2>&1 || say "E3 saits rc=$?"
for bb in bolt timesfm chronos2; do
  $W2_CHRONOS_PY -u scripts/v54_latency_e2e.py --role chain --backbone "$bb" \
    --overwrite > "logs/v55/cost_chain_${bb}.log" 2>&1 || say "E3 chain $bb rc=$?"
done
$W2_CORE_PY scripts/v54_latency_e2e.py --role merge --overwrite \
  > logs/v55/cost_merge.log 2>&1 || say "E3 merge rc=$?"
say "=== finisher done ==="
