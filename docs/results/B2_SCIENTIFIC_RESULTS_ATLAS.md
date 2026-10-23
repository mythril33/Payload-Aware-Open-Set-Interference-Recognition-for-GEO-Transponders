# B2 scientific results atlas — E5

Date:2026-10-23. **BOUNDED_PILOT / ENGINEERING_VALIDATION; benchmark_complete=false.**
This atlas reports existing simulated observations and bounded experiments, not field measurements or
a completed B2 benchmark. No full data generation, GPU training or LOKO sweep was performed.
The [context ledger](../engineering/B2_E5_CONTEXT_LEDGER.md) establishes actual main/CI state and
the [fresh independent review](../research/b2_e5_unified_scientific_review.md) records findings and limits.

## Regenerate and verify

```bash
python scripts/plot_b2_scientific_results.py
python -m pytest -q tests/test_b2_scientific_figures.py
```

Run from the repository with `.[dev]` installed. Exact rendering environment:
Python3.12.14, NumPy2.5.4, SciPy1.18.1, Matplotlib3.11.2, Pillow13.0.0;
Agg, DejaVu Sans, fixed SVG hash salt, no rendering timestamps. In a read-only home,
set `MPLCONFIGDIR=/tmp/b2-e5-mpl XDG_CACHE_HOME=/tmp/b2-e5-cache`.
The [manifest](b2_figure_manifest.json) records per-figure source path/SHA256, dataset identity, stage,
role, scene/group counts, units, displayed values, model status, package versions, output hashes and
regeneration command. PNG is300dpi; SVG/PDF are vector exports. Source JSON is strict and hash-locked by
[b2_figure_sources.json](b2_figure_sources.json); modified inputs fail before rendering. Refreshing a source
lock requires explicit evidence review, never automatic acceptance of arbitrary changed data.

Representative tests regenerate A2/B1/C1 twice, check byte-identical PNG/SVG/PDF in the same environment,
300dpi, signatures, source tampering, strict JSON, direct metric arithmetic, population separation and
closed gates. Cross-version font/render byte equality is not promised. On other versions compare numeric
values/denominators first, then deliberately rebaseline visual/output hashes after review. Normal plot
regeneration needs no torch, XGBoost, dataset, checkpoint or network, and calls no simulation/training.

## Physical source extraction

[b2_physical_figure_data.json](b2_physical_figure_data.json) is a small derived display summary of the
already-existing verified `data/b2-readiness-known` artifact (`dcffb264...`, P20 B2-feat/1/obs-cancel/1).
It is deliberately separate from both E4 fixtures. The selection rule is lowest test scenario ID3200000,
clean and CuC, before examining outputs. Only two observations/one group are displayed. Shard metadata,
arrays and calibration are validated by the existing artifact reader before extraction; original request,
artifact/calibration/shard/JSONL paths and SHA256 are retained. Raw data and checkpoints remain outside Git.

```bash
python scripts/plot_b2_scientific_results.py --extract-physical data/b2-readiness-known
```

The summary stores16×128 tiles per polarization/scene, produced by linear-power means over8snapshots×4bins,
plus512-bin time-averaged PSD/residual curves and unmodified operator masks. It is a display/experiment
summary, not reusable model data. No interpolation or simulator rerun. The FFT bin-centred extent is
−48.09375…47.90625MHz; snapshot-cell extent−0.005…1.275s. Snapshot time is the observation schedule,
not1.28s of contiguous IQ. Masks use a separate relative-dB axis from PSD dB(power/Hz).
Independent review checked all8192tile values plus curves/masks against the existing shard.

## Figure inventory

Every link below is a PNG; the identical basename also has `.svg` and `.pdf` in `docs/figures/b2/`.
All22figures/66exports are actually generated. Source hash/precise counts are in the manifest.

