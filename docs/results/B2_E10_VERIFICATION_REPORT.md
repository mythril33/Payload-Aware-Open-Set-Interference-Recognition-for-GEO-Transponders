# B2 E10 — verification report

**Branch:** `fix/b2-e10-scientific-integrity-hardening`.
**Baseline:** `origin/main` `e43987ea8b6a50d0df9b6969e69e80d36d03f182` (PRs #30, #31, #32 merged).
**Exact HEAD of the change set:** `HEAD_PLACEHOLDER` (recorded after the commit; see section 7).
**Scope:** CPU-only verification. No dataset generation, no GPU, no training, no held-out evaluation, no LOKO, no new held-out observation opened.

## 1. Environment

| Item | Value |
|---|---|
| Local interpreter | Python 3.13.17 in a scratch venv under the session scratchpad (not in the repository) |
| Pinned packages (from `scripts/setup_cloud.sh`) | numpy 2.5.4, scipy 1.18.1, pytest 9.1.1, matplotlib 3.11.2, torch 2.14.1 (PyPI build; the CPU index was blocked), xgboost-cpu 3.4.1 |
| Threads | `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2` |
| CI reference | `.github/workflows/b2-readiness-ci.yml` runs on Python 3.12 with `pip install -e ".[dev,ml,xgb]"`. **Local runs used Python 3.13, so they are not an exact reproduction of the CI interpreter.** |
| Editable install | not performed; tests used `PYTHONPATH=src` |

## 2. Commands and results

All commands were run from the repository root with `PYTHONPATH=src` and the scratch venv interpreter.

| # | Command | Scope | Result |
|---|---|---|---|
| T1 | `pytest tests/test_b2_e10_k17d.py tests/test_b2_e10_records.py tests/test_b2_e10_calibration.py tests/test_ml.py tests/test_openset_metrics.py -q` | new E10 tests, plus stage-A metrics and open-set metrics | **103 passed** (after one test-fixture correction, described in section 3) |
| T2 | `pytest tests/test_b2_execution.py -v` | isolated executor, including the calibration and evaluation isolation tests | **42 passed** after two test corrections (section 3) |
| T3 | `pytest tests/test_b2_e9_contract.py tests/test_b2_production_preflight.py -v` | E9 contract and preflight gates | RESULT_T3 |
| T4 | `pytest -q -rs` (full suite, all test files, CI-equivalent flags) | whole repository | FULL_RESULT |
| T5 | `python -m compileall -q src tests scripts` | syntax of every source file | COMPILE_RESULT |
| T6 | `python scripts/b2_e10_k17d_identity.py` | metadata-only K17d derivation over 500 test groups with the audit cross-check | **exit 0**: headline 500, co-feed 35, sensitivity 465, cross-feed 43, total missing 78; `agrees=True`; `observation_reads: 0`, `waveform_synthesis_calls: 0` |

Failures and skips are recorded in section 4.

## 3. Test corrections made during verification (and why each is legitimate)

These were the only edits to existing tests. Each was made because the test encoded the historical linear rule, or because
a refactor removed a name that a monkeypatch relied on. No assertion was weakened to pass.

| Test | Before | After | Reason |
|---|---|---|---|
| `tests/test_b2_execution.py::test_threshold_rule_matches_independent_power_probability_arithmetic` | expected `np.quantile(..., .95)` (linear) | expected `np.quantile(..., .95, method="higher")` | It asserted the historical rule. The approved R10 rule is `higher`, and the change note records the switch. |
| `tests/test_b2_execution.py::test_fixture_evaluation_uses_only_frozen_objects_and_readonly_inputs` | monkeypatched `threshold_at_pfa` | the name is removed from the list; `clean_alarm_threshold` stays | `b2_execution` no longer imports `threshold_at_pfa`, so `monkeypatch.setattr` failed. The guard still applies to the function the calibrate path now calls. |
| `tests/test_b2_e10_calibration.py` (own test, during development) | `TrainConfig()` | `TrainConfig(labels=...)` | `TrainConfig` requires `labels`. |
| `tests/test_b2_e10_calibration.py` (own test, during development) | role-literal check by substring | AST string-constant check | The substring check matched the log sentence "no test source opened". |

## 4. Failures and skips

- **Failures in the final T1 and T2 runs:** none after the corrections in section 3.
- **Failures found during development (before correction):** the four `TrainConfig` errors and the single `B2Source.index`
  error in my own new calibration tests, and the two `test_b2_execution` failures in section 3. All were fixed in the tests or
  in the helper function, not in the approved code.
- **Skips:** SKIPS_PLACEHOLDER

## 5. New negative and regression tests (what each one proves)

| File | Tests | What they prove |
|---|---|---|
| `tests/test_b2_e10_k17d.py` | 38 | Exact 500/35/465 partition; canonical and order-independent output; fingerprints change when identities change; refusal of wrong count, duplicate, out-of-range ID, wrong role or protocol, diagnostic override, malformed or out-of-range drop, `plan_consistency` mismatch, outcome-bearing keys (accuracy, prediction, unknown score), missing fields; audit disagreement (missing group, polarization mismatch, wrong total, duplicate row); the metadata path never reaches `simulate_dual` (patched to fail); the validator module imports nothing from `geoml`, torch, metrics or prediction code |
| `tests/test_b2_e10_records.py` | 8 | The committed identity record declares zero observation reads and zero waveform calls; its counts and fingerprints recompute from its own lists; it agrees with the committed audit; **tampering with one co-feed ID is detected; tampering with one audit polarization is detected**; gate values in the approved protocol are unchanged (`benchmark_complete` false, production false, activation false, full generation/GPU/LOKO `NOT_AUTHORIZED`, production launch `DISABLED`); the contract still refuses every execution action |
| `tests/test_b2_e10_calibration.py` | 33 | Hand-computed higher-quantile values (`arange(100)` gives 95.0, the historical helper gives 94.05); the threshold is an order statistic; monotone in Pfa; ties (strict `>` raises no alarm on equal scores); small samples n = 1, 2, 20; input order independence; refusal of empty, two-dimensional, NaN and infinite scores and of invalid Pfa; distinct acceptance and clean-alarm populations; **training refuses val-calib, test, test-matched and val-select sources, and accepts the train role**; the calibrate path opens only the `val-calib` role and contains no other role literal; the calibrate path calls the approved function and not the historical one; the alarm-rule label changed |

## 6. Gate invariants verified

- `benchmark_complete` is false in the approved protocol, the readiness gates and the candidate configuration.
- `full_generation`, `full_gpu_training`, `full_loko_sweep` and `gpu_probe` remain `NOT_AUTHORIZED`; `production_launch` is `DISABLED`.
- `runtime_permitted()` is false and every `guard_execution(action)` raises `ExecutionNotAuthorized`.
- No approved JSON, gate JSON or P-document in `docs/plan/` that carries a gate value was edited. The only edited planning
  document is `docs/plan/P33_b2_e9_production_executor_readiness.md`, line 17, which withdrew an unsourced resource figure.
- No file under `configs/` or `src/geoml/b2_e9_contract.py` changed.

## 7. Exact HEAD, file changes and CI

- **Exact HEAD:** `HEAD_PLACEHOLDER`, pushed to `fix/b2-e10-scientific-integrity-hardening`.
- **CI status (exact head):** CI_PLACEHOLDER
- **File changes:** see the draft pull request description.

## 8. What this report does not show

- It shows that the code and the records behave as specified on synthetic fixtures and on the committed records. It does **not**
  show any recognition performance, and no such number is claimed here.
- The K17d identity list is a candidate derived from the frozen generator at the recorded source hashes. Its scientific
  acceptance is a researcher decision.
- Local tests ran on Python 3.13 with torch 2.14.1 from PyPI. The CI interpreter is Python 3.12, and CI was not reproduced locally.
