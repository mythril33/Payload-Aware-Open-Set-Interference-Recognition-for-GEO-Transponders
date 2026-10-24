# E12 — D-1–D-8 scientific decision ratification (2026-10-24)

**Verdict: SCIENTIFIC DECISIONS RATIFIED — EXECUTION NO-GO.**
**Researcher choices:** approved explicitly by the user in the conversation on
2026-10-24. **GitHub recording:** pending review of this dated addendum.
**Verified implementation base:** `a335eed5fd3ac22eb341aa7ecf148f4efe7bd023`.
[Machine-readable register](b2_e12_d1_d8_decisions_2026-10-24.json).

The authority source is the user-supplied **B2 — D-1–D-8 Birleşik Bilimsel
Karar Tutanağı**, v1.0, dated24 October2026, together with the attached E12
implementation instructions. The decision packet's SHA256 is
`9abeef0ba8229d8fbd9ec3788f7855cc7fa1efa9b9745fbaa84f66204ee9e96b`.
This records actual conversation provenance, not a cryptographic signature,
a fabricated per-decision timestamp or an execution authorization.

The [E10 decision packet](B2_E10_RESEARCHER_DECISION_PACKET.md) remains a
historical pending-options document. This addendum records the later explicit
choices. The [E9 approval](B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md)
and its R1–R10 parameter values are retained; amendments below are dated and
prospective. No historical pilot, observation artifact, numerical result,
source identity or approval timestamp is rewritten.

## Accepted choices and effect on R1–R10

| ID | Approved choice | Scientific requirement and rationale | Effect on existing commitments |
|---|---|---|---|
| D-1 | **A** | Preserve existing test roles with disclosed prior exposure and mandatory exclusion sensitivity rows. Preserve reproducibility without describing exposed groups as pristine. | R8's future final-read barrier remains; earlier reads are disclosed. No seeds, roles, headline counts or K17d definitions change. |
| D-2 | **1** | Conditional dual-polarization operator receiver: calibrated co/cross monitors and separately declared co/cross plans. State the actual input assumption. | R1 nine cells unchanged; `dual_residual` headline, `co` and `dual` comparators. P20 co-only cancellation retained. |
| D-3 | **A** | Auxiliary target denotes physically missing planned carrier, not arbitrary plan–spectrum misalignment. | R3/K18 target, BCE, center/CE loss and K17b augmentation unchanged. |
| D-4 | **1-FPR** | Near-family pooled unknown-positive FPR@95TPR on `dual_residual` is primary. Other reporting is exploratory. | R1 seeds0/1/2 and R8/R10 calibration retained; no seed selection or confirmatory superiority claim. |
| D-5 | **1** | Preregister receiver-level plan-error physics sensitivity only. Exact plan assumptions need explicit limits. | No R1–R10 change. Design details and every execution permission remain open. |
| D-6 | **A** | NumPy `higher` clean quantile and strict greater-than alarm remove order-statistic ambiguity. | Clarifies R10; retains E9's saturation-free score and all historical results. |
| D-7 | **B** | Default-deny legacy test observation access, with explicit restricted historical intent. Prevent accidental access through CLI or Python API. | Future R8 train/calibrate/freeze/evaluate guards remain independent; historical caps are not raised. |
| D-8 | **A** | Accept the frozen-generator-derived K17d identity record, conditioned on its source and audit bindings. | Dated amendment of K17d's metadata-source wording;500/35/465 unchanged, later production cross-check mandatory. |

### D-1 — prior exposure and required reporting

