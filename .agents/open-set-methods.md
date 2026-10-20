# Open-set methods agent

Own only the assigned scoring/calibration/metric modules and their tests. Prefer
NumPy/SciPy for post-processing; reuse logits and embeddings from the existing
model. Agree on APIs before editing.

All unknown scores use larger = more unknown-like. Use numerically stable
formulas. Fit Mahalanobis means/covariance on training embeddings only, with
explicit regularization and serializable provenance. Fit rejection thresholds
on separate known calibration observations. Final unknowns never tune a model,
score hyperparameter or threshold.

Test hand-computable cases, ties, extremes, malformed inputs, score direction,
serialization and regularization when features outnumber observations. For ROC,
PR and OSCR, state positive populations and tie handling. Do not add a dependency
when existing NumPy/SciPy suffices. Report APIs, tests and scientific limits.
