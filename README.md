# Payload-Aware Open-Set Interference Recognition for GEO Transponders

**B2 production readiness (2026-10-23; E1/E2/E3a merged, bounded E3b implemented):** [P23 implementation/gate plan](docs/plan/P23_b2_production_readiness.md), [P26 EDSC](docs/plan/P26_b2_e3a_edsc_baseline.md), [P27 XGBoost](docs/plan/P27_b2_e3b_xgboost_baseline.md), [decision gate JSON](docs/plan/b2_readiness_gates_2026-10-21.json). Full production remains authorization-gated.


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

## B2 test-only families and open-set evaluation

`B2-test/1` generates the five pre-registered test-only families (`pulsed`,
`intermittent_bursts`, `adjacent_satellite_downlink`, `wideband_noise`, `cid_overlay`) for
frozen test groups only, bound to a verified known artifact (same plans, streams and
receiver calibration). `geoml.b2_experiment --unknown-data` scores them with the frozen
checkpoints and thresholds; the K17b training plan-shift augmentation is enabled in
`configs/b2_feat.json`.

```bash
python -m geosim.b2_test_dataset --out data/b2-test-pilot --known data/b2-feat-pilot --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_test_families.py --known data/b2-feat-pilot --test data/b2-test-pilot --out runs/b2-test-pilot/family_check.json
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --unknown-data data/b2-test-pilot --out runs/b2-feat-pilot-os
```

The pilot run is at chance and proves execution only. The matched ASI set is implemented below; full LOKO rotations and
full production remain. See [P21](docs/plan/P21_b2_test_families.md) and the
[pilot report](docs/results/b2_test_pilot.md).

## B2 level-matched ASI versus unauthorized set (K17c)

`B2-match/1` generates the frozen `test-matched` role (groups 3 300 000–3 300 149): per group a
`clean`, an `adjacent_satellite` and an `unauthorized` variant that share plans, link, streams,
activity, calibration, cancellation setting, carrier descriptor and one C/I_psd target from
U(4, 13) dB, differing only in placement (plan overlap versus free gap). It is a controlled
intervention, not the natural level distribution. `geoml.b2_experiment --matched-data` scores it
with frozen checkpoints and thresholds (2×2 among the pair with clean/other/rejected counted,
per-bin metrics, natural comparison, paired spectrogram figures).

```bash
python -m geosim.b2_matched_dataset --out data/b2-match-pilot --known data/b2-feat-pilot --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_matched.py --matched data/b2-match-pilot --out runs/b2-match-pilot/matched_check.json --oracle-groups 2
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --unknown-data data/b2-test-pilot --matched-data data/b2-match-pilot --out runs/b2-full-pilot
python scripts/profile_b2_generation.py --stage matched --known data/b2-feat-pilot --config configs/b2_base.json --cancellation configs/cancellation.json --groups 20 --groups-per-shard 4 --out-data data/b2-match-profile --report runs/profile/matched_20_cancel.json
```

See [P22](docs/plan/P22_b2_matched_asi.md), the [matched pilot](docs/results/b2_matched_pilot.md) and the
[production budget](docs/results/b2_production_budget.md). Pilots are at chance; full production and
GPU training wait for the researcher's authorization (K18, K17d, compute).

## B2 streaming data path (E1)

`geoml.b2_experiment` no longer loads whole roles: `geoml.b2_stream` verifies each artifact once, shard
by shard, keeps only small per-sample arrays resident, trains on windows of `window_shards` verified
shards (deterministic shard/sample order, exact `ceil(N/batch)` steps per epoch) and infers one shard at a
time. With a single window the result is bit-identical to the former in-memory path; the memory bound is
measured on fixtures, not claimed for full scale.

