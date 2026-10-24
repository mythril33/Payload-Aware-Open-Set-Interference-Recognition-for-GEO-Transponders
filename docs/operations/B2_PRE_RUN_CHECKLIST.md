# B2 pre-run GO / NO-GO checklists (E11-B)

**Status: PROPOSAL. These checklists authorize nothing, enable nothing and change no gate.** Date: 2026-10-24. Base `origin/main`
`293c487d2fd236286e59f6a0ef941feb8ff1b708`. `benchmark_complete=false`. Companions:
[resource budget reconciliation](B2_RESOURCE_BUDGET_RECONCILIATION.md), [compute approval requirements](B2_COMPUTE_APPROVAL_REQUIREMENTS.md).

How to use: a stage is **GO** only when every row of its checklist is `MET` with the evidence named in that row, **and** the researcher has
issued that stage's own written authorization (see the approval requirements). A single `OPEN` row is a NO-GO. Scientific approval of the protocol
(K18, K17d, OBS-CANCEL-2, R1-R10) is a prerequisite for every stage but is not a compute authorization, and approving one stage never approves
another. "Current" is the state at the base commit; it is a snapshot, not a promise.

Evidence conventions: *cmd* = a read-only command whose output is archived outside Git with the run journal; *rev* = an independent read-only
review written to `docs/research/` naming the reviewed head hash; *rec* = a dated written researcher record; *ci* = green CI on the exact head.
Self-asserted JSON fields (hashes, approvals, review claims inside records) detect accident, not forgery; the control is review at merge.

## Current verdict (all stages NO-GO)

| Stage | Verdict | Blocking reasons today |
|---|---|---|
| G - full generation (DR-04) | **NO-GO** | `full_generation` NOT_AUTHORIZED; `PRODUCTION_LAUNCH_ENABLED=False` and no unbounded command builder; no host/ceilings/backup designated; no production lock; D-1 open |
| P - bounded GPU probe | **NO-GO** | no probe executor, no gate for it (always `NOT_AUTHORIZED`), no identified GPU host, no pre-registered parity tolerance |
| T - nine-fit training | **NO-GO** | `full_gpu_training` NOT_AUTHORIZED; no width-16/30-epoch/GPU executor (`src/geoml/b2_execution.py:39,92` cap 2 groups, 2 epochs, width 8, CPU only; `src/geoml/b2_experiment.py:819` refuses `--device cuda`); no probe; no measured budget |
| F - nine-cell freeze | **NO-GO** | no completed fits; no real-artifact freeze wiring (E9 `validate_nine_cell_freeze` checks metadata only) |
| E - test evaluation | **NO-GO** | no frozen cells; D-1 (held-out exposure) undecided; no separate authorization |

## X. Cross-cutting requirements (apply to every stage)

