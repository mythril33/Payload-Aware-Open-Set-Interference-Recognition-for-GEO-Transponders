#!/usr/bin/env bash
# One-shot setup for the RF-ML learning project.
#
# Creates a local virtual environment in .venv/, installs requirements.txt
# (CPU-friendly PyTorch from PyPI, numpy, matplotlib, pytest) and runs a
# smoke check that imports the libraries and the rfml package.
#
# Usage:  bash setup.sh            # create .venv and verify
#         bash setup.sh --test     # also run the pytest suite
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: $PYTHON not found; set PYTHON=/path/to/python3 and retry" >&2
    exit 1
fi

if [ ! -d .venv ]; then
    echo "==> creating .venv with $("$PYTHON" --version)"
    "$PYTHON" -m venv .venv
fi

VENV_PY=".venv/bin/python"

echo "==> installing requirements.txt"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

echo "==> smoke check"
"$VENV_PY" - <<'PY'
import sys
import matplotlib
import numpy
import torch

print(f"python      {sys.version.split()[0]}")
print(f"torch       {torch.__version__} (cuda available: {torch.cuda.is_available()})")
print(f"numpy       {numpy.__version__}")
print(f"matplotlib  {matplotlib.__version__}")

# The rfml package is written in parallel; check whatever is present.
import importlib
for name in ("signals", "dataset", "models", "train", "openset", "metrics"):
    try:
        importlib.import_module(f"rfml.{name}")
        print(f"rfml.{name:<9} ok")
    except ModuleNotFoundError as exc:
        print(f"rfml.{name:<9} missing ({exc.name})")
PY

if [ "${1:-}" = "--test" ]; then
    echo "==> pytest"
    "$VENV_PY" -m pytest -q
fi

echo "==> done. Activate with: source .venv/bin/activate"