The preserved `B2-test/1` headline contains **500** scenario groups; the
test-matched role contains **150**. Test groups **3200000,3200001** and matched
groups **3300000,3300001** have already been exposed in historical pilot
outcomes; group3200000 also has committed observation-level spectrogram
content. The [E10 exposure ledger](B2_E10_RESEARCHER_DECISION_PACKET.md#d-11-what-was-exposed-verified-from-committed-artifacts-only)
documents those reads. The existing test population must **not** be called
pristine or entirely unseen. The documentary record cannot rule out prior
exposure influencing a reader; this decision does not retroactively prove
independence.

Every future authorized final report must include the500/150 headline and
mandatory **498/148** sensitivity rows excluding the four disclosed IDs by
identity, not outcome. K17d's headline500, co-feed35 and complementary465
rows remain unchanged and separately labelled; exposed test groups are not
in the35-group co-feed missing set. No new role, seed or silent
`B2-test/2` is introduced. Historical pilots remain pilots and their
reported numbers are not rewritten.

R8's freeze-before-read obligation applies to the **future separately
authorized final evaluation**. It must acknowledge, not erase, the earlier
pilot exposure. No held-out read is permitted by this addendum.

### D-2 and D-3 — receiver and auxiliary-target contracts

The operator is assumed to possess calibrated co-pol and cross-pol IQ/PSD
streams and **two separately declared polarization plans**. This is a
conditional receiver capability, not a claim about all GEO ground stations
or full DVB-S2 framing. `dual_residual` remains headline; `co` and `dual`
are comparators. All three views use seeds0/1/2, exactly nine planned fits.
The residual uses **co-pol IQ and the co-pol operator plan only**, via P20
`obs-cancel/1`; no cross-pol cancellation input, oracle symbols or P21b
receiver substitution is introduced.

`plan_consistency = int(dropped is not None)` means a planned carrier is
physically absent in the scene. K17b mask shifting changes the input belief
and preserves that physical-state target. The auxiliary head is **not** a
general plan–spectrum alignment detector. No label, loss weight, optimizer,
training configuration or augmentation definition changes.

### D-4 — primary endpoint and uncertainty

Primary endpoint: **near-family pooled unknown-positive FPR@95TPR** for
`dual_residual`. Pool only the P18 near families (`pulsed`,
`intermittent_bursts`, `adjacent_satellite_downlink`); `cid_overlay` is a
legitimate control and `wideband_noise` remains separately reported.
Unknown-positive TPR uses unknown samples; FPR uses known test samples.
Report both denominators, sample/group counts and unavailable values as
`null` with reasons.

Report seeds0,1,2 individually. Their arithmetic mean is a **descriptive**
headline summary, not a best-seed choice or seed-level confidence interval.
Scenario-group bootstrap resamples whole groups (preserving paired
variants) **conditional on frozen models and calibrators**; it does not
estimate training-seed uncertainty. AUROC, AUPR, Macro-F1, OSCR, operating
points, comparisons and ablations are exploratory. No confirmatory
superiority or unadjusted multiple-testing significance claim is approved.
Unknown-positive95% TPR is distinct from R10's95% known acceptance.

The accepted choice fixes the endpoint and model view but does not select
one primary scorer among MSP, energy and Mahalanobis. That designation and
the reporting freeze remain OPEN before any authorized final test read;
test-guided scorer selection is forbidden. No scorer choice is invented here.

### D-5 — preregistration only, no sweep permission

Prespecified perturbation values:

- Frequency error:0,±0.25,±0.5,±1MHz.
- Relative symbol-rate error:0,±1%,±2%.
- Roll-off error:0,±0.05.
- Modulation: correct and controlled mismatched declarations.

Only `train` and `val-select` would be eligible, with cancellation depth
and decision SNR as the only endpoints, supplementary/physical-sensitivity
reporting only. **SNR definition, controlled modulation pairs, sampling and
paired design, treatment of combined errors and CPU ceilings remain OPEN.**
No RF sweep, even a small CPU pilot, is authorized. No classifier training,
inference or held-out observations belong to this preregistration.

### D-6 and D-7 — thresholds and access intent

D6 ratifies `Pfa=0.05`,
`np.quantile(clean_scores,1-Pfa,method="higher")`, and alarm
`score > threshold`; equality is non-alarm. Use eligible **clean val-calib
only**; never test outcomes for threshold or hyperparameter choice.
E9's numerically stable `sum(P(non-clean))` is retained; it is
mathematically equivalent to `1-P(clean)` without subtraction saturation.
Calibration false-alarm fractions are not independent-test guarantees,
especially with tiny clean samples. Archived linear-rule/subtraction-score
pilot results are not relabelled or rerun.

D7 authorizes only the narrowly scoped fail-closed access-guard code and
synthetic CPU tests: legacy observation access defaults to denied through
both CLI and direct Python API. A default-false explicit historical-intent
flag may admit only already documented, bounded historical pilot identities,
subject to the existing `LEGACY_MAX_GROUPS` and all other caps. Unknown,
matched and alias paths must not bypass it. GPU/CUDA use is refused. The
flag grants no new held-out final evaluation, freeze, production, GPU,
training, LOKO, generation or run authorization. Actual observations are
not opened while implementing or testing this guard. Historical numerical
contracts remain; any source edit creates a new provenance identity and
historical checkpoints are refused rather than relabelled.

### D-8 — accepted metadata identity and mandatory future cross-check

Accepted immutable artifact:
[`docs/results/b2_e10_k17d_identity.json`](../results/b2_e10_k17d_identity.json),
SHA256 **`ccdf0a8f40e71d7ddb388068e455a77a131214f5644ab332a16c8268cfc49c6d`**.
Its generator metadata establishes500 headline groups,35 co-feed
missing-carrier groups (`pol==0`),43 cross-feed missing groups,78 total
drops and465 groups complementary to the35 co-feed set.

Acceptance is conditioned on the artifact's recorded three explicit source
hashes, **all28 geosim modules** package digest
`01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b`,
and [historical drift audit](../results/k17d_drift_audit.json) SHA256
`be4e2434bcd562f6521821da3403a5c5d5a14b8951ec6174ba0a795564fda65e`.
The register copies those bindings and identity fingerprints. They detect
mismatch, not cryptographic authorization or independent scientific truth.

This is **generator-derived metadata acceptance**, not observation-level
test validation or evidence that production metadata already exists.
The historical identity JSON remains byte-for-byte unchanged, including its
candidate/pending status and `authorizes: nothing` wording; acceptance
lives in this external dated record.

Before any separately authorized production final evaluation, compare this
accepted identity **fail-closed against actual production generation
metadata**: headline membership, unique sorted IDs, role, co/cross drop
predicate and source/audit identity must all agree. That future cross-check
is **NOT RUN**. A change to generator, predicate, package or relevant audit
hash requires re-derivation and independent review before reuse; this
addendum does not authorize such a run or silently re-version test roles.

## Unchanged authority and unresolved work

`full_generation`, `full_gpu_training`, `full_loko_sweep` and GPU probe
remain **NOT_AUTHORIZED**; compute approvals remain `null`. Final held-out
evaluation remains **NOT_AUTHORIZED**. `activation=false`,
`production_authorized=false`, `PRODUCTION_LAUNCH_ENABLED=False`,
`benchmark_complete=false`. No existing production or isolated-smoke cap is
raised, and production configs, frozen classes, seeds, physics, loss, P20
cancellation and approved training hyperparameters are unchanged. D7 adds
restrictive historical-access ceilings: CPU only, at most3 epochs, width8
and batch32; test identities are limited to3200000/3200001 and matched
identities to3300000/3300001. The existing `LEGACY_MAX_GROUPS=12` ceiling
is retained. These additional access limits are not new approved production
training parameters or execution authorization.

DR-04/DR-05/DR-06 host identities, resource ceilings, backup, GPU probe and
run-specific approvals remain unresolved. The reviewed production executor,
environment/source lock, completed nine fits, frozen cells, future
production-metadata identity cross-check and separate final-read approval
are still required. R6 TF32-off remains a scientific requirement; this
addendum does not claim a GPU runner already enforces it.
[E11-B pre-run checklists](../operations/B2_PRE_RUN_CHECKLIST.md) are
historical snapshots: D1/D4/D8 decisions are now recorded here, but none of
the operational OPEN rows becomes GO merely through ratification.

Implementation/test evidence belongs to the E12 verification report and
exact-head CI, not this approval record. No experiment completion or
recognition-performance claim is made.
