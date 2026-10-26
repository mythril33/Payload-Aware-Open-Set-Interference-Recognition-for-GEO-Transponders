# B2 E18 — stage-boundary checklist

Version 1, 2026-10-25. **Engineering checklist for the synthetic lifecycle — DR-04 NO-GO — NO COMPUTE AUTHORIZED.** Passing every
item below is evidence about *documents and fabricated bytes*; it is not permission to run anything. The "Automated" column says what
`SyntheticExecutorLifecycle` already checks at the boundary; the "Human / external" column lists what no code in this repository can
supply today.

Boundaries: `pre_launch` (before `known`), `after_known` (before and after `test`), `after_test` (before and after `matched`),
`after_matched`. The lifecycle evaluates one E16 boundary report before a stage starts and one when it completes.

| # | Boundary item | Automated check (E16 condition id) | Human / external dependency (absent) |
|---|---|---|---|
| 1 | Trusted evidence is fresh: signature of the exact committed record, Git lineage reviewed R → approval A, scoped DR-04 block, signed revocation `ACTIVE` for this grant, signed exact-head CI, one-time challenge; a stage may start only within 300 s **and** before the signed answers' own expiry | E17 evaluation before each stage start and end; `authorization.policy`, `authorization.scope` | real signer/issuer keys, `PINNED_TRUST_ROOT`, credentialed CI evidence, durable replay custodian |
| 2 | Source, configuration, environment, lock identity equals the sealed plan; no untracked importable file | `identity.source_config_environment`, `plan.dr04`; E17 clean-checkout verification; source recheck every 64 shards | clean production lock on the approval commit, designated host |
| 3 | Approval has not expired and is not revoked | `authorization.unexpired`, `authorization.not_revoked`, `runtime.stop_conditions` | a genuine DR-04 record with run-bound expiry |
| 4 | Frozen inventory and sealed specification | `inventory.frozen`, `spec.sealed`, `sequence.stages` | — |
| 5 | D-1 non-pristine disclosure (498/148 rows) and D-8 K17d identity (500/co35/cross43/total78/complement465) preserved | `reporting.d1_d8`; from `after_known`: `k17d.metadata` + a journaled `k17d_check` with the same identity | the **production** K17d metadata cross-check (fabricated here; summaries say `NOT_RUN`) |
| 6 | Predecessor stages complete; **no data exists for any later stage** (also re-checked when a stopped run is resumed) | `durability.<stage>` (stage-order data → STOPPED) | — |
| 7 | Every planned shard committed: descriptor, payload and metadata hash-verified, durably admitted, read-only, unaliased, no orphan | `durability.<stage>` (deep classification `COMPLETE`, admissions, manifest, immutability) | behaviour of the real storage; `media_verified` is always false |
| 8 | Role isolation: stage roots and role directories are distinct; train/val-select/val-calib read only their own known roles; test and matched roles never reach training, selection or calibration | `isolation.roles`, `isolation.consumers` | an enforcing runtime for real consumers (none exist yet) |
| 9 | Later request identity is bound to the completed predecessor artifacts, not to a fixture, and does not alias another stage | journal `stage_bound` derived from predecessor manifests; alias check | — |
| 10 | Backup: byte-verified restore of every role; working and backup devices distinct, durable filesystems, enough capacity | `backup.<stage>` (restore re-verification; device validation over **fabricated** device records) | independent persistent backup, capacity/retention choice, restore drill |
| 11 | External journal: hash chain, independent anchor, ordered stage entries bound to the working-tree manifests, no unresolved interruption or halting incident | `journal.external` | independent append-only sink and anchor custody on a different failure domain |
| 12 | Resources within ceilings and projections (wall, core, RSS, disk, backup space, attempts, interruptions, first-shard timing) | `runtime.stop_conditions` + per-shard evaluation, counters journaled | a real CPU-only observer on the designated host and approved ceilings |
| 13 | Execution boundary | `execution.boundary` — **permanently BLOCKED** | a separate, reviewed launch decision and executor (not part of E18) |

## Disposition if an item fails

