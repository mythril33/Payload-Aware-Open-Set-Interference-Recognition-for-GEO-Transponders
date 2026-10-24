"""E12 read-only metadata checks. No IQ, observation artifact, waveform or fit.

The only real generator call resolves metadata through prepare_scene; waveform
synthesis and NumPy observation loading are patched to fail in that test. The
fixed, committed ETSI FIR coefficients needed by config validation are allowed.
All corruption tests mutate isolated copies, never committed historical records.
"""
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from geosim import b2_k17d as K, b2_scenarios

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("b2_e12_verify_k17d", ROOT / "scripts/b2_e12_verify_k17d.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + "\n")


@pytest.fixture
def metadata(tmp_path):
    for source in (ROOT / "src/geosim").glob("*.py"):
        destination = tmp_path / "src/geosim" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for name in (V.IDENTITY, V.AUDIT):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def mutate(root, fn):
    path = root / V.IDENTITY
    record = json.loads(path.read_text())
    fn(record)
    write(path, record)


def acceptance(root):
    record = json.loads((root / V.IDENTITY).read_text())
    document = {"schema": "B2-E12-scientific-decisions/1", "scientific_decisions_ratified": True,
                "execution_authorized": False, "production_authorized": False,
                "activation": False, "benchmark_complete": False,
                "decisions": {"D-8": {"choice": "A", "status": "RESEARCHER_APPROVED"}},
                "k17d_identity": {"path": V.IDENTITY, "sha256": hashlib.sha256((root / V.IDENTITY).read_bytes()).hexdigest()}}
    document["k17d_bindings"] = {name: record[name] for name in
                                ("schema", "source_sha256", "package_files", "package_sha256",
                                 "audit_path", "audit_sha256", "fingerprints")}
    path = root / "acceptance.json"
    write(path, document)
    return path


def test_committed_identity_rederives_without_waveforms_or_observation_reads(monkeypatch):
    paths = [ROOT / V.IDENTITY, ROOT / V.AUDIT]
    before = [p.read_bytes() for p in paths]
    def forbidden(*_args, **_kwargs):
        raise AssertionError("observation/waveform access is forbidden")
    original_load = np.load
    def coefficients_only(path, *args, **kwargs):
        assert Path(path).resolve() == (ROOT / "src/geosim/data/mux_fir.npz").resolve()
        return original_load(path, *args, **kwargs)
    monkeypatch.setattr(np, "load", coefficients_only)
    monkeypatch.setattr(b2_scenarios, "simulate_dual", forbidden)
    report = V.verify_identity()
    assert report["counts"] == V.COUNTS
    assert report["audit_agrees"] is report["generator_rederived"] is True
    assert report["identity_sha256"] == "ccdf0a8f40e71d7ddb388068e455a77a131214f5644ab332a16c8268cfc49c6d"
    assert report["observation_reads"] == report["waveform_synthesis_calls"] == 0
    assert report["execution_authorized"] is report["benchmark_complete"] is False
    assert report["production_metadata_cross_check"] == "NOT_RUN_REQUIRES_SEPARATE_AUTHORIZATION"
    assert [p.read_bytes() for p in paths] == before
    json.loads(K.canonical(report), parse_constant=forbidden)


def test_metadata_only_synthetic_mode_does_not_claim_generator_or_production_validation(metadata):
    result = V.verify_identity(root=metadata, rederive=False)
    assert result["generator_rederived"] is False
    assert result["execution_authorized"] is False
    assert result["production_metadata_cross_check"].startswith("NOT_RUN")


@pytest.mark.parametrize("mutator,match", [
    (lambda r: r["source_sha256"].update({"src/geosim/b2_scenarios.py": "0" * 64}), "generator source hashes"),
    (lambda r: r.update(package_sha256="0" * 64), "generator package hash"),
    (lambda r: r.update(package_files=27), "generator package hash"),
    (lambda r: r.update(audit_sha256="0" * 64), "audit path/hash"),
    (lambda r: r.update(audit_path="other.json"), "audit path/hash"),
    (lambda r: r["fingerprints"].update({"co_feed_missing_ids": "0" * 64}), "fingerprint mismatch"),
    (lambda r: r["headline_ids"].pop(), "missing, duplicate"),
    (lambda r: r["co_feed_missing_ids"].__setitem__(1, r["co_feed_missing_ids"][0]), "missing, duplicate"),
    (lambda r: r["cross_feed_missing_ids"].reverse(), "missing, duplicate"),
    (lambda r: r["headline_ids"].__setitem__(0, 3000000), "outside the frozen test role"),
    (lambda r: r["headline_ids"].__setitem__(0, True), "integer IDs"),
    (lambda r: r["derivation"].update(groups="train 3000000-3000499"), "role/predicate"),
    (lambda r: r["derivation"].update(predicate="dropped pol == 1"), "role/predicate"),
    (lambda r: r.update(unknown_score=0.8), "frozen metadata contract"),
    (lambda r: r.update(role="val-calib"), "frozen metadata contract"),
    (lambda r: r.update(observation_reads=1), "zero observations"),
    (lambda r: r.update(waveform_synthesis_calls=True), "zero observations"),
    (lambda r: r.update(authorizes="production"), "cannot authorize"),
    (lambda r: r.update(status="APPROVED"), "historical identity status"),
])
def test_metadata_and_hash_tampering_is_rejected(metadata, mutator, match):
    mutate(metadata, mutator)
    with pytest.raises(K.K17dError, match=match):
        V.verify_identity(root=metadata, rederive=False)


@pytest.mark.parametrize("name", ["src/geosim/b2_scenarios.py", "src/geosim/b2_protocol.py",
                                  "src/geosim/b2_k17d.py", "src/geosim/dual.py", V.AUDIT])
def test_generator_or_audit_file_change_requires_new_derivation_review(metadata, name):
    path = metadata / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(K.K17dError, match="hash"):
        V.verify_identity(root=metadata, rederive=False)


@pytest.mark.parametrize("name", [V.IDENTITY, V.AUDIT, "src/geosim/b2_scenarios.py"])
def test_missing_metadata_or_source_is_rejected(metadata, name):
    (metadata / name).unlink()
    with pytest.raises(K.K17dError, match="missing/unreadable"):
        V.verify_identity(root=metadata, rederive=False)


def test_co_cross_swap_cannot_preserve_the_partition(metadata):
    def swap(record):
        co, cross = record["co_feed_missing_ids"], record["cross_feed_missing_ids"]
        co[0], cross[0] = cross[0], co[0]
        co.sort(); cross.sort()
        # Self-recomputed co fingerprint still cannot repair the physical partition.
        record["fingerprints"]["co_feed_missing_ids"] = K.sha256_of(co)
    mutate(metadata, swap)
    with pytest.raises(K.K17dError, match="partition mismatch|co/cross-feed"):
        V.verify_identity(root=metadata, rederive=False)


def test_bound_acceptance_is_separate_from_immutable_non_authorizing_identity(metadata):
    path = acceptance(metadata)
    before = (metadata / V.IDENTITY).read_bytes()
    result = V.verify_identity(root=metadata, acceptance_path=path, rederive=False)
    assert result["acceptance_record_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["execution_authorized"] is False
    assert (metadata / V.IDENTITY).read_bytes() == before


@pytest.mark.parametrize("mutator,match", [
    (lambda a: a["k17d_identity"].update(sha256="0" * 64), "SHA-256 binding"),
    (lambda a: a["k17d_identity"].update(path="another-identity.json"), "SHA-256 binding"),
    (lambda a: a["decisions"]["D-8"].update(choice="B"), "D-8 acceptance"),
    (lambda a: a["decisions"]["D-8"].update(status="PENDING_RESEARCHER"), "D-8 acceptance"),
    (lambda a: a.update(execution_authorized=True), "cannot enable execution"),
    (lambda a: a.update(production_authorized=True), "cannot enable execution"),
    (lambda a: a.update(activation=True), "cannot enable execution"),
    (lambda a: a.update(benchmark_complete=True), "cannot enable execution"),
    (lambda a: a["k17d_bindings"].update(audit_sha256="0" * 64), "acceptance audit_sha256 binding"),
    (lambda a: a["k17d_bindings"]["source_sha256"].update({"src/geosim/b2_scenarios.py": "0" * 64}),
     "acceptance source_sha256 binding"),
])
def test_acceptance_binding_and_compute_negatives(metadata, mutator, match):
    path = acceptance(metadata)
    value = json.loads(path.read_text()); mutator(value); write(path, value)
    with pytest.raises(K.K17dError, match=match):
        V.verify_identity(root=metadata, acceptance_path=path, rederive=False)


@pytest.mark.parametrize("content,match", [("{\"counts\":NaN}", "non-finite"),
                                          ("{\"counts\":1e999}", "non-finite"),
                                          ("{\"a\":1,\"a\":2}", "duplicate"),
                                          ("{broken", "invalid strict JSON")])
def test_strict_json_refuses_nonfinite_duplicate_or_malformed_documents(metadata, content, match):
    (metadata / V.IDENTITY).write_text(content)
    with pytest.raises(K.K17dError, match=match):
        V.verify_identity(root=metadata, rederive=False)


def test_cli_fails_without_writing_when_record_is_missing(tmp_path, capsys):
    missing = tmp_path / "absent.json"
    assert V.main(["--record", str(missing)]) == 1
    assert "FAIL-CLOSED" in capsys.readouterr().err
    assert not missing.exists()


def test_committed_acceptance_matches_the_immutable_identity_without_rewriting_it():
    path = ROOT / "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json"
    before = (ROOT / V.IDENTITY).read_bytes()
    report = V.verify_identity(acceptance_path=path, rederive=False)
    assert report["acceptance_record_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["execution_authorized"] is False
    assert (ROOT / V.IDENTITY).read_bytes() == before


def test_nested_malformed_identity_fields_raise_closed_metadata_errors(metadata):
    for name in ("derivation", "fingerprints"):
        original = (ROOT / V.IDENTITY).read_bytes()
        (metadata / V.IDENTITY).write_bytes(original)
        mutate(metadata, lambda r: r.update({name: None}))
        with pytest.raises(K.K17dError):
            V.verify_identity(root=metadata, rederive=False)


def test_changed_audit_polarization_cannot_be_repaired_by_updating_only_its_hash(metadata):
    audit_path = metadata / V.AUDIT
    value = json.loads(audit_path.read_text())
    value["rows"][0]["pol"] = 1 - value["rows"][0]["pol"]
    write(audit_path, value)
    mutate(metadata, lambda r: r.update(audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest()))
    with pytest.raises(K.K17dError, match="polarization mismatches"):
        V.verify_identity(root=metadata, rederive=False)


def test_source_change_during_verification_is_refused(metadata, monkeypatch):
    original = V._source_binding
    counter = 0
    def unstable(root):
        nonlocal counter
        counter += 1
        sources, package, count = original(root)
        return sources, package if counter == 1 else "0" * 64, count
    monkeypatch.setattr(V, "_source_binding", unstable)
    with pytest.raises(K.K17dError, match="changed during verification"):
        V.verify_identity(root=metadata, rederive=False)


def test_even_unused_nested_audit_fields_cannot_hide_nonfinite_overflow(metadata):
    path = metadata / V.AUDIT
    audit = json.loads(path.read_text())
    audit["unused_nested"] = {"value": "OVERFLOW_SENTINEL"}
    path.write_text(json.dumps(audit).replace('"OVERFLOW_SENTINEL"', "1e999"))
    mutate(metadata, lambda r: r.update(audit_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    with pytest.raises(K.K17dError, match="non-finite"):
        V.verify_identity(root=metadata, rederive=False)
