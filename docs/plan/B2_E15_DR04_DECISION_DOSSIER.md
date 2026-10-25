# B2 E15 — DR-04 operational decision dossier

Version 1, 2026-10-25. **Researcher review package, not an approval record.**
Recommendation: **NO-GO**. Execution authority: none.
**SCIENTIFIC APPROVAL IS NOT COMPUTE AUTHORIZATION.**

## 1. Verified identity and authority

The fetched engineering baseline is `9e176ad20aa1f355adac06e5a22c77b38a616099`,
which merges PR #38. Its reviewed E14 code commit is
`edf1d929d5d40c310242a68bf5b3e3f7daa7c412`; PR #38's exact head is
`03b01972102074b055fee3624f4ddb03757d389c` (the following commit adds evidence
only). Baseline PR-head CI [40161909630/job121075064242](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40161909630/job/121075064242)
passed 3,232 tests with seven environment-dependent skips and 46 pytest warnings.
That CI is evidence for its named PR head, not a production-release certification
or an exact-head run of the later merge commit. E15's own checks are reported in
[verification](../results/B2_E15_VERIFICATION.md).

Scientific identity is unchanged:

| Frozen record | SHA-256 |
|---|---|
| `P18_b2_protocol.md` | `a25a73e1675aff5fcce9a4fca0ea4a25ccdd6b81e2cb03013f788f199dd65d8a` |
| `b2_e9_approved_scientific_protocol.json` | `ab96b933284ad134411db638bc3e18540efb749db60de4654beb00c7d1cc6eb1` |
| `B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md` | `817380b9fa10871da0774b1cc9cd043a56ae868c211b83f2967a0d6b6c372842` |
| `b2_e12_d1_d8_decisions_2026-10-24.json` | `ce900de1ae1b324d5de73997a8b303f2158fddf33fd544337347bb3df91689b1` |
| `configs/b2_base.json` | `8626109431cf9bd19c01920109b9265f202b1e27d6a0f5be526d8e033813d1a7` |
| `configs/cancellation.json` | `f3dc37078a5f289bf9e1c951bab480679178df8168b3dd297982f82a1f3260ec` |

K18, K17d, OBS-CANCEL-2, R1–R10 and D-1–D-8 remain scientifically ratified.
Canonical generation, GPU training and LOKO compute gates stay `NOT_AUTHORIZED`
with null approvals; GPU probe and final held-out evaluation are also unauthorized.
`PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`, the E9 guard and
E14 execution refusal remain closed. No intended generation host or persistent
backup has been explicitly designated in the verified records. The sandbox and
CI runner are not substituted for either.

## 2. DR-04 control matrix

Each primary status describes the current operational control, not a prediction
of future success. `VERIFIED` is deliberately limited to the stated engineering
scope. `PARTIAL` does not mean ready to run.

| ID | Requirement | Primary status | Verified evidence and exact unresolved requirement |
|---|---|---|---|
| Q-01 | Approved 21,350-observation inventory | VERIFIED | P18 and code-derived E13 inventory: 18,400 known + 2,500 test-only + 450 matched; no generation performed |
| Q-02 | 2,450 groups / 739 planned shards | VERIFIED | Frozen role ranges, paired variants and four-group planning; final partial shards retained; no committed production shards exist |
| Q-03 | known → test-only → matched | VERIFIED | Existing capped supervisor and E14 explicit predecessor chain `[null, known, test]`; later stages also require verified known-artifact binding; production execution unverified |
| Q-04 | Source/config/environment identity | PARTIAL | Existing source/config hashes and validators verified; no designated-host measurements or clean final production lock; future code must be reviewed and locked after approval |
| Q-05 | Sealed launch contract | VERIFIED | E14 hashes every planned stage/shard and refuses execution; this is a non-runnable specification, not a launcher |
| Q-06 | Runnable production executor | MISSING | `stage_argv` refuses production; fixture cap is two; E9/E14 always deny; independently reviewed runtime admission/supervision integration does not exist |
| Q-07 | Atomic generator durability | PARTIAL | Existing descriptor-last/checksum logic and E14 fsync/no-clobber synthetic reference tests; physical generators lack integrated durable publication and power-loss qualification |
| Q-08 | Persistent independent backup / restore | BLOCKED — EXTERNAL DEPENDENCY | No designated devices or real measurements; E14 record/observer/synthetic restore checks do not certify physical independence or a production backup; active workflow integration also missing |
| Q-09 | First-shard timing / stop rules | PARTIAL | Existing bounded timing gate, sealed stop rules and remaining wall/core projection requirement; target-host timing and production runtime enforcement unmeasured/unimplemented |
| Q-10 | DR-04 scope / expiry | NOT AUTHORIZED | No researcher compute authorization; blanks below are a worksheet only; neither green CI nor scientific approval grants generation |
| Q-11 | Exact-head CI / independent release review | PARTIAL | E14 named-head CI and independent model-agent code review verified; no production execution path exists to review, and final release-head evidence must be obtained after its changes |
| Q-12 | K17d production verification / held-out isolation | PARTIAL | Accepted identity, E14 metadata-only verifier and existing default-deny/P31 freeze contracts; actual production cross-check NOT RUN, future final evaluation separately unauthorized |

