"""Assemble V4.3 manuscript: resolve stable-ID citations to IEEE numbers, fill counts, write md sources."""
import csv, glob, os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refs_db

B = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.dirname(B)
V = os.path.join(SCR, "verify")

def reached(row):
    q = row.get("queries", "") or ""
    for m in re.finditer(r"\[(\d+)[^\]]*\]|->\s*(\d+)", q):
        if int(m.group(1) or m.group(2)) > 0:
            return True
    return False

# ---------- counts from logs ----------
def read(f):
    return list(csv.DictReader(open(os.path.join(V, f), encoding="utf-8")))

def executed(r):
    t = (r["n_results_returned"] + " " + r["exclusion_notes"]).lower()
    return not re.search(r"not (performed|executed|run)", t) and re.match(r"\s*\d+", r["n_results_returned"]) and int(re.match(r"\s*(\d+)", r["n_results_returned"]).group(1)) >= 0

AUDIT = [
 dict(search_id="AUD-01", database_or_source="WebSearch (general engine; lead session)", query="carrier-under-carrier interference detection satellite PCMA cancellation", search_date="2026-10-26", filters="standard; no domain filter", n_results_returned="9", duplicates_existing_ids="R014 (Via Satellite page)", relevant_candidates="Feder et al. 2025 blind PCMA estimation (KIT repository) -> N013; US 8351495 (modem in-band interference detection, logged only); Anritsu SpectraVision help (vendor constraint on carrier-in-carrier detection, logged only)", exclusion_notes="Patent records and vendor help pages logged but not cited except where noted"),
 dict(search_id="AUD-02", database_or_source="WebSearch (general engine; lead session)", query="ETSI TR 102 376-2 V1.2.1 4.4.1.3 cross-polar interference C/I Ku-band 24 dB", search_date="2026-10-26", filters="extended; no domain filter", n_results_returned="9", duplicates_existing_ids="R054 (ETSI V1.2.1 official PDF listing; DVB A171-2 draft)", relevant_candidates="Dimitrov et al. 2024 (N014); ETSI TR 102 376-2 V1.1.1 (2015) logged", exclusion_notes="standards.iteh.ai catalogue pages used only to confirm edition metadata"),
 dict(search_id="AUD-03", database_or_source="WebSearch (general engine; lead session)", query='Gardner "Exploitation of spectral redundancy in cyclostationary signals" 1991', search_date="2026-10-26", filters="standard", n_results_returned="0 (not performed: per-turn search budget exhausted)", duplicates_existing_ids="", relevant_candidates="", exclusion_notes="NOT EXECUTED - budget exhausted"),
]

def search_stats():
    streams = []
    allrows = []
    for name, f, topics in [("RF physics and signal processing", "search_log_rf.csv", "bent-pipe entry, monitoring, geolocation; IMUX/TWTA/OMUX, IM, NPR, power robbing; ASI and C/I conventions"),
                            ("Machine learning and uncertainty", "search_log_ml.csv", "satellite interference ML; open-set/OOD; score critiques; calibration; novelty threats (partial)"),
                            ("Standards and primary physics", "search_log_std.csv", "ETSI TR 102 376-2; EN 302 307-1 Annex H; Saleh model; IM scaling")]:
        rows = read(f)
        ex = [r for r in rows if executed(r)]
        links = sum(int(re.match(r"\s*(\d+)", r["n_results_returned"]).group(1)) for r in ex)
        streams.append(dict(name=name, topics=topics, n=len(ex), links=links, notrun=len(rows) - len(ex), stream=f))
        for r in rows:
            r = dict(r); r["stream"] = name; allrows.append(r)
    ex = [r for r in AUDIT if executed(r)]
    streams.append(dict(name="Lead-session checks", topics="PCMA / carrier-under-carrier; ETSI cross-polar model; Gardner", n=len(ex),
                        links=sum(int(re.match(r"\s*(\d+)", r["n_results_returned"]).group(1)) for r in ex), notrun=len(AUDIT) - len(ex), stream="audit"))
    for r in AUDIT:
        r = dict(r); r["stream"] = "Lead-session checks"; allrows.append(r)
    return streams, allrows

