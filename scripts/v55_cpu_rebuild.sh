#!/usr/bin/env bash
# Registered D-01/D-02 rebuild. Run inside an independent tmux session.
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
mkdir -p logs/v55 results/v55
LOG=logs/v55/cpu_rebuild_20260923.log
STATUS=results/v55/cpu_rebuild_status.json
START=$(date -Is)
printf '{"status":"running","started":"%s","pid":%s}\n' "$START" "$$" > "$STATUS"
finish() {
  rc=$?
  if [ "$rc" -eq 0 ]; then state=completed; else state=failed; fi
  printf '{"status":"%s","started":"%s","finished":"%s","pid":%s,"exit_code":%s}\n' \
    "$state" "$START" "$(date -Is)" "$$" "$rc" > "$STATUS"
  printf '[%s] rebuild %s rc=%s\n' "$(date -Is)" "$state" "$rc" >> "$LOG"
}
trap finish EXIT
say() { printf '[%s] %s\n' "$(date -Is)" "$*" >> "$LOG"; }
say 'D-01/D-02 full CPU rebuild starts'
"$W2_CORE_PY" -m pytest tests/v55/test_v55_contracts.py tests/v54/test_v54_contracts.py -q \
  > logs/v55/cpu_rebuild_tests.log 2>&1
say 'contract tests passed'
for bb in bolt timesfm chronos2; do
  say "select $bb"
  "$W2_CORE_PY" scripts/v55_select.py --backbone "$bb" \
    > "logs/v55/select_${bb}.log" 2>&1
  "$W2_CORE_PY" scripts/v55_select_1se.py --backbone "$bb" \
    >> "logs/v55/select_${bb}.log" 2>&1
  say "conformal $bb"
  "$W2_CORE_PY" scripts/v55_conformal.py --backbone "$bb" \
    > "logs/v55/conformal_${bb}.log" 2>&1
  say "evaluate $bb"
  "$W2_CORE_PY" scripts/v55_evaluate.py --backbone "$bb" \
    > "logs/v55/eval_${bb}.log" 2>&1
  say "gate controls $bb"
  "$W2_CORE_PY" scripts/v55_gate_controls.py --backbone "$bb" \
    > "logs/v55/gate_${bb}.log" 2>&1
done
"$W2_CORE_PY" scripts/v55_paper_tables.py > logs/v55/paper_tables_20260923.txt 2>&1
say 'D-01/D-02 full CPU rebuild completed'
