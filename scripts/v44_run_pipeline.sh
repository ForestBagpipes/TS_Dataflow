#!/usr/bin/env bash
# v4.4 replay-bank pipeline driver.
#
# Runs the remaining stages in order for every block and both development
# backbones, then the K/beta gate and the TRAIN-Eval admission.
#
# Each stage refuses to overwrite an existing artifact, so this driver skips a
# stage whose output is already on disk and re-runs only what is missing.  GPU
# stages take locks/gpu.lock, so this must not run alongside another GPU job.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
source scripts/env_new_server.sh
mkdir -p logs/v44

BLOCKS="${BLOCKS:-gate train_eval}"
BACKBONES="${BACKBONES:-bolt timesfm}"
# Replay-Fit carries the bank itself, so its forecasts are needed for both
# backbones even though its TS-ICL stage is usually already done.
ALL_BLOCKS="replay_fit ${BLOCKS}"

step() {
  local name="$1"; local guard="$2"; shift 2
  if [ -n "$guard" ] && [ -e "$guard" ]; then
    echo "=== [$(date +%H:%M:%S)] ${name} SKIPPED (exists: ${guard}) ==="
    return 0
  fi
  echo "=== [$(date +%H:%M:%S)] ${name} ==="
  if "$@"; then
    echo "=== [$(date +%H:%M:%S)] ${name} OK ==="
  else
    echo "=== [$(date +%H:%M:%S)] ${name} FAILED ==="
    exit 1
  fi
}

for block in $BLOCKS; do
  step "stage-B tsicl ${block}" "results/v44/replay/tsicl/${block}.json" \
    "$W2_TSICL_PY" -u scripts/v44_replay_tsicl.py --block "$block"
done

for block in $ALL_BLOCKS; do
  for backbone in $BACKBONES; do
    step "stage-C forecast ${block}/${backbone}" \
      "results/v44/replay/forecast/${block}/${backbone}/status.json" \
      "$W2_CHRONOS_PY" -u scripts/v44_replay_forecast.py \
        --block "$block" --backbone "$backbone"
  done
done

# The replay bank itself is only ever built from Replay-Fit (task book §10).
for backbone in $BACKBONES; do
  step "stage-D bank replay_fit/${backbone}" \
    "results/v44/banks/replay_fit/replay_bank_${backbone}.summary.json" \
    "$W2_CORE_PY" -u scripts/v44_replay_bank.py \
      --block replay_fit --backbone "$backbone"
done

step "gate selection" "results/v44/gate/gate_sweep.json" \
  "$W2_CORE_PY" -u scripts/v44_selector.py --mode gate
step "train-eval admission" "results/v44/evaluation/train_eval.json" \
  "$W2_CORE_PY" -u scripts/v44_selector.py --mode eval

echo "=== pipeline complete $(date +%H:%M:%S) ==="
