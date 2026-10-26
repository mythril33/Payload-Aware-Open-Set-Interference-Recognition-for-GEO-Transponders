"""Provenance and integrity checks. Read-only: nothing here writes, regenerates or repairs a record.

The package digest is the same algorithm as scripts/b2_e10_k17d_identity.py::package_digest, so a
committed record can be checked against the current source tree. A mismatch is reported as STALE,
meaning the record was generated from different source and must be re-derived, not edited.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import evidence, results
from .paths import REPO_ROOT
from .repo_status import gate_rows

OK, STALE, FAILED, UNAVAILABLE = "OK", "STALE", "FAILED", "UNAVAILABLE"
K17D_RECORD = REPO_ROOT / "docs" / "results" / "b2_e10_k17d_identity.json"
K17D_AUDIT = REPO_ROOT / "docs" / "results" / "k17d_drift_audit.json"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_digest(repo: Path = REPO_ROOT) -> tuple[str, int]:
    """SHA-256 over src/geosim/*.py, each file bound to its repository-relative path."""
    digest = hashlib.sha256()
    files = sorted((repo / "src" / "geosim").glob("*.py"))
    for path in files:
        name = path.relative_to(repo).as_posix()
        digest.update(name.encode("utf-8") + b"\0" + sha256_file(path).encode("ascii") + b"\n")
    return digest.hexdigest(), len(files)


def check_k17d_record(repo: Path = REPO_ROOT) -> list[Check]:
    record_path = repo / "docs" / "results" / K17D_RECORD.name
    if not record_path.is_file():
        return [Check("K17d record present", UNAVAILABLE, "docs/results/b2_e10_k17d_identity.json is absent")]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    checks: list[Check] = []
    digest, _ = package_digest(repo)
    if record.get("package_sha256") == digest:
        checks.append(Check("K17d record bound to current src/geosim", OK, "package digest matches"))
    else:
        checks.append(Check("K17d record bound to current src/geosim", STALE,
                            "src/geosim changed after the record was generated; re-derive it, do not edit it"))
    for rel, expected in sorted(record.get("source_sha256", {}).items()):
        path = repo / rel
        actual = sha256_file(path) if path.is_file() else None
        checks.append(Check(f"source hash {rel}", OK if actual == expected else STALE,
                            "matches the record" if actual == expected else "differs from the record"))
    audit_path = repo / "docs" / "results" / K17D_AUDIT.name
    if audit_path.is_file():
        ok = sha256_file(audit_path) == record.get("audit_sha256")
        checks.append(Check("K17d audit hash", OK if ok else STALE,
                            "matches the record" if ok else "audit file differs from the record"))
    boundary_ok = record.get("observation_reads") == 0 and record.get("waveform_synthesis_calls") == 0
    checks.append(Check("K17d record boundary (no observation reads, no waveform calls)",
                        OK if boundary_ok else FAILED,
                        f"observation_reads={record.get('observation_reads')}, "
                        f"waveform_synthesis_calls={record.get('waveform_synthesis_calls')}"))
    return checks


def check_gate_invariants(repo: Path = REPO_ROOT) -> Check:
    rows = gate_rows(repo)
    if not rows:
        return Check("gate invariants", UNAVAILABLE, "no gate record found")
    bad = [r["gate"] for r in rows if r.get("matches_expected") is False]
    closure_open = [r["gate"] for r in rows if r["gate"] in ("production_authorized", "activation",
                                                            "benchmark_complete", "readiness: benchmark_complete")
                    and r["value"] is not False]
    if bad or closure_open:
        return Check("gate invariants", FAILED, f"unexpected: {bad + closure_open}")
    return Check("gate invariants", OK, "closure gates are False; operational decisions match their expected values")


def check_evidence_coverage() -> Check:
    entries = evidence.inventory()
    unclassified = [e.path for e in entries if e.evidence_class == evidence.UNCLASSIFIED]
    stale = [e.path for e in entries if e.evidence_class == evidence.STALE]
    if unclassified or stale:
        return Check("evidence map coverage", FAILED, f"unclassified={unclassified} stale={stale}")
    return Check("evidence map coverage", OK, f"{len(entries)} files classified; none unclassified")


def check_restricted_not_in_catalog() -> Check:
    restricted = {e.path for e in evidence.inventory() if e.evidence_class == evidence.RESTRICTED}
    catalogued = {spec.file for spec in results.CATALOG}
    overlap = sorted(restricted & catalogued)
    if overlap:
        return Check("restricted files kept out of the metric catalog", FAILED, f"found: {overlap}")
    return Check("restricted files kept out of the metric catalog", OK, "no restricted file is read for values")


def check_generated_not_tracked(repo: Path = REPO_ROOT) -> Check:
    try:
        done = subprocess.run(["git", "ls-files", "data", "runs"], cwd=str(repo), capture_output=True,
                              text=True, timeout=30, check=False, shell=False)
    except (OSError, subprocess.SubprocessError):
        return Check("generated artifacts are not in Git", UNAVAILABLE, "git is not available")
    tracked = [line for line in done.stdout.splitlines() if line.strip()]
    if tracked:
        return Check("generated artifacts are not in Git", FAILED, f"{len(tracked)} tracked files under data/ or runs/")
    return Check("generated artifacts are not in Git", OK, "nothing under data/ or runs/ is tracked")


def all_checks(repo: Path = REPO_ROOT) -> list[Check]:
    checks = check_k17d_record(repo)
    checks.append(check_gate_invariants(repo))
    checks.append(check_evidence_coverage())
    checks.append(check_restricted_not_in_catalog())
    checks.append(check_generated_not_tracked(repo))
    return checks


__all__ = ["Check", "OK", "STALE", "FAILED", "UNAVAILABLE", "package_digest", "sha256_file", "all_checks",
           "check_k17d_record", "check_gate_invariants", "check_evidence_coverage"]
