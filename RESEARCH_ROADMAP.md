# Research roadmap

Status date: 2026-10-28, branch `claude/serene-johnson-urtxgj` (base main
`8911fee`). This file tracks the route from the current state to publication.
It summarizes and links evidence; it never replaces the protocol documents
(`docs/plan/P18_b2_protocol.md` and the frozen stages) or the researcher
decision records. Where this file and a protocol disagree, the protocol wins.

The repository holds two tracks:

- **Track A — GEO/B2 main project** (`src/geosim`, `src/geoml`, `docs/`,
  `paper/`): payload-aware open-set interference recognition for GEO
  transponders. Heavily governed; full-scale experiments are gated.
- **Track B — `learning/rfml-basics/`**: a self-contained, ungated synthetic
  benchmark (modulation classification, RF fingerprinting, open-set scores
  under hardware impairments) with a Streamlit UI and a pre-registered
  multi-seed campaign. It shares no code or data with Track A and makes no
  GEO claim; it exists for learning and as a small publishable benchmark
  study.

## 1. Completed and verified (evidence in the linked files)

### Track A

- Payload simulator with ETSI-derived IMUX/OMUX and TWTA curves, Saleh/Rapp/
  OpenDPD amplifier models, dual-pol coupling, interference and unknown
  families — unit- and physics-tested (`docs/research/PROJECT_AUDIT.md` §2;
  provenance: `docs/research/ETSI_DERIVED_DATA_PROVENANCE.md`).
- Frozen data stages B2-base/1, B2-feat/1, B2-test/1, B2-match/1, verified at
  pilot scale only.
- Bounded training/evaluation stack (ResNet 2/4/5-channel, MSP/energy/
  Mahalanobis, known-only calibration, OSCR/AUROC; EDSC and XGBoost
  baselines), CPU caps 2 groups/role, 2 epochs, width 8
  (`src/geoml/b2_execution.py`).
- **Real measured-data results** (`docs/results/public_data_baselines.md`):
  GNSS LC receiver-strength AUROC 0.9842 (detections 55/76, false alarms
  0/44, bootstrap CI [0.9599, 0.9978]); FIOT clean-distance AUROC 0.8578
  (105/162, FA 3/81); the negative FIOT RGB result (AUROC 0.2590) is kept.
  Coverage caveat: only 120/159 LC test records are non-empty.
- Simulation diagnostics: NPR slope 1.248 dB/dB, ASI median C/I 20.3 dB,
  cancellation depth 12.78–16.47 dB, analytic ceiling 21.74 dB
  (`docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md`).
- Synthetic ML pilots are **at chance or negative** (12.5% known-test
  accuracy on 16 observations; EDSC unknown AUROC 0.344). Pilots prove
  execution, not recognition quality.
- Two manuscript drafts in `paper/`: the observability/reproducibility paper
  (V1, 14 audited citations, claim–evidence manifest) and the GEO
  experimental paper whose Results §7.2 is entirely NOT RUN.

### Track B (this branch)

- `rfml` package (signals with IQ imbalance / Rapp PA / phase noise / DC /
  CFO, device-level splits, MLP/CNN1D/ResNet1D, MSP / distance /
  Objectosphere, known-val threshold calibration), 165 passing tests,
  Streamlit UI, lessons 01–04 with full-run results.
- Pre-registered multi-seed campaigns 1 and 2
  (`learning/rfml-basics/experiments/PREREGISTRATION.md` and
  `PREREGISTRATION_V2.md`, `run_campaign.py`, `run_campaign2.py`); results
  in `learning/rfml-basics/experiments/campaign*/` and
  `VALIDATION_REPORT.md`. Outcomes: H1/H2/H3/H7 supported, H8 weakly
  supported, H4/H5/H6 honestly negative; all output-space scores below
  chance, Euclidean distance best, Objectosphere gain shown to be
  outlier-similarity transfer.
- Benchmark paper draft v1.0 with six generated figures
  (`learning/rfml-basics/paper/`), every number traceable to the committed
  aggregates.

## 2. Remaining work, prioritized

### P0 — researcher decisions and gates (block everything full-scale; not executable by an agent)

