#!/usr/bin/env bash
# TATO on one backbone, over the three severity blocks.
#
# The pipeline search depends on the backbone and the TRAIN windows alone, so
# it is cached per backbone and only the first block pays for it.  The stage
# holds its own lock and runs beside the forecast queues.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh

BB="${1:?backbone required}"
LOG="logs/v47/tato_${BB}.log"
mkdir -p logs/v47
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "TATO queue for $BB begins"
for B in test test30 test50; do
  MARK="results/v47/baselines/tato_${B}_${BB}/records.json"
  if [ -f "$MARK" ]; then say "SKIP $MARK"; continue; fi
  say "START tato $BB $B"
  if "$W2_CHRONOS_PY" -u scripts/v47_tato.py --backbone "$BB" --block "$B" \
      --trials 48 --windows 8 --deadline-minutes 40 >> "$LOG" 2>&1; then
    say "OK tato $BB $B"
  else
    say "FAIL tato $BB $B"
  fi
done
say "TATO queue for $BB ends"
