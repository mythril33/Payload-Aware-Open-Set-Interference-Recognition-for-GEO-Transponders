# P29 — B2/1 production preflight (E6)

Date: 2026-10-23. Base `main` `59ed11d`. `benchmark_complete=false`. This is an engineering contract for a **read-only
validator**; it grants no authorization, edits no frozen protocol (P18/P19-P22/P28 are untouched) and generates no benchmark data.
Tool: [`scripts/b2_production_preflight.py`](../../scripts/b2_production_preflight.py); tests:
[`tests/test_b2_production_preflight.py`](../../tests/test_b2_production_preflight.py); readiness
[checklist](B2_E6_PRODUCTION_READINESS_CHECKLIST.md) and [audit findings](b2_e6_audit_findings.json); researcher
[decision packet](B2_E6_RESEARCHER_DECISION_PACKET.md); measured [evidence](../results/b2_e6_preflight_evidence.md).

## 1. Why a script, not a package module

`geosim.dataset._generator_provenance()` hashes every `src/geosim/*.py` and `src/geosim/data/*` into each artifact request, and
checkpoint provenance (P28 section 6, `check_source_rule`) hashes `src/**/*.py` and refuses unexpected additions. A new file under
`src/` would therefore change frozen request identities or invalidate checkpoint identities. The preflight lives in `scripts/`
(like `b2_a5_matrix.py`) and imports the generators' own private helpers (`_request`, `_stage`, `_calibration`, `_verify_part`),
so "would the generator resume this root?" is answered by the generator's own definition of a request, not by a copy of it.

## 2. Status vocabulary and exit codes

PASS = verified here by a test or an inspected location; FAIL = a verified defect, gap or mismatch that engineering can fix
without a researcher decision (or a root that must not be used); BLOCKED = needs a researcher decision, authorization,
hardware or a measurement, or an operator action; NOT_RUN. Exit 0 = PASS, 3 = FAIL, 4 = BLOCKED, 5 = NOT_RUN (nothing was verified, e.g. an absent or mistyped root), 2 = usage error or refused overwrite;
`--allow-blocked` waives BLOCKED only for `gates`, `checklist` and `inventory`, never for an `audit`. Reports are strict JSON (`B2-production-preflight/1`) with
`benchmark_complete=false` and `production_authorized=false` fixed; the tool cannot emit anything else. Output files are never overwritten.

## 3. Commands

| Command | Reads / writes | Purpose |
|---|---|---|
| `inventory` | frozen constants, E5 plan, geoml preprocessing defaults | Role/stage inventory derived from the frozen constants equals the E5 plan table (21,350 = 18,400 + 2,500 + 450); role id ranges are disjoint and reserved; interruption bound (32/20/12 observations per shard at four groups per shard); plan arithmetic (storage, wall/core hours, sample-passes, window memory) reproduces |
| `gates` | gates JSON + E5 memorandum JSON | Every gate is BLOCKED while pending; an approval without `approved_by`/`approved_at`/`decision`/`record` (and, for `full_*`, positive wall/core/disk ceilings), an approval attached to a pending gate, an unknown status, a gates/memorandum disagreement or `benchmark_complete=true` is FAIL |
| `lock-create --out F` | repo; writes `F` | Immutable `B2-production-lock/1`: git commit and tree cleanliness, SHA-256 of every `src/**/*.py` and `src/geosim/data/*`, the generator provenance, frozen configs and gates file, parsed physical/canceller configs, Python/NumPy/SciPy/torch/xgboost versions, BLAS and hash-seed environment, the frozen production request choices. Refuses a dirty tree unless `--allow-dirty` |
| `lock-verify --lock F [--require-clean]` | repo | Names every drift (source file added/modified/removed, config, generator, environment, commit, thread settings, edited lock) |
| `audit --stage known\|test\|matched --root R [--lock F] [--known K] [--depth structure\|checksum\|full] [--production]` | read-only | Classifies a (possibly partial) root, see section 4 |
| `transfer-manifest --root R --out M` / `--verify M` | reads; writes `M` | Path/length/SHA-256 manifest for backup and GPU-host transfer; verification names missing, extra, resized, modified files |
| `resources --root R` | probes; scratch dir removed | Disk, atomic rename + fsync, RAM, CPU against the **proposed** ceilings; GPU is always BLOCKED |
| `drill --workdir W` | writes a scratch tree | Capped real-physics drill: exactly two groups of the train role, one group per shard, B2-feat/1 with `obs-cancel/1`; interrupt, corrupt, orphan and request-change scenarios on copies |
| `checklist [--markdown F] [--host-root R]` | repo | Static checks + manual audit findings (+ host probes); renders the committed checklist |

