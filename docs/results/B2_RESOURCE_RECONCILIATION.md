# B2 resource reconciliation — current campaign and source register

Date: 2026-11-04. Baseline: `3f26393`. **Reporting/arithmetic only; no new
measurement, reservation, resource ceiling or execution authorization.**
`benchmark_complete=false`. The older
[E11-B reconciliation](../operations/B2_RESOURCE_BUDGET_RECONCILIATION.md)
remains a historical register. This update ties its estimates to committed JSON,
adds the current **15-fit minimum** and includes the later E15 storage correction.
The [M-11 erratum](B2_P1_RESOURCE_ERRATA.md) and immutable approved records retain
their identities.

## 1. Sources and interpretation

JSON paths below use slash-separated keys (array indices start at zero).

| ID | Committed source | What it establishes |
|---|---|---|
| A | [Matched profile](b2_profile_matched_20_cancel.json) | Historical single-process measurement: 20 groups, 60 observations, 4-CPU container, two BLAS threads; not a current-host or full-scale measurement |
| B | [E8 resource budget](b2_e8_resource_budget.json) | Analytic counts, assumed throughput and extrapolations; status `ARITHMETIC_NOT_A_RESERVATION` |
| C | [E7 training proposal](../plan/b2_e7_training_proposal.json) | Origins of width-8 6 h allowance and incomplete 5.88 h loader estimate; historical proposal, not current approval |
| D | [C2 experiment matrix](../plan/b2_c2_experiment_matrix.json) | 9 canonical + 6 required matched dual + 6 optional matched co fits; analytic sample passes; status `UNAPPROVED_NOT_EXECUTABLE` |
| E | [E15 resource/backup assessment](../operations/B2_E15_RESOURCE_AND_BACKUP_ASSESSMENT.md) | Explicit array/artifact bytes, startup free-space rule, CID correction and backup staging arithmetic; no qualified host |

**Measured** means a value already recorded by the historical pilot, not a command
run for this update. **Analytic** means arithmetic conditional on the stated
counts/layout. **Extrapolation** scales small-pilot measurements or assumptions;
its range is not a confidence interval and need not contain actual runtime.
GPU throughput, full-epoch memory and target-host loader rate remain unmeasured.

## 2. Generation and storage

| Quantity | Value | Evidence class and source pointer |
|---|---:|---|
| Historical matched profile | 60 observations; 261.989 s wall; 300.194 CPU-s | Measured; A `/n_observations_generated`, `/wall_s`, `/cpu_s` |
| Historical steady-state observation cost | 4.3634 s wall; 3.0031 s simulator; 1.3384 s cancellation | Measured; A `/per_observation/{wall_s,simulate_s,cancellation_s}` |
| Historical generator peak RSS | 600.949 MiB | Measured; A `/peak_rss_mib`; not a production-memory guarantee |
| Historical artifact | 24,362,235 B total; 406,037.25 B/observation | Measured; A `/artifact_bytes`, `/bytes_per_observation` |
| Frozen production inventory | 18,400 known + 2,500 test-only + 450 matched = **21,350 observations** | Analytic; B `/generation/observations`; E inventory table; 2,450 distinct groups |
| E8 single-process generation band | 23.0 / 26.6 / 30.2 h (low/central/high) | Historical extrapolation; B `/generation/wall_hours_single_process`; not a fresh measurement |
| CID-aware recomputation | 23.1194 / 26.5944 / 30.0694 h | Analytic extrapolation; E: `(20,850 × s + 500 × 8)/3600`, `s = 3.8/4.4/5.0`; separate basis from the rounded E8 band |
| Generation wall/core allowances | 36 wall h / 42 core-h | Unapproved planning allowances; B `/generation/{reserved_wall_hours,reserved_core_hours}`; key names do not establish a reservation |
| Float16 arrays | 8,438,886,400 B = 8.4388864 GB = 7.859325409 GiB | Analytic; E: `395,264 × 21,350`; B `/storage/float16_array_gb` rounds to 8.44 |
| Supervisor artifact allowance | 8,668,100,000 B = 8.6681 GB = 8.072797209 GiB | Pilot-derived estimate; E: `406,000 × 21,350`; B `/storage/artifact_estimate_gb` rounds to 8.7 |
| Startup data-volume free space | **36,378,455,600 B = 33.880076930 GiB** | Analytic rule from E: 25 GiB remaining reserve + 1.1 × artifact allowance; **25 GiB initially free is insufficient under that rule** |
| Independent backup | 9 GB old proposal; 12 GB later proposal | Unapproved assumptions; B `/storage/backup_gb_proposed`, E backup table; neither is verified capacity |
| Retain old backup while staging a new copy | At least 17.3362 GB before overhead | Analytic; E: `2 × 8.6681 GB`; a 12 GB device cannot hold both estimated full copies |

GB = 10^9 bytes; GiB = 2^30 bytes. These are per-copy values unless stated
otherwise. C2 matched arms reuse the same dataset and add no generation.
Backup/restore, verification, quarantine and retries need explicit time and disk
allowances. E15 also shows that a first-shard timing pass can still exceed the
proposed 36/42 h totals; a pass does not establish whole-run feasibility.