| Item | Gate / record |
| --- | --- |
| DR-04 full B2 generation (21,350 observations) | `docs/plan/B2_E8_GO_NO_GO.md` (NO-GO), `docs/plan/B2_E15_DR04_DECISION_DOSSIER.md` |
| DR-05 GPU qualification and the 15 mandatory fits | `docs/plan/B2_C2_COMPARATIVE_EXPERIMENTS.md` §9 (no executor; GPU path never run) |
| Primary scorer designation (Mahalanobis is only a recommendation) | B2_C2 §7, decision D-4 |
| Final held-out read authorization (test set non-pristine; sensitivity rows mandatory) | E12 compute gates, decision D-1 |
| Authorship, venue, ETSI written permission record, Fraunhofer licence clarification, SmartSpace access request | `paper/README.md` blockers; `docs/plan/P8_dis_veri.md` |

### P1 — executable now, no approval needed (next concrete steps on Track A)

1. Reconcile status documents: CLAUDE.md's readiness paragraph (PASS 31/FAIL 1)
   contradicts `B2_E8_GO_NO_GO.md` (36/0/19/1) and the current
   `B2_E6_PRODUCTION_READINESS_CHECKLIST.md` (39/0/16/1); K18/K17d/OBS-CANCEL/2
   read PENDING in CLAUDE.md but were approved at E9. One truth, one pointer.
2. Apply documented errata at the source: the M-11 arithmetic error via the
   checklist generator (`scripts/b2_production_preflight.py`), the M-6
   no-uncertainty note near atlas line 162 (erratum, not a hash-locked edit).
3. Produce the M-14 K17d 35-group drift table from the committed
   `docs/results/k17d_drift_audit.json` (metadata only).
4. Add the ETSI provenance statement (with its explicit placeholder) to both
   manuscripts and `paper/geo_b2_evidence.json`; rerun
   `paper/validate_geo_b2.py` and `paper/audit_evidence.py`.
5. Update the E9 publication checklist with the E10/E12 dispositions
   (it still reads "Critical 0/2 closed", which is outdated).
6. Build the consolidated resource table (E9 checklist §7) from existing
   budget JSONs — no new measurement.

### P2 — after gates open (Track A science)

- DR-04 generation → 15 mandatory fits (canonical 9 + matched dual 6) →
  frozen-threshold evaluation → H1 (cross-pol), H2 (observed residual),
  H3 (plan access) matched contrasts → C3 payload-gap 2×2 design →
  A5 counterfactuals on real checkpoints → held-out read, once.
- Only then can `paper/geo_b2_manuscript.md` §7.2 be filled; until then the
  GEO paper remains a methods/design manuscript.

### P3 — publication steps

- Track A observability paper: resolve P0 licence/authorship items, choose
  venue honestly (reproducibility/methods scope; `paper/literature_audit.md`
  already judges it insufficient for a new-recognizer claim).
- Track B benchmark paper (`learning/rfml-basics/paper/`): campaign results,
  verified references, limitations; realistic venues are a workshop /
  education / reproducibility track, an open-source benchmark venue, or an
  arXiv preprint. No acceptance guarantee is claimed.

## 3. Risks

- **Status-document divergence** (P1.1) invites wrong decisions; worst case,
  someone relies on CLAUDE.md's stale gate summary.
- **Provenance gaps** before submission: no written ETSI permission record;
  72 MHz FIR taps unchecked; Saleh coefficients unvalidated (M-12); Fraunhofer
  licence conflict (CC BY-SA vs BY-NC-SA).
- **Test exposure**: two observation IDs were exposed pre-freeze (D-1); the
  mandated sensitivity analysis must accompany any held-out result.
- **At-chance pilots**: no evidence yet that the B2 recognizer works at scale;
  the publication plan must not assume positive results.
- **Process**: PRs #21/#27/#43 merged with red or pending CI; 7 K18
  golden-capture tests skip on CI runners.
- Track B: synthetic-only; conclusions do not transfer to measured RF.

## 4. Success criteria

- Track A paper submitted only when: gates DR-04/DR-05 resolved by the
  researcher, results tables populated from actually-run experiments,
  provenance records complete, and `benchmark_complete` honestly set.
- Track B paper: every number traceable to
  `experiments/campaign/aggregate.json` under a pre-registered criterion;
  all tests green; reproduction = one documented command.
