"""Document/evidence checks only: no simulation, fitting, network or observation access."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"


def main():
    manifest = json.loads((PAPER / "geo_b2_evidence.json").read_text())
    text = (PAPER / "geo_b2_manuscript.md").read_text()
    checked = {}
    for name, expected in manifest["files_sha256"].items():
        path = Path(name)
        assert not path.is_absolute() and ".." not in path.parts, name
        assert path.parts[0] in {"paper", "docs", "src", "configs", "scripts"}, name
        assert path.suffix in {".md", ".json", ".py", ".bib", ".png"}, name
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, name
        checked[name] = ROOT / path
    for name, anchors in manifest["source_anchors"].items():
        source = checked[name].read_text()
        assert all(anchor in source for anchor in anchors), name
    assert set(manifest["claims"]) == {f"E{n:02d}" for n in range(1, 19)}
    for key, files in manifest["claims"].items():
        assert files and all(name in checked for name in files), key
        assert f"| {key} |" in (PAPER / "geo_b2_evidence.md").read_text(), key
    used = set()
    for tag in re.findall(r"\[E\d\d[^\]\n]*\]", text):
        for first, last in re.findall(r"E(\d{2})(?:[–-]E?(\d{2}))?", tag):
            used.update(f"E{n:02d}" for n in range(int(first), int(last or first) + 1))
    assert used == set(manifest["claims"]), used
    bibliography = (PAPER / "geo_b2_references.bib").read_text()
    keys = re.findall(r"@\w+\s*\{\s*([^,]+),", bibliography)
    assert len(keys) == len(set(keys)), "duplicate bibliography key"
    citations = set(re.findall(r"@([A-Za-z][A-Za-z0-9_-]+)", text))
    assert citations and citations <= set(keys), citations - set(keys)
    assert citations <= set(manifest["literature_keys"]), "citation lacks source verification entry"
    assert len(text.split()) >= 6000, "substantive manuscript text missing"
    for heading in (
        "# 1. Introduction", "# 2. Related Work", "# 3. GEO Bent-Pipe Physical System Model",
        "# 4. Payload-Aware Recognition Methodology", "# 5. Open-Set Detection and Calibration",
        "# 6. Experimental Design and Ablations", "# 7. Existing Simulated Evidence and Results Specifications",
        "# 8. Threats to Validity and Reproducibility", "# 9. Conclusion", "# References",
    ):
        assert heading in text, heading
    for item in manifest["numeric_assertions"]:
        value = json.loads(checked[item["source"]].read_text())
        for part in item["pointer"].strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert value == item["value"], item
        assert format(value, item["format"]) in text, item
    assert 1500 * 8 == 12000 and (1500 + 150 + 150 + 500) * 8 == 18400
    assert 18400 + 500 * 5 + 150 * 3 == 21350
    assert 500 * 3 == 1500 and 500 * 8 == 4000 and 30 * (12000 // 32) == 11250
    assert 3 * 3 + 2 * 3 == 15
    for value in ("21,350", "18,400", "12,000", "1,500", "4,000", "11,250", "498/148", "NOT DESIGNATED"):
        assert value in text, value
    for left, right in manifest["identical_figures"]:
        assert checked[left].read_bytes() == checked[right].read_bytes(), (left, right)
    result_section = text.split("## 7.2.", 1)[1].split("## 7.3.", 1)[0]
    rows = []
    for line in result_section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] in {"Co", "Dual", "Dual-residual", "Dual-planmask", "Dual-noplan"}:
            assert cells[1] == "0, 1, 2 separately" and all(c == "NOT RUN" for c in cells[2:]), cells
            rows.append(cells)
        elif cells[0].startswith(("H1:", "H2:", "H3:")):
            assert all(c == "NOT RUN" for c in cells[1:]), cells
            rows.append(cells)
    assert len(rows) == 8, "missing NOT RUN result rows"
    specs = (PAPER / "geo_b2_display_specs.md").read_text()
    for marker in ("T6:", "T7:", "T8:", "T9:", "G3:", "G4:", "G5:", "G6:", "NOT RUN", "NOT DESIGNATED", "DEFERRED"):
        assert marker in specs, marker
    print(f"GEO document audit PASS: {len(checked)} hashed sources/figures; 18 claim groups; "
          f"{len(citations)} resolved citations; {len(manifest['numeric_assertions'])} aggregate checks; "
          f"8 NOT RUN result rows; {len(text.split())} manuscript words.")


if __name__ == "__main__":
    main()
