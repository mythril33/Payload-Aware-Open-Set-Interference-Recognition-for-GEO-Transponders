# P33 — B2 E9 production executor preparation (engineering only)

**State:** DESIGN / TEST PLAN, NOT EXECUTABLE, NO COMPUTE AUTHORIZATION.  
**Source baseline:** `141ba6032779504091c76e850f97c8aac4019cac`; scientific record: [B2 E9 approved decisions](B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md).  
**No modifications to `src/`, `configs/`, supervisor production caps or compute release gates in this PR.**

## Objective and separation of authority

Record researcher choices without confusing them with permission to run. Design the next engineering milestone for the isolated production executor; implementation and approval of that executor require a **separate reviewed milestone**. This document does not implement or call data generation, GPU throughput probe, full training, LOKO, or test inference.

## Required E9 future implementation interfaces

1. **Production configuration:** a validated explicit `TrainConfig`/runner input in a later commit, with views `co/dual/dual_residual`, seeds `0/1/2`, width16, time_pool2, carrier reference, epochs30, batch32, center0.005, plan BCE1.0, plan head enabled, K17b0.15 and 0.5MHz, groups/shard4 and window_shards4. Refuse omitted/implicit P20 settings. Leave `docs/plan/b2_e8_candidate_production_config.json` in its non-executable historical state.
2. **Isolated GPU execution:** extend P31 train-only and known-only calibration through explicit, reviewed mode(s), keeping independent freeze of nine cells and a strict first-test-read barrier. Current `b2_execution.py` caps (`groups_per_role<=2`, `epochs<=2`, `width<=8`, CPU only) remain in force until independent authorization and release. Never route full work through legacy coupled experiment.
3. **Numeric policy / lock:** implement `B2-R6-fp32-tf32-off/1` before source lock. Assert **effective** `torch.backends.cudnn.allow_tf32 == False`, `torch.backends.cuda.matmul.allow_tf32 == False`, and autocast disabled; persist torch, CUDA, cuDNN, GPU model, driver, flags and source commit in the later lock/checkpoints. The numerical switch is registered at P18 §10, but not yet implemented.
4. **Interruption protocol:** atomic output states, `attempt_id`, `INCOMPLETE` and parent hashes. Only restart the affected view/seed from epoch 0, never resume a partial optimizer/cursor; refuse duplicate/modified/unfinished cells at freeze.
5. **Resource checks:** read-only host inventory and separate-device backup assessment; measure generation host, CPU RAM, working disk and GPU VRAM/throughput **only after** the appropriate distinct approvals. A GPU probe must be explicitly capped, use train/val-select only, and authorize no production fit. An earlier "10–22 h width-16 nine-fit" figure cited here had no committed source and is withdrawn (E10 correction); the sourced, unmeasured estimates are in [the E8 host/resource assessment](B2_E8_HOST_RESOURCE_ASSESSMENT.md) and the approved protocol record, and none is a reservation.
6. **Release process:** reviewed production argv builder and first-shard gate (independent reviewer records exact source head); ensure no automatic cap removal based only on scientific gate PASS; exact-head CI green, clean tree, source/config/environment lock, resource ceilings and separately signed DR-04/DR-05/DR-06 decisions. `PRODUCTION_LAUNCH_ENABLED` stays `False` in the present PR.

## Read-only / CPU-only verification expectations

- Static scientific-record test: 13 decision headings, 29 parameter records; decisions agree with gates and mirrored E5 memo; compute gates remain all `NOT_AUTHORIZED`, `benchmark_complete=false`.
- Existing preflight test: scientific gates now PASS with actual research record; **all three compute gates still BLOCKED**. Pending/approved mismatch must FAIL and unapproved compute authorization must not be inferred from scientific PASS.
- Historical E7/E8 candidate remains `UNAPPROVED` and non-runnable, and all old E8 candidate tests continue to pass.
- P18 §10 records only the scientific R6 numerics selection; separate tests should fail if false TF32 is omitted from the approved science record.
- No full data creation, GPU probing, fitting or LOKO is performed as part of this PR. Existing CPU unit/fixture and source/document tests are the only intended validation. Legacy GPU-sensitive golden tests may be skipped on unsupported CI runners, and any skip is disclosed.

## Order of later gates (no auto-approval)

1. Review/merge **documentation-only** scientific approvals and E9 readiness plan after exact-head CI and independent review.
2. Implement future production executor and fail-closed guards in a **separate** engineering PR; re-review source and first-shard launch path; lock source and approved config **after** final `src/` edits.
3. Designate generation host, working disk, separate-device backup and **explicit DR-04 ceilings**; obtain a **separate DR-04 human authorization** before any full generation.
4. Audit/transfer/restore verification; designate GPU host and ceilings; obtain **separate bounded GPU probe authorization**; then a distinct **training DR-05** decision after measured results.
5. Freeze all nine train/scorer/calibrator bundles prior to first held-out read; any LOKO sweep is a separately budgeted **DR-06** request.

**Current outcome: all compute and release gates remain NO-GO.**
