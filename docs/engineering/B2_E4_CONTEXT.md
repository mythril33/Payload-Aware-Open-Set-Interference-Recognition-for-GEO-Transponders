# B2 E4 context pack — dual-pol A5 operator-plan corruption

Status vocabulary: `VERIFIED` (checked in this session against code/tests), `IMPLEMENTED`, `BOUNDED_PILOT`,
`PLANNED`, `BLOCKED`, `APPROVAL_REQUIRED`. Updated as the work lands; the final state is in
[the pilot note](../results/b2_a5_dual_pol_pilot.md) and DURUM.

## 1. Starting point

| Item | Value | Class |
|---|---|---|
| Base | `main@ff81cae1b4e2563cc88271566665e9feae7cd44e` (after `git fetch origin main`, `origin/main == HEAD`) | VERIFIED |
| Working branch | `claude/dazzling-maxwell-y0hw0q` (harness-designated; the master prompt's `feature/b2-e4-dual-pol-plan-corruption` was only a recommendation, the designated branch takes precedence) | VERIFIED |
| Open PRs at start | none | VERIFIED |
| Python / platform | 3.13.16, Linux 6.18, 4 CPUs, 15 GiB, no GPU | VERIFIED |
| Env | `/workspace/.venvs/geosim`, `torch==2.14.1`, `numpy==2.5.4`, `scipy==1.18.1`, `xgboost-cpu==3.4.1` | VERIFIED |
| Existing data / checkpoints | none in the clone (`data/`, `runs/` are git-ignored) | VERIFIED |

## 2. Frozen contracts that bound E4

- **P18 §7a/§8:** A5 = stale (shifted), missing and extra declared carriers; the plan deviation is in the
  operator plan and the transmitted signal does not change; shift 0.5 MHz ≈ 2.7 bins; `drop_one` is the
  observational twin of `unauthorized`.
- **P20 / `obs-cancel/1`:** `cancel_planned_carriers(calibrated co-pol IQ, co-pol operator plan, config)`;
  residual stored as float16 PSD `[128,512]`; settings `srrc_span_symbols=10, phase_grid=16, iterations=3,
  edge_guard=512`. The canceller already accepts any positive-power plan; it validates f0/Rs/α/power/modulation/
  monitor band, not unit total power. Never replaced by `obs-cancel/2` (APPROVAL_REQUIRED, pending).
- **P23 §E4:** perturb both descriptors, recompute the residual on the 5-channel path, mask-only = labelled weaker
  control, freeze checkpoints/calibrators, never touch the received observation, preserve group ids.

## 3. Verified code facts used by the design

| Fact | Location | Consequence |
|---|---|---|
| Observation = `spec[N,2,128,512]` f16, `mask[N,2,512]` f16, `residual[N,128,512]` f16; axis 1: co, cross | `geosim/b2_dataset.py` `_read_part` | `ObservedInputs` has exactly these three arrays |
| IQ exists only with `keep_iq=True`; B2 generation drops it right after `cancel_planned_carriers` | `b2_dataset.generate_b2_dataset` | replay recomputes IQ deterministically, never reads it from the artifact |
| Calibration is the artifact's own `receiver_calibration.npz` (bound to the request, checksum-verified) | `b2_dataset._calibration` | replay reuses it, never fits a new one |
| Physical plan, activity, events live in `B2Scene`/metadata; operator masks are `plan_mask_db(plan)` of the **full** plan, missing carriers stay in the plan | `b2_scenarios.py`, `dual.py` | belief ≠ physical type: `OperatorPlans` is separate; `simulate_dual` validates unit power, the canceller does not |
| `simulate_dual` mask output comes from the physical plans | `dual.py` | corrupted masks are rebuilt outside the simulator |
| Known `unauthorized` event record carries `f0, symbol_rate, alpha, mod, c_over_i_db` | `interferers.modulated` | `authorize_intruder` intervention source (replay layer only) |
| Checkpoint provenance = `{protocol, data_fingerprint, roles, source_files_sha256}` with hashes of **every** `src/**/*.py` | `geoml/b2_experiment.py`, `experiment._source_identity` | E4 may not edit existing source files; new modules are allowed by the provenance rule of P28 §6 |
| Geosim request provenance = hashes of `src/geosim/*.py` and `data/*` | `geosim/dataset._generator_provenance` | E4 code lives in `geoml/` so artifacts generated on `main` keep their identity |
| `preprocess_dual` raises if a mask has no core bin; the carrier reference comes from the co-pol mask | `geoml/data.py` | mask corruption changes the normalization reference (reported, expected) |
| Cost per scene ≈ 3.0 s simulator + 1.34 s canceller | `docs/results/b2_production_budget.md` | the 16-replay / 24-cancellation caps bound a smoke to ≈ 1–2 min |

## 4. Design decisions

1. New code only: `src/geoml/b2_a5_plan.py` (pure belief transformation), `b2_a5_replay.py` (privileged replay,
   parity, receiver adapter), `b2_a5.py` (frozen-model evaluation, caps, CLI). No existing source file edited.
2. Privileged boundary: replay may use hidden scene state; only `ObservedInputs` reaches models and the canceller
   receives IQ + co belief + config. Event descriptors reach the model only through the intentionally altered plan.
3. Fail closed: wrong stage, calibration, cancellation version, generator drift, checksum, checkpoint provenance,
   replay parity, incomplete outputs.
4. Reporting never promotes counterfactual agreement to accuracy (P28 §7).

## 5. Risk register

| Risk | Mitigation / status |
|---|---|
| Replay differs numerically from the stored shard (different BLAS/FFT) | parity policy with fail-closed tolerance; exact on the generating machine — VERIFIED in the pilot (see results note) |
| Stale residual reused after a co-plan change | adapter tests count canceller calls; MASK_ONLY labelled separately |
| Counterfactual label ambiguity | descriptive agreement metrics only; transition matrices |
| Canceller rejects a meaningful belief plan | `blocked` + message counted; algorithm untouched |
| Provenance break from adding source files | additions-only rule (P28 §6) and no edits to existing sources |
| Small populations mistaken for evidence | caps, pilot labelling, null CIs below two groups |
| Pilot checkpoints are chance-level stand-ins | disclosed; outputs are interface checks, not recognition results |

## 6. Work packages, ownership, execution

Roles follow the master prompt. The runtime executed agents A–D sequentially in the integrator context (shared
tree, strict file ownership below); Agent E was run as an independent read-only reviewer.

| Agent | Role | Owns |
|---|---|---|
| A — RF physics & replay | deterministic replay, parity, P20 integration | `src/geoml/b2_a5_replay.py`, `tests/test_b2_a5_replay.py` |
| B — plan perturbations | frozen A5 semantics, masks, applicability | `src/geoml/b2_a5_plan.py`, `tests/test_b2_a5_plan.py` |
| C — evaluation & metrics | frozen-model paired evaluation, bootstrap, caps | `src/geoml/b2_a5.py`, `configs/b2_a5_smoke.json`, `tests/test_b2_a5_eval.py` |
| D — QA & CI | negative tests, strict JSON, workflow | `tests/test_b2_a5_negative.py`, `.github/workflows/b2-readiness-ci.yml` (additive) |
| E — red team | read-only review | `docs/research/b2_e4_red_team_review.md` |

## 7. Researcher authorization status

`FULL B2 PRODUCTION NOT AUTHORIZED — NOT STARTED` · `FULL GPU TRAINING NOT AUTHORIZED — NOT STARTED` ·
`FULL LOKO NOT AUTHORIZED — NOT STARTED` · K18, K17d, OBS-CANCEL/2 `PENDING_RESEARCHER` ·
`benchmark_complete=false`. The researcher authorized E4 engineering preparation and bounded validation only.
