# B2 K17d / M-14 — co-feed missing-carrier level-drift disclosure

**Generated/verified:** 2026-11-03 from the committed metadata-only `docs/results/k17d_drift_audit.json` at baseline main `8aa6645718def6c49ca6ae6653bbb2cf2cb91b16`. **No test observation, waveform, spectrogram, checkpoint, final scoring or production artifact was opened or generated.** This is an engineering disclosure, not a new measurement, a scientific approval or compute authorization.

## Populations and mandatory reporting

| Population | Scenario groups | Reporting status |
| --- | ---: | --- |
| Frozen B2-test/1 headline | **500** | Retain without outcome-driven removal |
| Co-feed missing-carrier level-drift subset (pol == 0) | **35** | Predeclared, separately labelled sensitivity/diagnostic row |
| Complement excluding precisely those 35 identities | **465** | Mandatory K17d sensitivity row |
| All missing-carrier groups (both feed polarizations) | **78** | Metadata count only; 35 co + 43 cross |
| Cross-feed drops (pol == 1) | **43** | Included in the 465; co-feed reference remains unchanged in this approximation |
| Groups with no missing-carrier event | **422** | Included in the 465 |

The other mandatory D-1 exposure-excluded rows (498 test / 148 matched) are **independent** of K17d. The four historically exposed scenario IDs are specified in `docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md`; the 35 co-feed IDs below do not include the exposed test IDs. Never describe the preserved test population as pristine.

## Audit method and checked bounds

For each `pol == 0` metadata entry, the expected downlink level drift is

```text
co_active_power = 1 - dropped_power_fraction
downlink_drift_db = 10 * log10(1 / co_active_power)
```

The input JSON contains **78 distinct group IDs**, exactly 35 with `pol=0` and 43 with `pol=1`. Every per-row drift agrees with the formula to <1e-9 dB; co-feed active power agrees with `1 - dropped_power_fraction` to <1e-9. Cross-feed rows have a unity co-feed reference within this model. Source summary statistics were independently recomputed with linear-interpolation quantiles and agree within 1e-10 dB.

| Co-feed drift (35 groups) | dB |
| --- | ---: |
| Minimum | 0.141579 |
| Median (p50) | 0.706711 |
| p90 | 2.926892 |
| Maximum | 5.912132 |

These values quantify a **simulated metadata-level** shift of the downlink-event reference, not measured RF signal strength, model-recognition quality, or uncertainty. The committed audit notes that weak cross-feed coupling at 30 dB XPD is ignored (estimated <0.01 dB); that approximation is not newly validated here.

## Full predefined 35-group table

| Frozen scenario group ID | Dropped planned-power fraction | Remaining co-feed power | Downlink drift (dB) |
| ---: | ---: | ---: | ---: |
| 3200035 | 0.401219 | 0.598781 | 2.227319 |
| 3200055 | 0.743677 | 0.256323 | 5.912132 |
| 3200072 | 0.193820 | 0.806180 | 0.935680 |
| 3200073 | 0.058647 | 0.941353 | 0.262475 |
| 3200075 | 0.055922 | 0.944078 | 0.249921 |
| 3200081 | 0.236519 | 0.763481 | 1.172018 |
| 3200112 | 0.508244 | 0.491756 | 3.082506 |
| 3200159 | 0.150176 | 0.849824 | 0.706711 |
| 3200161 | 0.220220 | 0.779780 | 1.080279 |
| 3200176 | 0.032074 | 0.967926 | 0.141579 |
| 3200230 | 0.449429 | 0.550571 | 2.591869 |
| 3200239 | 0.367187 | 0.632813 | 1.987248 |
| 3200240 | 0.136508 | 0.863492 | 0.637419 |
| 3200257 | 0.101866 | 0.898134 | 0.466590 |
| 3200262 | 0.049979 | 0.950021 | 0.222670 |
| 3200279 | 0.037097 | 0.962903 | 0.164175 |
| 3200296 | 0.425482 | 0.574518 | 2.406966 |
| 3200300 | 0.264975 | 0.735025 | 1.336982 |
| 3200301 | 0.525667 | 0.474333 | 3.239168 |
| 3200314 | 0.165988 | 0.834012 | 0.788277 |
| 3200318 | 0.247013 | 0.752987 | 1.232127 |
| 3200327 | 0.098427 | 0.901573 | 0.449990 |
| 3200331 | 0.076591 | 0.923409 | 0.346058 |
| 3200333 | 0.255506 | 0.744494 | 1.281386 |
| 3200352 | 0.462160 | 0.537840 | 2.693472 |
| 3200362 | 0.411456 | 0.588544 | 2.302207 |
| 3200363 | 0.101972 | 0.898028 | 0.467101 |
| 3200366 | 0.700440 | 0.299560 | 5.235169 |
| 3200372 | 0.093751 | 0.906249 | 0.427524 |
| 3200394 | 0.098069 | 0.901931 | 0.448265 |
| 3200413 | 0.065380 | 0.934620 | 0.293649 |
| 3200447 | 0.107193 | 0.892807 | 0.492422 |
| 3200470 | 0.043595 | 0.956405 | 0.193582 |
| 3200472 | 0.066494 | 0.933506 | 0.298830 |
| 3200498 | 0.084790 | 0.915210 | 0.384791 |

## Interpretation and fail-closed boundary

- Headline evaluation, if separately authorized, retains all **500** B2-test groups. Reporting must also identify the **35** shifted co-feed groups and the complementary **465** groups, with consistent frozen scores and thresholds.
- This table is derived from the historical committed audit, *not* a re-derivation of separately generated production metadata. E12 D-8 still requires a fail-closed production identity/metadata cross-check before any authorized final test evaluation. That check remains **NOT RUN**.
- This report is not an invitation to select a subset after inspecting classifier outcomes or to alter frozen `B2-test/1` role definitions.
- Authoritative decisions: `docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md` (K17d A+C), `docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md` (D-1, D-8); original audit `docs/research/B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md` (M-14).
