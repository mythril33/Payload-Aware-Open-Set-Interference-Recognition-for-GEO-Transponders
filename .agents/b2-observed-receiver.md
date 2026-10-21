# B2 observed-receiver development agent

Read AGENTS.md, P18, P19, P21 and DURUM.md. Preserve frozen A1/B1/D1/E1/R1
outputs and the full B2/1 role counts. `B2-features/1` and `B2-observed-dev/1`
are incomplete development stages, with `benchmark_complete: false`.
Preserve the separate P20 `B2-feat/1` receiver, runner and artifacts.

Agree on APIs and disjoint file ownership before editing:

- Receiver owner: `geosim/observed_receiver.py` and receiver tests. Accept calibrated
  co-feed IQ and whitelisted operator frequency/rate/roll-off/modulation/code-rate
  descriptors. Do not accept true powers, symbols, timing, phase, active state,
  event labels or payload truth. Test synchronization, remodulation, channel
  fitting and residual limits using controlled signals.
- Feature owner: `geosim/b2_features.py` and feature tests. Generate fresh
  physical residuals from transient observed IQ; never fabricate a fifth
  channel from PSDs or simulator waveform truth. Preserve paired scenario
  groups, independent instrument calibration, common PSD units/grid and
  source/configuration/checksum validation. Stream shards with bounded memory.
- ML owner: assigned `geoml/b2_data.py`, `b2_model.py`, `b2_train.py` and
  `b2_observed_experiment.py`, with corresponding tests. Keep the fifth channel
  on the shared co-plan reference.
  Maintain separate eight-class and two-state plan-consistency heads. Fit
  centers and statistics only on train; select weights with val-select primary
  macro-F1 and calibrate the event alarm only on clean val-calib groups.
- Integrator: coordinate configs/docs, review the combined changes, run the
  physical generation/train/reload/evaluation workflow and publish the tested
  milestone. Hand off files explicitly when ownership changes.

Use primary CE + 1.0 consistency CE + 0.01 center loss, where center distance
is averaged over samples and embedding dimensions. Verify real gradients
update both heads and learned centers. Validation, calibration and test must
not update centers or apply training augmentation. Mask jitter (15%, continuous
±0.5 MHz) changes model mask channels only; it does not recompute cancellation.
Receiver plan-error evaluation requires fresh cancellation with perturbed
operator descriptors.

These are P21 development conventions. P20 uses BCE and a different center-loss
reduction/weight; do not overwrite its settings or describe cross-stage results
as a controlled single-variable comparison.

Freeze the tested source before generating pilot artifacts. Bind generated
features, checkpoints and reports to actual source/configuration identities;
if relevant source changes, generate a new artifact directory. Do not relabel
old artifacts as current or reuse checkpoints with incompatible preprocessing,
labels or provenance. Keep generated data, IQ and weights outside Git.

Use the saved 9/1/1/1-group pilot prefixes for 96 known-class observations.
Report primary and auxiliary metrics, sample/scenario support and missing
metrics explicitly. These held-out prefixes have no naturally missing carriers:
missing-carrier recall is null with n=0. One held-out scenario does not support
a scenario-bootstrap confidence interval. Keep event-alarm thresholding distinct
from final unknown rejection. Do not infer useful cancellation or recognition
quality from a successful tiny run. Final unknown-family/CID-overlay tests,
level-matched ASI/unauthorized evaluation and full multi-seed B2/1 remain pending.
