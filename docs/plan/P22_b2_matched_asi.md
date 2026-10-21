# P22 — B2-match/1: the K17c level-matched ASI ↔ unauthorized set, matched evaluation and production readiness

Date: 2026-10-21. Parent protocol: frozen [B2/1](P18_b2_protocol.md) §4 (role `test-matched`,
groups 3 300 000–3 300 149), §6 (pre-registered confusable pair), §7a K17c. Builds on P19 (B2-base/1),
P20 (B2-feat/1), [P21a](P21_b2_test_families.md) (B2-test/1). The parallel observed-receiver
development stage of [P21b](P21_b2_observed_receiver.md) is not touched; both P21 documents keep their
file names and are listed as P21a/P21b in DURUM. `benchmark_complete` stays `false`.

## 1. Why a matched set

In the natural B2/1 distribution the `adjacent_satellite` (ASI) and `unauthorized` classes differ in two
cues: level (ASI C/I_psd mostly > 10 dB from the sourced geometry, unauthorized −3…10 dB) and placement
(ASI overlaps a planned carrier by 20–80 %, unauthorized sits in a free gap). P18 §6 pre-registers the pair
as confusable by design and K17c asks for a level-matched set so that only the placement cue remains. The
matched set is a controlled intervention; its conditional distribution is **not** a model of natural
operating levels and its results are reported beside, never instead of, the natural test role.

## 2. Contract of `B2-match/1` (`geosim.b2_matched_dataset`, scenes in `geosim.b2_scenarios`)

| Item | Value |
|---|---|
| Role / groups | `test-matched`, 3 300 000–3 300 149 (150 groups, pilot prefixes allowed) |
| Variants per group | `clean`, `adjacent_satellite`, `unauthorized` (labels stored as known indices 0, 6, 3) |
| Shared within a group | operator plans (`default_plan(2g)`, retries `[g,1810,retry]`), link draws `[g,1801]`, carrier/noise/phase streams, missing-carrier state `[g,1813]`, receiver calibration and cancellation setting of the bound known artifact, symbol rate, roll-off, modulation, one C/I_psd target |
| Matched draw | RNG `[g, 1840]`: C/I_psd ~ U(4, 13) dB; (Rs, α) uniform among pairs feasible for **both** placements; modulation uniform; ASI centre uniform among overlap-20–80 % grid positions; unauthorized centre uniform inside a feasible free gap with the A1 guard |
| Requested power | `mean_psd_plan · Rs · 10^(−C/I_psd/10)` for both events, relative to the unit planned uplink load (identical to 1e-12 by construction and asserted on read) |
| Injection | both at the co uplink before the payload; the ASI uses `asi.adjacent_satellite_uplink_at_level` (level imposed, `geometry: null`, `level_source: matched_intervention`), the unauthorized uses `interferers.modulated` with `psd_offset_db = −C/I_psd` |
| Difference | frequency placement only (ASI overlap ∈ [0.2, 0.8]; unauthorized overlap = 0 inside a gap) |
| Plan conditioning | plans are redrawn only when no (Rs, α) admits both placements (4 of 150 frozen groups needed a redraw; recorded) |
| Bins | frozen `[4,7)`, `[7,10)`, `[10,13]` dB, stored as `matched_bin`; over the 150 frozen groups the draw gives 50 / 54 / 46 groups |
| Natural-range flags | per group: target inside the natural ASI range (2.5–33 dB) and inside the natural unauthorized range (−3…10 dB); targets above 10 dB lie outside the natural unauthorized range by design |
| Arrays | `spec[N,2,128,512]`, `mask[N,2,512]`, `label`, `seed`, `plan_consistency`, `matched_bin`, `residual[N,128,512]` when bound to B2-feat/1 |
| Metadata | every record carries the identical `matched` block (`pair_id = "B2-match/1:<group>"`, target, bin, carrier descriptor, requested power, both centres, gap, natural flags, limitation note) |
| Binding | known protocol, data and request fingerprints, calibration copied from the known artifact; different physics or canceller settings are refused |
| Validation | pairing across variants (plans, activity, config, matched block, requested power, (Rs, α, mod), ASI overlap, unauthorized gap + guard), per-record scene/event checks, cancellation provenance, bins vs metadata, duplicate (group, label) detection, nonfinite values, foreign role directories, resume by identical request |

```bash
python -m geosim.b2_matched_dataset --out data/b2-match-pilot --known data/b2-feat-pilot \
    --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1
python scripts/check_b2_matched.py --matched data/b2-match-pilot --out runs/b2-match-pilot/matched_check.json --oracle-groups 2
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot \
    --unknown-data data/b2-test-pilot --matched-data data/b2-match-pilot --out runs/b2-full-pilot
python scripts/profile_b2_generation.py --stage matched --known data/b2-feat-pilot --config configs/b2_base.json \
    --cancellation configs/cancellation.json --groups 20 --groups-per-shard 4 --out-data data/b2-match-profile --report runs/profile/matched_20_cancel.json
```

## 3. Is the pairing real? (acceptance evidence)