| Figure | Content and denominator |
|---|---|
| [A1](../figures/b2/A1_physical_spectrograms.png) | clean/CuC co/cross spectrograms,2scenes/1group; common power scale |
| [A2](../figures/b2/A2_psd_plan_residual.png) | same scenes: co/cross PSD, co/cross belief masks, observed post-cancellation residual |
| [A3](../figures/b2/A3_cancellation_by_class.png) |64scenes/8groups/fourroles,8scenes/class;37active-carrier cores/class |
| [A4](../figures/b2/A4_npr_amplifiers.png) | standalone notched-noise NPR versus IBO, all6available amplifier families, one waveform seed |
| [A5](../figures/b2/A5_asi_cuc_observability.png) | separate ASI120groups and CuC24groups×6levels; truth-labelled offline paired-twin diagnostic |
| [B1](../figures/b2/B1_cancellation_displacement.png) | core cancellation-depth displacement, both modes, known19invocations,2groups/cell |
| [B2](../figures/b2/B2_residual_displacement.png) | full96MHz-band residual-power displacement, both modes; same populations asB1 |
| [B3](../figures/b2/B3_edsc_input_score.png) | recomputed EDSC score displacement; no E4 baseline fitting |
| [B4](../figures/b2/B4_cfar_input_sensitivity.png) | planned/blind CA-CFAR: maximum per-statistic changed-scene count, not union cardinality |
| [B5](../figures/b2/B5_xgboost_feature_displacement.png) | number of26expert feature dimensions changed anywhere in each invocation |
| [B6](../figures/b2/B6_unknown_score_displacement.png) | MSP/energy/Mahalanobis score deltas of dual_residual stand-in, independent native scales |
| [B7](../figures/b2/B7_mask_receiver_model_input_effect.png) | max absolute logit displacement by view/mode; output response to changed inputs |
| [B8](../figures/b2/B8_replay_parity.png) | all25invocations,90/90exact checks; known/matched labels separate |
| [B9](../figures/b2/B9_matched_receiver_displacement.png) | matched6invocations only; depth/power displacement separate from known population |
| [C1](../figures/b2/C1_binary_baselines.png) | EDSC/plannedCFAR/blindCFAR/XGBoost binary alarms,16test scenes/2groups,2/class |
| [C2](../figures/b2/C2_neural_open_set.png) | neural three views×three scorers; AUROC/AP/OSCR in separate panels;16known+6nearunknown |
| [C3](../figures/b2/C3_xgboost_multiclass_confusion.png) | stored eight-class XGBoost count matrix,16test scenes/2groups, no rejection filter |
| [C4](../figures/b2/C4_observed_dev_raw_confusion.png) | raw-prediction confusion matrices, separate P21b observed-dev stage,8scenes/1group |
| [C5](../figures/b2/C5_streaming_real.png) | real-artifact streaming/legacy memory+runtime; fourroles×16scenes/2groups; fit train only |
| [C6](../figures/b2/C6_streaming_layout.png) | synthetic layout/random spectra/fake canceller; fourroles×384scenes/48groups; fit train only |
| [C7](../figures/b2/C7_xgboost_open_set.png) | multiclass MSP rejection AUROC/AP/OSCR, family and near-pool rows; overlapping rows labelled |
| [C8](../figures/b2/C8_binary_unknown_rankings.png) | binary anomaly AUROC/AP against all known including interference; no OSCR |

## Measured physical findings

The older64-observation P20 diagnostic ([source](b2_feat_cancellation_check.json)) measures mean active-carrier
core depth12.78dB for cross_pol through16.47dB for clean. These are averages over active carrier cores,
not the registered full-band ratio. Its paired8-group CuC median victim-band PSD contrast rises
0.986→6.461dB after cancellation,8/8pairs improve. Truth supplies the victim band only to this labelled
offline diagnostic, never to the canceller/model. A3 includes four roles only for physical engineering
inspection, without fitting, calibration or a test-performance population claim.

NPR source is a standalone amplifier test, not the full IMUX/TWTA/OMUX B2 chain. DVB-S2 nonlinear NPR's
10–14dB IBO slope is1.248dB/dB. OpenDPD APA/DPA are fitted solid-state PA models, not TWTAs; hollow squares
mark nonzero input amplitude beyond measured support. They are not validated PA extrapolation.
The low-drive dvbs2_lin downturn is the documented digitized transfer/phase-step artifact, not a discovered
device effect. No curve is silently interpolated or assigned confidence limits.

ASI PSD-level C/I and CuC total-plan C/I are incommensurate physical definitions and occupy separate panels.
At20dB total-plan C/I, CuC median PSD contrast is0.373dB; at30dB it is0.041dB. ASI in-plan evidence is
much weaker than out-of-plan spill. Paired oracle twins help explain observability; these differences are
not receiver detector scores, RF-origin identification or model accuracy.

## Unified E4 meaning and measured findings

Only [the unified25-case source](b2_a5_dual_pol_pilot.json) supplies B1–B9.
[The separate9-case report](b2_a5_postmerge_partial_pilot.json) remains unchanged and is not numerically
combined. Fingerprints/source SHA256 and detailed counts are in the context ledger and manifest.
The unified25calls are100selected scene-slots=90applied+10not-applicable,154cancellations,
64receiver recomputations and870scored condition/view evaluations. They reuse only8distinct physical
scenes across4scenario IDs (2known test groups and2matched groups). They are not90independent scenes.
Grey cells in heatmaps are unregistered configurations (`none` only has both scope), not measured zeros.

