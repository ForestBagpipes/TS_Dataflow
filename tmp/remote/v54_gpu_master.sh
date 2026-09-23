#!/usr/bin/env bash
# v54 master GPU queue.
#
# Host quirk (A100-SXM4-40GB, driver 595.84): a *newly launched* job whose
# kernels are large fails with "CUDA error: unrecognized error code" while
# several CUDA processes are already resident; a job that survives its first
# minute then runs to completion even as the machine fills up.  Reproduced
# 2026-09-23 for T1 on Traffic and on Electricity, and for the PSW-I workers
# on Traffic and Weather.  So the policy is opportunistic: try to launch,
# check that the launch took, and otherwise back off and try again, rather
# than blocking on an exclusive GPU for hours.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/gpu_master.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

# $1 method (t1|pswi)  $2 source
attempt() {
  local method="$1" src="$2" a="$3"
  local lower tag marker logf pid
  lower=$(echo "$src" | tr 'A-Z' 'a-z')
  tag="${method}-${lower}-full"
  marker="results/v54/replay/external/${method}/test__${tag}.npz"
  logf="logs/v54/${method}_${lower}.m${a}.log"
  if [ "$method" = t1 ]; then
    $BASE_PY -u scripts/v54_external_t1.py --sources "$src" \
      --blocks train_eval,test,test30,test50 --tag "$tag" > "$logf" 2>&1 &
  else
    $BASE_PY -u scripts/v54_external_pswi.py --mode full --sources "$src" \
      --tag "$tag" > "$logf" 2>&1 &
  fi
  pid=$!
  sleep 150            # long enough for the fit to clear its first kernels
  if ! kill -0 "$pid" 2>/dev/null; then
    say "$method $src attempt=$a died within 150s"
    return 1
  fi
  say "$method $src attempt=$a launch took, waiting"
  wait "$pid"
  if [ -f "$marker" ]; then say "$method $src OK attempt=$a"; return 0; fi
  say "$method $src attempt=$a finished without output"
  return 1
}

run_job() {
  local method="$1" src="$2" lower tag marker
  lower=$(echo "$src" | tr 'A-Z' 'a-z')
  tag="${method}-${lower}-full"
  marker="results/v54/replay/external/${method}/test__${tag}.npz"
  for a in 1 2 3 4 5 6 7 8; do
    [ -f "$marker" ] && { say "$method $src already present"; return 0; }
    say "$method $src attempt=$a starting"
    if attempt "$method" "$src" "$a"; then return 0; fi
    sleep 600
  done
  say "$method $src GAVE UP after 8 attempts"
  return 1
}

say "MASTER v2 START"

# Track A: T1 Traffic is the long pole (~190 min at the published 300 epochs),
# so it tries to start now instead of queueing behind PSW-I.
( run_job t1 Traffic ; say "TRACK A DONE" ) &
TRACK_A=$!

# Track B: PSW-I Traffic and Weather, serial, once no T1 fit is starting up.
(
  while pgrep -f 'v54_external_t1.py' > /dev/null; do sleep 120; done
  sleep 60
  run_job pswi Traffic
  run_job pswi Weather
  say "TRACK B DONE"
) &
TRACK_B=$!

wait "$TRACK_A" "$TRACK_B"
say "EXTERNALS DONE"

# ---- E3 re-measurement on an idle GPU -------------------------------------
# The 2026-09-22 cost run recorded MULTI_TSICL as unavailable on Electricity
# and Traffic because the TS-ICL role hit CUDA OOM under contention: 60 of the
# 80 requests disagreed with the frozen catalog's legal action set.  Re-run
# that role and everything downstream with the GPU to itself.
while pgrep -f 'v54_external_(t1|pswi)\.py' > /dev/null; do sleep 120; done
sleep 60
say "E3 tsicl start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role tsicl --overwrite \
  > logs/v54/cost_tsicl.log 2>&1 || say "E3 tsicl rc=$?"
say "E3 saits start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role saits --overwrite \
  > logs/v54/cost_saits.log 2>&1 || say "E3 saits rc=$?"
for bb in bolt timesfm chronos2; do
  say "E3 chain $bb start"
  $W2_CORE_PY scripts/v54_latency_e2e.py --role chain --backbone "$bb" \
    --overwrite > "logs/v54/cost_chain_${bb}.log" 2>&1 || say "E3 chain $bb rc=$?"
done
say "E3 merge start"
$W2_CORE_PY scripts/v54_latency_e2e.py --role merge --overwrite \
  > logs/v54/cost_merge.log 2>&1 || say "E3 merge rc=$?"
say "MASTER QUEUE FINISHED"
