#!/usr/bin/env bash
# Bounded E4 A5 pilot matrix: one separately capped CLI invocation per (perturbation, scope).
#
# Resumable at two levels, and never silent about failures. Every invocation is always handed to
# geoml.b2_a5: a finished one is reused only after its experiment identity (configuration, artifacts,
# checkpoints, run files, source tree) and checksum verify, an interrupted one resumes at scene level from its
# verified state/ directory (uncommitted writes are discarded, modified state is rejected), and a changed
# identity is refused rather than skipped. A failing invocation is reported and fails the script; at the end
# every expected invocation must have a verified results.json, otherwise it is listed as MISSING and the script
# exits non-zero. Nothing here generates data, trains a model or lifts a cap. Usage (repository root, pilot
# artifacts and run directory in place; PYTHON selects the interpreter):
#
#   scripts/run_b2_a5_pilot_matrix.sh [DATA] [MATCHED] [RUNS] [OUT]
#
# defaults: data/b2-feat-pilot data/b2-match-pilot runs/b2-feat-pilot runs/b2-a5-pilot
set -u -o pipefail
DATA=${1:-data/b2-feat-pilot}
MATCHED=${2:-data/b2-match-pilot}
RUNS=${3:-runs/b2-feat-pilot}
OUT=${4:-runs/b2-a5-pilot}
PYTHON=${PYTHON:-python}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-2} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-2} MKL_NUM_THREADS=${MKL_NUM_THREADS:-2}
mkdir -p "$OUT"
failed=0
expected=()

run() {  # name, then geoml.b2_a5 arguments
  local name=$1; shift
  expected+=("$name")
  echo "run    $name"
  "$PYTHON" -m geoml.b2_a5 --data "$DATA" --runs "$RUNS" --out "$OUT/$name" "$@" 2>&1 | tail -3
  local status=${PIPESTATUS[0]}
  if [ "$status" -ne 0 ]; then echo "FAILED $name (exit $status)"; failed=1; fi
}

run known_none_both --config configs/b2_a5_smoke.json --perturbation none --scope both
for p in shift_plus shift_minus drop_one phantom authorize_intruder stale_plan; do
  for s in co_only cross_only both; do
    run "known_${p}_${s}" --config configs/b2_a5_smoke.json --perturbation "$p" --scope "$s"
  done
done
for p in drop_one phantom authorize_intruder; do
  for s in co_only both; do
    run "matched_${p}_${s}" --config configs/b2_a5_matched_smoke.json --matched-data "$MATCHED" --perturbation "$p" --scope "$s"
  done
done

for name in "${expected[@]}"; do   # every expected invocation must have a verified, checksummed result
  results="$OUT/$name/results.json"; sidecar="$OUT/$name/results.json.sha256"
  if [ ! -f "$results" ] || [ ! -f "$sidecar" ] \
     || [ "$(sha256sum "$results" | cut -d' ' -f1)" != "$(tr -d '[:space:]' < "$sidecar")" ]; then
    echo "MISSING $name"; failed=1
  fi
done
echo "MATRIX_DONE expected=${#expected[@]} failed=$failed"
exit $failed