Original means stored observations and masks. MASK_ONLY changes belief masks and keeps stored residual;
RECEIVER_CONSISTENT recomputes the residual with obs-cancel/1 under the corrupted co belief. Co/cross/both
refer to operator-plan descriptors. Cross-only causes no co cancellation recomputation; on this exact
same-machine pilot the stored/replayed residuals also agree. A tolerated replay would require weaker
equality wording. No physical carrier or IQ changes under the belief intervention.

Known co_only receiver-consistent core-depth displacements are−8.191dB shift_plus,−8.007dB shift_minus,
−6.160dB drop_one and−12.956dB stale_plan. Corresponding full-band residual-power increases are
5.535/5.533/6.950/9.256dB. MASK_ONLY retains residual power exactly; cross_only remains unchanged.
These point means condition on two groups, original-mask core bins and the frozen receiver. They support
the physical distinction between mask changes and receiver recomputation, not population robustness.
Shared color limits are used for comparable mode/depth/EDSC panels. Full-band power and original-core
depth remain distinct definitions; their displacements need not be equal and opposite.

E4's EDSC/CFAR/XGBoost evidence is input/statistic recomputation only. CFAR counts are the maximum of
changed counts for its two input statistics; they are not the union of affected scenes. XGBoost magnitudes
and per-feature directions are absent from this summary, so B5 reports counts only. Neural preprocessed
tensor differences are not preserved; B7 displays logits, explicitly an output displacement. Masks and
residual changes are evidenced by design/diagnostics; no fabricated tensor norms are supplied.
K17b mask-shift augmentation also confounds MASK_ONLY versus receiver-consistent shift exposure.

The three-epoch neural weights are chance-level stand-ins on16training observations. Zero argmax changes
or small logits demonstrate no robustness; all counterfactual agreement is against original labels, not
conventional accuracy. E4 has no unknown-family test population and supplies no AUROC/OSCR. Its90exact
parity checks prove same-machine stored/replay consistency only. Historical raw invocation/state/NPZ files
are unavailable locally; the fresh audit checks committed summaries and baseline source identity, while
historical raw verification remains attributed to its preserved review. Raw IQ is transient/unpersisted.

## ML metrics and scientific limits

C1 uses one verified E3b fixture and common clean-only calibration rule for its four binary methods.
Positive binary event means non-clean; clean's column is the alarm rate among clean. EDSC/CFAR have no
eight-class predictions/OSCR. XGBoost's binary1−P(clean), its multiclass argmax and its classifier
unknown score1−max(P) are different tasks. These are never collapsed into one ranking.

C2 is a separate canonical neural pilot; C7/C8 are the E3b fixture. They are not pooled or used to claim
cross-pilot superiority. Unknown-positive AUROC/AP include all known test scenes as negative, including
known interference. Near pool has6unknown/16known, AP prevalence6/22; each unknown-family row has2/16,
prevalence2/18. CID is benign and excluded; wideband noise is separate. OSCR's known denominator remains
all16known, and correct-classification rate is distinct from binary alarm sensitivity. Neural stand-ins
have12.5%known-test accuracy; bounded XGBoost has6/16correct in its own fixture, not evidence of an advantage
on a shared independent production test. C3 uses the committed audited count matrix; C4 actually
recomputes matrices from raw prediction records and is explicitly P21b, not canonical P20.

The synthetic48-group E1 layout measurement reports peak RSS3005MiB legacy versus1040MiB window1 and
1230MiB window4; total timings39.54/24.62/26.44s. It contains random spectra/fake cancellation and is solely
engineering evidence. C5 is a different real-artifact measurement. Both are single runs including import
baseline and four-role verification/loading, with fit/inference on train only. They do not establish
GPU throughput, full-scale memory bounds or scientific model quality.

No uncertainty is drawn. Some source JSON includes group bootstraps, but two-group conditional intervals
are unsuitable for broad scientific confidence: scorer/threshold fixed; training, calibration, simulator
and field uncertainty absent. No new interval or seed variability is invented. Missing unavailable
metrics remain null/explicitly scoped. Two clean calibration samples cannot validate nominal population
Pfa5%. Publication-quality layout and reproducibility do not turn bounded pilot values into publishable
recognition claims. A production-scale claim requires the explicit decisions and resource validation in
[the execution plan](../plan/B2_E5_PRODUCTION_EXECUTION_PLAN.md).
