# B1-dev/2: unknown families, Mahalanobis and ranking evaluation

Date: 2026-10-20. Development milestone following [P11](P11_openset_development.md).
This connects additional unknown sources to the single-polarization A1 model;
it does not implement the final eight-known-class, dual-polarization benchmark.

## Protocol and data roles

The known classes remain A1 minus one non-clean held-out family (default swept
CW). Known training, weight-selection validation and rejection calibration use
the same group separation as B1-dev/1. The held-out A1 family and the additional
[U1-dev/1 families](P12_unknown_events.md) are final test populations only.

Unknown source generation uses a separate RNG namespace and default scenario
IDs starting at 900000. The runner rejects unknown IDs overlapping optimization
or validation groups. It also rejects a different unknown transponder bandwidth,
so this experiment isolates event-family rejection from a bandwidth shift.
Physical cause remains ambiguous where spectra are observationally equivalent,
especially extra wideband noise versus an elevated uplink noise floor.

Final test samples never select the model, fit feature statistics, choose score
hyperparameters or calibrate an operating threshold. Per-family and pooled
metrics use the same fitted scorer and threshold. Their sample counts and
unknown prevalence are recorded; different prevalences change average precision.

## Methods

MSP and energy retain their earlier definitions and score direction. A new
`MahalanobisScorer` fits class means and a pooled within-class covariance from
**training embeddings only**. For shrinkage `a`, covariance is
`(1-a) S + a trace(S)/D I + floor I`, where
`floor=max(trace(S)/D * 1e-6, 1e-8)`. Cholesky solves produce the minimum squared
distance to the known-class means. Larger distance is more unknown-like.

Default shrinkage is 0.1, fixed before the experiment. The scorer remains
numerically defined when feature dimension exceeds sample count; this does not
establish that the covariance estimate generalizes. Its NPZ contains plain
numeric arrays, source/training provenance and parameter/metadata checksums.

`calibrate_scores` accepts precomputed known calibration scores. Mahalanobis
distances are not temperature-scaled. Calibration artifacts preserve an
inclusive acceptance threshold, sample count and scorer/checkpoint identity.

## Metrics

- Unknown-positive AUROC scans from high unknown score to low score.
- `unknown_aupr` is average precision: a recall-weighted step integral, not
  trapezoidal integration of PR points. An all-tied scorer yields unknown
  prevalence, while its AUROC is 0.5.
- OSCR accepts from low unknown score to high. Its horizontal axis is unknown
  false acceptance divided by all unknown test samples. Its vertical axis is
  correctly classified and accepted known samples divided by all known test
  samples. Its maximum height is the closed known accuracy, not automatically 1.
- Equal-score groups enter together. OSCR uses straight-line interpolation
  across a mixed tie, giving half credit within that tie.

The reports retain known acceptance, conditional accepted-known accuracy,
correct-known acceptance, known macro-F1 before/after rejection, unknown
rejection and clean false alarms. Ranking curves describe final test ordering;
they do not change the threshold chosen from known calibration data. Point
AUROC/AP/OSCR estimates have no multi-seed uncertainty claim. Rate intervals
retain the fixed-model scenario-bootstrap limitations documented in P11.

## Reproduce a small run

From the checkout root, using a fresh output/data directory for changed sources:

```bash
source /workspace/.venvs/geosim/bin/activate
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.dataset --out data/openset-v2 --splits train_nl val_nl test_id_nl --limit-seeds 6 --workers 1
python -m geosim.unknowns --out data/unknowns-v1 --n-seeds 6
python -m geoml.experiment --config configs/stage_b_unknowns.json --data data/openset-v2 --unknown-data data/unknowns-v1 --out runs/openset-v2
python -m geoml.experiment --config runs/openset-v2/config.json --data data/openset-v2 --unknown-data data/unknowns-v1 --out runs/openset-v2 --reuse
python -m pytest -q
```

Outside the prepared environment, install `pip install -e '.[dev,ml]'` first.
`bash scripts/setup_cloud.sh` reproduces the prepared CPU environment. Existing
B1-dev/1 configurations remain supported without `--unknown-data`; the extended
protocol requires explicit test-only artifacts and a distinct output directory.

In addition to earlier outputs, `mahalanobis.npz` stores fitted feature
statistics. `results.json` contains per-family and pooled metrics, ROC/PR/OSCR
points, family counts and generation/configuration identities. `predictions.json`
includes each event's true family and the decision of every selected method.

Compatibility follows actual source-file hashes, not merely the Git revision:
a commit that leaves source bytes unchanged does not invalidate weights. Reports
retain the training revision and current revision separately. A changed source,
training dataset or model configuration still rejects checkpoint reuse.

## Remaining research work

Validation: **226 tests passed**. The physical smoke run generated 90 A1 source
observations and 18 additional unknown observations, trained for three epochs,
fitted Mahalanobis statistics on 24 known training samples, and calibrated on 12
separate known observations. Saved-config/checkpoint/scorer/calibrator reuse and
verified generation resume completed successfully. [Recorded metrics and
predictions](../results/openset_extended.md) retain the weak result: 25% closed
known accuracy, with pooled unknown AUROC near chance. This is an execution
check, not evidence of operational recognition quality.

This small run validates the connected workflow; it does not demonstrate useful
open-set recognition. Full-data multi-seed experiments, class-holdout rotation,
operating-condition robustness, dual polarization, phase noise, additional known
classes and measured-data transfer remain outstanding.
