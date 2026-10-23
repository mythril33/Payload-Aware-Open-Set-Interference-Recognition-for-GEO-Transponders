# E4 post-merge independent scientific review — 2026-10-23

This is a separate read-only agent review within the engineering workflow,
not an external scientific endorsement. The reviewer did not implement the
fixes, edit source, fit a model, generate RF data or run the physical pilot.
Scope: merged P28 and the plan/replay/evaluation modules, E1 validators,
frozen checkpoint/scorer/calibration bindings, scene/result reuse, matrix
orchestration, summarizer and adversarial tests. Base main is
`4b736a6c425ab532e7c8e1bccc7c906f86ebe0be`; recovery engineering commit is
`2ee03c53ea2183e1b227f09d428701215cfb2090`.

## Findings and resolution

1. **Blocking, resolved — failure masking and checksum-only matrix skips.**
   The old shell pipeline ended in `tail -3` without pipefail, hiding Python
   failures. A matching result checksum also bypassed current provenance.
   The new driver captures actual subprocess status and full per-attempt
   logs, always enters the provenance-aware CLI, enforces the overall
   budget before work, and records every canonical inventory slot.
2. **Blocking, resolved — unbound committed scene metadata.** The reviewer
   changed cached parity and work.replays to999 without changing the array
   checksum; the old loader accepted it. State/2 now binds the entire
   canonical metadata payload to SHA-256, rejects incompatible/legacy
   schemas, duplicate keys, nonfinite values and inconsistent work/status/
   parity/array bindings, and enforces logical replay/cancellation totals.
   This is checksummed integrity, not an authenticated digital signature.
3. **Resolved — misleading partial summaries.** The summary now verifies
   all25 canonical names, per-result hashes/configurations and consistent
   completion flags, status and totals. Empty parity populations yield
   null rather than a vacuous true. Nine successful selected invocations
   still mean PARTIAL, with16 pending invocation slots; pending slots are
   distinct from non-applicable or blocked samples.
4. **Resolved — counterfactual metric names.** Nested matched
   `pair_accuracy*` fields become `pair_agreement_with_original_label*`
   for MASK_ONLY/RECEIVER_CONSISTENT. Arithmetic and denominators remain
   unchanged; original-condition accuracy remains conventional accuracy.
5. **Resolved — cross-only invariance wording.** An unchanged co descriptor
   causes no cancellation call and reuses the original replay residual.
   Equality to stored residual requires exact replay parity. The accepted
   0.125dB portability tolerance does not guarantee bit equality; a
   regression checks this distinction without changing the receiver.

No remaining material code blocker was found in the reviewed recovery
commit. Physical sampling, RNG, perturbation definitions, cancellation,
neural training code, fitting roles and thresholds are unchanged.

## Positive checks and evidence boundaries

Only spec/mask/residual cross the model input boundary. Labels, scenario
IDs and plan-consistency targets are bookkeeping, with permutation tests.
The replay has no belief argument; physical IQ is read-only, and the
receiver gets calibrated co IQ, corrupted co belief and frozen P20 config.
`authorize_intruder` deliberately uses privileged true carrier parameters
to construct the controlled test intervention. It is not a deployable
oracle detector and must not be described as having no simulator truth
anywhere in the experiment.

Physical-IQ invariance evidence consists of the replay/receiver boundary,
runtime assertions and physical tests with before/after IQ hashes and
simulator/canceller spies. Pilot JSON persists PSD/mask/residual/metadata
parity, not raw IQ or per-scene IQ hashes. These evidence types stay separate.

E1 fully verifies known/matched shard checksums and contents before complete
result reuse. Replay also checks generator, calibration and cancellation
identity. Frozen run-file hashes enter the experiment fingerprint, so
modified checkpoint/scorer/calibration/config/results cannot reuse it.
No test/matched fitting or threshold selection was found. Clean alarm and
known-acceptance rejection calibrations remain distinct.

