# GEO manuscript: publication tables and figure specifications

Companion to `geo_b2_manuscript.md`, baseline main `6e9ff7f`. These are display definitions, not additional experiments or permission to access data. The manuscript already renders Tables 1–7 and two existing physical figures. Every future recognition measurement below has status **NOT RUN**. Primary scorer: **NOT DESIGNATED**. Optional co-only matched fits: **DEFERRED**. No placeholder confidence interval, invented curve or zero-valued missing result is drawn.

## Common production reporting contract

Use the exact fifteen cells: co, dual, dual_residual, dual_planmask, dual_noplan × seeds 0/1/2. Canonical and H3-dual inventories use the same verified data, source and runtime identity and their separately declared recipes. Fit weights and Mahalanobis state on train only; select on val-select; calibrate known-only on val-calib. All fitted objects, primary designation and canonical→H3-dual order must be frozen before separately authorized final reads. The display package cannot supply the missing authorization or inference reader.

Every metric record retains profile, view, seed, scorer, scenario population, sample count, numerator/denominator when applicable, threshold provenance, exclusions and unavailable reason. Use fractions in machine-readable records, percentage points for FPR differences, dB only for physical power quantities. At publication render at least three meaningful decimals for ranking fractions and counts alongside rates; never add significant figures beyond the retained source value. Scores have their own units and are never rescaled to suggest common calibration.

Use all 500 natural and 150 matched groups for the declared headline. Repeat on the identity-excluded 498/148 groups. For downlink ASI separately show the accepted K17d 500/35/465 grouping; 35/465 is not the exposure exclusion. No outcome-based subgroup removal. Whole-group paired bootstrap resamples are common across compared arms and seeds; intervals condition on fixed trained objects. Report seed 0/1/2 separately, then descriptive mean/min/max/SD without implying a seed-population confidence interval. Do not add a new bootstrap replicate count/seed by invention: retain and record the evaluator's resolved preregistered settings before final evaluation.

## Tables

### T1–T5: populated methods and physical evidence

Manuscript Tables 1–4 define physical assumptions, known labels, populations and contrasts. Table 5 contains only already committed simulation diagnostics. Its cancellation range is the range of class mean active-carrier-core depths, not min/max sample depth, full-band cancellation or a confidence interval. The ASI and CuC runs have different C/I denominators and populations. Validate their exact values against `geo_b2_evidence.json` numeric pointers. No recognition score belongs in Table 5.

### T6: complete fit/performance table — NOT RUN

Expand the manuscript's five-view skeleton into fifteen view/seed rows; do not average seeds first. Minimum columns: view; seed; selected epoch; known accuracy (correct/all known); macro-F1; near-family FPR95 for MSP, energy and Mahalanobis. Put a visible marker next to the researcher-designated scorer only after its pre-test approval is bound. Each metric is currently **NOT RUN**; selected epoch is also NOT RUN, not zero. Repeat the panel for 500 and 498 natural groups; count variants explicitly.

Companion T6a: for every view/seed/scorer, give near-pooled AUROC/AP/OSCR and each near-family row. Known negatives are all 4,000 natural known observations (or the actual retained exposure-excluded population); near positives are 1,500 in the full population. Family AP prevalences differ and must be printed. Wideband noise has a separate equivalence-limited panel; CID has no unknown-positive entry.

Companion T6b: fixed val-calib thresholds with score units; known acceptance accepted/all known; accuracy among accepted known correct-accepted/accepted-known; unknown rejection rejected/all unknown; clean alarm alarmed-clean/all clean; per-known-class event detection non-clean alarm/class count. Clean alarm is distinct from rejecting unknowns and from multiclass argmax. Include numerator/denominator and conditional interval. Calibration target 95% acceptance or 5% clean alarm is a reference annotation, never a measured test value.

### T7: H1–H3 paired contrasts — NOT RUN

Rows H1 dual−co, H2 dual_residual−dual, H3 dual_planmask−dual_noplan. Columns: scorer; seed 0/1/2 FPR95 difference; descriptive seed mean/spread; paired group-bootstrap limits. Use percentage points, richer minus comparator; negative favors richer. The headline endpoint/view and the H1–H3 comparisons are different objects: do not call three contrasts independent confirmatory endpoints. All three scorers appear, with one predeclared primary designation. Intervals exclude training and calibration uncertainty. Keep adverse and uncertain effects; no stars or unregistered significance tests.

### T8: matched ASI/unauthorized mechanism table — NOT RUN

Panels for natural test, level-matched test, and exposure-excluded versions. Matched columns: bin 4–7/7–10/10–13 dB; groups; class; class count; recall; precision; predicted-clean/other-known/pair-class counts; rejected count per scorer; pair correctness over all pair observations and, separately, conditional correctness among accepted observations. Provide unconditional 3×8 confusion and rejection-aware 3×9 confusion; a 2×2 pair submatrix must retain the omitted-prediction denominators beside it.

