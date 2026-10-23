# B2 E3a EDSC baseline — bounded engineering verification

Date: 2026-10-22. Base remote `main` and local HEAD were verified as
`2cc473fad07fc08984c17e212a06ddb26409a9cd` after fetching; branch
`feature/b2-e3a-edsc-baseline`. Definition:
[P26 EDSC/1](../plan/P26_b2_e3a_edsc_baseline.md). Audited context and prior
E2 merge/CI evidence: [context ledger](../research/b2_e3a_context_ledger.md).
Machine-readable measurements and EDSC reporting strata are retained in
[`b2_edsc_baseline.json`](b2_edsc_baseline.json).

This slice verifies implementation, isolation, reproducibility and bounded
execution. The two-group smoke observations cannot establish recognition
performance, a population false-alarm rate or a ranking of methods.
`benchmark_complete=false`; researcher and production-compute gates are unchanged.

## Implemented and checked

`geoml.edsc` computes one deterministic whole-transponder residual-energy
score on the canonical 128 × 512 grid. The anomaly evidence is the stored P20
`obs-cancel/1` residual; the observed co-pol planned-core PSD supplies only
power normalization. The scorer's inputs are arrays, not simulator metadata.
Core/non-core scores are diagnostics and do not select bands or thresholds.

`geoml.b2_edsc` uses E1 verified shard streaming, validates the canonical
known stage and bound test/matched artifacts, and freezes all clean-only
`val-calib` thresholds before evaluation scoring. Train/val-select are
validated but not scored or fitted by EDSC. Execution caps are 32 groups/role,
256 observations/shard and 1000 bootstrap draws; the executed smoke is capped
at two groups/role. Whole-role spectra are never concatenated. Output reuse
checks source/configuration/artifact identities and checksums and recomputes
the calibration from the same allowed observations before test scoring.

`geoml.b2_edsc_metrics` reports binary alarm rates, unknown-positive ranking,
fixed report-only operating strata, complete matched-pair differences and
whole-scenario bootstrap intervals. Multiclass accuracy, class predictions
and OSCR are explicitly null with reasons. Optional planned/blind CA-CFAR
uses the same calibration population, threshold rule and evaluation rows.
The comparison interface rejects incompatible populations, score directions,
provenance and known-acceptance thresholds. No neural fitting/comparison or
XGBoost fitting was performed.

## Environment and executed commands

Environment: Linux 6.18.55 x86_64, glibc 2.41, three allocated CPUs;
Python 3.12.14, NumPy 2.5.4, SciPy 1.18.1, PyTorch 2.14.1+cpu and
pytest 9.1.1. Execution used the prepared
`/workspace/.venvs/geosim/bin/python`; OMP/OpenBLAS/MKL threads were capped at
two. No GPU was used. The test suite includes its existing bounded fixtures
and physics tests; this task launched no full generation or training job.

Final focused command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /workspace/.venvs/geosim/bin/python -m pytest -q \
    tests/test_b2_edsc.py tests/test_edsc.py tests/test_b2_edsc_metrics.py
```

Result: **46 passed in 15.49 s** (pytest timer), exit 0. The subprocess
measurement including interpreter/import startup was **16.722984 s**, peak
RSS **557,920 KiB** (544.84 MiB). Evidence was captured in
`/tmp/b2-e3a-evidence/focused.json` and `focused.log` and summarized in the
committed JSON note. During test-driven development the initial missing-module
collection failed as expected; an intermediate integration run had two
failures and 39 passes. Those implementation issues were fixed before the
final passing run; no failing check is represented as a pass.

Tests exercise role and known-only calibration isolation, deterministic
thresholds/ties, score monotonicity and shared gain invariance, unsupported
power normalization, empty/insufficient calibration populations, missing
residuals/stage mismatch, corrupt disk artifacts, within-group and cross-stage
operator-plan mismatch, full provenance binding, strict JSON and output reuse,
paired/bootstrap denominators, empty/one-group intervals and comparison-bundle
population/score-identity checks. Disk integration tests use the real writer,
validator and streaming reader with **stand-in physics and cancellation**;
they are separate from the real small physical artifacts used below.

Full repository command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m pytest -q
```

Result: **1023 passed, 1 skipped, 0 failed in 376.44 s** (pytest timer),
exit 0. Subprocess wall including startup was **378.396741 s** (6 min 18 s),
peak RSS **1,281,420 KiB** (1251.39 MiB). Measurements were captured in
`/tmp/b2-e3a-evidence/full.json` and `full.log` and retained in the committed
JSON note. The one skip was the existing
`tests/test_b2_stream.py::test_streaming_peak_memory_stays_below_the_whole_dataset_footprint`:
this environment could not reset the process peak through
`/proc/self/clear_refs`; the test's `legacy.json` records `peak_reset=false`.
Thus the suite passed all supported checks, but the E1 comparative peak-memory
regression was not re-established here. The separately reported EDSC smoke RSS is
a measured process high-water mark, not a substitute for that comparison.

