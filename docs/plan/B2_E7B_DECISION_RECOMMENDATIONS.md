# E7b researcher recommendations — proposals only

Date: 2026-10-24. Verified starting main:
`ed65eb54632fc4373accebc88452ddf0ff9fadfe` (PR22/PR23 merged).
This note reviews the **29 parameter records and ten R1–R10 questions** in
[the E7a proposal](B2_E7_TRAINING_SPEC_PROPOSAL.md) and its
[JSON twin](b2_e7_training_proposal.json). It changes no candidate value,
approval object, frozen config or scientific decision. Every proposal
`approval` remains null; `frozen=false`, `approved=false` and
`benchmark_complete=false`. R1–R10 approval would still authorize neither
DR-04 generation, DR-05 GPU work nor DR-06 full LOKO.

## One decision table

The coverage column maps each of the29 JSON records once. It is a review
cross-reference, not a new approval schema: carried frozen conventions
remain frozen, the three-seed **count** is already K17, and resource
estimates still require separate designated-host/compute decisions.
Recommendations below use existing protocols and evidence; no test result
or new sizing experiment was used to choose them.

P18 §5 requires P6 settings without a search. As the current proposal now
states for R2/R4/R5/R6, a non-P6-default value, or a data-driven epoch-sizing
rule, needs an explicit P18 §10 entry and a version name **before the first
fit**. Listing an alternative below neither approves it nor changes a
frozen protocol. R10 separately asks to confirm the acceptance and
Mahalanobis constants; they must not be called already approved P18 values.

| Decision | Covered parameter records | Recommendation awaiting the researcher | Alternative and resource consequence |
|---|---|---|---|
| **R1: scope/seeds** | `views`, `training_seed_count`, `training_seed_values` (3) | Keep co/dual/dual_residual and preregister values0,1,2; report every seed, select none by outcome. | Nine main fits; a single-view scope would use three, approximately one third of comparable fit work, but changes the comparison scope. It cannot silently weaken P31's full-protocol nine-cell admission rule. |
| **R2: width/resolution and resource context** | `model_width`, `time_pool`, `level`, `expected_cpu_ram`, `expected_gpu_vram`, `expected_sample_passes_and_wall_clock`, `compute_hardware` (7) | Candidate width16/time_pool2 with the existing carrier reference preserves the P6 default. Recompute the budget for that choice and require a separately authorized train/val-select-only throughput/VRAM probe on the designated host. | Width8 is the lower-cost pilot/budget option; width32 or time_pool1 increases cost. Non-default choices need the P18 §10/version step. Width16 has about3.31× width8 model MACs and twice the saved activations; the old6GPU-h reservation does not carry over. |
| **R3: K18** | `loss_composition`, `center_loss_weight`, `plan_loss_weight` (3) | Recommend E6 optionA: retain P20 sum-of-squared-distances weight0.005 and plan BCE1.0, with the existing observation-only train diagnostic. Decide jointly with width. | P21b's0.01×mean is64× weaker at width8 and128× weaker at width16; adopting it, searching another weight or disabling the mechanism needs an explicit method/config decision. No automatic width-dependent rescaling is proposed. |
| **R4: epoch budget** | `epochs`, `epochs_selection_procedure` (2) | If adopting the P6 assumption, fix30epochs before fitting. A different N or train/val-select-only sizing rule requires the prior P18 §10/version step; neither val-calib nor any test outcome may inform N. | At12,000train observations,30epochs means360,000passes per fit and3.24million for nine. Changing N changes the fixed-length OneCycle schedule; appending epochs is not equivalent to the originally specified fit. |
| **R5: batch** | `batch_size` (1) | Candidate batch32, as in the P6/default recipe, subject to the separate host probe. | Batch8 requires the P18 §10/version step, reduces batch activations by roughly4× but changes BatchNorm and steps375→1,500per epoch; at30epochs,11,250versus45,000steps per fit. No gradient-accumulation substitute is assumed. |
| **R6: unchanged recipe and explicit numerics** | `optimizer`, `learning_rate_schedule`, `gradient_clipping`, `precision_and_determinism`, `plan_shift_augmentation`, `mirror_roll_augmentation` (6) | Preserve AdamW peak lr1e-3, weight decay1e-4 on all existing parameter groups, current OneCycle, no clipping, mirror/roll and frozen K17b15%/±0.5MHz train-only shift. Explicitly decide/pin torch and numerical flags: fp32 storage does not mean TF32 is off. | Constructor betas are(0.9,0.999), but OneCycle cycles effective beta1 0.95→0.85→0.95. Current torch cuDNN TF32 defaults True and matmul TF32 False; there are no deterministic flags. Non-default recipe/numeric choices need the prior P18 §10/version step; no GPU parity is implied by CPU smoke. |
| **R7: streaming order** | `streaming_groups_per_shard`, `streaming_window_shards` (2) | Candidate four groups/shard × four shards/window: at most16scenario groups/128observations; keep each group's variants in its role/window. | The generator default of eight groups/shard doubles the corresponding window from about128 to256MiB and changes sample order. This is blocked shuffle, not a claim of parity with whole-role uniform shuffle. |
| **R8: isolation/freeze** | `checkpoint_selection_rule`, `test_evaluation_coupling` (2) | Prefer the separately reviewed P31 train-only → known-val-calib → freeze → evaluation capability before the production lock, preserving val-select first-maximum checkpoint choice. Confirm the constants separately in R10. | Legacy coupled pilot remains for compatibility. Full-protocol evaluation requires all three views × three explicit distinct seeds verified before the first test read/inference. A fixture profile proves wiring only and cannot satisfy that scientific admission claim. |
| **R9: interruption** | `interruption_policy` (1) | Recommend restart of the interrupted view/seed from epoch0 with parent-checkpoint lineage; do not splice partial fits. The choice is still pending. | A true resume snapshot needs optimizer/scheduler/RNG/data-cursor state and separate resume tests. A restart loses up to one fit;0.1–0.5h compute was width8-only and excludes loading/evaluation. Fixed-seed GPU restart is not a bit-identical replay with current non-deterministic numerical defaults. |
| **R10: calibration/Mahalanobis constants** | `mahalanobis_fit`, `calibration` (2) | Recommend explicit confirmation of pilot/P20 values: known acceptance0.95, clean alarm Pfa0.05, train-only Mahalanobis regularization0.1. Keep acceptance and clean-alarm operating points separate. | The clean5% Pfa is also P18;0.95acceptance and0.1regularization are P20/pilot constants, not approved P18 numbers. Different values require the stated P18 §10 step before use. Confirmation adds no model fit, but a different scorer/calibration identity invalidates prior frozen bundles. |

