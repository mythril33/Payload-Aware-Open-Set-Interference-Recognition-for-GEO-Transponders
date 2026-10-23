# E7a candidate production-training specification — PROPOSAL, NOT FROZEN, NOT APPROVED

Date: 2026-10-23. Base commit `755b474`. `benchmark_complete=false`. Machine-readable twin:
[`b2_e7_training_proposal.json`](b2_e7_training_proposal.json) (schema `B2-training-proposal/1`, every parameter with value, basis,
source, `needs_researcher_approval`, alternatives, consequence and `approval: null`). Footprint tool:
[`scripts/b2_training_footprint.py`](../../scripts/b2_training_footprint.py); tests: `tests/test_b2_training_footprint.py`.

**Nothing here is a frozen configuration.** `configs/` was not touched (`configs/b2_feat.json` is still the 3-epoch pilot config), no protocol
document or gate was edited (the only `src/geoml` edits of this pull request are the observation-only K18 train-time diagnostics, see R3
and section 7), K18 / K17d / OBS-CANCEL/2 stay `PENDING_RESEARCHER`, and full generation / full GPU training /
full LOKO stay `NOT_AUTHORIZED`. **Approving any value below does not authorize GPU training, data generation or LOKO**; those are the separate
gates DR-04 / DR-05 / DR-06 of the [E5 memorandum](B2_E5_RESEARCHER_DECISIONS.md). The K18 analysis is in the
[E6 decision packet](B2_E6_RESEARCHER_DECISION_PACKET.md) section 2 and is not repeated. File:line citations refer to commit `755b474`;
the K18 diagnostic edits of this pull request shift later line numbers in `src/geoml/train.py` and `b2_stream.py`.

## 1. Four findings the researcher should know first

1. **No production training config exists.** P18 section 5 (`P18_b2_protocol.md:126`) says "hyperparameters: P6 settings, no search"
   (P18 is frozen: every change is a section 10 entry, and the gates file lists "new protocol semantics without version and P18 section 10" as
   prohibited without explicit approval; so **choosing the P6 / `TrainConfig` defaults closes an item, while any other width, batch, optimizer
   constant or epoch count, and any data-driven sizing run, is a change to P18 section 5 that needs a section 10 entry and a new version name
   before the first fit**); P6 section 4
   (`P6_modeller.md:39-43`) lists AdamW lr 1e-3 one-cycle, weight decay 1e-4, 30 epochs, batch 32, three seeds, all tagged `[VARSAYIM]` (assumption) by P6 itself.
   The `TrainConfig` defaults reproduce them (`train.py:26-32`: width **16**, epochs 30, batch 32). The pilot config uses width **8**, batch **8**, 3 epochs.
2. **The budget was written for width 8, the defaults are width 16.** The 200-1000 samples/s band is stated "for the ~80 k-parameter ResNet"
   (`b2_production_budget.md:74`, width 8; the E5 GPU-memory line says batch 8 / width 8). Width 16 has 3.3x the multiply-accumulates and K18's D/2 ratio doubles (64 -> 128).
3. **The runner trains and tests in one invocation**, one seed per invocation, with no train-only mode (`b2_experiment.py:479-499`, `:766-775`); a checkpoint holds
   the best-epoch weights only, no optimizer / scheduler / RNG / cursor (`train.py:313-321`).
4. **The loader is synchronous** (no `DataLoader`, prefetch or workers anywhere). At the E1 loader rates the data path alone is about 39 min per 30-epoch fit and 5.9 h for nine fits,
   which is of the order of the whole 6 GPU-h reservation (section 6). The estimate omits the val-select read (about 4 s per epoch), val-select
   preprocessing (about 4.4 s) and the K17b re-preprocessing of 15 % of the rows (about 6.7 s): about 93 s per epoch, 7.0 h for nine fits, roughly
   1.9x the reservation. Unverified on the target host; the DR-05 probe must measure end to end.

## 2. Candidate values (full records, alternatives and consequences are in the JSON)

Basis: `existing_config` = committed config or frozen protocol text; `repository_default` = code default or closed design document, not frozen in a production config;
`plan_assumption` = exists only in planning documents; `engineering_recommendation` = this work package, no repository source.

