#!/usr/bin/env python3
"""Derive and cross-check the K17d identity lists from frozen scene metadata (E10). Metadata only.

Resolves the 500 headline test-role groups through ``geosim.b2_k17d.derive_from_generator``, which calls only
``prepare_scene`` (plans, link and carrier activity). ``simulate_dual`` is patched to fail, so any waveform
synthesis aborts the run. No held-out observation is read or written. The derived identities are cross-checked
against the committed audit ``docs/results/k17d_drift_audit.json``; the output is written only when the
cross-check agrees exactly. Otherwise the script exits non-zero and writes nothing.

Usage: python scripts/b2_e10_k17d_identity.py [--out docs/results/b2_e10_k17d_identity.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geosim import b2_k17d as K  # noqa: E402
from geosim import b2_scenarios  # noqa: E402

STATUS = "DERIVED_FROM_FROZEN_GENERATOR_METADATA_CROSS_CHECKED_PENDING_RESEARCHER_ACCEPTANCE"
AUDIT = "docs/results/k17d_drift_audit.json"
SOURCES = ("src/geosim/b2_scenarios.py", "src/geosim/b2_protocol.py", "src/geosim/b2_k17d.py")


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_digest():
    """SHA-256 over every module of src/geosim, each bound to its repository-relative path.

    Any edit to the generator or to this validator changes the digest, so a committed record that no longer
    matches the current source is detected by the records test.
    """
    digest = hashlib.sha256()
    files = sorted((ROOT / "src" / "geosim").glob("*.py"))
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        digest.update(name.encode("utf-8") + b"\0" + _sha256_file(path).encode("ascii") + b"\n")
    return digest.hexdigest(), len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="docs/results/b2_e10_k17d_identity.json")
    parser.add_argument("--audit", default=AUDIT)
    args = parser.parse_args(argv)

    calls = {"simulate_dual": 0}

    def forbidden(*_a, **_k):
        calls["simulate_dual"] += 1
        raise RuntimeError("waveform synthesis attempted from the K17d metadata derivation")

    b2_scenarios.simulate_dual = forbidden
    try:
        derived = K.derive_from_generator()
    except RuntimeError as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1
    audit_path = ROOT / args.audit
    audit = json.loads(audit_path.read_text())
    try:
        cross = K.cross_check_audit(derived, audit)
    except K.K17dError as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1
    if calls["simulate_dual"]:
        print("FAIL-CLOSED: waveform path was reached", file=sys.stderr)
        return 1

    package_sha256, package_files = package_digest()
    record = {
        "schema": "B2-E10-k17d-identity-record/1",
        "status": STATUS,
        "authorizes": "nothing; the identity list is a candidate pending researcher acceptance",
        "observation_reads": 0,
        "waveform_synthesis_calls": calls["simulate_dual"],
        "package_sha256": package_sha256,
        "package_files": package_files,
        "source_sha256": {path: _sha256_file(ROOT / path) for path in SOURCES},
        "audit_path": args.audit,
        "audit_sha256": _sha256_file(audit_path),
        "derivation": {
            "generator": "geosim.b2_scenarios.prepare_scene (metadata only, label 'clean')",
            "groups": "frozen test role 3200000-3200499",
            "predicate": derived["predicate"],
            "note": ("No committed production generation metadata exists in this repository. The identities are "
                     "derived from the frozen generator's scene metadata at the source hashes above, which is the "
                     "generator a production run would use. Researcher acceptance is required before any test read."),
        },
        "counts": derived["counts"],
        "fingerprints": derived["fingerprints"],
        "audit_cross_check": cross,
        "headline_ids": derived["headline_ids"],
        "co_feed_missing_ids": derived["co_feed_missing_ids"],
        "sensitivity_ids": derived["sensitivity_ids"],
        "cross_feed_missing_ids": derived["cross_feed_missing_ids"],
    }
    out = (ROOT / args.out).resolve()
    label = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(K.canonical(record) + "\n")
    print(f"wrote {label}: counts={derived['counts']} agrees={cross['agrees']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
