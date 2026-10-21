# B2-match/1 pilot: K17c level-matched ASI versus unauthorized (execution and physics evidence)

Date: 2026-10-21. Stage `B2-match/1` bound to the `B2-feat/1` pilot; `benchmark_complete: false`.
Scope: pairing physics of the matched set and execution of the matched evaluation with pilot
checkpoints. **No recognition-quality or separability claim.** Machine-readable records:
[matched physics](b2_matched_check.json), [full pilot run](b2_full_pilot.json).

## Data

| Artifact | Groups | Observations | Note |
|---|---|---|---|
| B2-feat/1 pilot (known, 4 roles) | 2 per role | 64 | [P20 pilot](b2_feat_pilot.md) |
| B2-test/1 pilot (test role) | 2 | 10 | [P21a pilot](b2_test_pilot.md) |
| B2-match/1 pilot (test-matched role) | 2 (3 300 000, 3 300 001) | 6 | 2.4 MiB; same receiver calibration and canceller as the known artifact; resume verified |

Over the full frozen role (150 groups, scenes resolved without waveforms): bins 4–7 / 7–10 / 10–13 dB
hold 50 / 54 / 46 groups; 4 groups needed an operator-plan redraw to admit both placements.

## Pairing evidence (two groups)

| Group | Bin | Target C/I_psd | Carrier | Requested power equal | Injected power vs request (oracle, before payload) | ASI overlap with plan / with transmitted carriers | ΔPSD in own band: ASI / unauthorized (spectrum) | ΔPSD in own band: ASI / unauthorized (residual) | Event-free gap floor shift: ASI / unauthorized |
|---|---|---:|---|---|---|---:|---|---|---|
| 3300000 (planned carrier missing) | 4–7 | 5.79 dB | 1.5 Mbaud 16APSK α 0.20 | yes (1e-12) | +0.04 dB / +0.04 dB | 0.51 / **0.00** | 13.8 / 15.2 dB | 13.9 / 15.1 dB | +0.20 / +0.15 dB |
| 3300001 | 7–10 | 9.22 dB | 1.0 Mbaud 16APSK α 0.20 | yes (1e-12) | +0.17 dB / +0.17 dB | 0.25 / 0.25 | 3.5 / 10.1 dB | 10.1 / 10.0 dB | +0.04 / +0.03 dB |

Reading. (1) Requested power and reference are identical by construction and verified on read.
(2) The injected waveform power (simulator truth, diagnostic only) is identical for the two events and
within 0.2 dB of the request, the difference being finite symbol statistics. (3) After the payload the
observable in-band rise differs by placement. In group 3300001 the ASI band holds a transmitted planned
carrier (overlap 0.25), so its rise over the clean twin is 3.5 dB against 10.1 dB for the unauthorized
carrier over the gap floor. Group 3300000 is a K17c **intersection** case flagged by the reviewer: the
shared missing-carrier draw mutes exactly the carrier the ASI overlaps, so its band is at the noise floor
in the clean twin too; the two rises differ only by the clean-twin level difference between the bands
(1.45 dB; the absolute in-band PSDs differ by 0.07 dB), and observationally this ASI is an
unauthorized-like carrier under a "planned" mask. Over the 150 frozen groups 5 such groups exist; the
metadata flags them and the runner reports them separately. (4) In the stored cancellation residual the
two events sit within ≈ 1.5 dB of each other (13.9 vs 15.1 dB; 10.1 vs 10.0 dB): once the planned carrier
is removed the matched interferers are at near-equal residual level, so the remaining cue is the plan
mask. Masks and activity are identical across the three variants of each group. In the widest free gap
disjoint from both event bands the floor moves by ≤ 0.2 dB, i.e. the intermodulation added by these weak
events is negligible in the pilot groups (an earlier draft measured the unauthorized carrier itself; corrected).
Matched carriers are narrow by joint feasibility (here 1.0 and 1.5 Mbaud; ≤ 6 Mbaud over all 150 groups).

## Matched evaluation with pilot checkpoints (execution evidence only)

Frozen checkpoints and val-calib thresholds from the 16-observation training pilot (`configs/b2_feat.json`).

| View | n | Unconditional accuracy | ASI recall | Unauthorized recall | Pair accuracy (argmax, no rejection) | Pair accuracy among accepted (MSP) | pred clean among pair | rejected (MSP) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| co | 6 | 0 % | 0 % (n = 2) | 0 % (n = 2) | 0 % (n = 4) | 0 % (n = 3) | 0 | 1 |
| dual | 6 | 0 % | 0 % | 0 % | 0 % | 0 % (n = 2) | 0 | 2 |
| dual_residual | 6 | 33 % | 0 % | 0 % | 0 % | 0 % (n = 4) | 4 | 0 |

Intersections reported separately: 2 pair samples in the group with a missing planned carrier (3300000),
1 ASI variant over an absent carrier.

The `dual_residual` pilot model predicts `clean` for everything (hence 33 % unconditional accuracy on
the two clean variants and all four pair samples counted as "predicted clean", not dropped). The natural
comparison found one natural ASI test sample in the 4–7 dB bin and one natural unauthorized sample in each
of the 4–7 and 7–10 dB bins (all misclassified by the chance-level models). Paired spectrogram figures were
written for groups 3300000 (bin 4–7) and 3300001 (bin 7–10) under `runs/b2-full-pilot/figures/` by the
fixed-seed rule. Reuse of checkpoints, scorers and calibrators was verified in a second run.

None of these numbers says anything about separability: the models are at chance and n = 2 per bin.
The run demonstrates the frozen-threshold evaluation path, the explicit pair denominators and the per-bin
and natural-comparison reporting. Reproduction: [P22](../plan/P22_b2_matched_asi.md) §2.
