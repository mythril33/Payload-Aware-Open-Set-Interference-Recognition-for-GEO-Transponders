# Frozen B2 production execution plan — planning only

Date:2026-10-23. `benchmark_complete=false`. This is a reviewable plan, not an execution authorization.
The [decision memorandum](B2_E5_RESEARCHER_DECISIONS.md) leaves every authority gate unchanged.
Sources: [P18](P18_b2_protocol.md), [P20](P20_b2_cancellation_residual.md),
[P23](P23_b2_production_readiness.md), [measured production profile](../results/b2_production_budget.md),
[E1 measurements](../results/b2_streaming_memory.md), [P25](P25_b2_e2_loko_harness.md).

## Exact inventory and isolation

| Role/stage | Groups | Variants/group | Observations | Permitted use |
|---|---:|---:|---:|---|
| B2-feat/1 train |1500|8|12000| weights, feature statistics, Mahalanobis |
| B2-feat/1 val-select |150|8|1200| fixed-budget checkpoint selection only |
| B2-feat/1 val-calib |150|8|1200| known-only acceptance thresholds;150clean alarm calibrators |
| B2-feat/1 known-test |500|8|4000| final test evaluation only |
| B2-test/1 |500 shared test groups|5|2500| four unknown families +500 benign CID; never fitting |
| B2-match/1 |150 separate test-matched groups|3|450| level-matched clean/ASI/unauthorized only |
| **Total** |||**21350**|18400known+2500test-only+450matched |

P18's old approximate prose count does not replace this exact arithmetic. Group IDs remain the frozen
3000000/3100000/3150000/3200000/3300000 namespaces. All variants stay in one role; known and test-only
variants deliberately share test groups and paired resampling; matched groups never enter training,
selection or calibration. CID is not unknown-positive; near-family pool contains only pulsed,
intermittent_bursts and adjacent_satellite_downlink. Wideband noise is separate.

## Resource reservation proposal (all full-scale numbers are estimates)

| Resource | Recommendation and basis |
|---|---|
| Generation wall time |23–30.2h, central26.6h; one generator process/two BLAS threads on comparable4CPU host. Reserve36h including validation/recovery, not a speed guarantee. Historical60-observation matched profile262s/300.2CPU-s; no new full-scale measurement. |
| CPU consumption |roughly26–35core-h if the measured CPU/wall ratio300.2/262 extrapolates; reserve42core-h including20% allowance. CPU time differs from elapsed time. |
| Storage |about8.7GB decimal (8.1GiB) for canonical observations and metadata; raw float16 arrays395264B/observation imply8.44GB before metadata. Reserve25GiB working space plus a separate checksum-verified backup of at least9GB. Keep raw IQ transient (saving it would add~170GB). |
| Generator memory |measured~601MiB single process; reserve2GiB/process and at least8GiB host RAM. No measured full-production peak. |
| Training host memory |E1 streams four shards/window; use4groups/shard initially:32scenes/shard, raw~12.1MiB, preprocessed~20MiB. Four-window buffers plus model/optimizer/imports need headroom; recommend16GiB host RAM, profile before booking larger windows. Multi-window order is blocked shuffle and is fingerprinted, not bit-identical to global legacy shuffle. |
| GPU memory |planning reservation8GiB minimum,12GiB preferred for batch8/width8/5×64×512; unmeasured. A separately authorized short throughput/peak-VRAM probe must establish an actual limit before multi-seed work. |
| Main training |3views×3seeds×30epochs×12000=3.24million sample-passes. Assumed200–1000passes/s gives0.9–4.5GPU-h pure training; reserve6GPU-h including IO/evaluation. This throughput is an assumption, not a measured result. |
| Full LOKO |7holdouts×3seeds=21 additional fits for the main five-channel view. Conservative12000-observation cost gives2.1–10.5GPU-h; held-out removal actually leaves10500train observations. Three views would mean63fits,6.3–31.5GPU-h; reserve~38h with20% overhead only if separately approved. No dispatcher/seed aggregation is certified yet. |

