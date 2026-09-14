#!/usr/bin/env bash
# 仅对随后启动的下载进程生效；不改正在运行的安装、全局 pip 或代理配置。
# 用法：先 source scripts/env_new_server.sh，再 source 本文件。
if [[ "${W2_ROOT:-}" != /home/vipuser/work/work2 ]]; then
  echo '请先 source scripts/env_new_server.sh' >&2
  return 1 2>/dev/null || exit 1
fi

export W2_PYPI_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
export W2_PYTORCH_MIRROR=https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/
export PIP_INDEX_URL="$W2_PYPI_MIRROR"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1},pypi.nvidia.com,pypi.nvidia.cn,mirrors.tuna.tsinghua.edu.cn,mirror.sjtu.edu.cn,s3.jcloud.sjtu.edu.cn"
export no_proxy="$NO_PROXY"
# Torch 下载需显式 --index-url "$W2_PYTORCH_MIRROR" 并保持冻结版本及哈希。
# 不清空其他 HTTP(S)_PROXY；Hugging Face 等尚未验证直连的站点仍用原线路。
