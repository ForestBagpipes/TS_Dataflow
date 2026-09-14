#!/usr/bin/env bash
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
exec "$W2_CORE_PY" -u scripts/monitor_v43.py --interval 30 --max-hours 24 >> logs/v43/monitor-launch.log 2>&1
