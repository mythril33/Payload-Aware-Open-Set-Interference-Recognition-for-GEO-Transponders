# Project audit — repository and scientific state

Date: 2026-10-21. Audited commit: `8e86287` (main = `claude/hopeful-feynman-f6nxfn` base) plus the
B2-feat/1 slice committed after this audit (see DURUM for the SHA). Method: read-only inspection of
the checkout, remote state, tests, source, documentation and result artifacts; full test run on the
unchanged HEAD (707 passed, 66.7 s, 4 CPUs, no GPU). Every row below names its evidence or is
marked **[VERIFY]**.

Status vocabulary: **VERIFIED** (tests/results in repo), **IMPLEMENTED-NOT-VALIDATED** (code exists,
no representative evidence), **SUPPORTED** (pilot-level evidence only), **ASSUMED**, **PLANNED**,
**BLOCKED**.

## 1. Repository state

| Item | Finding | Evidence |
|---|---|---|
| Branch / remote | `claude/hopeful-feynman-f6nxfn` tracks origin; clean tree at start | `git status`, `git branch -a` |
| Size | 168 tracked files; 12.3 k lines of Python (src + tests + scripts) | `wc -l` |
| Environment | Python 3.13; no venv in the fresh container; PyTorch CPU index blocked by network policy (403), PyPI allowed → torch 2.14.1+cu130 wheel runs on CPU | pip logs; `scripts/setup_cloud.sh` now falls back |
| Hardware | 4 CPUs, 15 GiB RAM, no GPU, ~31 GB free disk | `nproc`, `free`, `df` |
| Tests | 707 pass on HEAD; 743 after this slice and the reviewer fixes | pytest output |
| Data / runs | None committed (by design); `data/`, `runs/` ignored | `.gitignore` |

## 2. Implementation matrix

| Component | Module(s) | Status | Evidence / gap |
|---|---|---|---|
| DVB-S2 reference payload: IMUX/OMUX from ETSI tables, TWTA AM/AM–AM/PM digitized, Saleh, Rapp, OpenDPD memory polynomials | `geosim.payload`, `data/*.json`, `scripts/digitize_twta_figures.py` | VERIFIED (numerics), ASSUMED (OpenDPD back-off mapping) | `tests/test_chain.py`, `test_amplifier_families.py`; NPR check (`docs/results/npr_check.md`): 1.25 dB/dB slope; `dvbs2_lin` distortion floor known |
| Multicarrier SRRC waveforms, random plans, plan masks | `geosim.waveform`, `geosim.plan` | VERIFIED | `test_classes.py`, `test_dataset.py`; APSK ring start angles "from memory" (waveform.py docstring) **[VERIFY]**, no spectral effect |
| Uplink/downlink impairments, output-C/N convention | `geosim.scenario`, `geosim.dual` | VERIFIED | `test_dual_impairments.py` |
| Phase noise (Wiener, common LO) | `geosim.phase_noise` | VERIFIED; linewidths ASSUMED | `test_phase_noise.py`, P15 |
| Dual-pol Jones coupling, instrument response, independent-pilot calibration | `geosim.polarization`, `geosim.dual` | VERIFIED | `test_polarization.py`, `test_dual.py`; symmetric unitary coupling, not a lossy antenna model (docstring) |
| Interferers: CW, swept CW, unauthorized, overdrive, CuC, uplink ASI (sourced ITU geometry), downlink ASI | `geosim.interferers`, `events`, `asi` | VERIFIED (generation); distributions ASSUMED where marked | `test_events.py`, `test_asi.py`, `docs/results/asi_visibility.md` |
| DVB-CID generator (ETSI TS 103 129) | `geosim.cid` | VERIFIED vs standard test vectors; scrambler **[VERIFY]** | `test_cid.py`, DURUM |
| Unknown families (pulsed, bursts, wideband noise) | `geosim.unknowns` | VERIFIED (U1-dev) | `test_unknowns.py` |
| B2/1 frozen contracts: labels, roles, seeds | `geosim.b2_protocol` | VERIFIED | `test_b2_protocol.py` |
| B2-base/1 paired eight-class scenes, fixed-gain carrier absence | `geosim.b2_scenarios`, `b2_dataset` | VERIFIED (64-obs pilot) | P19, `docs/results/b2_base_pilot.md` |
| **B2-feat/1 observation-based cancellation residual (fifth channel)** | `geosim.cancellation`, `b2_dataset --cancellation` | VERIFIED (physics pilot); SUPPORTED (K9 at physics level) | P20, `docs/results/b2_feat_pilot.md`, `tests/test_cancellation.py` |
| Small ResNet, 2/4/5 channels, auxiliary plan-consistency head, center loss | `geoml.model`, `geoml.train` | VERIFIED (interfaces, save/load parity) | `tests/test_b2_ml.py`, `test_training.py` |
| Post-hoc scoring MSP/energy, Mahalanobis, known-only calibration, ranking metrics, OSCR | `geoml.openset`, `mahalanobis`, `calibration`, `openset_metrics` | VERIFIED (unit) | corresponding tests |
| CA-CFAR baselines (plan-aware/unaware) | `geoml.cfar` | VERIFIED (A1) | `test_ml.py` |
| Experiment runners A1, B1-dev, D1/E1-dev, R1-eval, A5 plan shortcut | `geoml.pipeline`, `experiment`, `dual_experiment`, `robustness`, `plan_shortcut` | VERIFIED (execution); results PILOT only | `docs/results/*` |
| **B2 frozen-role experiment runner** | `geoml.b2_experiment` | VERIFIED (execution on pilot) | `tests/test_b2_experiment.py`, `docs/results/b2_feat_pilot.md` |
| Test-only B2 families (pulsed, bursts, downlink ASI, `cid_overlay`, wideband noise) in the dual chain | — | PLANNED | generators exist for A1/E1; no B2 dual-pol adapter or role binding |
| Matched ASI ↔ unauthorized set (K17c), A5 dual-pol plan corruption, K17a sub-box | — | PLANNED | P18 §7a |
| EDSC baseline, SCF branch (A4b), expert features + XGBoost, FiLM (A7), LOKO (A8) | — | PLANNED | P18 §5, §8 |
| Full-scale Stage A, R1 and B2 production/training | — | BLOCKED on compute/approval | DURUM §5.2 (S1–S3, S8); B2 ≈ 20–25 core-hours generation [ESTIMATE] |
| DVB-S2 PL framing, dual-pol beyond basis coupling | — | PLANNED / deliberately deferred | DURUM §5.4 |

