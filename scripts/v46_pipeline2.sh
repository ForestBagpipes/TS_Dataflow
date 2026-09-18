#!/usr/bin/env bash
# Severity sweep, queued behind the main pipeline.  Waits for the GPU to be
# released rather than competing for the lock.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 02:05" +%s)
LOG=logs/v46/pipeline2.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "waiting for the main pipeline to release the GPU"
while ! grep -q "chronos2 ends" logs/v46/pipeline3.log 2>/dev/null; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE while waiting"; exit 0; fi
  sleep 20
done
say "main pipeline finished, starting the severity sweep"

run() {
  local marker="$1"; shift
  if [ -f "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, not starting: $*"; return 1; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; return 1; fi
}

for B in test30 test50; do
  run "results/v46/replay/inputs/$B.json" "$W2_CORE_PY" -u scripts/v46_prepare.py --block "$B" || break
done
for B in test30 test50; do
  run "results/v46/replay/tsicl/$B.json" "$W2_TSICL_PY" -u scripts/v46_tsicl.py --block "$B" || break
done
for BB in bolt timesfm; do
  for B in test30 test50; do
    run "results/v46/replay/forecast/$B/$BB/status.json" "$W2_CHRONOS_PY" -u scripts/v46_forecast.py --block "$B" --backbone "$BB" || true
  done
done
say "severity sweep ends"
