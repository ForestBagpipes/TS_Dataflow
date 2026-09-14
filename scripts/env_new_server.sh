#!/usr/bin/env bash
# Source explicitly from this project. This file does not modify global shell settings.
export W2_ROOT=/home/vipuser/work/work2
export W2_ENVS=/home/vipuser/work2-envs
export W2_CACHE=/home/vipuser/work2-cache
export W2_CORE_PY="$W2_ENVS/w2-core/bin/python"
export W2_TSICL_PY="$W2_ENVS/w2-tsicl/bin/python"
export W2_CHRONOS_PY="$W2_ENVS/w2-chronos/bin/python"
export PYTHONPATH="$W2_ROOT/src:$W2_ROOT/experiments"
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
export HF_HOME="$W2_CACHE/huggingface"
export PIP_CACHE_DIR="$W2_CACHE/pip"
export CONDA_PKGS_DIRS="$W2_CACHE/conda-pkgs"
export XDG_CACHE_HOME="$W2_ROOT/.cache"
export MPLCONFIGDIR="$W2_ROOT/.cache/matplotlib"
export TRITON_CACHE_DIR="$W2_ROOT/.cache/triton"
export HF_HUB_DOWNLOAD_TIMEOUT=120
export MPLBACKEND=Agg
export HTTP_PROXY=http://127.0.0.1:17890 HTTPS_PROXY=http://127.0.0.1:17890
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY"
export ALL_PROXY=http://127.0.0.1:17890 all_proxy=http://127.0.0.1:17890
export NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1
unset HF_ENDPOINT