| ID | Requirement | Evidence | Current |
|---|---|---|---|
| X-1 | **Source fingerprint.** Clean git tree at the exact reviewed head; production lock created from it; the lock's source tree hash equals the hash of every `src/**/*.py` used by checkpoints. The lock is created **after** the last executor edit: any later `src` change invalidates the lock and every historical checkpoint (they are refused, never relabelled). | *cmd* `scripts/b2_production_preflight.py lock-create` / `lock-verify --require-clean`; E9 `validate_lock_requirements` describes the fields | OPEN: no lock; executor milestone not built |
| X-2 | **Environment pin.** Exact versions recorded in the lock: Python, NumPy, SciPy, torch, CUDA, cuDNN, NVIDIA driver, GPU model and count, the four environment variables the E9 contract requires (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `PYTHONHASHSEED`) and the effective numerics flags. `pyproject.toml` pins only `numpy>=1.24`, `scipy>=1.10`, `torch>=2.2`, so the lock, not the project file, is the pin. `scripts/b2_production_preflight.py:323-331` records versions/threads only, not CUDA/cuDNN/driver/GPU/TF32. | E9 `validate_environment_record` schema; a lock that includes the GPU fields | OPEN: lock lacks GPU fields (`audit.lock_environment_lacks_gpu_pins`) |
| X-3 | **Immutable data identity.** Every artifact binds its request (config, source hashes, roles, groups) into a fingerprint and checksums every shard; readers verify before use. After DR-04 verification the artifact root is made read-only and a manifest (path, length, SHA-256, artifact fingerprint) is stored outside Git and on the backup device. Archive immutable object versions, never mutable symlinks. A transfer or restore revalidates every shard before training. Never relax a validator to make stale data load. | *cmd* manifest verification on the training host; *rec* manifest hash recorded in the run journal | OPEN: no production data |
| X-4 | **Numerics: TF32 off.** Profile `B2-R6-fp32-tf32-off/1`: fp32 everywhere, mixed precision off, cuDNN TF32 off, matmul TF32 off. The effective flags are **read back at runtime before the first optimizer step** (and written into every checkpoint, calibration and report), not inferred from code. torch's default leaves cuDNN TF32 on (E8: torch 2.14.1), and no source pins it today. Any mismatch aborts the fit. Proposal: also record `torch.get_float32_matmul_precision()` and the cuDNN deterministic/benchmark flags as evidence (the approved record does not require determinism; GPU parity is untested anywhere). | probe report `numerics` field; E9 `validate_environment_record` effective-flag fields; a runtime assertion in the (future) executor | OPEN: no executor sets or reads the flags |
| X-5 | **Interruption handling.** Generation: resume only under an identical request/source/environment; shard-level commit (a hard stop loses at most one 4-group shard: 32 known / 20 test-only / 12 matched observations); damaged committed shards stop the run and go to a fresh root or documented restoration; orphan work is quarantined, never counted. Training (R9): an interrupted fit restarts from epoch 0 under a new `attempt_id` with parent hash, no optimizer/scheduler/RNG/cursor/weights carried; never splice partial epochs. | supervisor journal (hash-chained, anchored), heartbeats, completion marker only after a clean attempt; E9 `validate_attempt_chain` | PARTIAL: supervisor exists for bounded runs (<= 2 groups); production launch and training restart executor not built |
| X-6 | **External run journal.** Planned/completed/failed/missing counts, per-attempt command, real exit code, elapsed and CPU time, peak RSS (and peak VRAM for GPU stages), stored outside Git on a device different from the working data. | journal file path in the approval | OPEN |
| X-7 | **No bypass.** No flag flipped in `src/` or `scripts/` to start a stage; `guard_execution` of the E9 contract always raises; production authorization lives in `docs/plan/b2_readiness_gates_2026-10-21.json` plus the code release gate (exact-head independent review, green CI, clean lock; `audit.release_gate_not_machine_checked`). | *rev* of the launch change | OPEN |
| X-8 | **Order.** decisions -> executor milestone (reviewed, merged) -> lock on clean tree on the designated host -> host inventory there -> G -> verify, manifest, read-only -> P -> T -> F -> E. Reordering invalidates locks or checkpoints, not just schedules. (Proposal: the synthetic, data-free part of P may run before G; it still needs the final lock.) | this table | binding |

## G. Generation GO / NO-GO (DR-04: 21,350 observations)

| ID | Check | Evidence | Current |
|---|---|---|---|
| G-1 | Researcher authorization for `full_generation` with named host, ceilings and backup, recorded in the gates JSON (`approved_by`, `approved_at`, `decision`, `record`, ceilings) | *rec*; `preflight gates` shows `full_generation` approved | OPEN (NOT_AUTHORIZED) |
| G-2 | Scientific gates K18, K17d, OBS-CANCEL-2 `APPROVED` | `preflight gates` | MET (PASS in the snapshot above) |
| G-3 | E10 decision D-1 (held-out exposure) recorded before any test-role stage is generated; if option B is chosen, a new protocol version and its own authorization exist first | *rec* | OPEN |
| G-4 | Launch milestone merged: unbounded command builder, production first-shard gate, release-gate record; independent review of both | *rev*, *ci* | OPEN (`PRODUCTION_LAUNCH_ENABLED=False`) |
| G-5 | Production lock created and verified on a clean tree (X-1, X-2) | `lock-verify --require-clean` | OPEN |
| G-6 | Host meets the proposed generation profile and ceilings (4 vCPU, >= 8 GiB RAM, >= 25 GiB working disk free, backup on a different device >= 9 GB) | `scripts/b2_host_inventory.py --role generation --path ROOT --backup-path BACKUP`; `preflight resources` | OPEN: sandbox fails (19.7 GiB free on one device, no separate backup) |
| G-7 | First-shard timing gate passes against the proposed wall ceiling (36 h) using the supervisor's recorded timing | supervisor journal | OPEN: gate not validated at production size |
| G-8 | Disk watermark and ceilings enforced by the supervisor (min free disk 25 GiB, RSS 2 GiB per process, 36 h wall, 42 core-h) | supervisor `plan` output | PARTIAL: ceilings exist in code for bounded runs; production ceilings are constants, not approvals |
| G-9 | Source/request/environment identity for resume is the lock's; stages run known -> test-only -> matched; roles never cross; test-only and matched never touch fitting | supervisor plan; artifact validators | designed, unrun |
| G-10 | Backup procedure written: second copy checksum-verified before the working copy is made read-only | *rec* | OPEN |
| G-11 | Stop conditions written: any failed shard, any validator refusal, any ceiling breach -> stop, quarantine, report; no cleanup that destroys evidence | journal template | OPEN |

