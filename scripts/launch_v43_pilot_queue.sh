#!/usr/bin/env bash
set -euo pipefail
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
exec "$W2_CORE_PY" -u scripts/run_v43_pilot_queue.py >> logs/v43/pilot-queue-launch.log 2>&1