| Parameter | Candidate | Basis | Source | Approval |
|---|---|---|---|---|
| Views | co, dual, dual_residual (2/4/5 channels) | existing_config | `b2_feat.json:3-7`, `data.py:43-44` | R1 |
| Training seeds | count 3 (K17, user decision); values 0, 1, 2 | existing_config / repository_default | `P18:150,152`; `b2_loko.py:81` (LOKO default) | values: R1 |
| Model width | **16** (alternatives 8 = pilot, 32); candidate only | repository_default | `train.py:26`, `P6:30` | R2 |
| time_pool / level | 2 / carrier | repository_default | `train.py:24-25`, `P6:26` (names 1 as a GPU option) | time_pool: R2 |
| Epochs | **30 - an ASSUMPTION** (P6 `[VARSAYIM]`, never validated on B2) | repository_default / plan_assumption | `train.py:27`, `P6:40`, E5 plan:37 | R4 |
| Batch | 32 (pilot 8) | repository_default | `train.py:28`, `P6:40` | R5 |
| Optimizer | AdamW, peak lr 1e-3, weight decay 1e-4 on **all** parameters (BatchNorm, biases, centres included), one group, constructor betas (0.9, 0.999) / eps 1e-8 (OneCycleLR then cycles the first moment 0.95 -> 0.85 -> 0.95, so beta1 is never 0.9 during a fit) | repository_default | `train.py:29,31,248-249`; `b2_stream.py:453-454` | R6 |
| Schedule | `OneCycleLR(max_lr=1e-3, total_steps=epochs x ceil(12000/batch))`, per step; torch defaults pct_start 0.3, cosine, div 25 (start 4e-5), final div 1e4 (end 4e-9), momentum cycling 0.85-0.95 | repository_default | `train.py:250-251,278`; defaults read in torch 2.14.1 | R6 |
| Gradient clipping | none | repository_default | no `clip_grad*` in `src/` or `scripts/` | R6 |
| Precision / determinism | fp32; no autocast, no `DataLoader`, no deterministic flags; `--device` defaults to `cpu`. **cuDNN TF32 is ON by default in torch 2.14.1** (`torch.backends.cudnn.allow_tf32` True, `matmul.allow_tf32` False), so on an Ampere or newer GPU the convolutions run in TF32 unless the lock pins the flag | repository_default | `b2_experiment.py:772`; `git grep` at `755b474` (no TF32 flag is set anywhere); flags read in the verification venv | R6 |
| Loss | CE + 0.005 x sum_d centre + 1.0 x plan BCE (K18 pending) | existing_config | `b2_feat.json:22-23`; `P20:84-88`; `train.py:269-274` | R3 |
| K17b plan shift | 15 % of samples (Bernoulli per sample per batch), continuous U(-0.5, +0.5) MHz, training only | existing_config (frozen K17b) | `b2_feat.json:24-25`; `P18:170-175`; `train.py:194-195` | - |
| Mirror / roll | mirror p = 0.5 per sample; **one** circular time roll per batch | repository_default | `train.py:263-266` | R6 |
| Groups per shard | 4 (generator default is 8) | plan_assumption | E5 plan; `b2_dataset.py:39` | R7 (with DR-04) |
| Window | `window_shards` 4: blocked shuffle, at most 4 x 4 = 16 scenario groups per window | repository_default | `b2_stream.py:67`, P24 section 5 | R7 |
| Checkpoint | best val-select macro-F1 over the 8 known classes, evaluated each epoch, first maximum kept | existing_config | `P18:258`; `train.py:281-292` | - |
| Mahalanobis | train-role embeddings of the selected checkpoint, regularization 0.1 (stated in `P20:92` and the pilot config; **no P18 line carries the number**) | existing_config | `b2_feat.json:16`; `b2_experiment.py:510`; `P20:92` | R10 (confirm) |
| Calibration | val-calib known classes only: acceptance 0.95 (stated in `P20:90-93` and the pilot config, **not in P18**), clean alarm Pfa 0.05 (`P18:149`) | existing_config | `b2_feat.json:14-15`; `b2_experiment.py:516-535`; `P18:94,149`; `P20:90-93` | R10 (confirm) |
| Interruption | restart the (view, seed) fit from epoch 0, record parent hash, never splice | engineering_recommendation | `train.py:313-321`; E5 plan:88-92 | R9 |
| Test coupling | procedural freeze of the 3 x 3 plan, or a reviewed train-only mode | engineering_recommendation | `b2_experiment.py:479-499` | R8 |

