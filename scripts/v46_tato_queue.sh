#!/usr/bin/env bash
# TATO on every backbone and every severity block.  The pipeline search is
# cached per backbone, so only the first block of a backbone pays for it.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
DEADLINE=$(date -d "today 11:05" +%s)
LOG=logs/v46/tato.log
mkdir -p logs/v46
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
say "TATO queue begins"
for BB in bolt chronos2 timesfm; do
  for B in test test30 test50; do
    MARK="results/v46/baselines/tato_${B}_${BB}/records.json"
    if [ -f "$MARK" ]; then say "SKIP $MARK"; continue; fi
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "DEADLINE, stopping"; break 2; fi
    say "START tato $BB $B"
    if "$W2_CHRONOS_PY" -u scripts/v46_tato.py --backbone "$BB" --block "$B" \
        --trials 48 --windows 8 --deadline-minutes 25 >> "$LOG" 2>&1; then
      say "OK tato $BB $B"
    else
      say "FAIL tato $BB $B"
    fi
  done
done
say "TATO queue ends"
