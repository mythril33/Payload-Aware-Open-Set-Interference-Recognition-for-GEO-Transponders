# B2 E16 — production integration architecture and DR-04 release policy

2026-10-25. Engineering only. **E16 PRE-AUTHORIZATION INTEGRATION — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No production observation was generated, no model trained, no GPU discovered or probed, no held-out
observation read. `PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`, `full_generation`,
`full_gpu_training`, `full_loko_sweep`, GPU probe and held-out final evaluation are all `NOT_AUTHORIZED`.
The E9 runtime refusal, the supervisor's two-group fixture cap and the E14 `deny_execution` are unchanged.

Verified base: `origin/main` = `09dd104acdde119f5b38098775dc8ee7c9d2e42a` (PR #39 merged; E15 exact-head CI
succeeded). The branch `feature/b2-e16-production-integration` started from it; no earlier E16 work, branch,
stash or staged file existed.

## 1. What E16 is

E13 (plan validator), E14 (sealed specification, synthetic storage, metadata verifier) and E15 (operational
dossier) each proved one control in isolation. E16 joins them into a single **data-only, fail-closed** architecture
that can be tested end to end with synthetic metadata and fake read-only adapters, and that **cannot** start
generation: every report ends in `NO-GO`, `execution_permitted=false`.

| Module (all under `scripts/`, no import of a process API, no environment read) | Role |
|---|---|
| `b2_e16_durability.py` | External durable-admission barrier, directory classification, evidence-preserving quarantine note, checksummed backup manifest, restore re-verification, immutability findings, generator-identity impact |
| `b2_e16_ledger.py` | Hash-chained external run ledger (verify/append), incident specification, pure stop-condition evaluator over injected resource readings |
| `b2_e16_policy.py` | Scoped DR-04 operational-authorization policy: gate classification, committed-record validation, release-order check, CI-facing gate check |
| `b2_e16_integration.py` | The release-boundary report that joins E13/E14 and the three modules above over injected evidence |

New tests: `tests/test_b2_e16_{durability,ledger,policy,integration,safety}.py`. New scoped workflow:
`.github/workflows/b2-e16-integration-ci.yml`. No existing source, configuration, workflow, gate, memorandum or
scientific record is edited (section 9).

## 2. Phase 1 — control-by-control integration gap matrix

Columns: **(1)** functionality that is real and verified today; **(2)** contract that exists only as documentation;
**(3)** synthetic reference only; **(4)** missing production integration; **(5)** scientific-provenance risk;
**(6)** the exact negative tests required; **(7)** implementable without enabling production?; **E16** what was done.

