# P31 — E7b isolated training, frozen evaluation and bounded LOKO

Engineering execution contract, revised for delivery on the newer merged
base. The scoped-role loader and an earlier phase prototype were developed
during the initial audit; this document grants no scientific approval.
Delivery base main: `ed65eb54632fc4373accebc88452ddf0ff9fadfe` (PR22/23 merged).
The earlier local draft and tests were preserved when integrating this newer base.
Versions: **B2-isolated-execution/1**, **B2-LOKO-matrix/1**. These are
execution/state contracts, not changes to frozen P18/P20 physical or loss
semantics. No parameter or R1–R10 choice is approved/frozen by this document.
K18/K17d/OBS-CANCEL/2 remain pending; production generation/GPU/LOKO remain
unauthorized. `benchmark_complete=false`.

## 1. Separate phases and observation access

The additive canonical runner modes are train-only, calibrate, freeze and
evaluate; the existing small legacy coupled pilot remains available. The
legacy coupled entry is limited to 12 groups/role, preserving small pilot/
integration fixtures while refusing a production-sized bypass of the
nine-cell admission gate. This cap changes no artifact or physical role.
The scoped E1 loader verifies small whole-artifact request/calibration/
descriptor metadata but opens spectrum/residual/metadata rows only for
explicit requested roles. Its identity equals the canonical whole-artifact
fingerprint. Reading descriptor hashes is not reading held-out observations.

1. Train-only opens train and val-select only. Weights, auxiliary loss and
   Mahalanobis embedding statistics use train; checkpoint selection uses
   val-select macro-F1, preserving the existing first-maximum rule.
2. Calibration is separately invoked, opens known val-calib only and loads
   already frozen checkpoint/scorer objects. Existing P20 known-acceptance
   and clean-alarm threshold arithmetic stays unchanged and separate.
3. Freeze binds all phase marker hashes and complete file bytes. The proposed
   full-protocol inventory requires exactly co/dual/dual_residual × three
   explicit distinct seed values, nine unique cells, common configuration
   except view/seed, data/source/runtime identity and compatible calibrators.
   Renaming one checkpoint into another seed/view does not satisfy it.
4. Evaluation verifies every inventory cell before opening any held-out
   source or producing any test inference. It fits/selects/calibrates nothing,
   reuses frozen state and writes only a separate output directory. Known
   test, optional test-only and matched artifacts must share the proper data,
   cancellation and reserved group bindings. Training inputs stay read-only.

Incomplete/non-strict/foreign source, runtime, data, configuration or file
identities fail closed. A phase marker is committed last. No historical
checkpoint is relabelled after changed source hashes. A fixture inventory
may explicitly contain fewer cells but can never claim full-protocol admission.

Execution introduced here is capped CPU engineering smoke: at most two
scenario groups per role, two epochs, width 8, batch 32. No unrestricted
production launcher or GPU execution is added. Full nine-cell admission is
implemented and adversarially validated on stand-ins; it is not evidence of
nine production-trained models or an authorization to build/evaluate them.

## 2. Bounded LOKO orchestration

Plan all seven registered non-clean holdouts × three explicit seeds × the
requested views, deterministically. Each immutable cell binds canonical
data/source/configuration and the exact filtered role populations. Held-out
labels leave train, val-select, val-calib and train-derived statistics before
preprocessing; all eight test variants remain paired final bookkeeping.
Neither test results nor proxy unknown scores choose a seed, view or recipe.

Only an explicitly declared immutable selection of at most two unique cells
can execute per output root, CPU only, under the existing E2 group/epoch/
width/batch caps. Re-entry cannot append a third cell or switch selection.
Completed cells require native checkpoint/scorer/calibrator/result/prediction
validation and matching full-byte hashes. Incomplete or incompatible cells
are refused rather than silently fitted again. No optimizer resume policy
is selected (R9 is still a researcher decision).

Aggregation defaults to requiring every planned cell. Explicit partial mode
lists missing cells and reports no full-sweep completion. Per fold/view,
preserve seed-level metrics and paired scenario-group CIs, report seed mean/
SD separately, and use common group draws for mean-of-seed metric uncertainty
where estimable. Never concatenate scores across independently fitted seeds
or pool different held-out tasks into a misleading AUROC. Missing metrics
are null with reasons/counts. Bootstrap is conditional on frozen models and
thresholds; scientific population/seed uncertainty is not established by two
smoke fits. Full21-fit/63-fit GPU execution is not exposed.

## 3. Validation and decision boundaries

Use deterministic stand-in arrays/artifacts only, never real reserved test
observations to validate or choose this engineering change. Test actual
role reads, train-only statistics, frozen threshold arithmetic, all-nine
admission before first test read/inference, corrupt/partial/mismatched phase
state, read-only inputs, strict JSON, LOKO exclusion/group pairing/seed-view
identity, bounded status/reuse/aggregation and diagnostics noninterference.
Run focused numerical/negative tests and the feasible full regression.
Independent read-only review must resolve material findings before delivery.

The E7a candidate's 29 parameters and R1–R10 stay proposals. A separate concise
recommendation table maps the choices/alternatives/resource consequences;
width8 budget assumptions are not silently applied to width16 defaults.
No production config is frozen. E7a supervisor/interruption evidence is
audited, not repeated. PR23's refreshed raw journal/head and verification
tests supersede the earlier sanitized-only evidence; that merged evidence
is preserved. Non-default P6 choices or sizing rules need the prescribed
P18 section 10 entry and version before fitting, in addition to authorization.

## 4. Bounded usage examples (not production commands)

Use an already verified, separately identified two-group-per-role fixture.
No data generation command is provided here. The existing one-epoch,
single-view smoke config is reused as a fixture recipe, not a production
choice. Keep the library/thread environment identical across phases.

```bash
python -m geoml.b2_experiment --mode train-only \
  --config configs/b2_loko_smoke.json --data data/known-two-group-fixture \
  --out runs/e7b/train
python -m geoml.b2_experiment --mode calibrate \
  --data data/known-two-group-fixture --runs runs/e7b/train
python -m geoml.b2_experiment --mode freeze --bundle runs/e7b/train \
  --profile fixture --seeds 0 --out runs/e7b/inventory.json
python -m geoml.b2_experiment --mode evaluate \
  --data data/known-two-group-fixture --inventory runs/e7b/inventory.json \
  --profile fixture --out runs/e7b/evaluation

python -m geoml.b2_loko_matrix plan --config configs/b2_loko_smoke.json \
  --data data/known-two-group-fixture --out runs/e7b/loko --views dual_residual
python -m geoml.b2_loko_matrix run --config configs/b2_loko_smoke.json \
  --data data/known-two-group-fixture --out runs/e7b/loko \
  --cell cw__dual_residual__seed-0 --cell cw__dual_residual__seed-1
python -m geoml.b2_loko_matrix aggregate --config configs/b2_loko_smoke.json \
  --data data/known-two-group-fixture --out runs/e7b/loko --partial
```

The LOKO output is PARTIAL (2/21 cells), with null full-inventory metrics.
Default aggregation refuses it. Reuse requires `--reuse` with exactly the
same immutable selection. A proposed-full primary freeze omits the fixture
profile and requires nine compatible native cells across three explicit
seeds; an incomplete roster is refused before test access. All new execution
and verification remain subject to the bounded caps above.
