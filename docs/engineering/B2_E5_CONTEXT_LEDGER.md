# E5 verified context ledger — 2026-10-23

Scope: scientific reporting and production preparation only. `benchmark_complete=false`.
Fresh branch `feature/b2-e5-scientific-atlas` starts at actual fetched
[`main@79a17cc`](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/commit/79a17ccb0ba9967cc8a31156faab49510e360b3e).
Both `git fetch origin --prune` and GitHub's branch API independently confirm it.

## GitHub preflight

| PR | Verified state | Merge SHA | Meaning |
|---|---|---|---|
| [15](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/15) | merged | `4b736a6` | E4 implementation |
| [16](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/16) | merged | `5ce96e2` | independent recovery, partial 9/25 fixture |
| [17](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/17) | merged | `ed5c603` | parallel evidence/resume hardening |
| [18](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/18) | merged | `79a17cc` | reconciliation and complete 25/25 unified evidence |

At preflight no open PRs. Branch API listed `main`, `claude/dazzling-maxwell-y0hw0q`,
`claude/hopeful-feynman-f6nxfn`, `claude/youthful-dijkstra-0ephko`,
`docs/b2-e4-postmerge-evidence`, `docs/b2-production-readiness-2026-10-21`,
`feature/b2-e1-streaming-loader`, `feature/b2-e2-loko-harness`,
`feature/b2-e3a-delivery-records`, `feature/b2-e3a-edsc-baseline`, `feature/b2-e3b-xgboost-baseline`.
No existing branch was overwritten.

Actual decoded logs of [run39967494290/job120461084118](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39967494290/job/120461084118)
were read, not inferred from PR prose: success; E4 **107 passed136.78s**;
remaining suite **1121 passed239.66s**, no skips/failures. Checkout synthetic merge
`b1ce405`, PR head `176faf5bb2f69d096557f3b3f90db96f55eb132e`; main merge has the same tree.
Gate and compile steps also succeeded. Completed E4 repair was not restarted.

## Frozen rules and verified artifacts

| Authority / artifact | Binding interpretation |
|---|---|
| [AGENTS](../../AGENTS.md), [CLAUDE](../../CLAUDE.md), [current status](../plan/DURUM.md) | preserve roles, physics, provenance and strict JSON; Turkish researcher communication |
| [P18](../plan/P18_b2_protocol.md) | group-isolated train / val-select / val-calib / test / test-matched; unknown positive; CID benign/excluded; near pool only |
| [P20](../plan/P20_b2_cancellation_residual.md) | `obs-cancel/1`, observed calibrated co IQ + co operator plan only; full-band and carrier-core depth are different statistics |
| [P28](../plan/P28_b2_e4_dual_pol_a5.md) | physical signal fixed; operator belief intervention; exact parity vs tolerated0.125dB explicitly distinct; bounded caps unchanged |
| [complete unified report](../results/b2_a5_dual_pol_pilot.json) | SHA256 `88bf7d2af40876c09b233697a68788a0d337d468adce996a5882e4b20f804b2d`; 25/25,90 replay checks,154 cancellations,64 recomputations,870 scored evaluations |
| [preserved recovery](../results/b2_a5_postmerge_partial_pilot.json) | SHA256 `289aedf43885ac2f76d9a81da47127f2b300f80d2a446c7f946b2187daf2ee67`;9/25,32 checks,56 cancellations,24 recomputations,312 evaluations;16 unselected slots |
| [historical implementation review](../research/b2_e4_red_team_review.md), [recovery review](../research/b2_e4_postmerge_review.md) | independent historical records, not a combined-code certificate |
| [fresh unified review](../research/b2_e5_unified_scientific_review.md) | separate read-only agent audits combined implementation, sources, denominators and E5 figures |
| [P23](../plan/P23_b2_production_readiness.md), [gates](../plan/b2_readiness_gates_2026-10-21.json) | scientific decisions pending; compute not authorized; proposals never approvals |

Complete known fingerprint: `6c2b95ed84cc0e51e614cc2311d32b646959c4697e5f4ffbbb0076b2942f59e2`;
partial known fingerprint: `1c510cd0d5eb76e4dc61d36497699fc9a938633f740bd375f2abd0a1f3928b81`.
Request fingerprints can match while data/checkpoint fingerprints differ. Never group by request alone.
Unified full source fingerprint at baseline:
`fc03075d665061d1b440cb8e6072b1b3c522bf817e25cad8b6e8a8facd189ef6`.
The E5 integrity fixes intentionally change the current source fingerprint; historical evidence stays
bound to its original revision, never relabelled as a fresh E5 pilot.

## Scientific meanings and denominators

`original` reads stored PSD/masks/residual. `MASK_ONLY` rebuilds corrupted masks but retains the stored
residual. `RECEIVER_CONSISTENT` rebuilds masks and recomputes the residual from replayed co IQ and the
corrupted co belief with the frozen canceller, after parity verification. `co_only` / `cross_only` / `both`
select belief descriptors, not physical injection paths. Both is the union of the independent transformations
and requires both to apply. Cross-only invokes no co-plan-driven cancellation; equality to stored residual
additionally requires exact parity. Original clean/event alarm rates under counterfactual beliefs are
descriptive rates, not conventional false-alarm/detection rates. Accuracy belongs to original only;
counterfactual agreement does not establish correctness.

Unified inventory:100 selected scene-slots=90 applied+10 not-applicable+0blocked. Nineteen known invocations
reuse four physical scenes (2groups × clean/unauthorized); six matched invocations reuse four scenes
(2groups × ASI/unauthorized). Thus eight distinct(scene_id,label), four distinct scenario IDs, not90
independent observations. Partial report also reuses eight scenes but belongs to a different fixture.
Scored870 includes paired conditions/views, not870 physical scenes. No statistical pooling across the two reports.

## Open risks and exclusions

Only committed E4 summaries are present locally; historical per-invocation JSON/state/NPZ are absent.
This audit verifies strict JSON, baseline source hashes, source fingerprint and internal conservation/denominators;
it does not pretend to recheck unavailable historical raw files. The physical display summary comes from the
separate existing `dcffb264...` verified E3 fixture, with original artifact/request/calibration/shard hashes.
No raw dataset/checkpoint is committed. Library/platform parity across machines is untested; checksums are
integrity rather than authentication. Two groups and two clean calibration scenes cannot support population
Pfa or recognition claims. Historical real SIGKILL evidence predates unified scene-state/2; its current
resume behavior has deterministic fault-injection tests.

No full generation, GPU training, full LOKO, protocol mutation, loss change, cancellation-version change,
threshold fitting or auto-merge. Physical truth is allowed only in labelled offline diagnostics and P28's
privileged `authorize_intruder` belief intervention; it is never a recognition input.
