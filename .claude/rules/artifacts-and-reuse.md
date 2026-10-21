---
description: Data, checkpoint and calibrator contracts
---

# Artifacts and reuse

- Generated data (`data/`), runs (`runs/`), checkpoints and virtual environments
  stay outside Git. Commit configs, commands, tests and small result summaries.
- Every artifact binds its request (config, source hashes, roles, groups) into a
  fingerprint; readers verify checksums before use. Never relax a validator to
  make stale data load; regenerate in a fresh directory instead.
- Reuse of checkpoints, Mahalanobis scorers and rejection calibrators requires
  provenance equality (`expected_config`, `expected_provenance`).
- Adding an array to an artifact stage means a new stage/protocol name; the old
  request layout must still verify bit for bit (see `B2-base/1` vs `B2-feat/1`).