## 3. Values that need researcher approval

Each sentence is a template: filling or copying it approves nothing until the researcher writes it in their own words and the record is entered in
the gates file. None of R1-R10 changes a gate; none authorizes compute. P18 section 5 (`P18_b2_protocol.md:126`) binds the recipe to P6 by reference and forbids a search; a section 10 entry is required, with a new version name, before the first fit whenever a value below departs from the P6 / `TrainConfig` default (R2 other than width 16, R4 other than 30 epochs or any sizing rule, R5 other than 32, R6 other than the recipe as implemented). R4's sizing run is itself a search under P18:126.

| # | Decision | What the choice changes | Exact sentence the researcher would have to give |
|---|---|---|---|
| R1 | Views and seeds | 9 fits (3 x 3), or 3 for the main view only; seeds are fixed before the first fit and all reported | "R1: I approve training the views [co, dual, dual_residual / dual_residual only / ...] with the fixed training seeds [0, 1, 2] per view ([9 / 3 / ...] fits); all seeds are reported and none is selected by outcome." |
| R2 | Width, time_pool | Parameters 79 k / 312 k / 1.24 M (dual_residual); D = 128 / 256 / 512; K18 ratio 64 / 128 / 256; MACs 0.097 / 0.321 / 1.154 G per sample; time_pool 1 doubles activations; **width other than 16: P18 section 10 entry before the first fit** | "R2: I choose model width [8 / 16 / 32] and time_pool [2 / 1] with the per-sample carrier reference." |
| R3 | K18 loss (after R2) | see the E6 packet; the centre term weighs 0.005 x D on the per-dimension mean square (0.64 / 1.28 / 2.56) | "R3: K18: I choose option [A / B / C / D]; centre-loss weight [..], plan-BCE weight [..]; keep the train-only centre/CE diagnostic already implemented in both trainers (observation-only, always on): [keep / remove before the source lock]." |
| R4 | Epoch budget | Cost 12,000 x N passes per fit; OneCycle is re-scaled to N, so a shorter run is a different run; a sizing run must use `fit_streaming` on train + val-select only, because the runner also evaluates test (`b2_experiment.py:479-499`) and no such driver exists; **30 epochs unchanged closes the item; any sizing rule is a search: P18 section 10 entry before the first fit** | "R4: I fix the budget at [N] epochs for every fit (fixed-length OneCycle, no early stopping); N is [taken unchanged from P6 / chosen by the pre-registered train/val-select sizing rule: ...] and no test, test-only, matched or val-calib result informs it." |
| R5 | Batch | 375 vs 1,500 steps per epoch (11,250 vs 45,000 per fit); BatchNorm batch statistics; VRAM scales ~linearly; **batch other than 32: P18 section 10 entry before the first fit** | "R5: I fix the batch size at [8 / 32 / ...]." |
| R6 | Optimizer recipe | The P6 recipe as implemented, incl. weight decay on centres and BatchNorm, no clipping, library-default schedule constants (the lock must pin torch); **any constant other than the recipe as implemented: P18 section 10 entry before the first fit** | "R6: I approve AdamW (peak lr [1e-3], weight decay [1e-4] on all parameters, torch default betas/eps) with OneCycleLR (torch defaults: pct_start 0.3, cosine, div_factor 25, final_div_factor 1e4, momentum cycling 0.85-0.95), no gradient clipping, fp32, mirror (p = 0.5) plus one circular time roll per batch, on the pinned torch version." |
| R7 | Sample-order policy | Blocked shuffle: <= 16 groups per window at 4 x 4 (32 at 8 groups per shard); the 8 variants of a group always share a window; not a replication of a uniform-shuffle run | "R7: I accept the blocked-shuffle sample order with [4] groups per shard and [4] shards per window (at most [16] scenario groups per window) as the production training order." |
| R8 | Test coupling | Per model the roles are clean; "all nine frozen before any test evaluation" (E5 plan step 7) is not met by the current runner | "R8: I choose [procedural freeze of the 3 x 3 plan / a reviewed train-only mode before the source lock] to keep test evaluation after all fits are frozen." |
| R10 | Calibration and Mahalanobis constants | Confirms acceptance 0.95, clean alarm Pfa 0.05 and Mahalanobis regularization 0.1, which the pilot config and P20 state but no P18 line does; a different value is a change to frozen text (section 10 entry) | "R10: I confirm known-class acceptance target [0.95], clean alarm Pfa [0.05] and Mahalanobis regularization [0.1] for the production run, as in the pilot config and P20 section 6." |
| R9 | Interruption | A restart loses at most one fit (0.1-0.5 h compute at the assumed throughput); a snapshot edits `src/geoml` and needs a bit-exact CPU resume test | "R9: an interrupted fit [restarts from epoch 0 with the parent checkpoint hash recorded / resumes from a reviewed snapshot implemented before long training]." |