Primary-status count: **VERIFIED 4 / PARTIAL 5 / MISSING 1 /
BLOCKED — EXTERNAL DEPENDENCY 1 / NOT AUTHORIZED 1** (12 controls).
This count is a dossier classification, not the E13 validator's finding count.
There are no measured operational PASS claims for an undesignated host.

## 3. Requested operational scope and exclusions

The prospective DR-04 scope is **full B2 generation only**, with frozen counts,
roles, seeds, variants, four-group shards, configurations and P20 `obs-cancel/1`.
The request is not granted here. Generation order is known, then test-only,
then matched; subsequent requests bind the verified known artifact at their
stage boundary because those fingerprints cannot be finalized before it exists.

Generation may create metadata for all frozen roles only after a separate grant;
it must not use unknown/test/matched outcomes for tuning or model selection.
The detector/model input boundary remains calibrated spectra, operator masks and
the observation-derived cancellation residual; privileged generation metadata
is never turned into a learned feature by this dossier. No P21b substitution.

DR-04 would not authorize GPU discovery/probe, training, LOKO, D-5 sensitivity,
nine-cell freeze/calibration inference, final held-out evaluation, arbitrary
observation access, or a production-launch flag/guard change. Their scopes and
approvals remain separate. P31 train/val-select/calibrate/freeze/evaluate role
isolation and the complete three-view × three-seed freeze requirement are not
weakened by a generation decision.

## 4. Host, resources, backup and restart decision

[Host qualification](../operations/B2_E15_HOST_QUALIFICATION.md) is a template
with measurements **NOT MEASURED / BLOCKED**, not an inventory of this sandbox.
The [resource and backup assessment](../operations/B2_E15_RESOURCE_AND_BACKUP_ASSESSMENT.md)
contains arithmetic, historical pilot anchors, extrapolations and uncertainty.
The following remain unapproved proposals: at least 4 usable vCPU, 8 GiB host
RAM, 2 GiB generator RSS, 36 h wall, 42 core-hours, remaining 25 GiB working
reserve (about 33.880 GiB startup free), and 12 GB independent durable backup
(existing E5 floor 9 GB). They are not measured target-host capacity or authority.

The researcher must state a finite restart/interrupt allowance covered by the
time and storage ceilings. Existing proposal bounds are at most two failed
attempts and 20 interruptions per stage; these counters do not reserve enough
time automatically. Repeated startup, audit, quarantine and in-flight shard loss
must fit the same remaining wall/core/disk budgets. The future executor must
stop when the remaining estimate cannot fit; increasing a cap requires a new
reviewed plan and explicit decision, not an environment override.

Backup requires different measured filesystem devices and independently
documented physical backing, persistent reviewed filesystems, nonnested/no-alias
roots, sufficient live capacity, SHA-256 manifests retained externally, and
restore re-verification of source/request/config/environment and every shard.
Finished roots require operator access controls; mode bits are not WORM storage.
An external append-only journal and evidence-preserving quarantine must survive
working-volume loss. No production copy, backup, restore or power-loss test has
been performed. E14 synthetic utilities remain unwired reference controls.