| # | Control | (1) Verified today | (2) Doc only | (3) Synthetic reference | (4) Missing integration | (5) Provenance risk | (6) Negative tests | (7) | E16 disposition |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Frozen inventory and stage sequencing | `derive_inventory` (21,350 obs / 739 shards / 2,450 groups); E14 sealed chain None→known→test (matched needs test); supervisor `_prior_stages_intact` | P18–P22 counts | — | Nothing compares a *real* stage tree with the plan at a boundary; deferred test/matched request fingerprints are not bound anywhere external | Late or changed deferred binding = different request identity | later-stage data before predecessor; aliased request; unplanned/missing shard | yes | `sequence.stages`, `durability.<stage>`, journal `stage_bound`; stage-order tests |
| 2 | Source / config / environment identity, lock | E13 source/environment/lock checks; preflight `build_lock/verify_lock` | E15 release sequence | — | Not re-checked at stage boundaries; evidence freshness unmodelled | Any script edit changes `tools_sha256` and voids an approved digest (intended) | head/clean/file/config/tool/environment mismatch; stale lock | yes | `identity.source_config_environment` (E13 report), `evidence.fresh` |
| 3 | DR-04 plan validation | E13 `validate_plan` (35 PASS / 0 FAIL / 9 BLOCKED on a template) | E13 checklist | — | Only run on demand | — | each E13 check | yes | `plan.dr04` reuses E13; no duplicate validator |
| 4 | Sealed launch specification | E14 `build_specification/admit` | E14 ADR | — | Never compared with boundary evidence | — | modified spec/hash/runtime policy | yes | `spec.sealed` |
| 5 | DR-04 authorization record and gate | E13 `_check_authorization`: record/digest/ceilings/scope/gate/supervisor view | E15 dossier | fabricated approved fixtures in E13 tests | No signer authentication, no revocation, no reviewed-commit binding, **hash-order circularity**, CI cannot express an approved gate | Approving must not alter scientific approvals | forged/partial/stale/contradictory/other-scope records | yes | `b2_e16_policy` (section 5) |
| 6 | Release ordering and hash-order | — | E15 sequence | — | No machine check of order or cross-binding | Omitting a hash to break a cycle would weaken identity | skipped/swapped step, digest drift, lock on wrong commit, recorded launch | yes | `check_release_order` |
| 7 | Durable shard commit | Generator: temp → replace → descriptor last; resume re-verifies hashes | E14 ADR | E14 writer (≤64 KiB, groups 0/1) | Generators never fsync; the E14 writer is not wired | Editing `src/geosim` changes the accepted package digest `01c4f26…` and generator provenance | corruption, truncation, descriptor older than data, symlink/hardlink/FIFO, post-sync change | yes (external) | `admit_shard` barrier (section 6); `source_identity_impact` |
| 8 | Orphans, partial commits, quarantine | Supervisor `quarantine_orphans`; generator refuses an unverified partial shard | E14 procedure | E14 synthetic quarantine | Classification against the plan; evidence note outside the data tree | Silent regeneration after an identity mismatch | temp orphan, payload+meta without descriptor, unplanned ordinal, stray entry, identity-mismatch resume | yes | `classify_directory`, `write_quarantine_note` |
| 9 | Backup verification, independent persistent device | E14 `validate_backup_devices`; preflight transfer manifest | E14/E15 procedures | — | No per-stage binding of the copy to the admitted bytes or to the planned device/host | `st_dev` ≠ physical independence | same device, volatile root/fs, wrong host/root, capacity, stale or differing measurement | yes | `build_manifest`, `backup.<stage>`; cross-check against the measured host inventory |
| 10 | Restore re-verification | — | E14 procedure | E14 synthetic restore | Real-byte manifest compare | A good restore ≠ DR qualification | extra/missing/changed file, tampered manifest, claimed qualification | yes | `verify_restore` (`disaster_recovery_qualified` always False) |
| 11 | External append-only journal | Supervisor journal: fsynced, hash-chained, **inside the workdir** | E14 requirement | — | Location outside the work tree, anchor, stage entries bound to evidence | A journal on the failing device is no journal | edit, reorder, gap, truncation (anchor), torn write, backwards time, halting incident | yes | `Ledger`, `verify_chain`, `check_independent_location`, `journal.external` |
| 12 | Resource ceilings, restart allowance, first-shard timing | Supervisor ceilings and `TimingGate` in fixture runs | E13/E14 stop rules | — | No pure evaluator usable at every boundary with injected readings and a remaining-budget projection | — | each ceiling at its boundary, projection, restart allowance, missing/NaN/stale reading | yes | `evaluate_stop_conditions`; `runtime.stop_conditions` |
| 13 | Approval expiry and revocation | E13: ≤30-day validity at validation time | E15 | — | Not re-evaluated; no revocation | — | expiry at the instant, revoked, no revocation answer | yes | policy (`authorization.unexpired/not_revoked`) + stop evaluator |
| 14 | K17d production-metadata cross-check | E14 `verify_production_metadata` (fabricated fixtures only) | E12 D-8 | fabricated trees | Never run on production metadata; not a boundary condition | Generator edit voids the identity | synthetic report, count/identity/head/request mismatch, observation reads | yes | `k17d.metadata`, mandatory from `after_known`, journal `k17d_check` |
| 15 | D-1 exposure reporting | E13 plan field | E12 D-1 | — | Nothing forces the disclosure into every report | Test role is not pristine | pristine claimed, rows altered, disclosure missing | yes | `mandatory_reporting` in every report; K17d report must restate it |
| 16 | Role isolation, test/matched leakage | E12 legacy test-read refusal; roles in P18 | P18 | — | No directory-aliasing or consumer-input check | Held-out roles reaching train/val/calibration | aliased directories/roots, foreign role dir, held-out in any consumer | yes | `isolation.roles`, `isolation.consumers`, `check_consumer_isolation` |
| 17 | Execution refusal | E9 `guard_execution`, supervisor `stage_argv`, flag False, cap 2, E14 `deny_execution` | — | — | — | — | each guard removed | yes | permanent `execution.boundary` condition; E16 `deny_execution` |
| 18 | CI release-policy conflict | Readiness CI hard-asserts closed gates | E15 sequence | — | A future approved gate would need the CI assertion disabled | Weakening CI would hide forged gates | approved-shaped vs forged/partial gate fixtures | yes (policy now, workflow change later) | `classify_gates`, `ci-gate`; E16 workflow; **readiness CI untouched** |
| 19 | Generator identity binding | E10/E12 package digest and audit | E14 | — | No programmatic "did the generator change?" with required re-acceptance steps | Any `src/geosim` edit | edit, added module | yes | `source_identity_impact`; the branch leaves `src/` byte-identical |

