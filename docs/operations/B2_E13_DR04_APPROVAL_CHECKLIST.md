# B2 E13 — DR-04 (full generation) approval checklist

**Status: PROPOSAL / CHECKLIST ONLY. Nothing here is an authorization, a reservation or an approved ceiling.** Date: 2026-10-24.
Base `origin/main` `943f8c29c00309a7e40f544ea0e57d8bebcc110c`. `benchmark_complete=false`, `PRODUCTION_LAUNCH_ENABLED=False`.
Built on the E11-B analysis ([reconciliation](B2_RESOURCE_BUDGET_RECONCILIATION.md), [pre-run checklist](B2_PRE_RUN_CHECKLIST.md),
[approval requirements](B2_COMPUTE_APPROVAL_REQUIREMENTS.md)) and the E13 [readiness analysis](../plan/B2_E13_GENERATION_READINESS.md).
DR-05 (GPU probe / training), DR-06 (LOKO) and the final held-out evaluation are out of scope and stay `NOT_AUTHORIZED`.

**Current readiness verdict: DR-04 NO-GO.** `python scripts/b2_e13_generation_plan.py status` reports `plan_status=INCOMPLETE_OR_INCONSISTENT`,
`verdict=NO-GO`, `execution_permitted=false`; five external facts are `BLOCKED` (lock, host inventory, backup device, release evidence, DR-04
authorization) and four structural blockers cannot be cleared by any document. Exact numbers are in the [verification](../results/B2_E13_VERIFICATION.md).

## 1. Evidence classes (what each number is)

| Class | Quantity | Value | Source | May it set a ceiling? |
|---|---|---|---|---|
| **Analytic** | observations | 21,350 = 18,400 known + 2,500 test-only + 450 matched; 2,450 distinct groups | `geosim.b2_protocol` constants via `pre.derive_inventory()` | yes (arithmetic) |
| Analytic | shards | 4 groups per shard; loss bound on interruption 32 known / 20 test-only / 12 matched observations | `check_inventory` | yes |
| Analytic | float16 arrays | 395,264 B/observation -> 8.44 GB (7.86 GiB) | array shapes | yes |
| **Historical pilot** | artifact size incl. metadata | about 406,000 B/observation -> 8.67 GB (8.07 GiB) | one measured artifact (`BUDGET["measured_artifact_bytes_per_observation"]`) | anchor only |
| Historical pilot | generation rate | 60-observation matched profile: 262 s wall / 300.2 CPU-s; E7a capped run 4.58 / 5.27 / 4.83 s per observation (known / test-only / matched, start-up included) | E5 plan, E7a verification | anchor only |
| Historical pilot | generator peak RSS | 566 - 582 MiB (E7a children, 2 groups); about 601 MiB (E5 single process) | E5, E7a | anchor only |
| **Extrapolated** | wall time, one process, 2 BLAS threads | 23.1 / 26.6 / 30.1 h at 3.8 / 4.4 / 5.0 s per observation (CID overlays at 8 s); supervisor's flat 5.0 s gives 29.7 h | `pre.wall_hours`, supervisor dry run | **no**: needs the first-shard gate |
| Extrapolated | core-hours | 26.5 / 30.5 / 34.5 core-h at CPU/wall = 300.2/262 | `pre.check_estimates` | no |
| Extrapolated | start-up free disk | `1.1 x 8.07 GiB + 25 GiB` = **33.9 GiB** (supervisor condition, `dry_run_checks`); preflight alone asks 25 GiB | arithmetic on the measured artifact size | binding for launch |
| **Ceiling proposals** (E5; not approved) | wall / core / RSS per process / host RAM | 36 h / 42 core-h / 2 GiB / 8 GiB | `PROPOSED_CEILINGS`, E5 plan | proposals |
| Ceiling proposals | disk reserve / backup | 25 GiB reserve (33.9 GiB free to start); backup 9 GB floor, **12 GB proposed by E11-B** (9 GB leaves about 3 % over 8.7 GB) | E5, E11-B | proposals |
| Ceiling proposals | attempts | at most 2 failed attempts and 20 interruptions per stage, 60 attempts backstop | supervisor constants | proposals (can only be lowered) |
| **Measured host inventory** (this sandbox only; **not** a designated host) | CPU / RAM / disk | 4 vCPU; 14.68 GiB RAM available; 19.84 GiB free on the data device; `host.working_disk` **FAIL** (25 GiB proposed) | `scripts/b2_host_inventory.py --role generation`, 2026-10-24, read-only | no |
| Measured host inventory | backup probe | `/dev/shm` shows "a different device" (tmpfs, volatile): a different `st_dev` is **not** evidence of a backup | same report | no |
| **Remaining approvals** | | DR-04 compute authorization; host and backup designation; ceilings; lock; reviewed launcher and release change | section 3 | — |

