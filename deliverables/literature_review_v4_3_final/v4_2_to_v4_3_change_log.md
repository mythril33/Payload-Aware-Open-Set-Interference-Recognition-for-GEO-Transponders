# V4.2 → V4.3 change log

## 0. Which version this log starts from

The requested file `GEO_Payload_Aware_Interference_Literature_Review_V4_2.docx` does not exist. It was not on disk, in the repository history or on any remote branch, and no 112-reference version was found either.

The functional V4.2 baseline is therefore the researcher-supplied DOCX attached to this request:
- SHA-256 `66e12744…185f`
- last modified 26 Oct 2026, revision 38
- 95 references, 3 OMML equation objects

That DOCX belongs to the researcher's own editing line, which starts from the original 95-reference draft. In parallel, the earlier automated revisions produced:
- the V4 technical revisions (96 and 105 references)
- the V4.1 editorial DOCX (106 references, 17 OMML objects, verified corrections)

V4.3 merges both lines. It keeps the researcher's structure and voice where they were sound, carries over the corrections already verified in V4.1, and adds the work of this audit.

None of the original files was modified.

## 1. Scope and framing

| Change | Reason / evidence |
|---|---|
| Retitled "From Detection to Mechanism Diagnosis: …" (working title refined) | Single-satellite source identification from downlink observables already exists (N003), so "diagnosis" was narrowed to *mechanism* diagnosis (K7-compatible refinement; scope unchanged) |
| Converted from a project-positioning narrative (C1–C3 contributions, "This project" table rows) into a structured critical review with RQ1–RQ4 (RQ1 = approved K3 question) | K1, K3, K6. The experimental programme is now confined to Section 10.3 and labelled as design, not results. |
| Added an abstract, keywords and a manuscript-status statement | K7 journal format; K6 no new results |
| Added Section 2: a documented search and verification methodology with verification states, evidence grades, yield and limitations | K1, K5. Access limits are stated honestly. |
| Added Sections 9–12: the MOE synthesis, a validation-priority matrix, limitations and conclusions | K4, Task D |

## 2. Removed or qualified unsupported claims

| V4.2 statement | V4.3 action | Evidence |
|---|---|---|
| SUIRG "62%", Intelsat "33%/47%", IRG "40%/half of downtime", "70–80%" incidence figures, highlighted in the baseline | Removed as quantitative evidence; trade sources are described qualitatively | Trade/vendor/2005 sources (E6); review_findings F7; V4.1 had already removed them |
| "34% of incidents from unknown sources" used to motivate open-set recognition | Removed. An unattributed origin is not an unseen signal class. | review_findings F7 |
| "Even ML tools in operator workflows end in a fixed threshold [4]" | Reworded: R004 is a proposed or anomaly-detection account, not a deployed-tool statistic | review_findings F5 |
| "The desired signal is decoded and subtracted [8]" | Attributed correctly: SPAWC 2016 cancels pilot symbols [R008]; decoded-signal cancellation is [R009] | batch-1 verification notes |
| "Cancellation step is what makes low-power interference detectable at all" | Qualified to "makes … detectable under noise and signal-power uncertainty; imperfect cancellation sets a floor" | R008, R009 abstracts |
| DVB-CID "27.5 dB below the host" | Replaced by a symbol-rate-dependent range (about 17.5–27.5 dB) | R014 excerpt; ESA DVB-CID excerpt; repository record of TS 103 129 Table 6 |
| "DVB-S2X reference channel assumes cross-polar and co-channel contributions negligible" | Removed. TR 102 376-2 §4.4.1.3 models aggregate cross-polar interference (≈24 dB Ku, ≈17 dB Ka deep fade). | standards stream excerpts; review_findings F1 |
| "IMUX/OMUX group delay masks the TWTA characteristic" | Replaced by "filter–nonlinearity–filter interaction complicates compensation" | R056 context; V4.1 |
| "Noise power ratio measurements of space TWTAs [57]" | R057 is not cited (existence unconfirmed; it was a simulation per F3); NPR is now described through N008/N009 with caveats | batch-3 notes |
| "none of these studies includes … amplifier nonlinearity" | Qualified: real captures contain uncontrolled payload effects; Agon has a testbed; the gap is the absence of a controlled multicarrier payload comparison | review_findings F6, F16 |
| "simulation-trained models degrade … [90] reaches the same conclusion" | Corrected: R090 reports that synthetic-trained VLMs generalize to real signals; transfer evidence is described as mixed | batch-4 notes |
| "small CNNs suffice … [28], [45]" | R028 removed from that claim (it concerns accelerators) | batch-2 notes |
| "Monte Carlo dropout as reliability measure [32]" | Reworded to "uncertainty estimates" | batch-2 notes (MC dropout not confirmed) |
| "cyclostationary features improve generalization of deep modulation classifiers [44]" | Claim and R044 removed (no record found) | batch-2 notes |
| "survey identifies OSR as under-studied [47]" | Removed (not confirmable) | batch-2 notes |
| "We found no paper that formalizes …; closest is [67]" / "This mapping … has not been done" | Replaced by an access-bounded statement, explicit novelty-limiting sources (N003, N015, N017, N018) and "not identified in the reviewed evidence" | Sec. 9.4 |
| Table 1 with ● for "Response to IBO" | "Response to drive" removed as an observable (operators rarely know or control drive); new Table 2 adds cross-pol, contiguous IQ, host side information and external evidence | review_findings F11, F12 |
| "Adjacent-satellite and unauthorized share the same row … formal sense inseparable" | Replaced by conditional identifiability class I-d with the external evidence required | review_findings F13 |
| Agon "against 0.8318 for TrID-like baselines" | Clarified as Agon's own re-evaluation; figures labelled source-reported and not re-inspected in this audit | V4.1, batch-1 notes |
| Table 2 reported results (44% false-detection reduction, "up to 11%", 31.23%, 98.22%, 0.9883, 97.66%) | Only figures checked against a primary text are retained (Agon); the others are removed or described qualitatively | V4.1 policy; no full-text access |
| Figures 2–3 (Saleh curves; three-carrier IM PSD "simulated for this review") | Removed. They were numerical results without hashed source data, and they look like measurements. Replaced by conceptual diagrams. | Task G instruction; V4.1 |

