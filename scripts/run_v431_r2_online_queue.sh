#!/usr/bin/env bash
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
date -Is
"$W2_CORE_PY" scripts/v431_r2_online.py results/v431-r2 --family bolt > logs/v431-r2/online-bolt-launch.log 2>&1
echo "bolt_exit=$?"
"$W2_CORE_PY" scripts/v431_r2_online.py results/v431-r2 --family timesfm > logs/v431-r2/online-timesfm-launch.log 2>&1
echo "timesfm_exit=$?"
date -Is
