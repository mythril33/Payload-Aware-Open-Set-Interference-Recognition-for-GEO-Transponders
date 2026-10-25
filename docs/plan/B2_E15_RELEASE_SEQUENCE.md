# B2 E15 — dependency-ordered DR-04 release sequence

Version 1, 2026-10-25. Base `9e176ad20aa1f355adac06e5a22c77b38a616099`.
**Design only — DR-04 NO-GO — NO COMPUTE AUTHORIZED.** No step below is a
production command, authorization transition, script to run, or automatic launch.

## 1. Required sequence

| Order | Required evidence / action in a future separately approved process | Exit condition and current blocker |
|---|---|---|
| 1 | Researcher designates the intended CPU generation host, working device and persistent independent backup; obtain fresh read-only CPU/RAM/OS/environment/filesystem/capacity facts and operator physical-identity evidence | Qualified measurements tied to the actual host, paths and time; currently NOT MEASURED / BLOCKED. Sandbox/CI cannot stand in |
| 2 | Complete the production executor architecture and durable generator, backup, external journal, timing/resource/expiry admission controls in a separately reviewed engineering milestone | Current E9/E14 are sealed and old runnable paths stay fixture-only; integration and future release/CI policy must be resolved, without production execution or retrospective approvals |
| 3 | Obtain independent review with no open material findings and green CI for the exact resulting source head | E14 evidence does not certify a later execution path; any findings/source changes require renewed review and checks |
| 4 | Freeze the final reviewed code/config/tool/generator/environment design identity | No later launcher/flag/guard edit may be smuggled under this identity; if changed, return to steps 2–4. Complete the required D-8 provenance re-derivation/review/acceptance before this freeze if geosim changed |
| 5 | Finalize the host-bound run plan, declared devices, explicit proposed ceilings, stop/expiry/restart rules and approval-request design digest | Researcher can inspect what is requested; later test/matched request fingerprints remain deferred until known is generated and verified. No final lock yet |
| 6 | Obtain the researcher's separate DR-04 written decision through the reviewed committed-record and matching canonical gate/memorandum process | Scope generation only; approver, timestamp, expiry and host/ceiling/design binding complete; presently NOT AUTHORIZED. A worksheet, PR or CI result cannot grant it |
| 7 | After that approval commit, create and verify the final production lock outside the locked source checkout; bind the final source commit, plan, lock, approval record and current exact-head CI/review evidence | The gates JSON is part of the lock; a pre-approval lock is obsolete. No lock exists now. The future approved-head CI-policy edge below must already be solved |
| 8 | Revalidate the designated host, devices, fresh free capacity, source/config/environment identities, approval validity, lock and remaining resource/restart budgets | Mismatch/expiry/changed source or host means stop, preserve evidence and return to the affected earlier step. Snapshot success alone is not runtime authority |
| 9 | Request a separate release/launch decision after the complete packet is independently reviewed | **Do not execute in E15.** Current code provides no runnable production transition; any future activation must use the reviewed identity-preserving mechanism, not an after-lock flag edit |

There is no currently executable path through this table. The table orders future
evidence and decisions; it does not lift the two-group fixture cap, alter E9's
guard, make E14's data specification runnable or approve full generation.

## 2. Hash and ordering dependencies that existing tooling cannot close

