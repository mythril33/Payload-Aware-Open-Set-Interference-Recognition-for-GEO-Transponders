import csv, sys, os
V = "/tmp/claude-0/-home-user-Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/887ebf34-f8d5-57b7-91ca-a1a8ca1e286f/scratchpad/verify/redteam_findings.csv"
OUT = sys.argv[1]
rt = {r["issue_id"]: r for r in csv.DictReader(open(V, encoding="utf-8"))}
D = {
"RT-01": ("Replaced the five-class scheme with two orthogonal axes (A: minimal observation set A0/A1-P,X,Q,H,G/A2/A-empty; B: dominant confounder B-N/B-P/B-I) plus a separate evidence status; distinguishability redefined with a total-variation margin at record length N (Eq. 9); Table 3, Table 6, Figure 4, Appendix D and MOE CSV rebuilt. Explicit derivations given for CuC, cancellation, cyclic, cross-pol and IM rows; other rows rest on stated assumptions.", "qualified"),
"RT-02": ("Sec. 1.3, 3.4 and 9.4 now acknowledge link-budget decomposition [N038; N006; N007] and model-based fault diagnosis (fault signatures, isolability) [N036; N037]; contribution narrowed to mapping these onto GEO ground-monitor observability with evidence grades; two concrete decision-changing cases added (downlink ASI invisible at large monitor; station-specific vs common cross-pol leakage). N036-N038 added from domain knowledge and not verified in this audit.", "qualified"),
"RT-03": ("Sec. 5.3 rewritten: periodogram-variance argument (4.34/sqrt(KM) dB), non-identifiability under host-level nuisance at any C/I, detectability only when 10log10(1+rho) exceeds level uncertainty; SNR-wall analogue cited [N035]; Table 3 CuC row and S3 updated.", "resolved"),
"RT-04": ("Eq. (2) now separates common uplink coupling kappa_u from station-specific leakage kappa_u,q; Sec. 4 and 5.3 add discriminators (leakage pattern across carriers, IMUX truncation, copied IM/noise floor, different down-converter LO); Table 3 adds station-specific vs common pair and assigns A1-X(+P) when one coupling dominates, A-empty only for comparable common-mode couplings.", "resolved"),
"RT-05": ("Uplink vs downlink ASI reclassified A1-G (second site, repointing, antenna geometry) with B-P only at a single fixed site and high back-off; Table 6 consistent.", "resolved"),
"RT-06": ("Table 2 legend redefined as discriminating power against Table 3 look-alikes; co-pol PSD re-rated (open circle) for unauthorized, ASI, cross-pol, IM, overdrive, broadband; S1 reworded to 'binary detection or closed-set classification'.", "resolved"),
"RT-07": ("Sec. 4 states uplink ASI is often co-frequency (CuC-like); Table 2 ASI PSD rated conditional; Sec. 4/5.1 add monitor-antenna discrimination limit (downlink ASI at customer sites may be unobservable at monitor) with S.465 pattern reference [N039].", "resolved"),
"RT-08": ("Table 1 regraded: trade/vendor E6, testbed E4, GNSS 'E5 other domain (temporal features)'; every cited cell carries a grade; Table 5 grades split per source.", "resolved"),
"RT-09": ("Abstract, S6 and Table 5 no longer list GNSS as mature rejection; new Table 5 row 'New-class adaptation (few-shot)' for [R034].", "resolved"),
"RT-10": ("Sec. 6.1 rephrased: operator practice is level/mask comparison [R002; R006]; CA-CFAR is the classical radar adaptive-threshold detector and a natural baseline [R010].", "resolved"),
"RT-11": ("Gap in Sec. 7.1 restated per dimension (i)-(v); D-4 code and programme jargon removed from Sec. 7.4/10.2/Table 6 ('receiver-consistent', 'clean-only'); Sec. 7.2 'building blocks for plan-conditioned models' replaced; Sec. 1.3 and status box now say the programme appears in Sec. 7.4 and 10.3.", "resolved"),
"RT-12": ("PIM and wideband-receiver nonlinearity added to Table 1, Fig. 2 and MOE CSV; sun transit added to benign look-alikes and Table 3. These are E1 physical inferences; primary PIM/receiver-nonlinearity literature was not searched (budget).", "qualified"),
"RT-13": ("phi_LO defined as the satellite receiver down-converter phase noise, per polarization receiver (phi_LO,co / phi_LO,x), placed in EP-P before the IMUX consistently in Eq. (2), Sec. 3.4, notation and Fig. 2; effect on co/cross correlation noted in Sec. 5.3.", "resolved"),
"RT-14": ("kappa_d now covers satellite transmit isolation and downlink depolarization only; monitor-feed leakage kappa_R assigned to EP-R inside R{.}; Table 3 adds 'monitor-feed leakage vs true cross-pol interference'.", "resolved"),
"RT-15": ("Sec. 7.4: FPR@95TPR described as a single operating point at a test-oracle threshold (AUROC is threshold-free); D_unk^near defined with sample-weighted pooling and per-family reporting; non-comparability with ID-positive FPR95 stated.", "resolved"),
"RT-16": ("Sec. 3.2 now: Saleh gives an equivalent I/Q form of the frequency-independent model and a separate frequency-dependent model.", "resolved"),
"RT-17": ("N010 (SM.1446) removed; near-saturation slope reduction supported by classical multicarrier TWT analyses [N032; R058] with explicit AM/PM contribution.", "resolved"),
"RT-18": ("[R063] now cited for amplifier nonlinearity being identity-bearing, which motivates varying payload parameters as a design recommendation; invalid 'supports randomization' transfer removed.", "resolved"),
"RT-19": ("Unverified load-bearing items flagged inline (R025-R027, R078-R081); exact Agon figures removed; N013 and N030 dropped; N017/N018 kept as novelty-limiting evidence with incomplete metadata (authors/venue unresolved).", "qualified"),
"RT-20": ("State name kept because it is mandated by the assignment, but Sec. 2.4 now defines it precisely as excerpt-level confirmation of a publisher/registry record that was not opened.", "qualified"),
"RT-21": ("Search tool named (Claude Code WebSearch, engine undisclosed), non-determinism stated; 14 planned query strings for unexecuted topics (novelty, polarization, PCMA, cyclostationarity, datasets, sim-to-real, conformal, energy-vs-DL) added to the search log.", "resolved"),
"RT-22": ("Discrepancy (74 + 134 logged queries vs reported 200-call limit) disclosed in Sec. 2.6 and Sec. 11; it could not be resolved from the logs.", "qualified"),
"RT-23": ("Figure 1 and Table A1 regenerated from the same computed counts (screened 62; retained RF 14, ML 14, standards 1; repository 2; red-team additions 5).", "resolved"),
"RT-24": ("Abstract now states partial metadata-level re-verification (82 of 106 reached, none full-text).", "resolved"),
"RT-25": ("Appendix B corrected: R047 removed from replaced-version list; CID note reworded as removal of the fixed-level statement; R038 now carries the state of its corrected record with the contradiction kept as history.", "resolved"),
"RT-26": ("Cross-references fixed (leakage rules -> Sec. 7.6; programme references -> Sec. 7.4 and 10.3).", "resolved"),
"RT-27": ("Sec. 8.3 rewritten without 'rows'; qualitative summary only.", "resolved"),
"RT-28": ("Condensed MOE matrix added as Appendix D (Table D1); Sec. 9.1 now says Tables 1-3 and 5 are its views.", "resolved"),
"RT-29": ("Notation revised: CFAR set W_i, roll-off beta_rc, known-class count L, known-confidence score Q(x), test sets D_kn/D_unk/D_unk^near; added T_E, c, N, P_j, psi/Psi/O, d_TV, epsilon, tau, t_95, g_c, kappa_u,q, kappa_R; XPD/XPI glosses aligned with co/cross definitions and XPI now used in Sec. 4; N_0 units normalized.", "resolved"),
"RT-30": ("Eq. (3) now includes channel-amplifier gain g_c (fixed or level-controlled); Eq. (6) defines P_out as total mean output power including IM and amplified noise.", "resolved"),
"RT-31": ("Table 1 CW row: EP-U1 or EP-D (terrestrial at monitor); overdrive cause includes EP-P (commanded gain).", "resolved"),
"RT-32": ("Handled by the RT-01 restructuring: overdrive vs broadband A1-P (B-P,B-I); pulsed vs TDMA A1-P/Q (B-I); CuC vs PCMA/CID A1-P or A2 (B-I).", "resolved"),
"RT-33": ("Table 2: payload IM spectrogram rated open circle (co-variation with carrier activity); cross-pol rows plan rated filled (cross-pol plan).", "resolved"),
"RT-34": ("Table 6 column renamed 'Related axes'; non-pair gaps marked '-' with gap type.", "resolved"),
"RT-35": ("Sec. 5.3 adds E1 cancellation-depth derivation (eps^2+theta^2; 1 deg -> -35 dB; 0.1 dB -> -39 dB; >20 dB suppression for C/I=20 dB), SNR-wall reference [N035] and conditional SCF record-length scaling (N ~ rho_eff^-2 under a stated Gaussian-background model).", "resolved"),
"RT-36": ("Added Scheirer 2013 [N034], Shimbo 1971 [N032], Benedetto-Biglieri-Daffara 1979 [N033], Maral-Bousquet-Sun [N038], ITU-R S.465-6 [N039], Basseville-Nikiforov [N036], Gertler [N037], Tandra-Sahai [N035]. Not added (metadata could not be checked; search budget exhausted): ITU-R P.618/P.310/S.524, Gardner 1988, Spooner co-channel classification, MaxLogit, conformal prediction.", "qualified"),
"RT-37": ("Geifman and El-Yaniv now cited for i.i.d. calibration data; no exchangeability claim.", "resolved"),
"RT-38": ("S2 retitled 'Entry plane can alter the signature' with dependence on back-off, loading and filter position.", "resolved"),
"RT-39": ("'European' removed; text now says the guideline describes the values as typical near-worst-case values for its scenarios (search excerpt 'typical near worst case values'), and calls them scenario values, not thresholds.", "resolved"),
"RT-40": ("Table 4 Intelsat 37e row now says 'operational satellite path' and states that the transponder architecture (analog bent pipe or digital channelizer) is not established.", "qualified"),
"RT-41": ("Sec. 5.1 and Fig. 3 caption: 'grouped by kind and side-information needs'.", "resolved"),
"RT-42": ("Figure 2 caption: payload blocks follow DVB-S2/S2X reference chain; polarization couplings, entry planes and monitor receiver are this review's modelling convention.", "resolved"),
"RT-43": ("Table 3 CuC row now reads 'E3 on-board plane only'; Sec. 5.3 states R008/R009 operate before payload and downlink.", "resolved"),
"RT-44": ("'To be confirmed' phrases removed from citation text (kept in reference_master notes); D-4 code removed from body; generative-AI assistance declaration added. Author affiliation not supplied in sources and not invented.", "qualified"),
}
rows = []
for k in sorted(rt, key=lambda x: int(x.split("-")[1])):
    r = rt[k]; a, st = D[k]
    rows.append(dict(issue_id=k, severity=r["severity"], location=r["location"], problem=r["problem"], evidence=r["evidence"], action_taken=a, final_status=st))
