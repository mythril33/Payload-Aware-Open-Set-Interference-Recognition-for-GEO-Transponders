# C2 comparison table — B2-C2-ablation/1

Metric: `near_fpr95` (pooled near-family unknown-positive FPR at 95 % TPR; known test events are the negatives); lower is better; contrast = richer − baseline, so a negative value favours the richer arm.
Primary scorer: NOT DESIGNATED (requires explicit researcher approval before any final test read); all three scorers are always reported.
Scope: NO EXPERIMENT RUN — template

| Contrast | Question | Isolates | Scorer | seed 0 | seed 1 | seed 2 | mean Δ (descriptive) | 95 % CI of mean (groups only) | n groups | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `H1_dual_vs_co` | H1 (primary): `dual` − `co` | cross-pol spectrum and its operator-plan mask channel (the canonical dual view carries both), canonical recipe in both arms | msp | — | — | — | — | — | — | **NOT RUN** |
| `H1_dual_vs_co` | H1 (primary): `dual` − `co` | cross-pol spectrum and its operator-plan mask channel (the canonical dual view carries both), canonical recipe in both arms | energy | — | — | — | — | — | — | **NOT RUN** |
| `H1_dual_vs_co` | H1 (primary): `dual` − `co` | cross-pol spectrum and its operator-plan mask channel (the canonical dual view carries both), canonical recipe in both arms | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `H2_residual_vs_dual` | H2 (primary): `dual_residual` − `dual` | observed cancellation residual channel (itself plan-dependent), canonical recipe | msp | — | — | — | — | — | — | **NOT RUN** |
| `H2_residual_vs_dual` | H2 (primary): `dual_residual` − `dual` | observed cancellation residual channel (itself plan-dependent), canonical recipe | energy | — | — | — | — | — | — | **NOT RUN** |
| `H2_residual_vs_dual` | H2 (primary): `dual_residual` − `dual` | observed cancellation residual channel (itself plan-dependent), canonical recipe | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_dual` | H3 (primary): `dual_planmask` − `dual_noplan` | operator-plan mask channels only; identical spectra, level reference, objective, budget | msp | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_dual` | H3 (primary): `dual_planmask` − `dual_noplan` | operator-plan mask channels only; identical spectra, level reference, objective, budget | energy | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_dual` | H3 (primary): `dual_planmask` − `dual_noplan` | operator-plan mask channels only; identical spectra, level reference, objective, budget | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_co` | H3 (secondary): `co_planmask` − `co_noplan` | operator-plan mask channel only, co-pol | msp | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_co` | H3 (secondary): `co_planmask` − `co_noplan` | operator-plan mask channel only, co-pol | energy | — | — | — | — | — | — | **NOT RUN** |
| `H3_planmask_vs_noplan_co` | H3 (secondary): `co_planmask` − `co_noplan` | operator-plan mask channel only, co-pol | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `H1_dual_vs_co_noplan` | H1 (secondary): `dual_noplan` − `co_noplan` | cross-pol channel when no plan information exists in either arm | msp | — | — | — | — | — | — | **NOT RUN** |
| `H1_dual_vs_co_noplan` | H1 (secondary): `dual_noplan` − `co_noplan` | cross-pol channel when no plan information exists in either arm | energy | — | — | — | — | — | — | **NOT RUN** |
| `H1_dual_vs_co_noplan` | H1 (secondary): `dual_noplan` − `co_noplan` | cross-pol channel when no plan information exists in either arm | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `D1_canonical_vs_matched_planmask` | decomposition (descriptive): `dual` − `dual_planmask` | plan-referenced level + plan-consistency target + plan shift (canonical recipe) versus the matched recipe | msp | — | — | — | — | — | — | **NOT RUN** |
| `D1_canonical_vs_matched_planmask` | decomposition (descriptive): `dual` − `dual_planmask` | plan-referenced level + plan-consistency target + plan shift (canonical recipe) versus the matched recipe | energy | — | — | — | — | — | — | **NOT RUN** |
| `D1_canonical_vs_matched_planmask` | decomposition (descriptive): `dual` − `dual_planmask` | plan-referenced level + plan-consistency target + plan shift (canonical recipe) versus the matched recipe | mahalanobis | — | — | — | — | — | — | **NOT RUN** |
| `D2_canonical_vs_noplan` | decomposition (descriptive): `dual` − `dual_noplan` | everything the canonical recipe derives from the plan (masks, per-sample carrier-referenced level, plan-consistency target, plan shift) versus no plan access and one global plan-free reference; upper-bounds the value of plan access | msp | — | — | — | — | — | — | **NOT RUN** |
| `D2_canonical_vs_noplan` | decomposition (descriptive): `dual` − `dual_noplan` | everything the canonical recipe derives from the plan (masks, per-sample carrier-referenced level, plan-consistency target, plan shift) versus no plan access and one global plan-free reference; upper-bounds the value of plan access | energy | — | — | — | — | — | — | **NOT RUN** |
| `D2_canonical_vs_noplan` | decomposition (descriptive): `dual` − `dual_noplan` | everything the canonical recipe derives from the plan (masks, per-sample carrier-referenced level, plan-consistency target, plan shift) versus no plan access and one global plan-free reference; upper-bounds the value of plan access | mahalanobis | — | — | — | — | — | — | **NOT RUN** |

No cell of this table is a research conclusion unless its scope line says a production-scale authorized run produced it.
Bounded fixtures (two scenario groups per role) establish functional and arithmetic correctness only.
