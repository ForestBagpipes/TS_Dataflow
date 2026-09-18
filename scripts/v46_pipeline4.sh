#!/usr/bin/env bash
# Chronos-2 completions: the TRAIN-eval acceptance block and the two higher
# severities.  Queued last because the main table does not depend on them.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 02:05" +%s)
LOG=logs/v46/pipeline4.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
while ! grep -q "severity sweep ends" logs/v46/pipeline2.log 2>/dev/null; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE while waiting"; exit 0; fi
  sleep 20
done
run() {
  local marker="$1"; shift
  [ -f "$marker" ] && { say "SKIP $marker"; return 0; }
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, not starting: $*"; return 1; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; return 1; fi
}
for B in train_eval test30 test50; do
  run "results/v46/replay/forecast/$B/chronos2/status.json" "$W2_CHRONOS_PY" -u scripts/v46_forecast.py --block "$B" --backbone chronos2 || true
done
say "chronos2 completions end"