## 3. Scientific contribution matrix

| Claim | Status | Evidence | What is missing |
|---|---|---|---|
| C1: payload-realistic simulator with reference-derived TWTA and MUX | VERIFIED (implementation), ASSUMED (parameter ranges C/N, C/I, loading; linewidths; XPD except ground-station sources) | P2, P4, NPR check | External validation against measured transponder data (none available; DURUM §5.5) |
| C2: plan-conditioned dual-pol open-set recognition of eight known classes with rejection of unseen families | IMPLEMENTED-NOT-VALIDATED | B1/D1/E1 pilots at chance or near-chance; B2 pilot at chance | Full production, multi-seed training, unknown families, matched tests |
| C2a: CuC invisible in PSD at high C/I, visible in cancellation residual (K9) | SUPPORTED at physics level (8/8 pilot groups; median ΔPSD 0.99 → 6.46 dB) | `docs/results/b2_feat_pilot.md`, `cuc_visibility.md` | Learned-model evidence, C/I-binned curves on full data |
| C2b: ASI ↔ unauthorized confusable by design; level is the stronger cue | SUPPORTED (visibility measurement) | `asi_visibility.md` | Matched-level test set (K17c) |
| C3: payload gap depends on operating point; shows in false alarms rather than accuracy | SUPPORTED (pilot: M-lin 23.3 % vs M-nl4 1.7 % false alarm in IBO sweep) | `r1_pilot.md` | Full A1/R1 runs (S1, S2, S8) |
| Novelty "first to model payload + plan + dual-pol + open-set jointly" | ASSUMED pending full-text coverage | P1 §8 (7 closest works read) | Systematic search (B9 optional) |

## 4. Experiment completeness