The acceptance tests separate four questions (`tests/test_b2_matched.py`, `scripts/check_b2_matched.py`):

1. **Requested interference power** — identical by construction (same formula, same inputs); asserted to
   1e-12 relative in the reader and the physics script.
2. **Reference normalization** — both relative to the unit planned uplink load and the same plan mean PSD
   (`total_planned_uplink`), the same reference the known classes use.
3. **Realized power after the physical chain** — the oracle diagnostic (`--oracle-groups`, simulator truth,
   report only) measures the injected waveform power before IMUX/TWTA: identical for both events
   (+0.04 and +0.17 dB over the request in the two pilot groups, from finite symbol statistics; same value
   for ASI and unauthorized). After the nonlinear payload the stored spectra show the **observable** rise
   over the clean twin in each event's own band. In pilot group 3300001 (ASI overlap 0.25 with a
   transmitted carrier) the ASI rise is 3.5 dB against 10.1 dB for the unauthorized carrier, because the ASI
   band already holds planned carrier power. In pilot group 3300000 the ASI overlaps the group's *dropped*
   carrier, so both bands are at the noise floor in the clean twin and the two rises differ only by the
   clean-twin level difference of the two bands (1.45 dB; the absolute in-band PSDs differ by 0.07 dB).
   In the stored cancellation residual the two events sit within ≈ 1.5 dB of each other (13.9 vs 15.1 dB;
   10.1 vs 10.0 dB), i.e. once the planned carrier is removed the matched interferers are at near-equal
   residual level and the remaining placement cue sits in the plan mask.
4. **Remaining differences attributable to placement and nonlinear interaction** — plan overlap fraction,
   the clean level difference between the two bands, and the widest-gap floor shift are reported per
   group; they are the intended intervention plus a small group-dependent IM term.

## 4. Matched evaluation (`geoml.b2_experiment --matched-data`)

With the frozen checkpoints, Mahalanobis scorers and val-calib thresholds of each view (no training,
selection or calibration on the matched set; binding, physics, canceller and role checks as for the
test-only families):

- unconditional 3 × 8 confusion and, per method, a 3 × 9 confusion with a `rejected` column;
- the 2 × 2 among the pair with explicit counts of predicted clean, predicted other-known, predicted pair
  class and rejected (denominator = all pair samples; nothing dropped), pair accuracy overall, among
  pair-class predictions and among accepted samples;
- per-class recall and precision with scenario-group bootstrap CIs (`null` below two groups);
- everything per frozen bin with group and sample counts;
- comparison with the natural `test` role: ASI and unauthorized recall overall and restricted to natural
  samples whose own `c_over_i_psd_db` falls in each bin (n reported; empty in pilots);
- representative paired spectrograms by a predeclared rule (`default_rng([20261021])`, up to three groups
  per bin), written under `figures/` with the selected groups and their predictions in `results.json`;
- pair metrics per `plan_consistency` and for ASI variants over an absent carrier (K17c intersections);
- the same scenes for every view; `results_summary.json` keeps the matched metrics except the unconditional
  3 × 8 `confusion` block (the rejection-aware 3 × 9 block survives) under the fixed dropped-key rule.

## 5. Evidence

See [the matched pilot report](../results/b2_matched_pilot.md) and the
[production budget](../results/b2_production_budget.md). Two-group pilots and a 20-group profile cannot
establish separability; with 16 training observations the checkpoints are at chance and every matched
metric is execution evidence only.

## 6. Decision audits (no protocol change; researcher decisions)

### K18 — training-loss weights (provisional, not approved)

Two conventions now exist in the repository: P20 `geoml.train` uses `center_loss_weight · Σ_d (e_d − c_d)²`
(squared Euclidean distance, Wen et al. form) with 0.005; the P21b observed stage uses 0.01 × the mean over
dimensions. For D = 16·width the two differ by D/2: 64× at width 8, 128× at width 16. Scaling: the center
term equals λ·D·σ²_within (sum convention) or λ·σ²_within (mean convention), where σ²_within is the per-dimension
within-class variance of the embedding; its gradient on the embedding is 2λ(e − c) per sample versus the CE
gradient of order ‖W‖/N on the logits, so the effective pull depends on the learned embedding scale, which
has no anchor (mean+max pooled ReLU features, no normalization). Measured on the pilot inputs
([k18_init_scale.json](../results/k18_init_scale.json), three random initializations recorded per seed;
[k18_scale_audit.json](../results/k18_scale_audit.json), trained pilot checkpoints): the embedding rms is
0.03 at initialization and 0.05–0.06 after the degenerate three-epoch pilots; the unweighted squared-distance
sum is 6·10⁻⁴ at initialization and 2·10⁻⁴–5·10⁻³ on the trained checkpoints, so the weighted center term is
≤ 3·10⁻⁵ (0.005 × sum) and ≤ 4·10⁻⁷ (0.01 × mean) against a CE of 2.08, negligible in both conventions
**at these scales**; the pilots cannot calibrate λ. Risk: with the sum
convention the term grows with D and with the embedding norm, so a model that expands its features would
feel a 0.005 weight strongly while a collapsed one feels nothing. Recommendation (awaiting approval): keep
the squared-Euclidean (sum) convention and λ = 0.005 as pre-registered, log the center/CE ratio per epoch
on the train split during the first full-scale run as a diagnostic only, and treat λ as frozen unless that
diagnostic shows the term dominating (> 50 % of CE) — any change would be a P18 §10 entry before any test
evaluation, never a search. The plan-consistency BCE weight 1.0 is unproblematic in scale (one binary term
beside an eight-class CE). Both remain **awaiting approval**.

