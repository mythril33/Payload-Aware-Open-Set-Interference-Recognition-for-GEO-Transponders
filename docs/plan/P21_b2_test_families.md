# P21 — B2 test-only families, K17b training augmentation and open-set evaluation

Date: 2026-10-21. Parent protocol: frozen [B2/1](P18_b2_protocol.md) (§3 families and groups, §4 roles and
RNG namespaces, §7 metrics, §7a K17b, K17d). Builds on [P19](P19_b2_base_observations.md) (B2-base/1) and
[P20](P20_b2_cancellation_residual.md) (B2-feat/1). New artifact stage: **B2-test/1**
(`test_only_families`). `benchmark_complete` stays `false`: the matched ASI ↔ `unauthorized` set (K17c),
LOKO rotations, the remaining baselines and full-scale production are still outstanding.

## 1. Why this is the critical-path dependency

Every open-set number of the final benchmark — per-family AUROC/AP/OSCR/FPR@95TPR, thresholded rejection,
the benign CID control — needs the test-only families generated through the *same* dual-pol chain,
groups, calibration and fifth channel as the known classes. Without them the learning slice of P20 can
only report known-class metrics with `null` open-set entries.

## 2. B2-test/1 contract

| Family | Pre-registered group (P18 §3) | Generator | Injection | Expected decision |
|---|---|---|---|---|
| `pulsed` | near | `geosim.unknowns.unknown_interferer` (U1-dev/1 pulsed CW; group-specific seed) | co uplink | unknown |
| `intermittent_bursts` | near | same module, burst CW | co uplink | unknown |
| `adjacent_satellite_downlink` | near | **new** `geosim.asi.adjacent_satellite_downlink`: identical draws to the known uplink ASI (geometry, C/I_psd, rate, roll-off, placement with 20–80 % plan overlap, modulation); only the injection point differs (K17d) | receiver feed after physical downlink mixing, bypassing the payload; scaled by the wanted feed power (P15 convention) | unknown |
| `wideband_noise` | equivalence-limited | U1-dev/1 band-limited noise, 60–90 % of the transponder | co uplink | unknown (reported separately) |
| `cid_overlay` | benign | `geosim.cid.cid_overlay(..., active=...)`: ETSI TS 103 129 DVB-CID under every **transmitted** planned co-pol carrier | co uplink | **clean** |

Shared with the group's eight known variants (`geosim.b2_scenarios._shared_scene`): operator plans, link
draws (nominal IBO, C/N), carrier/noise RNG streams, phase realizations, missing-carrier state and the
receiver calibration of the bound known artifact. Event parameters use their own RNG namespace
`[group, 1830, family_index]` (P18 §4). Only groups of the frozen `test` role (3 200 000–3 200 499) are
accepted; the generator refuses any other role and the reader rejects artifacts that contain a `train`,
`val-select`, `val-calib` or `test-matched` directory.

Implementation conventions recorded here (not protocol changes):

- A CID rides on its host carrier, so a muted (missing) planned carrier carries no CID; its identifier
  draws are still consumed so the other CIDs are unchanged. Metadata records `host_active` and
  `n_transmitted`.
- The downlink ASI power is `mean_psd_plan · Rs · 10^(−C/I_psd/10)` relative to a unit wanted load and is
  scaled by the realized wanted feed power at the injection point, i.e. the same "C/I_psd relative to the
  plan's mean PSD" definition as the known uplink ASI.
- Temporal families must show active and inactive retained snapshots (inherited U1 visibility rule).

Binding: the request stores the known artifact's protocol, data fingerprint, request fingerprint, test
groups and calibration; the test stage copies that calibration file and refuses a different physical
configuration or cancellation setting. Arrays: `spec[N,2,128,512]`, `mask[N,2,512]`, `family` (index into
`TEST_FAMILIES`), `seed`, `plan_consistency`, plus `residual[N,128,512]` when the known stage is
B2-feat/1. Per-record validation mirrors P19/P20 (plans, activity, nominal scene, event conventions per
family, cancellation provenance, pairing across families).

```bash
python -m geosim.b2_test_dataset --out data/b2-test-pilot --known data/b2-feat-pilot \
    --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_test_families.py --known data/b2-feat-pilot --test data/b2-test-pilot --out runs/b2-test-pilot/family_check.json
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --unknown-data data/b2-test-pilot --out runs/b2-feat-pilot-os
```

## 3. K17b training-time plan-shift augmentation (now implemented)

`TrainConfig.plan_shift_fraction` (B2: **0.15**) and `plan_shift_max_hz` (B2: **0.5 MHz**): for the
selected fraction of each training batch the operator-plan masks are rebuilt from the sample's plans
with all carriers moved by Δf ~ U(−0.5, +0.5) MHz (continuous; 187.5 kHz bins, so ≈ 2.7 bins). The
spectra and the residual are untouched: this models an operator plan with a wrong frequency reference
while the transmitted signal is unchanged (K17b). Both feeds' masks move together [implementation
choice: one frequency reference per operator plan database]. Validation, calibration and test masks are
never shifted (tested). The augmentation precedes the existing mirror/roll so masks and spectra stay
aligned. Zero shift reproduces the stored float16 masks within 0.02 dB (tested). Default 0 keeps every
historical configuration unchanged.

## 4. Open-set evaluation (`geoml.b2_experiment --unknown-data`)

With the frozen checkpoints, Mahalanobis scorers and val-calib thresholds of each view, the test-only
families are scored and reported per family and per pre-registered group: `ranking_metrics` (AUROC, AP,
OSCR AUC, FPR@95TPR; unknown positive; known test events as negatives; ties grouped), rejection rate
at the calibrated threshold, and the alarm rate of the clean-vs-event detector. Pooled numbers use the
near families only; `wideband_noise` is listed separately; `cid_overlay` reports clean acceptance
(predicted `clean` and accepted), `carrier_under_carrier` call rate and rejection as unknown. The
runner refuses a test-only artifact bound to a different known dataset or with different physics or
canceller settings, and requires its groups to be known test groups. Nothing is tuned on these families.

## 5. Evidence

See [the pilot report](../results/b2_test_pilot.md). Summary: the B2-test/1 pilot (2 test groups,
10 observations) generated and resumed with verified binding to the B2-feat/1 pilot; the family physics
check and the open-set run executed end to end. With 16 training observations the models are at chance,
so every open-set number of the pilot is execution evidence only.

## 6. Limitations and next steps

- The matched ASI ↔ `unauthorized` set (K17c, groups 3 300 000–3 300 149) has its own generator still to
  write; `test-matched` remains reserved.
- The 11.7 GHz sensitivity row of K17d (downlink ASI geometry at the downlink frequency) is not generated;
  the family uses the known 14.25 GHz draw as the protocol's primary definition.
- LOKO rotations (A8), EDSC/XGBoost baselines, A5 dual-pol plan corruption at test time and A7 FiLM are
  not implemented.
- Full-scale production: 500 test groups × 5 families ≈ 2 500 additional observations
  (≈ 2.5–3 core-hours with cancellation) [ESTIMATE].
