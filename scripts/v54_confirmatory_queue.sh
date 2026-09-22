#!/usr/bin/env bash
# v54 confirmatory queue: Solar + US_Term_Structure through the v46/v47 stages.
#
# One sequential driver.  Every GPU stage takes the project-wide lock
# `flock locks/gpu.lock` (blocking), so this queue serialises behind any
# running or queued heavy GPU task (e.g. the main-set BRITS/CSDI runs).
# CPU preparation runs lock-free.  Tasks are idempotent: a finished stage
# leaves its marker file and is skipped on re-entry.
#
# Usage:  tmux new -s v54-confirm 'bash scripts/v54_confirmatory_queue.sh'
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh

BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
LOCK=locks/gpu.lock
LOG=logs/v54/confirmatory_queue.log
mkdir -p logs/v54 results/v54/confirmatory

BLOCKS="bankx train_eval test test_m2 test_m3"
EVAL_BLOCKS="train_eval test test_m2 test_m3"

say() { echo "=== [$(date '+%F %T')] $*" | tee -a "$LOG"; }

run() {  # run <marker> <cmd...>   (CPU, no GPU lock)
  local marker="$1"; shift
  if [ -e "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  say "START $*"
  if "$@" >> "$LOG" 2>&1; then say "OK $marker"; else say "FAIL $marker (exit $?)"; return 1; fi
}

grun() {  # grun <marker> <cmd...>  (GPU, behind the project-wide lock)
  local marker="$1"; shift
  if [ -e "$marker" ]; then say "SKIP (exists) $marker"; return 0; fi
  say "WAIT-LOCK $*"
  if flock "$LOCK" "$@" >> "$LOG" 2>&1; then say "OK $marker"; else say "FAIL $marker (exit $?)"; return 1; fi
}

say "v54 confirmatory queue begins"

# ---- Stage 0: frozen parent manifest -------------------------------------
run "results/v54/confirmatory/parent_manifest.json" \
    "$W2_CORE_PY" -u scripts/v54_confirmatory_prepare.py --dump-grid || exit 1

# ---- Stage A: CPU preparation ---------------------------------------------
for B in $BLOCKS; do
  run "results/v54/confirmatory/replay/inputs/$B.json" \
      "$W2_CORE_PY" -u scripts/v54_confirmatory_prepare.py --block "$B" || exit 1
done
say "stage A (prepare) done"

# ---- Stage B: TS-ICL candidates -------------------------------------------
for B in $BLOCKS; do
  grun "results/v54/confirmatory/replay/tsicl/$B.json" \
      "$W2_TSICL_PY" -u scripts/v54_confirmatory_tsicl.py --block "$B" || exit 1
done
say "stage B (tsicl) done"

# ---- SAITS: cross-fitted bank, then deployment imputer ---------------------
grun "results/v54/confirmatory/replay/saits/report_crossfit.json" \
    "$BASE_PY" -u scripts/v54_confirmatory_saits.py --mode crossfit || exit 1
grun "results/v54/confirmatory/replay/saits/report_full.json" \
    "$BASE_PY" -u scripts/v54_confirmatory_saits.py --mode full || exit 1
say "saits done"

# ---- External imputers: BRITS / CSDI ---------------------------------------
for M in BRITS CSDI; do
  LOWER=$(echo "$M" | tr 'A-Z' 'a-z')
  grun "results/v54/confirmatory/replay/external/$LOWER/report_crossfit.json" \
      "$BASE_PY" -u scripts/v54_confirmatory_external.py --method "$M" --mode crossfit || exit 1
  grun "results/v54/confirmatory/replay/external/$LOWER/report_full.json" \
      "$BASE_PY" -u scripts/v54_confirmatory_external.py --method "$M" --mode full || exit 1
done
say "external imputers done"

# ---- Stage C: three frozen backbones ----------------------------------------
# Same interpreter policy as scripts/v47_queue.sh: the chronos environment
# carries bolt (chronos package), timesfm (source overlay) and chronos2.
for BB in bolt timesfm chronos2; do
  for B in test train_eval test_m2 test_m3 bankx; do
    grun "results/v54/confirmatory/replay/forecast/$B/$BB/status.json" \
        "$W2_CHRONOS_PY" -u scripts/v54_confirmatory_forecast.py \
        --block "$B" --backbone "$BB" || exit 1
  done
done
say "stage C (forecast) done"

# ---- Self-check --------------------------------------------------------------
run "results/v54/confirmatory/check_report.json" \
    "$W2_CORE_PY" -u scripts/v54_confirmatory_check.py || exit 1

say "v54 confirmatory queue done"
