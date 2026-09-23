#!/usr/bin/env bash
# PSW-I Traffic and Weather in parallel with the ETTm1 run already in flight.
# The replacement card is healthy and holds 33 GiB free, so the serial policy
# that the faulty card forced is no longer needed and the two remaining sources
# start now instead of queueing behind a two hour ETTm1 job.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/gpu_master.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
run() {
  local src="$1" lower tag marker
  lower=$(echo "$src" | tr 'A-Z' 'a-z'); tag="pswi-${lower}-full"
  marker="results/v54/replay/external/pswi/test__${tag}.npz"
  for a in 1 2 3; do
    [ -f "$marker" ] && { say "PSWI $src present"; return 0; }
    say "PSWI $src parallel attempt=$a"
    $BASE_PY -u scripts/v54_external_pswi.py --mode full --sources "$src" \
      --tag "$tag" > "logs/v54/pswi_${tag}.p${a}.log" 2>&1
    [ -f "$marker" ] && { say "PSWI $src OK attempt=$a"; return 0; }
    say "PSWI $src failed attempt=$a"; sleep 180
  done
  say "PSWI $src gave up"
}
run Traffic &
sleep 45
run Weather &
wait
say "PSWI PARALLEL PAIR DONE"
