# B2 compute approval requirements (E11-B)

**Status: PROPOSAL. Every number below is a proposed ceiling or a planning figure. None is an authorization, none is recorded in a gate, and
none changes `PROPOSED_CEILINGS`, the supervisor ceilings or any code.** Date: 2026-10-24. Base `origin/main`
`293c487d2fd236286e59f6a0ef941feb8ff1b708`. `benchmark_complete=false`. Companions: [resource budget reconciliation](B2_RESOURCE_BUDGET_RECONCILIATION.md),
[pre-run checklists](B2_PRE_RUN_CHECKLIST.md).

The scientific protocol is approved (K18, K17d, OBS-CANCEL-2, R1-R10). Compute is not: `full_generation`, `full_gpu_training` and
`full_loko_sweep` are `NOT_AUTHORIZED`, the GPU probe has no gate and is always `NOT_AUTHORIZED`, and `PRODUCTION_LAUNCH_ENABLED=False`. Each
authorization below is separate; approving one never approves another.

## 1. What every compute approval must contain

A written researcher record (and, for the three gated stages, the matching entry in the gates JSON) must state all of:

1. **Scope:** one stage only (G, P, T, F or E of the [checklists](B2_PRE_RUN_CHECKLIST.md)), its observation/fit counts, and an explicit list of what it does **not** authorize.
2. **Code identity:** the exact git head, the lock fingerprint, and the independent review (path and reviewed head) of the code that will run.
3. **Host identity:** hostname or asset id, the output of `scripts/b2_host_inventory.py` for the stage's role, GPU model/count/VRAM, driver, CUDA, cuDNN, torch, Python.
4. **Ceilings:** wall hours, core-hours (CPU stages) or GPU-hours (GPU stages), working disk, backup size and device, host RAM, per-process RSS, VRAM; plus the restart allowance.
5. **Data identity:** the artifact fingerprints and manifest hash the stage may read, and the roles it may not read.
6. **Numerics:** `B2-R6-fp32-tf32-off/1` with the effective flags to be read back at run time (X-4).
7. **Journal and backup:** where the run journal lives, where the verified backup lives, and that both are on devices different from the working data.
8. **Stop conditions and expiry:** the events that stop the run (any failed shard, validator refusal, ceiling breach, OOM, flag mismatch) and a date after which the approval lapses.
9. **Signer, date, record path.** The record may not be inferred from a plan, a pull request or a passing test.

An approval that omits an item is incomplete and the stage stays NO-GO. A raised ceiling is a new approval.

## 2. Proposed ceilings (proposals, not authorizations)

| Stage | Resource | Proposed ceiling | Origin and class |
|---|---|---|---|
| G generation | wall time | 36 h (central estimate 26.6 h; band 22.5 - 30.2 h) | E5 plan, carried unchanged; extrapolation |
| G | CPU consumption | 42 core-h (estimate 26 - 35) | E5 plan; extrapolation |
| G | working disk free at start | **about 34 GiB** on the data device: the supervisor requires `free >= 1.1 x 7.86 GiB + 25 GiB reserve` (`scripts/b2_production_supervisor.py:891`), while the preflight check only compares free space with 25 GiB (`scripts/b2_production_preflight.py:748`) | arithmetic here; the two readings of "25 GiB" differ and the stricter one is binding for the launch |
| G | backup | **12 GB** on a different device, checksum-verified (E5 floor 9 GB leaves about 3 % over the 8.7 GB artifacts; proposed 12 GB covers manifests, journals and checkpoints) | E5 plan 9 GB floor; the 12 GB figure is an E11-B proposal |
| G | RAM | 2 GiB RSS per generator process; 8 GiB host | E5 plan; measured peak 566 - 601 MiB at 2 groups / 60 observations |
| G | failures | at most 2 failed attempts and 20 interruptions per stage (supervisor constants) | supervisor `PRODUCTION_CEILINGS` |
| P probe | total / per configuration | <= 1,800 s / <= 300 s | `b2_e8_gpu_probe_spec.json` caps |
| P | steps | 20 warm-up, <= 400 timed, <= 2 epoch-equivalents | spec |
| P | devices / host RSS / VRAM | 1 GPU / <= 8 GiB / <= 0.8 of the device | spec |
| P | persistence | <= 1 file written, 0 checkpoints retained, no network | spec |
| T training | GPU-hours | **no figure is proposed before the probe.** Formula in section 4 | the 6 GPU-h width-8 figure is withdrawn; 10 - 22 h is a screening band, not a ceiling |
| T | GPU memory | >= 8 GiB minimum, 12 GiB preferred (analytic need 0.45 - 0.88 GiB plus CUDA context; unmeasured, do not lower without the probe) | E5 plan / `PROPOSED_CEILINGS` |
| T | host RAM / disk | >= 16 GiB RAM; >= 25 GiB free including its own verified 8.1 GiB data copy | E5 plan; plan assumption |
| T | restarts | R9: from epoch 0, up to one fit lost per interruption; researcher states the number of restarts the ceiling covers | R9, E7 proposal |
| F freeze | compute | CPU/GPU inference over val-calib (1,200 observations x 9 cells) and scorer/calibrator fits; **not budgeted anywhere**; to be sized from the probe's forward-only rate | gap |
| E evaluation | compute | one read-only pass over 6,950 held-out observations x 9 cells; **not budgeted anywhere**; same sizing rule | gap |

