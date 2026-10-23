# Fresh unified E4 and E5 scientific red-team — 2026-10-23

Independent read-only agent `e5_independent_review`, requested explicitly for final unified PR18/main
`79a17ccb0ba9967cc8a31156faab49510e360b3e`. The reviewer did not implement these changes or edit files.
This is independent engineering review within the agent workflow, not external scientific endorsement.
Read AGENTS/CLAUDE/.agents/review, P18/P20/P28, combined implementation, matrix/summarizer,
historical reviews and both committed pilot reports directly. Earlier branch reviews did not substitute
for this combined-code pass.

## Findings and dispositions

| Finding | Severity | Concrete correction |
|---|---|---|
| SceneState removed unrelated `state/*.tmp`; direct reproduction deleted operator_notes.tmp |P2 material engineering| cleanup now accepts only identity.json.tmp or numeric-scene-ID/known-label JSON/NPZ temporaries; preservation regression |
| Orphan `scene-*.npz` cleanup also deleted foreign scene-notes.npz |P2 same ownership defect| same numeric-ID/known-label validation before removal; foreign orphan preservation test |
| Completed checksummed result used permissive json.loads, accepting NaN/duplicate keys |P2 material reproducibility| use existing strict object reader; finite parse_float also rejects overflow1e999; parametrized negative tests |
| CFAR summary changed-scene count is max per-statistic, not union |scientific reporting| figure/atlas labels precise; no arithmetic change |
| FFT display extent shifted pooled centres by half original bin |figure accuracy| bin-centred edges−48.09375…47.90625MHz recorded and used |
| Independent zero/nonzero mode color scales obscured comparison |figure clarity| shared comparable mode/CFAR scales; readable luminance-based annotations |
| Request fingerprint alone did not separate E4 fixtures |provenance| explicit full known-data fingerprint added to E4 figure identities, plus source hashes |
| Streaming time includes four-role verification/load, not train-only work |denominators| per-role scene/group counts and fit/infer scope recorded |

No frozen physics, cancellation algorithm/version, role definition, perturbation/RNG, primary loss,
threshold or metric arithmetic was changed. Integrity changes intentionally change the source fingerprint;
historical pilots are not relabelled as fresh runs of this corrected source. Existing P28 source-reuse
checks remain strict: old E4 checkpoints/results cannot simply be reused under a changed source identity.

## Independently executed verification

Baseline stable source hashes: E4 evaluator
`f4b101c13c6de3b0dfec0c2f4d5eb216036e5ee5190eb08091f9b520f25c4d89`, matrix
`faeb7d90ffe786b6b78e7370b1ccbd58c27a24a996e9cd8971b3ff422b60eee5`, summarizer
`76c7ba86883cb8b083030e7fb845802331cbca8917275815f89fddbe54025b60`.

- State-integrity/matrix/resume/summary:56passed39.00s,exit0.
- Plan/replay/eval/negative:85passed104.01s,exit0; includes bounded real known+matched replay,
  read-only IQ checks, direct frozen-canceller equality, cross-only no-cancellation and tolerated parity.
- First corrected state-integrity/resume:31passed45.19s,exit0.
- Figure tests:6passed11.63s,exit0, stable source hash guard. Representative A2/B1/C1 regenerated twice;
  byte-identical three-format outputs,300dpi, source tampering, strict JSON, counts and gates verified.

Commands used the workspace Python3.12 venv with OMP/OPENBLAS/MKL2, CPU/Agg. No full RF generation,
training or LOKO. Final ownership extension and final artifact/document checks are recorded in the
delivery validation record after their execution; these earlier runs are not claimed as certificates
of files edited subsequently.

## Independent numerical audit

Both reports pass strict JSON/duplicate-key/finite checks. Recomputed per-invocation populations,
parity/work conservation, scene/group counts, alarm denominators, agreement counts and matched pair
denominators/naming. Unified summary SHA88bf7d2a...:25calls,100slots,90applied/parity,10NA,
154cancellations,64recomputations,870scored. Partial SHA289aedf4...:9calls,36slots,32applied/parity,
4NA,56cancellations,24recomputations,312scored. Each reuses8distinct physical scenes/fourIDs but has
different data/checkpoint fingerprints. No pooling. Baseline `_source_identity()` including Python
and bundled geosim/data exactly matches unified fingerprintfc03075d... .

Raw historical E4 invocation/state/NPZ are absent from this workspace. Fresh review therefore validates
committed summaries/source/internal consistency, not unavailable historical raw checksums. It independently
checked the existing separate physical artifact fingerprintdcffb264..., five original source hashes,
two correctly selected scenes, all8192pooled tile values by explicit block means, every512-bin PSD/residual
curve and mask (agreement within3e-14dB), without simulation/fitting. PNGs were visually inspected.

## Scientific judgment and remaining limits

No blocker found in frozen physics, role/group isolation, observable-only model boundary, environment
binding/resume, output locking, matrix real exit-code/coverage behavior, replay/cancellation invariants
or descriptive counterfactual arithmetic. Hashes detect integrity, not adversarial authentication.
Cross-machine parity is untested. Privileged intruder parameters enter only the declared test belief
intervention; raw IQ hashes are not persisted. Historical SIGKILL evidence predates unified scene-state/2;
current unified interruption behavior is exercised by fault-injection tests.

Figure values match verified sources. Binary alarm, multiclass classification and unknown rejection stay
separate; benignCID excluded, wideband noise separate, near pooling labelled. B5 is changed-feature
counts, not magnitudes; B7 is logit response, not tensor-input norms. Synthetic memory data is engineering
only. OpenDPD out-of-support points are flagged; NPR is standalone amplifier diagnostics. No statistical
confidence is invented; two groups/stand-ins cannot validate recognition, robustness or populationPfa.
Full production/GPU/LOKO and K18/K17d/OBS-CANCEL/2 remain gated; benchmark_complete=false.

## Final stable-source closure

Independent final affected regression: **37passed49.46s**,exit0,stable source guard
(state-integrity,resume,scientific-figures). All22figures/66outputs pass hashes,lengths,format signatures
and300dpi; all12source locks/strict JSON and renderer/manifest identities match. Full known/matched data
fingerprints are explicit. Gate decision objects equal origin/main; P18/P20/P28,cancellation,primary
training/loss/config,streaming and protocol files are byte-identical. Additional source-to-manifest audit
checked27neural open-set cells,15XGBoost family/pool metric cells,8binary-ranking cells and24matched
physical displacement cells exactly. Representative final PNGs were visually inspected and readable.

Final evaluator SHA256`64e24110cc7f08b45a5cb86827040b4ffbf46deacaa88596a7259f6852fa555f`;
renderer`667250bc68fa91b612e0057af7ba3b4cf149bb9ae275e11d6f9f8ee48c36a177`;
manifest`74ad2f7619890254cf841df04826564234f1f30c9bdc2a919dcd0399521c0cd7`.
No remaining material code/figure blocker for bounded reporting/draft delivery. The final scientific
recommendation clarification specifies36Mbaud/64symbols for the proposed35dB OBS-CANCEL/2 reference,
with lower-rate feasibility separate (phase-only ceiling depends on duration, not symbol count alone).
This is a memorandum qualifier only, not a receiver/protocol or authorization change.
