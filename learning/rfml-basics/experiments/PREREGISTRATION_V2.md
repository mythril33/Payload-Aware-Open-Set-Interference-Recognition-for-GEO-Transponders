# Pre-registered analysis plan — campaign 2 (scorer bench)

Written 2026-10-28, **before** any campaign-2 run, as an amendment extending
[PREREGISTRATION.md](PREREGISTRATION.md). Campaign 1 is closed; its criteria
and results stand. Campaign 2 answers three follow-up questions raised by
campaign 1's results and limitations:

1. Is the distance score's advantage over MSP a property of the *score
   space* (output vs embedding) or of the separate training runs campaign 1
   used for each variant?
2. Is the Objectosphere gain (H2) driven by the similarity between the 8PAM
   auxiliary outlier and the 4PAM unknown — the confound we recorded in
   advance?
3. Does MSP's below-chance AUROC worsen with SNR, as the confidence
   explanation predicts?

## Design

- Scale `full`, seeds 0–4, CPU, as in campaign 1. New stage
  `run_scorer_bench` (additive code; `run_open_set` and the lessons are not
  modified).
- **One CE model per seed**; five post-hoc scores evaluated on the *same*
  model, so score comparisons are paired at the model level:
  MSP (1 − max softmax), max-logit (−max logit), energy
  (−logsumexp(logits)), Euclidean distance to known-train centroids, and
  Mahalanobis distance with a shared within-class covariance fitted on known
  training embeddings with shrinkage 0.1 toward the scaled identity.
  Larger = more unknown-like for every score.
- **Three Objectosphere arms** (ξ = 10, λ = 0.1, MSP score), identical except
  for the auxiliary outlier pool: full {16PSK, 8PAM}, PSK-only {16PSK},
  PAM-only {8PAM}. Outlier device counts: the single-class arms use the same
  20 devices of that class as the full arm (the pool halves; this is part of
  the manipulation, and we report outlier frame counts per arm).
- Thresholds: for every scorer and arm, on known val-calib frames at 0.95
  target acceptance, exactly as in campaign 1.
- New measurements per variant: AUROC and rejection per unknown class
  (64QAM and 4PAM separately), AUROC per SNR value and for two bands
  (low ≤ 2 dB, high ≥ 10 dB), and the OSCR operating curve (area, and
  correct-classification rate at 10% unknown false-accept).

## Hypotheses and success criteria

Same rule as campaign 1: paired per-seed differences, predicted sign in
**≥ 4 of 5 seeds**; means and sds reported; no p-values at n = 5.

- **H5 (covariance):** Mahalanobis AUROC > Euclidean-distance AUROC on the
  same CE model. Prediction from Lee et al. (2018); a negative result is
  informative (covariance estimation noise at D = 128 with 3,200 training
  frames).
- **H6 (output-space score):** energy AUROC > MSP AUROC on the same model.
  Prediction from the energy-based OOD literature; both may remain below
  0.5, which would strengthen the "output space is the wrong place" reading.
- **H7 (confound test):** rejection of **4PAM** unknowns is higher under the
  PAM-only arm than under the PSK-only arm. If supported, campaign 1's H2
  gain is at least partly similarity transfer, and the pre-registered caveat
  becomes a measured effect. 64QAM rejection under the two arms is reported
  descriptively.
- **H8 (confidence mechanism):** CE+MSP AUROC in the low band (≤ 2 dB) is
  **higher** than in the high band (≥ 10 dB) — i.e. the anti-correlation is
  strongest where the classifier is confident. Band AUROCs condition both
  known and unknown frames on the band.

Descriptive only (no pass/fail): OSCR areas, CCR@FPR=0.1, per-SNR AUROC
curves, max-logit results, per-arm outlier frame counts, closed-set accuracy
on accepted frames.

## Honesty rules

As in campaign 1: no seed dropped, failures recorded in the aggregate,
every rate names its positive class, denominator and n, and the unknown
classes touch nothing before test-time scoring. Σ, centroids and thresholds
use only train (fit) and val-calib (thresholds) roles. Synthetic data only;
nothing transfers to measured RF. These results also do not decide the main
project's primary-scorer question (D-4); they are evidence from a toy
instrument, offered to the researcher, not a decision.
