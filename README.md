# Payload-Aware Open-Set Interference Recognition for GEO Transponders

GEO bent-pipe transponderindeki girişimi, operatörün downlink spektrum izlemesinden tanıyan derin öğrenme çalışması. Ders projesi; makaleye genişletilecek.

- Plan ve kararlar: `docs/plan/` (`00_ana_plan.md` ile başlayın)
- Simülatör: `src/geosim/` — şartname `docs/plan/P2_sistem_modeli.md`, kullanım `docs/plan/P4_simulator_tasarim.md`

```
pip install -e .[dev]
pytest
```

Simülatör, DVB-S2 referans transponderinden türetilmiş verilerle birlikte gelir (`src/geosim/data/`). Ham ETSI dosyaları depoda değildir; yeniden üretmek için `docs/plan/kaynak_transponder_modeli.md` içindeki bağlantılardan indirip `data/` altına koyun ve `scripts/` altındaki iki betiği çalıştırın.

## First open-set development experiment

The `B1-dev/1` runner connects the existing ResNet to MSP and energy rejection.
By default, `swept_cw` is excluded from training, model selection and calibration,
then evaluated as an unknown family. `clean` remains a known reference.

```bash
pip install -e '.[dev,ml]'
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.dataset --out data/openset-pilot --splits train_nl val_nl test_id_nl --limit-seeds 6 --workers 2
python -m geoml.experiment --config configs/stage_b_openset.json --data data/openset-pilot --out runs/openset-pilot
```

In the prepared cloud environment, activate `/workspace/.venvs/geosim/bin/activate`
instead of reinstalling dependencies. Reports, predictions, checkpoint and rejection
calibrators are saved under the output directory. Add `--reuse` to the experiment
command to reuse matching artifacts. Use a fresh data directory when generation
parameters or generator source change; existing shards are validated before reuse.

This tiny run validates execution, not recognition quality. It does not implement
the final eight-class/dual-polarization benchmark. See the [implementation plan](docs/plan/P10_implementation_structure.md)
and [development protocol and commands](docs/plan/P11_openset_development.md).

## Extended unknown-family experiment

`B1-dev/2` adds test-only pulsed, wideband-noise and intermittent-burst sources,
training-only regularized Mahalanobis scoring, and unknown-positive AUROC/AP plus
OSCR curves. It reports each family separately and pooled, using the same frozen
known-only calibration for all test families.

```bash
python -m geosim.dataset --out data/openset-v2 --splits train_nl val_nl test_id_nl --limit-seeds 6 --workers 1
python -m geosim.unknowns --out data/unknowns-v1 --n-seeds 6
python -m geoml.experiment --config configs/stage_b_unknowns.json --data data/openset-v2 --unknown-data data/unknowns-v1 --out runs/openset-v2
```

See [unknown-source definitions](docs/plan/P12_unknown_events.md) and
[extended protocol, metric conventions and reuse](docs/plan/P13_extended_openset.md).
Reusable coding-agent briefs are versioned in [.agents/](.agents/README.md), with
repository instructions in [AGENTS.md](AGENTS.md).

## Dual-polarization leakage development

`D1-dev/1` adds separate polarization payload paths, physical uplink/downlink
coupling and receiver calibration from independent pilots. Each feed has its own
operator carrier plan. The matched models use co-pol spectrum/plan (two channels)
or both spectra/plans (four channels), with one shared power reference.

```bash
python -m geosim.dual_dataset --out data/dual-pilot --n-seeds 6
python -m geoml.dual_experiment --config configs/dual_polarization.json --data data/dual-pilot --out runs/dual-pilot
```

This controlled `clean` versus `cross_pol` experiment tests a simulated uplink-XPD
change. It is not the final eight-class open-set benchmark or proof of a unique
physical cause. Calibration corrects instrument response while retaining
propagation leakage. See [physics, data and experiment details](docs/plan/P14_dual_polarization.md).

## Phase noise and received interference

