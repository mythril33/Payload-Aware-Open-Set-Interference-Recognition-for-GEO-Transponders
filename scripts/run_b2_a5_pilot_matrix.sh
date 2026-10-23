#!/usr/bin/env bash
# Bounded P28 matrix orchestration; no pipeline can hide a Python exit status.
# Defaults: DATA MATCHED RUNS OUT, followed by optional --only NAME / budget flags.
# First use --plan to inventory work; an explicit successful subset exits 3/PARTIAL.
# See python scripts/b2_a5_matrix.py --help. Every invocation validates provenance
# through geoml.b2_a5, including verified results and interrupted scene state.
set -euo pipefail
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-2} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-2} MKL_NUM_THREADS=${MKL_NUM_THREADS:-2}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${PYTHON:-python}" "$SCRIPT_DIR/b2_a5_matrix.py" "$@"
