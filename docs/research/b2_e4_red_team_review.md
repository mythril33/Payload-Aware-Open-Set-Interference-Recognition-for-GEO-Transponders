# E4 independent scientific red-team review — 2026-10-23

Scope: read-only review of the dual-pol A5 harness (`src/geoml/b2_a5_plan.py`, `b2_a5_replay.py`, `b2_a5.py`, the
`tests/test_b2_a5_*.py` files and `tests/b2_a5_support.py`, `scripts/summarize_b2_a5_pilot.py`, the CI step and the E4 claims in
[P28](../plan/P28_b2_e4_dual_pol_a5.md), [the context pack](../engineering/B2_E4_CONTEXT.md), README and CLAUDE.md), following
[.agents/review.md](../../.agents/review.md) and the master prompt's Agent E brief. The reviewer ran as a separate agent with no write
access to the repository; the implementer (integrator) did not review its own code. This is engineering review within the agent workflow,
not external scientific endorsement.

P28 was committed (`b58c658`) before any code, replay or A5 outcome existed. The review checked the physical boundary (belief never reaches the
simulator, IQ unchanged, canceller input), false-oracle and leakage paths, parity strength, provenance rules, frozen-protocol compatibility,
statistics, caps, test quality and overstated claims.

## Round 1 — HEAD `8bedd2b` (against base `ff81cae`)

Executed by the reviewer: the fast test files (`test_b2_a5_plan.py`, `test_b2_a5_negative.py`: 42 passed in 14 s) and ad-hoc snippets; it also
read the in-progress pilot outputs. **Verdict: no BLOCKER.** The physical core held: the belief never reaches the simulator, the IQ is a
read-only copy, the canceller receives only `iq[0]` through the generator's own `_residual` path, the residual is recomputed iff the co
descriptor changed, `cross_only` never calls the canceller, models read only `spec/mask/residual`, the Mahalanobis/rejection/alarm identities
match `b2_experiment` key for key, and E4 adds exactly three new source files.

| ID | Severity | Defect (verified by the reviewer) | Disposition (commit `a595bcf` unless stated) |
|---|---|---|---|
| M1 | MATERIAL | `reproduction_command` omitted the CLI `--perturbation/--scope` overrides, so 24 of 25 pilot records pointed at a different experiment; the matched config lived outside the repo | **Fixed.** Overrides are recorded; resolved `a5_config.json` is written; `configs/b2_a5_matched_smoke.json` committed; test re-runs the recorded command and checks the same `experiment_fingerprint` |
| M2 | MATERIAL | Summarizer compared identities only between two `known` invocations; matched or mixed inputs were never compared, contradicting its docstring | **Fixed.** Known fingerprint, checkpoints, calibration, cancellation, run config, source and per-stage request/artifact identities are always compared; mixed-stage and re-signed-tamper negatives added |
| m1 | MINOR | Reuse fingerprint omitted the run directory's `config.json` (pfa, methods), scorer/rejection hashes and non-E4 sources, so a changed alarm rule could return a stale result | **Fixed.** Fingerprint now covers the resolved run config, frozen-file hashes and the full source tree; test edits a frozen run file and expects a new identity |
| m2 | MINOR | Only applicable scenes are replayed/parity-checked, P28 said "every selected scene" | **Clarified** in P28 §5 and the §13 log |
| m3 | MINOR | Two binding negatives passed through generic manifest integrity, not the targeted check | **Strengthened:** a second valid known artifact (other canceller settings) exercises the matched↔known binding with its own message. The defensive cancellation-equality check cannot be reached with a legitimately generated artifact (the generator refuses it) and is stated as such |
| m4 | MINOR | `stale_plan` gloss ("the plan the operator held") is not what the formula does | **Corrected** in P28 §3 (formula `default_plan(2(id−1)+pol)`; preceding id may be outside the roles and its group may have redrawn plans); the stale-and-invalid case is `blocked` (also i4) |
| m5 | MINOR | `phantom_overlaps_physical_event` only for the co descriptor | **Fixed:** per-polarization flags |
| m6 | MINOR | `original` scored on all rows then sliced, counterfactuals on the applicable subset (batch-composition effects ~1e-5) | **Fixed:** the paired `original` is scored with the same batching; the `none` test asserts exact 0.0 |
| m7 | MINOR | Results recorded only E4 source hashes and no SciPy version (P28 promised current hashes) | **Fixed:** full source-file hashes, tree fingerprint, frozen-file hashes, SciPy version |
| m8 | MINOR | Summary text hard-coded "chance-level stand-ins"; `all_parity_exact` counted `None` as exact | **Fixed:** note is an input; checked/unchecked invocations are counted separately |
| m9 | MINOR | Weaker-than-named assertions; union test skipped `authorize_intruder`; no real-physics matched replay | **Fixed:** exact equality; union test includes `authorize_intruder`; real-physics matched replay test |
| i1 | INFO | `open_replay_source` could open train/validation roles | **Fixed:** A5 replays the frozen `test` role only |
| i2 | INFO | The 0.125 dB tolerance applies on any machine; only `exact=false` signals a difference | Accepted and documented; pilot values lie in −120…−70 dB so it is two float16 ulps |
| i3 | INFO | The stand-ins were trained with the K17b mask-shift augmentation, confounding `MASK_ONLY` shifts | **Stated** in the results note (§4) |

Overstated or unsupported claims found, and their disposition: links to a non-existent results note (now committed with the evidence);
"chance-level stand-ins" without committed evidence (now in the results note); "verified equal to stored"/"identical by construction" without the
parity condition (P28 reworded); "union (tested)" (test extended); `clean_false_alarm`/`event_detection` read as false-alarm/detection rates under
counterfactuals (reworded as alarm rates among original-clean / original-event scenes, in P28, the results text and the report table headers);
the P18 log row that listed `stale_plan` among "frozen" perturbations (reworded: defined by P28); invariant A described as tested although it
holds by construction (P28 reworded).

Residual risks named by the reviewer and kept open: cross-machine bit-parity is untested (CI generates and replays on the same runner); batch
composition may matter on other BLAS/oneDNN builds; NumPy/SciPy versions recorded in an artifact's request are not compared with the current
ones (only the parity check protects against version drift).

## Round 2 — re-review of the fixes and of the resumability feature

Requested for commit `a595bcf` (merged to `main` as `4b736a6`, identical tree): verification of every row above, and an attack on the new
resumable-state design (`SceneState`, `_output_state`, per-scene `state/`, `scripts/run_b2_a5_pilot_matrix.sh`). The first attempt was
interrupted by an external API usage limit; it was resumed after the limit reset.

**Status at this commit: round 2 is still running; its findings are not yet part of this record.** They are appended below when the reviewer reports, together with the resulting fixes.

