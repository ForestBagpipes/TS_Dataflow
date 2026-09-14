# Activate the IntroAct-TS (work2) environment on the AutoDL box.
#
#   source /root/autodl-tmp/work2/scripts/env_autodl.sh
#
# Deliberately sourced rather than wired into ~/.bashrc: work1 (forecastcore)
# lives in the same container with its own conda env at envs/fc, and a login
# shell that silently activated one project's environment would eventually run
# the other project's code against the wrong interpreter.
#
# What is isolated:
#   code            /root/autodl-tmp/work2        (work1: .../work1)
#   interpreter     /root/autodl-tmp/envs/w2      (work1: .../envs/fc)
#   model weights   work2/.cache/hf               (work1: .../.cache/huggingface)
#
# What is deliberately shared:
#   the pip *download* cache, because it only ever accelerates downloads --
#   packages still install into each environment's own site-packages, and the
#   container has 39 GB free, not enough to duplicate a 3 GB torch wheel for
#   the sake of purity.

export W2_ROOT=/root/autodl-tmp/work2
export W2_ENV=/root/autodl-tmp/envs/w2

export VIRTUAL_ENV="$W2_ENV"
export PATH="$W2_ENV/bin:$PATH"
unset PYTHONHOME
unset PYTHONPATH

# Weights land inside the project, so removing work2 removes its downloads too.
export HF_HOME="$W2_ROOT/.cache/hf"
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DOWNLOAD_TIMEOUT=120
mkdir -p "$HF_HOME"

export PIP_CACHE_DIR=/root/autodl-tmp/.cache/pip

# Keep BLAS from oversubscribing: the probe is many small matrix products, and
# thread thrash costs more than the parallelism buys.
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8

cd "$W2_ROOT" 2>/dev/null || true

echo "work2 env active"
echo "  python : $(python -V 2>&1)  ($W2_ENV)"
echo "  root   : $W2_ROOT"
echo "  HF_HOME: $HF_HOME"
