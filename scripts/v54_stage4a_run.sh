#!/usr/bin/env bash
# v54 stage 4a driver: rebuild bank states, re-select, re-evaluate, aggregate.
# Pure CPU; no GPU lock.  Writes only under results/v54/ and configs/v54/.
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
PY="$W2_CORE_PY"
LOGDIR=results/v54/logs
mkdir -p "$LOGDIR"

echo "== stage4a start $(date -Is) =="

echo "== [1/6] parent manifest =="
$PY scripts/v54_parent_manifest.py > "$LOGDIR/parent_manifest.log" 2>&1

echo "== [2/6] rebuild bank (bankx,train_eval x 3 backbones) =="
$PY scripts/v54_rebuild_bank.py --blocks bankx,train_eval --backbones bolt,timesfm,chronos2 \
    > "$LOGDIR/rebuild_bank.log" 2>&1

for BB in bolt timesfm chronos2; do
    echo "== [3/6] select $BB =="
    $PY scripts/v54_select.py --backbone "$BB" > "$LOGDIR/select_$BB.log" 2>&1
done

for BB in bolt timesfm chronos2; do
    echo "== [4/6] evaluate $BB (6 blocks) =="
    $PY scripts/v54_evaluate.py --backbone "$BB" > "$LOGDIR/evaluate_$BB.log" 2>&1
done

for BB in bolt timesfm chronos2; do
    echo "== [5/6] gate controls + banksize $BB =="
    $PY scripts/v54_gate_controls.py --backbone "$BB" > "$LOGDIR/gate_controls_$BB.log" 2>&1
    $PY scripts/v54_banksize.py --backbone "$BB" --block test > "$LOGDIR/banksize_$BB.log" 2>&1
done

echo "== [6/6] main table =="
$PY scripts/v54_main_table.py > "$LOGDIR/main_table.log" 2>&1

echo "== stage4a done $(date -Is) =="
