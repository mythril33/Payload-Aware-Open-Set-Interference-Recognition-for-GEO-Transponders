# B2 E10 — verification report

**Branch:** `fix/b2-e10-scientific-integrity-hardening`.
**Baseline at start:** `origin/main` `e43987ea8b6a50d0df9b6969e69e80d36d03f182` (PRs #30, #31, #32 merged).
**Merged state:** PR #33 was merged by its maintainer at head `4efb7f0`; `origin/main` is now `293c487`, a merge commit whose tree equals `4efb7f0`. This report covers the follow-up work after that merge.
**Code under test:** `68b13bb` (the follow-up code commit). The documentation commit that carries this report changes no file under `src/`, `tests/`, `scripts/` or `configs/`; this is checked with `git diff --stat 68b13bb HEAD` in section 7.
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

All commands ran from the repository root with `PYTHONPATH=src` and the scratch venv interpreter, at `68b13bb`.

| # | Command | Scope | Result |
|---|---|---|---|
| T1 | `pytest tests/test_b2_e10_k17d.py tests/test_b2_e10_records.py tests/test_b2_e10_calibration.py -q` | E10 new tests | **PENDING_T1** |
| T2 | `pytest tests/test_b2_execution.py -q` | isolated executor, including the calibration and evaluation isolation tests | **PENDING_T2** |
| T3 | full suite, included in T4 | E9 contract and preflight gates | covered by T4 |
| T4 | `pytest -q -rs -p no:cacheprovider` (full suite, CI-equivalent flags) at `68b13bb` | whole repository | **PENDING_T4** |
| T5 | `python -m compileall -q src tests scripts` at `68b13bb` | syntax of every source file | **PENDING_T5** |
| T6 | `python scripts/b2_e10_k17d_identity.py` at `68b13bb` | metadata-only K17d derivation over 500 test groups with the audit cross-check | **PENDING_T6** |

Failures and skips are recorded in section 4.

## 3. Test corrections made during verification (and why each is legitimate)

No assertion was weakened to pass. Each edit below was made because the test encoded the historical rule, the subtraction score, or a fixture that lacked a field the stricter validator now checks.

| Test | Before | After | Reason |
|---|---|---|---|
| `tests/test_b2_execution.py::test_threshold_rule_matches_independent_power_probability_arithmetic` | expected `np.quantile(1-p_clean, .95)` (linear) | expected `np.quantile(p[:,1:].sum(1), .95, method="higher")` | The first change encoded the historical linear rule. The second uses the same non-cancelling score as the executor. For ordinary margins the two forms agree to rounding. |
| `tests/test_b2_execution.py::test_fixture_evaluation_uses_only_frozen_objects_and_readonly_inputs` | monkeypatched `threshold_at_pfa` | the name is removed from the list; `clean_alarm_threshold` stays | `b2_execution` no longer imports `threshold_at_pfa`, so `monkeypatch.setattr` failed. |
| `tests/test_b2_e10_k17d.py::fixture_audit` | header had `n_missing_groups` only | adds `n_missing_co_feed` and `n_missing_cross_feed` | The validator now checks these header counts against the derivation. The fixture was a real audit shape, so it had to carry the fields. |
| `tests/test_b2_e10_k17d.py::test_cross_check_refuses_an_audit_missing_one_group` | `match="only_in_derived|disagrees"` | `match="1 derived-only"` | The loose pattern matched the word "disagrees" alone. |
| `tests/test_b2_e10_k17d.py` AST allow-list | any `from . import x` accepted as a bare `"."` | exact set `{__future__, hashlib, json, numbers, .b2_protocol, .b2_scenarios}` | The old check did not constrain which sibling modules the validator imports. |

## 4. Failures and skips

- **Failures in the full run (T4):** PENDING_T4_FAILURES
- **Skips (T4):** PENDING_T4_SKIPS
- **Tripwires (unchanged):** `tests/test_b2_e8_tools.py:237` and `tests/test_b2_training_footprint.py:553` still encode the approved TF32 sequence. They pass at `68b13bb`.
- **Failures found during development (before correction):** a `TrainConfig` constructor error, a `B2Source.index` fixture error, the `dict(**{7: ...})` keyword error in one new test (a `TypeError` in my own test code), and the two `test_b2_execution` failures in section 3. All were fixed in tests or helpers, not in approved code.

## 5. New negative and regression tests (what each one proves)

| File | Tests | What they prove |
|---|---|---|
| `tests/test_b2_e10_k17d.py` | 43 | Exact 500 / 35 / 465 partition; canonical and order-independent output; fingerprints change when identities change; refusal of wrong count, duplicate, out-of-range ID, wrong role or protocol, diagnostic override, malformed or out-of-range drop, `plan_consistency` mismatch, outcome-bearing keys, missing fields; audit disagreement (missing group, polarization mismatch, wrong total, duplicate row, **audit header count mismatch**, **non-mapping audit row raises `K17dError`**); **mixed-type record keys and mixed-type drop keys raise `K17dError`, not `TypeError`**; **numpy-typed metadata normalises to the same identities and fingerprints**; the metadata path never reaches `simulate_dual` (patched to fail); the validator module's import set is exactly the allow-list |
| `tests/test_b2_e10_records.py` | 11 | The committed record declares zero observation reads and zero waveform calls; counts and fingerprints recompute from its own lists; **headline IDs, predicate and headline fingerprint recompute**; **`package_sha256` equals the digest of the current `src/geosim` tree**; **`audit_sha256` and `source_sha256` equal the files on disk**; **the derivation reproduces from the frozen generator with `simulate_dual` patched to fail**; tampering with one co-feed ID and one audit polarization is detected; gate values in the approved protocol are unchanged; the contract refuses every execution action |
| `tests/test_b2_e10_calibration.py` | 35 | Hand-computed higher-quantile values (`arange(100)` gives 95.0, the historical helper gives 94.05); order statistic; monotone in Pfa; ties; small samples; refusals; distinct acceptance and clean-alarm populations; training refuses val-calib, test, test-matched and val-select sources; the calibrate path opens only `val-calib`; the calibrate path calls the approved function; **a clean sample with a 40 or 45 nat margin keeps a strictly positive ordered score, while `1 - P(clean)` by subtraction returns 0**; **both calibrate and evaluate bodies use `clean_alarm_score` and not `1.-probabilities`** |
| `tests/test_b2_execution.py` | 42 | Unchanged count; expectations updated as in section 3 |

## 6. Gate invariants verified

- `benchmark_complete` is false in the approved protocol, the readiness gates and the candidate configuration.
- `full_generation`, `full_gpu_training`, `full_loko_sweep` and `gpu_probe` remain `NOT_AUTHORIZED`; `production_launch` is `DISABLED`.
- `runtime_permitted()` is false and every `guard_execution(action)` raises `ExecutionNotAuthorized`.
- The approved protocol JSON, the approval record, the E8 decision approval, `src/geoml/b2_e9_contract.py`, `configs/` and the candidate configuration are **byte-identical to `e43987e`** (section 7).
- P33 is restored to its `e43987e` text. The `4efb7f0` edit that withdrew a resource figure was wrong and is reverted.

## 7. Exact HEAD, file changes and CI

- **Merged state:** PR #33 merged at `4efb7f0`. `origin/main` is `293c487`, tree identical to `4efb7f0`.
- **Follow-up code commit under test:** `68b13bb` (rebased onto `293c487` for the follow-up PR; tree content unchanged by the rebase, since `origin/main` tree equals `4efb7f0` tree).
- **Protected paths:** `git diff --stat e43987e HEAD -- docs/plan/b2_e9_approved_scientific_protocol.json docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md docs/plan/B2_E8_DECISION_APPROVAL.md src/geoml/b2_e9_contract.py configs/ docs/plan/b2_e9_candidate_production_config.json` is **empty**.
- **Documentation-only check:** `git diff --stat 68b13bb HEAD` lists only `docs/` paths for the documentation commit.
- **CI:** the follow-up draft PR's exact-head check run is recorded in its description after it completes. The prior check on `4efb7f0` (run `40108670413`, job `120915592427`) passed; it is superseded.
- **Local-versus-CI interpreter:** local runs used Python 3.13; CI uses Python 3.12. CI is the authoritative exact-head evidence for 3.12.

## 8. Independent review and dispositions

A review workflow (`wf_38b51234-8d4`) ran on `4efb7f0` with three reviewers (scientific and statistical; leakage and safety; code), and a second agent re-checked every material finding against the cited line. Its findings and dispositions are in the closure document, section 8 (N-1 to N-8). Fixed in `68b13bb`: N-1 (score saturation), N-6 (validator normalisation, mixed keys, non-mapping rows, header counts, tautological partition, script ordering), N-7 (record binding). Recorded as decisions or errata: N-2 (packet D-7), N-3 and N-4 (closure E-10 and E-11), N-5 (packet D-6), N-8 (corrections in this PR's text). This review is an automated workflow. It is not a human researcher review, and independent human review of the calibration rule, the K17d validator and the decision packet is still requested.

## 9. What this report does not show

- It shows that the code and the records behave as specified on synthetic fixtures and on the committed records. It does **not** show any recognition performance, and no such number is claimed here.
- The K17d identity list is a candidate derived from the frozen generator at the recorded source hashes. The approval asks for committed production generation metadata; that is a researcher decision (packet D-8).
- Local tests ran on Python 3.13 with torch 2.14.1 from PyPI. The CI interpreter is Python 3.12.
- The historical stages keep the linear rule and the subtraction score (closure E-10). The E7b evidence was produced by the linear-rule executor (closure E-11); no rerun is performed here.
