# P20 — B2 observation-based cancellation residual and five-channel model interface

Date: 2026-10-21. Parent protocol: frozen [B2/1](P18_b2_protocol.md) (§1 channel 5, §5 K9, §7a K17b).
Artifact stage: **B2-feat/1** (`known_physical_observations_with_cancellation_residual`). The manifest
still records `benchmark_complete: false`: unknown families, benign CID overlays and the matched ASI
set are later stages.

## 1. Scientific motivation

P18 §6 pre-registers that `carrier_under_carrier` at high C/I is at chance level from the spectrum
alone and is expected to separate only through a cancellation residual or cyclic features (K9).
Commercial monitoring tools find under-carrier interference by cancelling the known carrier. The
residual must be computed from what an operator observes, never from simulator symbols; an oracle
canceller is only a labelled upper bound and is not implemented as a model input.

## 2. What the canceller sees (`geosim.cancellation`)

Inputs: the calibrated co-pol monitor IQ `[n_snap, 4096]` at 96 MHz and the co-pol **operator plan**
(centre frequency, symbol rate, roll-off, MODCOD, nominal relative power of each *planned* carrier).
Nothing else: no activity masks, realized IBO/OBO, XPD, C/I, labels, event parameters or transmitted
symbols. The function signature `cancel_planned_carriers(iq, plan, config)` is tested to accept only
these. Every planned carrier is processed whether or not it was transmitted, because the operator
cannot know that in advance; the residual therefore also carries plan-inconsistency evidence.

**[ASSUMPTION]** The operator plan includes each carrier's MODCOD (modulation and, for APSK, the
code-rate ring ratios). This is standard carrier-plan information but is an assumption about the
monitoring system; a MODCOD-blind variant would need blind modulation classification.

## 3. Algorithm (frozen as `obs-cancel/1`, `configs/cancellation.json`)

Per planned carrier and monitor snapshot:

1. Upsample ×3 to the 288 MHz simulation rate (`scipy.signal.resample_poly`) so that every supported
   symbol rate has an integer samples/symbol (`geosim.waveform.samples_per_symbol`).
2. Mix to baseband at the planned centre frequency; matched filter with a unit-energy time-domain SRRC
   truncated to 10 symbols.
3. Non-data-aided symbol timing with the Oerder–Meyr spectral-line estimator, quantized to the
   288 MHz grid (≤ 1/16 symbol at 36 Mbaud, finer for lower rates).
4. Coarse carrier phase from a 16-point grid over the constellation's symmetry sector (QPSK/16APSK/
   32APSK 90°, 8PSK 45°), chosen by minimum hard-decision error; then three decision-directed
   iterations with a complex least-squares gain per snapshot. The remaining rotational ambiguity is
   absorbed by the gain and does not change the remodulated waveform.
5. Remodulate the decided symbols with the same SRRC, mix back, sum over carriers, decimate to 96 MHz
   and subtract from the observed IQ.
6. Store the Welch PSD (same estimator as the spectra) of the residual after dropping 512 monitor
   samples at each block edge, where unobserved neighbouring symbols leave unavoidable truncation
   residue. Shape `[128, 512]` float16 dB(power/Hz), same grid and scale as channel 1.

Residual power from decision errors, payload nonlinearity (AM/AM, AM/PM, IMUX/OMUX ISI), cross-pol
leakage, phase noise, timing quantization and SRRC truncation remains in the residual. This is
measured, not hidden: it is part of what the model sees.

Observation-derived per-carrier diagnostics (timing, gain, decision SNR) are stored in metadata under
`cancellation.carriers`. They are derived from the same observable inputs and are **not** model
channels in this stage.

## 4. Artifact contract (B2-feat/1)

- Same roles, seeds, plans, paired scenes, calibration method and missing-carrier convention as
  B2-base/1 (P19). Arrays: `spec[N,2,128,512]`, `mask[N,2,512]`, `label`, `seed`, `plan_consistency`
  **plus** `residual[N,128,512]` float16. Raw IQ is not stored (≈ 8 MiB per observation would be
  170 GB for the full benchmark).
- The request carries `cancellation` (frozen settings) and `fifth_channel` (input/exclusion contract);
  readers verify both and the per-record provenance. Records with cancellation metadata are rejected
  in a B2-base/1 artifact and vice versa.
- **Backward compatibility:** the B2-base/1 request layout is unchanged when no canceller is given;
  B2-base/1 artifacts keep their fingerprints and remain readable (tested).
- Cost (pilot, 64 observations, 2 OMP threads, test suite running concurrently for part of the time):
  243.8 s wall, 285.1 s CPU, peak RSS 585 MiB, 24.75 MiB stored (B2-base/1 pilot: 109.6 s, 545 MiB,
  16.49 MiB). The canceller adds roughly 1.3–1.8 s per observation on this CPU. **[ESTIMATE]** for the
  full 2300 groups × 8 variants: ≈ 20–25 core-hours including cancellation.

## 5. Five-channel model interface (`geoml`)

- `preprocess_dual(..., view="dual_residual", residual_db=...)` appends the residual as channel 5,
  referred to the **same co-pol planned-carrier level** as channels 1–2 (so cancellation depth is
  visible relative to the carriers), with the same linear-power time pooling and clipping.