## P. GPU probe GO / NO-GO (DR-05 probe; specification only today)

| ID | Check | Evidence | Current |
|---|---|---|---|
| P-1 | A separate researcher message naming the host, the one CUDA device and the caps (the `b2_e8_gpu_probe_spec.json` caps or tighter) | *rec* | OPEN: no gate exists for the probe (always `NOT_AUTHORIZED`) |
| P-2 | Probe executor exists, was independently reviewed, refuses val-calib, test, B2-test/1, B2-match/1 and more than one visible GPU | *rev*, tests | OPEN: not implemented |
| P-3 | Lock verified on a clean tree (the probe runs the code that would train) | `lock-verify` | OPEN |
| P-4 | Parity tolerance for GPU vs CPU fp32 pre-registered by the researcher **before** the probe is run | *rec* | OPEN |
| P-5 | Spec gaps resolved (see approval requirements G-1..G-4): val-select forward-only rate, K17b shift enabled in the timed loop, storage read rate, GPU clock/thermal state | spec revision | OPEN |
| P-6 | Caps applied: <= 1,800 s total, <= 300 s per configuration, 20 warm-up and <= 400 timed steps, <= 2 epoch-equivalents, 1 GPU, host RSS <= 8 GiB, VRAM <= 0.8 of device, <= 1 persisted file, 0 retained checkpoints, no network | probe report `caps_applied` | designed, unrun |
| P-7 | Output schema `B2-gpu-probe-report/1`, exclusive creation, `benchmark_complete=false`, `production_authorized=false` | probe report | designed |
| P-8 | Results are not used to change width, epochs, batch, loss or any fitted choice; a ceiling is derived from the end-to-end rate by the researcher, with the margin stated | *rec* | binding |

## T. Nine-fit training GO / NO-GO (DR-05)

| ID | Check | Evidence | Current |
|---|---|---|---|
| T-1 | Researcher authorization for `full_gpu_training` with a **GPU-hour ceiling derived from the probe** (not 6 h, not the 10 - 22 h screening band), a wall ceiling and a restart allowance | *rec* | OPEN (NOT_AUTHORIZED) |
| T-2 | Executor for the approved recipe merged and independently reviewed: width 16, time_pool 2, carrier, 30 epochs, batch 32, AdamW 1e-3 / 1e-4, OneCycleLR, CE + 0.005 centre-sum + 1.0 plan BCE with the plan head on, K17b 15 % / 0.5 MHz, fp32 | *rev*; E9 `validate_scientific_config` equals `APPROVED_CONFIG` | OPEN (E9 validates records; no executor) |
| T-3 | Bare `TrainConfig` defaults are never used (centre weight 0, plan head off, no shift) | E9 validator fails them | contract exists; executor OPEN |
| T-4 | Probe report reviewed; TF32-off cost and parity are known; budget arithmetic stated for 3,240,000 passes | probe report | OPEN |
| T-5 | Immutable data identity on the training host (X-3); roles train / val-select only visible to fitting; val-calib not opened until calibrate; test not opened | manifest verification; isolated-mode role scoping (`train-only`) | designed (P31) |
| T-6 | Environment/TF32 flags read back and recorded before step 1 of every fit (X-4) | checkpoint metadata | OPEN |
| T-7 | Resource profile T present on the host: GPU >= 8 GiB (12 GiB preferred), host RAM >= 16 GiB, >= 25 GiB free disk, CPU threads pinned | `b2_host_inventory.py --role training` | OPEN: sandbox has no GPU |
| T-8 | Interrupted-fit policy accepted: restart from epoch 0 under a new attempt; each restart costs up to one fit (about 0.33 - 1.7 h compute at the assumed 302 - 60 samples/s plus 0.65 - 0.78 h loader); the restart allowance is in the ceiling | E9 `validate_attempt_chain` | policy approved (R9); executor OPEN |
| T-9 | Checkpoint rule: best epoch by val-select, strict-greater first maximum; training-time diagnostics observation-only | checkpoint metadata | approved; executor OPEN |
| T-10 | No automatic batch reduction on OOM: an out-of-memory error stops the run for a decision | executor test | OPEN |

