# E8 production go/no-go report — **NO-GO** for every compute stage

Date: 2026-10-24. Base `main` `4a1cc95913b430fee5c5e7d2e54cf48c9feeb8d8`. `benchmark_complete=false`. This report authorizes nothing and changes no
gate. Status words: PASS = verified here (command or inspected location named); BLOCKED = needs a researcher decision, authorization, hardware, a
measurement or an engineering milestone; NOT_RUN = not executed. The full machine-checked list is the regenerated
[readiness checklist](B2_E6_PRODUCTION_READINESS_CHECKLIST.md) (PASS 36 / FAIL 0 / BLOCKED 19 / NOT_RUN 1).

## 1. Verdict per stage

| Stage | Verdict | Why |
|---|---|---|
| DR-04 full data generation (21,350 observations) | **NO-GO** | OBS-CANCEL/2, K17d not decided; no host, ceilings or backup designated; production launch is not implemented (`PRODUCTION_LAUNCH_ENABLED=False`); first-shard timing gate unvalidated at production size |
| DR-05 bounded GPU probe | **NO-GO** | no identified GPU host or caps; no probe executor exists (the isolated modes are CPU-only); R2/R5/R6 undecided |
| DR-05 nine production fits | **NO-GO** | needs the probe, K18/R1-R10, a production executor (width 16, 30 epochs, GPU) and the width-explicit budget |
| DR-06 full LOKO | **NO-GO** | needs production fits, a reviewed production dispatcher; 21 or 63 fits are separate budgets |
| What can proceed now | **GO** | read-only preparation: approvals recorded by the researcher, the engineering milestone of section 5, bounded CPU fixtures |

## 2. Findings

