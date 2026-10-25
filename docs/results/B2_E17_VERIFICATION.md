# B2 E17 — trusted evidence verification

2026-10-25. Engineering only. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No production dataset, GPU discovery/probe/training, D-5 sweep, LOKO or held-out
inference was performed. No real signing credential, grant or revocation was created.

## Baseline and preserved work

Fetched `origin/main` and compared it with local HEAD:
`d82873967d6eb3a3f8f75a3f0ec9f89637e5873e`. PR [#40](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/40)
is merged; its final head was `3d0b24625c582b472d27fc77524c60f7b1265f27`.
One ordinary worktree, three pre-existing stashes and all historical branches
were preserved. The fresh E17 branch is `feature/b2-e17-trusted-release-evidence`.
The continuation preserved the unfinished E17 files rather than starting over.

The two requested final-head E16 runs were inspected through GitHub API job
metadata **and raw logs**, not inferred from a merge or earlier code-head run:

| Workflow | Run / job | Observed terminal evidence |
|---|---|---|
| E16 integration | [40184290052](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40184290052) / 121141684832 | SUCCESS; 2040 passed, 0 failed/skipped, 97.45 s |
| Readiness | [40184289910](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40184289910) / 121141684338 | SUCCESS; E4 107 passed in 148.33 s; repository 3844 passed in 1140.44 s; 0 failed/skipped; 46 existing Matplotlib `set_bad` deprecation warnings |

Those are baseline results, not E17 results. E16's old draft/in-progress language
is preserved as historical evidence. This report and the new DURUM entry reconcile
the current state without rewriting the protected historical report.

## Delivered changes

| Files | Change |
|---|---|
| `scripts/b2_e17_signatures.py` | Real OpenSSH Ed25519 SSHSIG verification of exact bytes, independently pinned policy, strict JSON, purpose separation, bounded public scratch data; no signing API |
| `scripts/b2_e17_git.py` | Exact object rehashing, direct single-parent approval lineage, exact three-file allowlist with a new grant record, source/config/tool maps, clean live checkout and lock identity; no repository mutation |
| `scripts/b2_e17_evidence.py` | Authenticated fresh explicit revocation and CI snapshots, grant/design/source/request binding, E16 adapter bridge and scoped CI check; public real root absent |
| Four `tests/test_b2_e17_*.py` files | Fabricated keys and Git histories; genuine positive cryptographic integration plus adversarial metadata and authority checks |
| E15/E16 workflows | Repair archival snapshot comparisons; retain frozen science/history checks and real current closed-gate checks |
| `.github/workflows/b2-e17-evidence-ci.yml` | Fixed 17-file CPU-only synthetic/metadata regression selection; original readiness workflow unchanged |
| E17 plan, two operations documents, E18 handoff, DURUM, this report | Trust boundaries, CI authority matrix, engineering versus operational blockers and actual evidence |

`src/`, `configs/`, `pyproject.toml`, original readiness workflow, scientific
protocols/approvals, gates/memorandum, K17d identity/audit and historical results
are unchanged. E17 changes tool identity, so a future plan/lock must bind its final
reviewed scripts; historical checkpoints are not reused under the new identity.

## Verification scope and environment

The local interpreter is `/workspace/.venvs/geosim/bin/python`, Python 3.12.14;
NumPy 2.5.4, SciPy 1.18.1, torch 2.14.1+cpu, pytest 9.1.1, Linux 6.18.55 x86_64.
Settings: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
PYTHONHASHSEED=0 MPLBACKEND=Agg CUDA_VISIBLE_DEVICES=''` for measured final runs.
These are test settings, not a qualified production environment or resource grant.
The initial plain `python -m pytest` attempt could not run (`No module named pytest`);
it is not counted as a passing test. The existing venv was then used.

Local E17 development checks and the final measured regression are recorded below.
Development failures were retained and corrected: a malformed-signature fixture
that did not actually truncate wire bytes, a strict-parser test that expected an
unwrapped error string, and serialization of a lock fixture's tuple as persisted
JSON. None was a production execution. Final evidence supersedes earlier counts.

The 17-file regression command is exactly the `python -m pytest -q -rs` file list
in the E17 workflow. It covers E17, all E16 suites, E14 launch/storage/metadata,
E13 generation-plan validation, E9 contract/freeze and E12 K17d/legacy metadata.
No full repository suite is claimed locally: the unmodified readiness workflow
runs its separate existing bounded E4 and repository commands on the PR head.

| Local check actually executed | Result |
|---|---|
| First three E17 suites during continuation | 184 passed in 32.04 s; 0 failed/skipped/warnings; before review hardening |
| Final Git suite including real cache-override reproduction | 86 passed in 9.18 s; 0 failed/skipped/warnings |
| E17 bridge after scientific-reference binding fixes | 86 passed in 45.58 s; 0 failed/skipped/warnings |
| Portable synthetic-host fixture, affected E17 bridge suite | 86 passed in 38.63 s; 0 failed/skipped/warnings; test SHA-256 `6fd01faef977cac45a985e34321457b5cc1d62e11c33a7fbc006086585f33f15` |
| Independent final four-suite run | 281 passed in 79.62 s (80.56 s wall); 0 failed/skipped/warnings |
| Measured 17-file synthetic/metadata regression | **2321 passed, 0 failed, 0 skipped, 0 warnings**, pytest 206.42 s; wall 208.09 s; peak child RSS 328,584 KiB |
| `python -m compileall -q` on E17 modules/tests; `git diff --check` | Exit 0 |
| Real `python scripts/b2_e16_policy.py ci-gate` | Exit 0, `CLOSED_CANONICAL`, `execution_permitted=false` |
| Protected source/config/science/gate/readiness diff against fetched main | Empty, exit 0 |
| Five E17/E18 documents: whitespace, local links, NO-GO; three workflow YAML parses | PASS (PyYAML from the base interpreter; unavailable in the test venv) |

These local runs used the proposed worktree on base
`d82873967d6eb3a3f8f75a3f0ec9f89637e5873e`, before its delivery commit. The measured
run's complete tracked-plus-untracked text snapshot was unchanged before/after
(snapshot SHA-256 `43c21fe86180151c9f20d96edc53c7a03868a4c8f29ba526e84ee89febedefbd`).
RSS is Linux maximum child high-water RSS, not summed concurrent memory. Raw
measurement/log records are outside Git under `/tmp/b2-e17-evidence/`.

After that run, the synthetic host fixture was made portable: its fabricated
Python/library/thread fields follow the test's actual environment pins before
the design is signed, instead of accidentally assuming local Python 3.12.14.
This is fixture maintenance, not qualification of the CI host or a scientific
change. The affected suite and exact committed regression evidence are reported
in the PR; the three product modules retain the hashes below.

| Final product source | SHA-256 |
|---|---|
| `scripts/b2_e17_signatures.py` | `faae68ef61cfda80b6774e825fc041c5bfa6bbdc973fa4f4492f6f9f5c14da08` |
| `scripts/b2_e17_git.py` | `49fe7e51562397910174dfa599ffebde98bd2607fcc1575d1a0390d93b218a3e` |
| `scripts/b2_e17_evidence.py` | `00e92db6f227123a558169f6df67d2e512dd4ff47a090158b0260d6927416b29` |

The `src/` Git tree remains `3da115d27898dc8a009c5ddb0fdfab4c34e084a7`;
`configs/` remains `d43808ae1d1e6e62d805af230a0127aa0d9ae858`.

## Independent read-only review

A separate model agent reviewed the patch and ran synthetic tests; this is not
human release approval. The review identified the following issues, resolved
with explicit regression tests before delivery:

| Finding | Resolution |
|---|---|
| Actual Git maps were not bound to plan/reference source maps | Compare exact Git-derived source/config/tool maps with both plan and reference |
| CI job claim was not bound to the signed run | Require exact run/job/head and successful terminal job; reject reused job IDs |
| Spaced/CRLF JSON fences had a parser differential | Strictly parse all JSON fences, including unknown schemas, before E16 parsing |
| Caller-supplied closed snapshot could hide an open repository | Bind closed-state gate/memorandum/protocol to committed bytes and a clean exact checkout |
| Ignored Python bytecode could override unchanged source | Reject executable caches; a real timestamp-valid fabricated `.pyc` reproduces the mismatch and is refused |
| Grant allowlist could overwrite another historical document | Require the named grant record to be new in the approval commit |
| Directory-only Git trees escaped the file-count budget | Count all tree entries, including directories, against the bound |
| An empty scientific-record map and unbound parsed decision could evade checks | Require the complete record key set and exact Git hashes/parsed decision/approval-record identities |

Final review: **NO OPEN MATERIAL FINDING**. The three modules, four test suites
and three workflows had identical before/after hashes during the independent
281-test run. The later fixture-only environment portability correction does not
change a product module or an authority rule. The independent reviewer read that
final fixture correction and confirmed the unchanged product hashes and verdict;
their 281-test execution belongs to the preceding fixture hash, not the correction.

## Authority and residual risks

| Invariant | Before E17 | After E17 |
|---|---|---|
| K18 / K17d / OBS-CANCEL-2 | APPROVED with provenance | Unchanged |
| D-1–D-8 / R1–R10 | Ratified scientific records | Unchanged |
| full_generation / full_gpu_training / full_loko_sweep | NOT_AUTHORIZED; approvals null | Unchanged |
| GPU probe / final held-out evaluation | Unauthorized | Unchanged |
| Production launch / benchmark_complete | false / false | false / false |
| E9/E14/E16 runtime refusals / two-group fixture cap | Active | Unchanged |

The public root remains literal `PINNED_TRUST_ROOT=None`. A configured-root test
can validate a fabricated document; the same open candidate through the real
entry returns `BLOCKED_TRUST_ROOT_MISSING`. Every E17 result keeps
`execution_permitted=false`, even `DR04_GENERATION_RECORD_VALID`.

Cryptographic key separation is not proof of independent human administrators.
No real researcher key mapping, independently authenticated revocation authority,
CI attestation service, trusted clock or durable challenge/replay custody has been
provisioned. The reader checks supplied challenge/floor and does not advance them;
reusing an externally reused challenge is not prevented by a stateless consumer.
Git verification is a point-in-time snapshot, not protection against a later host
compromise. The verifier process, OS, Git/OpenSSH binaries and import loader remain
deployment trust dependencies. Synthetic host/K17d fixture claims are labelled as
such; they are not production host qualification or a production metadata check.

Designated host, independent persistent backup/restore, external journal, run-bound
ceilings, real DR-04 record, final source/environment lock and separate release
decision remain missing. See the [E18 handoff](../plan/B2_E18_EXECUTOR_INTEGRATION_HANDOFF.md);
E18 is not started by this milestone.

## Delivery evidence convention

The final commit cannot contain its own SHA or the outcome of CI triggered by that
commit. The draft PR body and final delivery report record the final head and its
run/job IDs and raw-log counts. They distinguish terminal results from pending
checks. No compute permission follows from a green run.
