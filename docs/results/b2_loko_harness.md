# B2 LOKO harness verification — 2026-10-22

Base `main@5a65062`, branch `feature/b2-e2-loko-harness`.
Implementation: [P25](../plan/P25_b2_e2_loko_harness.md).
`benchmark_complete=false`; all researcher and production-compute gates unchanged.

## Evidence

Environment: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, PyTorch
2.14.1+cpu, pytest 9.1.1; CPU execution with OMP/OpenBLAS/MKL threads capped at 2.

Focused command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  python -m pytest -q tests/test_b2_loko.py
```

**9 passed in 47.10 s.** Covers seven-fold/three-seed planning and fingerprints,
clean holdout refusal, remapping and exact input preservation, empty derived
shards/reordered reads/group boundaries, label drift, role leakage and incomplete
groups, execution caps, wrong artifact stages, paired bootstrap/score ties/null
populations, CPU training/scoring/calibration, checkpoint reuse and incompatible
derived-file refusal, plan-only CLI, and a disk writer/validator/streaming-loader
integration smoke with checksum-corruption rejection.

The integration fixtures use **stand-in RF physics and cancellation** with the
real versioned artifact writer, checksums and loader. The in-memory fixture has
two groups/role: 14 retained known samples for training, selection and calibration;
test has 14 known and two held-out samples. The disk fixture has one group/role,
seven known and one held-out test observation, so its CI is null. These fixtures
prove execution and isolation, not physically meaningful recognition quality.

The independent read-only review found two reuse weaknesses, both fixed and
covered by negative tests; re-review found no remaining material blocker. See
[review record](../research/REVIEWER_RED_TEAM.md).

Syntax compilation, `git diff --check`, and explicit preservation checks for
`benchmark_complete=false`, pending K18/K17d/OBS-CANCEL/2 and unauthorized full
generation/GPU/LOKO passed.

Full repository suite actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  python -m pytest -q
```

**978 passed in 1014.36 s (16 min 54 s).** This includes the existing E1
streaming parity, deterministic replay, corruption and subprocess peak-memory
regressions, as well as the nine new LOKO tests. No tests were skipped or failed.
The elapsed time is measured on this environment; it is not a production cost estimate.

## Limitations

- No actual full data generation, GPU training or full 21-fit-per-view sweep.
- No production dispatcher or cross-seed uncertainty aggregation exists yet.
- No RF-quality or generalization claim is inferred from fixture metrics.
- Group bootstrap fixes models/scorers/thresholds. It does not include training
  seed variability, physical-model uncertainty or threshold estimation uncertainty.
- Memory safety is inherited structurally from E1's shard/window reader; this
  slice did not repeat E1's peak-RSS benchmark or measure full-scale resources.
- Existing source and artifact versions are unchanged. K18's two loss conventions
  are still an unresolved researcher decision; the canonical P20 loss is inherited.

Previous remote evidence was independently checked: PR #9 merged E1; GitHub
Actions run `39602354253` succeeded on head `3f484a6`. This does not imply that
new E2 CI has passed; its run must be assessed separately.