Carried unchanged, no new approval asked (frozen or pre-registered): K17b shift 15 % / 0.5 MHz, auxiliary plan head, checkpoint rule, `level=carrier`, three training seeds as a count.
Compute figures (host RAM, VRAM, throughput, GPU-hours) are information for DR-05, not part of R1-R10.

## 4. Engineering-only facts verified (at `755b474`)

| Fact | Evidence |
|---|---|
| Embedding D = 16 x width (mean + max pooling of 8 x width channels); centre loss is the squared distance summed over D, averaged over the batch | `model.py:44,51-53,77` |
| dual_residual input is 5 x 64 x 512 (5 channels, 128 rows / time_pool 2, 512 bins); stored arrays are float16 `[n,2,128,512]`, `[n,2,512]`, `[n,128,512]` | `data.py:44`, `train.py:25`, `b2_dataset.py:344,350` |
| One AdamW group over model + centres; no gradient clipping; OneCycleLR stepped per optimizer step with `total_steps = epochs x ceil(N/batch)` | `train.py:248-251,275-278`; `b2_stream.py:453-457,487-490` |
| Loss = CE + `center_loss_weight` x centre + `plan_loss_weight` x BCE(aux head) | `train.py:269-274`; `b2_stream.py:481-486` |
| Checkpoint = best val-select macro-F1, strict `>`, val-select inference each epoch with batch 32; saved file holds weights, config, history, reference only | `train.py:281-292,313-321`; `b2_stream.py:495-506` |
| Seed drives init (`torch.manual_seed`) and one `Generator` for order, augmentation, plan shift; one seed per `b2_experiment` invocation | `train.py:237,252`; `b2_stream.py:448`; `b2_experiment.py:65,101` |
| Plan shift: Bernoulli per sample per batch, continuous U(-max, +max), full re-preprocessing of the selected rows | `train.py:185-207` |
| The runner fits, then infers the test role, per view, in the same call; `--device` default `cpu`; no train-only flag | `b2_experiment.py:479-499,766-775` |
| Mahalanobis from train embeddings; alarm threshold from clean val-calib; rejection thresholds from val-calib | `b2_experiment.py:495,510,516-518,535` |
| `DEFAULT_WINDOW_SHARDS = 4`; whole shards are permuted only if `n_shards > window_shards`; steps per epoch asserted | `b2_stream.py:67,465,493` |
| Generators default to 8 groups per shard; train / val-select / val-calib / test = 1500 / 150 / 150 / 500 groups, 8 labels each | `b2_dataset.py:39`; `b2_protocol.py:34` |
| LOKO harness default seeds (0, 1, 2); smoke caps epochs <= 2, width <= 8, batch <= 32 | `b2_loko.py:81,170-171` |
| No autocast, GradScaler, `DataLoader`, workers, `cudnn.deterministic` anywhere in `src/` or `scripts/` (checked again by the tests) | `git grep` at `755b474`; `test_repository_facts_cited_as_engineering_only_still_hold` |
| Stale text: `P20:135-136` says K17b plan shift is "not implemented yet", but `train.py:185-207` implements it and `b2_feat.json:24-25` enables it | read, not edited |

Not verified here: behaviour on a GPU, `numpy.load` throughput on the target host, anything about real B2 data (none exists).

## 5. Measured and analytic footprint

Command (run once, 18 configurations, about 2 min, all `ok`):

```
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 CUDA_VISIBLE_DEVICES= PYTHONHASHSEED=0 \
  python scripts/b2_training_footprint.py --out runs/footprint/b2_training_footprint.json --time-cap-s 120 --total-cap-s 1500 --warm-steps 2 --threads 2
```