## 3. Training: distinguish 9, 15 and 21 fits

Recipe arithmetic: width 16, 30 epochs, 12,000 train observations and 1,200
val-select observations per fit. One fit uses 360,000 train sample passes and
36,000 val-select forward passes. These are planned workloads, not completed fits.

| Campaign | Fits | Train passes | Val-select forward passes | Indicative compute + synchronous loader h |
|---|---:|---:|---:|---:|
| Canonical `co`, `dual`, `dual_residual` × seeds 0/1/2 | 9 | 3,240,000 | 324,000 | 9.95–21.87 |
| Required matched `dual_noplan`, `dual_planmask` × seeds 0/1/2 | 6 | 2,160,000 | 216,000 | 6.63–14.58 |
| **Minimum campaign covering H1/H2/H3** | **15** | **5,400,000** | **540,000** | **16.58–36.45** |
| Optional matched `co_noplan`, `co_planmask` × seeds 0/1/2 | 6 | 2,160,000 | 216,000 | 6.63–14.58 |
| All declared controls | 21 | 7,560,000 | 756,000 | 23.22–51.03 |

Counts come from D `/roster/declared_fits` and `/sample_passes`; the required count
is `/roster/declared_fits/required_for_h3_primary`. Training hours come from B
`/widths/16/campaigns/0/gpu_compute_plus_loader_hours_screening`; rows other than
nine fits scale its **rounded** endpoints by `fits/9`, then round to two decimals.
The same five-channel cost assumption is used for every view. This is only
screening arithmetic; different input widths, matched-recipe preprocessing and
GPU utilization require measurements. It is not an upper bound or a new ceiling.

The nine-fit band comprises 2.98–14.89 h assumed compute and 6.97 h synchronous
loader, from B `/widths/16/campaigns/0/{gpu_pure_compute_hours_screening,
synchronous_loader_hours}`. The compute band scales a width-8 **assumed**
200–1,000 samples/s by a MAC ratio of 3.31. Loader cost assumes 93 s per epoch.
Full-precision components were rounded independently, so displayed endpoints
need not add exactly. Neither component has been timed on the target GPU host.

The band omits a qualified budget for GPU val-select forward computation,
train-only Mahalanobis fitting, calibration, freeze, evaluation, backup and
interrupted-fit restarts. Those are not licensed as "negligible" by this table.
LOKO's 21/63 fits are a different campaign from C2's 21 fits: B
`/widths/16/campaigns/1` and `/2` use 10,500 train observations per fit and
20.32–44.64 / 60.96–133.93 screening hours. They remain outside the 15-fit minimum.

## 4. M-11 arithmetic and unresolved resources

The old 6 GPU-h number was a width-8 planning allowance; B `/withdrawn_figure`
explicitly withdraws its application to width 16. C
`/parameters/expected_sample_passes_and_wall_clock/value/synchronous_loader_estimate`
records an older **5.88 h loader-only** estimate and the mistaken "7.0 h ...
roughly 1.9x" wording. The corrected comparisons are:

- `7.0 / 6 = 1.1667`, approximately **1.17×**, for the rounded complete loader estimate.
- `11.5 / 6 = 1.9167`, approximately **1.92×**, for the older width-8 compute-plus-loader upper estimate.
- The width-16 nine-fit **total** screening band is 9.95–21.87 h; the current
  **15-fit total** is separately extrapolated above. Neither is a measured GPU duration.

No immutable proposal or scientific approval JSON was rewritten. Remaining
dependencies are a designated and qualified generation/GPU/backup host,
end-to-end loader and GPU measurements, verified independent backup/restore,
run-specific resource ceilings and separate DR-04/DR-05/final-read authorization.
These estimates cannot establish a delivery date or recognition quality.

## 5. Reproduce the arithmetic without running an experiment

From the repository root; reads committed summary JSON only:

```bash
python - <<'PY'
import json
from pathlib import Path

budget = json.loads(Path('docs/results/b2_e8_resource_budget.json').read_text())
matrix = json.loads(Path('docs/plan/b2_c2_experiment_matrix.json').read_text())
main = budget['widths']['16']['campaigns'][0]
counts = matrix['roster']['declared_fits']
assert counts['approved_primary_fits'] == main['fits'] == 9
assert counts['required_for_h3_primary'] == 15
assert counts['total_fits'] == 21
for fits in (9, 6, 15, 21):
    train = fits * matrix['sample_passes']['per_fit']
    val = fits * main['val_select_forward_passes'] // main['fits']
    band = [round(h * fits / main['fits'], 2)
            for h in main['gpu_compute_plus_loader_hours_screening']]
    print(fits, train, val, band)
n = budget['generation']['observations']
assert n == 18400 + 2500 + 450 == 21350
artifact = 406000 * n
print('array bytes:', 395264 * n)
print('artifact bytes:', artifact)
print('startup GiB:', (25 * 2**30 + 1.1 * artifact) / 2**30)
print('two backup copies, GB:', 2 * artifact / 10**9)
print('CID-corrected hours:', [(20850 * s + 500 * 8) / 3600
                               for s in (3.8, 4.4, 5.0)])
print('M-11 ratios:', 7 / 6, 11.5 / 6)
PY
```