```bash
python scripts/profile_b2_experiment_memory.py --data data/b2-feat-pilot --window-shards 1 4 --epochs 3 --report runs/profile/e1_pilot.json
python scripts/profile_b2_experiment_memory.py --synthetic-groups 48 --fixture-dir data/e1-synthetic-48 --window-shards 1 4 --report runs/profile/e1_synthetic_48.json
```

See [P24](docs/plan/P24_b2_e1_streaming_loader.md) and the [measurements](docs/results/b2_streaming_memory.md).

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

**Current research boundary:** Stage A is single-polarization/five known classes, with a small pilot. B2-base/1 and B2-feat/1 connect the eight frozen known classes, the fifth channel and the two-output model. B2-features/1 and B2-observed-dev/1 provide a separate observed-receiver development stage with distinct artifacts and training conventions. The separate canonical B2-test/1 and B2-match/1 artifacts supply test-only unknown/CID and level-matched evaluations. E1 streams these stages; P25 adds a bounded A8 harness. Full-scale training and production LOKO remain unexecuted. B1-dev/1 implements known-class holdout rejection with MSP and energy; B1-dev/2 adds unknown families, Mahalanobis and ranking metrics. D1-dev/1 adds calibrated dual-polarization observations and a controlled two-class leakage task. E1-dev/1 adds phase noise and two modulated-interference mechanisms in a separate three-class task. Full-data results and the unified eight-class dual-polarization open-set benchmark remain outstanding. The pilots are not evidence of field/deployment performance. The code repository does not currently specify a top-level license; third-party PDF/data licenses and redistribution conditions must be handled separately. Official primary-source links are preserved instead of automatically mirroring restricted documents.

### A8 LOKO engineering harness (2026-10-22)

See [P25](docs/plan/P25_b2_e2_loko_harness.md) and [verification](docs/results/b2_loko_harness.md). `python -m geoml.b2_loko --config configs/b2_feat.json --data data/b2-feat-pilot --out runs/b2-loko-plan` creates a deterministic plan only. One CPU smoke fold is available with `configs/b2_loko_smoke.json` and `--smoke-holdout cw`, on an existing artifact with <=2 groups/role. Production scheduling and seed aggregation remain open; no production authorization or benchmark completion is implied.

### E3a EDSC binary baseline

`python -m geoml.b2_edsc --data data/b2-readiness-known --unknown-data data/b2-readiness-test --matched-data data/b2-readiness-matched --out runs/b2-e3a-edsc-smoke --smoke --with-cfar`
streams existing verified P20 residuals, freezes a clean-only val-calib alarm
threshold, and reports binary detection and unknown-positive rankings. Paths
refer to local artifacts outside Git. EDSC provides no class predictions or
OSCR; two-group smoke evidence cannot establish population Pfa or recognition
performance. See [P26](docs/plan/P26_b2_e3a_edsc_baseline.md) and
[bounded verification](docs/results/b2_edsc_baseline.md). XGBoost is the proposed
E3b follow-up; researcher and production gates remain pending.

### E3b expert-feature/XGBoost CPU baseline

With Python >=3.12, install the pinned CPU dependency with
`pip install -e '.[dev,ml,xgb]'` (xgboost-cpu 3.4.1 requires Python >=3.12).
`python -m geoml.b2_xgb --config configs/b2_xgb_smoke.json --data data/b2-readiness-known --unknown-data data/b2-readiness-test --matched-data data/b2-readiness-matched --out runs/b2-e3b-xgb-smoke --smoke --with-baselines`
streams 26 fixed observation-only features from existing P20 artifacts, fits
train only, selects one of two preregistered boosting prefixes on val-select,
then freezes clean-only val-calib alarms before test scoring. The binary
`1-P(clean)` score shares the EDSC/CFAR comparison contract; multiclass and
MSP/OSCR reports are separate. See [P27](docs/plan/P27_b2_e3b_xgboost_baseline.md)
and [bounded results](docs/results/b2_xgb_baseline.md). Tiny pilot values do
not establish recognition quality or population Pfa; no production run is implied.