CPU generation estimate does not assume an unimplemented multiprocess writer/merge facility. Keep stages
serial on the current canonical root; do not combine separately generated role roots by copying files.
Training source verification and NPZ decompression can dominate small-model GPU throughput; validate
sample-passes/s on the intended host with E1. No inference-time or memory number here is a GPU measurement.

## Execution order after explicit authorization

1. Archive the researcher's gate decisions with timestamp, exact config hashes, authorized compute/storage
   ceiling and production commit. Resolve K18/K17d and the choice to retain obs-cancel/1 before data starts.
   Freeze a clean checkout, Python/package lock, BLAS/thread settings, generator hashes (including bundled
   payload curves), source/calibration/cancellation identities and artifact version. Never change code mid-root.
2. Preflight space and filesystem atomic renames; record machine/CPU and environment. Create a fresh
   outside-Git artifact root. Production known command is the existing `geosim.b2_dataset` with
   `configs/b2_base.json`, `--cancellation configs/cancellation.json`, `--groups-per-shard4`, all four roles
   and no group limit. Actual CLI flags must be copied from `--help` at the pinned commit before launch.
   This document deliberately supplies no runnable unrestricted shell launcher.
3. Produce known first; verify request/calibration, descriptor and NPZ/JSONL hashes, schema/dtypes/shapes,
   finite arrays, unique(group,label), role ranges/counts, consistency target and cancellation provenance.
   Keep all eight variants of each group together. Quarantine failures and stop; never recast numerical
   simulation failures as infeasible scenes. Validate completed roles before dependent stages.
4. Produce B2-test/1 bound to this exact known root/calibration; verify all five families and CID behavior.
   Produce B2-match/1 with separate150groups and the registered4–7/7–10/10–13dB bins. Confirm21350records,
   no group-role crossing and exact request/fingerprint bindings. Run physical diagnostic checks offline,
   without using truth to train, normalize or select thresholds. Keep natural/matched distributions separate.
5. Write a transfer manifest of paths/lengths/SHA256 and artifact fingerprints; verify after transfer to GPU
   host, including source/environment compatibility. Archive immutable object versions, not mutable symlinks.
   A backup restoration must revalidate every shard before training.
6. Under separate GPU approval, use canonical E1 streaming trainer with registered seed/config per view,
   train-only normalizers/Mahalanobis, val-select checkpoint rule and val-calib known-only thresholds.
   Record epoch/sample order, window_shards, seed, source/config/data/calibration hashes, loss convention,
   optimizer and scheduler. A checkpoint for inference is not automatically a restartable training snapshot.
7. Freeze all nine selected checkpoints and scorers/thresholds before final test evaluation. Evaluate once,
   report three training seeds separately from scenario-bootstrap uncertainty, keep tasks/positive classes
   and denominators explicit, and regenerate the atlas from approved measured results.
8. Treat full LOKO as a later independently approved milestone: finish dispatcher and multi-seed aggregation
   with bounded tests first. Remove each held-out class from weights, val-select, calibration and train
   statistics; clean remains known. No automatic21/63-fit expansion or threshold tuning on held-out outcomes.

## Recovery and provenance

Generation resumes only under an identical request/source/environment; existing validators check committed
shards before reuse. Four groups/shard caps interruption loss at32known/20test-only/12matched observations.
Incomplete temporary writes are uncommitted, never counted; verify their ownership before cleanup.
Stop on incompatible requests or damaged committed shards and use a fresh root or documented restoration;
do not overwrite evidence to make resume succeed. Keep an external stage journal with planned/completed/
failed/missing counts, per-attempt command, real exit code, elapsed time, CPU time and peak process RSS.
The E4 matrix runner is capped and cannot be used as an unrestricted production dispatcher.

Training interruption recovery is a readiness gap: current selected model checkpoints do not promise full
optimizer/scheduler/RNG/data-cursor restart. Before long training, either implement a separately reviewed
snapshot binding all these objects plus source/data/config/environment, or restart the interrupted seed/view
from epoch0 under the same budget. Never splice partial epochs or present resumed weights as deterministic
continuation without proof. Record parent checkpoint hash and whether a fit restarted or truly resumed.

Acceptance is complete verified artifacts and provenance, not `benchmark_complete=true`. That flag stays
false until the researcher explicitly accepts all scientific requirements, ablations and review results.
