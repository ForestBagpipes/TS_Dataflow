#!/usr/bin/env bash
# Run on the new Linux server only. No models are downloaded by this script.
set -Eeuo pipefail
umask 027

export W2_ROOT=/home/vipuser/work/work2
export W2_ENVS=/home/vipuser/work2-envs
export W2_CACHE=/home/vipuser/work2-cache
export W2_BOOTSTRAP=/home/vipuser/work2-staging/bootstrap-20260914
CONDA_BIN=/home/vipuser/miniconda3/bin/conda
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
VERIFY_SCRIPT="$W2_BOOTSTRAP/verify-bootstrap-envs.py"
LOG_DIR="$W2_BOOTSTRAP/logs"
REQ_DIR="$W2_ROOT/requirements/bootstrap-20260914"
mkdir -p "$LOG_DIR" "$REQ_DIR" "$W2_ENVS" "$W2_CACHE" "$W2_ROOT/third_party"
exec 9>"$W2_BOOTSTRAP/bootstrap.lock"
flock -n 9 || { echo 'Another bootstrap owns the project lock.' >&2; exit 73; }
exec > >(tee -a "$LOG_DIR/bootstrap-direct-resume.log") 2>&1

export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false MPLBACKEND=Agg
export HF_HOME="$W2_CACHE/huggingface" PIP_CACHE_DIR="$W2_CACHE/pip"
export CONDA_PKGS_DIRS="$W2_CACHE/conda-pkgs"
export XDG_CACHE_HOME="$W2_CACHE/xdg" MPLCONFIGDIR="$W2_CACHE/matplotlib"
export HTTP_PROXY=http://127.0.0.1:17890 HTTPS_PROXY=http://127.0.0.1:17890
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY"
export NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
export PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_DEFAULT_TIMEOUT=120
unset PIP_EXTRA_INDEX_URL PIP_TRUSTED_HOST HF_ENDPOINT ALL_PROXY all_proxy PYTHONPATH
mkdir -p "$HF_HOME" "$PIP_CACHE_DIR" "$CONDA_PKGS_DIRS" "$XDG_CACHE_HOME" "$MPLCONFIGDIR"
STARTED_AT=$(date -Is)
PHASE=preflight

write_status() {
  local state="$1" code="${2:-0}"
  "$W2_CORE_PY" - "$state" "$PHASE" "$code" "$STARTED_AT" <<'PY'
import datetime, json, os, pathlib, sys
state, phase, code, started = sys.argv[1:]
root = pathlib.Path(os.environ['W2_BOOTSTRAP'])
report = dict(status=state, phase=phase, exit_code=int(code), started_at=started,
              updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              pid=os.getppid(), project=os.environ['W2_ROOT'],
              environments=os.environ['W2_ENVS'], models_downloaded=False)
report['environment_reports'] = {}
for name in ('w2-core', 'w2-tsicl', 'w2-chronos'):
    path = root / 'logs' / (name + '.verification.json')
    if path.exists():
        report['environment_reports'][name] = json.loads(path.read_text())
tmp = root / ('status.json.tmp.' + str(os.getpid()))
tmp.write_text(json.dumps(report, indent=2) + '\n')
tmp.replace(root / 'status.json')
PY
}
on_error() {
  local code=$?
  trap - ERR
  write_status failed "$code" || true
  echo "Bootstrap failed at phase=$PHASE exit_code=$code"
  exit "$code"
}
trap on_error ERR
trap 'PHASE=interrupted; write_status failed 130; exit 130' INT TERM

source "$W2_ROOT/scripts/env_new_server.sh"
source "$W2_ROOT/scripts/env_download_routes.sh"
unset PYTHONPATH ALL_PROXY all_proxy
PHASE=download-direct-wheels
write_status running
"$W2_CORE_PY" - <<'CHECK'
import json, pathlib, psutil
r=json.loads(pathlib.Path('/home/vipuser/work/work2/logs/v43/direct-switch-20260914/transition.json').read_text())
assert r['status']=='old_installer_stopped'
for x in r['old_installers']:
 if psutil.pid_exists(x['pid']):
  p=psutil.Process(x['pid'])
  assert p.create_time()!=x['create_time'] or p.status()==psutil.STATUS_ZOMBIE