- `SmallResNet(n_classes, width, in_ch, aux_outputs)`: optional independent auxiliary head; `forward`
  still returns known-class logits only, so every historical checkpoint and caller is unchanged.
- `TrainConfig` gains `input_mode="dual_residual"`, `plan_consistency` (BCE head, weight
  `plan_loss_weight`), and `center_loss_weight` (prototype/center loss, Wen et al. 2016 form, centers
  trained with AdamW). Checkpoint selection uses known-class macro-F1 on val-select only; the
  auxiliary head is monitored, not selected on (tested).
- **Pre-registered hyperparameter (K18 candidate, needs researcher confirmation):** P18 §5 fixes the
  center-loss weight "by P6 settings, no search", but P6 gives no value. `configs/b2_feat.json`
  freezes **0.005** before any B2 training, chosen from the literature range (Wen et al. report
  0.003–0.1 depending on the embedding scale) without any search on B2 data. Changing it later
  requires a P18 §10 entry. `plan_loss_weight = 1.0` likewise.

## 6. Experiment runner (`geoml.b2_experiment`, `configs/b2_feat.json`)

Frozen P18 §4 roles: train → weights and Mahalanobis statistics (regularization 0.1); val-select →
checkpoint; val-calib → MSP/energy/Mahalanobis acceptance thresholds at 95 % known acceptance and the
clean alarm threshold at Pfa 5 %, known classes only; test → once. Matched views `co` (2 channels),
`dual` (4) and `dual_residual` (5) share data, seed and budget. Reports: accuracy and per-class
recall with scenario-group bootstrap, macro-F1, confusion, ECE (15 bins), clean false alarm, event
detection, plan-consistency accuracy/recall/precision with positive counts, known acceptance and
accuracy on accepted per method. Unknown metrics are `null` with `n_unknown = 0`. Checkpoints,
scorers and calibrators are bound to data fingerprint, role groups and source hashes; a source edit
invalidates reuse by design.

## 7. Evidence

- Synthetic single-carrier checks (`tests/test_cancellation.py`): at C/N 25 dB the residual reaches
  the noise floor (depth > 20 dB, within 1.5 dB of the floor) for QPSK, 8PSK, 16APSK and 32APSK,
  including a 3.6 Mbaud carrier with a non-integer 26.67 samples/symbol at the monitor rate; a
  −25 dB under-carrier becomes visible (ΔPSD < 0.3 dB before, > 3 dB after); an unplanned carrier is
  untouched; a missing planned carrier does not raise the in-band residual.
- [Pilot physics report](../results/b2_feat_pilot.md) on 64 real B2 observations: mean in-band depth
  12.8–16.5 dB (bounded by the receiver noise floor at low C/N and by the un-tracked LO phase walk within
  a snapshot — ≈ 21–25 dB ceiling at the frozen 150 Hz effective linewidth — at high C/N), out-of-plan
  gap floor unchanged (−0.02…−0.09 dB),
  lower depth for `overdrive` and `cross_pol` (physical), and the paired clean/CuC victim-band ΔPSD
  rising from a median 0.99 dB before to 6.46 dB after cancellation in 8/8 groups.
- Test suite: see DURUM; all historical identities preserved.

## 8. Limitations and open items

- Decision-directed cancellation is deliberately simple: one complex gain per snapshot (no phase
  tracking inside the 42.7 µs block), no fractional timing refinement, no frequency-offset tracking
  (the plan frequency is assumed exact), no equalization of IMUX/OMUX ISI, no handling of unknown
  MODCOD. Without phase noise these limit depth to roughly 35–48 dB; **with the frozen 150 Hz
  effective linewidth the block-constant gain caps depth at ≈ 21–25 dB regardless of C/N**, so for
  C/N above ≈ 20 dB the algorithm, not the receiver noise, bounds the residual (reviewer finding,
  reproduced). A per-segment phase-tracking `obs-cancel/2` would be a separately versioned stage.
- The simulator places symbol timing exactly on the 288 MHz grid and the monitor warm-up is a multiple
  of three samples, so the timing quantization step is never exercised with a fractional offset here;
  real receivers would add that residual. APSK ring start angles in `geosim.waveform.constellation`
  are still **[VERIFY]** against EN 302 307-1; simulator and canceller share the function, so the
  pipeline is self-consistent but not yet standard-checked.
- Channel 5 is estimated from 3072 guarded samples (11 Welch segments) versus 4096 (15 segments) for
  channel 1: same density scaling, slightly higher per-bin variance. Center-loss centers share the
  AdamW weight decay (1e-4) of the network rather than Wen et al.'s separate center update; both are
  frozen conventions of this stage.
- **K17b training-time plan-shift augmentation (15 % of training samples, Δf ~ U(−0.5, +0.5) MHz) is
  not implemented yet.** Models trained with the current `b2_experiment` are therefore not the P18
  main model; the augmentation is the next training-side task.
- The residual of a `cw` on top of a carrier degrades decisions (minimum depth 4.5 dB in the pilot).
  This is a property of the observation, not an error, and will show up in ablation A4.
- EDSC baseline (energy detection after cancellation) and the SCF branch (A4b) are not yet
  implemented; they will reuse this module.
- The pilot learning run (16 training observations, 3 epochs) is execution evidence only:
  12.5 % accuracy (chance) for all views; plan-consistency 100 % with **zero positives** in the pilot
  groups, i.e. uninformative.