## 4. Artifact audit semantics

Depths: `structure` (file names, descriptors; **cannot see byte flips**), `checksum` (default; SHA-256 of every committed part/meta
file, `hashed_bytes` reported), `full` (adds the generator's own `_verify_part` decode and semantic validation on a bounded sample
of shards per role, `--max-full-shards`). Checks: request strict-JSON and equal to the request the generator would build today
(source, NumPy/SciPy, config and canceller drift show as `generator_would_refuse_resume`); frozen contract and
`benchmark_complete=false`; role group ranges; descriptor binding (groups, counts, request fingerprint); checksums; group
isolation across shards and roles; stray files; manifest consistency; calibration artifact; with `--lock` the request's source,
versions and configs equal the lock; with `--known` the test/matched request is bound to that known root's fingerprints **and**
shares its generator source, NumPy/SciPy, config and canceller (the generators bind fingerprints only); with `--production` the
request is the full frozen one (all roles, no group limit, four groups per shard, B2-feat/1, `obs-cancel/1`).

| State | Meaning | Operator action |
|---|---|---|
| NOT_STARTED | absent or empty | none |
| RESUMABLE | identical request, committed shards verified, others missing | re-run the same pinned command; verified shards are not rewritten |
| COMPLETE | manifest present and consistent with all shards | none |
| NEEDS_QUARANTINE | data files exist without a committed descriptor (kill between the renames and the descriptor write); the generator refuses | move those files to a quarantine directory (never delete), re-audit, then resume |
| INVALID | modified, foreign, role-crossing, source-drifted or tampered; the generator refuses or must not be trusted | stop; use a fresh root or a documented restoration; do not edit evidence |

Temporary files (`*.tmp.npz`, `*.jsonl.tmp`, `*.json.tmp`) are reported but harmless: the generator ignores and overwrites them.

## 5. What this does and does not prove

Proves, on fixtures and on the capped real-physics drill: fail-closed behavior on tampering, source/config drift, role crossing
and unbound stages; checksum integrity; that an interrupted root resumes bit-equal without rewriting verified shards; that the
orphan state is detected and recoverable by quarantine. **Does not prove:** anything at production size (memory, throughput, wall
time, disk behavior of 8.7 GB), GPU behavior, scientific correctness of the data (physics checks remain separate), absence of
deliberate forgery (digests detect accidental modification only), or any researcher approval. The host probe describes only the
machine it runs on. Audit findings that remain FAIL or BLOCKED are listed in the checklist and need engineering or researcher action
before DR-04.

## 6. Recommended order after a separate, explicit authorization (descriptive, not a launcher)

1. Record the gate decisions in the gates JSON with approver, time and record; run `gates` (all PASS, none BLOCKED).
2. Commit the production training configuration and diagnostics decided in K18; create the lock from a clean checkout on the
   designated host (`lock-create`), keep it with the run; `lock-verify --require-clean` before every stage.
3. `resources --root <output root>` on the production host; copy the generator flags from `--help` at the pinned commit.
4. Known stage first, then `audit --stage known --production --lock`; then test-only and matched with `--known`; resume only under an
   identical lock; quarantine orphans; stop on INVALID.
5. `transfer-manifest` before and after every copy; re-audit the copy at `checksum` depth before training.

## 7. Change control

No P18 entry: E6 changes no semantics, version, seed, label, count or request layout. Any future edit to `src/` after the lock
creates a new lock and invalidates resumption of any root generated under the old one.