INH = [
("INH-01","major","Baseline Sec. 1 (highlighted paragraphs)","SUIRG/Intelsat/IRG incidence percentages and '70-80%' used as quantitative evidence from trade sources (2005-2014).","refs R001-R004 are trade/vendor/newsletter (E6); review_findings F7.","Removed as quantitative evidence; trade sources described qualitatively with explicit E6 status.","resolved"),
("INH-02","major","Baseline Sec. 5 polarization equation","Single symmetric kappa applied after transponder outputs only; no uplink coupling, no downlink-entry interference.","review_findings F8, F17.","Layered model Eqs. (1)-(4) with kappa_u, kappa_u,q, kappa_d, kappa_R and i_d,l; entry-plane taxonomy.","resolved"),
("INH-03","major","Baseline Sec. 4-7 equations","Most equations stored as raw LaTeX text in the DOCX (only 3 OMML objects); CA-CFAR equation garbled (broken sum, 'P_F A').","pandoc export of baseline DOCX.","All 19 numbered equations and inline symbols rebuilt as native OMML (185 objects); CA-CFAR corrected with validity conditions.","resolved"),
("INH-04","major","Baseline Figures 2-3","Numerical Saleh AM/AM-AM/PM curves and a 'simulated for this review' three-carrier IM PSD without hashed source data; resemble measured results.","Task G; V4.1 note; xlsx inventory shows Saleh-based figures not matching repository default model.","Removed; replaced by conceptual diagrams (Figures 1-4) labelled as such.","resolved"),
("INH-05","major","Baseline Sec. 5","'DVB-S2X reference channel assumes cross-polar and co-channel negligible'.","review_findings F1; standards excerpts of TR 102 376-2 Sec. 4.4.1.3.","Removed; aggregate cross-polar model described with E2 status.","resolved"),
("INH-06","minor","Baseline ref [54]","Cited the 2020 DVB BlueBook draft instead of ETSI TR 102 376-2 V1.2.1 (2021).","V4.1 reconciliation; standards excerpts.","Official 2021 edition cited; draft identified.","resolved"),
("INH-07","major","Baseline Sec. 7 and refs [92]-[95]","Dataset licences stated as 'CC BY 4.0' / 'CC BY-SA 4.0' / 'licence per record' without verification; combined Fraunhofer citation.","batch-4 notes; paper/literature_audit.md; P8.","Exact titles; licence state reported as inconsistent/unresolved in Table 4 and Appendix B.","unresolved_external_dependency"),
("INH-08","major","Baseline Sec. 8 C1-C3 and comparison table","'This project: Yes' rows and 'has not been done' novelty claims presented as established; contributions stated as project claims.","review_findings F15/F16; paper/literature_audit.md:54-56.","Project rows removed; review contributions restated; programme confined to Sec. 7.4/10.3; novelty bounded by search limits.","resolved"),
("INH-09","major","Baseline Table 1 'Response to IBO' column","Response to drive treated as an operator observable.","review_findings F11.","Removed; plan is the practical observable; drive response noted as rarely available.","resolved"),
("INH-10","minor","Baseline Sec. 6","FPR at 95% TPR mentioned without positive class; OSCR 'FPR' naming conflict.","Task C D-4 requirement.","Eqs. (16)-(17) define UAR and unknown-positive FPR@95TPR with denominators; distinct from operational thresholds, AUROC, OSCR, accuracy.","resolved"),
("INH-11","minor","Baseline Sec. 7 payload gap","Delta(c) with f_full vs f_lin ambiguous about class set; risk of M-nl5 substitution.","P5_veri_protokol.md:19; Task E.","Eq. (19) restricted to four common classes with M-nl4 vs M-lin; M-nl5 separate; simulator-internal.","resolved"),
("INH-12","minor","V4.1 change summary","367-example data-pipeline pilot conflated with the model pilot.","repo_context: P5:83-98 vs docs/results/pilot_A.md:3.","V4.3 quotes no pilot figure; states pilots are pipeline trials, reported, not reproduced.","resolved"),
("INH-F2","minor","Ref R017 (Calian)","URL reported to redirect (review_findings F2).","review_findings.md:13.","URL retained; could not be re-checked (network policy).","unresolved_external_dependency"),
("INH-F20","minor","Sec. 6.3","Primary cyclic-feature references (CSPB.ML etc.) not added (review_findings F20).","review_findings.md.","Not added; search budget exhausted; listed as planned query.","unresolved_external_dependency"),
("INH-F32","minor","Ref R058","Fuenzalida-Shimbo-Cook 1973 content not verified (review_findings F32).","batch-3 notes: metadata via COMSAT index only.","Cited only for classical multicarrier IM/weak-carrier effects together with N032; content not verified.","qualified"),
("INH-F38","minor","DVB-CID","ETSI TS 103 129 should be primary source; CID level is a range (review_findings F38).","repository DURUM.md:299; P18:57.","N011 added (secondary); fixed 27.5 dB statement removed.","qualified"),
("INH-F44","minor","Missing reference","Zhou et al., IEEE TAES 2025, doi 10.1109/TAES.2025.3573297 suggested (review_findings F44).","review_findings.md.","Not added: title/authors could not be verified in this audit.","unresolved_external_dependency"),
("AUD-01","major","Whole bibliography","No full-text verification possible; 24 legacy references not reached; novelty search not executed.","Network policy; web-search budget.","Documented in Sec. 2.6, 11, Appendix B, provenance; claims qualified accordingly.","unresolved_external_dependency"),
("AUD-02","minor","Ref R090","Manuscript used RF-Analyzer as evidence of sim-to-real degradation; abstract reports successful generalization.","batch-4 notes.","Claim reversed; transfer evidence described as mixed.","resolved"),
("AUD-03","minor","Ref R008/R009","Decode-and-subtract attributed to SPAWC 2016 (pilot cancellation).","batch-1 notes.","Attribution corrected.","resolved"),
]
for t in INH:
    rows.append(dict(zip(["issue_id","severity","location","problem","evidence","action_taken","final_status"], t)))
with open(os.path.join(OUT, "red_team_issue_register.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["issue_id","severity","location","problem","evidence","action_taken","final_status"], quoting=csv.QUOTE_ALL)
    w.writeheader(); [w.writerow(r) for r in rows]
from collections import Counter
print(len(rows), Counter(r["final_status"] for r in rows), Counter(r["severity"] for r in rows))
