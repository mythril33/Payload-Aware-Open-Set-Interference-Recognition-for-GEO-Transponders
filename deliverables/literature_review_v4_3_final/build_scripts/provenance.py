import hashlib, json, os, subprocess, sys, datetime
REPO = "/home/user/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders"
OUT = sys.argv[1]
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_meta.json")))
UP = "/root/.claude/uploads/887ebf34-f8d5-57b7-91ca-a1a8ca1e286f/2589db9d-Literature_Review-Payload-Aware_Open-Set_Interference_Recognition_for_GEO_Transponders_2.docx"
def sha(p):
    h = hashlib.sha256(); h.update(open(p, "rb").read()); return h.hexdigest()
def git(*a):
    return subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True).stdout.strip()
inputs = [
 (UP, "researcher-uploaded DOCX attached to the V4.3 request (core.xml: modified 2026-10-26T22:22Z, revision 38, 95 references, 3 OMML objects); used as the functional V4.2 baseline because no file named V4.2 exists"),
 (REPO + "/Literature_Review_GEO_Transponders_v4_1_Editorial.docx", "V4.1 editorial DOCX (106 references, 17 OMML objects); technical secondary baseline"),
 (REPO + "/BurakTOS-Literature Review-Payload-Aware Open-Set Interference Recognition for GEO Transponders (2).docx", "researcher DOCX rev 36 (2026-10-24); differs from upload only in the uplink equation"),
 (REPO + "/BurakTOS-Literature Review-Payload-Aware Open-Set Interference Recognition for GEO Transponders.docx", "researcher DOCX rev 34 (2026-10-23)"),
 (REPO + "/Literature Review — Payload-Aware Open-Set Interference Recognition for GEO Transponders.docx", "original review DOCX (95 references; matches original_docx_sha256 in reconciliation JSON)"),
 (REPO + "/Literature_Review_GEO_Transponders.md", "technical revision (23 Oct) Markdown, 96 references"),
 (REPO + "/Literature_Review_GEO_Transponders (1).md", "technical revision (23 Oct) Markdown, 105 references (V4 lineage)"),
 (REPO + "/Payload-Aware Open-Set Interference Recognition for GEO Transponders_ Literature Review.md", "original gap-scan report (research tool)"),
 (REPO + "/refs.json", "legacy 95-entry reference manifest"),
 (REPO + "/reference_reconciliation_v4_1.json", "V4.1 reconciliation: stable IDs R001-R106"),
 (REPO + "/review_findings.md", "independent review findings F1-F46 on earlier draft"),
 (REPO + "/V4_1_revize_degisiklik_ozeti.md", "V4.1 change summary"),
 (REPO + "/GEO_Interference_Oturum_Envanteri.xlsx", "session inventory workbook (no K1-K7 publication decisions inside)"),
 (REPO + "/litcheck.py", "legacy consistency checker (logic re-implemented for V4.3 QA because the V4.3 manifest uses new verification states)"),
 (REPO + "/paper/literature_audit.md", "manuscript V1 literature audit"),
 (REPO + "/docs/plan/P5_veri_protokol.md", "Stage A data protocol (matched payload gap)"),
 (REPO + "/docs/results/pilot_A.md", "Stage A model pilot record (pipeline trial, not a result)"),
 (REPO + "/docs/plan/P18_b2_protocol.md", "frozen B2/1 protocol"),
 (REPO + "/docs/plan/P20_b2_cancellation_residual.md", "observation-based cancellation"),
 (REPO + "/docs/plan/P31_b2_e7b_isolated_execution.md", "isolated execution and calibration"),
 (REPO + "/docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md", "E9 scientific approval"),
 (REPO + "/docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md", "E12 D-1..D-8 decisions"),
 (REPO + "/docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json", "E12 decisions JSON"),
 (REPO + "/docs/plan/DURUM.md", "current status (benchmark_complete=false)"),
 (REPO + "/docs/plan/P2_sistem_modeli.md", "system model"),
 (REPO + "/docs/plan/P14_dual_polarization.md", "dual-polarization model"),
 (REPO + "/docs/plan/kaynak_transponder_modeli.md", "transponder source note"),
 (REPO + "/src/geosim/dual.py", "entry-plane order in dual-pol simulator (read only)"),
 (REPO + "/docs/plan/00_ana_plan.md", "main plan (project K decisions; distinct from publication K1-K7)"),
]
files = []
for p, role in inputs:
    if os.path.exists(p):
        files.append(dict(path=p.replace(REPO + "/", "repo:") if p.startswith(REPO) else p, sha256=sha(p), bytes=os.path.getsize(p), role=role))
    else:
        files.append(dict(path=p, missing=True, role=role))