Group bootstrap resamples scenario IDs together, uses explicit sample and
scenario denominators and gives null intervals below two groups. Matched
clean/other-known/rejected predictions remain in the denominator.
Bootstrap conditions on the fitted scorer and threshold; training,
calibration, simulator and field uncertainty are absent.

## Independent commands actually run

All runs used Python at `/workspace/.venvs/geosim/bin/python`, with
OMP/OPENBLAS/MKL threads2 and Agg rendering. Logs and measurement records
are under the ignored `/tmp/b2-e4-review/` directory in this workspace.

- Initial merged code: plan/eval/negative/resume/summary modules,
  **78 passed in62.68s**, process65.717846s, peak428504KiB, exit0.
- Post-fix focused modules excluding real RF replay: **116 passed
  in247.13s**, process249.878580s, peak431204KiB. Pytest exit0;
  the wrapper returned9 because only summary source/test changed during
  the run. This is not a certificate of every final file.
- Final affected summary regression (three node IDs, including a two-case
  parametrization): **4 passed in49.80s**, process52.207503s,
  peak437412KiB, pytest/wrapper exit0, source/test hash guard stable.

```bash
/workspace/.venvs/geosim/bin/python -m pytest -q \
 tests/test_b2_a5_summary.py::test_uninventoried_or_partial_results_never_claim_full_matrix_completion \
 tests/test_b2_a5_summary.py::test_checksummed_non_strict_json_is_rejected \
 tests/test_b2_a5_summary.py::test_invocations_without_scenes_are_counted_not_called_exact
```

The reviewer did not run an independent full repository suite or real RF
generation. The integrator's separate tests and actual bounded pilot are
in the [results note](../results/b2_a5_dual_pol_pilot.md).

Historical PR15 CI was independently checked: head
`a595bcfae465e30dd8263cbeb57fae29b7dc9102`, run39947778403,
job120394555595, success;95passed116.27s +1087passed234.45s, zero
skips/failures. This is evidence for the merged implementation, not the
new recovery PR head.

## Final numerical evidence closure

The reviewer separately read the final nine raw invocations, summary,
state and arrays; no new simulation, replay, inference, fitting or test
was started. Result:9invocations/36 selected scene-slots =32applied +4
not-applicable +0blocked;32physical replays/56cancellations/24receiver
recomputations/312scored sample evaluations. These are repeated evaluation
slots, not36 independent physical scenarios. All32 checked replays had
exact parity and maximum difference0dB. The matrix is PARTIAL9/25,
16pending, zero failed/missing, zero unavailable views.

All9 result sidecars/summary hashes,36state metadata fingerprints and32
NPZ checksums matched. Current source hashes, frozen checkpoint/scorer/
calibration files and independently recomputed experiment fingerprints
matched. Known fingerprint is
`1c510cd0d5eb76e4dc61d36497699fc9a938633f740bd375f2abd0a1f3928b81`;
matched fingerprint is
`6ff7970eb6f28e9a4780a588f2b9f4fde93d6b734aa2af3c42b4e5230a56bf4e`.

Every cached receiver-consistent PSD was bit-equal to its stored PSD;
cross-only/none cached residuals were bit-equal to stored residuals on
this exact-parity pilot. All none-condition logit displacements were0;
co/dual MASK_ONLY and RECEIVER_CONSISTENT logits were identical. Clean/
event denominators, zero-denominator nulls and group counts were checked.
No nested counterfactual accuracy field remained. Maximum reported process
RSS was742884KiB, below the planned1572864KiB bound. Sampling of the
matrix driver did not certify simultaneous child-tree memory; the result
uses per-invocation self RSS and waited-child peak accounting.

No material numerical evidence blocker remained. Two scenario groups, two
clean calibration observations and three-epoch stand-in models support
execution checks only. They cannot establish population Pfa5%, recognition
quality or robustness. Full matrix coverage and representative scientific
validation remain separate. K18/K17d/OBS-CANCEL/2 and production/GPU/LOKO
approvals remain unchanged; benchmark_complete=false.