**Planning envelope for procurement only (not a ceiling).** Applying the formula of section 4 with a 25 % margin and two lost-fit restarts to the
unmeasured screening band of 9.95 - 21.87 h gives roughly 15 - 32 GPU-hours of booking for stage T. This describes the order of magnitude to
reserve a host, nothing more; it inherits every uncertainty of the assumed throughput (reconciliation section 4.1, finding 5).

## 3. Resource profiles and the smallest sufficient setup

No profile below weakens a scientific decision: group counts, width 16, batch 32, 30 epochs, nine fits, fp32/TF32-off and all caps stay as approved.
Nothing here is measured on a target host; the sandbox fails both profiles (15.1 GiB RAM, 19.7 GiB free on one device, no GPU).

| Profile | Role | Minimum (proposal) | Notes |
|---|---|---|---|
| **G** | generation, CPU only | 4 vCPU, 8 GiB RAM, >= 34 GiB free on the data volume, a **second device** with >= 12 GB for backup | one generator process with two BLAS threads; 2 vCPU is untested and not proposed; no multiprocess writer exists, so more cores do not shorten the 23 - 30 h |
| **T** | training, one GPU | 1 CUDA GPU (>= 8 GiB, 12 GiB preferred), >= 2 vCPU (4 recommended so the synchronous loader is not starved), 16 GiB RAM, >= 25 GiB free, its own verified copy of the 8.1 GiB artifacts, pinned CUDA/cuDNN/driver | exactly one visible GPU (`CUDA_VISIBLE_DEVICES`); fits run sequentially; no automatic batch reduction |
| **G+T combined** | one machine | union of the above: 4 vCPU, 16 GiB RAM, one GPU, >= 34 GiB free data volume, second device >= 12 GB | removes the transfer and re-verification step but idles the GPU for 23 - 30 h during generation |