Rows 1–4 and 17 are reused; rows 5–6, 7–16, 18 and 19 gained the E16 modules. **No row is wired to a production
executor** — none exists.

## 3. Architecture

```
frozen inventory ──► E13 plan ──► E14 sealed spec ─────────────┐
 (preflight)        (validate)    (build/admit)                │
                                                               ▼
adapters (injected, read-only)        evaluate_release_boundary(boundary, scope, now)
  shard_state(stage)   ─► classify/admit/manifest evidence ──►  durability.<stage>, isolation.*
  backup_state(stage)  ─► devices + restore re-verification ─►  backup.<stage>
  journal_state()      ─► hash-chained external ledger ──────►  journal.external
  k17d_metadata()      ─► E14 production-metadata report ────►  k17d.metadata
  resource_state(stage)─► observation ─► stop-condition eval ─►  runtime.stop_conditions
  signature/ancestry/revocation ─► E16 policy ───────────────►  authorization.policy / .scope
                                                               ▼
                       permanent BLOCKED  execution.boundary ──► verdict NO-GO, execution_permitted=false
```

Boundaries: `pre_launch`, `after_known`, `after_test`, `after_matched`. At a boundary every earlier stage must be
COMPLETE (deep classification, durable admission per shard, manifest equal to the admitted bytes, read-only files,
restore re-verified on the planned backup device) and every later stage must hold **no data**. From `after_known` the
production K17d comparison is mandatory (it needs only committed known test-role metadata); it is checked before the
`test` stage is admitted. The external journal must carry, in this order: `known` completed → backed up →
`k17d_check` → `test` bound → completed → backed up → `matched` bound → completed → backed up, each bound to the
working-tree manifests.

Adapters are the trust boundary. An adapter that lies defeats the integration; the integration's defence is that
*independent* records (working tree, backup copy, external journal, device measurements, the plan's own host
inventory) must agree with each other and with the sealed plan, so a forgery has to be consistent everywhere.
An unsupplied adapter is a missing fact (`NOT_RUN`), a raising or non-JSON adapter is `FAIL`. Unknown adapter names
are refused, so no adapter named `execute` or `launcher` can exist.

## 4. Structural validity is not authority

* `evaluate_release_boundary` never returns anything but `verdict=NO-GO` and `execution_permitted=false`.
* `execution.boundary` is `BLOCKED` permanently: it re-derives, on every call, that `PRODUCTION_LAUNCH_ENABLED` is
  `False`, the fixture cap is two groups, the E9 guard, E14 `deny_execution` and E16 `deny_execution` raise, and the
  supervisor builds no unbounded production command. If any of them changed it is `FAIL`.
* `document_conditions_met=true` means every *other* applicable condition is `PASS`. It is a statement about
  documents; `execution_conditions_met` is always `false`.

## 5. Phase 5 — release policy (conflict resolution)

**The conflict.** The readiness CI asserts that `full_generation`, `full_gpu_training` and `full_loko_sweep` are
`NOT_AUTHORIZED` with no approval. A genuinely approved DR-04 gate will violate that assertion, and "just disable the
assertion" would also admit a forged gate.

**Resolution implemented now (policy, not a workflow edit).** `b2_e16_policy.classify_gates` separates three states:

