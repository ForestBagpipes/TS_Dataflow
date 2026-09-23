#!/usr/bin/env bash
# Isolated confirmation: one SAITS fit/source, frozen on TRAIN before TEST score.
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh

OLD="$PWD/results/v54/confirmatory/replay"
NEW="$PWD/results/v55/confirmatory/replay"
LOG="$PWD/logs/v55/confirmatory_once.log"
BASE_PY=/home/vipuser/work2-envs/w2-baseline/bin/python
mkdir -p "$NEW/saits" "$PWD/logs/v55"
exec >>"$LOG" 2>&1
echo "[$(date --iso-8601=seconds)] single-fit confirmation starts"

if ! grep -q '=== finisher done ===' logs/v54/gpu_master.log; then
  echo 'E3 and the old GPU queue have not finished'; exit 1
fi
if pgrep -f 'v54_external_(t1|pswi|timesnet)\.py|v54_confirmatory_(saits|forecast)\.py|v54_latency_e2e\.py' >/dev/null; then
  echo 'another project GPU job is still running'; exit 1
fi
for item in inputs tsicl external; do
  if [ ! -e "$NEW/$item" ]; then ln -s "$OLD/$item" "$NEW/$item"; fi
done
if [ ! -e "$NEW/saits/bankx.npz" ]; then
  ln -s "$OLD/saits/bankx.npz" "$NEW/saits/bankx.npz"
fi
for bb in bolt timesfm chronos2; do
  for block in bankx train_eval test test_m2 test_m3; do
    test -f "$OLD/forecast/$block/$bb/status.json"
    test -f "$OLD/forecast/$block/$bb/predictions.npz"
  done
done

if [ ! -f "$NEW/saits/report_full_once.json" ]; then
  "$BASE_PY" -u scripts/v55_confirmatory_saits_once.py
fi
for bb in bolt timesfm chronos2; do
  for block in bankx train_eval; do
    marker="$NEW/forecast/$block/$bb/status.json"
    if [ ! -f "$marker" ]; then
      "$W2_CHRONOS_PY" -u scripts/v55_confirmatory_forecast.py \
        --block "$block" --backbone "$bb" \
        --donor "$OLD/forecast/$block/$bb/predictions.npz"
    fi
  done
done
for bb in bolt timesfm chronos2; do
  marker="results/v55/confirmatory/freeze_$bb.json"
  if [ ! -f "$marker" ]; then
    "$W2_CORE_PY" -u scripts/v55_confirmatory.py freeze --backbone "$bb"
  fi
done
for bb in bolt timesfm chronos2; do
  for block in test test_m2 test_m3; do
    marker="$NEW/forecast/$block/$bb/status.json"
    if [ ! -f "$marker" ]; then
      "$W2_CHRONOS_PY" -u scripts/v55_confirmatory_forecast.py \
        --block "$block" --backbone "$bb" \
        --donor "$OLD/forecast/$block/$bb/predictions.npz"
    fi
  done
done
"$W2_CORE_PY" -u scripts/v55_confirmatory_check.py
"$W2_CORE_PY" - <<'PY'
import json
from pathlib import Path
p=Path('results/v55/confirmatory/check_report.json')
assert json.loads(p.read_text())['all_passed'], 'single-fit audit failed'
PY
for bb in bolt timesfm chronos2; do
  marker="results/v55/confirmatory/evaluation_$bb.json"
  if [ ! -f "$marker" ]; then
    "$W2_CORE_PY" -u scripts/v55_confirmatory.py evaluate --backbone "$bb"
  fi
done
echo "[$(date --iso-8601=seconds)] single-fit confirmation completed"
