#!/usr/bin/env bash
# Resume the nine-row external grid only after the existing GPU finisher.
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
mkdir -p logs/v55 results/v55
LOG="$PWD/logs/v55/external_finish.log"
STATUS="$PWD/results/v55/external_finish_status.json"
START="$(date --iso-8601=seconds)"
printf '{"status":"running","started":"%s","pid":%s}\n' "$START" "$$" >"$STATUS"
finish() {
  rc=$?
  if [ "$rc" -eq 0 ]; then state=completed; else state=failed; fi
  printf '{"status":"%s","started":"%s","finished":"%s","pid":%s,"exit_code":%s}\n' \
    "$state" "$START" "$(date --iso-8601=seconds)" "$$" "$rc" >"$STATUS"
}
trap finish EXIT
exec >>"$LOG" 2>&1
echo "[$START] waiting for existing GPU finisher"
while ! grep -q '=== finisher done ===' logs/v54/gpu_master.log 2>/dev/null; do
  sleep 120
done
if pgrep -f 'v54_external_(t1|pswi|timesnet)\.py|v54_confirmatory_(saits|forecast)\.py|v54_latency_e2e\.py' >/dev/null; then
  echo 'GPU jobs still running after finisher marker'; exit 1
fi

"$W2_CORE_PY" scripts/v55_hardware_compare.py
"$W2_CORE_PY" - <<'PY'
import json
from pathlib import Path
p=Path('results/v54/cost/e2e_latency.json')
assert p.exists(), 'E3 latency report missing'
json.loads(p.read_text())
PY

for method in PSW_I T1; do
  echo "[$(date --iso-8601=seconds)] merge $method"
  "$W2_CORE_PY" scripts/v54_external_merge.py --method "$method"
done
"$W2_CORE_PY" - <<'PY'
import json
from pathlib import Path
for method in ('timesnet','pswi','t1'):
    path=Path(f'results/v54/replay/external/{method}/merge_report.json')
    report=json.loads(path.read_text())
    for block in ('train_eval','test','test30','test50'):
        row=report['blocks'].get(block,{})
        assert row.get('status')=='ok' and row.get('coverage_match'), \
            f'{method}/{block}: incomplete external grid'
PY

for method in pswi t1; do
  "$W2_CORE_PY" scripts/v54_new_baselines_prepare.py --method "$method"
  for bb in bolt timesfm chronos2; do
    for block in test test30 test50; do
      marker="results/v47/baselines/${method}_${block}_${bb}/records.json"
      if [ ! -f "$marker" ]; then
        echo "[$(date --iso-8601=seconds)] forecast $method $block $bb"
        "$W2_CHRONOS_PY" -u scripts/v47_baseline_forecast.py \
          --method "$method" --backbone "$bb" --block "$block"
      fi
    done
  done
done
for bb in bolt timesfm chronos2; do
  echo "[$(date --iso-8601=seconds)] reevaluate $bb"
  "$W2_CORE_PY" scripts/v55_evaluate.py --backbone "$bb"
done
"$W2_CORE_PY" scripts/v55_paper_tables.py > logs/v55/paper_tables_complete.txt
echo "[$(date --iso-8601=seconds)] external grid completed"
