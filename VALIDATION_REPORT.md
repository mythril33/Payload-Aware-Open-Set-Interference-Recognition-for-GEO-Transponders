# Validation report

Date: 2026-10-28, branch `claude/serene-johnson-urtxgj`. This report records
what was actually executed and verified in this session, with reproduction
commands. It covers Track B (`learning/rfml-basics/`) in full and points to
the main project's own evidence records for Track A; it asserts nothing that
was not run here.

## 1. Test suites executed

| Suite | Command | Result |
| --- | --- | --- |
| Track B full suite | `cd learning/rfml-basics && .venv/bin/python -m pytest -q` | 187 passed (after the campaign-2 code landed; 166 before it) |
| Campaign runner smokes | `pytest -q tests/test_campaign.py tests/test_campaign2.py` (subprocess, quick scale) | passing (included above) |

Track A's suite was not rerun in this session; the latest recorded full CI is
run 40389841693 (107 E4 + 4,867 passed / 1 failed / 7 environment skips; the
single failure was a stale footprint assertion, repaired per
`docs/plan/DURUM.md` 2026-10-26). Seven K18 golden-capture tests skip on CI
runners (`tests/test_b2_train_diagnostics.py`).

## 2. Multi-seed campaign (Track B, pre-registered)

Plan: `learning/rfml-basics/experiments/PREREGISTRATION.md` (written before
the runs). Command:

```bash
cd learning/rfml-basics
.venv/bin/python experiments/run_campaign.py --scale full --seeds 0 1 2 3 4
```

Provenance: commit `c9e9c9f`, Python 3.13.17, PyTorch 2.14.1 (CPU,
4 threads), NumPy 2.5.4. Wall time 1045 s. Failures: none (all 25 stage runs
completed). Full numbers:
`learning/rfml-basics/experiments/campaign/aggregate.json` and
`aggregate_summary.md` (generated).

### Headline results (mean ± sd over seeds 0–4)

| Stage | Metric | Value |
| --- | --- | --- |
| Open set | CE+MSP AUROC | 0.343 ± 0.061 (below chance in every seed) |
| Open set | CE+distance AUROC | 0.779 ± 0.013 |
| Open set | Objectosphere+MSP AUROC | 0.518 ± 0.030 |
| Open set | Unknown rejection at 0.95 target (MSP / distance / Objectosphere) | 0.034 / 0.511 / 0.158 |
| Modulation (impaired) | CNN1D test accuracy (chance 0.25) | 0.755 ± 0.041 |
| Modulation (impaired) | MLP test accuracy (train 0.889 ± 0.138 — memorisation) | 0.252 ± 0.008 |
| Modulation (ideal ablation) | CNN1D test accuracy | 0.770 ± 0.021 |
| Fingerprint | impaired devices (chance 0.10, n = 600/seed) | 0.250 ± 0.039 |
| Fingerprint | ideal-device control | 0.098 ± 0.015 (at chance) |

### Pre-registered hypotheses (criterion: predicted sign in ≥ 4/5 seeds)

| Hypothesis | Mean paired diff | Positive seeds | Verdict |
| --- | --- | --- | --- |
| H1 distance − MSP AUROC | +0.437 | 5/5 | **Supported** |
| H2 Objectosphere − MSP unknown rejection | +0.124 | 5/5 | **Supported** (with the pre-registered 8PAM/4PAM caveat) |
| H3 fingerprint impaired − ideal accuracy | +0.152 | 5/5 | **Supported**; control at chance |
| H4 modulation ideal − impaired CNN accuracy | +0.015 | 3/5 | **Not supported** — honest negative; prediction did not replicate |

## 2b. Campaign 2 (scorer bench, pre-registered amendment)

Plan: `experiments/PREREGISTRATION_V2.md`, committed (`99dd4f2`) before any
campaign-2 run. Command: `experiments/run_campaign2.py --scale full --seeds
0 1 2 3 4`. Provenance: commit `2dbc00e`, wall time 1093 s, zero failures
(the first attempt was killed by a container restart and the campaign was
rerun whole; determinism is test-verified). Code passed two independent
reviews (leakage/protocol with a perturbation test on unknown inputs, and
numerics with brute-force OSCR cross-checks) with zero findings.

| Hypothesis | Mean paired diff | Positive seeds | Verdict |
| --- | --- | --- | --- |
| H5 Mahalanobis − Euclidean AUROC | −0.030 | 0/5 | **Not supported** — Mahalanobis consistently worse |
| H6 energy − MSP AUROC | −0.027 | 2/5 | **Not supported** — all output-space scores below chance |
| H7 4PAM rejection, 8PAM-arm − 16PSK-arm | +0.402 | 5/5 | **Supported** — Objectosphere gain is similarity transfer |
| H8 CE+MSP AUROC, low − high SNR band | +0.042 | 4/5 | **Supported, weak** — within one sd, curve not monotone |

