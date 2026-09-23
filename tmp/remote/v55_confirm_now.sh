#!/usr/bin/env bash
# Confirmatory set, started in parallel with the remaining external baselines.
# The replacement card has the headroom, and E3 is what needs an idle GPU, so
# the confirmatory stages move ahead of it rather than behind it.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOG=logs/v54/confirmatory_queue.log
mkdir -p logs/v54 results/v54/confirmatory
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
run() {
  local marker="$1"; shift
  if [ -e "$marker" ]; then say "SKIP $marker"; return 0; fi
  say "RUN $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $marker"; else say "FAIL $marker rc=$?"; return 1; fi
}
say "=== confirmatory begins (parallel mode) ==="
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
for BB in bolt timesfm chronos2; do
  for B in bankx train_eval test test_m2 test_m3; do
    run "results/v54/confirmatory/replay/forecast/$B/$BB/status.json" \
        "$W2_CHRONOS_PY" -u scripts/v54_confirmatory_forecast.py \
        --block "$B" --backbone "$BB" || exit 1
  done
done
run "results/v54/confirmatory/check_report.json" \
    "$W2_CORE_PY" -u scripts/v54_confirmatory_check.py || exit 1
say "=== confirmatory done ==="