`E1-dev/1` adds common satellite/receiver oscillator phase noise and a paired
three-class task: clean, carrier-under-carrier uplink interference and received
adjacent-satellite interference. The downlink event bypasses the wanted payload.
Both model views share scenario partitions and training budgets.

```bash
python -m geosim.event_dataset --config configs/interference_events_data.json --out data/events-pilot
python -m geoml.dual_experiment --config configs/interference_events.json --data data/events-pilot --out runs/events-pilot
```

The linewidth and power ranges are exploratory engineering assumptions. This
closed-set task tests simulator causes; PSD alone does not uniquely establish
satellite origin or authorization. See [physical stages, contracts and reuse](docs/plan/P15_phase_noise_and_events.md).

## Robustness evaluation (R1-eval/1)

Test-only splits with their own protocol name and seeds: a back-off sweep (nominal
5–14 dB, overdrive 0–5 dB), a Rapp SSPA and two memory polynomials fitted to OpenDPD
solid-state Doherty PA measurements (nominal back-off only). The evaluator reloads
Stage A checkpoints without retraining and reports the payload gap per 1 dB back-off
bin, ECE, FPR@95TPR and thresholded detection. Keep R1 data in its own directory.

```bash
python -m geosim.dataset --protocol R1-eval/1 --out data/r1 --workers 4
python -m geoml.robustness --data data/stageA --runs runs/stageA --r1 data/r1 --out runs/r1
```

The OpenDPD devices are not TWTAs; the measured-RMS-to-back-off mapping and memory-tap
scaling are assumptions. See [protocol, assumptions and validation](docs/plan/P17_r1_robustness_eval.md).

## B2 known physical observations

The completed preliminary `B2-base/1` artifact stage connected the frozen B2/1
roles and eight known classes. Operator plans remain intact when a planned
carrier is absent, with fixed nominal gain and preserved waveform RNG streams.

```bash
python -m geosim.b2_dataset --config configs/b2_base.json --out data/b2-base-pilot --limit-groups 2 --groups-per-shard 1
```

This historical stage emits paired spectra, operator masks and a separate
plan-consistency target. It has no cancellation channel, and its manifest marks
the benchmark incomplete. See [contracts, sampling assumptions and reuse](docs/plan/P19_b2_base_observations.md).

## B2 cancellation residual and five-channel model

`B2-feat/1` adds the observation-based co-pol cancellation residual (fifth model
channel, P18 §5) computed at generation time from the calibrated co-pol monitor IQ
and the co-pol operator plan only. `geoml.b2_experiment` trains matched
`co`/`dual`/`dual_residual` models with an independent `plan_consistency` head and a
pre-registered center-loss weight on the frozen P18 roles.

```bash
python -m geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json --out data/b2-feat-pilot --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_cancellation.py --data data/b2-feat-pilot --out runs/b2-feat-pilot/cancellation_check.json
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --out runs/b2-feat-pilot
```

The pilot shows the paired clean/under-carrier visibility rising from 1 dB to 6.5 dB
median after cancellation; the tiny learning run is at chance and proves execution only.
Unknown families, CID overlays and the matched ASI set are not generated yet. See
[P20](docs/plan/P20_b2_cancellation_residual.md) and the [pilot report](docs/results/b2_feat_pilot.md).
Claude Code context lives in [CLAUDE.md](CLAUDE.md), `.claude/rules/` and `.claude/skills/`.

## B2 observed receiver and two-output development model

`B2-features/1` is a separate development stage using the
`geosim.observed_receiver` linear receiver. It generates fresh physical
observations with a co-feed cancellation residual PSD. The receiver uses
calibrated monitor IQ and declared operator frequency, symbol rate, roll-off,
modulation and APSK code-rate information. Availability of those fields is an
experiment assumption. Transmitted symbols, true powers, timing, phase and
active-state truth are excluded. The decision-directed receiver estimates
synchronization and a received-domain FIR channel; it does not invert the
nonlinear payload or implement a complete DVB-S2 modem.

