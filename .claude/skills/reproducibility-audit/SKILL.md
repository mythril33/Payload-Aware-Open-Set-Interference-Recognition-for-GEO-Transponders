---
name: reproducibility-audit
description: Verify that a claimed result traces to configuration, data fingerprint, code revision, command and output before it is documented or pushed.
---

# Reproducibility audit

For each result to be recorded in `docs/results/`:

1. Identify `protocol`, `data_fingerprint`, `experiment_fingerprint`, `source.revision` in the
   results JSON; confirm `git rev-parse HEAD` matches or the diff is explained.
2. Re-run the exact reproduction command from the result's Markdown with `--reuse`; artifacts must
   verify (no "incompatible"/"changed" errors) and reports must be byte-identical.
3. Check roles: train/val-select/val-calib/test group IDs disjoint and inside
   `geosim.b2_protocol.ROLE_STARTS` ranges; thresholds fitted on val-calib known samples only.
4. Check every rate has `n_samples`, `n_scenarios`, positive class; missing metrics are `null`.
5. Record runtime, peak memory, artifact size and the exact command in the Markdown summary, labelled
   as pilot when group counts are below the frozen protocol counts.
