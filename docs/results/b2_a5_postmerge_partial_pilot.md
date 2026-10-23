# E4 post-merge bounded A5 evidence — 2026-10-23

> **Record status.** This is the post-merge *recovery* record of the parallel session (commit `b8e4cd3`), preserved verbatim except for the
> three relative links and this note, which now use the `*_postmerge_partial_pilot*` / `b2_e4_postmerge_review.md` file names (the recorded summarize command at the end and the JSON's file list still show the former `b2_a5_dual_pol_pilot*` output names). A later,
> separate record covers the full 25-invocation inventory on the unified code: [b2_a5_dual_pol_pilot.md](b2_a5_dual_pol_pilot.md). The two
> records use different data fixtures and experiment fingerprints and are not merged or compared numerically.

**Engineering/evidence closure for a partial pilot. Full matrix coverage,
recognition performance and robustness are not established.**
`benchmark_complete=false`; researcher and production gates are unchanged.
Machine-readable measurements, full rate denominators/group intervals,
commands and checksum traces are in [JSON](b2_a5_postmerge_partial_pilot.json);
the [table](b2_a5_postmerge_partial_pilot_table.md) is generated from the raw calls.
See [P28](../plan/P28_b2_e4_dual_pol_a5.md), the preregistered
[recovery execution budget](../engineering/B2_E4_POSTMERGE_EXECUTION.json)
and the [independent review](../research/b2_e4_postmerge_review.md).

## Verified starting point and recovery

Fetched main: `4b736a6c425ab532e7c8e1bccc7c906f86ebe0be`. PR14 XGBoost
merged as `ff81cae1b4e2563cc88271566665e9feae7cd44e`; PR15 E4 merged as
that main SHA. No implementation was restarted and no merge was invoked
in this recovery session. No other open closure PR/branch was found.

The four referenced E4 report/review files were absent from the merge
tree. Named pilot data/run directories were absent from this checkout.
Existing readiness artifacts had different generator hashes; their old
neural checkpoints also failed P28 source rules. They were preserved and
not silently reused. P21b artifacts were not substituted.

Only the documented two-group fixture was recreated:64 known observations
(16 each train/val-select/val-calib/test),6 matched observations. The fixed
config trained three CPU stand-in views on16 train observations for3epochs;
val-select chose checkpoints, Mahalanobis scorers fitted train-only, and
val-calib supplied frozen thresholds before A5 evaluation. Full known-test accuracy was2/16 for
every view. These are chance-level interface stand-ins, not research models.

Recovery engineering commit and training/evaluation source revision:
`2ee03c53ea2183e1b227f09d428701215cfb2090`. Subsequent delivery changes
are documentation/evidence only. All current source hashes match the
pilot and frozen models. Existing physical/RNG/perturbation/canceller/
neural training code and calibration definitions are unchanged.

## Reliability fixes and test evidence

The former shell pipeline could hide Python failures and skip results
based on checksum alone. The new driver always enters the provenance-aware
CLI, preserves full per-attempt logs and exit codes, validates outputs,
enforces an overall budget before work and inventories all25 calls.
Successful selected subsets exit3/PARTIAL; only all25 verified calls can
exit0/COMPLETE. Failed/missing/blocked/skipped slots remain explicit.

Committed scene metadata previously accepted altered parity/work values
without an array checksum change. Internal `B2-A5-scene-state/2` now binds
the entire metadata payload and rejects incompatible/legacy state, strict
JSON/schema failures and invalid logical work. This is an explicit cache
integrity change, not a new physical artifact or perturbation version.
Original interrupted-state resume remains covered. Counterfactual nested
matched accuracy names now say agreement; zero-check parity is null;
cross-only equality to stored residual is qualified by exact parity.

Actual local verification, with OMP/OPENBLAS/MKL threads2 and Agg:

| Scope | Actual result | Whole-process wall | Peak process RSS |
|---|---|---|---|
| Initial adversarial state test against old code |9 failed,1 passed /2.67s, expected TDD failure |not separately measured|not separately measured|
| Intermediate integrity/resume/eval regression |41 passed /84.01s|85.886459s|431960KiB|
| Intermediate eight-module E4 snapshot |133 passed /232.19s|236.216576s|759852KiB|
| State/matrix/summary focused regression |41 passed /126.96s|129.172373s|427916KiB|
| Full repository regression |1220 passed,1 skipped,0 failed /718.13s|719.893069s|1298088KiB|
| Final affected summary module |7 passed /94.79s|98.116711s|436480KiB|

The intermediate focused snapshots are not certificates of every final
file: fixes landed while those processes ran. Exactly two paths changed
after full-suite launch: `scripts/summarize_b2_a5_pilot.py` and its test.
No detector/model/physical source changed. The final seven-test affected
regression ran after those last guards and passed. Final-head GitHub CI
is verified separately in the delivery PR, not inferred from this local
snapshot or from historical PR15 CI.

The single full-suite skip is
`tests/test_b2_stream.py::test_streaming_peak_memory_stays_below_the_whole_dataset_footprint`
at line421: this environment cannot reset `/proc/self/clear_refs`.
It is not a passed test. Syntax compilation, bash syntax, strict JSON,
unchanged decision objects, source/checkpoint/state/checksum integrity
and whitespace checks also passed.

Independent read-only validation: initial78passed62.68s; post-fix116passed
247.13s with a hash guard explicitly refusing whole-final certification
after the same two summary files changed; final affected4cases passed
49.80s with stable hashes. The reviewer ran no independent full suite or
RF pilot. It found no remaining material code/evidence blocker after
separate final raw-file, pairing and denominator inspection.

## Coverage and physical consistency

The nine names were fixed before recovery generation or A5 outcomes:
known `none/both`, `shift_plus/cross_only`, `shift_minus/both`,
`drop_one/co_only`, `phantom/both`, `authorize_intruder/both`,
`stale_plan/both`; matched `drop_one/both`, `authorize_intruder/both`.
Known labels are clean/unauthorized; matched labels are ASI/unauthorized.
Two groups per stage and two labels per call are used throughout.

Measured matrix: **9/25 complete,16 pending,0 failed,0 missing**;
matrix status PARTIAL, exit3.36 selected scene-slots comprise32applied,
4not-applicable,0blocked,0unavailable views. The four non-applicable slots
are original-clean/ASI scenes under authorize_intruder. They were not
replayed or parity-checked. The16 unexecuted invocation slots are pending,
not non-applicable samples. Only eight unique physical scenes from four
scenario IDs underlie these repeated slots; counts across perturbations
must not be interpreted as independent sample sizes.

Logical work:32physical replays,56cancellations (32original/parity plus
24corrupted-co recomputations),312scored sample evaluations. Every call
stayed within2groups/2classes/one configuration/16replays/24cancellations.
The preflight conservative overall budget was9calls/144replays/
216cancellations/900s; no unrestricted mode was enabled.

All32 applicable-scene original replays had **exact** stored
PSD/mask/residual/metadata parity, maximum difference0dB. Received IQ is
transient; physical invariance is checked by the replay/receiver boundary,
runtime assertions and physical tests with IQ hashes/spies. The pilot
files do not persist per-scene IQ hashes. Cached receiver-consistent PSD
arrays were independently checked bit-equal to the stored PSD.

None had zero input/logit displacement in all views. Cross-only made no
co residual recomputation and its residual stayed bit-equal on this exact
pilot; on portable non-exact replay only equality to the original replay
residual is guaranteed. Co-plan changes used the unchanged P20
`obs-cancel/1` on calibrated co IQ and corrupted co belief. MASK_ONLY kept
the stored residual and remains a weaker control. Co/dual MASK_ONLY versus
RECEIVER_CONSISTENT logits were identical; dual_residual logits differed
for co-changing calls. All selected model argmax changes were zero; these
stand-in outputs provide no robustness evidence.

Illustrative measured receiver-input effects, not method performance:
known drop_one/co_only changed mean core cancellation depth by-6.159926dB
and residual total power by+6.95dB; matched drop_one/both changed core
depth by-8.461037dB. Cross-only/none core depth displacement was0.
The table preserves all other observed displacements and alarm counts.
Baseline entries are EDSC/CFAR/XGBoost **input/feature recomputation**,
not frozen baseline classifier/detector comparisons or eight-class EDSC.

## Provenance, metrics and limitations

Known data fingerprint:
`1c510cd0d5eb76e4dc61d36497699fc9a938633f740bd375f2abd0a1f3928b81`.
Matched fingerprint:
`6ff7970eb6f28e9a4780a588f2b9f4fde93d6b734aa2af3c42b4e5230a56bf4e`.
The JSON binds both request fingerprints, receiver calibration parameter/
artifact SHA, frozen obs-cancel/1 settings, complete source hashes,
checkpoint/scorer/threshold identities, per-call experiment fingerprints,
result/state/log checksums and exact reproduction commands.

Independent inspection verified9results/sidecars,36state metadata
fingerprints,32NPZ hashes and all frozen file hashes. Confusion/transition
sums and matched breakdowns retain paired denominators, including clean,
other-known and rejected predictions. Counterfactual outputs are
agreement with ORIGINAL labels, never conventional accuracy. Alarm rows
are among original-clean/original-event scenes; an intervention can
change the operational meaning. Empty denominators are null with counts.

Group bootstrap (2000resamples,seed0) conditions on fixed models and
thresholds and resamples scenarios together. Only two groups per stage
exist; degenerate intervals are not statistical precision. Two clean
val-calib observations per view cannot establish empirical/population
Pfa5%. No unknown-family AUROC/OSCR is estimated here. Model fitting,
calibration, simulator uncertainty and real field transfer are unmeasured.
`authorize_intruder` uses privileged event parameters solely to construct
the explicitly controlled operator-belief intervention, not as an
unlabelled deployed inference input.

## Cost, environment and exact commands

Python3.12.14, NumPy2.5.4, SciPy1.18.1, torch2.14.1+cpu,
xgboost-cpu3.4.1; Linux6.18.55,x86_64, three allocated CPUs, CPU only,
CUDA_VISIBLE_DEVICES empty. Tests and setup/pilot overlapped; these times
are execution measurements, not isolated speed benchmarks.

| Operation | Wall | Peak process RSS | Outcome |
|---|---|---|---|
|64known fixture generation|274.449210s|574192KiB|exit0|
|6matched fixture generation|31.946755s|562816KiB|exit0|
|Three fixed CPU stand-ins|65.422668s|475084KiB|exit0|
|Nine-call partial matrix|272.103641s|742884KiB|exit3/PARTIAL|
|Pure summary|0.201127s|14208KiB|exit0|

RSS is maximum process RSS from waited-child accounting, not simultaneous
total memory. Matrix /proc sampling saw the driver; it does not certify
descendant-tree memory enforcement. Raw per-call self RSS and the waited-
child maximum are available and below the planned1.5GiB process bound.
The32replay/56cancellation counts and900s overall execution limit were
enforced; actual matrix wall was below the cap.

Full generation, GPU training and full LOKO were **not executed**. K18,
K17d and OBS-CANCEL/2 remain pending; approvals were not inferred from
successful engineering tests. Full25-call coverage, meaningful trained
models/calibration populations and representative scientific validation
remain open.

The following commands are copied from the actual measurement records.
Run from the repository root; raw data/checkpoints/run state remain
outside Git. Prepend the recorded thread/Agg/CPU environment to each.

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg CUDA_VISIBLE_DEVICES=
/workspace/.venvs/geosim/bin/python -m geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json --out data/b2-feat-pilot --limit-groups 2 --groups-per-shard 1
/workspace/.venvs/geosim/bin/python -m geosim.b2_matched_dataset --known data/b2-feat-pilot --config configs/b2_base.json --cancellation configs/cancellation.json --out data/b2-match-pilot --limit-groups 2 --groups-per-shard 1
/workspace/.venvs/geosim/bin/python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --out runs/b2-feat-pilot
env PYTHON=/workspace/.venvs/geosim/bin/python bash scripts/run_b2_a5_pilot_matrix.sh data/b2-feat-pilot data/b2-match-pilot runs/b2-feat-pilot runs/b2-a5-pilot --only known_none_both --only known_shift_plus_cross_only --only known_shift_minus_both --only known_drop_one_co_only --only known_phantom_both --only known_authorize_intruder_both --only known_stale_plan_both --only matched_drop_one_both --only matched_authorize_intruder_both --max-invocations 9 --max-physical-replays 144 --max-cancellations 216 --max-wall-seconds 900 --plan
env PYTHON=/workspace/.venvs/geosim/bin/python bash scripts/run_b2_a5_pilot_matrix.sh data/b2-feat-pilot data/b2-match-pilot runs/b2-feat-pilot runs/b2-a5-pilot --only known_none_both --only known_shift_plus_cross_only --only known_shift_minus_both --only known_drop_one_co_only --only known_phantom_both --only known_authorize_intruder_both --only known_stale_plan_both --only matched_drop_one_both --only matched_authorize_intruder_both --max-invocations 9 --max-physical-replays 144 --max-cancellations 216 --max-wall-seconds 900  # expected exit 3: PARTIAL
/workspace/.venvs/geosim/bin/python scripts/summarize_b2_a5_pilot.py --runs runs/b2-a5-pilot --out docs/results/b2_a5_dual_pol_pilot.json --markdown docs/results/b2_a5_dual_pol_pilot_table.md --checkpoint-note 'Fresh fixed three-epoch CPU stand-ins on16 train observations; no A5 fitting; execution evidence only'
/workspace/.venvs/geosim/bin/python -m pytest -q -rs
/workspace/.venvs/geosim/bin/python -m pytest -q tests/test_b2_a5_state_integrity.py tests/test_b2_a5_summary.py tests/test_b2_a5_matrix.py
/workspace/.venvs/geosim/bin/python -m pytest -q tests/test_b2_a5_summary.py
/workspace/.venvs/geosim/bin/python -m compileall -q src tests scripts
bash -n scripts/run_b2_a5_pilot_matrix.sh
```

Historical merged implementation CI: PR15 heada595bcf, [run39947778403](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39947778403)/job120394555595:95passed116.27s +1087passed234.45s, zero skipped/failed. PR14 final head25f984d, run39928576202/job120330933282:1087passed234.26s. Recovery PR exact-head CI is recorded in its description after publication. These are distinct environments and source revisions.
