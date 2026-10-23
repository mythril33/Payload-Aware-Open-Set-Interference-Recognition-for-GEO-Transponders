Matrix coverage: **COMPLETE**; complete=True; completed=25/25, pending=0, failed=0, missing=0. Unexecuted invocation slots are not non-applicable samples.

### Receiver-level and baseline-input displacement (model independent; RC = RECEIVER_CONSISTENT)

| Invocation | Applied / selected | Replays | Cancellations | Parity exact | Core depth Δ (dB) | Residual Δ (dB) | EDSC score Δ MASK_ONLY / RC (dB) | CFAR planned scenes changed | CFAR blind scenes changed | XGB features changed MASK_ONLY / RC |
|---|---|---|---|---|---|---|---|---|---|---|
| `known_authorize_intruder_both` | 2 / 4 | 2 | 4 | True | -0.00 | -0.87 | +0.00 / -1.17 | 2 | 0 | 3 / 11 of 26 |
| `known_authorize_intruder_co_only` | 2 / 4 | 2 | 4 | True | -0.00 | -0.87 | +0.00 / -1.17 | 2 | 0 | 0 / 8 of 26 |
| `known_authorize_intruder_cross_only` | 2 / 4 | 2 | 2 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_drop_one_both` | 4 / 4 | 4 | 8 | True | -6.16 | +6.95 | +0.15 / +7.95 | 3 | 0 | 10 / 15 of 26 |
| `known_drop_one_co_only` | 4 / 4 | 4 | 8 | True | -6.16 | +6.95 | +0.15 / +7.95 | 3 | 0 | 9 / 14 of 26 |
| `known_drop_one_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_none_both` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 0 / 0 of 26 |
| `known_phantom_both` | 4 / 4 | 4 | 8 | True | +0.00 | -0.24 | +0.29 / -0.06 | 2 | 0 | 10 / 15 of 26 |
| `known_phantom_co_only` | 4 / 4 | 4 | 8 | True | +0.00 | -0.24 | +0.29 / -0.06 | 2 | 0 | 9 / 14 of 26 |
| `known_phantom_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_shift_minus_both` | 4 / 4 | 4 | 8 | True | -8.01 | +5.53 | +0.39 / +6.66 | 3 | 0 | 10 / 15 of 26 |
| `known_shift_minus_co_only` | 4 / 4 | 4 | 8 | True | -8.01 | +5.53 | +0.39 / +6.66 | 3 | 0 | 9 / 14 of 26 |
| `known_shift_minus_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_shift_plus_both` | 4 / 4 | 4 | 8 | True | -8.19 | +5.53 | +0.39 / +6.63 | 4 | 0 | 10 / 15 of 26 |
| `known_shift_plus_co_only` | 4 / 4 | 4 | 8 | True | -8.19 | +5.53 | +0.39 / +6.63 | 4 | 0 | 9 / 14 of 26 |
| `known_shift_plus_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_stale_plan_both` | 4 / 4 | 4 | 8 | True | -12.96 | +9.26 | +2.70 / +12.94 | 4 | 0 | 10 / 15 of 26 |
| `known_stale_plan_co_only` | 4 / 4 | 4 | 8 | True | -12.96 | +9.26 | +2.70 / +12.94 | 4 | 0 | 9 / 14 of 26 |
| `known_stale_plan_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `matched_authorize_intruder_both` | 2 / 4 | 2 | 4 | True | -0.00 | -2.02 | +0.00 / -2.28 | 2 | 0 | 3 / 11 of 26 |
| `matched_authorize_intruder_co_only` | 2 / 4 | 2 | 4 | True | -0.00 | -2.02 | +0.00 / -2.28 | 2 | 0 | 0 / 8 of 26 |
| `matched_drop_one_both` | 4 / 4 | 4 | 8 | True | -8.46 | +5.16 | -0.14 / +5.31 | 3 | 0 | 10 / 15 of 26 |
| `matched_drop_one_co_only` | 4 / 4 | 4 | 8 | True | -8.46 | +5.16 | -0.14 / +5.31 | 3 | 0 | 9 / 14 of 26 |
| `matched_phantom_both` | 4 / 4 | 4 | 8 | True | -0.00 | -0.93 | +0.40 / -0.64 | 2 | 0 | 10 / 15 of 26 |
| `matched_phantom_co_only` | 4 / 4 | 4 | 8 | True | -0.00 | -0.93 | +0.40 / -0.64 | 2 | 0 | 9 / 14 of 26 |

