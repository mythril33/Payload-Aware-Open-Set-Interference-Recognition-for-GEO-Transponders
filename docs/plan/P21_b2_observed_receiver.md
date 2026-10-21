# P21 — Observed cancellation and two-output B2 development

Date: 2026-10-21. Parent: frozen B2/1 (P18). Separate development stage only;
final unknown/CID/matched tests and full multi-seed evaluation remain pending.

## Relationship to the existing P20 stage

PR #5 concurrently introduced `B2-feat/1` / `obs-cancel/1` and the canonical
`geoml.b2_experiment` runner. Those APIs, configurations, reports and historical
artifacts remain intact. This separate `B2-features/1` development stage uses
`geosim.observed_receiver` and `geoml.b2_observed_experiment`. Its receiver uses
fractional-grid timing and a short received-domain FIR; its independent auxiliary
head uses two-state CE and it streams shards during training.

The P20 K18 candidate uses center coefficient 0.005 multiplying a squared-distance
**sum** over embedding dimensions. Here 0.01 multiplies the feature/sample
**mean**. These are different development loss conventions; the numeric weights
are not directly comparable. Neither replaces or approves the other's settings.
This stage adds training mask jitter but does not establish full receiver
robustness to operator-plan errors. The two receivers are not a single-variable
ablation and their small pilots must not be compared as recognition evidence.

## Predeclared implementation settings

These choices are recorded before the physical feature/training pilot.

- The cancellation receiver consumes calibrated co-feed monitor IQ and an
  explicitly declared operator descriptor: center frequency, symbol rate,
  roll-off, modulation and APSK code-rate identifier. Availability of these
  operator fields is an assumption of this experiment. True carrier power,
  symbols, timing, phase, active state, IBO/XPD and event labels are excluded.
- Cancellation uses observed synchronization/decisions, SRRC remodulation and
  a small received-domain linear channel estimate. It is a linear receiver
  baseline with finite-window boundaries, not inversion of the nonlinear TWTA
  or a complete DVB-S2 modem. Controlled known-waveform tests establish its
  operating limits before benchmark observations are evaluated.
- Stored residual PSD has the same units and time/frequency grid as the two
  original PSDs. The fifth channel shares their co-plan power reference.
  No separate residual normalization or placeholder channel is used.
- The two heads predict eight primary classes and two plan-consistency states.
  Loss is primary CE + **1.0** × consistency CE + **0.01** × center loss.
  Center loss is squared embedding-to-class-center distance averaged over
  feature dimensions and samples. Centers are learned only on train groups.
  P6 did not specify a numeric center weight; this fixes the missing value
  without a validation/test parameter search.
- The matched four-channel and five-channel views use identical roles, seeds
  and training budgets. Weight selection uses val-select primary macro-F1;
  clean val-calib alone fixes the event-alarm threshold at target Pfa 5%.
- P18's 15% continuous ±0.5 MHz plan-mask jitter is **model-mask augmentation**.
  The already computed cancellation feature is unchanged during this training
  augmentation. Full A5 operator-plan-error tests must recompute cancellation
  with perturbed descriptors; mask-only jitter does not validate that case.
- The execution pilot uses prefixes: train 9 groups, val-select 1, val-calib 1,
  test 1. These limits leave the frozen full counts unchanged. Train includes
  natural missing group 3000008. The held-out prefixes contain no natural
  missing carriers, so missing-carrier recall there is null with n=0.

The feature artifact is `B2-features/1`, with `benchmark_complete: false`.
Generated IQ is used transiently and is not stored with the feature shards.

## Execution and artifact contracts

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.b2_features --config configs/b2_base.json --cancellation-config configs/b2_receiver.json --out data/b2-features-pilot --role-limits configs/b2_feature_pilot_limits.json --groups-per-shard 1
python -m geoml.b2_observed_experiment --config configs/b2_observed_experiment.json --data data/b2-features-pilot --out runs/b2-observed-pilot
python -m geoml.b2_observed_experiment --config configs/b2_observed_experiment.json --data data/b2-features-pilot --out runs/b2-observed-pilot --reuse
```

Feature production re-simulates calibrated IQ because historical PSD artifacts
do not contain enough information for decision-directed cancellation. Transient
IQ becomes residual PSD before writing the shard. Arrays are spectra
`[N,2,128,512]`, masks `[N,2,512]`, residual `[N,128,512]` and independent
primary/consistency targets. The five-channel model uses
`[co PSD, cross PSD, co mask, cross mask, co residual]`.

Atomic records bind the receiver algorithm and resolved settings, declared
fields, physical settings, independent calibration, source hashes and shard
checksums. Historical reads validate artifacts without invoking the current
receiver. New generation/resume requires the exact original request and source.
Models stream validated shards, bind feature/source/config identities, and
reject stale checkpoints or event thresholds. Saving/reloading retains both
heads and learned class centers. Center loss trains the representation; final
open-set scoring and LOKO evaluation are separate remaining work.

The four-channel control has the same heads, centers, scenario partitions and
training budget as the five-channel model. The fifth feature additionally
depends on the declared operator modulation/rate descriptor. Any future
comparison must state that information assumption alongside channel count.

Training mask interpolation occurs in linear power with floor padding; no
frequency wrap-around is introduced. Mirroring/time shifts act on every
observed channel together. No auxiliary truth or receiver lock diagnostic enters
the model frontend.

Receiver controls cover all four supported modulations, fractional monitor
samples per symbol, noise/absent carriers and preservation of an off-plan tone.
Carrier-under-carrier interference inside an occupied band can partly enter
the linear estimate. Total residual-power reduction alone cannot establish
interference preservation or unknown-rejection quality.

## Executed development evidence

The [96-observation pilot](../results/b2_observed_pilot.md) and its
[JSON evidence](../results/b2_observed_pilot.json) were regenerated after merging
concurrent PR #5. All 923 repository tests pass. Two three-epoch fits and exact
checkpoint/detector replay complete. Both primary accuracies are 12.5%, with
degenerate auxiliary predictions and no held-out missing targets. The one
natural train omission is on the cross feed; this pilot does not validate
co-feed absence or missing-detection generalization. Source hashes, role counts,
normalization/receiver settings and null/count conventions are retained.

These results close the execution connection, not scientific recognition quality
or the final B2 benchmark. No hyperparameters were retuned after this pilot.