## Strictly capped real-artifact smoke

Command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /workspace/.venvs/geosim/bin/python -m geoml.b2_edsc \
    --data data/b2-readiness-known --unknown-data data/b2-readiness-test \
    --matched-data data/b2-readiness-matched --smoke --with-cfar \
    --bootstrap 200 --out runs/b2-e3a-edsc-smoke
```

Exit **0**, subprocess wall **4.431314 s**, peak RSS **251,600 KiB**
(245.70 MiB). The runner's internal wall timer was **1.309500 s**, excluding
interpreter and module-import startup; it reports the same process high-water
RSS. Peak RSS includes imports and verification, not just score arrays, and
is not a measured production memory ceiling. Measurement source:
`/tmp/b2-e3a-evidence/smoke.json`; raw strict JSON/calibration/scores/state
remain outside Git under the run directory.

Existing **real simulated physical observations** were reused; no RF data
were generated by this command. Known data contain 64 observations: two
groups × eight variants in each of train, val-select, val-calib and test.
Test-only data have ten observations (two × five families); matched data
have six (two complete triples). Only two clean val-calib observations
calibrate the threshold. Thus 32 observations were scored for calibration
and known evaluation, plus ten test-only and six matched observations;
train/val-select were only verified. No observations were silently truncated.

The run identity is
`7527661bce5b090e477a609a88ad42f91c002e527a13789895999b1c833935bd`.
The three artifact identities are recorded in the context ledger and the
committed JSON; the full source hashes and identities are in the raw results.

## Smoke outputs, not performance evidence

The EDSC alarm threshold was **−16.3357547775 dB**, the higher empirical 95th
percentile of the two clean calibration scores, with alarm strictly above
threshold. Nominal Pfa remains **5%**; achieved calibration alarms were
**0/2**. Empirical rate resolution is **50 percentage points**, so this is
not evidence that the actual population false-alarm rate is 5% or zero.

| EDSC population | Alarms / denominator | Scenario-bootstrap 95% interval |
|---|---:|---|
| Known test clean | 1/2 | [0, 1] |
| Known test non-clean events | 13/14 | [0.8571, 1] |
| Near unknown families pooled | 4/6 | [0.3333, 1] |
| Benign CID control | 1/2 | [0, 1] |
| Equivalence-limited wideband noise | 2/2 | [1, 1] |

Known per-class detections were CW **1/2** and **2/2** for each of swept CW,
unauthorized, overdrive, cross-pol, ASI and carrier-under-carrier. Each family
has only two scenarios. The degenerate [1,1] intervals arise because every
resampled observed group has an alarm; they do not establish perfect population
sensitivity. The JSON retains all configured-IBO, C/N and C/I strata, including
empty and one-group entries with null intervals and explicit counts.

For the pooled near unknowns versus all 16 known test observations,
unknown-positive AUROC was **0.343750** (bootstrap [0.1250, 0.4167]), AUPR
**0.280612** ([0.2157, 0.3500]), and FPR@95TPR **0.937500**
([0.8750, 0.9375]). These ranking outputs compare unknown identity against
all known scenes, including known interference; they are distinct from
clean-versus-event anomaly detection and do not calibrate the operating
threshold. Low ranking values do not justify reversing the score direction.

| Family | Alarms / n | Unknown AUROC | Unknown AUPR | FPR@95TPR |
|---|---:|---:|---:|---:|
| pulsed | 1/2 | 0.218750 | 0.104167 | 0.8750 |
| intermittent_bursts | 1/2 | 0.187500 | 0.100490 | 0.9375 |
| adjacent_satellite_downlink | 2/2 | 0.625000 | 0.326923 | 0.6875 |
| wideband_noise (separate) | 2/2 | 0.687500 | 0.226190 | 0.3125 |
| cid_overlay (benign) | 1/2 | null | null | null |

The matched set produced **0/2 ASI** and **0/2 unauthorized** detections;
its clean controls had **0/2** alarms. The paired unauthorized-minus-ASI
alarm difference was **0**, with a descriptive two-group bootstrap interval
[0,0]. There was one pair in `[4,7)` and one in `[7,10)`; their intervals
are null because each bin has one group. `[10,13]` is empty, with null
rates and intervals. This is an execution check of pairing and bins, not a
claim that EDSC distinguishes or reliably detects these causes. Natural-test
ASI and unauthorized each had 2/2 alarms but represent different levels and
carrier-width distributions; no natural-versus-matched performance conclusion
is supported by these denominators.

CA-CFAR planned/blind scorers used the same two clean calibration rows and
0.95-higher/strict-`>` rule; both achieved 0/2 calibration alarms. Their
known-test clean alarm counts were respectively **1/2** and **2/2**, and event
detections **11/14** and **11/14**. Near-unknown AUROC/AUPR/FPR95 were
**0.270833/0.217444/0.8125** for planned CFAR and
**0.541667/0.327859/0.6875** for blind CFAR. These are common-interface smoke
outputs, not a scientifically supported ordering against EDSC. Neural
95%-known-acceptance rejection thresholds were not reused as clean-Pfa
operating thresholds; no neural score bundle was claimed evaluated.

## Independent read-only review and limits

A separate agent reviewed the changed source and adversarial tests read-only,
checking truth leakage, clean-only calibration, score direction/Pfa, paired
uncertainty, comparable populations, cancellation assumptions and provenance.
The review prompted stronger known-artifact bindings (protocol, request,
calibration and test groups), mandatory method-specific scorer identity, and
metric-population validation in comparison bundles. These changes were
covered by negative tests before final verification. Re-review found **no
remaining material blocker**; the reviewer independently ran the same focused
suite: **46 passed in 15.89 s**. This is independent engineering review within
the agent workflow, not an external scientific endorsement.

The reviewer also recomputed all 32 evaluation scores from raw NPZ arrays
without importing detector helpers: maximum discrepancy **2.13e-14 dB**;
the threshold and 0/2 calibration, 1/2 test-clean and 13/14 event alarm counts
were independently confirmed. The retained arithmetic audit was executed as
`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 /workspace/.venvs/geosim/bin/python scripts/check_b2_edsc_smoke.py`:
exit 0, subprocess wall **0.316785 s**, peak RSS **27,736 KiB**. See the
[review record](../research/b2_e3a_review.md) for its scope and timing boundaries.

The residual includes receiver/cancellation errors, phase noise, payload
distortion and leakage; its `obs-cancel/1` phase-noise depth ceiling remains
about 21–25 dB. The core reference can change with an interferer or missing
planned carrier, and whole-band averaging can dilute short/local events.
Two-group bootstrap intervals condition on the already frozen scorer and
threshold and omit calibration/physical-model uncertainty. No eight-class
prediction, multiclass accuracy, OSCR, field validation or full benchmark
completion is inferred.

K18, K17d and OBS-CANCEL/2 remain **pending researcher decisions**. Full B2
generation, GPU training and full LOKO remain blocked and were not run.
The next bounded engineering step is the [P26 §9](../plan/P26_b2_e3a_edsc_baseline.md#9-proposed-e3b-xgboost-follow-up)
E3b observation-only expert-feature/XGBoost interface, with train-only fitting,
separate selection/calibration, pinned dependency/budgets and the same verified
binary score-bundle comparison contract. Production work requires the existing
researcher/compute decisions; this report changes no approval.

## Final delivery verification — 2026-10-23

Remote `main` was fetched again and remained at `2cc473fad07fc08984c17e212a06ddb26409a9cd`.
The proposed delivery contains exactly the 17 reviewed E3a paths. Source and
test files match the earlier staged full-suite contents; every current
`geoml`/`geosim` Python source hash matches the recorded smoke provenance.
The only later-added executable is the retained independent arithmetic audit,
which was checked separately. No new detector experiment, RF waveform generation, model
training or E3b work was started for delivery.

The same focused command above was repeated against the final proposed code:
**46 passed in 8.78 s**, exit 0; process wall **9.632499 s**, peak RSS
**557,860 KiB**. The retained `scripts/check_b2_edsc_smoke.py` command was
repeated: exit 0, process wall **0.473946 s**, peak RSS **27,736 KiB**, with
the same arithmetic discrepancies and alarm counts. These are final checks
of existing evidence, not another detector experiment.

`python -m compileall -q src tests scripts`, staged/unstaged whitespace checks,
strict JSON and saved-output checksum/provenance checks passed. The P18 diff
is one additive implementation-log row; researcher approval objects equal
the base commit exactly and `benchmark_complete=false`. Code/test SHA-256 values and exact
measurements are retained in the JSON report. The earlier full-suite result
is retained separately from the later final-delivery repeat below.

The new PR-head Actions result is recorded with the exact commit, run and job
links in the draft PR description after publication; historical E2 Actions
evidence in the readiness ledger does not stand in for E3a CI. A green E3a
head satisfies the engineering/CI prerequisite for proposing E3b, but neither
a draft PR nor CI authorizes merge, research decisions or production work.

The complete local suite was subsequently repeated on the published implementation
commit `ec47a90b9e8f9ed756bee822d1c2b548830951ee`:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m pytest -q -rs
```

Result: **1023 passed, 1 skipped, 0 failed in 343.50 s**, exit 0;
subprocess wall **346.210088 s**, maximum process RSS including descendants
**1,272,224 KiB**. The `-rs` output explicitly reports the existing E1 RSS
test skipped at `tests/test_b2_stream.py:421` because this runner cannot reset
`/proc/self/clear_refs`. It is not reported as passed. This repeat changes
no scientific smoke result and launches no production job.

The implementation commit was normally pushed to the feature branch and
[draft PR #11](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/11)
was opened against unchanged `main`. This results-only follow-up records
the completed local repeat. The final PR-head Actions evidence is maintained
in the PR description with exact run/job/commit links; the PR remains draft
and unmerged.
