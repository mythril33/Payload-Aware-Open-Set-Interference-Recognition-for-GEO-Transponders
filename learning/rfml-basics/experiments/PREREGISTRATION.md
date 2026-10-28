# Pre-registered analysis plan — multi-seed campaign

Written 2026-10-28, **before** the campaign was run. The campaign exists to
replace the single-seed full-run numbers in `results/` with multi-seed
estimates, and to test the four directional hypotheses below. Success criteria
are fixed here; the campaign report may not move them after the fact.

## Design

- Code: `rfml/experiments.py` at the commit recorded in the campaign output
  (`provenance.git_commit`). Scale preset: `full` (40/10/10 known devices per
  class for train/val/test, 20/10/10 frames per device, 25 epochs max,
  patience 5, 512 samples per frame).
- Seeds: 0, 1, 2, 3, 4. Each seed redraws devices, frames, noise, and weight
  initialisation through the per-role `SeedSequence` streams. The committed
  single-run lesson results used seeds 2/3/4 and are superseded by this
  campaign for any comparative statement.
- Stages per seed, run sequentially on CPU (4 threads):
  1. `run_modulation(impaired=True)` — MLP and CNN1D
  2. `run_modulation(impaired=False)` — device-impairment ablation
  3. `run_fingerprint(impaired=True)` and `run_fingerprint(impaired=False)`
  4. `run_open_set(xi=10, lam=0.1, target_known_accept=0.95)` — variants
     CE+MSP, CE+distance, Objectosphere+MSP
- Everything is synthetic data from `rfml/signals.py`. No field data.

## Hypotheses and success criteria

Each hypothesis is evaluated on paired per-seed values (same seed, same data
where the comparison allows it). "Supported" requires the difference to have
the predicted sign in **at least 4 of 5 seeds**; we additionally report the
mean difference and its standard deviation across seeds. With n = 5 seeds no
p-value is reported; a sign consistency of 5/5 corresponds to a two-sided
sign-test p of 0.0625, which we state rather than a significance claim.

- **H1 (score geometry):** CE+distance AUROC > CE+MSP AUROC on the unknown
  test classes. (Single-seed pilot: 0.798 vs 0.351.)
- **H2 (outlier exposure):** Objectosphere+MSP unknown-rejection rate at the
  0.95 known-acceptance calibration target > CE+MSP unknown-rejection rate.
  Caveat recorded in advance: the auxiliary outlier 8PAM is similar to the
  unknown 4PAM, so H2 support is optimistic for this pair and says nothing
  about disjoint unknowns.
- **H3 (fingerprint signal source):** fingerprint test accuracy with impaired
  devices > with ideal devices, and the ideal-device accuracy lies within
  3 binomial standard errors of chance (0.10, n = 600 → SE ≈ 0.012).
- **H4 (impairment cost):** CNN1D overall modulation accuracy without
  impairments > with impairments (the ablation isolates what device
  impairments cost the classifier).

Secondary, descriptive only (no pass/fail): MLP train-vs-test accuracy gap
(memorisation), per-SNR curves, closed-set accuracy on accepted known frames,
known-acceptance rates versus the 0.95 calibration target.

## Metrics and reporting rules

- AUROC: positive class = unknown, larger score = more unknown-like
  (Mann-Whitney with ties at 0.5). Rates name their positive class,
  denominator and n, as everywhere in this project.
- Aggregates: per-seed values listed in full, then mean, sample standard
  deviation (ddof = 1), min, max. No seed is dropped for any reason; a failed
  run is reported as failed.
- Frames of one device are correlated; n counts frames, not independent
  samples. Seed-level aggregation is the unit of replication.

## What this campaign cannot show

Synthetic data from our own simplified transmitter model; results do not
transfer to measured RF without separate evidence. The main repository's
GEO/B2 protocol, its frozen artifacts and its gated experiments are not
touched by this campaign.
