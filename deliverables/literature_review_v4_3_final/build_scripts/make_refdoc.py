from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
d = Document("ref_default.docx")
def setfont(st, name="Liberation Serif", size=None, bold=None, italic=None, color=None):
    st.font.name = name
    rpr = st.element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = rpr.makeelement(qn('w:rFonts'), {}); rpr.append(rf)
    for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'): rf.set(qn(a), name)
    for a in ('w:asciiTheme', 'w:hAnsiTheme', 'w:cstheme', 'w:eastAsiaTheme'):
        if rf.get(qn(a)) is not None: del rf.attrib[qn(a)]
    if size: st.font.size = Pt(size)
    if bold is not None: st.font.bold = bold
    if italic is not None: st.font.italic = italic
    if color is not None: st.font.color.rgb = RGBColor.from_string(color)
S0 = d.styles
class _S:
    def __getitem__(self,k):
        for st in S0:
            if st.name==k: return st
        raise KeyError(k)
    def __iter__(self): return iter(S0)
S=_S()
for n in ["Normal", "Body Text", "First Paragraph", "Compact", "Block Text"]:
    if n in [s.name for s in S]:
        setfont(S[n], size=10.5)
for n in ["Body Text", "First Paragraph"]:
    pf = S[n].paragraph_format; pf.space_before = Pt(0); pf.space_after = Pt(6); pf.line_spacing = 1.12
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
S["Compact"].paragraph_format.space_after = Pt(1)
for n, sz in [("Title", 17), ("Subtitle", 12), ("Heading 1", 13.5), ("Heading 2", 11.5), ("Heading 3", 10.5)]:
    setfont(S[n], size=sz, bold=(n != "Subtitle"), color="1F2A44")
    S[n].paragraph_format.space_before = Pt(12 if n.startswith("Heading 1") else 8)
    S[n].paragraph_format.space_after = Pt(4)
    S[n].paragraph_format.keep_with_next = True
S["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
for n in ["Author", "Date"]:
    if n in [s.name for s in S]:
        setfont(S[n], size=10.5); S[n].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
for n in ["Abstract"]:
    if n in [s.name for s in S]: setfont(S[n], size=10)
for n in ["Caption", "Table Caption", "Image Caption"]:
    if n in [s.name for s in S]:
        setfont(S[n], size=9, italic=False)
        S[n].paragraph_format.space_after = Pt(8); S[n].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
setfont(S["Hyperlink"] if "Hyperlink" in [s.name for s in S] else S["Normal"])
for sec in d.sections:
    sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0); sec.top_margin = sec.bottom_margin = Cm(2.2)
d.save("reference.docx")
print([s.name for s in S if s.type == 1][:60])
