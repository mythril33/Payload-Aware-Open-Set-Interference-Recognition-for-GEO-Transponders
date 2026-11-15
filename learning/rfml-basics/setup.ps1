# One-shot setup for the RF-ML learning project on Windows (PowerShell).
#
# Creates a local virtual environment in .venv\, installs requirements.txt
# (on Windows, pip installs the CPU-only PyTorch wheel) and runs a smoke
# check that imports the libraries and the rfml package.
#
# Usage, from this folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup.ps1          # create .venv and verify
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Test    # also run the pytest suite
#
# Needs Python 3.11+ from python.org (tick "Add python.exe to PATH" in the
# installer). This script is the Windows counterpart of setup.sh.

param([switch]$Test)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Prefer the py launcher (installed with python.org Python); fall back to python.
if (Get-Command py -ErrorAction SilentlyContinue) {
    $createVenv = { py -3 -m venv .venv }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $createVenv = { python -m venv .venv }
} else {
    Write-Error "No Python found. Install Python 3.11+ from python.org and tick 'Add python.exe to PATH'."
}

if (-not (Test-Path .venv)) {
    Write-Host "==> creating .venv"
    & $createVenv
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "==> installing requirements.txt (torch is several hundred MB; first run takes a while)"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt

Write-Host "==> smoke check"
& $venvPy -c @"
import sys
import matplotlib, numpy, torch
print(f'python      {sys.version.split()[0]}')
print(f'torch       {torch.__version__} (cuda available: {torch.cuda.is_available()})')
print(f'numpy       {numpy.__version__}')
print(f'matplotlib  {matplotlib.__version__}')
import importlib
for name in ('signals', 'dataset', 'models', 'train', 'openset', 'metrics', 'experiments'):
    try:
        importlib.import_module(f'rfml.{name}')
        print(f'rfml.{name:<11} ok')
    except ModuleNotFoundError as exc:
        print(f'rfml.{name:<11} missing ({exc.name})')
"@

if ($Test) {
    Write-Host "==> pytest"
    & $venvPy -m pytest -q
}

Write-Host "==> done. Run the UI with:  .venv\Scripts\python -m streamlit run app.py"
