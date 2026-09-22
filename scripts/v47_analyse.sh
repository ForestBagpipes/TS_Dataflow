#!/usr/bin/env bash
# CPU analysis, started as soon as each backbone's forecasts land.
#
# Selection runs first and refuses to proceed without the bank, then the
# evaluation of every block, then the diagnostics.  Every stage is skipped when
# its output exists, so the loop can be restarted at any point.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
# An optional backbone argument keeps one watcher per family, so a slow
# diagnostic on one does not hold up the selection of another.
ONLY="${1:-}"
LOG="logs/v47/analyse${ONLY:+_$ONLY}.log"
mkdir -p logs/v47 results/v47
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
step() {
  local marker="$1"; shift
  [ -e "$marker" ] && return 0
  say "RUN $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $*"; else say "FAIL $*"; fi
}

BLOCKS="test test30 test50 train_eval test_m2 test_m3"
DEADLINE=$(( $(date +%s) + 6*3600 ))

say "analysis watcher begins"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  DONE=1
  for BB in ${ONLY:-bolt timesfm chronos2}; do
    BANK="results/v47/replay/forecast/bankx/$BB/status.json"
    [ -f "$BANK" ] || { DONE=0; continue; }
    step "results/v47/protocol/selection_$BB.json" \
         "$W2_CORE_PY" -u scripts/v47_select.py --backbone "$BB" --bank-blocks bankx
    [ -f "results/v47/protocol/selection_$BB.json" ] || { DONE=0; continue; }
    for B in $BLOCKS; do
      if [ ! -f "results/v47/replay/forecast/$B/$BB/status.json" ]; then DONE=0; continue; fi
      # The main table carries a published baseline, so a block that has one
      # waits for its records.  Evaluating early would write a table without
      # that row and then skip itself on every later pass.
      case "$B" in
        test|test30|test50)
          if [ ! -f "results/v47/baselines/tato_${B}_${BB}/records.json" ]; then
            DONE=0; continue
          fi;;
      esac
      step "results/v47/evaluation/${B}_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_evaluate.py --backbone "$BB" --block "$B" \
           --bank-blocks bankx
    done
    if [ -f "results/v47/evaluation/test_$BB.json" ]; then
      step "results/v47/diagnostics/reconstruction_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_reconstruction.py --backbone "$BB" --block test
      step "results/v47/diagnostics/operating_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_operating.py --backbone "$BB" --block test
      step "results/v47/diagnostics/retrieval_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_retrieval.py --backbone "$BB" --block test
      step "results/v47/diagnostics/severity_bias_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_severity_bias.py --backbone "$BB"
      step "results/v47/ablations/banksize_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_banksize.py --backbone "$BB" --block test
      step "results/v47/ablations/selection_stability_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_selection_stability.py --backbone "$BB" --block test
      step "results/v47/cost_audit/latency_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_latency.py --backbone "$BB" --block test
      step "results/v47/diagnostics/score_utility_test_$BB.json" \
           "$W2_CORE_PY" -u scripts/v47_score_utility.py --backbone "$BB" --block test
    fi
  done
  if [ "$DONE" -eq 1 ]; then say "every stage has its output"; break; fi
  sleep 30
done
say "analysis watcher ends"
