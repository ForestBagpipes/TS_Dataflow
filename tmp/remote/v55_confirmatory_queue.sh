#!/usr/bin/env bash
# v55 confirmatory queue: Solar and US_Term_Structure through the frozen stages.
#
# Same stages as scripts/v54_confirmatory_queue.sh with the BRITS and CSDI
# stages removed, because those two methods left the comparison on 2026-09-22
# and the confirmatory set only needs the rows the paper actually reports.
# Inputs and TS-ICL candidates are already on disk, so the queue resumes at the
# SAITS deployment imputer.  Every stage is idempotent and skipped when its
# marker exists.  It waits for the main GPU queue to finish first so the E3
# latency measurement keeps the card to itself.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/confirmatory_queue.log
mkdir -p logs/v54 results/v54/confirmatory
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
run() {
  local marker="$1"; shift
  if [ -e "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  say "RUN $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $marker"; else say "FAIL $marker rc=$?"; return 1; fi
}

say "=== v55 confirmatory follower waiting for the main GPU queue ==="
while ! grep -q 'MASTER v3 FINISHED' logs/v54/gpu_master.log 2>/dev/null; do sleep 120; done
while pgrep -f 'v54_latency_e2e|v54_external_(t1|pswi|timesnet)\.py' > /dev/null; do sleep 60; done
sleep 30
say "=== main queue finished, confirmatory begins ==="

for B in bankx train_eval test test_m2 test_m3; do
  run "results/v54/confirmatory/replay/inputs/$B.json" \
      "$W2_CORE_PY" -u scripts/v54_confirmatory_prepare.py --block "$B" || exit 1
done
for B in bankx train_eval test test_m2 test_m3; do
  run "results/v54/confirmatory/replay/tsicl/$B.json" \
      "$W2_TSICL_PY" -u scripts/v54_confirmatory_tsicl.py --block "$B" || exit 1
done
run "results/v54/confirmatory/replay/saits/report_crossfit.json" \
    "$BASE_PY" -u scripts/v54_confirmatory_saits.py --mode crossfit || exit 1
run "results/v54/confirmatory/replay/saits/report_full.json" \
    "$BASE_PY" -u scripts/v54_confirmatory_saits.py --mode full || exit 1
say "saits done"

for BB in bolt timesfm chronos2; do
  for B in bankx train_eval test test_m2 test_m3; do
    run "results/v54/confirmatory/replay/forecast/$B/$BB/status.json" \
        "$W2_CHRONOS_PY" -u scripts/v54_confirmatory_forecast.py \
        --block "$B" --backbone "$BB" || exit 1
  done
done
say "forecast done"

run "results/v54/confirmatory/check_report.json" \
    "$W2_CORE_PY" -u scripts/v54_confirmatory_check.py || exit 1
say "=== v55 confirmatory queue done ==="
