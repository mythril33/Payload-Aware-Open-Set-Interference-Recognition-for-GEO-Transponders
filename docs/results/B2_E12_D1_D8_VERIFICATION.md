# E12 — D1–D8 ratification and safe legacy access verification

Date: 2026-10-24. **SCIENTIFIC DECISIONS RATIFIED — EXECUTION NO-GO.**

Verified base main: `a335eed5fd3ac22eb341aa7ecf148f4efe7bd023`.
PR33, PR34 and PR35 were independently confirmed merged.
Initial worktree was clean; existing branches/work were preserved.
Branch: `docs/b2-e12-d1-d8-scientific-ratification`.

**Exact implementation commit tested:**
`da3770d1fe9c1f1728d6ba686f1dd5e257390601`.
The subsequent evidence commit changes only this report, its JSON ledger
and DURUM. The final PR head and exact-head CI result are recorded in the
draft PR after completion; a pending CI is not a pass.

## Delivered change

The [dated addendum](../plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md)
and [decision register](../plan/b2_e12_d1_d8_decisions_2026-10-24.json)
record the researcher's eight conversation decisions, without inventing a
signature or compute approval. E9's prior approval text is preserved as an
unchanged prefix with a dated amendment; P18 only gains dated §7a/§10
cross-references. Its original seeds, classes, physics and hyperparameters
are unchanged. The E9 machine-readable protocol and its13 decisions remain
byte-identical: no schema-breaking edit was needed.

D7 adds default-deny CLI/API intent, checks all three metadata headers
before full observation readers, admits only exposed test3200000/3200001
and matched3300000/3300001, and refuses GPU/automatic device selection.
`--allow-test-read` is rejected by isolated modes. The existing12-group
ceiling is retained; legacy historical access is additionally bounded by
epochs<=3,width<=8,batch<=32, excluding the production30-epoch/width16
recipe. These are access ceilings, not modified training hyperparameters.
Permitted repetitions carry explicit non-pristine/no-authority provenance.
Shared isolated calibration/freeze/evaluation helpers are unchanged.

Existing synthetic tests now request historical intent explicitly. The
three-group streaming fixture remains for streaming/partial-shard coverage;
a two-group fixture covers admitted legacy calls, and a negative test
refuses the third test ID before the full reader. Four-group matched
denominator/bin coverage is retained through a pure metric test.

D8's read-only verifier re-derives metadata only, validates strict JSON,
unique sorted role IDs, the pol==0 predicate, source/package/audit hashes,
and external acceptance bindings. It never rewrites the identity artifact.
Tampering, missing/duplicate/cross-feed IDs, roles, source/audit drift,
missing acceptance and nested non-finite numeric overflow are rejected.
The CLI has no generator/observation execution option.

## Actually executed local evidence

Python3.12.14; Linux6.18.55/glibc2.41; NumPy2.5.4, SciPy1.18.1,
torch2.14.1+cpu, pytest9.1.1, xgboost-cpu3.4.1. CPU thread ceilings:
OMP/OPENBLAS/MKL=2, PYTHONHASHSEED=0, MPLBACKEND=Agg. Temporary fixtures
and raw evidence are outside Git.

| Command / scope | Actual result | Wall seconds | Peak child RSS KiB |
|---|---|---:|---:|
| Exact-code synthetic selection below |187 passed,0 failed/skipped/warnings; pytest18.43s |19.576041|346952|
| Metadata-only verifier with E12 acceptance |exit0;500/35/465,cross43,total78;0 observation/waveform calls |11.947778|85484|
| Production preflight `gates` |expected exit4;4PASS/0FAIL/3BLOCKED/0NOT_RUN; no authority |6.256282|82832|
| `python -m compileall -q src tests scripts` |exit0 |not separately measured|not measured|
| `git diff --check` and protected-path comparison |exit0 |not separately measured|not measured|

Every measured command records identical before/after HEAD and tracked-file
SHA256 maps. Exact argv, environment, summaries and selected hashes are
preserved in the [JSON evidence](b2_e12_d1_d8_verification.json).