| State | Meaning | Accepted by this build's CI check |
|---|---|---|
| `CLOSED_CANONICAL` | the three compute gates exactly closed in the readiness JSON and the memorandum twin; K18/K17d/OBS-CANCEL-2 approved and equal in gate, twin and the ratified protocol (approver, instant, record, choice, 13 decisions); `merge_to_main`, GPU probe and production launch closed | **yes — the only accepted state** |
| `OPEN_CANDIDATE_REQUIRES_RECORD` | `full_generation` alone is open, consistently in gate and twin, with structurally complete provenance; every other compute gate still closed | no — it needs the full record evaluation |
| `DENIED` | anything else (partial, one-sided, other gates opened, scientific approval altered, flags changed) | no |

`python scripts/b2_e16_policy.py ci-gate` exits `0` only for `CLOSED_CANONICAL`, `3` for a candidate and `2`
otherwise. **A gate edit without a full record therefore cannot pass.** The new workflow runs it against the real
files (must be `CLOSED_CANONICAL`) and the tests run it against approved-shaped, forged, partial and contradictory
fixtures. The existing `b2-readiness-ci.yml` is **not edited**; the exact future change is documented in
[B2_E16_RELEASE_POLICY.md](../operations/B2_E16_RELEASE_POLICY.md) and must itself be reviewed and tested against
both fixture families before it is applied.

`evaluate_operational_authorization` classifies a plan + reference + committed record. It reuses every E13
authorization check (basis, record, approver, provenance, binding, ceilings, scope, gate, supervisor view,
isolation) and adds what E13 cannot: the request must be exactly `full_generation` for known/test/matched (every other
compute stage is refused by name); an operational block inside the researcher's committed record restates scope,
approver, expiry, design digest, host, both storage ids, every ceiling, the **reviewed code commit**, a revocation id
and a signature reference; the parsed text must hash to the cited record; an injected verifier must confirm the
signature (exactly `True`); an injected ancestry checker must show the reviewed commit is a strict ancestor of the
plan commit with **only** the gate JSON, its twin and the record changed since; an injected revocation query must be
fresh and negative; the reference must be fresh; the authorization must be unexpired; gate, twin, plan, record block
and protocol must agree. The best outcome is `DR04_GENERATION_RECORD_VALID`, which still reports NO-GO.

**Hash-order resolution (no hash omitted, no guard bypassed).** The cycle is: the gates JSON is hashed into the
lock; the approval lives in the gates JSON; the authorization names the plan commit and lock; the plan commit is the
commit that contains the approval. E13 already breaks the *record* cycle by excluding exactly four things from
`approved_plan_digest`: the commit, the gates/memorandum hashes, the lock and the measured host report. E16 does not
widen that exclusion. It binds what the digest leaves out *afterwards*, in this order, and `check_release_order`
enforces it:

1. `final_reviewed_code` — commit R, after the last executor/tool edit and its review.
2. `design_digest` — `approved_plan_digest` computed on R (it already covers every script hash, the generator
   provenance, the known request fingerprint, configs other than the gates JSON, D-1/D-8, host, roots, ceilings).
3. `researcher_authorization` — the researcher's record states that digest and the **reviewed commit R**.
4. `authorization_commit` — commit A, a *direct child* of R changing only gates JSON, twin and record (verified by
   the ancestry adapter; any code, config, test or workflow path voids the authorization).
5. `final_lock` — created on A (the gates JSON is hashed into it); its fingerprint is bound by the E13 authorization.
6. `revalidation` — E13 + E16 re-run on A with the lock; digest equal to step 2, lock equal to step 5.
7. `launch_decision` — a separate decision that this build cannot record (a recorded launch decision is a failure).

## 6. Phase 3 — generator durability decision

The accepted generators write `part`/`meta` through a temporary name and `replace`, the descriptor last through
`_atomic_json` (`write_text` + `replace`), and never call `fsync` on a file or directory. A power loss can therefore
leave a descriptor that names data which did not reach the device. Hash verification on resume detects that, but
nothing ensures a shard is durable before downstream work counts it.

**Decision.** Do not edit `src/geosim`. Any edit changes the accepted 28-module package digest
`01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b` and the generator provenance fingerprint, which
invalidates the accepted K17d identity record (`docs/results/b2_e10_k17d_identity.json`), every sealed request
fingerprint and every earlier checkpoint's provenance. If such an edit is ever wanted, `source_identity_impact`
returns the required steps: keep the historical records unchanged, metadata-only K17d re-derivation (zero
observation reads and waveform calls), independent review, explicit researcher acceptance, re-hash of every plan and
specification built on the old identity; production stays blocked until then.

