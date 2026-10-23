# B2 E3a context ledger — 2026-10-22

This ledger records the audited starting point, delivered engineering scope and
scientific boundaries for the first EDSC slice. Detailed measured verification
is reported separately; historical pilots are never fresh recognition evidence.

## Verified repository and remote evidence

- Working repository: `mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders`.
  After `git fetch origin main`, local HEAD and `origin/main` both resolved to
  `2cc473fad07fc08984c17e212a06ddb26409a9cd`. No reset was used. The dedicated branch
  is `feature/b2-e3a-edsc-baseline`.
- [PR #10](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/10)
  merged at `2026-10-22T08:24:23Z` with that merge SHA. Its head was
  `a138608faed6beae16c24170ccec06aa6dba3f9b`.
- GitHub API `get_pr_info`, `fetch_commit_workflow_runs` and
  `fetch_workflow_run_jobs` independently verified E2
  [Actions run 39741030340](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39741030340)
  as `completed/success`. Job `119698005413`, including installation, gate checks,
  syntax compilation and repository tests, succeeded. This establishes E2 CI
  status only. The E2 local suite's 978 passes in 1014.36 s remain historical
  evidence from [its report](../results/b2_loko_harness.md).
- The PR #10 discussion/review timeline returned no comments. A repository issue
  search for K18 returned no results. Neither absence is evidence of approval;
  the versioned decision ledger still governs.

## Sources read and implemented boundaries

The audit read `AGENTS.md`, `CLAUDE.md`, `README.md`, `DURUM.md`, frozen
[P18](../plan/P18_b2_protocol.md), [P20](../plan/P20_b2_cancellation_residual.md),
[P23](../plan/P23_b2_production_readiness.md), [P24](../plan/P24_b2_e1_streaming_loader.md),
[P25](../plan/P25_b2_e2_loko_harness.md), the machine-readable readiness ledger,
agent briefs, relevant source/tests and the cancellation, matched, streaming,
LOKO and production-budget result records.

| Verified implementation at the base | Consequence for E3a |
|---|---|
| P20 `geosim.cancellation.cancel_planned_carriers(iq, plan, config)` is observation-only `obs-cancel/1`; B2-feat/1 stores residual PSD | Consume the saved residual. Do not rerun oracle cancellation or substitute P21b `B2-features/1` / `observed_receiver` |
| E1 `geoml.b2_stream` verifies descriptors, checksums, role ranges, per-record provenance and index consistency; reads one shard/window | Reuse E1. Keep only bounded PSD chunks and small per-sample score/index arrays |
| `geoml.b2_experiment` binds known/test/matched fingerprints, physics and cancellation; has group-aware rates and paired matched evaluation | Preserve these bindings and P18 groups; expose binary detection/ranking without inventing class predictions |
| `geoml.calibration` uses higher empirical quantiles and strict `score > threshold` rejection, with inclusive acceptance | Freeze and document a clean-only alarm rule, achieved counts and score direction; existing known-class rejection thresholds are a different operating point |
| `geoml.cfar` computes local linear-power ratios, two extrema and clean-validation standardization | Existing CA-CFAR is not automatically a directly comparable B2 clean-Pfa operating point; use common samples/calibration and label the score definition |
| E2 `geoml.b2_loko` filters a holdout before fit/calibration and supports one capped CPU fold | Production dispatcher, full sweep and cross-seed aggregation remain missing |

At the audited base EDSC and XGBoost were unimplemented. E3a implements the first
binary EDSC slice in `geoml.edsc`, `geoml.b2_edsc` and `geoml.b2_edsc_metrics`,
under [EDSC/1 / P26](../plan/P26_b2_e3a_edsc_baseline.md). XGBoost, full dual-pol A5 residual recomputation, production
LOKO scheduling/aggregation, approved full-scale results and field validation
remain open. Older prose in historical P20/P23/results may describe their own
starting point; current implementation status is in DURUM and the gate ledger.

## Existing bounded artifact inventory

Read-only checks with `/workspace/.venvs/geosim/bin/python` called
`open_b2_known`, `open_b2_test` and `open_b2_matched` on the following existing
artifacts. All passed current E1 validation and have stored residuals. These
are real small simulated observations, distinct from stand-in test fixtures.

| Path (outside Git) | Stage | Samples / groups / shards | Verified identity |
|---|---|---|---|
| `data/b2-readiness-known` | B2-feat/1 | 16 / 2 / 2 in each of train, val-select, val-calib, test; 64 total | `dcffb26470837a5340277d5ca9af7e3f7377cad9c809e5fd37d05769c95bb83b` |
| `data/b2-readiness-test` | B2-test/1 | 10 / 2 / 2, test only | `3b49f0b324e5a5e9653760d1fc99bfcfa81c08871dd71fad119793c19aae8d8c` |
| `data/b2-readiness-matched` | B2-match/1 | 6 / 2 / 2, test-matched only | `0bb04632b4fa8d4e2db1346f3f8cd2df306398d60d4bc7a50c6e3919d89aa434` |

Verification calls took 0.285, 0.050 and 0.033 s respectively; the process took
4.48 s including imports. Only **two clean calibration observations** exist in
this pilot. Their empirical false-alarm count has 50 percentage-point resolution;
a nominal 5% target cannot imply a precisely estimated population Pfa. EDSC/1
requires two distinct clean scenario groups as an engineering guard, not
statistical sufficiency; smaller calibration populations fail closed.
The README's historical `data/b2-feat-pilot` path is absent in this checkout.
`data/b2-features-*` artifacts belong to the incompatible parallel P21b stage.

## Scientific constraints and unresolved questions

- Preserve frozen classes, all paired variants, role/seed ranges and observation
  grid: 128 snapshots, 512 frequency bins at 187.5 kHz spacing from a 96 MHz
  monitor. P20 residual uses 3072 guarded samples/11 Welch segments versus the
  spectra's 4096 samples/15 segments, so identical grid/density units do not imply
  identical estimator variance.
- Detector inputs may include receiver-observed residual PSD and documented
  observable power references/operator plans. Labels, true activity, symbols,
  realized IBO/XPD/C-I, source geometry and simulator event parameters may only
  define evaluation strata or targets after scores/thresholds are frozen.
- Calibration is clean known `val-calib` only. All test/test-matched samples,
  unknown families and benign CID controls are excluded from fitting, threshold
  selection and feature choices. Higher scores mean more anomaly-like.
- Unknown-positive ranking uses all known test variants as negatives, with
  denominators explicit. P18 near families are pooled; equivalence-limited
  `wideband_noise` remains separate and benign `cid_overlay` is not an unknown.
  Binary anomaly detection cannot support eight-class accuracy or OSCR.
- K17c matched ASI/unauthorized is a controlled intervention: common C/I_psd
  in U(4,13) dB, bins 4–7, 7–10 (primary), 10–13. Keep complete pairs and compare
  detection, not invented origin/authorization predictions. Frequency placement
  still differs by definition.
- Group bootstrap fixes the detector and threshold; it does not cover threshold
  estimation uncertainty, physical-model uncertainty or training-seed variation.
  Two-group intervals are descriptive smoke outputs, not performance evidence.
- The residual includes decision errors, phase noise, payload distortion,
  leakage and truncation. Its 150 Hz effective-linewidth depth ceiling is about
  21–25 dB. A rising residual is observable evidence, not a uniquely identifiable
  source, authorization status or receiver-noise-only quantity.

## Delivered E3a engineering and bounded evidence

- [P26](../plan/P26_b2_e3a_edsc_baseline.md) defines the deterministic normalized
  whole-band residual-energy score, its direction, diagnostic regions, clean-only
  higher-quantile threshold and shared comparison contract. Train/val-select fit
  no EDSC state. Source versions and P20 cancellation remain unchanged.
- Binary metrics retain unknown-positive ranking, counts, explicit null reasons,
  group-bootstrap pairing, natural versus matched separation and report-only
  condition metadata. CA-CFAR and neural score bundles must share evaluation rows,
  provenance and clean-calibration operating rule; a known-acceptance neural
  threshold cannot be substituted.
- Focused verification: **46 passed in 15.49 s**. Independent read-only re-review:
  **46 passed in 15.89 s**. Material findings covering complete evaluation groups,
  known-artifact binding/receiver calibration and scorer identity, threshold,
  protocol and denominator checks were resolved; no material blocker remained.
- A single capped smoke consumed the existing real artifacts above: **64 known,
  10 test-only and 6 matched observations**, with **two clean calibration samples**.
  Wall time **4.431314 s**, peak RSS **251600 KiB**. No RF generation or model/GPU
  training was performed. This is execution evidence only.
- Full repository suite: **1023 passed, 1 skipped, 0 failures in 376.44 s**;
  subprocess wall **378.396740513 s**, peak RSS **1281420 KiB**, exit code 0.
  The existing E1 test
  `tests/test_b2_stream.py::test_streaming_peak_memory_stays_below_the_whole_dataset_footprint`
  skipped because `/proc/self/clear_refs` peak-RSS reset is unsupported in this
  environment (`legacy.json` reported `peak_reset: false`). E1's comparative
  memory regression is therefore not revalidated here; measured E3a smoke RSS
  is a separate result. The baseline's historical 978 passes remain separate.
- Independent raw-NPZ arithmetic audit via `scripts/check_b2_edsc_smoke.py`
  recomputed **32 scores** with maximum stored-score discrepancy
  **2.13e-14 dB** and threshold discrepancy **7.11e-15 dB**, confirming alarm
  counts. Subprocess wall **0.316785 s**, peak RSS **27736 KiB**. This validates
  implementation arithmetic, not recognition quality.
- Exact commands and smoke limitations belong in
  [the results report](../results/b2_edsc_baseline.md). E3b XGBoost and approved
  production science remain outstanding.

## Research decisions and resource boundary

The machine-readable [gate ledger](../plan/b2_readiness_gates_2026-10-21.json)
retains **K18**, **K17d**, and **OBS-CANCEL/2** as `PENDING_RESEARCHER`, with
`approval: null`. K18's canonical P20 summed-distance 0.005 convention differs
from P21b's mean-distance 0.01 convention; this engineering slice cannot settle
that decision. K17d's 35/500 affected co-feed-loss groups and drift reporting
proposal remain unresolved. Phase tracking requires a separate cancellation
version and researcher decision.

Only unit tests, existing small artifacts and explicitly capped CPU smoke work
are within scope. No full B2 generation, GPU fitting, full LOKO or repeated
smoke sweep is authorized. The historical full-generation estimate is 21,350
observations, 23–30.2 h and 8.7 GB, not a measured production run. Keep generated
data, calibrators/checkpoints and environments out of Git. Preserve
`benchmark_complete=false`; no automatic merge or force push.
