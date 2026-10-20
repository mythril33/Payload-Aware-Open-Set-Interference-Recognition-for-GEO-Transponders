# Payload-Aware Open-Set Interference Recognition for GEO Transponders

GEO bent-pipe transponderindeki girişimi, operatörün downlink spektrum izlemesinden tanıyan derin öğrenme çalışması. Ders projesi; makaleye genişletilecek.

- Plan ve kararlar: `docs/plan/` (`00_ana_plan.md` ile başlayın)
- Simülatör: `src/geosim/` — şartname `docs/plan/P2_sistem_modeli.md`, kullanım `docs/plan/P4_simulator_tasarim.md`

```
pip install -e .[dev]
pytest
```

Simülatör, DVB-S2 referans transponderinden türetilmiş verilerle birlikte gelir (`src/geosim/data/`). Ham ETSI dosyaları depoda değildir; yeniden üretmek için `docs/plan/kaynak_transponder_modeli.md` içindeki bağlantılardan indirip `data/` altına koyun ve `scripts/` altındaki iki betiği çalıştırın.

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

**Current research boundary:** Stage A is single-polarization/five known classes, with a small pilot. Full-data results and Stage B unknown-class rejection are not yet available. The pilot is not evidence of field/deployment performance. The code repository does not currently specify a top-level license; third-party PDF/data licenses and redistribution conditions must be handled separately. Official primary-source links are preserved instead of automatically mirroring restricted documents.
