#!/usr/bin/env python3
"""Read-only E12 K17d metadata/provenance verification; never an execution authorizer.

The historical E10 identity artifact is immutable. Acceptance belongs to a separate
dated decision register. This command resolves scene metadata only, with waveform
synthesis explicitly forbidden; it neither opens observations nor writes artifacts.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geosim import b2_k17d as K  # noqa: E402
from geosim import b2_scenarios  # noqa: E402

IDENTITY = "docs/results/b2_e10_k17d_identity.json"
AUDIT = "docs/results/k17d_drift_audit.json"
SOURCES = {"src/geosim/b2_scenarios.py", "src/geosim/b2_protocol.py", "src/geosim/b2_k17d.py"}
COUNTS = {"headline": 500, "co_feed_missing": 35, "sensitivity": 465,
          "cross_feed_missing": 43, "missing_total": 78}
LISTS = {"headline_ids": 500, "co_feed_missing_ids": 35,
         "sensitivity_ids": 465, "cross_feed_missing_ids": 43}
FIELDS = {"schema", "status", "authorizes", "observation_reads", "waveform_synthesis_calls",
          "package_sha256", "package_files", "source_sha256", "audit_path", "audit_sha256",
          "derivation", "counts", "fingerprints", "audit_cross_check", *LISTS}


def _require(condition, message):
    if not condition:
        raise K.K17dError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _strict(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    def nonfinite(value):
        raise K.K17dError(f"non-finite JSON value {value}")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            nonfinite(value)
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)
    except (ValueError, UnicodeError) as error:
        raise K.K17dError(f"invalid strict JSON: {error}") from error
    _require(isinstance(value, dict), "JSON document must be a mapping")
    return value


def _read(path):
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise K.K17dError(f"missing/unreadable metadata: {path}") from error


def _source_binding(root):
    sources = {name: _sha(_read(root / name)) for name in sorted(SOURCES)}
    files = sorted((root / "src/geosim").glob("*.py"))
    package = hashlib.sha256()
    for path in files:
        name = path.relative_to(root).as_posix()
        package.update(name.encode() + b"\0" + _sha(_read(path)).encode() + b"\n")
    return sources, package.hexdigest(), len(files)


def verify_identity(record_path=IDENTITY, *, root=ROOT, audit_path=AUDIT,
                    acceptance_path=None, rederive=True):
    """Verify metadata identities and hashes, raising K17dError on any mismatch.

    ``rederive=False`` is for synthetic unit fixtures only and is explicitly
    reported as an incomplete generator check. The CLI always re-derives.
    Even a complete report authorizes no observation access or compute.
    """
    root = Path(root).resolve()
    resolve = lambda name: root / Path(name)
    record_file, audit_file = resolve(record_path), resolve(audit_path)
    raw_record, raw_audit = _read(record_file), _read(audit_file)
    record, audit = _strict(raw_record), _strict(raw_audit)
    _require(set(record) == FIELDS, "identity fields differ from the frozen metadata contract")
    _require(record["schema"] == "B2-E10-k17d-identity-record/1", "wrong identity schema")
    _require(record["status"] == "DERIVED_FROM_FROZEN_GENERATOR_METADATA_CROSS_CHECKED_PENDING_RESEARCHER_ACCEPTANCE",
             "historical identity status was rewritten")
    _require(isinstance(record["authorizes"], str) and record["authorizes"].startswith("nothing"),
             "identity artifact cannot authorize execution")
    _require(type(record["observation_reads"]) is int and record["observation_reads"] == 0
             and type(record["waveform_synthesis_calls"]) is int and record["waveform_synthesis_calls"] == 0,
             "identity artifact must declare zero observations/waveforms")
    _require(record["counts"] == COUNTS and all(type(v) is int for v in record["counts"].values()),
             "K17d counts differ from 500/35/465, cross43, total78")
    for name, count in LISTS.items():
        ids = record[name]
        _require(isinstance(ids, list) and all(type(g) is int for g in ids), f"{name} must contain integer IDs")
        _require(len(ids) == count and ids == sorted(set(ids)), f"{name} missing, duplicate or unsorted IDs")
        _require(set(ids) <= set(K.TEST_IDS), f"{name} carries IDs outside the frozen test role")
    _require(record["headline_ids"] == list(K.TEST_IDS), "headline IDs differ from frozen test role")
    co, cross, sensitivity = (set(record[name]) for name in
                              ("co_feed_missing_ids", "cross_feed_missing_ids", "sensitivity_ids"))
    _require(not co & sensitivity and co | sensitivity == set(K.TEST_IDS), "K17d partition mismatch")
    _require(not co & cross and cross <= sensitivity, "co/cross-feed identity confusion")
    _require(isinstance(record["fingerprints"], dict) and
             set(record["fingerprints"]) == {"headline_ids", "co_feed_missing_ids", "sensitivity_ids", "scene_metadata"},
             "unexpected identity fingerprints")
    for name in ("headline_ids", "co_feed_missing_ids", "sensitivity_ids"):
        _require(record["fingerprints"][name] == K.sha256_of(record[name]), f"{name} fingerprint mismatch")
    _require(isinstance(record["derivation"], dict) and set(record["derivation"]) == {"generator", "groups", "predicate", "note"},
             "malformed derivation metadata")
    _require(record["derivation"]["predicate"] == K.PREDICATE
             and record["derivation"]["groups"] == "frozen test role 3200000-3200499", "role/predicate mismatch")
    binding = _source_binding(root)
    _require(record["source_sha256"] == binding[0], "generator source hashes changed; re-derivation/review required")
    _require(record["package_sha256"] == binding[1] and type(record["package_files"]) is int
             and record["package_files"] == binding[2], "generator package hash changed; re-derivation/review required")
    _require(record["audit_path"] == AUDIT and record["audit_sha256"] == _sha(raw_audit), "audit path/hash mismatch")
    cross_check = K.cross_check_audit(record, audit)
    _require(record["audit_cross_check"] == cross_check, "stored audit cross-check differs")
    if rederive:
        def forbidden(*_args, **_kwargs):
            raise K.K17dError("waveform synthesis forbidden during metadata verification")
        with patch.object(b2_scenarios, "simulate_dual", forbidden):
            derived = K.derive_from_generator()
        for name in (*LISTS, "counts", "fingerprints"):
            _require(record[name] == derived[name], f"frozen generator {name} differs")
    raw_acceptance = None
    if acceptance_path is not None:
        raw_acceptance = _read(resolve(acceptance_path))
        acceptance = _strict(raw_acceptance)
        _require(acceptance.get("schema") == "B2-E12-scientific-decisions/1", "wrong acceptance schema")
        _require(acceptance.get("scientific_decisions_ratified") is True, "scientific acceptance absent")
        _require(all(acceptance.get(key) is False for key in
                     ("execution_authorized", "production_authorized", "activation", "benchmark_complete")),
                 "acceptance cannot enable execution")
        _require(isinstance(acceptance.get("decisions"), dict), "malformed acceptance decisions")
        accepted = acceptance["decisions"].get("D-8", {})
        _require(isinstance(accepted, dict), "malformed D-8 acceptance")
        _require(accepted.get("choice") == "A" and accepted.get("status") == "RESEARCHER_APPROVED",
                 "D-8 acceptance absent")
        identity = acceptance.get("k17d_identity", {})
        _require(isinstance(identity, dict), "malformed acceptance identity binding")
        _require(identity.get("path") == IDENTITY and identity.get("sha256") == _sha(raw_record),
                 "acceptance identity SHA-256 binding differs")
        accepted_bindings = acceptance.get("k17d_bindings")
        _require(isinstance(accepted_bindings, dict), "acceptance generator/audit bindings absent")
        for name in ("schema", "source_sha256", "package_files", "package_sha256",
                     "audit_path", "audit_sha256", "fingerprints"):
            _require(accepted_bindings.get(name) == record[name], f"acceptance {name} binding differs")
    _require(_read(record_file) == raw_record and _read(audit_file) == raw_audit
             and _source_binding(root) == binding, "metadata/source changed during verification")
    if raw_acceptance is not None:
        _require(_read(resolve(acceptance_path)) == raw_acceptance, "acceptance changed during verification")
    report = {"schema": "B2-E12-K17d-verification/1", "identity_sha256": _sha(raw_record),
              "audit_sha256": _sha(raw_audit), "source_sha256": binding[0], "package_sha256": binding[1],
              "counts": record["counts"], "fingerprints": record["fingerprints"], "audit_agrees": True,
              "generator_rederived": bool(rederive), "observation_reads": 0, "waveform_synthesis_calls": 0,
              "acceptance_record_sha256": None if raw_acceptance is None else _sha(raw_acceptance),
              "production_metadata_cross_check": "NOT_RUN_REQUIRES_SEPARATE_AUTHORIZATION",
              "execution_authorized": False, "benchmark_complete": False}
    K.canonical(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", default=IDENTITY)
    parser.add_argument("--audit", default=AUDIT)
    parser.add_argument("--acceptance")
    args = parser.parse_args(argv)
    try:
        report = verify_identity(args.record, audit_path=args.audit, acceptance_path=args.acceptance)
    except (K.K17dError, KeyError, TypeError) as error:
        print(f"FAIL-CLOSED: {error}", file=sys.stderr)
        return 1
    print(K.canonical(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
