#!/usr/bin/env bash
# Chronos-2, the held-out backbone.  Queued last and limited to the two blocks
# the main table needs, so a slow backbone cannot starve the rest of the run.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 02:05" +%s)
LOG=logs/v46/pipeline3.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
say "waiting for the severity sweep to release the GPU"
while ! grep -q "v46 pipeline ends" logs/v46/pipeline.log 2>/dev/null; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE while waiting"; exit 0; fi
  sleep 20
done
say "starting Chronos-2"
run() {
  local marker="$1"; shift
  if [ -f "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, not starting: $*"; return 1; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; return 1; fi
}
for B in bank test; do
  run "results/v46/replay/forecast/$B/chronos2/status.json" "$W2_CHRONOS_PY" -u scripts/v46_forecast.py --block "$B" --backbone chronos2 || true
done
say "chronos2 ends"
