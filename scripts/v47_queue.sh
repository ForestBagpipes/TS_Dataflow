#!/usr/bin/env bash
# v4.7 run driver.  One role per tmux window.
#
# The device is shared rather than serialised.  Every call in this run is a
# single series on a small checkpoint, so the device is latency bound and the
# stages together finish sooner than the same stages one after another.  Each
# stage holds its own lock and checks that the device still has free memory
# before it loads, which is what keeps sharing from turning into an allocation
# failure.
#
# Usage: bash scripts/v47_queue.sh <role>
#   prep | tsicl | saits_full | saits_cross | fc_bolt | fc_timesfm | fc_chronos2
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh

W2_BASELINE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
ROLE="${1:?role required}"
LOG="logs/v47/${ROLE}.log"
mkdir -p logs/v47 results/v47

say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# Every eval block, then the bank last, because the bank's imputer records are
# cross-fitted and therefore land later than the deployment imputer.
EVAL_BLOCKS="test test30 test50 train_eval"
LATE_BLOCKS="test_m2 test_m3"
BANK_BLOCK="bankx"
ALL_BLOCKS="$BANK_BLOCK $EVAL_BLOCKS $LATE_BLOCKS"

run() {  # run <marker> <cmd...>
  local marker="$1"; shift
  if [ -e "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $* (exit $?)"; return 1; fi
}

wait_for() {  # wait_for <path> [<path>...]
  local waited=0
  for path in "$@"; do
    while [ ! -e "$path" ]; do
      sleep 20
      waited=$((waited + 20))
      if [ "$waited" -gt 14400 ]; then say "TIMEOUT waiting for $path"; return 1; fi
    done
  done
  return 0
}

case "$ROLE" in

prep)
  say "preparation begins"
  for B in $ALL_BLOCKS; do
    run "results/v47/replay/inputs/$B.json" "$W2_CORE_PY" -u scripts/v47_prepare.py --block "$B" || exit 1
  done
  say "preparation ends"
  ;;

tsicl)
  say "waiting for the preparation of every block"
  for B in $ALL_BLOCKS; do wait_for "results/v47/replay/inputs/$B.json" || exit 1; done
  for B in $ALL_BLOCKS; do
    run "results/v47/replay/tsicl/$B.json" "$W2_TSICL_PY" -u scripts/v47_tsicl.py --block "$B" || exit 1
  done
  say "tsicl ends"
  ;;

saits_full)
  say "waiting for the preparation of the bank and the evaluation blocks"
  wait_for "results/v47/replay/inputs/$BANK_BLOCK.json" || exit 1
  for B in $EVAL_BLOCKS $LATE_BLOCKS; do wait_for "results/v47/replay/inputs/$B.json" || exit 1; done
  run "results/v47/replay/saits/report_full.json" "$W2_BASELINE_PY" -u scripts/v47_saits.py \
      --mode full --blocks "test,test30,test50,train_eval,test_m2,test_m3" || exit 1
  say "deployment imputer ends"
  ;;

saits_cross)
  say "waiting for the preparation of the bank"
  wait_for "results/v47/replay/inputs/$BANK_BLOCK.json" || exit 1
  run "results/v47/replay/saits/report_crossfit.json" "$W2_BASELINE_PY" -u scripts/v47_saits.py \
      --mode crossfit --blocks "$BANK_BLOCK" || exit 1
  say "cross-fitted imputer ends"
  ;;

fc_*)
  BB="${ROLE#fc_}"
  say "forecast queue for $BB"
  for B in $EVAL_BLOCKS $BANK_BLOCK $LATE_BLOCKS; do
    wait_for "results/v47/replay/inputs/$B.json" \
             "results/v47/replay/tsicl/$B.json" \
             "results/v47/replay/saits/$B.npz" || exit 1
    run "results/v47/replay/forecast/$B/$BB/status.json" "$W2_CHRONOS_PY" -u \
        scripts/v47_forecast.py --block "$B" --backbone "$BB" || true
  done
  say "forecast queue for $BB ends"
  ;;

*)
  echo "unknown role $ROLE" >&2; exit 2;;
esac
