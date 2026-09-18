#!/usr/bin/env bash
# v4.6 run driver.  Every stage writes its own status file and is skipped when
# that file already exists, so an interrupted run resumes where it stopped.
# No stage is started after DEADLINE, which leaves time to archive the partial
# result set before the machine goes down.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 02:05" +%s)
LOG=logs/v46/pipeline.log
mkdir -p logs/v46 results/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
guard() {
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    say "DEADLINE reached, not starting: $*"; return 1
  fi
  return 0
}
run() {  # run <marker> <env-python> <script> <args...>
  local marker="$1"; shift
  if [ -f "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  guard "$*" || return 1
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $* (exit $?)"; return 1; fi
}

say "v46 pipeline begins"

for B in bank train_eval test; do
  run "results/v46/replay/inputs/$B.json" "$W2_CORE_PY" -u scripts/v46_prepare.py --block "$B" || break
done

for B in bank train_eval test; do
  run "results/v46/replay/tsicl/$B.json" "$W2_TSICL_PY" -u scripts/v46_tsicl.py --block "$B" || break
done

for BB in bolt timesfm; do
  for B in bank train_eval test; do
    run "results/v46/replay/forecast/$B/$BB/status.json" "$W2_CHRONOS_PY" -u scripts/v46_forecast.py --block "$B" --backbone "$BB" || true
  done
done

say "v46 pipeline ends"
