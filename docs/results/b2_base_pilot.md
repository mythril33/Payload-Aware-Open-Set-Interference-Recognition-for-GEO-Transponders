# B2-base/1 physical-observation pilot

Date: 2026-10-21.

Known physical observations under frozen B2/1. The manifest marks the full benchmark incomplete.
No classifier was trained; cancellation features, unknown/CID tests and the final B2 learning benchmark remain outstanding.

| Role | Scenario groups | Observations |
|---|---:|---:|
| train | 2 | 16 |
| val-select | 2 | 16 |
| val-calib | 2 | 16 |
| test | 2 | 16 |

Total: 64 observations in 8 paired groups, eight known classes per group.
Generation wall time: 109.55 s. CPU time: 131.99 s.
Peak resident memory: 545.52 MiB. Stored artifact size: 16.49 MiB.
Single producer, two OMP/BLAS threads; the test suite ran concurrently for part of production. This is a pilot measurement, not a full-run time guarantee.

## Missing-carrier diagnostics

The fixed first two groups in every role drew no natural missing carriers. Their auxiliary targets are all consistent.
Eight separately forced twins cover each primary class; they are excluded from the dataset and recognition metrics.

| Class | Missing feed/index | Active planned power | Actual IBO before | Actual IBO after |
|---|---|---:|---:|---:|
| clean | 0/2 | 0.960653 | 11.6844 dB | 11.8632 dB |
| cw | 0/2 | 0.960653 | 11.6048 dB | 11.7802 dB |
| swept_cw | 0/2 | 0.960653 | 11.6530 dB | 11.8308 dB |
| unauthorized | 0/2 | 0.960653 | 11.2985 dB | 11.4617 dB |
| overdrive | 0/2 | 0.960653 | 2.7683 dB | 2.9470 dB |
| cross_pol | 0/2 | 0.960653 | 11.6788 dB | 11.8440 dB |
| adjacent_satellite | 0/2 | 0.960653 | 11.6751 dB | 11.8535 dB |
| carrier_under_carrier | 0/2 | 0.960653 | 11.6783 dB | 11.8562 dB |

All diagnostic twins retain full operator plans and fixed nominal gain, reduce active planned power and produce finite spectra.
CuC retains an active victim; its placement may be redrawn if the initially selected victim is the missing carrier.
A separate artifact regression includes natural missing group 3000008 and verifies all eight auxiliary targets through writing, lazy reading and split loading.

## Reuse and legacy preservation

Completed generation resume verified all 64 samples without changing original provenance.
Two previous-engine comparisons (36 MHz without phase noise, 72 MHz with 100/50 Hz phase noise) preserved IQ/PSD/masks bit for bit and default metadata exactly.
Calibration pilots use a separate RNG namespace; source/config, calibration and shard identities are bound into the request.

Data fingerprint: `5a44abc1f7d56d94f67e8d0cd112b2f46463e1d94b0fb99c5027d9d7ce106a15`.
Request fingerprint: `3c71400ca6b3966247d1a950f6f189442a049951dc3ca0fd1b8979f1e1c51d79`.

Reproduction commands: [P19](../plan/P19_b2_base_observations.md). Raw datasets remain outside Git.
