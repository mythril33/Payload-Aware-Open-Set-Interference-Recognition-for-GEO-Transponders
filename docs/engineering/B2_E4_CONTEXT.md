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
| Delivery | PR [#15](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/15) merged by the researcher as `4b736a6` (implementation head `a595bcf`, identical tree); follow-up evidence PR from the restarted designated branch | VERIFIED |
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
| Replay differs numerically from the stored shard (different BLAS/FFT) | parity policy with fail-closed tolerance; bit-exact on the generating machine for 90/90 pilot scene replays (BOUNDED_PILOT, see results note); cross-machine parity still untested |
| Stale residual reused after a co-plan change | adapter tests count canceller calls; MASK_ONLY labelled separately |
| Counterfactual label ambiguity | descriptive agreement metrics only; transition matrices |
| Canceller rejects a meaningful belief plan | `blocked` + message counted; algorithm untouched |
| Provenance break from adding source files | additions-only rule (P28 §6) and no edits to existing sources |
| Small populations mistaken for evidence | caps, pilot labelling, null CIs below two groups |
| Pilot checkpoints are chance-level stand-ins | disclosed; outputs are interface checks, not recognition results |
| `MASK_ONLY` shift equals the K17b training augmentation of the stand-ins | stated in P28 §2 and the results note; compare `MASK_ONLY` and `RECEIVER_CONSISTENT` shifts with this in mind |

## 6. Work packages, ownership, execution

Roles follow the master prompt. The runtime executed agents A–D sequentially in the integrator context (shared
tree, strict file ownership below); Agent E was run as a separate, independent read-only reviewer (first review of `8bedd2b`;
re-review of `a595bcf`/`4b736a6` after the fixes and the resumability feature; see the review record).

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

## 8. Resume / handoff (how to continue an interrupted E4 job)

State lives in Git (branch `claude/dazzling-maxwell-y0hw0q`; PR #15 is merged, follow-ups are new PRs) and in re-creatable local artifacts under the git-ignored
`data/` and `runs/`. Everything below is idempotent; re-running a command continues verified work and refuses modified work.

| Interrupted step | Continue with | What is reused / rejected |
|---|---|---|
| Pilot generation (`geosim.b2_dataset`, `b2_matched_dataset`) | the same command and output directory | verified shards; a directory with a different request or an unverified partial shard is refused (use a fresh directory) |
| Stand-in training (`geoml.b2_experiment`) | the same command with `--reuse` | checkpoints/scorers/calibrations whose provenance equals the data; mismatch is refused |
| One A5 invocation (`python -m geoml.b2_a5 ...`) | the same command and `--out` | per-scene `out/state/` entries (payload digest + array SHA-256, bound to the experiment fingerprint and library environment); the invocation's own uncommitted `*.tmp`/array files are discarded; modified or foreign entries are refused (digests detect accidental modification, they do not authenticate); a second concurrent process is refused by a lock; a complete checksummed result is reused after its identity verifies |
| The pilot matrix | `scripts/run_b2_a5_pilot_matrix.sh` | every invocation is handed to the CLI: finished ones are reused after identity verification, an interrupted one resumes at scene level, a changed identity is refused (use a fresh `OUT`); failures and missing results make the script exit non-zero |
| Summary | `scripts/summarize_b2_a5_pilot.py` (pure function of the invocation results) | refuses mixed identities |

Pilot environment (this session): `scripts/setup_cloud.sh`-equivalent venv at `/workspace/.venvs/geosim`; pilot data
`data/b2-feat-pilot` (`geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2
--groups-per-shard 1`), `data/b2-match-pilot` (`geosim.b2_matched_dataset ... --known data/b2-feat-pilot --limit-groups 2`), run directory
`runs/b2-feat-pilot` (`geoml.b2_experiment --config configs/b2_feat.json`, trained on the unmodified `main` source before the E4 files
existed; E4 allow-lists exactly three added files). A new session without these directories regenerates them with the commands above
(about 5 + 1 minutes of generation and 10 s of training on 4 CPUs); no full-scale generation, GPU training or LOKO sweep is involved.