### Model-level paired conditions (frozen checkpoints supplied by the run directory; see the summary's interpretation block for what they are)

| Invocation | View | Condition | n | Agreement | Changed | max abs Δlogit | Alarm among original-clean | Alarm among original-event |
|---|---|---|---|---|---|---|---|---|
| `known_authorize_intruder_both` | co | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_both` | co | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_both` | co | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_both` | dual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=2) |
| `known_authorize_intruder_both` | dual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0040 | n/a (n=0) | 100.0% (n=2) |
| `known_authorize_intruder_both` | dual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0040 | n/a (n=0) | 100.0% (n=2) |
| `known_authorize_intruder_both` | dual_residual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_both` | dual_residual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_both` | dual_residual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | co | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | co | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | co | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | dual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=2) |
| `known_authorize_intruder_co_only` | dual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0040 | n/a (n=0) | 100.0% (n=2) |
| `known_authorize_intruder_co_only` | dual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0040 | n/a (n=0) | 100.0% (n=2) |
| `known_authorize_intruder_co_only` | dual_residual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | dual_residual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0007 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_co_only` | dual_residual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0008 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | co | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | co | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0000 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | co | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0000 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0001 | n/a (n=0) | 50.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0001 | n/a (n=0) | 50.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual_residual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual_residual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0001 | n/a (n=0) | 0.0% (n=2) |
| `known_authorize_intruder_cross_only` | dual_residual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0001 | n/a (n=0) | 0.0% (n=2) |
| `known_drop_one_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0015 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0015 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_drop_one_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0057 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0057 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0017 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0015 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0015 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0015 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_drop_one_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0028 | 50.0% (n=2) | 50.0% (n=2) |
| `known_drop_one_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0028 | 50.0% (n=2) | 50.0% (n=2) |
| `known_drop_one_co_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0013 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0008 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_drop_one_cross_only` | dual | MASK_ONLY | 4 | 0.0% | 50.0% | 0.0059 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 50.0% | 0.0059 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0009 | 0.0% (n=2) | 0.0% (n=2) |
| `known_drop_one_cross_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0009 | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_none_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 50.0% (n=2) | 50.0% (n=2) |
| `known_none_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 50.0% (n=2) | 50.0% (n=2) |
| `known_none_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_none_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0026 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0026 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_phantom_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0055 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0055 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0017 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0017 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_co_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0026 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0026 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_co_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_phantom_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0040 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0040 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_co_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_co_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0011 | 0.0% (n=2) | 50.0% (n=2) |
| `known_phantom_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0011 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_phantom_cross_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0028 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_cross_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0028 | 100.0% (n=2) | 100.0% (n=2) |
| `known_phantom_cross_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0007 | 0.0% (n=2) | 0.0% (n=2) |
| `known_phantom_cross_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0007 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0031 | 50.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0031 | 50.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0052 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_minus_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0052 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_minus_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0022 | 0.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0021 | 0.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_co_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0031 | 50.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0031 | 50.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_co_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0034 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0034 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_co_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_co_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0031 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0026 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_cross_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_cross_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_cross_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_cross_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_cross_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0068 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_cross_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0068 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_cross_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_minus_cross_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0029 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_minus_cross_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0029 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0053 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_plus_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0053 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_plus_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0024 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_plus_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0023 | 100.0% (n=2) | 100.0% (n=2) |
| `known_shift_plus_co_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_co_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0036 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0036 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_co_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_co_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0022 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0026 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_cross_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_cross_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_cross_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_cross_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_cross_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0085 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_cross_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0085 | 50.0% (n=2) | 50.0% (n=2) |
| `known_shift_plus_cross_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_cross_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_shift_plus_cross_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0025 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_both` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0042 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0042 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_both` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0070 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0070 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_both` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_both` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0039 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0038 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_co_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0042 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0042 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_co_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0090 | 100.0% (n=2) | 100.0% (n=2) |
| `known_stale_plan_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0090 | 100.0% (n=2) | 100.0% (n=2) |
| `known_stale_plan_co_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_co_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0032 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0020 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_cross_only` | co | original | 4 | 0.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_cross_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_cross_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0000 | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_cross_only` | dual | original | 4 | 0.0% | n/a | n/a | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_cross_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0059 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_cross_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0059 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_cross_only` | dual_residual | original | 4 | 50.0% | n/a | n/a | 0.0% (n=2) | 0.0% (n=2) |
| `known_stale_plan_cross_only` | dual_residual | MASK_ONLY | 4 | 50.0% | 0.0% | 0.0019 | 50.0% (n=2) | 50.0% (n=2) |
| `known_stale_plan_cross_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 50.0% | 0.0% | 0.0019 | 50.0% (n=2) | 50.0% (n=2) |
| `matched_authorize_intruder_both` | co | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_both` | co | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0018 | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_both` | co | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0018 | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_both` | dual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_both` | dual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0026 | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_both` | dual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0026 | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_both` | dual_residual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `matched_authorize_intruder_both` | dual_residual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0013 | n/a (n=0) | 0.0% (n=2) |
| `matched_authorize_intruder_both` | dual_residual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0013 | n/a (n=0) | 0.0% (n=2) |
| `matched_authorize_intruder_co_only` | co | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_co_only` | co | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0018 | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_co_only` | co | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0018 | n/a (n=0) | 50.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0030 | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0030 | n/a (n=0) | 100.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual_residual | original | 2 | 0.0% | n/a | n/a | n/a (n=0) | 0.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual_residual | MASK_ONLY | 2 | 0.0% | 0.0% | 0.0012 | n/a (n=0) | 0.0% (n=2) |
| `matched_authorize_intruder_co_only` | dual_residual | RECEIVER_CONSISTENT | 2 | 0.0% | 0.0% | 0.0013 | n/a (n=0) | 0.0% (n=2) |
| `matched_drop_one_both` | co | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0017 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0017 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_both` | dual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=4) |
| `matched_drop_one_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0082 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0082 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_both` | dual_residual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 25.0% (n=4) |
| `matched_drop_one_both` | dual_residual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0014 | n/a (n=0) | 0.0% (n=4) |
| `matched_drop_one_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0014 | n/a (n=0) | 0.0% (n=4) |
| `matched_drop_one_co_only` | co | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0017 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0017 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_co_only` | dual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=4) |
| `matched_drop_one_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0036 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0036 | n/a (n=0) | 50.0% (n=4) |
| `matched_drop_one_co_only` | dual_residual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 25.0% (n=4) |
| `matched_drop_one_co_only` | dual_residual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0014 | n/a (n=0) | 25.0% (n=4) |
| `matched_drop_one_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0011 | n/a (n=0) | 25.0% (n=4) |
| `matched_phantom_both` | co | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=4) |
| `matched_phantom_both` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0022 | n/a (n=0) | 75.0% (n=4) |
| `matched_phantom_both` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0022 | n/a (n=0) | 75.0% (n=4) |
| `matched_phantom_both` | dual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_both` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0069 | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_both` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0069 | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_both` | dual_residual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 25.0% (n=4) |
| `matched_phantom_both` | dual_residual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0028 | n/a (n=0) | 0.0% (n=4) |
| `matched_phantom_both` | dual_residual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0028 | n/a (n=0) | 0.0% (n=4) |
| `matched_phantom_co_only` | co | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 50.0% (n=4) |
| `matched_phantom_co_only` | co | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0022 | n/a (n=0) | 75.0% (n=4) |
| `matched_phantom_co_only` | co | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0022 | n/a (n=0) | 75.0% (n=4) |
| `matched_phantom_co_only` | dual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_co_only` | dual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0043 | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_co_only` | dual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0043 | n/a (n=0) | 100.0% (n=4) |
| `matched_phantom_co_only` | dual_residual | original | 4 | 0.0% | n/a | n/a | n/a (n=0) | 25.0% (n=4) |
| `matched_phantom_co_only` | dual_residual | MASK_ONLY | 4 | 0.0% | 0.0% | 0.0018 | n/a (n=0) | 25.0% (n=4) |
| `matched_phantom_co_only` | dual_residual | RECEIVER_CONSISTENT | 4 | 0.0% | 0.0% | 0.0021 | n/a (n=0) | 25.0% (n=4) |