Stratify the registered missing-carrier/absent-overlap intersections without dropping cases. State matched symbol-rate conditioning, out-of-natural-range targets and absence of matched geometry. Requested input-power matching is not equal post-payload PSD rise. Do not pool natural and matched populations or use natural-bin counts as matched denominators.

### T9: near-family, benign and ambiguity controls — NOT RUN

For downlink ASI: all500/co-missing35/complement465 plus the separately identified exposure sensitivity; show requested and effective C/I labels. For benign CID: accepted-as-clean/all CID, called-CuC/all CID and rejected/all CID. Wideband noise: a separate unknown row, never added to near-family pooling. For CuC: registered total-plan C/I bins 5–15/15–25/25–30 dB with counts. For overdrive: nominal-looking subgroup defined using the predeclared clean val-calib regrowth threshold, and its registered comparator rows. Label simulator-derived strata as analysis metadata, not deployable features.

## Figures

### Existing Figure 1: ASI/CuC visibility — AVAILABLE, SIMULATED DIAGNOSTIC

Reuse `paper/figures/asi_cuc_observability.png` byte-for-byte. Original source `docs/figures/b2/A5_asi_cuc_observability.png`; Figure 1 caption in the manuscript states fixed-link, single-pol, no-phase-noise conditions, separate 120/24-group populations and oracle-twin interpretation. Axes and numeric values must not be relabeled as detection probabilities. No new observation extraction or regeneration is needed.

### Existing Figure 2: cancellation by class — AVAILABLE, SIMULATED DIAGNOSTIC

Reuse `docs/figures/b2/A3_cancellation_by_class.png` byte-for-byte. Caption records 64 observations/eight groups/four roles, eight observations per class and 37 active cores per class. The bars are class means; the graphic supplies no population confidence interval. Prior pilot test exposure is disclosed. Keep reference receiver `obs-cancel/1`; this is not a P21b receiver figure.

### G3: information and role boundary diagram — SPECIFICATION ONLY

Use a two-column vector schematic. Left: two uplinks→uplink coupling→common satellite phase→separate IMUX/TWTA/OMUX paths→downlink coupling→downlink injection→receiver phase/instrument/noise→estimated instrument correction. Right: spectra/masks to canonical views; co-IQ+co-plan to residual; plan-free reference to matched H3 arms; simulator truth ends at a dashed metadata-only reporting box. A lower lane shows train→selection→known calibration→15-cell freeze→separately authorized evaluation. Mark signals, metadata and operator context with distinct line styles, not color alone. Equations and assumptions follow E01–E10; no empirical quantity is implied. No schematic is rendered as a new measured result in this draft.

### G4: near-family rankings and calibrated operating points — NOT RUN

Separate panels per scorer, unknown-positive x=known false-unknown fraction, y=unknown rejection/detection fraction. Curves use grouped ties; include all near unknowns and all known negatives, not clean-only negatives. Distinguish three seeds with line style; all models of a comparison share axes. Mark independently calibrated operating thresholds on each model's own curve, with acceptance/rejection convention stated. Provide per-family curves separately, not an interpolated average of incompatible AP populations. Report AP in the accompanying table; do not draw it as ROC area. Equivalence-limited noise and benign CID are separate displays. Legends retain H1/H2/H3 information regimes.

### G5: paired H1–H3 effect display — NOT RUN

Three horizontal panels, one per question. x=FPR95 difference in percentage points, with a vertical zero line and negative direction labeled “richer arm lower FPR95.” y=scorer; show individual seed estimates as points and the declared paired group-bootstrap intervals with an explicit fixed-state uncertainty label. A distinct symbol may show descriptive seed mean, never a fabricated three-seed confidence interval. Render full/exposure-excluded populations in separate panels or line styles. Do not choose an axis range or only a subset of scorers after seeing a favorable result.

### G6: matched confusion and physical ambiguity — NOT RUN

Confusion panels use raw counts and row-normalized recall with shared scales. Include clean and rejection/other-known destinations so a pair-only plot cannot hide errors. Plot level-bin recall with actual group/sample counts and conditional intervals; use separate natural/matched panels, with the rate-conditioning caveat. For any representative paired spectra, use P22's already recorded selection rule `default_rng([20261021])`, up to three groups per bin, fixed axes/scales and recorded IDs. Never select the cleanest or most separable cases by model outcome. Protected observations are not opened to construct a placeholder in this draft.

## Minimum completion record

The narrow manuscript needs the existing three data stages, fifteen declared fits, known-only calibration/freeze, one authorized ordered evaluation, and offline aligned contrasts/required subgroup reports. No extra fit is needed to populate T6–T9/G4–G6. Optional co controls, full LOKO, C3 transfer, cyclic features and receiver-error sensitivity remain NOT RUN and outside this minimum. If future text claims superiority to classical/feature-based baselines, evaluate those on the same frozen production populations first; historical pilot plots cannot supply that claim. This is a scientific completion list for Results and Discussion, not a new engineering milestone or execution authorization.