| Experiment | Protocol | Scale run so far | Final? |
|---|---|---|---|
| Stage A five-class | A1 | 6 % pilot | No (S1/S2 on researcher's machine) |
| B1-dev/1, /2 | holdout, unknown families | 6 seeds | No |
| D1-dev/1, E1-dev/1 | dual-pol, events | 36 / 54 obs | No |
| R1-eval/1 + A5 | robustness | 120/60/30 + 4×60 | Pilot |
| B2-base/1, B2-feat/1 | frozen B2/1 known stage | 2 groups per role (64 obs) | No; `benchmark_complete: false` |

## 5. Reproducibility gaps

- Full-scale runs depend on the researcher's hardware; commands exist, outputs do not.
- Checkpoint/scorer/calibrator reuse is bound to source hashes: any source edit forces retraining
  (safe, but costly for the full B2 run; consider binding to a declared module subset later).
- `scripts/setup_cloud.sh` pinned the PyTorch CPU index, which this cloud environment blocks; a PyPI
  fallback was added. The CUDA wheel (~1.5 GB) is used on CPU here.
- `/usr/bin/time` is absent in the container; pilot cost was measured in-process (`resource`).

## 6. Data-leakage review

- Model inputs are limited to `spec`, `mask` and `residual`; `geoml.train._inputs` never reads `meta`,
  `active_carriers`, event parameters or labels (checked by reading; residual signature tested).
- The canceller processes every planned carrier regardless of actual transmission, so plan
  inconsistency enters the residual legitimately as an observation effect.
- Roles are disjoint and inside frozen ranges (`b2_experiment._check_roles`, tested). Mahalanobis uses
  train only; thresholds use val-calib known samples only; checkpoint selection uses val-select only.
- Residual risk: the paired-twin comparisons in `check_b2_cancellation.py` use event metadata for
  measurement; they are diagnostics, never model inputs. The independent reviewer confirmed no
  leakage path (see `REVIEWER_RED_TEAM.md`).

## 7. Physical-modelling concerns

- TWTA linearized curve is sparse (DURUM §5.5); `dvbs2_lin` has an artificial distortion floor.
- Jones coupling is unitary and symmetric; no antenna loss, no frequency-dependent XPD, no rain.
- Phase noise is an effective Wiener model, not a measured mask.
- Cancellation assumes exact plan frequency and MODCOD knowledge [ASSUMPTION], no equalization of
  MUX ISI, and one complex gain per snapshot: with the frozen 150 Hz effective linewidth the depth is
  capped at ≈ 21–25 dB regardless of C/N (reviewer finding, reproduced), so for C/N above ≈ 20 dB
  the algorithm rather than the noise floor bounds the residual.
- Overdrive label is IBO-defined and therefore not amplifier-independent (K17a sub-box planned).

## 8. Source-verification issues (carried from P16)

L1 Jammertest/Highway 2 licence wording, L7 Daoud title and TR 102 376-2 title, L10 satellite XPD
source, L12 near/far OOD grouping rationale remain **[VERIFY]**; CID scrambler has no test vector;
APSK ring start angles unchecked against EN 302 307-1 figures.

## 9. Compute and storage

- Pilot B2-feat/1: 3.8 s per observation on this CPU (2 threads), 585 MiB peak, 0.39 MiB stored
  per observation. Full B2/1 (≈ 21 300 observations): ≈ 20–25 core-hours and ≈ 8.3 GB stored
  [ESTIMATE]; raw IQ is not stored (would be ≈ 170 GB).
- Training of 3 views × 3 seeds × (1 + 7 LOKO) on 12 000 five-channel observations is for the
  researcher's GPU (K17).

## 10. Prioritized next steps

1. Researcher decision K18: confirm center-loss weight 0.005 and plan BCE weight 1.0 (P18 §10).
2. B2 test-only families and `cid_overlay` through the dual chain with role binding (P18 §3), then the
   matched ASI set (K17c) as its own generator; extend `b2_experiment` with per-family metrics.
3. EDSC baseline reusing `geosim.cancellation`; A5 dual-pol plan corruption; K17a sub-box tables.
4. Measure a 20-group B2-feat/1 production slice to firm up the cost estimate; then full production.
5. Stage A / R1 full runs on the researcher's machine (S1, S2, S8) for C3.