**What E16 provides instead.** `admit_shard` runs *after* the generator finished a shard and before anything may rely
on it: verify descriptor, payload and metadata against the sealed identity (role, groups, sample count, request
fingerprint, hashes, descriptor not older than the data); fsync each file; fsync the shard directory and every ancestor;
evict and re-verify identically. Required properties:

| Property | Where |
|---|---|
| descriptor-last | generator order, checked by `descriptor_not_older_than_data`; E14 reference writer for new writers |
| no-clobber commits | generator refuses an unverified partial shard; E14 `_publish` (link + unlink) for E16-written notes |
| hash-verified payloads | `verify_shard`, `classify_directory(deep=True)`, `build_manifest`, `verify_restore` |
| partial-write detection | `PARTIAL`, `CORRUPT`, `TEMPORARY_ORPHAN`, `UNPLANNED` states, unexpected entries |
| evidence-preserving quarantine | `write_quarantine_note` into a separate directory; nothing moved, deleted or repaired |
| identical-request resume | a changed expected identity makes a committed shard `CORRUPT`, never regenerated |
| clean interrupted-work handling | `NEEDS_QUARANTINE` until a human decision; `RESUMABLE` only with no orphan |
| no silent regeneration after mismatch | classification never mutates; the journal records the incident and halts the run |

Limits stated plainly: fsync and a post-eviction re-read are evidence, not proof of what the device holds
(`media_verified` is always `false`); mode bits are accident protection, not WORM (`worm_proven=false`); an admission
snapshot cannot stop a later hostile writer, so the runtime must re-check at every boundary.

## 7. Phase 4 — backup, journal and resource controls

* **Backup**: device records must pass E14 `validate_backup_devices` (disjoint, non-nested roots; different `st_dev`
  and physical id; durable filesystem; measured within the freshness bound; capacity floors from the sealed disk policy)
  *and* equal the E13 measured host inventory the plan was approved with (device number, filesystem type, root, host,
  storage ids). Each role's backup copy must sit on the planned backup device, a different device from the working
  directory, with a restore report whose manifest equals the working-tree manifest and the admitted bytes.
  `disaster_recovery_qualified` must be `false`: a one-off byte check is not qualification.
* **Journal**: location separate from the working filesystem, independent anchor retained elsewhere (without it
  truncation is undetectable and the condition fails), stage entries bound to the working-tree manifests, any
  non-resumable incident halts the run, an interruption must be followed by a resume restating the identical plan and
  specification.
* **Resources**: `evaluate_stop_conditions` checks wall/core/RSS/disk/backup ceilings, failed/interruption/total
  attempts, restart allowance, the first-shard timing gate, and a projection of the remaining budget (unmeasured rate
  uses the upper band edge), plus authorization expiry and revocation, at every stage boundary. Missing, malformed,
  NaN, bool, negative or stale readings are themselves stop reasons. "No stop condition" is explicitly not permission.

## 8. Controls implemented as engineering contracts vs. not wired to any executor

Implemented and tested here (against synthetic metadata, temporary directories and fake adapters): everything in
sections 3–7. **Not connected to production execution, because no executor exists:** the barrier is not invoked by any
generator or supervisor; no real backup copier; no real restore drill; no real external ledger location, anchor
custody or immutable sink; no real signature verifier, ancestry checker (read-only git) or revocation source; no real
resource observer; no real production K17d metadata comparison; no designated host; no approved ceilings; no DR-04
record; no final lock. Wiring them into a future executor is a separately reviewed change (recommended E17 scope).

## 9. Provenance impact

| Item | State |
|---|---|
| `src/` (git tree), `configs/`, `pyproject.toml`, `.github/workflows/b2-readiness-ci.yml`, E15 workflow | byte-identical to base |
| Gates JSON, memorandum twin, scientific protocol, decision register, K17d identity and audit | byte-identical to base |
| 28-module geosim package digest | unchanged (`01c4f26…`), asserted by a test |
| `scripts/*.py` tool hashes | four new files change `tools_sha256` (and therefore `approved_plan_digest`) of any plan made on or after this branch: intended, a plan made before it must be re-derived |
| New hashes | recorded in [B2_E16_VERIFICATION.md](../results/B2_E16_VERIFICATION.md) |

No historical result or checkpoint is relabelled; no scientific parameter changed; no test-informed tuning occurred.