deliv = []
for f in sorted(os.listdir(OUT)):
    fp = os.path.join(OUT, f)
    if os.path.isfile(fp) and not f.endswith(".zip") and f != "audit_provenance.json":
        deliv.append(dict(file=f, sha256=sha(fp), bytes=os.path.getsize(fp)))
status = git("status", "--porcelain")
prov = dict(
 schema="GEO-literature-review-V4.3-provenance/1",
 generated_utc=datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
 repository=dict(url="https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders", head_sha=git("rev-parse", "HEAD"),
                 branch=git("branch", "--show-current"), origin_main_sha=git("rev-parse", "origin/main"),
                 working_tree_status_excluding_deliverables=[l for l in status.splitlines() if "deliverables/" not in l],
                 note="Local clone present. Deliverables were written only under deliverables/literature_review_v4_3_final/ (untracked); no existing tracked file was modified; nothing committed or pushed."),
 missing_requested_inputs=["GEO_Payload_Aware_Interference_Literature_Review_V4_2.docx", "Verification_Ledger_GEO_Review.docx", "Progress_Summary_Kademe_A.docx",
                           "approved K1-K7 publication-scope record as a separate file (decisions taken from the assignment text)"],
 baseline_decision="No V4.2 file found on disk, in the repository history or on any remote branch. The researcher-uploaded DOCX (latest, 2026-10-26) was used as the functional V4.2 baseline; the V4.1 editorial DOCX and the 105-reference technical revision were used for previously verified corrections. Original files were not modified.",
 reference_counts=dict(original_v4_docx=95, technical_revision_md_1=96, technical_revision_md_2=105, v4_1_editorial=106, uploaded_baseline=95, v4_3_cited=len(M["order"]), v4_3_legacy_retained=len(M["legacy_cited"]), v4_3_new=len(M["new_cited"]), legacy_not_cited=["R031","R044","R047","R057"],
                       note="The assignment mentions approximately 112 references; no file with 112 references was found."),
 inputs=files,
 deliverables=deliv,
 database_availability={
  "Crossref API": "blocked (proxy 403 / DNS failure)", "OpenAlex": "blocked", "arXiv": "blocked", "Semantic Scholar API": "blocked", "doi.org": "blocked",
  "IEEE Xplore": "blocked (direct); reachable only as search-engine results", "Scopus": "not available", "Web of Science": "not available", "Google Scholar": "blocked",
  "ETSI portal": "blocked (direct)", "ITU portal": "blocked (direct)",
  "General web search engine (WebSearch tool)": "available until per-turn budget of 200 calls was exhausted (shared across all agents)"},
 tools=["pandoc 3.1.3 (Markdown+TeX math -> DOCX with native OMML)", "python-docx (post-processing)", "matplotlib 3.11 (vector/PNG diagrams)", "LibreOffice 24.2 + libreoffice-math (PDF proof; Math module installed in the container only)",
        "pdftoppm/pdfinfo (render QA)", "WebSearch tool", "parallel verification/search sub-agents (same model family)"],
 incomplete_verifications=[
  "No reference reached verified_full_text (no full-text access).",
  "%d legacy references not reached for re-verification (budget): %s." % (len(M["notreach"]), ", ".join(M["notreach"])),
  "Dedicated novelty-threat search, polarization/PCMA/cyclostationarity primary-source searches and dataset searches not executed (budget).",
  "ETSI clause contents confirmed at search-excerpt level only; informative status of EN 302 307-1 Annex H inherited from V4.1.",
  "Dataset licences (IEEE DataPort R094, Fraunhofer R095, SmartSpace R092/R093, OpenDPD data vs code) unresolved.",
  "Saleh coefficient provenance unresolved (4.0033 vs 4.033)."],
 declared_non_execution=dict(rf_simulation=False, dataset_generation=False, model_training=False, model_evaluation=False, held_out_access=False, gpu=False,
                             github_actions=False, repository_files_modified=False, protocols_or_configs_changed=False, push_merge_publish=False,
                             benchmark_complete=False, note="benchmark_complete=false as recorded in docs/plan/DURUM.md (2026-10-26) and E12 JSON"),
)
json.dump(prov, open(os.path.join(OUT, "audit_provenance.json"), "w"), indent=1, ensure_ascii=False)
print("ok", len(files), len(deliv))