**Smallest sufficient setup (recommendation, researcher's choice):** two roles on whichever hosts are cheapest to book, joined by a verified transfer:
a CPU-only host for G (about 1 - 1.3 days of wall time) and one single-GPU host for P, T, F and E. A combined host is acceptable if no separate
CPU host exists. Either way the setup is minimal in the sense that nothing smaller than 4 vCPU / 8 GiB / 34 GiB free / backup device (G) or one
>= 8 GiB GPU / 16 GiB RAM / 25 GiB free (T) has been argued for, and nothing larger is needed by any figure in the record. A larger GPU than 12 GiB
is justified only if the probe shows a higher footprint.

**Recovery and backup.** Generation state lives in committed 4-group shards (loss <= 32 / 20 / 12 observations); resume is allowed only under the
identical request, source and environment; a damaged committed shard stops the run. The backup is made after verification and before the working copy is
made read-only; a restored copy revalidates every shard before use. Training state is the attempt chain; an interrupted fit is rerun from epoch 0
(about 0.33 - 1.7 h of compute at the assumed rates plus 0.65 - 0.78 h of loader time at width 16). Checkpoints are about 1.2 MiB per fit and are
copied to the backup device after each completed fit.

**Environment pinning.** The lock must record exact Python, NumPy, SciPy, torch, CUDA, cuDNN, driver, GPU model/count, the four environment variables
(`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `PYTHONHASHSEED`), the git head, the clean-tree flag and per-file `src/` hashes. A
range such as `torch>=2.2` is not a pin. The future executor must not be run until this lock exists; creating the lock is a post-executor step.

## 4. Bounded GPU resource-probe plan (specification only; not run, not implemented)

Built on [`b2_e8_gpu_probe_spec.json`](../plan/b2_e8_gpu_probe_spec.json) (caps in section 2 are the spec's, unchanged). It needs, before it may run:
(1) a separate researcher message naming the host and GPU and the caps, (2) an independently reviewed probe executor (none exists; the isolated modes are
CPU-only), (3) a verified clean lock, (4) a pre-registered parity tolerance.

**Roles and data.** Train and val-select only, through the synthetic layout fixture (random float16 arrays of the stored shapes, seeded) and, for the
end-to-end part, at most 2 groups per role of a verified B2-feat/1 artifact via the E1 streaming loader. Never val-calib, test, B2-test/1 or B2-match/1.

**Smallest sufficient configuration set (proposal).** The spec lists five. R5 fixed batch 32, so the batch-8 entry is not needed. Minimum:

| Config | Why |
|---|---|
| `w16_b32_dual_residual_tf32off` | the candidate; the heaviest view, so an upper bound on per-fit cost |
| `w16_b32_co_tf32off` | the lightest view, to bound the range across the three views |
| `w8_b32_dual_residual_tf32off` | anchors the old width-8 assumption (200 - 1,000 samples/s) so the extrapolation can be judged |
| `w16_b32_dual_residual_tf32on` (optional) | price of the torch default; informational, since TF32-off is approved; it cannot change R6 without a new researcher decision |

Four configurations at <= 300 s each fit inside the 1,800 s total. **Two parts (proposal):** part A, synthetic and data-free, can run on the final
lock before generation to answer "is this GPU adequate and what is the pure-compute rate"; part B, real-layout loader, runs after generation has produced a
verified train/val-select artifact.

**Gaps in the current spec that should be fixed before an authorization is requested (E11-B findings; no spec file is edited here):**

| ID | Gap | Why it matters |
|---|---|---|
| G-1 | no forward-only rate for the val-select pass | 324,000 forward passes and the freeze/evaluation inference are unbudgeted |
| G-2 | the timed loop is not stated to enable the K17b 15 % plan shift or the plan head | omitting them under-measures the preprocessing and loss path of the approved recipe |
| G-3 | a 2-group real-layout read is cached by the OS page cache and says nothing about reading 4.7 GB per epoch | the loader (about 7 h of the 10 - 22 h band) would be mis-measured |
| G-4 | no record of GPU clocks/thermal state or competing processes | throughput on shared or throttled devices is not reproducible |
| G-5 | no pre-registered parity tolerance | "report differences, assert nothing" allows a post-hoc reading; fix a tolerance first (decision P-1) |

**Pre-registered use of results (spec, restated).** Hours for a campaign = passes / measured end-to-end rate; the report states the arithmetic for
nine fits (3,240,000 passes); no ceiling is derived from a single run; the margin is stated, not applied silently; results never change width, epochs,
batch, loss or any fitted choice except through an explicit, versioned researcher decision before the first production fit.

**Training ceiling formula (to be filled with probe numbers):**

```
T9_hours      = ( 3,240,000 / r_train  +  324,000 / r_val ) / 3600        # r_* = measured end-to-end samples/s incl. loader
fit_hours     = T9_hours / 9
ceiling_hours = 1.25 x T9_hours  +  k x fit_hours                          # k = restarts the researcher chooses to cover
```

The probe measures `r_train` per view; use the slowest view or per-view sums, not the average. `r_val` needs gap G-1 closed. Calibration, scorer fitting,
freeze and the single evaluation are added from the forward-only rate once measured.

## 5. Approval message templates (blanks to be filled by the researcher; nothing is pre-filled)

> **[G] Generation authorization.** I authorize `full_generation` (21,350 observations) on host `<id>` at head `<hash>` with lock `<fingerprint>`, reviewed
> in `<path>`, with ceilings wall `<h>`, core-h `<h>`, free disk `<GiB>`, backup `<GB>` on `<device>`, RSS `<GiB>`, expiry `<date>`. D-1 decision: `<A/B/C, record>`.
> This does not authorize any probe, training, freeze or evaluation. Signed `<name>`, `<date>`, record `<path>`.

> **[P] Probe authorization.** I authorize the bounded GPU probe of `b2_e8_gpu_probe_spec.json` (configurations `<list>`) on host `<id>`, GPU `<model>`,
> at head `<hash>`, with the spec caps (or tighter: `<values>`), parity tolerance `<value>` pre-registered, roles train and val-select only, expiry `<date>`.
> It authorizes no fit, no checkpoint retention and no change to any protocol value.

> **[T] Training authorization.** I authorize `full_gpu_training` of the nine approved fits on host `<id>`, GPU `<model>`, at head `<hash>`, lock `<fp>`,
> data manifest `<hash>`, with ceiling `<GPU-h>` derived from probe report `<path>` using the stated formula and margin, restarts covered `<k>`, expiry `<date>`.
> It does not authorize calibration use of test data, freezing, evaluation or LOKO.

> **[F] Freeze.** Proposed as its own written record: all nine fits `COMPLETE`; I accept calibration and freeze on val-calib only, manifest `<hash>`.

> **[E] Evaluation.** Proposed as its own written record, issued after the freeze manifest exists: one read-only evaluation of the frozen nine cells over
> the held-out roles, D-1 exposure statement attached, primary endpoint `<D-4>`, output directory `<fresh path>`. A repeat is a new authorization.

## 6. Decisions requested from the researcher

| ID | Decision | Default if undecided |
|---|---|---|
| R-A | Decide E10 D-1 (held-out exposure) before any test-role generation | test-role stages stay NO-GO |
| R-B | Choose host layout: separate G and T hosts, or one combined host | none; no host is designated |
| R-C | Backup size (12 GB proposed, 9 GB floor) and the second device | 9 GB floor, which leaves about 3 % margin |
| R-D | Pre-register the GPU-vs-CPU parity tolerance (P-1/G-5) | probe stays NO-GO |
| R-E | Accept the probe spec gaps G-1 to G-4 as required changes to the (future) probe executor | probe stays NO-GO |
| R-F | Whether freeze and evaluation get written authorizations of their own (proposed yes; no gate exists for them) | not runnable in any case: no executor |
| R-G | Margin (25 % proposed) and the number of restarts `k` covered by the training ceiling | no training ceiling can be written |
| R-H | Whether to correct the stale `main_training_gpu_hours: 6` constant and the "1.9x" wording in the approved record (changes to existing files; not done here) | left as is, labelled in this document |

## 7. Safety risks (as assessed from the record; not measured)

1. **Stale 6 GPU-h figure.** It is still a code constant and appears in reservation tables; if read as a ceiling it under-budgets the approved width-16 recipe by 1.7 - 3.7x.
2. **Throughput band is an assumption.** The compute part of every training figure spans a factor of five; the loader part rests on a different CPU. A budget based on either can be missed in both directions.
3. **Disk preflight vs supervisor.** The two checks encode different "25 GiB" meanings (about 34 GiB free needed to start). A host sized to the weaker check fails the stronger one at launch.
4. **TF32 default.** Without a runtime read-back, a run on Ampere or newer would silently use cuDNN TF32 (torch default), contradicting the approved profile.
5. **Source drift.** Any `src/` edit after the lock invalidates the lock and every earlier checkpoint; the executor milestone must complete first.
6. **Held-out exposure.** Test and matched groups already have published pilot outcomes (D-1). Generating or reading them without a decision hardens an unresolved contamination question.
7. **Legacy path.** `--mode legacy` still opens and evaluates test before freeze (audit M-10); the production chain must never route through it.
8. **Unbudgeted stages.** Freeze and evaluation compute, restarts and the val-select pass are in no current total.
9. **Single copy risk.** Generation is 23 - 30 h of CPU time; without the second-device backup made before the data is frozen read-only, a disk fault repeats the whole stage.
10. **Self-asserted records.** Hashes, approvals and reviews inside JSON records detect accident, not forgery; the control is the merge review and the researcher's own record.