## 2. Why a plan is validated, and what that does not mean

`scripts/b2_e13_generation_plan.py validate --plan FILE` compares a researcher/engineer-prepared plan with the checkout and returns findings per
control. A plan can reach `COMPLETE_AND_CONSISTENT`; the verdict is still `NO-GO` and `execution_permitted` is `false` by construction, because the
unbounded launcher does not exist (`stage_argv` refuses), `PRODUCTION_LAUNCH_ENABLED` is `False` and E9 `guard_execution` raises. Green CI, scientific
approval and a consistent plan are evidence; none of them is the DR-04 authorization.

## 3. DR-04 approval checklist

`State` is the state at the base commit. `MET` needs the named evidence; everything else is a NO-GO. E11-B IDs (G-n) are the earlier checklist rows.

| ID | E11-B | Requirement | Evidence | E13 finding / control | State |
|---|---|---|---|---|---|
| D4-01 | G-2 | K18, K17d, OBS-CANCEL-2 approved; `benchmark_complete=false` | `preflight gates` | `authorization.scientific_prerequisites` | **MET** (scientific only) |
| D4-02 | G-3 | D-1 decided (A: test not pristine; 498/148 rows mandatory) and carried into the plan | E12 register | `scientific.d1_exposure`, `obligations.post_generation` | **MET** (decision); carrying it is checked per plan |
| D4-03 | — | D-8: K17d identity accepted (500/35/465, cross 43, total 78); metadata re-derived, zero reads | `scripts/b2_e12_verify_k17d.py` | `scientific.d8_identity`, `scientific.k17d_verification`, `scientific.k17d_bindings` | **MET** (identity); production cross-check **NOT RUN**, mandatory later |
| D4-04 | G-1 | Researcher's DR-04 authorization in `full_generation` and its memorandum twin, bound to plan, commit, lock, host, storage ids; restating the ceilings; grants generation only | gates JSON; `docs/` record with SHA-256 | `authorization.*` | **OPEN** (`NOT_AUTHORIZED`, `approval: null`) |
| D4-05 | G-6 | Designated generation host; measured `b2_host_inventory.py --role generation` report: >= 4 usable CPUs, RAM >= host-RAM ceiling, free disk >= 33.9 GiB (plus any higher reserve) | host report embedded in the plan | `host.inventory`, `host.cpu`, `host.ram`, `host.disk` | **OPEN** (none designated; sandbox fails disk) |
| D4-06 | G-6, G-10 | Independent, durable backup device, different `st_dev` **and** different declared storage id, not nested in the working root, not under `/dev` `/proc` `/sys` `/run` `/tmp` `/var/tmp`, a durable filesystem type (not tmpfs, ramfs, overlay, squashfs), both roots measured themselves, capacity >= backup ceiling | host report (with filesystem types, node name, collection time <= 14 days); operator-declared ids | `backup.device`, `backup.capacity`, `plan.paths_host`, `host.filesystems`, `host.roots_exist`, `host.identity` | **OPEN** |
| D4-07 | G-8 | Explicit ceilings, never above the proposals, never below the estimated need (wall >= 30.1 h, core >= 34.5 core-h, RSS >= 601 MiB, RAM >= 8 GiB, reserve >= 25 GiB, backup >= 9 GB) | plan + authorization | `ceilings.*` | **OPEN** (proposals only) |
| D4-08 | G-5 | Production lock on a clean tree **after** the DR-04 approval is committed (the gates JSON is hashed into the lock); lock fingerprint bound in the plan | `lock-create`, `lock-verify --require-clean` | `lock.document`, `lock.verify`, `source.*` | **OPEN** (no lock) |
| D4-09 | — | Exact pinned python/numpy/scipy and the four environment variables (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `PYTHONHASHSEED`) | plan environment | `environment.pin`, `environment.matches_host` | **OPEN** (per run) |
| D4-10 | G-9 | First-shard timing gate enabled with the E6 band; stop rules fixed (stop on damaged shard, validator refusal, gate failure, ceiling breach; resume only under identical request; never delete evidence) | plan | `timing.first_shard`, `stop_rules.defined` | **MET in the plan template**; gate unvalidated at production size |
| D4-11 | G-4 | Launcher: unbounded command builder, production first-shard gate, release-gate record, independently reviewed | merged release PR + review | structural blockers | **OPEN** (`stage_argv` refuses; flag `False`) |
| D4-12 | G-4 | Independent review and exact-head CI attached to the release head (self-asserted) | plan `release_evidence` | `release.evidence` | **OPEN** |
| D4-13 | G-9 | Known -> test-only -> matched order; later stages bind to the verified known root | supervisor | `plan.stage_order` | **MET** (design, 2-group fixtures) |
| D4-14 | G-11 | Stop conditions and quarantine written; no cleanup that destroys evidence | plan `stop_rules` | `stop_rules.defined` | **MET in the plan template** |
| D4-15 | G-10 | Backup written and checksum-verified before the finished root is made read-only | procedure | `obligations.post_generation` | **OPEN** (procedure, no tooling) |
| D4-16 | — | K17d production-metadata cross-check and exposure disclosure scheduled before any final evaluation | later authorization | `obligations.post_generation` | **OPEN** (later; code not written) |