Internal consistency check: CE+MSP per-seed AUROCs in campaign 2 equal
campaign 1's exactly (same seed → same CE model), confirming end-to-end
determinism across the two campaigns.

### Reading rules

- AUROC positive class = unknown; larger score = more unknown-like. Known
  test n = 400 and unknown test n = 200 frames per seed; frames of one
  device are correlated, so the seed is the unit of replication.
- The Objectosphere comparison (H2) is optimistic by design: the auxiliary
  outlier 8PAM resembles the unknown 4PAM. Recorded in the pre-registration.
- All data are synthetic (`rfml/signals.py`); no claim transfers to measured
  RF.

## 3. Interactive UI and lessons

- `app.py` (Streamlit): verified earlier on this branch via
  `streamlit.testing.v1.AppTest` on all four stages plus a headless server
  health check (HTTP 200). Not re-run in this session.
- Lessons 01–04 run as scripts and are covered by subprocess tests
  (`tests/test_lessons_experiments.py`) that also assert lesson output equals
  the `rfml.experiments` functions at the same seed, so the UI and the
  lessons cannot drift apart.

## 4. Track A evidence pointers (not rerun here)

- Measured-data results: `docs/results/public_data_baselines.md` (LC AUROC
  0.9842 with FA 0/44; FIOT 0.8578; negative RGB 0.2590 kept).
- Simulation diagnostics: `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md`.
- Synthetic ML pilots: at chance (e.g., 12.5% on 16 observations) — pilots
  prove execution, not recognition quality.
- Gates: full generation DR-04 NO-GO (`docs/plan/B2_E8_GO_NO_GO.md`); GPU
  and the 15 mandatory fits DR-05; held-out read not authorized;
  `benchmark_complete=false`. These block any Track A performance claim.

## 4b. Peer review of the paper (subagent panel)

Three independent reviewers (methods/statistics; a scripted number audit of
every value in the paper against the aggregates, 135 checks; claims versus
evidence) examined draft v1.0. Verdicts: PASS, PASS, FAIL — 27 findings, of
which 18 were applied, 4 deferred (immutable pre-registration texts and
follow-up experiments), 0 rejected. The substantive corrections:

- Campaign 1's CE+MSP vs CE+distance comparison used **separately trained**
  models (seed offsets 0/1/2); the "identical network" wording was wrong and
  is fixed — the paired same-model claim belongs to campaign 2 only.
- **Pre-registration timing, stated honestly:** campaign 1's plan file was
  committed (`07792b9`, 21:49:06Z) about 3.5 minutes *after* the campaign's
  first output existed (21:45:36Z); the plan text was written beforehand,
  but the auditable record only proves post-start commitment. Campaign 2's
  pre-registration commit (`99dd4f2`) verifiably precedes its runs.
- The Objectosphere arms differ in training seed as well as outlier pool
  (offsets +101/102/103); "differ only in the aux pool" was corrected and
  outlier frame counts (800/400/400) added.
- H4's dispersion corrected to ±0.054; "every output-space score"
  universalization narrowed to the three scores tested; the He et al.
  citation moved off the skip-free CNN1D; missing n values and the
  CCR@FPR=0.1 column added; sign-test p for 4/5 (0.375) stated.
- The number audit found exactly one numeric error in 135 checks (the H4
  sd last digit); all six figures regenerate **byte-identically** from
  `make_figures.py`, and the raw seed-0 score file used by Figures 2 and 6
  is now committed.
- Historical note: in aggregates produced before 2026-10-28T23:30Z the
  provenance field `started_utc` was recorded at aggregation time (end of
  run), not start; the runners now record the true start. Committed
  aggregates were not altered.

## 5. Known issues found and their disposition

| Issue | Disposition |
| --- | --- |
| CLAUDE.md readiness paragraph contradicts the current checklist and E9 approvals | Reported in `RESEARCH_ROADMAP.md` P1.1; not edited here (governance file) |
| Lesson 02's memorisation diagnostic lost in the experiments refactor | Fixed on this branch (`train_accuracy` restored, commit 8911fee) |
| Binomial SE values in lesson 03 docstring | Fixed during alignment (correct formula and values) |
| `requirements.txt` streamlit removal by a review agent | Reverted (streamlit required by `app.py`) |
| Reference caveats | [8] page range and [10] DOI must be re-checked on IEEE Xplore before submission (noted in `references.bib`) |

## 6. Reproduction quickstart

```bash
cd learning/rfml-basics
bash setup.sh --test                 # venv + deps + full test suite
.venv/bin/python experiments/run_campaign.py --scale full --seeds 0 1 2 3 4
.venv/bin/streamlit run app.py       # interactive UI
```
