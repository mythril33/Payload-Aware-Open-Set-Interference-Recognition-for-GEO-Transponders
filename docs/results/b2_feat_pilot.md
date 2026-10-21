# B2-feat/1 pilot: observation-based cancellation residual and five-channel learning slice

Date: 2026-10-21. Protocol stage `B2-feat/1` under frozen `B2/1`; `benchmark_complete: false`.
Scope: physics of the stored fifth channel and execution of the frozen-role learning slice.
**No recognition-quality claim.** Machine-readable records:
[cancellation check](b2_feat_cancellation_check.json), [learning slice](b2_feat_pilot.json).

## Data

| Role | Scenario groups | Observations | Planned carrier missing |
|---|---:|---:|---:|
| train | 2 | 16 | 0 |
| val-select | 2 | 16 | 0 |
| val-calib | 2 | 16 | 0 |
| test | 2 | 16 | 0 |

64 observations, eight paired known classes per group, same groups as the B2-base/1 pilot.
Generation (single producer, 2 OMP/BLAS threads, test suite running concurrently for part of the time):
243.8 s wall, 285.1 s CPU, peak RSS 585 MiB, 24.75 MiB stored (B2-base/1 pilot: 109.6 s, 545 MiB, 16.5 MiB).
Resume after completion verified all 64 samples without regeneration.

Commands: see [P20](../plan/P20_b2_cancellation_residual.md) and `CLAUDE.md`.

## Cancellation physics (64 observations, 37 active planned co-pol carriers per label)

Depth = in-band (occupied core) PSD of the observed co-pol spectrum minus that of the residual.
Gap-floor shift = residual minus observation in the widest operator-plan gap (should be ≈ 0: the canceller must not touch out-of-plan bins).

| Label | n | Mean depth (dB) | Min depth (dB) | Gap-floor shift (dB) | Median decision SNR (dB) |
|---|---:|---:|---:|---:|---:|
| clean | 8 | 16.5 | 14.2 | −0.09 | 16.4 |
| cw | 8 | 15.5 | 4.5 | −0.05 | 15.8 |
| swept_cw | 8 | 15.6 | 11.7 | −0.06 | 16.2 |
| unauthorized | 8 | 16.3 | 14.2 | −0.04 | 16.1 |
| overdrive | 8 | 13.3 | 11.2 | −0.03 | 12.8 |
| cross_pol | 8 | 12.8 | 9.0 | −0.02 | 12.0 |
| adjacent_satellite | 8 | 15.3 | 6.8 | −0.08 | 15.2 |
| carrier_under_carrier | 8 | 15.2 | 6.2 | −0.09 | 16.0 |

By modulation (all labels): QPSK 14.3 dB (n = 72), 8PSK 14.7 (48), 16APSK 14.9 (96), 32APSK 16.2 (80).

Reading: two limits bound the depth. At low C/N the residual reaches the receiver noise floor. At high
C/N the un-tracked LO phase walk within a 42.7 µs snapshot caps it: `obs-cancel/1` fits one complex gain
per snapshot, and with the frozen effective linewidth of 150 Hz (satellite 100 Hz + receiver 50 Hz) a
synthetic 9.6 Mbaud QPSK carrier shows a ceiling of ≈ 24–25 dB at C/N 25 and 40 dB alike (30.7 and
43.8 dB without phase noise; the independent reviewer measured ≈ 21 dB on another realization). So in the
upper half of the frozen C/N range the algorithm, not the noise, limits the depth. This is an
algorithmic limit that a later versioned `obs-cancel/2` with per-segment phase tracking could raise.
Lower depth for `overdrive` (nonlinear constellation warping, IM floor) and `cross_pol` (−10 dB
leakage of the other feed's carriers into the co-pol decisions) is physical. A `cw` sitting on a carrier
degrades its decisions (minimum 4.5 dB). The gap floor is unchanged in every label.

### Paired clean versus carrier-under-carrier (8 groups)

ΔPSD in the hidden carrier's occupied band between the CuC scene and its clean twin
(same plans, carriers, noise and phase realizations):

| Group | C/I (dB, total plan) | Victim C/I (dB) | Victim / interferer MODCOD | ΔPSD before (dB) | ΔPSD after cancellation (dB) |
|---|---:|---:|---|---:|---:|
| 3000000 | 28.4 | 14.3 | 8PSK / 16APSK | 0.15 | 2.91 |
| 3000001 | 18.8 | 6.2 | 8PSK / 8PSK | 1.03 | 7.57 |
| 3100000 | 24.1 | 13.0 | 16APSK / 16APSK | 0.27 | 4.44 |
| 3100001 | 19.0 | 5.8 | QPSK / 16APSK | 1.02 | 7.88 |
| 3150000 | 25.9 | 24.6 | 32APSK / 8PSK | 0.03 | 1.45 |
| 3150001 | 16.0 | 3.4 | 16APSK / QPSK | 1.58 | 5.35 |
| 3200000 | 9.9 | 5.0 | QPSK / 16APSK | 0.98 | 10.82 |
| 3200001 | 17.2 | 10.4 | QPSK / 16APSK | 0.99 | 11.03 |

Median ΔPSD 0.99 dB before, 6.46 dB after; after > before in 8/8 groups. This supports the K9
pre-registration (P18 §6: CuC separable from clean via the residual, not via the spectrum) at the
physics level. It is an oracle-twin comparison for measurement only: the model never sees the twin.

### Overdrive versus clean

In the widest plan gap the overdrive scene lies 5.8–10.6 dB above its clean twin in the spectrum and
by the same amount in the residual (difference ≤ 0.27 dB): cancellation preserves intermodulation
evidence while removing the planned carriers.

## Learning slice (execution evidence only)

`configs/b2_feat.json`: 3 epochs, batch 8, width 8, seed 0, center-loss weight 0.005 (pre-registered,
P20 §5), independent plan-consistency head, Mahalanobis regularization 0.1, 95 % known acceptance,
Pfa 5 %. Three matched views trained on the same 16 observations.

| View | Channels | Parameters | Test accuracy (n = 16) | Macro-F1 | Known acceptance MSP / energy / Mahalanobis |
|---|---:|---:|---:|---:|---|
| co | 2 | 78 777 | 12.5 % | 0.028 | 50 % / 100 % / 100 % |
| dual | 4 | 79 177 | 12.5 % | 0.028 | 0 % / 100 % / 56 % |
| dual_residual | 5 | 79 377 | 12.5 % | 0.028 | 100 % / 100 % / 50 % |

All three models are degenerate (chance level, constant prediction); validation macro-F1 stayed at
0.028 in every epoch. The plan-consistency head reports 100 % accuracy with **zero positive cases**
in these pilot groups, which is uninformative. Reuse of checkpoints, Mahalanobis scorers and
rejection calibrators was verified in a second run; editing experiment source invalidates reuse by
design (provenance includes source hashes). This slice demonstrates data flow, role separation and
artifact binding. It says nothing about recognition quality, the value of the fifth channel or the
payload gap; those need the full frozen production and the researcher's GPU training.
