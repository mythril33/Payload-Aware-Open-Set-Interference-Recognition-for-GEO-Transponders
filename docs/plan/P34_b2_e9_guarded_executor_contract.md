# P34 — E9 guarded-executor engineering contract (non-executing)

Date: 2026-10-24. Base `main` `a5e3b7b8a87ed7b9fb41f513ddb8bb6b685ec4b1` (the brief named `d14f31d`; PR #27 had merged since, with the same scientific record).
`benchmark_complete=false`. **Engineering readiness, not runtime authorization.** This contract adds one source file, one test file and this
document. It starts nothing, enables nothing and changes no physics, metric, held-out rule, config, gate value, CPU fixture cap or
`PRODUCTION_LAUNCH_ENABLED` (still `False`). Scientific approval (OBS-CANCEL/2 A, K17d A+C, K18/R3 A, R1-R10 A; record
[B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md](B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md), [JSON](b2_e9_approved_scientific_protocol.json))
is one thing; generation, GPU probe, full training and LOKO are four other authorizations, none granted.

## 1. Architecture

`src/geoml/b2_e9_contract.py` is pure: standard library only (`copy`, `hashlib`, `json`, `math`, `re`), no file, environment, clock, network, GPU
or subprocess access, no mutation of its inputs. Every validator takes plain dicts and returns a strict-JSON report
`{contract, kind, ok, failures[{field, code, expected, actual}], authorizes_nothing: true, ...}`; codes are `MISSING`, `CONFLICT`, `UNEXPECTED`,
`TYPE`, `NONFINITE`, `INVALID`. A report with `ok=true` is a statement about a record, never a permission (`authorizes_nothing` is fixed).

| Contract | Entry points | What it enforces |
|---|---|---|
| Scientific configuration | `APPROVED_CONFIG`, `validate_scientific_config`, `validate_protocol_record`, `config_from_protocol` | The explicit configuration equals the approved one field by field: views, seeds 0/1/2, width 16, time_pool 2, carrier, 30 epochs, batch 32, CE + 0.005 centre-sum + 1.0 plan BCE with the plan head on, K17b 15 % / 0.5 MHz, AdamW and OneCycleLR constants, fp32 with mixed precision, cuDNN TF32 and matmul TF32 all off, 4 groups/shard x 4 shards/window, P31 phases, R9 restart, 0.95 / 0.05 / 0.1. Missing, conflicting, unexpected, mistyped (a bool is not a number) and non-finite fields each fail explicitly; derived consistency (steps per fit, peak learning rate = scheduler maximum) is checked too. The approved JSON record is validated as such (not executable, no activation, no production authorization, 13 decisions with the approved choices, every control true) and the reference is **derived from it** (`config_from_protocol(record) == APPROVED_CONFIG`, tested), so a drift of either side fails. Bare `TrainConfig` defaults (centre weight 0, plan head off, no shift) fail the validator. |
| Execution state | `STATES`, `TRANSITIONS`, `transition`, `evaluate_state`, `authorization_status`, `guard_execution`, `runtime_permitted` | `NOT_AUTHORIZED -> ENGINEERING_READY -> AWAITING_SEPARATE_APPROVAL`; **no runnable or running state exists** and `transition` names such targets as refused. `NOT_AUTHORIZED` unless the record, the configuration and the K18/K17d/OBS-CANCEL-2 gate approvals (provenance fields, matching approver and record) agree and `benchmark_complete` is false; `ENGINEERING_READY` with that; `AWAITING_SEPARATE_APPROVAL` additionally with exact-head evidence (independent review of the same source head with zero open material findings, exact-head CI success). Each of generation, GPU probe, full training and LOKO is judged on **its own** gate only (the probe has no gate and is always `NOT_AUTHORIZED`); at best `APPROVAL_RECORDED_NOT_RUNNABLE`. `guard_execution(action)` is the call a future executor must make first: it validates the name and **always raises** `ExecutionNotAuthorized`. A truthy production-launch flag passed in is an inconsistency that forces `NOT_AUTHORIZED`. |
| Nine-cell freeze | `validate_nine_cell_freeze` | Metadata only (no artifact opened): exactly three views x three seeds, each cell `COMPLETE` with 30 epochs and a selected epoch in range, zero held-out reads, identical base-config hash, data identity, source tree, environment id, profile and calibration constants (0.95 / 0.05 / 0.1) across all nine, and **all model, scorer and calibrator hashes distinct** (a renamed checkpoint cannot stand in for another seed or view). The report's `evaluation_admissible` is about the freeze only. |
| Restart provenance | `make_attempt_record`, `record_hash`, `validate_attempt_chain` | `attempt_id`, status `INCOMPLETE` / `COMPLETE`, parent attempt and hash, `start_epoch == 0`, nothing carried (`carried_state` optimizer, scheduler, rng, weights and cursor all `null`); any extra field such as `optimizer_state_sha256` or `resume_from_epoch` is `UNEXPECTED`. A restart follows an `INCOMPLETE` parent only, with the same view, seed, source, data and environment; at most one restart per attempt and one `COMPLETE` attempt per cell; no cycles. |
| Resources and lock | `validate_environment_record`, `validate_resource_ceilings`, `validate_backup_location`, `validate_lock_requirements` | Schemas for GPU model / count (exactly one) / VRAM / driver, CUDA, cuDNN, torch, Python, NumPy, SciPy, the effective TF32 and mixed-precision flags, git commit, clean tree, source tree hash and per-file `src/` hashes, thread variables, six explicit positive ceilings, and a backup on a **different device** (the 9 GB minimum is the E5 proposal and is a parameter). `validate_lock_requirements` describes what a future lock must hold and **refuses a document that claims to be one** (`created` must be false, no `lock_fingerprint`, `authorized` false). |

## 2. Why this cannot bypass the existing authorization system

* It does not import `scripts/` or the supervisor; the supervisor (`PRODUCTION_LAUNCH_ENABLED False`, `--limit-groups 1..2`, `stage_argv` refusing an
  unbounded command), the preflight gate check and the gates JSON stay the only authorization machinery. A test cross-checks that this module's
  structural approval verdict agrees with the preflight's `check_gates`.
* There is no function that returns "runnable", no constant that enables execution, and a test proves that patching module attributes cannot change
  `runtime_permitted()` or the guard.
* An approval record in a gate yields only `APPROVAL_RECORDED_NOT_RUNNABLE`; approving one authorization never changes another.
* Naming: numeric-flag fields are `cudnn_tf32_enabled`, `matmul_tf32_enabled`, `mixed_precision_enabled`, and the module reads the approved record's
  library-style keys by stem (`_by_stem`) so that it never spells the library attribute names. `tests/test_b2_training_footprint.py::test_repository_facts_cited_as_engineering_only_still_hold`
  (no source pins numerics) therefore still passes and will fail, deliberately, when the real executor sets the flags.

## 3. Tests (`tests/test_b2_e9_contract.py`, CPU-only, synthetic metadata and fake artifacts, 165 tests)

Fail-closed coverage: 35 conflicting and 13 missing critical configuration fields, unexpected / mistyped / non-finite values, a configuration built from bare
`TrainConfig` defaults, 13 over-reaching or malformed scientific records, malformed scientific approvals (each provenance field, wrong approver, bad time,
null approval, `benchmark_complete=true`), each runtime authorization approved alone (others stay closed), malformed compute approvals (missing ceilings,
approval attached to a pending gate, unknown status), every illegal transition, the guard under all inputs, 22 nine-cell failures (incomplete, duplicate,
renamed or reused artifacts, held-out read, mixed provenance or calibration, wrong epochs), 21 restart failures (epoch > 0, each kind of carried state,
extra resume fields, broken parent hash, changed view / seed / source / data / environment, two completions, branching, cycles), 18 missing and 15
conflicting environment fields (including every TF32 / mixed-precision pin), ceilings, same-device backup, lock-document refusals, and static checks that the
module imports only the standard library, contains no I/O or execution call, mutates no input and touches no file.

## 4. Remaining E9 implementation gaps (not done here, by design)

1. The executor itself: a reviewed GPU-capable isolated mode for the approved recipe behind `guard_execution`, with the P31 caps lifted only through an
   explicit, reviewed profile (`src/geoml/b2_execution.py:39,92`, `src/geoml/b2_experiment.py:54,819` are unchanged).
2. Setting and asserting the effective numerics (`B2-R6-fp32-tf32-off/1`) at runtime, and persisting the environment record in checkpoints and the lock.
3. Wiring the attempt records and the freeze validator to real training / calibration artifacts (this contract validates metadata, not files).
4. The production argv builder, first-shard gate and release-gate record (`audit.release_gate_not_machine_checked`); the production lock (extend the lock's
   environment fields to the schema above); the probe harness (specification only, `b2_e8_gpu_probe_spec.json`).
5. Source changes must be completed and independently reviewed **before** a production source lock: this PR adds one `src/geoml` file, so any lock must
   be created after the final executor edits.

## 5. Safety assessment

Engineering readiness here means the contracts exist, are tested and fail closed. It grants no runtime permission: generation, GPU probe, full training
and LOKO each remain `NOT_AUTHORIZED` with null approvals; resources, hosts, backup and ceilings are unresolved; `benchmark_complete=false`.
