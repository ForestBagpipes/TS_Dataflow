#!/usr/bin/env bash
# Mask-realisation stability: the same TEST parents under two further
# deterministic deletion patterns, on the two backbones the appendix names.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 11:00" +%s)
LOG=logs/v46/mask.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
run() {
  local marker="$1"; shift
  [ -f "$marker" ] && { say "SKIP $marker"; return 0; }
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, not starting: $*"; return 1; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; return 1; fi
}
say "mask stability begins"
for B in test_m2 test_m3; do
  run "results/v46/replay/inputs/$B.json" "$W2_CORE_PY" -u scripts/v46_prepare.py --block "$B" || break
done
for B in test_m2 test_m3; do
  run "results/v46/replay/tsicl/$B.json" "$W2_TSICL_PY" -u scripts/v46_tsicl.py --block "$B" || break
done
for BB in bolt chronos2; do
  for B in test_m2 test_m3; do
    run "results/v46/replay/forecast/$B/$BB/status.json" "$W2_CHRONOS_PY" -u scripts/v46_forecast.py --block "$B" --backbone "$BB" || true
  done
done
for BB in bolt chronos2; do
  for B in test_m2 test_m3; do
    if "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block "$B" >> "$LOG" 2>&1; then
      say "eval OK $BB $B"
    else
      say "eval FAIL $BB $B"
    fi
  done
done
say "mask stability ends"
