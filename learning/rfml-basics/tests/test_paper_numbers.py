"""The paper prints no hand-typed result: every \\Num key exists and no stray decimals remain."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PAPER = Path(__file__).resolve().parents[1] / "paper"
TEX = PAPER / "paper.tex"
NUMBERS = PAPER / "generated" / "numbers.json"

# Three-decimal literals that are not results: the sign-test p-values quoted for reference.
ALLOWED_LITERALS = {"0.002", "0.021", "0.109", "0.344"}

pytestmark = pytest.mark.skipif(not NUMBERS.exists(), reason="run paper/make_numbers.py first")


def _body() -> str:
    lines = [line.split("%", 1)[0] for line in TEX.read_text(encoding="utf-8").splitlines()]
    return "\n".join(lines)


def test_every_number_key_is_defined():
    known = set(json.loads(NUMBERS.read_text()))
    used = set(re.findall(r"\\Num\{([^}]+)\}", _body()))
    used |= {f"{key}:pm" for key in re.findall(r"\\pmnum\{([^}]+)\}", _body())}
    used.discard("#1:pm")  # the macro definition itself
    used.discard("#1")
    assert used, "the paper uses no generated number"
    assert not (used - known), f"undefined keys: {sorted(used - known)}"


def test_no_hand_typed_three_decimal_results():
    """Results have three decimals; any such literal in the source must come from \\Num."""
    text = re.sub(r"\\(?:Num|pmnum)\{[^}]+\}", "", _body())
    literals = set(re.findall(r"(?<![\d.])\d\.\d{3}(?!\d)", text))
    assert literals <= ALLOWED_LITERALS, f"hand-typed result-like numbers: {sorted(literals - ALLOWED_LITERALS)}"


def test_every_citation_has_a_bib_entry_and_back():
    bib = (PAPER / "references.bib").read_text(encoding="utf-8")
    entries = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited = set()
    for group in re.findall(r"\\cite\{([^}]+)\}", _body()):
        cited |= {key.strip() for key in group.split(",")}
    assert cited <= entries, f"cited but missing from references.bib: {sorted(cited - entries)}"
    assert entries <= cited, f"in references.bib but never cited: {sorted(entries - cited)}"