`B2-observed-dev/1` compares the four-channel `dual` view with the five-channel
`b2` view using the same scenario roles, seeds and training budget. The fifth
channel shares the co-plan power reference. Both models have an eight-class
head and an independent two-state plan-consistency head. Training uses primary
CE + 1.0 × consistency CE + 0.01 × mean squared embedding-to-center loss;
class centers and feature statistics are fitted on train groups only.

The P20 and P21 stages retain separate receiver algorithms, artifacts and
training conventions. P20 uses a one-logit BCE auxiliary head and center weight
0.005 on squared distance summed over features, then averaged over samples.
P21 uses two-logit CE and center weight 0.01 on distance averaged over both
features and samples. These coefficients and results are not directly
comparable as a single-variable ablation.

```bash
python -m geosim.b2_features --config configs/b2_base.json \
  --cancellation-config configs/b2_receiver.json \
  --role-limits configs/b2_feature_pilot_limits.json \
  --groups-per-shard 1 --out data/b2-features-pilot
python -m geoml.b2_observed_experiment --config configs/b2_observed_experiment.json \
  --data data/b2-features-pilot --out runs/b2-observed-pilot
```

These commands select 96 known-class observations: 9 train groups and one each
for val-select, val-calib and test, with eight paired classes per group.
Val-select primary macro-F1 selects weights; clean val-calib observations alone
set the event-alarm threshold. The held-out prefixes have no missing carriers,
so their missing-carrier recall is `null` with zero support.

Training applies mirroring and time shifts. Separately, 15% of samples receive
continuous ±0.5 MHz mask jitter. This jitter changes model mask inputs only;
the stored receiver residual stays fixed. Full receiver plan-error tests must
rerun cancellation with perturbed descriptors. Final unknown-family,
CID-overlay and level-matched ASI/unauthorized tests, full-data training and
multi-seed evaluation remain pending. This is an execution pilot, with
`benchmark_complete: false`, rather than evidence of useful recognition or
cancellation quality. Freeze source before generation, use a fresh data
directory after source/configuration changes, and use experiment `--reuse`
only for matching artifacts. See [P21 receiver assumptions and development
contract](docs/plan/P21_b2_observed_receiver.md).

## Research dossier (2026-10-20)

This is an evolving research project, **not** a completed dual-polarization, eight-class open-set system.

- [P1 literature review and novelty audit](docs/plan/P1_literatur.md)
- [P8 external dataset/source and license audit](docs/plan/P8_dis_veri.md)
- [P9 roadmap and risks](docs/plan/P9_yol_haritasi.md)
- [P16 post-literature-review correction and completion programme](docs/plan/P16_literatur_duzeltme_programi.md)
- [Proposed open-set benchmark and identifiability protocol](docs/research/open_set_protocol.md)
- [Primary/original source URLs and provenance](sources/ORIGINALS.md)
- [Original user-supplied project brief — text transcription](sources/original_proposal.md)
- [Literature bibliography (BibTeX)](references/references.bib)
- [Detailed current Stage A status](docs/plan/DURUM.md) and [pilot-only results](docs/results/pilot_A.md)

**Current research boundary:** Stage A is single-polarization/five known classes, with a small pilot. B2-base/1 and B2-feat/1 connect the eight frozen known classes, the fifth channel and the two-output model. B2-features/1 and B2-observed-dev/1 provide a separate observed-receiver development stage with distinct artifacts and training conventions. Neither B2 stage includes final unknown/CID/matched test families or full-scale training. B1-dev/1 implements known-class holdout rejection with MSP and energy; B1-dev/2 adds unknown families, Mahalanobis and ranking metrics. D1-dev/1 adds calibrated dual-polarization observations and a controlled two-class leakage task. E1-dev/1 adds phase noise and two modulated-interference mechanisms in a separate three-class task. Full-data results and the unified eight-class dual-polarization open-set benchmark remain outstanding. The pilots are not evidence of field/deployment performance. The code repository does not currently specify a top-level license; third-party PDF/data licenses and redistribution conditions must be handled separately. Official primary-source links are preserved instead of automatically mirroring restricted documents.