## 5. D-1 exposure and D-8 identity obligations

The existing test population is **not pristine**. Historical test IDs
`3200000`, `3200001` and matched IDs `3300000`, `3300001` remain disclosed.
Keep the 500/150 headline groups and mandatory **498/148** exclusion-sensitivity
rows in every separately authorized final report. Do not remove these IDs from
generation, invent new seeds, or describe exclusion as proof of no past influence.

D-8 accepted identity SHA-256 is
`ccdf0a8f40e71d7ddb388068e455a77a131214f5644ab332a16c8268cfc49c6d`:
500 exact headline IDs, 35 co-feed missing groups (`pol==0`), 43 cross-feed,
78 total drops and 465 complementary groups. The accepted all-28-module geosim
package digest is `01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b`;
audit digest is `be4e2434bcd562f6521821da3403a5c5d5a14b8951ec6174ba0a795564fda65e`.
The historical identity file stays immutable; acceptance lives in the E12 record.

The future production metadata comparison must fail closed on group, role,
polarization, drop index, source, generator, request or checksum mismatch before
any separately authorized final evaluation. The E14 verifier does not open NPZ
or performance outputs and does not replace full payload/backup byte-integrity
audits. Actual production comparison is **NOT RUN**. A geosim source change,
including future durability integration, invalidates the package binding:
re-derive metadata under the new provenance and obtain independent review and
the required explicit acceptance before reuse; never relabel the old identity.

## 6. Researcher review worksheet — intentionally incomplete

This distinct worksheet schema is not accepted by E13 as an approval record.
Every decision/signature/host/approval time field is blank (`null`). Filling it
does not change a gate or activate a runner. After the operational blockers are
resolved, a separate researcher-authored record must follow the actual reviewed
approval contract, including scope, exact bindings and expiry (current E13
validation allows at most 30 days), with matching gate/memorandum provenance.
The committed design-approval block precedes the production lock; concrete
post-approval plan/source/lock bindings are assembled afterward as described in
the release sequence. This worksheet does not pretend those future hashes exist.

```json
{
  "schema": "B2-E15-DR04-review-worksheet/1",
  "valid_for_execution": false,
  "engineering_recommendation": "NO-GO",
  "requested_scope": "full B2 generation only: 21350 observations",
  "researcher_decision": null,
  "approved_by": null,
  "approved_at": null,
  "expires_at": null,
  "researcher_record_path": null,
  "release_source_head": null,
  "approved_design_digest": null,
  "run_plan_fingerprint": null,
  "production_lock_fingerprint": null,
  "host_id": null,
  "host_qualification_record": null,
  "working_root": null,
  "working_storage_id": null,
  "backup_root": null,
  "backup_storage_id": null,
  "external_journal_identity": null,
  "ceilings": {
    "wall_hours": null,
    "core_hours": null,
    "generator_rss_gib": null,
    "host_ram_gib": null,
    "working_reserve_gib": null,
    "backup_gb": null,
    "failed_attempts_per_stage": null,
    "interruptions_per_stage": null
  },
  "separate_release_decision": null,
  "launch_authorized": false,
  "benchmark_complete": false
}
```

## 7. Blocking decisions and smallest next milestone

Host/device designation and real read-only qualification are external dependencies.
The smallest code milestone is a **separate, still non-launching integration and
release-policy review** of production admission, durable generator commits,
backup/journal/resource supervision and provenance. It must resolve the CI and
hash-order conflicts in the [release sequence](B2_E15_RELEASE_SEQUENCE.md) before
freezing an approval-request digest. No caps or guards are changed in E15.

Only after the pre-approval controls, exact-head checks and host/resource evidence
exist should the researcher consider a DR-04 decision. The production lock is
created after that approval commit; a later separate launch decision still needs
the complete final packet. E15 completes the decision package while leaving the
run NO-GO.