STOPPED (final): stage order, K17d, role isolation, resource/timing/authorization stop conditions, identity or journal faults.
QUARANTINED (final, evidence frozen): integrity of shard state or backup. BLOCKED (retry): missing or unproven facts.
STOPPED by `interrupt()`, a producer failure, an unreachable revocation source or an observer clock skew during a run are the only resumable stops. See the
[failure and recovery runbook](B2_E18_FAILURE_RECOVERY_RUNBOOK.md).

## Actual execution blockers and release decisions — 2026-10-26

This audit follows merged PR47, main `b9728526008044bc23fab0d7458c030af65c34d0`.
It does not reopen completed C2 controls or approve computation. **Required budget:
15 fits = canonical nine + H3-dual six. Optional H3-co six are deferred before
any held-out read.** No scientific approval object or frozen scenario identity changes.

### Real CI regression

Exact-head readiness run40316846687/job121551472832 on `d99bb92` failed:
E4 107 passed/137.10s; remainder 7 failed,4629 passed,7 skipped,46 warnings/1953.27s.
All seven failures were global E18 workflow-lint compatibility failures: valid
`contents: read` at the end of the header was not recognized without an extra
newline, and the paper-only fixed APT dependency installation was rejected.
The seven skips are the existing machine/torch capture mismatch at
`test_b2_train_diagnostics.py:392`; warnings are existing Matplotlib notices.
This was not a demonstrated C2 numerical regression. The focused repair keeps
scientific command bans and canonical gates, accepting only the two exact
reviewed document-package commands in the named manuscript workflow. Final-head
checks and review are recorded in the repair PR; historical CI is not reused as
proof of that head.

### Full execution is structurally absent, not merely unauthorized

| Required capability | Actual executable code / missing integration |
|---|---|
| Full supervised generation | `scripts/b2_production_supervisor.py`: `PRODUCTION_LAUNCH_ENABLED=False`, `assert_bounded`, `stage_argv`, and production branch of `main` refuse full execution. Raw generator CLIs can generate full data but invoking them directly would evade the required supervisor and is not a release path |
| Release admission | E9 `guard_execution`, E14 `deny_execution` and E18 `production_gate` always refuse. E16 valid-record state explicitly is not execution permission; E17 real trust root is unconfigured |
| Actual lifecycle ports | E18 implements fabricated-byte producers/attestors only. Real host/resource observer, external journal/replay custody, generation metadata attestation, independent backup/restore and supervised process ownership are not connected |
| Full training artifact and device support | `geoml.b2_execution`: CAPS2groups/role,2epochs,width8,batch32; `_cpu` and fit/load calls force CPU, markers require `BOUNDED_FIXTURE`. Raising only CAPS would mislabel artifacts. `b2_stream.fit_streaming` has a generic device kernel but not a qualified production GPU runner or enforced R6 TF32/environment record |
| Pre-test freeze | Existing nine-cell and H3-dual six-cell inventories bind model/scorer/calibrator/data/source/runtime. Primary scorer and ordered cross-profile final evaluation are not bound into that freeze; post-evaluation `contrasts --primary-scorer` is not a substitute |

No row above is marked implemented by this CI repair. The requested *complete*
production integration remains **NOT DELIVERED**; asserting that an approval
alone makes the existing commands runnable would be false. Preserve historical
fixture guards; a separately reviewed production-scope release/artifact adapter
must reuse the validators and numerical kernels, capture actual device/TF32
identity, and bind both inventories/scorer/evaluation order. Do not copy models
or add another parallel safety framework. Existing source-changing checkpoints
must be rejected, not relabelled.

Prefer supervision of existing stage CLIs plus the E16 external
validate→fsync→revalidate admission barrier before journal acceptance. This can
preserve the accepted28-module geosim identity. A writer callback inside geosim
would instead change that identity and require D-8 metadata-only rederivation,
review and explicit reacceptance. Descriptor-last publication alone is not durable
acceptance. This is the precise remaining code boundary, not an implied runtime
cap exception.

### Non-invasive current host inventory

Measured26 October2026 on the attached workspace (not an independently observed separate Claude Code machine), without GPU library/device calls: affinity3logicalCPUs,
but cgroup CPU quota2CPU-equivalents; cgroup RAM limit8GiB (host-reported9.73GiB
is not the usable entitlement). Working overlay31.45GiB total/16.24GiB free at
inspection. No `/dev/nvidia*` or `/dev/dri` device was exposed. No GPU probe was
run. Session lifetime and cross-session persistence have no verified guarantee;
there is no verified independent backup device. This is not a qualified DR-04
host and falls below the existing25GiB free-working-reserve proposal. Those
proposals are not approvals.

