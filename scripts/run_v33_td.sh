#!/bin/bash
# Detached launcher for the v3.3 candidate-table rebuild.
# env per scripts/env_autodl.sh, plus offline HF mode: the weights cache is
# complete, and this box currently has no outbound network.
cd /root/autodl-tmp/work2
export HF_HOME=/root/autodl-tmp/work2/.cache/hf
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=8 MKL_NUM_THREADS=8
exec setsid nohup /root/autodl-tmp/envs/w2/bin/python -u \
  experiments/v33_training_data.py --device cuda --n-jobs 16 \
  > logs/v33_training_data.log 2>&1