## 3. Physics and mathematics corrections

The equation-by-equation detail is in `rf_and_mathematics_validation.md`. In summary:
- **Entry planes:** separate uplink and downlink cross-polar coupling, satellite LO phase noise, downlink-entry interferers and a receiver operator.
- **IM3 frequency set:** corrected.
- **C/IM slope:** stated as an asymptotic result.
- **Garbled CA-CFAR equation:** fixed, with its validity conditions stated.
- **SCF statements:** qualified.
- **OSCR false-positive naming:** separated from the unknown-positive FPR@95TPR (UAR vs FPR).
- **Energy score sign:** stated.
- **Mahalanobis:** described as a simplification of the cited method.
- **Payload gap:** restricted to the four-class matched design.
- **Equation format:** 19 numbered equations are now native Word OMML; in the baseline most were raw LaTeX text.

## 4. Original synthesis added (Task D)

- Table 1: RF entry-plane and payload-transformation taxonomy (EP-U0, EP-U1, EP-P, EP-D, EP-R).
- Table 2: mechanism-versus-observable matrix (13 mechanism rows, including benign look-alikes).
- Table 3: operational observability and identifiability matrix (14 confusable pairs), characterized on two axes, minimal observation set (A0/A1/A2/A∅) and dominant confounder (B-N/B-P/B-I), plus evidence status. This replaced a five-class scheme after the red-team review.
- Table 5: method-versus-evidence-quality matrix (E1–E6).
- Table 6: research-gap and validation-priority matrix.
- Figures 2–4 (entry planes, observation ladder, MOE framework) and Figure 1 (search flow).
- Machine-readable `mechanism_observation_evidence_matrix.csv`.

## 5. Bibliography

- **Totals:** 106 legacy stable IDs were reconciled; 102 are cited and 4 are not cited (R031, R044, R047, R057, with reasons); 36 new references were added (N001–N039 without N010, N013 and N030, which were dropped after the red-team review); the manuscript cites 138 references in total. N034–N038 were added from domain knowledge after the red-team review and are marked as not verified in this audit.
- **Published versions substituted for preprints:**
  - R007: IEEE Signal Process. Mag. 2019
  - R029: Intelligent and Converged Networks 2021
  - R030: IEEE COMST 2025
  - R043: IEEE TVT 2021, with the missing sixth author added
  - R036: ICL-GNSS 2025
  - R040: GNU Radio Conference 2022
  - R045: INFOCOM Workshops 2023
  - R059: IEEE TVT 2025
- **DOIs and pages added:** R061 (ISCAS DOI), R074 (pages and DOI), R091 (ACM DOI).
- **Titles corrected:**
  - R038: "… interference and jammer"
  - R092/R093: exact SmartSpace dataset titles
  - R095: split into three exact Zenodo record titles
- **Name corrections:** R021 (Ortiz-Gomez); R087 name order flagged.
- **Every entry** now carries its stable ID and verification state.

## 6. Red-team round

See `red_team_issue_register.csv` for the issues raised by the independent sub-agent review of the V4.3 draft and how each was handled. The changes made in response are listed in the register's `action_taken` column.

Main red-team-driven changes:
- **Identifiability.** The scheme was restructured into two orthogonal axes plus an evidence status, with distinguishability defined by a total-variation margin (Eq. 9).
- **Novelty.** The narrative now acknowledges link-budget decomposition and fault-diagnosis isolability.
- **Carrier-under-carrier.** The argument now separates effect size from identifiability: host-level nuisance, the SNR wall, a cancellation-depth derivation and conditional cyclic scaling.
- **Polarization coupling.** Station-specific uplink leakage ($\kappa_{u,q}$) and monitor-feed leakage ($\kappa_R$) are now modelled separately.
- **Gain and LO.** The channel gain $g_c$ was added and the down-converter LO placement corrected.
- **Ratings and grades.** Table 2 was re-rated for discriminating power, and the Table 1 and Table 5 evidence grades were corrected.
- **GNSS.** GNSS was moved from "rejection" to "new-class adaptation".
- **Metric.** The FPR@95TPR description was corrected (test-oracle operating point; pooling; non-comparability).
- **Payload plane.** PIM, wideband-receiver nonlinearity and sun transit were added.
- **Programme references.** Programme jargon was removed from the body.
- **Disclosure.** A generative-AI assistance declaration was added.
- **Status counts.** 48 issues are resolved, 11 qualified and 5 remain external dependencies (register totals, including inherited issues).
