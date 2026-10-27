"""Document QA checks on the numbered manuscript and the produced DOCX (litcheck-style C1-C4, C8 plus DOCX checks)."""
import re, sys, json, zipfile, subprocess
md = open(sys.argv[1], encoding="utf-8").read()
docx = sys.argv[2]
body, refs = md.split("\n# References", 1)
refs = refs.split("# Appendix A.")[0]
res = {}
# citations in body (exclude math)
nomath = re.sub(r"\$\$.*?\$\$", " ", body, flags=re.S)
nomath = re.sub(r"\$[^$]*\$", " ", nomath)
seq = []
for m in re.finditer(r"\[(\d+)(?:,[^\]]*)?\](?:–\[(\d+)\])?", nomath):
    a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else a
    seq += list(range(a, b + 1))
listed = [int(x) for x in re.findall(r"^\[(\d+)\] ", refs, flags=re.M)]
res["C1_cited_exist"] = sorted(set(seq) - set(listed))
res["C2_uncited_refs"] = sorted(set(listed) - set(seq))
first = []
for n in seq:
    if n not in first: first.append(n)
res["C3_first_citation_order_ok"] = first == sorted(first) and first == list(range(1, len(first) + 1))
res["C4_markers"] = re.findall(r"to verify|to complete|\bTBD\b|\?\?|XXX|\{\{|lorem", md, flags=re.I)
figs = [int(x) for x in re.findall(r"!\[Figure (\d+)\.", md)]
tabs = re.findall(r"\*\*Table ([A-Z]?\d+)\.\*\*", md)
res["C8_figures"] = figs
res["C8_tables"] = tabs
res["figure_refs_in_text"] = sorted(set(int(x) for x in re.findall(r"Figure (\d+)", re.sub(r"!\[Figure \d+\.", "", md))))
res["table_refs_in_text"] = sorted(set(re.findall(r"Table ([A-Z]?\d+)", re.sub(r"\*\*Table [A-Z]?\d+\.\*\*", "", md))))
eqs = [int(x) for x in re.findall(r"\\tag\{(\d+)\}|\\qquad\\qquad\\qquad\((\d+)\)", md) for x in x if x]
res["equation_numbers"] = eqs
res["equation_refs_in_text"] = sorted(set(int(x) for x in re.findall(r"Eqs?\.\s*\((\d+)\)", md)))
res["n_references"] = len(listed)
z = zipfile.ZipFile(docx)
xml = z.read("word/document.xml").decode("utf-8")
res["docx_omml_objects"] = xml.count("<m:oMath>") + xml.count("<m:oMath ")
res["docx_images"] = len([n for n in z.namelist() if n.startswith("word/media/")])
res["docx_tables"] = xml.count("<w:tbl>")
res["docx_raw_latex_leftovers"] = len(re.findall(r"\\(mathrm|frac|sum|left|right|mathcal)\b", re.sub(r"<[^>]+>", "", xml)))
print(json.dumps(res, indent=1, ensure_ascii=False))