## Width8 budget versus width16 default

The current committed proposal's E7a footprint evidence gives, for dual_residual:

- Width8:79,377model parameters, embeddingD128,0.097GMac/sample,
  P20/P21b center-term ratioD/2=64, and0.005×D=0.64.
- Width16:311,705parameters,D256,0.321GMac/sample, ratio128,
  and0.005×D=1.28. Relative to width8 this is about3.93× parameters,
  3.31× model MACs and2× saved activation bytes at the same batch/shape.
- At batch32 the analytic saved activations are214.0versus428.1MiB;
  the recorded analytic VRAM bounds are235.3–449.3versus452.9–881.0MiB.
  Those bounds exclude CUDA context, kernel workspaces and fragmentation;
  they are not GPU measurements or a safe allocation ceiling.

At four groups/shard and four shards/window, the current proposal records
about128MiB steady window storage and208.3MiB build peak; the latter is
not the128.3MiB earlier snapshot. Eight groups/shard doubles these to about
256MiB and416.5MiB. These are analytic layout figures, not production RSS.

The [production budget](../results/b2_production_budget.md) and
[E5 execution plan](B2_E5_PRODUCTION_EXECUTION_PLAN.md) assumed width8
throughput200–1,000sample-passes/s, giving0.9–4.5GPU-h of pure model
compute for nine30epoch fits and a proposed6GPU-h reservation. The basic
synchronous-loader extrapolation is about5.88h for nine fits on a different
loaded CPU; it omitted val-select reads/preprocessing and K17b
re-preprocessing. Including those terms gives about93s/epoch and7.0h for
nine fits, with an estimated width8 compute-plus-serial-loader total of
about7.9–11.5h (the older partial accounting was6.8–10.4h). All are
extrapolations, not a designated-host measurement. The6GPU-h figure needs
revision regardless of whether width8 or16 is selected.

Multiplying width8's pure-compute band by the model-MAC ratio would give
about3.0–14.9h for width16, **an analytic screening extrapolation only**.
Real GPU utilization, the batch, kernels and synchronous I/O do not scale
solely with MAC count; this is neither a measured budget nor a reservation.
Use a separately authorized bounded train/val-select-only probe to replace
these assumptions. This session runs no such GPU probe or production fit.
E7b's width≤8 CPU smoke cap is an engineering limit, not an R2 decision.

## Evidence and authority

Sources: [E7a proposal §§2–6](B2_E7_TRAINING_SPEC_PROPOSAL.md), its JSON
`evidence.footprint_run.widths`/`rows`/window records,
[P6](P6_modeller.md), frozen [P18](P18_b2_protocol.md),
[P20](P20_b2_cancellation_residual.md),
[E6 decision packet](B2_E6_RESEARCHER_DECISION_PACKET.md), and
[P31 execution contract](P31_b2_e7b_isolated_execution.md).
The footprint was measured previously on CPU using synthetic random
batches; the GPU columns and production rates are estimates. No historical
checkpoint may be relabelled after E7b source-identity changes.

P31 provides bounded execution engineering while researcher choices remain
open. Its default full inventory has nine cells; its LOKO planner names
seven non-clean holdouts × three seeds × selected views, but execution
remains at most two explicitly selected CPU smoke cells per immutable
output selection. Neither21fits nor63fits is authorized or exposed as an
unrestricted launch. A capability/readiness PASS is not an approval of
R1–R10, K18/K17d/OBS-CANCEL/2 or production compute. The prior local
nine-row R1–R9 recommendation was based on an older main snapshot; this
ten-row table supersedes it without replacing the current source proposal
or editing its approval objects.
