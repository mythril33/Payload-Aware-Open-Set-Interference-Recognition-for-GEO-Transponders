#!/usr/bin/env python3
"""litcheck — consistency checker for the literature review.

Usage:  python3 litcheck.py doc.md refs.json [--json report.json]

Checks the exported review (Markdown) against the reference manifest:
  C1  every cited [n] exists in the reference list and the manifest
  C2  every reference is cited at least once in the body
  C3  references are numbered in order of first citation (IEEE style)
  C4  no unresolved markers remain ("to verify", "to complete", "TBD", "??")
  C5  every manifest entry has authors, title and a verification status
  C6  identifiers are well formed (DOI, arXiv) and not duplicated
  C7  the title in the document matches the manifest title
  C8  figures and tables are numbered 1..k and each is referred to in the text
  C9  numeric claims (%, dB, counts) in prose sit in a paragraph that cites a source
Exit code 0 = no errors (warnings allowed), 1 = errors.
"""
import json, re, sys, unicodedata
from difflib import SequenceMatcher

ARXIV = re.compile(r"^\d{4}\.\d{4,5}$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
MARKERS = re.compile(r"to verify|to complete|\bTBD\b|\?\?|XXX", re.I)
STATUSES = {"verified-registry", "verified-publisher", "verified-secondary",
            "vendor-or-trade", "dataset"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def expand(tok):
    out = []
    for part in tok.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)\]?\s*[–-]\s*\[?(\d+)$", part)
        if m:
            out += range(int(m.group(1)), int(m.group(2)) + 1)
        elif part.isdigit():
            out.append(int(part))
    return out


def citations(text):
    """Return cited numbers in order of appearance; handles [3], [3, 5], [3]–[7]."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # ignore formulas
    seq = []
    for m in re.finditer(r"\[(\d+)\](?:\s*[–-]\s*\[(\d+)\])?|\[(\d+(?:\s*,\s*\d+)+)\]", text):
        if m.group(1) and m.group(2):
            seq += range(int(m.group(1)), int(m.group(2)) + 1)
        elif m.group(1):
            seq.append(int(m.group(1)))
        else:
            seq += expand(m.group(3))
    return seq


def main(doc_path, refs_path, out_json=None):
    md = open(doc_path, encoding="utf-8").read()
    # undo Markdown escaping produced by exporters: &#91;3\] or \[3\] -> [3]
    md = md.replace("&#91;", "[").replace("&#93;", "]").replace("\\[", "[").replace("\\]", "]")
    manifest = {r["n"]: r for r in json.load(open(refs_path, encoding="utf-8"))}
    body, _, reflist = md.partition("## References")
    errors, warns = [], []

    doc_refs = {}
    for line in reflist.splitlines():
        m = re.match(r"^\s*[-*]\s*\\?\[(\d+)\\?\]\s*(.*)$", line)
        if m:
            doc_refs[int(m.group(1))] = m.group(2)

    cited = citations(body)
    first = []
    for n in cited:
        if n not in first:
            first.append(n)

    # C1
    for n in sorted(set(cited)):
        if n not in doc_refs:
            errors.append(f"C1 [{n}] cited but missing from the reference list")
        if n not in manifest:
            errors.append(f"C1 [{n}] cited but missing from the manifest")
    # C2
    for n in sorted(doc_refs):
        if n not in set(cited):
            errors.append(f"C2 [{n}] listed but never cited in the body")
    # C3
    expected = sorted(first)
    if first != expected:
        out = [(i + 1, n) for i, n in enumerate(first) if n != i + 1][:10]
        warns.append(f"C3 not in order of first citation; first mismatches (position, ref): {out}")
    # C4
    for i, line in enumerate(md.splitlines(), 1):
        if MARKERS.search(line):
            errors.append(f"C4 unresolved marker on line {i}: {line.strip()[:90]}")
    # C5–C7
    seen = {}
    for n, r in sorted(manifest.items()):
        for f in ("authors", "title"):
            if not r.get(f):
                errors.append(f"C5 [{n}] manifest field '{f}' is empty")
        if r.get("status") not in STATUSES:
            errors.append(f"C5 [{n}] status '{r.get('status')}' not one of {sorted(STATUSES)}")
        if r.get("status", "").startswith("verified") and not r.get("evidence"):
            errors.append(f"C5 [{n}] marked verified but has no evidence URL")
        if r.get("doi") and not DOI.match(r["doi"]):
            errors.append(f"C6 [{n}] malformed DOI {r['doi']}")
        if r.get("arxiv") and not ARXIV.match(r["arxiv"]):
            errors.append(f"C6 [{n}] malformed arXiv id {r['arxiv']}")
        for key in ("doi", "arxiv"):
            v = (r.get(key) or "").lower()
            if v:
                if (key, v) in seen:
                    errors.append(f"C6 [{n}] duplicates {key} of [{seen[(key, v)]}]")
                seen[(key, v)] = n
        if n in doc_refs and r.get("title"):
            t, d = norm(r["title"]), norm(doc_refs[n])
            ratio = max((SequenceMatcher(None, t, d[i:i + len(t)]).ratio()
                         for i in range(max(1, len(d) - len(t) + 1))), default=0)
            if ratio < 0.85:
                errors.append(f"C7 [{n}] title in doc does not match manifest ({ratio:.2f})")
        if n in doc_refs:
            for key in ("doi", "arxiv"):
                v = r.get(key)
                if v and v.lower() not in doc_refs[n].lower():
                    warns.append(f"C7 [{n}] manifest {key} {v} not shown in the doc entry")
    # C8
    for kind in ("Figure", "Table"):
        defined = [int(x) for x in re.findall(rf"\*\*{kind} (\d+)\.\*\*", body)]
        if defined != list(range(1, len(defined) + 1)):
            errors.append(f"C8 {kind}s not numbered 1..k: {defined}")
        for k in defined:
            mentions = len(re.findall(rf"\b{kind} {k}\b", body))
            if mentions < 2:
                warns.append(f"C8 {kind} {k} is never referred to in the text")
    # C9
    paras = [p for p in re.split(r"\n\s*\n", re.sub(r"```.*?```", "", body, flags=re.S))
             if not p.lstrip().startswith(("|", "#", "**Figure", "**Table", "<"))]
    num = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:%|dB|percent|carriers|incidents|MHz)\b")
    for p in paras:
        if num.search(p) and not re.search(r"\[\d+\]", p):
            warns.append(f"C9 numeric claim without a citation in paragraph: {p.strip()[:110]}…")

    status = {}
    for r in manifest.values():
        status[r.get("status", "missing")] = status.get(r.get("status", "missing"), 0) + 1
    report = {"references_in_doc": len(doc_refs), "references_cited": len(set(cited)),
              "manifest_status": status, "errors": errors, "warnings": warns}
    print(f"litcheck: {len(doc_refs)} references, {len(set(cited))} cited, "
          f"{len(errors)} errors, {len(warns)} warnings")
    print("manifest status:", status)
    for e in errors:
        print("ERROR  ", e)
    for w in warns:
        print("WARN   ", w)
    if out_json:
        json.dump(report, open(out_json, "w"), indent=2, ensure_ascii=False)
    return 1 if errors else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    out = a[a.index("--json") + 1] if "--json" in a else None
    sys.exit(main(a[0], a[1], out))
