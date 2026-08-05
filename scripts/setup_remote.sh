#!/usr/bin/env bash
# Environment setup for a rented GPU box (AutoDL and similar).
#
#   bash scripts/setup_remote.sh          # everything
#   bash scripts/setup_remote.sh chronos  # one family only
#
# Each foundation-model family is installed separately: they pin conflicting
# versions of transformers and gluonts often enough that a single resolve fails,
# and a family that will not install should disable one adapter rather than the
# whole environment.

set -u
FAMILY="${1:-all}"

log() { printf '\n=== %s ===\n' "$1"; }

log "core"
pip install -q -r requirements.txt || exit 1
pip install -q "torch>=2.0" || exit 1

install_family() {
  local name="$1"; shift
  log "$name"
  if pip install -q "$@"; then
    echo "  installed"
  else
    echo "  FAILED -- ${name} adapter will be unavailable, others are unaffected"
  fi
}

if [ "$FAMILY" = "all" ] || [ "$FAMILY" = "chronos" ]; then
  install_family chronos "chronos-forecasting>=1.4.0"
fi
if [ "$FAMILY" = "all" ] || [ "$FAMILY" = "moment" ]; then
  install_family moment "momentfm"
fi
if [ "$FAMILY" = "all" ] || [ "$FAMILY" = "timesfm" ]; then
  install_family timesfm "timesfm[torch]"
fi

log "environment"
python - <<'PY'
import importlib
import torch

print(f"torch {torch.__version__}  cuda={torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"device: {torch.cuda.get_device_name(0)}")
for mod in ("chronos", "momentfm", "timesfm", "transformers"):
    try:
        m = importlib.import_module(mod)
        print(f"{mod:16s} {getattr(m, '__version__', 'ok')}")
    except Exception as exc:
        print(f"{mod:16s} MISSING ({type(exc).__name__})")
PY

log "next"
cat <<'EOF'
Weights download on first use; pre-warm them and check the adapters with:

    python scripts/verify_backends.py --device cuda

Only once that reports every backend green is a long run worth starting:

    python experiments/run_agent.py --scale full --source ett \
        --preset multi-family --device cuda
EOF