## 4. Required order (binding; reordering invalidates locks)

1. Researcher designates host, backup device and ceilings; runs the read-only host inventory there.
2. Researcher records the DR-04 authorization in `full_generation` and the memorandum twin, with the `docs/` record, and commits it.
3. Release change (reviewed) for the launcher; independent review; exact-head CI.
4. Create the production lock on the clean release head; **then** fill and validate the plan (`validate`). The lock must follow step 2 because the gates JSON is hashed into it.
5. Only then can a launch be considered by a separate decision; this checklist and the validator cannot make it.

## 5. DR-04 authorization record skeleton (`B2-E13-dr04-authorization-record/1`)

Not pre-filled and not valid as written; every `<...>` is the researcher's. Field semantics are enforced by `validate_plan`. The committed `docs/` record
named in `record` must itself contain the approved-plan digest, the host id, the expiry and the approver's name; the validity window is at most 30 days and
may not start before the E12 register (2026-10-24).

```json
{
  "schema": "B2-E13-dr04-authorization-record/1",
  "kind": "compute_generation", "gate": "full_generation", "stage": "DR-04", "observations": 21350,
  "basis": "researcher_written_compute_authorization",
  "approved_by": "<name>", "approved_at": "<ISO-8601 instant>", "expires_at": "<ISO-8601 instant>",
  "decision": "<text>", "record": "docs/<committed record>.md", "record_sha256": "<sha256 of that file>",
  "plan_fingerprint": "<plan_fingerprint of the validated plan>", "approved_plan_digest": "<approved_plan_digest(plan) the approver read>",
  "git_commit": "<release head>",
  "lock_fingerprint": "<production lock>", "host_id": "<host>", "working_storage_id": "<id>", "backup_storage_id": "<other id>",
  "ceilings": {"wall_hours": "<h>", "core_hours": "<core-h>", "working_disk_gib": "<reserve GiB>", "backup_disk_gb": "<GB>"},
  "grants": ["full_generation"],
  "does_not_grant": ["gpu_probe", "full_gpu_training", "full_loko_sweep", "nine_cell_freeze", "held_out_final_evaluation", "production_launch_flag_change"]
}
```

## 6. Decisions still required from the researcher

| ID | Decision |
|---|---|
| R-1 | Designate the generation host and its measured inventory (4 vCPU, RAM, about 34 GiB free) |
| R-2 | Designate the independent backup device and size (12 GB proposed) |
| R-3 | Approve or change the ceilings (all values above are proposals) |
| R-4 | Issue (or withhold) the DR-04 written authorization; set an expiry |
| R-5 | Commission the reviewed launcher / release change (outside E13) |
| R-6 | Accept that the production K17d cross-check and the 498/148 disclosure bind the later final evaluation |
