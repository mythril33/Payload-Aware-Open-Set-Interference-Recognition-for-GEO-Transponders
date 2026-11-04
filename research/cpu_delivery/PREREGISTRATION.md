# CPU-delivery-B1/1 — fixed before execution, 2026-11-04

User direction: adapt experiments to this 2-CPU/8-GiB environment and deliver
code, experimental results and report by Sunday 8 November. This is a bounded
**single-polarization development campaign**, using existing B1-dev/2, A1 and
U1-dev/1 definitions. It does not replace B2/1, change its gates or read B2
held-out observations. Frozen physical sampling, payload reference models,
class definitions and source split seed ranges are unchanged.

The exact recipe is committed in `configs/cpu_delivery.json`. The runner writes
all three resolved fit configurations and a source-bound campaign record before
generation/training. A failed or interrupted run is incomplete; no parameter is
changed after viewing test results. Resume requires identical configuration,
runner and scientific source bytes. Existing generators/checkpoint loaders
validate artifact identities on reuse.

## Fixed sample and model budget

- 40 scenario groups from each A1 split: train_nl, val_nl, test_id_nl.
  At most 600 physical source observations (five class variants/group).
  The source generator records physically infeasible unauthorized-carrier
  placements; actual class counts must be reported, not silently filled in.
- Swept CW is excluded from optimization, model selection and calibration.
  Known labels: clean, CW, unauthorized carrier, overdrive.
- The 40 validation groups divide deterministically into 20 weight-selection
  and 20 known-only calibration groups (split seed 0). Expected retained counts:
  160 train, 80 selection, 80 calibration, 160 known test, 40 swept-CW test.
- U1 adds 40 groups × pulsed, wideband noise and intermittent bursts, from
  its existing separate seed namespace starting at 900000. Unknown test total
  is 160 if all source samples exist. Paired family variants share groups.
- Three fixed training seeds: 0, 1, 2. Width 8, batch 16, 10 epochs, time-pool 4,
  learning rate .001 and weight decay .0001. Existing known-only selection and
  training augmentations; no search. Time pooling changes neural preprocessing,
  not simulated sampling. One generator/trainer process, two numerical threads,
  CPU only. Separate output directories for each seed.
- MSP, energy and train-only Mahalanobis (shrinkage .1) all reported; no scorer
  chosen by test performance. Inclusive rejection calibration targets .95
  acceptance on known calibration groups only. Test inference follows frozen
  calibration. No proxy unknowns, post-test sign flip or threshold adjustment.

## Endpoints and reporting

Descriptive endpoints: known closed accuracy/macro-F1, unknown-positive AUROC,
average precision and OSCR; unknown rejection and known acceptance at the frozen
threshold; clean false alarm. Larger score means more unknown-like. Report each
training seed and each family, plus the predeclared pooled mixture. Wideband
noise may be observationally equivalent to an increased noise floor, so its
separate result is essential; pooled performance alone is not the conclusion.

Report actual sample/group counts. The accuracy chance reference is .25 for
balanced four-class data; AUROC chance is .5. AP chance is the observed unknown
prevalence. Clean false alarm includes rejected clean examples and clean samples
predicted as another known class. OSCR includes all known/unknown samples.

All three seeds use the same dataset: mean and min/max describe optimization
variation, not independent experimental replications or a seed confidence
interval. Existing rate intervals resample scenario groups **conditional on each
frozen model and threshold**, excluding training and calibration uncertainty.
No AUROC confidence interval, statistical significance or positive result is
promised. Negative/inconclusive outcomes are retained. Figures show per-seed
results and family-specific metrics without selecting a favorable seed.

## Resource and stop policy

The runner requires 1 GiB free disk initially, caps every generation subprocess
at 45 minutes and each fit at 30 minutes, and uses existing artifact validators
on restart. These are protective limits, not duration predictions. Source data,
predictions and checkpoints stay outside Git; only small aggregate evidence and
figures enter the delivery. The eight-class, dual-polarization, residual-channel
and matched B2 hypotheses remain NOT RUN. This campaign cannot establish their
success or measured GEO transfer.

## Reproduction

From the installed checkout, with a fresh output outside the repository:

```sh
python research/cpu_delivery/run.py --out /workspace/geo-cpu-campaign
```

After an interruption, use the identical command with `--resume`. Figures and
the campaign summary are produced only after all three fits have results.