### Two practical hosting routes and cost uncertainty

Official pages checked26 October2026; listed prices are not a reservation or
proof of regional capacity. No account, purchase or resource provisioning occurred.

| Option | Verified published offering | Proposed use / estimated cost |
|---|---|---|
| Hetzner CCX23 CPU | 4dedicatedAMDvCPU/16GB/160GBNVMe, EUR0.1386/h excludingVAT; [official dedicated page](https://www.hetzner.com/cloud/general-purpose/) | Recommended generation host, fixed two BLAS threads initially. At36h proposed ceiling aboutEUR4.99 compute; actual performance unmeasured |
| Hetzner CX43 CPU | 8sharedvCPU/16GB/160GB, EUR0.0264/h excludingVAT; [official page](https://www.hetzner.com/cloud/cost-optimized/) | AboutEUR0.95/36h, cheaper but shared-CPU timing uncertain |
| RunPod Secure RTX4090 | USD0.89/GPU-h; Community listedUSD0.34/h; [official pricing](https://www.runpod.io/pricing) | Prefer Secure if selected. Fifteen-fit rough scaling of old nine-fit9.95–21.87h gives16.58–36.45GPU-h, aboutUSD14.76–32.44 GPU-only. Not a GPU measurement or budget guarantee; matched arms and I/O differ |
| Persistent storage and independent backup | RunPod network volumesUSD0.07/GB-month; [storage docs](https://docs.runpod.io/storage/network-volumes). Hetzner object-storage baseEUR6.49/month excludingVAT; [official FAQ](https://docs.hetzner.com/storage/object-storage/faq/general/) | Example100GBnetworkvolumeUSD7/month plus separate off-host backup. A network volume or S3 bucket is not automatically an independent device compatible with current local-device attestation; verify IDs, custody, checksums and restore before approval |

Minimum proposed allocation: CPU16GiB RAM, persistent80GB or larger working
storage with at least25GiB free reserve, and independently identified durable
backup; training one24GBGPU,16GiB system RAM or more and persistent artifacts.
These are conservative proposals, not measured minima. Full-generation historical
wall estimate22.5–29.7h/~26–35core-h and~8.7GB artifact estimate remain
extrapolations. Budget USD50–100-equivalent initially for compute/storage/transfer
contingency, not a price quote; taxes, IPv4, retained volumes, egress, retries,
capacity and actual qualification can increase it. No guarantee of15-fit success
is implied by multiplying a nine-fit band.

Practical setup after explicit spend approval: researcher creates private CPU
host and GPU account/region, persistent work volume and independent backup;
restricted SSH access, TLS/private-bucket transfer, pinned environment/source;
copy only verified manifests/shards with checksums, restore-check them, then
review host/storage identity and ceilings. Credentials stay outside Git. Do not
use this ephemeral workspace as the sole artifact copy.

### Single researcher decision/resource list and fixed sequence

1. Name the CPU host, GPU provider/region, work/backup/journal custodians and an
   explicit spend/retention ceiling. Approve no purchase by inference.
2. Explicitly decide the primary scorer. Recommended wording (not yet approved):
   **“For B2-C2/D-4, Mahalanobis is primary on design grounds; MSP and Energy
   remain secondary and all are reported. Required fits are15; optional co
   controls are deferred. Final evaluation order is canonical then H3-dual,
   followed by offline paired contrasts. This precedes protected evaluation.”**
   Rationale is the approved center-loss/embedding geometry, not pilot/test scores.
3. Accept/review the exact production-scope adapter changes above, with source,
   configuration/environment identity and no stale checkpoint reuse. If geosim
   changes, obtain D-8 reacceptance before lock/authorization. No existing
   approval authorizes widening fixture caps.
4. Supply the real signer/trust-root and independent revocation/CI authority,
   designated host/backup/journal evidence and resource ceilings required by the
   existing E13–E18 release contracts. Then separately sign DR-04 generation
   scope and final launch decision against the reviewed code/lock.
5. After authorized generation in known→test-only→matched order and metadata-only
   integrity/D-8 cross-check, separately authorize GPU qualification and DR-05
   training for15fits. Fit/select on train/val-select only; calibrate known-only
   val-calib; freeze9+6cells plus scorer and evaluation order before any test read.
6. Separately authorize final held-out evaluation, preserving D-1 exposure and
   exclusion reporting; evaluate canonical then H3-dual once as declared, and
   compute paired contrasts offline. DR-04 does not authorize these later steps.

**First production command: NOT AUTHORIZED AND NOT IMPLEMENTED in this build.**
There is no honest launch command that becomes usable just by supplying DR-04.
The existing non-launching diagnostic command is:

```sh
python scripts/b2_production_supervisor.py plan --production --workdir /chosen/persistent/run
```

It returns a plan/NO-GO, not data. The launch-shaped `run --production --execute`
continues to refuse. Do not invoke unsupervised raw full-generator commands as
a workaround. Actual launch syntax must be supplied by the reviewed adapter,
not fabricated in advance. All canonical compute gates remain closed,
`PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`. No generation,
training, GPU workload/probe, paid resource or protected observation was used.

CI bootstrap limitation: the E18 workflow reads its lint policy from the PR base. Until this reviewed parser repair is present on main, that step can still reject the already-merged document workflows even though the candidate policy passes all136focused tests. Do not bypass the base-policy guard or claim that candidate lint is exact-head full CI success. Final run outcomes belong in the repair PR.

## Real execution adapter handoff — 2026-10-26

The preceding missing-code inventory describes PR48, not this adapter. No new milestone or approval is created. `scripts/b2_real_generation.py` connects the existing stage commands to E16 admission/journal/backup and E17 authorization; `geoml.b2_production_training` uses the existing streaming kernels with separate production markers and R6 device identity. The old fixture launchers/caps remain unchanged. The external production host, pinned signer/revocation/CI authority and independent storage/journal custody are still required; injectable evidence is not proof of those facts. Production evaluation inference is not implemented by this change; the campaign module binds the fifteen fits, primary-scorer designation and once-only order for a future separately authorized reader.

The real-code development command is (activate the environment first):

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=''
PYTHONPATH=src python scripts/b2_real_execution.py --out /data/geo-development-exercise --groups 1
```

Use a fresh output outside the repository. This command creates only train/val-select/val-calib (24 observations), fits a width-2 model for two CPU epochs, selects on val-select, calibrates all three scorers on eight known val-calib observations, freezes and byte-verifies local copies. It does not qualify an independent backup, train a production model or authorize protected evaluation. Artifacts remain outside Git. A source change invalidates the old source-bound artifacts.

### Operator setup (DR-04, GPU training, final held-out remain CLOSED)

Hardware to approve before any purchase:
- CPU: existing persistent Linux machine with 4 usable CPU cores, >=16 GiB RAM, >=80 GB durable working disk and >=25 GiB working reserve after planned data. Small suitable named cloud choice: Hetzner CCX23 (4 dedicated vCPU,16 GB,160 GB NVMe); CX43 is cheaper shared-CPU alternative with uncertain timing. These are proposed classes, not measured performance minima.
- Backup: >=20 GiB independently identified persistent block device on the CPU host, ext4/xfs/btrfs/zfs, separate st_dev AND physical storage identity; separate custodian for journal/anchors/replay and a successful restore drill. A second directory, overlay, temporary disk, S3 bucket, or unverified volume name is insufficient. Ask provider/operator to identify independent storage failure domains; retain an off-host copy too. The current local E14 contract cannot directly attest S3/NFS as its backup device.
- GPU later: one RTX4090/24 GB host (RunPod Secure-class is a suitable example), >=16 GiB system RAM, >=80 GB persistent artifacts/working volume. GPU qualification needs a separate authorization before probing CUDA; DR-05 training is another authorization. No GPU was exercised here.
- Obtain a written maximum spend, region, retention/deletion policy and named host/storage/journal custodians. Existing published estimates in B2_E18_STAGE_BOUNDARY_CHECKLIST.md are illustrative, not purchase quotes. Do not provision anything from this handoff until paid resources are explicitly approved.

For an operator unfamiliar with Linux:
1. Have the approved host owner create an Ubuntu24.04 or comparable supported Linux host, a private SSH key login, and the backup device already formatted and mounted. Do not run mkfs on an unfamiliar disk. Have them give you CPU_HOST, your login, /data/geo-work and /mnt/geo-backup and identify which device backs each path. Keep private keys outside this repository.
2. Open Terminal (macOS/Linux) or PowerShell (Windows). Connect using the provider's displayed command, for example:
   ssh YOUR_LOGIN@CPU_HOST
   Each later command runs in that remote terminal, not on your laptop. Do not paste YOUR_LOGIN or CPU_HOST literally.
3. After host/spend approval, install basic tools on that host:
   sudo apt-get update
   sudo apt-get install -y git python3-venv python3-pip tmux rsync
   These commands install software; they do not generate research data.
4. Ask the host owner to create the approved empty roots, owned by your login. Then check mounts:
   findmnt -T /data/geo-work
   findmnt -T /mnt/geo-backup
   df -h /data/geo-work /mnt/geo-backup
   lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,SERIAL
   Stop if either root is missing/overlay/tmpfs or both use the same device. Save provider storage IDs separately; SERIAL output alone does not prove independent physical custody.
5. Fetch reviewed code (replace REVIEWED_COMMIT with the exact independently reviewed commit from the PR, after researcher acceptance):
   mkdir -p ~/research
   cd ~/research
   git clone https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders.git geo
   cd geo
   git checkout --detach REVIEWED_COMMIT
   python3 -m venv ~/geo-venv
   . ~/geo-venv/bin/activate
   python -m pip install -e '.[dev,ml]'
   python -m pip freeze > /data/geo-work/python-packages.txt
   git rev-parse HEAD > /data/geo-work/source-commit.txt
   Package resolution is not an approved environment pin. The final plan must lock this exact resolved environment and source identity before any authorized production launch.
6. Set CPU/thread environment for this terminal (repeat after each reconnect):
   export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=''
   Read-only closed-gate diagnostics:
   python scripts/b2_e16_policy.py ci-gate
   python scripts/b2_e18_ci_policy.py gate-decision
   python scripts/b2_e13_generation_plan.py template --out /data/geo-work/generation-plan-template.json
   Expected NO-GO/closed gates are correct. The template is incomplete, not an approval.
7. Obtain real source-bound signed DR-04 authorization, trusted signer, independent fresh revocation/CI authority, designated host/storage evidence and immutable external journal/anchor/replay custody. The researcher/operator must fill and review the plan against actual host evidence; do not manufacture signatures, change canonical gate JSON or use fabricated fixture custody. Validate the approved plan with the reviewed adapter's prescribed evidence; generation remains closed until it passes every existing contract.
8. The first data-producing action after host qualification and separate DR-04 launch approval is the supervised existing known-data generation stage. Use only the reviewed production adapter command delivered by the PR. Do not directly invoke an unbounded geosim CLI. Keep known -> test-only -> matched ordering, byte/durability admission, ceilings and backups. No training approval is implied.
9. After authorized generation/metadata integrity, separately approve GPU qualification and DR-05 for 15 fits: canonical nine plus matched dual no-plan six; train/val-select only, known val-calib, freeze. Before held-out access, the researcher must select the primary scorer and bind evaluation order (canonical then H3-dual then offline contrasts). Mahalanobis is a recommendation only. Final held-out requires another explicit authorization; never use the protected set for setup.

Use tmux only after the actual launch has been separately authorized: tmux new -s geo, run the approved command; detach Ctrl-b then d; reconnect with tmux attach -t geo. The supervisor's durable journal/recovery contract, not tmux, determines whether work can resume.

Actual bounded evidence: two development groups per role (48 RF observations), generator153.007s wall/153.434CPU-s/570472KiB observed peak RSS; two CPU epochs, val-select selected epoch1; three rejection calibrators used16 known calibration observations and clean alarm used2 clean observations. Validation macro-F1 was0.0227 then0.0278: this is an execution check, not useful recognition evidence. Data and model copies, freeze checksum and anchored journal were reverified; current scientific source-file hashes match the exercise. No test directory existed. No independent-device, media-survival, GPU or full-production claim. Tests/independent-review/remote-CI results are recorded in the single delivery PR, not inferred from this exercise.