## F. Nine-cell freeze GO / NO-GO

| ID | Check | Evidence | Current |
|---|---|---|---|
| F-1 | Exactly 3 views x seeds 0/1/2, each cell `COMPLETE` with 30 epochs and a selected epoch in range | E9 `validate_nine_cell_freeze` on the real cell records | OPEN |
| F-2 | Calibration used only the known val-calib role: known-acceptance target 0.95, Mahalanobis shrinkage 0.1 and the clean-alarm threshold (pfa 0.05) by the higher empirical quantile at 1 - pfa (`clean_alarm_threshold`, alarm strictly `score > threshold`); Mahalanobis fitted on train only | calibration artifacts | approved; execution OPEN |
| F-3 | All model, scorer and calibrator hashes distinct; training-config hash equals the approved digest; identical data identity, source tree, environment id and numerics profile across the nine cells | `validate_nine_cell_freeze` | contract exists; wiring to files OPEN |
| F-4 | Zero held-out reads recorded in all nine cells (journal and artifact read logs) | journal | OPEN |
| F-5 | One freeze manifest (hashes of the nine cells and thresholds) written outside Git, signed into the run journal and the backup **before** the evaluation authorization is requested | manifest | OPEN |
| F-6 | A failed cell is handled by the approved restart rule only; a replaced cell is a new attempt with a visible chain, never silent substitution; no cell is selected or dropped on the basis of any outcome | attempt chain | binding |

## E. Test evaluation GO / NO-GO (once, read-only)

| ID | Check | Evidence | Current |
|---|---|---|---|
| E-1 | Separate researcher authorization for the single test read, issued **after** F-5 | *rec* | OPEN: no gate for this step exists (proposal: record it as its own written authorization; a gate belongs to a later engineering milestone) |
| E-2 | E10 decision D-1 recorded; the exposure statement (test groups 3200000/3200001, matched 3300000/3300001) travels with every held-out number; the sensitivity row excluding exposed groups is prepared | *rec* | OPEN |
| E-3 | Evaluate mode is read-only: it cannot calibrate, select, fit, tune or write thresholds; it refuses unless all nine cells verify against the freeze manifest | isolated-mode tests (`tests/test_b2_execution.py` isolation tests) | designed (P31); production wiring OPEN |
| E-4 | Legacy coupled path unreachable for this run (it opens and evaluates test before freeze; audit M-10) | run command is the isolated `evaluate` mode only | OPEN (follow-up) |
| E-5 | Primary endpoint, multiplicity and reporting plan (E10 decision D-4) fixed before the read; K17d A+C rows (headline 500, sensitivity 465, co-feed 35) both reported | *rec* | OPEN |
| E-6 | Outputs written exclusively-created to a fresh directory; no overwrite; a second read is a new, separately authorized run, never a re-run to improve a number | journal | binding |
| E-7 | `benchmark_complete` stays false until the researcher accepts all scientific requirements, ablations and reviews | gates JSON | binding |

## Appendix: read-only commands that are safe now

```bash
source /workspace/.venvs/geosim/bin/activate
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python scripts/b2_production_preflight.py gates                                   # exit 4 until compute gates are approved
python scripts/b2_host_inventory.py --role generation --path ROOT --backup-path BACKUP --out host_generation.json
python scripts/b2_host_inventory.py --role training   --path ROOT --out host_training.json
python scripts/b2_e8_budget.py                                                    # arithmetic only; prints no reservation
```

There is deliberately **no** command here that generates data, probes a GPU, trains, freezes or evaluates. None exists in the repository.
