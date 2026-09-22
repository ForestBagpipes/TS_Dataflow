#!/usr/bin/env bash
# v54 parallel scheduler v2: adds a RAM gate (MemAvailable >= 4 GiB).
set -u
cd /home/vipuser/work/work2
source scripts/env_new_server.sh
PY=/home/vipuser/work2-envs/w2-baseline/bin/python
mkdir -p logs/v54

MAX_PAR="${MAX_PAR:-4}"
MIN_FREE_MIB="${MIN_FREE_MIB:-8192}"
MIN_RAM_MB="${MIN_RAM_MB:-4096}"
SOURCES="ETTh1 ETTh2 ETTm1 ETTm2 Electricity Exchange Traffic Weather"

free_mib() {
  nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1
}

free_ram_mb() {
  awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo
}

unit_done() {
  local m="$1" s="$2" mode="$3"
  local ml="${m,,}" sl="${s,,}"
  local tag="${ml}-${sl}-${mode}"
  local dir="results/v54/replay/external/${ml}"
  local blocks="bankx"
  [ "$mode" = "full" ] && blocks="train_eval test test30 test50 test_m2 test_m3"
  local b
  for b in $blocks; do
    [ -f "${dir}/${b}__${tag}.npz" ] || return 1
  done
  return 0
}

unit_running() {
  pgrep -f "v54_external_imputers_par.py.*--tag $1" > /dev/null 2>&1
}

launch() {
  local m="$1" s="$2" mode="$3"
  local ml="${m,,}" sl="${s,,}"
  local tag="${ml}-${sl}-${mode}"
  echo "[$(date +%H:%M:%S)] launch $tag (gpufree=$(free_mib) MiB ramfree=$(free_ram_mb) MiB)"
  "$PY" -u scripts/v54_external_imputers_par.py \
    --method "$m" --mode "$mode" --sources "$s" --tag "$tag" \
    > "logs/v54/par_${tag}.log" 2>&1 &
}

echo "[$(date)] v54-par2 scheduler start (MAX_PAR=$MAX_PAR MIN_FREE=$MIN_FREE_MIB MIN_RAM=$MIN_RAM_MB)"
for m in BRITS CSDI; do
  for s in $SOURCES; do
    for mode in crossfit full; do
      tag="${m,,}-${s,,}-${mode}"
      if unit_done "$m" "$s" "$mode"; then
        echo "[$(date +%H:%M:%S)] skip ${tag} (archives exist)"
        continue
      fi
      if unit_running "$tag"; then
        echo "[$(date +%H:%M:%S)] skip ${tag} (already running)"
        continue
      fi
      while :; do
        running=$(jobs -rp | wc -l)
        free=$(free_mib)
        ramfree=$(free_ram_mb)
        if [ "$running" -lt "$MAX_PAR" ] && [ "$free" -ge "$MIN_FREE_MIB" ] && [ "$ramfree" -ge "$MIN_RAM_MB" ]; then
          break
        fi
        sleep 60
      done
      launch "$m" "$s" "$mode"
      sleep 20
    done
  done
done
wait
echo "[$(date)] v54-par2 scheduler done"
