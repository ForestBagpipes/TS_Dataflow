#!/usr/bin/env bash
# SAITS: train one imputer per source, forecast its repaired inputs with each
# backbone, then re-run the evaluation so the baseline rows enter every table.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
DEADLINE=$(date -d "today 11:00" +%s)
LOG=logs/v46/saits.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
run() {
  local marker="$1"; shift
  [ -f "$marker" ] && { say "SKIP $marker"; return 0; }
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, not starting: $*"; return 1; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; return 1; fi
}
say "SAITS queue begins"
run "results/v46/baselines/saits/report.json" "$BASE_PY" -u scripts/v46_saits.py --blocks test,test30,test50
for BB in bolt chronos2 timesfm; do
  for B in test test30 test50; do
    run "results/v46/baselines/saits_${B}_${BB}/records.json" \
        "$W2_CHRONOS_PY" -u scripts/v46_baseline_forecast.py --method saits --backbone "$BB" --block "$B" || true
  done
done
say "SAITS queue ends"
say "re-running the evaluation and the reconstruction comparison"
for BB in bolt timesfm chronos2; do
  for B in test test30 test50; do
    rm -f "results/v46/evaluation/${B}_${BB}.json"
    if "$W2_CORE_PY" -u scripts/v46_evaluate.py --backbone "$BB" --block "$B" >> "$LOG" 2>&1; then
      say "eval OK $BB $B"
    else
      say "eval FAIL $BB $B"
    fi
  done
  rm -f "results/v46/diagnostics/reconstruction_test_${BB}.json"
  if "$W2_CORE_PY" -u scripts/v46_reconstruction.py --backbone "$BB" --block test >> "$LOG" 2>&1; then
    say "recon OK $BB"
  else
    say "recon FAIL $BB"
  fi
done
say "all queues end"
