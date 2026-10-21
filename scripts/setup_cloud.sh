#!/usr/bin/env bash
# Reproduce the CPU environment used for the first development milestone.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="${GEOSIM_VENV:-/workspace/.venvs/geosim}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/workspace/.cache/pip}"
cd "$repo_root"
python -m venv "$venv_path"
# The PyTorch CPU index may be blocked by the environment's network policy; fall back to PyPI.
"$venv_path/bin/python" -m pip install 'torch==2.14.1+cpu' --index-url https://download.pytorch.org/whl/cpu \
  || "$venv_path/bin/python" -m pip install 'torch==2.14.1'
"$venv_path/bin/python" -m pip install -e '.[dev,ml]' 'numpy==2.5.4' 'scipy==1.18.1' 'pytest==9.1.1' 'matplotlib==3.11.2'
"$venv_path/bin/python" -m pip check