Environment (measured): 4 vCPU Intel Xeon @ 2.10 GHz, 16 GiB RAM, Python 3.13.17, torch 2.14.1 (build string `2.14.1+cu130`, run on CPU with CUDA hidden), numpy 2.5.4. The kernel allowed the peak-RSS reset, so
step-only peaks are real (`VmHWM` after `clear_refs`). **Load average rose from 1.1 to 3.3 during the run (other agents were working), so wall times are noisy** (a
width-8 `co` step came out slower than the larger `dual_residual` step); the memory columns are the reliable ones. The step is a synthetic random batch of the real input shape: forward, loss
(CE + 0.005 centre + 1.0 BCE), backward, AdamW, mirror/roll augmentation; it excludes data loading and preprocessing. Basis per column: parameters, saved activations, VRAM = **analytic**;
baseline, step peaks, times = **measured on this CPU**. The full per-view table (18 rows) is in the JSON evidence block.

| dual_residual | Width | Batch | Params | D | Saved activations MiB (analytic) | **GPU VRAM MiB: analytic estimate, not measured; needs the authorized GPU probe** (low - high) | CPU baseline MiB | Cold step peak over baseline MiB | Warm step peak over baseline MiB | Warm samples/s (noisy) |
|---|---|---|---|---|---|---|---|---|---|---|
| | 8 | 8 | 79,377 | 128 | 53.5 | 59.7 - 113.3 | 697.3 | 131.2 | 148.3 | 59.1 |
| | 8 | 32 | 79,377 | 128 | 214.0 | 235.3 - 449.3 | 712.4 | 428.3 | 429.5 | 50.8 |
| | 16 | 8 | 311,705 | 256 | 107.0 | 116.8 - 223.8 | 698.3 | 230.7 | 247.6 | 29.2 |
| | 16 | 32 | 311,705 | 256 | 428.1 | 452.9 - 881.0 | 713.2 | 632.7 | 689.7 | 25.6 |
| | 32 | 8 | 1,235,241 | 512 | 214.1 | 238.0 - 452.0 | 701.7 | 377.1 | 405.1 | 11.1 |
| | 32 | 32 | 1,235,241 | 512 | 856.2 | 895.1 - 1751.3 | 716.8 | 1161.7 | 1170.9 | 8.0 |

- Parameters (model only): co 78,777 / 310,505 / 1,232,841, dual 79,177 / 311,305 / 1,234,441, dual_residual 79,377 / 311,705 / 1,235,241 at widths 8 / 16 / 32. P6's "about 310,000" is the width-16 `co` count. With the 8 x D centre-loss parameters the optimizer holds 80,401 / 313,753 / 1,239,337.
- fp32 weights + gradients + AdamW state + BatchNorm buffers: 1.23 / 4.79 / 18.92 MiB. Activations dominate everything; the checkpoint weights are 0.31 / 1.19 / 4.72 MiB.
- VRAM bounds: lower = static state + input batch + autograd-saved activations (tallied on the real graph); upper adds activation gradients (at most the saved bytes). Excluded: CUDA context, cuDNN/cuBLAS workspaces, allocator fragmentation, mixed precision. The largest capped configuration is 1.71 GiB at the upper bound.
- Host RAM: baseline about 0.7 GiB (imports plus first-use kernels) + step peak (up to 1.13 GiB at width 32 / batch 32) + a 128 MiB window gives about 2 GiB for one fit; the 16 GiB planning figure is not binding. This is a step measurement plus window arithmetic, not a full-run measurement.
- `co` and `dual` rows differ from `dual_residual` by under 1 % in parameters and by at most about 100 MiB in step peak, which is within the noise of this run (see JSON).

Streaming window (analytic, repository constants; `window_shards` x shard). The build peak is raw shards + the per-shard float32 tensors + their
`torch.cat` result (two float32 copies coexist; measured 159.7 MiB above the resident raw shards for a 4 x 32-observation `dual_residual` window,
twice the 80 MiB single copy):