| Dependency | Existing executable fact | Required future resolution; no bypass |
|---|---|---|
| Approval commit → lock | `b2_production_preflight.LOCKED_CONFIGS` includes the canonical gates JSON; `build_lock` binds the git commit and per-file hashes; `verify_lock` refuses drift | Record approval first, then lock on the clean final approval head. Keep the lock/run evidence outside the locked checkout; committing a newly created lock changes HEAD and would require a new lock |
| Design approval → tool changes | E13 `approved_plan_digest` binds source tree, all script tool hashes, generator/known request, parsed configs, roots, host ID and ceilings | A later launch-flag/guard/executor edit changes the approved design. Finish and review the source-side release mechanism before design freeze, or request a new approval after changes; never reuse an earlier approval by updating hashes only |
| Final approval head → green CI | `.github/workflows/b2-readiness-ci.yml` currently asserts canonical `full_generation` and twin are `NOT_AUTHORIZED` with null provenance; a genuine approved DR-04 gate would fail that assertion | A separate reviewed CI operational-authority policy is required before the approval commit can obtain appropriate exact-head evidence. It must validate complete scoped provenance and keep unrelated gates closed; deleting the check, skipping CI or claiming the older green head is forbidden. No CI policy change is made by this dossier |
| Frozen scientific record → separate operational authority | E9 `validate_protocol_record` pins the historical scientific record as non-executable with unresolved operational flags; `authorization_status` separately reads active gates and can describe `APPROVAL_RECORDED_NOT_RUNNABLE` | Preserve the immutable historical scientific snapshot. Do not rewrite its flags to activate compute. A future operational/release policy must distinguish it from a new scoped gate record; the pinned record is not itself an additional prohibition on recording a separate approval |
| Approval digest → final plan/lock/evidence | E13 design digest deliberately excludes commit, gate/memorandum hashes, lock, measured report and CI/review evidence that the approval commit changes; full plan fingerprint and authorization subsequently bind the concrete values | Approve the design digest in the researcher's own record, then hydrate the final concrete bindings under the reviewed policy. The current validator checks document consistency only; it does not authenticate an approver or release a process. Avoid self-referencing committed hashes or pretending all post-approval values existed beforehand |
| Source identity → D-8 | The accepted K17d identity binds all 28 geosim modules, not merely equations; durability edits under `src/geosim/` change that package digest | Metadata-only re-derivation, provenance review and any required explicit acceptance under the new source are prerequisites before reuse. Keep old identity/history intact; no automatic acceptance from equal counts |
| Known artifact → later requests | `b2_test_dataset` and `b2_matched_dataset` requests embed the verified known artifact identity | Predeclare stage options/order now; compute and verify later request bindings only at the known-stage boundary of a future authorized run. Do not invent hashes or use a fixture known root |
| Snapshot admission → execution | E13 reports NO-GO; E14 `deny_execution` always raises; supervisor `stage_argv` refuses unbounded production and `assert_bounded` caps children; E9 has no runnable state | Future executor/release integration requires its own independently reviewed contract. No current combination of host JSON, approval-shaped JSON, green CI or correct plan can remove these structural refusals |

In particular, **"approve E14, lock it, then flip the production flag" is not a
valid sequence**: it changes source/tool identity after approval and invalidates
the lock. Likewise, **"approve the gate and cite the old green CI" is invalid**:
the final head differs and the existing CI checks would reject the new state.
The future release design must resolve both dependencies before seeking a
run-specific approval; E15 records the blockers and implements no workaround.

E15 adds only a dedicated synthetic/metadata dossier workflow. The existing
`b2-readiness-ci.yml` authority assertions and full RF test workflow are unchanged.
The full workflow is not dispatched for E15 because its real-waveform replay
fixtures exceed this milestone's permitted verification scope. The new workflow
does not supply a future approved-generation CI policy or execution authority.

## 3. Stop, quarantine and requalification rules

Every future stage and shard boundary must recheck the identity/expiry/resource
conditions through the separately reviewed runtime. Stop on a failed shard,
corruption, partial descriptor, orphan temporary, unexpected path/inode, changed
source/request/environment/host/device, stale measurement, insufficient remaining
capacity or wall/core budget, first-shard timing failure, revoked/expired approval,
or journal/backup refusal. Preserve partial and corrupt evidence; quarantine must
not silently repair, delete or overwrite it. Resume only with identical admitted
request and run identity and sufficient remaining approved budget.

The first-shard timing band remains a historical-pilot extrapolation, not a
production measurement. A passing band test cannot ignore projected remaining
wall/core ceilings. Device snapshots cannot prove physical independence or later
stability; operator evidence, immutable finished roots, checksum manifests and an
external append-only incident journal remain necessary. E14's capped synthetic
writer/restore verifier is not integrated production durability or disaster
recovery qualification.

## 4. Held-out boundary and final decision

Generation creates frozen roles only after a scoped grant. It does not authorize
training, validation inference, nine-cell freeze, LOKO, D-5, GPU work or final
held-out evaluation. Preserve P31 phase separation and the complete three-view ×
three-seed freeze before any separately authorized final read. Preserve D-1's
non-pristine disclosure, 500/150 headlines and 498/148 exclusion rows; preserve
D-8 exact identity, source and audit bindings. The future production metadata
cross-check is mandatory and NOT RUN, and never opens observation arrays or
performance outputs.

The smallest next engineering milestone is the still non-launching integration
and release-policy review in step 2, alongside external host/backup qualification.
It is not launched by accepting this dossier. All compute gates and
`PRODUCTION_LAUNCH_ENABLED=False` remain unchanged; `benchmark_complete=false`.
