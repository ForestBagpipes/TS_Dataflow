#!/usr/bin/env bash
# Rerun the forecast stage after the guard fix, reusing what is already on disk.
#
# The earlier run rejected the reference action on every episode, so its archive
# holds every repaired input and none of the untouched ones.  A prediction is
# keyed by the input hash under a pinned revision, so this run reads the earlier
# archive for the inputs it already covers and spends a call only on the rest.
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh

BB="${1:?backbone required}"
LOG="logs/v47/refc_${BB}.log"
mkdir -p logs/v47
say() { echo "=== [$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

BLOCKS="bankx test test30 test50 train_eval test_m2 test_m3"

for B in $BLOCKS; do
  DIR="results/v47/replay/forecast/$B/$BB"
  PRE="${DIR}_pre"
  if [ -f "$DIR/status.json" ] && [ ! -f "$PRE/status.json" ]; then
    mv "$DIR" "$PRE"
    say "moved the earlier archive of $B/$BB aside"
  elif [ -d "$DIR" ] && [ ! -f "$DIR/status.json" ]; then
    rm -rf "$DIR"
    say "removed the incomplete directory of $B/$BB"
  fi
done

for B in $BLOCKS; do
  DIR="results/v47/replay/forecast/$B/$BB"
  PRE="${DIR}_pre/predictions.npz"
  if [ -f "$DIR/status.json" ]; then say "SKIP (done) $B/$BB"; continue; fi
  DONOR=""
  [ -f "$PRE" ] && DONOR="--donor $PRE"
  say "START $B/$BB ${DONOR:-no donor}"
  if "$W2_CHRONOS_PY" -u scripts/v47_forecast.py --block "$B" --backbone "$BB" $DONOR \
       >> "$LOG" 2>&1; then
    say "OK $B/$BB"
  else
    say "FAIL $B/$BB"
  fi
done
say "forecast rerun for $BB ends"