def verify_queries():
    n = 0
    for f in glob.glob(os.path.join(V, "out_batch*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            for q in r["queries_run"].split(";"):
                m = re.search(r"\[(\d+)|->\s*(\d+)", q)
                if q.strip() and m and "not performed" not in q and int(m.group(1) or m.group(2)) >= 0:
                    n += 1
    return n

# ---------- citations ----------
CIT_RE = re.compile(r"\[((?:[RN]\d{3})(?:[^\]\[]*?))\]")

def parse_group(inner):
    """Return list of (ids, suffix) items; suffix e.g. ', §4.4.1.3'."""
    items = []
    for part in inner.split(";"):
        part = part.strip()
        m = re.match(r"^([RN]\d{3})\s*[–-]\s*([RN]\d{3})(.*)$", part)
        if m:
            a, b = m.group(1), m.group(2)
            ids = ["%s%03d" % (a[0], k) for k in range(int(a[1:]), int(b[1:]) + 1)]
            items.append((ids, m.group(3)))
            continue
        m = re.match(r"^([RN]\d{3})(.*)$", part)
        if not m:
            return None
        items.append(([m.group(1)], m.group(2)))
    return items

def assemble():
    parts = [open(os.path.join(B, "part%d.md" % i), encoding="utf-8").read() for i in range(1, 6)]
    body = "\n".join(parts)
    return body

def main():
    db = refs_db.build()
    body = assemble()
    # protect math from citation parsing: citations never inside $$...$$
    order, seen = [], set()
    for m in CIT_RE.finditer(body):
        items = parse_group(m.group(1))
        if items is None:
            continue
        for ids, _ in items:
            for i in ids:
                if i not in db:
                    raise SystemExit("Unknown reference " + i)
                if i not in seen:
                    seen.add(i); order.append(i)
    num = {sid: k + 1 for k, sid in enumerate(order)}

    def fmt(m):
        items = parse_group(m.group(1))
        if items is None:
            return m.group(0)
        out = []
        items = sorted(items, key=lambda it: num[it[0][0]])
        for ids, suf in items:
            ns = [num[i] for i in ids]
            if len(ns) > 2 and ns == list(range(ns[0], ns[0] + len(ns))):
                out.append("[%d]–[%d]%s" % (ns[0], ns[-1], ""))
            else:
                for j, n in enumerate(ns):
                    out.append("[%d%s]" % (n, suf if (j == len(ns) - 1 and suf) else ""))
        # merge suffix-less list
        return ", ".join(out)
    numbered = CIT_RE.sub(fmt, body)

    # counts
    streams, allrows = search_stats()
    nq = sum(s["n"] for s in streams)
    nl = sum(s["links"] for s in streams)
    nv = verify_queries()
    legacy_cited = [s for s in order if s.startswith("R")]
    new_cited = [s for s in order if s.startswith("N")]
    notreach = [s for s in sorted(db) if s.startswith("R") and not reached(db[s]) and db[s]["state"] == "unverified" and s in legacy_cited]
    def compress(ids):
        nums = [int(x[1:]) for x in ids]
        out, i = [], 0
        while i < len(nums):
            j = i
            while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                j += 1
            out.append("R%03d" % nums[i] if i == j else "R%03d–R%03d" % (nums[i], nums[j]))
            i = j + 1
        return ", ".join(out)
    states = ["verified_full_text", "verified_publisher_metadata", "verified_primary_dataset_record", "secondary_only", "unverified", "contradicted"]
    state_rows = "\n".join("| `%s` | %d | %d | %d |" % (st, sum(db[s]["state"] == st for s in legacy_cited), sum(db[s]["state"] == st for s in new_cited),
                                                    sum(db[s]["state"] == st for s in order)) for st in states)
    state_rows += "\n| **Total** | %d | %d | %d |" % (len(legacy_cited), len(new_cited), len(order))
    CATS = [("RF-search", "search_log_rf.csv"), ("ML-search", "search_log_ml.csv"), ("STD-search", "search_log_std.csv"),
            ("audit search", "audit"), ("repository context", "repo"), ("red-team addition", "redteam")]
    cand = {v: 0 for _, v in CATS}
    newcat = {}
    for s_ in new_cited:
        for k, v in CATS:
            if k in db[s_]["note"]:
                cand[v] += 1; newcat[s_] = v; break
    srows = "\n".join("| %s | %s | %d | %d | %d | %d |" % (s["name"], s["topics"], s["n"], s["links"], s["notrun"], cand[s["stream"]]) for s in streams)
    srows += "\n| Repository records | standards and protocol records already in the project repository | – | – | – | %d |" % cand["repo"]
    srows += "\n| Red-team additions | classical references named by the internal red-team review (domain knowledge, not searched) | – | – | – | %d |" % cand["redteam"]
    srows += "\n| Reference verification | title/identifier/claim checks for legacy references | %d | – | %d references not reached | – |" % (nv, len(notreach))
    rep = {"{{NQ_TOPIC}}": str(nq), "{{NLINKS}}": str(nl), "{{NQ_VERIFY}}": str(nv), "{{N_NOT_REVERIFIED}}": str(len(notreach)),
           "{{NOT_REVERIFIED_LIST}}": compress(notreach), "{{SEARCH_ROWS}}": srows, "{{STATE_ROWS}}": state_rows,
           "{{NREF}}": str(len(order)), "{{NLEG}}": str(len(legacy_cited)), "{{NNEW}}": str(len(new_cited))}
    for k, v in rep.items():
        numbered = numbered.replace(k, v); body = body.replace(k, v)
    assert "{{" not in numbered, re.findall(r"\{\{\w+\}\}", numbered)
    # equation tags -> visible numbers
    numbered_doc = re.sub(r"\\tag\{(\d+)\}", r"\\qquad\\qquad\\qquad(\1)", numbered)
    # references section
    refs_md = ["", "# References", "",
               "Each entry ends with its stable identifier and the verification state reached in this audit (Section 2.4). Trade, vendor and company sources are cited only for operator practice, product capabilities or reported events and are not peer-reviewed."]
    for sid in order:
        r = db[sid]
        refs_md.append("")
        refs_md.append("::: {custom-style=\"Bibliography\"}\n[%d] %s [%s; %s]\n:::" % (num[sid], r["cit"], sid, refs_db.STATE_LABEL[r["state"]]))
    # insert references before Appendix A
    idx = numbered_doc.index("# Appendix A.")
    final_doc = numbered_doc[:idx] + "\n".join(refs_md) + "\n\n" + numbered_doc[idx:]
    open(os.path.join(B, "manuscript_numbered.md"), "w", encoding="utf-8").write(final_doc)
    # source with stable ids (editable source deliverable)
    src_refs = ["", "# References (stable identifiers)", "",
                "Citations in this source use stable identifiers (R = legacy corpus, N = added in V4.3). The publication copy numbers them in order of first citation as listed below."]
    for sid in order:
        r = db[sid]
        src_refs.append("")
        src_refs.append("- **%s** → [%d] %s *(verification: %s)*" % (sid, num[sid], r["cit"], r["state"]))
    idx2 = body.index("# Appendix A.")
    src = body[:idx2] + "\n".join(src_refs) + "\n\n" + body[idx2:]
    open(os.path.join(B, "literature_review_v4_3.md"), "w", encoding="utf-8").write(src)
    json.dump(dict(cand=cand, newcat=newcat, order=order, num=num, nq=nq, nl=nl, nv=nv, notreach=notreach, streams=streams, legacy_cited=legacy_cited, new_cited=new_cited),
              open(os.path.join(B, "build_meta.json"), "w"), indent=1)
    with open(os.path.join(B, "all_search_rows.json"), "w") as f:
        json.dump(allrows, f)
    print("refs", len(order), "legacy", len(legacy_cited), "new", len(new_cited), "nq", nq, "links", nl, "nv", nv, "notreach", len(notreach), compress(notreach))
    uncited = [s for s in db if s not in num]
    print("uncited:", uncited)

if __name__ == "__main__":
    main()
