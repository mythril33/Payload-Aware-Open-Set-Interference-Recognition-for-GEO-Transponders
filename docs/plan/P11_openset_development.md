# B1-dev/1: first connected open-set development workflow

Date: 2026-10-20. Implements M0 and the first M1 slice from
[P10](P10_implementation_structure.md). This development protocol extends the
frozen A1 observations without changing A1 classes, sampling ranges or split
definitions. It is separate from the final eight-class proposal in
[open_set_protocol.md](../research/open_set_protocol.md).

## What is implemented

The pipeline now executes:

`validated A1 artifacts -> scenario-group partitions -> known-class ResNet ->
checkpoint reload -> known-only rejection calibration -> test inference ->
known class or unknown -> JSON/Markdown reports and per-event predictions`.

- `geosim/protocol.py`: hold out one non-clean A1 family. By default that is
  `swept_cw`; known labels are `clean`, `cw`, `unauthorized`, `overdrive`.
- `geoml/experiment.py`: configuration-driven training, checked reuse and
  end-to-end experiment execution.
- `geoml/openset.py`: stable NumPy scoring. MSP uses `1-max(softmax(z/T))`;
  energy uses `-T logsumexp(z/T)`. Both are larger for more unknown-like events.
- `geoml/calibration.py`: inclusive acceptance `score <= threshold`; threshold
  is the higher empirical quantile of known calibration scores at the requested
  acceptance level. Ties and small sample sizes may increase empirical acceptance.
- `geoml/evaluation.py`: known acceptance, closed known accuracy, conditional
  accepted-known accuracy, correct known acceptance, macro-F1 before/after
  rejection, held-out rejection and clean false alarms.
- `geoml/train.py`: compatible checkpoint loading and inference returning logits
  plus the existing ResNet embedding. Artifact identity includes label ordering,
  training/preprocessing configuration, source and input data provenance.
- `geosim/dataset.py`: artifact version 2 adds generation-request fingerprints,
  source/reference-data hashes, shard hashes, counts and seed validation. Existing
  A1 artifacts remain readable after structural checks but cannot be resumed
  without their original checksums. Infeasible unauthorized-carrier scenes are
  the only deliberately skipped simulator exceptions.
- The Stage-A runner validates checkpoint reuse and writes empty C/I bins as
  JSON `null` plus sample counts and Markdown dashes.

## Data separation

Use A1 `train_nl`, `val_nl`, and `test_id_nl` as sources. The source files can
contain all five labels; held-out-family samples are removed before any call
that optimizes weights, selects checkpoints or estimates rejection thresholds.

1. Training uses known samples from `train_nl`.
2. Distinct `val_nl` scenario groups are assigned deterministically to model
   selection and rejection calibration, using `split_seed`. All samples from a
   seed stay together. At least two validation groups are required.
3. `test_id_nl` supplies known and unknown test samples. Paired known/unknown
   scenes may share a test seed; no test seed may occur in train or validation.
4. Every requested class must be present in its partition; an empty class is an
   explicit failure, not a silently skipped test.

Calibration uses no final unknown samples. No test inference occurs until both
thresholds have been frozen. The validation acceptance target is not a guarantee
of the same acceptance on new known samples. This milestone does not tune a
detector against the final unknown family.

## Commands

From the repository root in the prepared cloud environment:

```bash
source /workspace/.venvs/geosim/bin/activate
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.dataset --out data/openset-pilot --splits train_nl val_nl test_id_nl --limit-seeds 6 --workers 2
python -m geoml.experiment --config configs/stage_b_openset.json --data data/openset-pilot --out runs/openset-pilot
python -m geoml.experiment --config runs/openset-pilot/config.json --data data/openset-pilot --out runs/openset-pilot --reuse
python -m pytest -q
```

Outside that environment, install `pip install -e '.[dev,ml]'` in a Python >=3.10
environment first. CPU is the default; `--device cuda` requires a compatible
PyTorch build and available accelerator. The prepared cloud environment uses
CPU PyTorch.

Generation requests include actual source hashes, including uncommitted code.
Use a new data directory when changing the generator, sampling configuration or
seed limit. Use a new output directory for a changed experiment; the runner does
not silently overwrite a trained model. `--reuse` accepts only a compatible
checkpoint and calibrators. Changes to test data do not affect training weights;
they do change the experiment report identity. Source changes require fresh
experiment artifacts. Existing legacy pilot data can be evaluated but should be
regenerated in a new directory for checksum-backed provenance.

## Outputs and interpretation

| File | Content |
|---|---|
| `model.pt` | Trained weights, feature-normalization reference, configuration and provenance |
| `calibration_msp.json`, `calibration_energy.json` | Frozen thresholds, acceptance target, sample count and checkpoint/calibration identity |
| `config.json` | Resolved, directly reusable experiment configuration |
| `results.json` | Metrics, sample/group counts, scenario IDs, source/data identities and training history |
| `results.md` | Readable metric and partition tables |
| `predictions.json` | True family, scenario ID, known prediction, unknown score and final decision per method |

Accepted-known accuracy is conditional on accepted known samples. If none are
accepted its value is `null`. Correct-known acceptance instead uses all known
test samples as the denominator. Clean false alarm includes rejecting a clean
sample or predicting a non-clean known class. Unknown rejection has the held-out
family as the positive population. These are different errors and are reported
separately.

Intervals bootstrap scenario groups at a fixed model and threshold; they do not
include uncertainty from retraining or threshold estimation. Conditional
accepted-known accuracy resamples the groups represented among accepted events.
Do not interpret small-run intervals as a scientific benchmark.

The initial physical smoke run used six seeds per source split (90 generated
samples total), three training epochs, four known classes and held-out swept CW.
It verifies generation, training, reload, calibration and reporting. Recognition
is weak at this size: the first run had 25% closed known accuracy and high clean
false alarms. Strong rejection performance has not been demonstrated.

## Next implementation slice

Validation: the complete suite passed **141 tests**; the final source-role guard
was then checked with all seven experiment tests passing again. Physical pilot
generation, three-epoch training, saved-config reload, compatible checkpoint
reuse and verified dataset resume all completed. Artifact and integration tests
also reject corruption, changed configurations, swapped train/test roles and
modified calibration artifacts.

Add distinct unknown-family generators, regularized Mahalanobis scoring, AUROC
and OSCR before extending physical observations to dual polarization. Full-data
multi-seed evaluation, dual-pol classes, cyclic features and real-hardware
transfer remain outstanding. The final benchmark's label/split semantics must
be versioned separately from this development holdout protocol.
