"""Generate CSV deliverables: reference_master, literature_search_log, claim_evidence_matrix, mechanism_observation_evidence_matrix."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refs_db
B = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(B, "build_meta.json")))
num = meta["num"]
db = refs_db.build()

def w(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, quoting=csv.QUOTE_ALL)
        wr.writerow(header)
        for r in rows:
            wr.writerow([r.get(h, "") for h in header])
    print(name, len(rows))

# ---------------- reference_master ----------------
recon = {e["stable_id"]: e for e in json.load(open(os.path.join(refs_db.REPO, "reference_reconciliation_v4_1.json")))["entries"]}
rows = []
for sid in sorted(set(list(db) + ["R031", "R044", "R047", "R057"])):
    r = db.get(sid)
    if r is None:  # R044 not in db
        e = recon[sid]
        r = dict(cit=e.get("publication_document_citation") or e.get("current_document_citation"), state="unverified", note="", legacy_status="verified-publisher (refs.json)",
                 v41_number=e.get("publication_number"), original_number=e.get("original_number"), evidence=e.get("url") or e.get("evidence", ""), claim_support="", claim_evidence="", content="", queries="2 queries; no matching record", origin="legacy")
    excl = refs_db.EXCLUDED.get(sid, "")
    rows.append(dict(
        stable_id=sid, v4_3_number=num.get(sid, ""), v4_1_publication_number=r.get("v41_number") or "", original_v4_number=r.get("original_number") or "",
        origin=r.get("origin"), cited_in_v4_3="yes" if sid in num else "no", exclusion_reason=excl,
        final_citation=r["cit"], verification_state=r["state"], legacy_manifest_status=r.get("legacy_status", ""),
        audit_note=r.get("note", ""), evidence_urls=r.get("evidence", ""), claim_support_snippet_level=r.get("claim_support", ""),
        claim_support_evidence=r.get("claim_evidence", ""), content_summary=r.get("content", ""), queries_run=r.get("queries", ""),
        full_text_access="not accessed in this audit (network policy); search excerpts only"))
w("reference_master.csv", ["stable_id", "v4_3_number", "v4_1_publication_number", "original_v4_number", "origin", "cited_in_v4_3", "exclusion_reason", "final_citation",
                           "verification_state", "legacy_manifest_status", "audit_note", "evidence_urls", "claim_support_snippet_level", "claim_support_evidence",
                           "content_summary", "queries_run", "full_text_access"], rows)

# ---------------- literature_search_log ----------------
allrows = json.load(open(os.path.join(B, "all_search_rows.json")))
INC = "Sec. 2.4 eligibility: topical relevance to satellite interference generation/propagation/detection/recognition/localization or directly transferable method; specific supporting or contradicting role; identifiable persistent metadata"
rows = []
for r in allrows:
    rows.append(dict(search_id=r["search_id"], stream=r["stream"], database_or_source=r["database_or_source"], query=r["query"], search_date=r["search_date"],
                     filters=r["filters"], n_results_returned=r["n_results_returned"], duplicates_existing_ids=r["duplicates_existing_ids"],
                     inclusion_criteria=INC, full_text_access="none (search-result excerpts only)", relevant_candidates=r["relevant_candidates"],
                     exclusion_notes=r["exclusion_notes"]))
for sid in sorted(db):
    if db[sid]["origin"] != "legacy":
        continue
    rows.append(dict(search_id="VER-" + sid, stream="Reference verification", database_or_source="WebSearch (general engine)", query=db[sid]["queries"] or "none (not reached: search budget exhausted)",
                     search_date="2026-10-26", filters="standard/extended as recorded in query string", n_results_returned="see bracketed counts in query field",
                     duplicates_existing_ids=sid, inclusion_criteria="verification of an existing reference", full_text_access="none (search-result excerpts only)",
                     relevant_candidates="", exclusion_notes="state reached: " + db[sid]["state"]))
for q in ["satellite interference classification transponder nonlinearity", "dual polarization interference classification satellite",
          "open set interference recognition satellite (IEEE Xplore and CNKI)", "interference taxonomy satellite communications survey",
          "observability interference satellite monitoring", "ITU-R P.618 depolarization XPD rain ice", "Dankberg paired carrier multiple access patent; Comtech DoubleTalk carrier-in-carrier",
          "Gardner spectral correlation of modulated signals 1986/1987; Gardner Napolitano Paura 2006", "PSD versus IQ interference recognition; wavelet interference analysis; monitoring receiver calibration",
          "conformal out-of-distribution detection thresholds", "Geirhos shortcut learning; RadioML synthetic-to-over-the-air shift; group k-fold leakage",
          "TorchSig Sig53; Jammertest dataset; NGSO interference dataset; OpenDPD dataset licence", "energy detector CFAR versus deep learning interference detection comparable",
          "ITU-R S.580-6/S.465 antenna patterns; S.1323 / RR Appendix 8 delta T/T; S.733 G/T"]:
    rows.append(dict(search_id="PLANNED", stream="Not executed (budget)", database_or_source="WebSearch (planned)", query=q, search_date="2026-10-26", filters="",
                     n_results_returned="0 (not executed)", duplicates_existing_ids="", inclusion_criteria=INC, full_text_access="", relevant_candidates="",
                     exclusion_notes="NOT EXECUTED: per-turn web-search budget (200) exhausted; required for completion of the novelty and primary-source search"))
w("literature_search_log.csv", ["search_id", "stream", "database_or_source", "query", "search_date", "filters", "n_results_returned", "duplicates_existing_ids",
                                "inclusion_criteria", "full_text_access", "relevant_candidates", "exclusion_notes"], rows)

# ---------------- claim_evidence_matrix ----------------
C = [
 ("C01", "1.1", "Operator/trade accounts associate GEO interference with terminal errors, cross-pol leakage, faults, ASI and unauthorized carriers; not incidence measurements", "R001;R002;R003;R004", "E6", "motivation only; no percentages used"),
 ("C02", "1.1", "Sustained intermittent interference against several commercial GEO satellites reported in 2026", "R005", "E6", "company report; not attribution evidence"),
 ("C03", "1.1/6.4", "Source identification and localization methods exist (TDOA/FDOA, single-satellite FoA, carrier matching)", "N001;N002;N003;R106;N031", "E1/E5", "metadata verified for N001,N002,N003,R106; N031 secondary"),
 ("C04", "1.2", "On-board detection is motivated by downlink noise and transponder distortion degrading ground detection", "R007", "E1", "snippet quote supports"),
 ("C05", "3.1", "IMUX-TWTA-OMUX cascade is the DVB-S2 reference satellite channel; EN 302 307-1 Annex H gives example curves; TR 102 376-2 V1.2.1 extends for S2X", "R052;R053;R097;R054", "E2", "edition metadata verified for R054,R097; R052,R053 not re-verified"),
 ("C06", "3.1", "Filter-nonlinearity-filter cascade has memory and complicates compensation", "R056;N005;R055", "E1/E3", "R056 secondary; N005 verified; R055 unverified"),
 ("C07", "3.2", "Layered per-polarization model Eqs.(1)-(4) with kappa_u, kappa_d, phi_LO, R{}", "", "E1", "modelling convention of this review"),
 ("C08", "3.2", "Saleh AM/AM-AM/PM forms; frequency-dependent model also in paper; coefficient provenance unresolved", "R051", "E1", "secondary_only; alpha_phi 4.0033 vs 4.033 discrepancy recorded"),
 ("C09", "3.3", "IM3 frequencies and asymptotic 2 dB/dB C/IM slope in weakly nonlinear regime", "", "E1", "derivation (cubic model)"),
 ("C10", "3.3", "Weak-carrier suppression and power robbing under multicarrier/near-saturation operation", "R058;N008", "E1/E3", "R058 metadata verified, content not; N008 NTRS verified"),
 ("C10b", "3.3", "Near-saturation C/IM slope reduction with AM/PM contribution (classical multicarrier TWT analyses)", "N032;R058", "E1/E3", "N032 secondary record; replaces N010 after red-team RT-17"),
 ("C11", "3.3", "NPR depends on test signal, notch and crest factor", "N009", "E6/E2", "vendor technical note"),
 ("C12", "3.3", "Payload chain modelled mainly for compensation; anti-jamming study notes missing transponder-nonlinearity modelling", "R055;R059;R053;N005;R060", "E3", "R060 snippet supports"),
 ("C13", "4", "Aggregate cross-polar C/I examples ~24 dB (Ku linear) and ~17 dB (Ka circular, deep fade) from three-term model", "R054", "E2", "search excerpts (V1.1.1, V1.2.1 draft) + inherited full-text check; power-sum arithmetic reproduces 24.03/17.07 dB"),
 ("C14", "4", "CID resolves identity when present; CID level 17.5-27.5 dB below host PSD depending on symbol rate", "R013;N011;R014", "E2/E6", "range per ESA/Via Satellite snippets and repository record"),
 ("C15", "4", "Blind detection of weaker PCMA carrier is hard", "R066;R067", "E1/E3", "R066 secondary; R067 unverified"),
 ("C16", "4/6.2", "Commercial monitors describe host/PCMA cancellation for CuC", "R015;R016;R017;R003", "E6", "vendor claims, not benchmarked"),
 ("C17", "4", "Cross-pol sources: polarization misalignment, antenna isolation, rain/ice depolarization", "R064;R065;R054", "E2/E3", "R064 rain supported; ice not in snippet; R065 authors unverified"),
 ("C18", "4", "Uplink ASI bounded by off-axis EIRP masks", "N012", "E2", "title to be confirmed"),
 ("C19", "4", "Aggregate 5G NR interference into FSS bent-pipe transponder uplink", "N004", "E3", "metadata verified"),
 ("C20", "5.3", "CuC PSD increase 0.043 dB at C/I=20 dB; resolvable by averaging (~4.34/sqrt(KM) dB) but non-identifiable from PSD when host level is a nuisance; SNR-wall analogue", "N035", "E1", "derivation; N035 added from domain knowledge (unverified)"),
 ("C20b", "5.3", "Residual host fraction ~eps^2+theta^2; 1 deg rms -> -35 dB, 0.1 dB -> -39 dB; CuC at C/I=20 dB needs >20 dB suppression", "", "E1", "derivation"),
 ("C20c", "5.2", "Identifiability defined with a total-variation margin; same notion as isolability in model-based fault diagnosis", "N036;N037", "E1", "N036/N037 added from domain knowledge (unverified)"),
 ("C20d", "3.4/9.4", "Link budgets already decompose uplink, payload and downlink contributions", "N038;N006;N007", "E2", "N038 unverified; N006/N007 metadata verified"),
 ("C20e", "4", "Downlink ASI depends on monitoring-antenna sidelobe discrimination", "N039", "E2/E1", "N039 secondary (repository record)"),
 ("C21", "5.3", "RRC-shaped linear modulation: non-conjugate cycle frequencies only 0, +/-1/Ts for 0<beta<1", "R011", "E1", "standard result; R011 secondary metadata"),
 ("C22", "5.3", "Pilot-symbol cancellation (SPAWC 2016) and decoded-signal cancellation (ICASSP 2017) for on-board weak-interference detection", "R008;R009", "E1/E3", "attribution corrected in V4.3"),
 ("C23", "5.3/6.4", "XPIC and wideband dual-pol compensation demonstrate synchronized dual-pol processing for recovery", "R103;N014", "E3/E4", "R103 not re-verified; N014 publisher page"),
 ("C24", "6.1", "CA-CFAR scale factor eta = N(Pfa^(-1/N)-1) for single-look exponential cells", "R010", "E1", "derivation; R010 secondary"),
 ("C25", "6.3", "SCF-input networks improve signal identification on real captures", "R043", "E5", "partially supported (snippet)"),
 ("C26", "7.1", "Satellite ML interference work predominantly detection (AE/LSTM, spectrum prediction, CNN localization, NGSO-GSO reconstruction, transformers)", "R018;R019;R004;R006;R020;R021;R022;R023;N016;R024", "E3/E5", "mostly metadata verified; R024 unverified in this audit"),
 ("C27", "7.1", "Closed-set classifiers of several interference types in simulated AWGN", "R025;R026;R027", "E3", "not re-verified in this audit (budget)"),
 ("C28", "7.1/9.4", "Source diagnosis from downlink observables already exists; class-incremental satellite interference recognition proposed", "N003;N017", "E3/E5", "narrows novelty; N017 metadata incomplete"),
 ("C29", "7.2", "GNSS real-data interference classification programme; few-shot adaptation rather than rejection", "R032;R033;R034;R035;R036;R037;R038;R099;R100", "E5", "MC-dropout wording removed (not confirmed)"),
 ("C30", "7.2", "Sim-to-real degradation for RadioML OTA; synthetic-trained VLMs reported to generalize (mixed evidence)", "R039;R089;R090", "E3/E5", "R090 claim corrected"),
 ("C30b", "7.3", "Open-set recognition formalized via open-space risk", "N034", "E1", "N034 added from domain knowledge (unverified)"),
 ("C31", "7.3", "MSP, ODIN, energy (negative free energy larger for ID), Mahalanobis (multi-layer original), OpenMax, ARPL, OE", "R070;R071;R072;R073;R074;R075;R101", "E1/E3", "energy sign confirmed in snippets"),
 ("C32", "7.3", "Good closed-set classifier matches many OSR methods; OSCR couples CCR and unknown acceptance", "R076;R077", "E3", "not re-verified in this audit (budget); widely known"),
 ("C33", "7.3", "Near-OOD harder; benchmark contamination; Mahalanobis fragility; KNN; position paper on irreducible errors", "N019;N020;N021;N022;N023;N024;N025;N026", "E3", "metadata verified"),
 ("C34", "7.4", "FPR95 positive-class conventions differ in literature; this review adopts unknown-positive D-4 definition", "", "E1", "definition; repository E12 D-4 wording"),
 ("C35", "7.4", "Calibration degrades under dataset shift; selective guarantees assume exchangeability", "N027;N028;N029", "E3", "metadata verified; Geifman bound stated as i.i.d. calibration (red-team RT-37)"),
 ("C36", "7.5", "Open-set RF, fingerprinting, jamming and radar-jamming recognition exist; none on satellite transponders", "R078;R079;R080;R081;R082;R083;R084;R085;R086;R087;R088", "E3", "R078-R081 not re-verified; R087 name order unresolved"),
 ("C37", "7.6", "Leakage via partition crossing and preprocessing fitted on evaluation data", "R105;R096", "E1", "not re-verified in this audit (budget)"),
 ("C38", "8.1", "Dataset licences: SmartSpace research-only; DataPort and Fraunhofer licence statements inconsistent/missing", "R092;R093;R094;R095", "E6", "unresolved external dependency"),
 ("C39", "8.3", "Agon reports AUC/F1 improvements over re-evaluated reconstruction baselines (exact figures not quoted in V4.3)", "R024", "E3/E4", "unverified in this audit; inherited primary-text check of figures"),
 ("C40", "9.4", "Measured-data payload simulators predate this work (TURKSAT 3A test data)", "N015", "E3/E5", "secondary_only"),
 ("C41", "9.4", "Patent on detecting cross-pol-generated interferers in a received frame", "N018", "E6", "unverified (USPTO link only)"),
 ("C42", "10.3", "Stage A matched payload gap: M-lin vs M-nl4 on identical eligible nonlinear test observations; M-nl5 separate; pilots reported, not reproduced", "", "repository record", "docs/plan/P5_veri_protokol.md:19; docs/results/pilot_A.md:3"),
 ("C43", "10.3", "Stage B primary endpoint near-family pooled unknown-positive FPR@95TPR; scorer undesignated; no production/held-out run; benchmark_complete=false", "", "repository record", "B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md:79-99; DURUM.md:14,20"),
]
rows = []
for cid, sec, claim, refs, grade, ver in C:
    ids = [x for x in refs.split(";") if x]
    rows.append(dict(claim_id=cid, section=sec, claim=claim, supporting_refs_stable=refs, supporting_refs_v4_3_numbers=";".join(str(num[i]) for i in ids if i in num),
                     verification_states=";".join("%s:%s" % (i, db[i]["state"]) for i in ids if i in db), evidence_grade=grade, verification_note=ver))
w("claim_evidence_matrix.csv", ["claim_id", "section", "claim", "supporting_refs_stable", "supporting_refs_v4_3_numbers", "verification_states", "evidence_grade", "verification_note"], rows)

# ---------------- mechanism_observation_evidence_matrix ----------------
OBS = ["obs_total_power", "obs_copol_psd", "obs_spectrogram", "obs_short_iq", "obs_contiguous_iq_cyclic", "obs_crosspol", "obs_carrier_plan", "obs_host_side_info_residual", "obs_external_evidence"]
M = [
 ("CW", "external", "EP-U1 (EP-D for terrestrial emitters at the monitor)", "EP-U1: receiver, IMUX, TWTA compression/AM-PM/mixing with carriers, OMUX, downlink, monitor receiver; EP-D: monitor receiver only",
  ["o", "P", "o", "o", "o", "o", "P", "-", "o"], "beacon/pilot/IM line (A1-P; B-I); collapsed modulated carrier (A1-X or terminal view; B-I)", "E1; E6 operator accounts", "R002", "Sec. 4; Tables 2-3"),
 ("Swept CW", "external", "EP-U1 or EP-D", "as CW", ["-", "o", "P", "o", "o", "-", "o", "-", "o"], "pulsed emitter (A0 spectrogram; B-N)", "E1; E5 other domain (GNSS temporal)", "R035;R046", "Sec. 4; Table 3"),
 ("Unauthorized / mis-tuned carrier", "external", "EP-U1", "as CW", ["o", "o", "o", "o", "o", "o", "P", "-", "P"], "uplink ASI (A2; B-I); cross-pol leakage at same frequency (A1-X; B-I)", "E1; E6", "R002;R003;R013;R106", "Sec. 4; Table 3"),
 ("Carrier-under-carrier", "external", "EP-U1", "as CW; weak-signal suppression possible near saturation", ["-", "-", "-", "o", "P", "-", "o", "P", "o"], "clean (A1-Q/H; B-N, B-P); legitimate PCMA/CID (A1-P or A2; B-I)", "E1; E3 on-board plane; E6", "R011;R008;R009;R066;R067;R015;N011;N035", "Sec. 4, 5.3; Eqs. 10-12"),
 ("ASI (uplink entry)", "external", "EP-U1", "full payload chain; often co-frequency with occupied carriers (CuC-like)", ["o", "o", "o", "o", "o", "-", "o", "o", "P"], "unauthorized carrier (A2; B-I); downlink ASI (A1-G; B-P)", "E1; E2 C/I conventions and EIRP masks", "N006;N012;R106", "Sec. 4; Table 3"),
 ("ASI (downlink entry)", "external", "EP-D", "downlink path; monitor receiver; depends on monitor-antenna sidelobes (may be invisible at a large monitor)", ["o", "o", "o", "o", "o", "-", "o", "-", "P"], "uplink ASI (A1-G; B-P)", "E1; E2 antenna patterns", "N039", "Sec. 3.4, 4, 5.1"),
 ("Cross-pol coupling (uplink, common)", "external", "EP-U1 (kappa_u)", "co-pol payload chain incl. mixing with co-pol carriers", ["o", "o", "o", "o", "o", "P", "P", "-", "o"], "unauthorized carrier (A1-X; B-I); downlink coupling (A1-X or A-empty; B-P)", "E2; E1", "R054;R064;R065", "Sec. 3.2, 4, 5.3"),
 ("Cross-pol leakage (uplink, station-specific)", "external", "EP-U0 cause; EP-U1 entry (kappa_u,q)", "as above, affecting only that station's carriers", ["o", "o", "o", "o", "o", "P", "P", "-", "o"], "common uplink coupling (A1-X with P; B-I)", "E1; E6", "R002", "Sec. 4, 5.3"),
 ("Cross-pol coupling (downlink)", "external", "EP-D (kappa_d)", "downlink path; monitor receiver; copies opposite transponder output incl. its IM and noise floor", ["o", "o", "o", "o", "o", "P", "P", "-", "o"], "uplink coupling (A1-X or A-empty; B-P); monitor-feed leakage (A1-G; B-I)", "E2; E3", "R054;R064", "Sec. 3.2, 4, 5.3"),
 ("Payload intermodulation (nominal loading)", "internal", "EP-P", "OMUX; downlink; monitor receiver", ["-", "o", "o", "o", "o", "-", "P", "o", "o"], "narrowband external energy at IM frequency (A1-P; B-P)", "E1; E2; E3", "R055;R058;N032;R097", "Sec. 3.3; Eqs. 7-8"),
 ("Overdrive / compression", "mixed (external or operational cause; internal manifestation)", "cause EP-U0/EP-U1 or EP-P (command); manifests EP-P", "compression, regrowth, IM, weak-carrier suppression", ["o", "o", "o", "o", "o", "-", "P", "o", "o"], "broadband uplink interference (A1-P; B-P, B-I)", "E1; E3", "R058;N008;N032", "Sec. 3.3, 4"),
 ("Wideband-receiver nonlinearity", "internal (externally triggered)", "EP-P (before IMUX)", "products in several channels; then IMUX, amplifier, OMUX", ["o", "o", "o", "o", "o", "-", "o", "-", "o"], "multiple simultaneous interferers (A1-P across channels; B-P)", "E1 (physical inference; primary sources not searched)", "", "Sec. 3.4"),
 ("Passive intermodulation (PIM)", "internal", "EP-P (receive side)", "treated as uplink-entry energy", ["o", "o", "o", "o", "o", "-", "o", "-", "o"], "uplink-entry carrier or CW (A1-P with transmit-plan knowledge; B-I)", "E1 (physical inference; primary sources not searched)", "", "Sec. 3.4"),
 ("Pulsed / burst", "external", "EP-U1 or EP-D", "depends on entry plane", ["o", "o", "P", "o", "o", "-", "o", "-", "o"], "TDMA traffic (A1-P/Q; B-I); swept CW (A0; B-N)", "E1; E5 other domain (GNSS temporal)", "R034;R035;R005", "Sec. 4"),
 ("Broadband noise-like", "external", "EP-U1 or EP-D", "uplink: power robbing/compression; downlink: additive", ["o", "o", "o", "o", "-", "o", "o", "-", "o"], "overdrive regrowth (A1-P; B-P); fade, gain change or sun transit (A1-P/A2; B-I)", "E1; E3", "N004;N008", "Sec. 4"),
 ("Benign: legitimate PCMA / DVB-CID", "benign", "EP-U1", "as carriers", ["-", "-", "-", "o", "P", "-", "P", "o", "P"], "carrier-under-carrier (A1-P or A2; B-I)", "E2; E1", "N011;R013", "Sec. 4"),
 ("Benign / observation-side: fades, depolarization, sun transit, receiver and feed artefacts", "benign / observation-side", "EP-D / EP-R (kappa_R)", "propagation; receiver response", ["o", "o", "o", "-", "-", "o", "o", "-", "o"], "broadband interference (A1-P/A2; B-I); true cross-pol interference vs feed leakage (A1-G; B-I)", "E1", "R064", "Sec. 3.4, 4"),
]
LEG = {"P": "primary discriminating evidence (conditional)", "o": "partial or conditional discrimination", "-": "not expected to discriminate"}
rows = []
for mech, ei, ep, tr, ratings, conf, ev, refs, basis in M:
    d = dict(mechanism=mech, external_or_internal=ei, entry_plane=ep, transformations_before_observation=tr, confusers_with_axisA_axisB=conf,
             evidence_grade=ev, key_refs_stable=refs, key_refs_v4_3_numbers=";".join(str(num[i]) for i in refs.split(";") if i and i in num), argument_basis=basis,
             status="proposed synthesis (hypothesis); not an experimentally validated mapping")
    for o, rt in zip(OBS, ratings):
        d[o] = LEG[rt]
    rows.append(d)
w("mechanism_observation_evidence_matrix.csv", ["mechanism", "external_or_internal", "entry_plane", "transformations_before_observation"] + OBS +
  ["confusers_with_axisA_axisB", "evidence_grade", "key_refs_stable", "key_refs_v4_3_numbers", "argument_basis", "status"], rows)