```bash
python -m pytest -q -rs tests/test_b2_e12_legacy_access.py tests/test_b2_e12_k17d_integrity.py \
  tests/test_b2_execution_cli.py tests/test_b2_e10_calibration.py \
  tests/test_b2_e9_scientific_freeze.py tests/test_b2_e10_records.py \
  tests/test_b2_experiment.py::test_all_matched_bins_keep_full_denominators_without_legacy_observation_access \
  tests/test_b2_execution.py::test_incomplete_inventory_is_rejected_before_any_test_read \
  tests/test_b2_execution.py::test_all_nine_inventory_cells_are_validated_before_test_access
python scripts/b2_e12_verify_k17d.py --acceptance docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json
python scripts/b2_production_preflight.py gates   # expected4, BLOCKED
```

The D7 positive path replaces fitting, scoring-state fitting, model loading
and inference with stand-ins. No actual model is trained or inferred
locally. The metadata verifier may read only the committed FIR coefficient
asset needed by configuration validation, not waveform/observation data.
The complete repository suite was **not run locally for E12**, because
local authorization is limited to synthetic CPU/metadata checks. The
existing authorized bounded CI runs the complete regression; its actual
counts/skips/Python version belong to the exact final PR head.

Earlier development evidence remains distinct: D7 initial42passed4.21s,
combined precommit selection136passed15.72s, D8 final51passed5.91s.
Two real red-test episodes were corrected: the overly broad np.load spy
initially blocked the committed FIR coefficients (42passed/1failed1.97s);
a strict-JSON overflow negative exposed1e999 (1failed/3passed/46deselected,
1.28s). Neither is relabelled as a passed suite. The final187-test run
covers both corrected cases.

## Source and artifact identities

Canonical experiment source SHA256 changed from
`e0fd87cf547b0c074c9584b9c5d92a954b7796450a5b6dd9b4ec6e75191ccaad`
to `72f498c46d7df115ef83f19f9b3aa35cdea048dc8816a0fc74c9ceb1f84536f2`.
This is a new checkpoint provenance identity. Historical checkpoints are
not relabelled or reused under changed source identities.

Identity SHA256 remains
`ccdf0a8f40e71d7ddb388068e455a77a131214f5644ab332a16c8268cfc49c6d`;
audit SHA256 remains
`be4e2434bcd562f6521821da3403a5c5d5a14b8951ec6174ba0a795564fda65e`.
The28-module geosim package SHA256 remains
`01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b`.
No production metadata exists or was validated. The future production
cross-check is explicitly NOT_RUN_REQUIRES_SEPARATE_AUTHORIZATION.

## Review, risks and remaining gates

Separate read-only scientific/engineering review found and resolved:
finite JSON overflow handling and truthful description of narrowed legacy
ceilings. No open material patch finding remains. Reviewers edited no
production code, ran no experiments and opened no observations.

- D1 preserves500/150 headline groups; the existing test is not pristine.
  The mandatory498/148 sensitivity row remains future reporting work.
- D4 names endpoint/view but does not select one primary scorer from MSP,
  energy and Mahalanobis. No winner may be chosen from test outcomes;
  a single-scorer headline requires pre-test registration.
- Artifact directories must remain immutable during a run, as required
  by existing readers. This narrow guard adds no hostile-writer lock or
  authorization service.
- D5 SNR definition, modulation pairs, paired sampling and CPU ceilings
  remain OPEN. No RF sensitivity sweep was run.
- DR-04/05/06 host/resource/backup/probe reservations, a reviewed production
  executor, nine-cell production freeze and separate final-read authority
  remain unresolved. TF32-off enforcement is future executor work.

Scientific K18/K17d/OBS-CANCEL-2 approvals and R1–R10 are intact.
All full-generation/GPU/LOKO compute statuses stay NOT_AUTHORIZED with
null approval fields. GPU probe/final held-out evaluation remain
unauthorized, production activation/launch disabled and
benchmark_complete=false. No RF sweep, dataset production, GPU probe,
training, held-out evaluation, LOKO or production workload was executed
as an E12 experiment. Unit/metadata evidence is not detection performance.
