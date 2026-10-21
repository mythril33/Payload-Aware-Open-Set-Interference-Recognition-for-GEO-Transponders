# B2-test/1 pilot: test-only families, K17b augmentation and the first open-set run

Date: 2026-10-21. Stage `B2-test/1` bound to the `B2-feat/1` pilot; `benchmark_complete: false`.
Scope: execution and physics of the five test-only families and of the frozen-role open-set
evaluation. **No recognition-quality or open-set-quality claim.** Machine-readable records:
[family physics](b2_test_family_check.json), [open-set run](b2_test_pilot.json).

## Data

| Artifact | Groups | Observations | Note |
|---|---:|---:|---|
| B2-feat/1 pilot (known, 4 roles) | 2 per role | 64 | [P20 pilot](b2_feat_pilot.md) |
| B2-test/1 pilot (test role only) | 2 | 10 | 5 families × 2 groups; 4.0 MiB; same receiver calibration as the known artifact; resume verified |

Generation of the ten test-only observations with cancellation took about 40 s on 2 threads
(≈ 4 s per observation; `cid_overlay` ≈ 8 s because it synthesizes one CID per planned carrier).

## Family physics against the clean twin (same group, plans, carriers, noise, phase)

ΔPSD = family minus clean, mean over the event band; "residual" uses the stored fifth channel.

| Family | Group | n | Median ΔPSD in band (spectrum) | Median ΔPSD in band (residual) | Mean co-pol ΔPSD |
|---|---|---:|---:|---:|---:|
| pulsed (CW, duty 36–41 %) | near | 2 | 0.10 dB | 0.87 dB | 0.00 dB |
| intermittent_bursts | near | 2 | 0.16 dB | 1.80 dB | 0.00 dB |
| adjacent_satellite_downlink (C/I_psd 26–27 dB) | near | 2 | 0.06 dB | 1.21 dB | 0.02 dB |
| wideband_noise | equivalence-limited | 2 | 0.20 dB | 3.51 dB | 0.43 dB |
| cid_overlay (6 and 4 transmitted CIDs, −21.5…−27.5 dB) | benign | 2 | n/a (under every carrier) | n/a | 0.00 dB |

Reading: at the drawn C/I values all four unknown families are nearly invisible in the raw
spectrum (≤ 0.2 dB) and become visible only after the planned carriers are cancelled (0.9–3.5 dB),
the same mechanism as for `carrier_under_carrier` in P20. The time-gated families (pulsed, bursts)
are additionally identifiable from their snapshot occupancy, which the spectrogram keeps as a time
axis. The downlink ASI family differs from the known uplink ASI only by injection point, as K17d
requires; whether a model can tell them apart is the pre-registered question of P18 §6.
Two groups cannot establish distributions; these are execution-level measurements.

## Open-set run (execution evidence only)

`configs/b2_feat.json` with the K17b augmentation enabled (15 %, ±0.5 MHz): 3 epochs, batch 8,
width 8, seed 0, center-loss weight 0.005, independent plan-consistency head. Three matched views,
16 training observations. Thresholds from val-calib known samples (95 % acceptance), alarm threshold
from val-calib clean scenes (Pfa 5 %). Test-only families scored with the frozen checkpoints.

| View | Known accuracy (n = 16) | Pooled-near AUROC MSP / energy / Mahalanobis (n = 6 unknown vs 16 known) | cid_overlay accepted as clean (MSP) |
|---|---:|---|---:|
| co | 12.5 % | 0.51 / 0.58 / 0.58 | 0 % (n = 2) |
| dual | 12.5 % | 0.53 / 0.41 / 0.51 | 0 % (n = 2) |
| dual_residual | 12.5 % | 0.37 / 0.51 / 0.50 | 100 % (n = 2) |

All models are at chance on the known classes, so every AUROC/AP/OSCR/FPR@95TPR value here is
noise around 0.5 with 2 positives per family. The run demonstrates that the test-only families flow
through the frozen pipeline, that pooled numbers use only the near families, that `wideband_noise` and
the benign `cid_overlay` are reported separately, and that reuse of checkpoints, scorers and
calibrators is verified when the same families are evaluated again. Nothing about open-set quality,
the value of the fifth channel or payload awareness follows from these numbers.

Reproduction: [P21](../plan/P21_b2_test_families.md) §2. Experiment and data fingerprints are in
[b2_test_pilot.json](b2_test_pilot.json).