| Status | Item | Evidence |
|---|---|---|
| PASS | Verified `origin/main` is `4a1cc95`; PR #24 merged | `git fetch` + `git log`; E7b head `d1e0898` |
| PASS | Exact-head CI of PR #24: 1771 passed (E4 107 + repository 1664), 7 skipped, 0 failed | Actions run 40064513568 / job 120784837702, raw log read |
| PASS | Historical records reconciled with that CI; authorization states unchanged | gates `engineering.e7b_head_ci`, `verified_remote_main`; findings `audit.pr_head_ci`; `decisions` untouched, all `approval: null` |
| PASS | Gates fail closed: K18/K17d/OBS-CANCEL-2 `PENDING_RESEARCHER`, full_generation/GPU/LOKO `NOT_AUTHORIZED`, `benchmark_complete=false` | `python scripts/b2_production_preflight.py gates` (exit 4, six BLOCKED); CI step "Fail closed if any researcher gate is implicitly approved" |
| PASS | Production cannot be launched: `supervisor plan --production` exit 3 (BLOCKED: gates + `PRODUCTION_LAUNCH_ENABLED False`); `run --production --execute` exit 2 REFUSED; `run --execute` without `--max-groups` and with `--max-groups 3` exit 2 REFUSED; no workdir content created | commands run in E8 (section 3) |
| PASS | Production stays refused even if every gate carries a well-formed approval; every spawned child must carry `--limit-groups 1..2`; production ceilings cannot be raised | `tests/test_b2_production_supervisor.py::test_production_execution_stays_refused_even_with_every_gate_approved` and neighbours, `tests/test_b2_e8_tools.py` |
| PASS | E7b contract: isolated phases, nine-cell admission before any held-out read, bounded LOKO (<= 2 CPU cells per root) | P31, `tests/test_b2_execution*.py`, `docs/research/b2_e7b_review.md` (no material finding open) |
| PASS | Candidate configuration exists, is UNAPPROVED, equals the P6/P20 defaults and cannot be loaded by any runner | `docs/plan/b2_e8_candidate_production_config.json`, `tests/test_b2_e8_tools.py` |
| PASS | Width-explicit resource arithmetic; the width-8 6 GPU-h figure is withdrawn, not carried | `scripts/b2_e8_budget.py`, `docs/results/b2_e8_resource_budget.json` |
| PASS | Read-only host inventory; this sandbox fails both roles (19.7 GiB free on one device, no GPU, 15.1 GiB RAM) | `scripts/b2_host_inventory.py`, `docs/results/b2_e8_host_inventory_sandbox_*.json` |
| BLOCKED | Researcher decisions: K18, K17d, OBS-CANCEL/2, R1-R10, DR-04, DR-05, DR-06 | [decision-approval document](B2_E8_DECISION_APPROVAL.md) |
| BLOCKED | No executor for the approved recipe (CPU-only, caps 2 groups/role, 2 epochs, width 8, batch 32; legacy 12 groups/role, coupled) | `src/geoml/b2_execution.py:39,92`; `src/geoml/b2_experiment.py:54,819`; finding `audit.production_executor_missing` |
| BLOCKED | GPU probe specified, not implemented, not run | [spec](b2_e8_gpu_probe_spec.json); `audit.gpu_probe_executor_missing` |
| BLOCKED | Production host, GPU, backup, ceilings undesignated | [host assessment](B2_E8_HOST_RESOURCE_ASSESSMENT.md); `audit.compute_hosts_undesignated` |
| BLOCKED | Lock does not record CUDA/cuDNN/driver/GPU model/TF32 flags; no source pins TF32 (torch 2.14.1 default: cuDNN TF32 on) | `scripts/b2_production_preflight.py:323-331`; `git grep allow_tf32 -- src scripts` empty; `audit.lock_environment_lacks_gpu_pins` |
| BLOCKED | `TrainConfig` code defaults are `center_loss_weight 0.0` and `plan_shift_fraction 0.0`: the P20 centre term (0.005) and the K17b shift (15 %) live only in `configs/b2_feat.json`; a production config built from 'the defaults' would silently drop both | `src/geoml/train.py`; `configs/b2_feat.json`; finding `audit.trainconfig_defaults_disable_p20_terms` |
| BLOCKED | Release gate is a process step, not a machine-checked record | `audit.release_gate_not_machine_checked`; section 4 |
| BLOCKED | Not measured at scale: generation wall time, streaming memory/throughput, synchronous loader, GPU throughput/VRAM | checklist `audit.wall_time_unmeasured_at_scale`, `streaming_unmeasured_at_scale`, `loader_synchronous`, `training_budget_width_mismatch` |
| BLOCKED | Interrupted-training policy (R9) | `audit.training_interruption_recovery` |
| NOT_RUN | CI on this E8 head | recorded in the draft PR after publication |

Recorded, not fixed here (no protocol change is introduced): `docs/plan/P20_b2_cancellation_residual.md:135-136` still says the K17b plan shift "is not
implemented yet" although `src/geoml/train.py` implements it and `configs/b2_feat.json` enables it (frozen text; a correction is a researcher/§10 matter);
7 K18 golden tests skip on the CI runner (`tests/test_b2_train_diagnostics.py:392`), so the comparison with the origin/main capture is exercised locally,
not on the runner, and GPU parity is untested anywhere.

## 3. Fail-closed evidence run in E8 (read-only, scratch workdir outside Git)

| Command | Exit | Result |
|---|---|---|
| `scripts/b2_production_preflight.py gates` | 4 | BLOCKED: K18, K17d, OBS-CANCEL-2, full_generation, full_gpu_training, full_loko_sweep |
| `scripts/b2_production_supervisor.py plan --workdir W --production` | 3 | `supervisor.authorization` BLOCKED, `supervisor.production_launch` BLOCKED (`PRODUCTION_LAUNCH_ENABLED is False`) |
| `scripts/b2_production_supervisor.py run --workdir W --production --execute` | 2 | REFUSED: production execution refused: four gates BLOCKED |
| `scripts/b2_production_supervisor.py run --workdir W --max-groups 3 --execute` | 2 | REFUSED: a bounded run needs `--max-groups 1..2` |
| `scripts/b2_production_supervisor.py run --workdir W --execute` | 2 | REFUSED: same |