### K17d — missing-carrier level drift of the downlink ASI family

Audit over the 500 reserved test groups with the predeclared draws only (`runs/k17d_drift_audit.json`,
no waveforms): 78 groups (15.6 %) drop a carrier; 35 drop a **co**-feed carrier, 43 a cross-feed one. Only a
co-feed drop changes the co feed power that scales the downlink event: drift = 10·log10(1/active co power),
median 0.71 dB, 90th percentile 2.93 dB, maximum 5.91 dB over those 35 groups (7 % of test groups). Cross-feed
drops leave the co reference unchanged (< 0.01 dB through the 30 dB uplink coupling). Assessment:
the pairing hypothesis ("same C/I_psd, only the injection point differs") holds exactly in 93 % of groups and
is biased low by up to 5.9 dB in the rest; the drift is physically meaningful at the top of that range
(comparable to the matched bins' width) and is documented, not dismissed. Options for the researcher:
(a) keep K17d as frozen and report the 35 drifting groups as a labelled sub-row (the metadata already carries
`effective_c_over_i_psd_db`); (b) a separately versioned `B2-test/2` that scales the downlink event by the
nominal unit load instead of the realized feed power, which restores exact pairing but changes the P15
"wanted feed power" convention; (c) a sensitivity row excluding the 35 groups. Recommendation: (a) now, (c)
as a reporting row, (b) only if the pre-registered §6 question turns out to hinge on those groups.

### OBS-CANCEL/2 — phase tracking

`obs-cancel/1` fits one complex gain per 42.7 µs snapshot; with the frozen 150 Hz effective linewidth the
depth ceiling is ≈ 21–25 dB regardless of C/N (P20 §8). Does it threaten the main experiment? The matched
pilot shows the residual channel leaving both matched interferers at equal level (above), and the
pre-registered K9 question (CuC visibility) is answered at 0.99 → 6.46 dB median in P20; the ceiling limits
how deep the residual can expose weak (C/I > 25 dB) in-band events, which is exactly the regime P18 §2
chose to measure the identifiability limit. The ceiling therefore bounds sensitivity, not validity, and
must be stated whenever residual-based results are interpreted. Proposal for a separately versioned
`obs-cancel/2` (not implemented): per-segment decision-directed phase tracking (64–128 symbol segments),
acceptance criteria: synthetic depth ≥ 35 dB at 150 Hz linewidth and C/N 40 dB; gap-floor shift ≤ 0.1 dB;
paired CuC visibility not reduced on the P20 pilot groups; runtime ≤ 2× `obs-cancel/1`; no tuning on any
test family; new artifact stage name and P18 §10 entry.

## 7. Limitations

- The matched set imposes levels outside the natural unauthorized range for targets above 10 dB and
  below the typical natural ASI range for targets near 4 dB; per-group flags record this.
- Placement positions use the ASI grid (4001 points) and uniform gap positions; the matched carrier
  descriptor is drawn uniformly among jointly feasible (Rs, α) pairs. Joint feasibility (an overlapping
  position **and** a free gap with guard) is a strong narrow-carrier filter: over the 150 frozen groups the
  matched Rs is always ≤ 6 Mbaud and is 1.0 or 1.5 Mbaud in 75 of them, whereas the natural ASI in the test
  role spans 1–28.8 Mbaud (≈ 45 % above 6 Mbaud). The natural-vs-matched bin comparison therefore differs in
  carrier width as well as in level; the report's denominator string says so and the physics check writes
  the matched Rs histogram.
- **ASI over an absent carrier.** Overlap is defined against the operator plan (the class definition), and
  the shared missing-carrier draw can mute the very carrier the ASI overlaps: in 5 of the 150 groups
  (3300000, 3300007, 3300091, 3300104 fully; 3300011 partly) the ASI band holds no transmitted carrier, so
  the variant is observationally an unauthorized-like carrier under a mask that says "planned". This is the
  P18 §7a K17c intersection with the missing/extra-carrier cases and is **reported, not hidden**: the
  metadata records `asi_overlap_fraction_plan`, `asi_overlap_fraction_active` and
  `asi_overlaps_only_absent_carrier`; the runner reports pair metrics per `plan_consistency` and for the
  "ASI over absent carrier" subset separately.
- No geometry is drawn for the matched ASI; antenna-related metadata is null by design.
- Realized post-payload levels are observable only as in-band rises; the oracle diagnostic measures the
  pre-payload injected power and is never stored with the data.
