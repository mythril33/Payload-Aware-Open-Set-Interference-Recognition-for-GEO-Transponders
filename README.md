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

**Current research boundary:** Stage A is single-polarization/five known classes, with a small pilot. B1-dev/1 implements known-class holdout rejection with MSP and energy; B1-dev/2 adds unknown families, Mahalanobis and ranking metrics. D1-dev/1 adds calibrated dual-polarization observations and a controlled two-class leakage task. E1-dev/1 adds phase noise and two modulated-interference mechanisms in a separate three-class task. Full-data results and the unified eight-class dual-polarization open-set benchmark remain outstanding. The pilots are not evidence of field/deployment performance. The code repository does not currently specify a top-level license; third-party PDF/data licenses and redistribution conditions must be handled separately. Official primary-source links are preserved instead of automatically mirroring restricted documents.