## 4. Release gate (the process the supervisor's flag stands for)

Enabling an unbounded launch is a code change (`PRODUCTION_LAUNCH_ENABLED`, an unbounded command builder, the production first-shard gate). Its release
is a separate milestone that must show, in the merged PR: (a) the researcher's recorded approvals in the gates JSON (`approved_by`, `approved_at`,
`decision`, `record`, ceilings) for K18, K17d, OBS-CANCEL-2 and `full_generation`, and `gates` PASS; (b) the exact head hash and a clean production lock;
(c) an independent read-only review of the unbounded command builder and of the first-shard gate, written to `docs/research/` with the reviewed head
hash and no open material finding; (d) green exact-head CI; (e) a production-size host assessment (`b2_host_inventory.py` + preflight `resources` on the
designated host). Items (b)-(d) are not machine-checked today (`audit.release_gate_not_machine_checked`); a self-asserted JSON field is not authentication, the
control is review at merge.

## 5. Sequencing constraint (why order matters)

Checkpoint provenance hashes every `src/**/*.py`, and the production lock hashes the same tree: the executor milestone (width 16 / 30 epochs / GPU /
numerics pin, probe harness, lock environment fields) must be merged **before** the lock, the data run and any fit. Required order:
researcher decisions (OBS-CANCEL/2, K17d, K18 with R2-R10) -> engineering milestone E9 (independent review) -> lock on a clean tree on the designated host ->
`resources` / `b2_host_inventory.py` there -> DR-04 generation (supervisor, first-shard gate) -> audit/transfer -> DR-05 probe -> DR-05 nine fits ->
frozen nine-cell evaluation -> DR-06 LOKO. Skipping or reordering invalidates locks or checkpoints, not just schedules.

## 6. The exact commands

**(a) Safe now and after approval (read-only or bounded; nothing is launched):**

```bash
source /workspace/.venvs/geosim/bin/activate; export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python scripts/b2_production_preflight.py gates                       # exit 0 only after the researcher's records are entered
python scripts/b2_host_inventory.py --role generation --path ROOT --backup-path BACKUP --out host_generation.json
python scripts/b2_host_inventory.py --role training   --path ROOT --out host_training.json
python scripts/b2_production_preflight.py lock-create --out OUTSIDE_GIT/production.lock.json    # clean tree only, after the E9 merge
python scripts/b2_production_preflight.py lock-verify --lock OUTSIDE_GIT/production.lock.json --require-clean
python scripts/b2_production_supervisor.py plan --workdir ROOT --production                    # validation only; exit 4 until the launch milestone
```

**(b) There is deliberately no runnable production-generation, probe or training command.** The supervisor never builds an unbounded command
(`stage_argv` raises for `limit_groups=None`), the isolated runner refuses `--device cuda`, and the probe has no executor. The next command is therefore
the researcher's decision message ([templates](B2_E8_DECISION_APPROVAL.md) section 4) followed by this Claude Code prompt:

> E9 - Production executor milestone (engineering only). Read B2_E8_DECISION_APPROVAL.md, B2_E8_GO_NO_GO.md and the researcher decisions I recorded in the gates
> JSON. Implement, behind explicit authorization flags and with every cap tied to an approved record: a GPU-capable isolated executor for the approved recipe
> (width/epochs/batch, the R6 numerics pin, restart policy R9), the bounded probe harness of b2_e8_gpu_probe_spec.json, and the lock environment fields
> (CUDA/cuDNN/driver/GPU/TF32). Do not generate data, train, or run any GPU computation. Keep benchmark_complete=false, leave all gates as recorded, add
> only stand-in tests, get an independent read-only review, open a draft PR, no auto-merge.
