# B2 observed-receiver development pilot — 2026-10-21

Protocol `B2-observed-dev/1`; parent `B2/1`.

Known classes only. Final unknown/CID/matched tests and multi-seed benchmark results remain outstanding.
The receiver uses observed IQ plus declared operator frequency/rate/roll-off/modulation information.
No true symbols, powers, timing, active state or event labels enter cancellation.

| View | Channels | Primary accuracy | Primary macro-F1 | Consistency accuracy | Missing recall | Clean false alarm |
|---|---|---|---|---|---|---|
| dual | 4 | 12.5% | 0.031 | 100.0% | not measured (n=0) | 100.0% |
| b2 | 5 | 12.5% | 0.028 | 0.0% | not measured (n=0) | 0.0% |

Model selection uses val-select primary macro-F1. Clean val-calib samples alone set the event threshold.
Consistency uses argmax over its independent two-state head. Missing recall is null when there are no positive targets.
Scenario-bootstrap intervals are null with fewer than two test groups; training-seed uncertainty is not estimated here.
Small known-class runs check the connection, not a recognition advantage or unknown-rejection quality.
Model-mask jitter leaves stored residuals unchanged; full operator-plan-error experiments require recomputed receiver features.

| Role | Groups | Samples | Missing targets |
|---|---|---|---|
| train | 9 | 72 | 8 |
| val-select | 1 | 8 | 0 |
| val-calib | 1 | 8 | 0 |
| test | 1 | 8 | 0 |

Experiment fingerprint: `fd921f5c9aaad3703189e454b05d15051633c7d1881f4d2cab9662e3fbfac3ec`.

## Scope and observed failures

Both models remain at chance-level primary accuracy (1/8 correct) after three
predeclared epochs on 72 training observations. The four-channel model predicts
only swept CW and carrier-under-carrier; the five-channel model predicts clean
for every test observation.
No weights, thresholds or receiver settings were changed after viewing these
results.

The auxiliary results are also degenerate: the four-channel view predicts
consistent on all eight test observations, whereas the five-channel view
predicts missing on all eight. All test targets are consistent. Thus 100% versus
0% auxiliary accuracy supplies no missing-detection evidence. The only natural
missing group is train 3000008: cross-feed carrier index 4, shared across its
eight primary variants. No held-out missing target or physically missing co-feed
carrier is covered by this pilot. Missing-carrier recall is null, n=0.

Each event class and the clean false-alarm rate have just one test observation
in a single shared scenario group. The 0%/100% alarm rates are individual binary
outcomes. There is just one clean calibration observation; target Pfa 5% does
not imply a measured or guaranteed operational 5% rate. Scenario confidence
intervals are null and no training-seed interval is estimated. Unknown-family,
CID-overlay, matched ASI and LOKO results remain absent.

## Physical receiver diagnostic

Cancellation consumes observed calibrated co IQ plus declared operator
frequency/rate/roll-off/modulation/code-rate fields. Raw IQ is transient.
The receiver estimates decisions/timing/phase and a short received-domain FIR;
it is not a complete DVB-S2 modem or nonlinear TWTA inversion. Total power
reduction includes wanted carriers, noise and any partly cancelled overlapping
intruders; it does not measure preserved interference or classification benefit.
The diagnostic summaries below aggregate all 12 groups after execution, with no
parameter selection from those summaries.

| Known class | Observations | Median total-power reduction (dB) | Min–max (dB) |
|---|---:|---:|---:|
| clean | 12 | 11.80 | 10.37–14.67 |
| cw | 12 | 11.08 | 5.78–14.23 |
| swept_cw | 12 | 11.19 | 3.16–12.69 |
| unauthorized | 12 | 9.55 | 6.86–11.16 |
| overdrive | 12 | 9.10 | 8.31–11.31 |
| cross_pol | 12 | 8.82 | 7.83–10.10 |
| adjacent_satellite | 12 | 11.29 | 5.43–13.41 |
| carrier_under_carrier | 12 | 11.30 | 3.70–14.42 |

## Timing and integrity

- Feature generation: 182.30 s wall,
  257.21 s CPU; peak RSS 598.98 MiB.
- Both three-epoch model fits, saving/loading and evaluation: 11.48 s wall;
  peak RSS 465.70 MiB. CPU, two OMP/OpenBLAS threads.
- Feature artifact: 40.31 MiB; no stored IQ or checkpoints in Git.
- All 96 feature observations pass checksum/semantic validation. Exact-source
  generation resume succeeds; model/detector reload produces identical
  predictions and metrics.
- Full merged repository suite: **923 passed** in 60.82 s, including **180**
  tests for this development stage. No old physics or canonical P20 source
  files were changed by the P21 integration.

These timings are single-run execution measurements, with tests partly concurrent,
not a full-production throughput guarantee. A successful pre-integration physical
run was retained locally but excluded from this report; the published run was
regenerated after integrating PR #5, with fresh source/request identities.

Feature fingerprint: `ceb562b178dfc7470ea35ab3cf42f1b4be2bb5b4c985ca023c4931745bc53e89`.

Request fingerprint: `82d5291e74bc91d7d78ad5707d0cc8a34dfcd6124ac792d130fad0278b663c2b`.

Source base revision: `707980d54c85fb79604063dad4f29137999e10b6`. Exact working-source hashes
are retained in the [machine-readable report](b2_observed_pilot.json); the
subsequent publishing commit adds those files and these summaries.

Small [test predictions](b2_observed_predictions.json) expose the failure modes.
The P20 `B2-feat/1` receiver, loss conventions and earlier reports remain separate;
these pilots are not a controlled receiver comparison. See
[P21 assumptions and commands](../plan/P21_b2_observed_receiver.md).

To verify a locally generated/timed run and replay checkpoints:

```bash
python scripts/check_b2_features.py --data data/b2-features-pilot --run runs/b2-observed-pilot --out docs/results/b2_observed_pilot.json
```

Timing fields are null when the optional local timing files are absent.
