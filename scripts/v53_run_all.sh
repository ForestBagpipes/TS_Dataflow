#!/usr/bin/env bash
# v53 runner: selection + controls + audits, sequentially, with raw logs.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
LOG=results/v53_state_compact/logs
mkdir -p "$LOG"
for b in bolt timesfm chronos2; do
  "$W2_CORE_PY" scripts/v53_state_compact.py --backbone "$b" > "$LOG/state_compact_$b.log" 2>&1
  echo "state_compact $b exit=$?"
done
for b in bolt timesfm chronos2; do
  "$W2_CORE_PY" scripts/v53_gate_controls2.py --backbone "$b" > "$LOG/gate_controls2_$b.log" 2>&1
  echo "gate_controls2 $b exit=$?"
  "$W2_CORE_PY" scripts/v53_source_fixed.py --backbone "$b" > "$LOG/source_fixed_$b.log" 2>&1
  echo "source_fixed $b exit=$?"
done
"$W2_CORE_PY" scripts/v53_harmcap_proposal.py > "$LOG/harmcap_audit.log" 2>&1
echo "harmcap exit=$?"
"$W2_CORE_PY" scripts/v53_latency_audit.py > "$LOG/latency_audit.log" 2>&1
echo "latency exit=$?"
echo ALL_DONE
