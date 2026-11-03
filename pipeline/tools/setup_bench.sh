#!/usr/bin/env bash
# Set up Kraken and Surya for the line-detection benchmark (pipeline/tools/bench_lines.py).
# Each gets its own virtual environment under .cache/, with CPU-only PyTorch, so neither touches the
# pipeline's own packages.  Downloads roughly 1-2 GB in total.
#
#   bash pipeline/tools/setup_bench.sh            # both
#   bash pipeline/tools/setup_bench.sh kraken     # one
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python}
BIN=bin; [ -d /c ] && BIN=Scripts          # Windows (Git Bash) venv layout
TORCH_CPU="--index-url https://download.pytorch.org/whl/cpu"

setup() {  # name, packages...
  local name=$1; shift
  local v=.cache/venv-$name
  [ -d "$v" ] || "$PY" -m venv "$v"
  "$v/$BIN/python" -m pip install -q --upgrade pip
  "$v/$BIN/python" -m pip install -q torch torchvision $TORCH_CPU
  "$v/$BIN/python" -m pip install -q "$@"
  echo "$name ready in $v"
}

for t in ${@:-kraken surya}; do
  case $t in
    kraken) setup kraken kraken ;;
    surya)  setup surya surya-ocr ;;
    *) echo "unknown tool $t" >&2; exit 1 ;;
  esac
done