| Layout | Obs / shard | Raw float16 / shard | Float32 inputs / shard | Window steady (inputs + plan-shift copy) | Window build peak | Groups / window | Shards / windows per epoch (12,000 train obs) |
|---|---|---|---|---|---|---|---|
| 4 groups, 1 shard | 32 | 12.06 MiB | 20.0 MiB | 32 MiB | 52.1 MiB | 4 | 375 / 375 |
| **4 groups, 4 shards** | 32 | 12.06 MiB | 20.0 MiB | **128 MiB** | 208.3 MiB | **16** | 375 / 94 |
| 8 groups, 4 shards (generator default) | 64 | 24.12 MiB | 40.0 MiB | 256 MiB | 416.5 MiB | 32 | 188 / 47 |

Per epoch the training role is 4.74 GB raw (9.49 GB with the double read of P24 section 2) plus 0.95 GB for the val-select pass. A window that holds the whole train role (uniform shuffle) would need 12.6 GB (7.9 GB float32 inputs + 4.7 GB plan-shift copy).

## 6. Sample passes and wall-clock bounds (ASSUMED unless stated)

| Quantity | Value | Basis |
|---|---|---|
| Train observations | 12,000 (1,500 groups x 8; 1,500 per class) | analytic |
| Passes per fit / nine fits | 360,000 / 3,240,000 (+ 324,000 val-select forward passes) | assumed epochs 30, 3 views x 3 seeds |
| Optimizer steps per fit | 11,250 (batch 32) / 45,000 (batch 8) | assumed epochs |
| GPU throughput band | 200-1,000 samples/s -> 0.9-4.5 h pure compute (0.1-0.5 h per fit) | **assumed**, stated for width 8, not measured on any GPU |
| Synchronous loader at E1 rates | 78 s/epoch (34 s read estimate, P24 section 2, + 12,000 / 270 obs/s preprocessing, `b2_streaming_memory.md:48-49`) = 39 min per fit = 5.9 h for nine | assumed; E1 rates came from a different, loaded CPU |
| Compute plus un-overlapped loader | 6.8-10.4 h against the 6 GPU-h reservation (about 7.9-11.5 h with the omitted val-select and K17b terms) | assumed; reservation may be low by up to about 1.7x (about 1.9x with those terms) |
| CPU-only fallback, compute only | 1.97 h (width 8), 3.91 h (width 16), 12.5 h (width 32) per fit | measured warm rate (dual_residual, batch 32, noisy) x assumed 30 epochs |

The 200-1,000 samples/s band says nothing about the CPU timings above and the CPU timings say nothing about it.

## 7. Not decided here

- Approval of this proposal; K18, K17d, OBS-CANCEL/2; DR-04 generation, DR-05 GPU training, DR-06 LOKO. All gates are unchanged.
- GPU model, VRAM ceiling, host, the bounded throughput/VRAM probe and its caps; GPU-hour / wall / disk ceilings (the 6 GPU-h is an E5 planning figure).
- The LOKO training recipe (same or reduced), the LOKO dispatcher and cross-seed aggregation.
- The cross-seed reporting rule (P6 averages; P18 keeps seed uncertainty separate), the epoch-sizing tolerance and candidate list (R4), and which P18 section 8 ablation names the three views stand for.
- Whether the observation-only train-time diagnostics (centre/CE ratio) are kept: they are already implemented in `src/geoml/train.py` and `b2_stream.py`
  unconditionally (there is no `TrainConfig` switch, because a new field would break loading of historical checkpoints), so R3 only asks whether to
  keep them; removing them is a further `src/geoml` edit that changes the source hashes again and must happen before the production source lock.

## 8. Reproduce and verify

```
python -m pytest -q -p no:cacheprovider tests/test_b2_training_footprint.py      # 73 passed in about 12 s (this checkout)
python scripts/b2_training_footprint.py --out runs/footprint/analytic.json --no-measure --views dual_residual --widths 8 16 32 --batches 8 32
```

The tests cover parameter counts against torch and an independent closed form, `D = 16 x width`, the D/2 ratio, byte accounting against a real AdamW step, input bytes against the real
`preprocess_dual`, strict JSON, every cap, refusal to overwrite, a basis label on every number (and a negative test that catches mislabelling), and that the claims in the proposal file still match
the repository (defaults, pilot config, LOKO seeds, torch's OneCycleLR defaults, absence of clipping / AMP / snapshots). A torch upgrade that changes a scheduler default will fail
`test_defaults_quoted_in_the_proposal_are_the_real_repository_values` on purpose: the production lock must pin torch.