CHECK
"$W2_TSICL_PY" -c 'from importlib.metadata import version; assert version("torch")=="2.9.1+cu126"'
"$W2_CORE_PY" -u "$W2_ROOT/scripts/download_bootstrap_wheels.py" download
PHASE=install-torch-w2-chronos-direct
write_status running
"$W2_CHRONOS_PY" -m pip install --no-index --require-hashes --report "$LOG_DIR/w2-chronos.torch-install.json" -r "$W2_ROOT/logs/v43/direct-switch-20260914/chronos-torch-local.txt"
PHASE=install-tsicl
write_status running
"$W2_ENVS/w2-tsicl/bin/python" -m pip install --dry-run --report "$LOG_DIR/w2-tsicl.resolve.json" -c "$REQ_DIR/tsicl-constraints.txt" "$W2_ROOT/third_party/ts-icl"
"$W2_ENVS/w2-tsicl/bin/python" -m pip install --report "$LOG_DIR/w2-tsicl.install.json" -c "$REQ_DIR/tsicl-constraints.txt" "$W2_ROOT/third_party/ts-icl"

PHASE=install-chronos
write_status running
"$W2_ENVS/w2-chronos/bin/python" -m pip install --dry-run --report "$LOG_DIR/w2-chronos.resolve.json" -c "$REQ_DIR/chronos-constraints.txt" -r "$REQ_DIR/chronos-science.txt" "$W2_ROOT/third_party/chronos-forecasting"
"$W2_ENVS/w2-chronos/bin/python" -m pip install --report "$LOG_DIR/w2-chronos.install.json" -c "$REQ_DIR/chronos-constraints.txt" -r "$REQ_DIR/chronos-science.txt" "$W2_ROOT/third_party/chronos-forecasting"

for name in w2-tsicl w2-chronos; do
  PHASE="verify-$name"
  write_status running
  "$W2_ENVS/$name/bin/python" -m pip check | tee "$LOG_DIR/$name.pip-check.txt"
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH="$W2_ROOT/src" "$W2_ENVS/$name/bin/python" "$VERIFY_SCRIPT" --environment "$name" --out "$LOG_DIR/$name.verification.json"
done

PHASE=freeze
write_status running
for name in w2-core w2-tsicl w2-chronos; do
  "$W2_ENVS/$name/bin/python" -m pip freeze --all > "$REQ_DIR/$name.freeze.txt"
  "$W2_ENVS/$name/bin/python" -m pip inspect > "$LOG_DIR/$name.pip-inspect.json"
  "$CONDA_BIN" list -p "$W2_ENVS/$name" --explicit > "$REQ_DIR/$name.conda-explicit.txt"
  "$W2_ENVS/$name/bin/python" -c 'import platform,sys; print(sys.version); print(platform.platform()); print(sys.executable)' > "$LOG_DIR/$name.platform.txt"
done
cp -- "$LOG_DIR/ts-icl.commit.txt" "$LOG_DIR/chronos-forecasting.commit.txt" "$REQ_DIR/"
cat > "$REQ_DIR/SOURCES.txt" <<'TXT'
Python and pip seed: conda-forge, explicit per-prefix conda records included.
PyTorch 2.9.1+cu126: official SHA256 pinned; SJTU/direct NVIDIA wheelhouse; logs/v43/direct-switch-20260914/
Python dependencies: https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple (task-scoped direct route)
TS-ICL: https://github.com/EDF-Lab/ts-icl.git (commit file alongside)
Chronos: https://github.com/amazon-science/chronos-forecasting.git (commit file alongside)
Each freeze is paired with installation reports and platform metadata in bootstrap logs.
No model weights or datasets were downloaded by this environment bootstrap.
GPU tensor validation may be deferred when another compute process is present.
TXT
(cd "$REQ_DIR" && sha256sum -- *.txt > SHA256SUMS)
PHASE=complete
write_status completed
echo "BOOTSTRAP_COMPLETE status=$W2_BOOTSTRAP/status.json"
