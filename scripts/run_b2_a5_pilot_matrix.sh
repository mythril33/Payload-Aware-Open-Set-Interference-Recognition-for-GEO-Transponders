#!/usr/bin/env bash
# Bounded E4 A5 pilot matrix: one separately capped CLI invocation per (perturbation, scope).
#
# Resumable at two levels. Re-running the script skips every invocation whose checksummed results.json
# verifies, and an invocation that was interrupted resumes at scene level from its verified state/ directory
# (geoml.b2_a5 discards uncommitted writes and rejects modified state). Nothing here generates data, trains a
# model or lifts a cap. Usage (from the repository root, with the pilot artifacts and run directory in place):
#
#   scripts/run_b2_a5_pilot_matrix.sh [DATA] [MATCHED] [RUNS] [OUT]
#
# defaults: data/b2-feat-pilot data/b2-match-pilot runs/b2-feat-pilot runs/b2-a5-pilot
set -u
DATA=${1:-data/b2-feat-pilot}
MATCHED=${2:-data/b2-match-pilot}
RUNS=${3:-runs/b2-feat-pilot}
OUT=${4:-runs/b2-a5-pilot}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-2} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-2} MKL_NUM_THREADS=${MKL_NUM_THREADS:-2}
mkdir -p "$OUT"
failed=0

run() {  # name, then geoml.b2_a5 arguments
  local name=$1; shift
  if [ -f "$OUT/$name/results.json" ] && [ -f "$OUT/$name/results.json.sha256" ] \
     && [ "$(sha256sum "$OUT/$name/results.json" | cut -d' ' -f1)" = "$(tr -d '[:space:]' < "$OUT/$name/results.json.sha256")" ]; then
    echo "done   $name"; return
  fi
  echo "run    $name"
  python -m geoml.b2_a5 --data "$DATA" --runs "$RUNS" --out "$OUT/$name" "$@" 2>&1 | tail -3 || failed=1
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
echo "MATRIX_DONE failed=$failed"
exit $failed
