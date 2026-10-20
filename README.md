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

## Research dossier (2026-10-20)

This is an evolving research project, **not** a completed dual-polarization, eight-class open-set system.

- [P1 literature review and novelty audit](docs/plan/P1_literatur.md)
- [P8 external dataset/source and license audit](docs/plan/P8_dis_veri.md)
- [P9 roadmap and risks](docs/plan/P9_yol_haritasi.md)
- [Proposed open-set benchmark and identifiability protocol](docs/research/open_set_protocol.md)
- [Primary/original source URLs and provenance](sources/ORIGINALS.md)
- [Original user-supplied project brief — text transcription](sources/original_proposal.md)
- [Literature bibliography (BibTeX)](references/references.bib)
- [Detailed current Stage A status](docs/plan/DURUM.md) and [pilot-only results](docs/results/pilot_A.md)

**Current research boundary:** Stage A is single-polarization/five known classes, with a small pilot. The B1-dev/1 extension implements known-class holdout rejection with MSP and energy; full-data results and the complete Stage B benchmark remain outstanding. The pilot is not evidence of field/deployment performance. The code repository does not currently specify a top-level license; third-party PDF/data licenses and redistribution conditions must be handled separately. Official primary-source links are preserved instead of automatically mirroring restricted documents.
