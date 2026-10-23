# Researcher decision memorandum — E5

Date:2026-10-23. Recommendations only. No decisions are approved here and no gate status changes.
Authoritative status remains [readiness gates](b2_readiness_gates_2026-10-21.json).
Budget details: [execution plan](B2_E5_PRODUCTION_EXECUTION_PLAN.md).

## DR-E5-01 — K18 primary loss convention

**Status:PENDING_RESEARCHER.** Recommend retaining P20's pre-registered
`CE +0.005×sum_d squared-distance +1.0×plan BCE`, with the existing AdamW center updates/weight decay.
P21b's `0.01×mean_d` is a distinct stage; at embedding widthD the relative scale differs byD/2.
The [initial-scale](../results/k18_init_scale.json) and [scale audit](../results/k18_scale_audit.json)
are diagnostics, not a hyperparameter search. Changing the primary convention now would weaken continuity.
Log center/CE ratios on train only; do not tune from test outcomes. Researcher choice needed: confirm this
candidate or pre-register a separately versioned alternative before production. E5 changes neither loss.

## DR-E5-02 — K17d ASI level drift

**Status:PENDING_RESEARCHER.** Recommend keeping frozen B2-test/1 generation and reporting all500groups,
with the preidentified35missing-co-carrier groups as an explicit diagnostic sub-row. The
[drift audit](../results/k17d_drift_audit.json) records median0.71dB/max5.91dB affected drift; target-level
matching is not guaranteed at the effective received reference when planned carriers are missing.
No outcome-driven sample removal. If stricter realized-level matching is desired, approve a separate
B2-test/2 sensitivity study with its normalization/reference rule registered before generation;
do not silently repair B2-test/1 or alter the near-family definition. Choice needed: retain+disclose versus
new sensitivity version; this memorandum cannot make that choice for the researcher.

## DR-E5-03 — OBS-CANCEL/2 phase tracking

**Status:PENDING_RESEARCHER.** Recommend preserving obs-cancel/1 as the primary frozen benchmark receiver.
Its150Hz effective-linewidth block-constant phase estimate has a documented~21–25dB ceiling. Authorize
phase tracking only as a separate versioned receiver study if scientifically desired:64–128-symbol
segments, proposed high-rate reference depth≥35dB at150Hz/CN40dB (36Mbaud,64symbols),
gap-floor shift≤0.1dB, no paired-CuC visibility regression,
runtime≤2×, no test-family tuning. Those are proposed acceptance criteria, not measured results or an
approved new protocol. New residual data/checkpoints would need distinct fingerprints; no old channels
may be relabelled. Choice needed: defer or authorize a separately scoped design/validation milestone.

The35dB target is not universal across symbol rates. For a block-constant Wiener phase approximation,
residual variance is roughly`2π×linewidth×segment_duration/6`:64symbols imply about25.5dB phase-only
ceiling at3.6Mbaud versus35.5dB at36Mbaud, before other errors. Report lower-rate/128-symbol cases
separately; select segment duration/estimator through a preregistered synthetic feasibility study,
not test-family outcomes. No performance at these proposed settings has been measured in E5.

## DR-E5-04 — full data production authorization

**Status:NOT_AUTHORIZED.** Recommend authorizing only after DR01/02 and the primary receiver choice are
recorded. Proposed scope:21350observations, one pinned source/config/environment, obs-cancel/1,
36elapsed-hour/42core-hour reservation,25GiB working disk+separate9GBbackup, single generator process.
Readiness evidence supports the implementation; budget extrapolation has not been validated at scale.
Researcher must explicitly approve resource ceilings and the exact execution plan. No production command
was launched in E5. Source/role/cancellation checks remain fail-closed throughout generation and recovery.

## DR-E5-05 — GPU training authorization

**Status:NOT_AUTHORIZED.** Recommend a separately approved bounded throughput/VRAM probe on the
researcher's actual GPU before booking nine full fits (3views×3seeds,30epochs, fixed settings).
Reserve6GPU-h conditionally on200–1000sample-passes/s and12GiBVRAM/16GiBhostRAM; these are assumptions.
The probe does not authorize full fits. Specify hardware, batch/window size, exact package/build versions,
checkpoint provenance and interrupted-seed restart policy. Do not compensate for poor test performance by
changing losses or training budget. Researcher approval of the full fits remains a second explicit choice.

## DR-E5-06 — full LOKO sweep authorization

**Status:NOT_AUTHORIZED.** Recommend deferring until production data, primary training and a reviewed
production dispatcher/seed aggregator exist. Frozen minimum:7non-clean holdouts×3seeds=21fits for the
declared primary view. Extending to all3views means63fits, not21, and needs an explicit budget choice.
Conservative21fit estimate2.1–10.5GPU-h; all-view6.3–31.5GPU-h before overhead. Current E2 is a bounded
planning/single-fold harness, not a certified full sweep. No full sweep or implicit expansion is approved.

## Next authorization message

Suggested next milestone is bounded decision closure and GPU profiling preparation, not full production.
The researcher can send this exact prompt:

> E6 — Researcher gate closure and bounded resource validation. Read the E5 atlas, independent review,
> decision memorandum and execution plan at the merged E5 commit. Keep benchmark_complete=false.
> Record my decisions only as explicitly stated here: K18=[my decision]; K17d=[my decision];
> OBS-CANCEL/2=[my decision]. Prepare an immutable production source/environment/config lock and validate
> recovery on a capped fixture. If I provide GPU access and explicitly authorize the bounded probe,
> measure throughput and peak VRAM within my stated observation/epoch/time caps. Do not infer full B2
> generation, nine-fit GPU training or LOKO authorization. Return a concrete final execution packet and
> updated budget for my separate approval. No auto-merge.

Placeholders intentionally require actual researcher choices; copying the prompt without filling them
does not approve any gate. A later full-production message must explicitly name DR04 and its budget.
