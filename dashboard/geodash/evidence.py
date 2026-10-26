"""Evidence classes for committed result and plan files.

The classes come from dashboard/data/evidence_map.json. A file that is not in the map is reported as
UNCLASSIFIED, never as verified. A map entry whose file is gone is reported as STALE.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import EVIDENCE_MAP_PATH, REPO_ROOT

VERIFIED_HISTORICAL = "VERIFIED_HISTORICAL"
DEVELOPMENT_PILOT = "DEVELOPMENT_PILOT"
UNEXECUTED = "UNEXECUTED"
GATE_OR_APPROVAL = "GATE_OR_APPROVAL"
DERIVED_DOCUMENTATION = "DERIVED_DOCUMENTATION"
VERIFICATION_LOG = "VERIFICATION_LOG"
RESTRICTED = "RESTRICTED_HELDOUT_OBSERVATION"
UNCLASSIFIED = "UNCLASSIFIED"
STALE = "STALE_MAP_ENTRY"
PROTECTED_PRODUCTION = "PROTECTED_PRODUCTION"
SCANNED_SUFFIXES = (".json", ".md", ".head", ".jsonl")


@dataclass(frozen=True)
class EvidenceEntry:
    path: str                       # repository-relative, forward slashes
    evidence_class: str
    rationale: str
    heldout_raw_matches: dict
    values_displayable: bool        # False for RESTRICTED entries

    @property
    def has_heldout_content(self) -> bool:
        return any(count > 0 for count in self.heldout_raw_matches.values())


def load_map(path: Path = EVIDENCE_MAP_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "geo-dashboard-evidence-map/1":
        raise ValueError(f"unexpected evidence map schema in {path}")
    return data


def _rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def scanned_files(repo_root: Path = REPO_ROOT) -> list[str]:
    """Result records and gate records. Narrative plan Markdown is out of scope by design: it is not a result.

    docs/results: every top-level result, verification and log file (figures/ is not scanned).
    docs/plan: JSON gate, approval and proposal records only.
    """
    found: list[str] = []
    results_dir = repo_root / "docs" / "results"
    plan_dir = repo_root / "docs" / "plan"
    if results_dir.is_dir():
        for path in sorted(results_dir.iterdir()):
            if path.is_file() and path.suffix in SCANNED_SUFFIXES:
                found.append(_rel(path, repo_root))
    if plan_dir.is_dir():
        for path in sorted(plan_dir.iterdir()):
            if path.is_file() and path.suffix == ".json":
                found.append(_rel(path, repo_root))
    return found


def inventory(evidence_map: dict | None = None, repo_root: Path = REPO_ROOT) -> list[EvidenceEntry]:
    """One entry per scanned file, plus STALE entries for map rows whose file no longer exists."""
    evidence_map = evidence_map or load_map()
    classes = evidence_map["classes"]
    mapped = evidence_map["entries"]
    entries: list[EvidenceEntry] = []
    seen = set()
    for rel in scanned_files(repo_root):
        seen.add(rel)
        row = mapped.get(rel)
        if row is None:
            entries.append(EvidenceEntry(rel, UNCLASSIFIED, "not in the curated evidence map", {}, True))
            continue
        cls = row["class"]
        if cls not in classes:
            raise ValueError(f"{rel} carries an unknown evidence class {cls!r}")
        entries.append(EvidenceEntry(rel, cls, row["rationale"], row["heldout_raw_matches"],
                                     values_displayable=cls != RESTRICTED))
    for rel, row in sorted(mapped.items()):
        if rel not in seen:
            entries.append(EvidenceEntry(rel, STALE, "mapped but the file is absent", row["heldout_raw_matches"], False))
    return entries


def counts_by_class(entries: list[EvidenceEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.evidence_class] = counts.get(entry.evidence_class, 0) + 1
    return dict(sorted(counts.items()))


def classes_legend(evidence_map: dict | None = None) -> dict[str, str]:
    evidence_map = evidence_map or load_map()
    return dict(evidence_map["classes"])


__all__ = ["EvidenceEntry", "inventory", "counts_by_class", "load_map", "classes_legend", "scanned_files",
           "VERIFIED_HISTORICAL", "DEVELOPMENT_PILOT", "UNEXECUTED", "GATE_OR_APPROVAL", "DERIVED_DOCUMENTATION",
           "VERIFICATION_LOG", "RESTRICTED", "UNCLASSIFIED", "STALE", "PROTECTED_PRODUCTION"]
