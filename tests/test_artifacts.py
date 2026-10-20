"""Dataset artifacts must never silently mix requests or accept damaged samples."""
from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import dataset as ds
from geosim.interferers import InfeasibleCarrierError


@pytest.fixture
def generated(tmp_path, monkeypatch):
    """Cheap deterministic observations; physical generation is covered in test_dataset."""
    def fake_sample(label, bandwidth, seed, ranges, linear=False, amplifier="dvbs2_nl"):
        spec = np.full((128, 512), -90 + ds.LABELS.index(label), np.float32)
        mask = np.full(512, -60.0, np.float32)
        mask[200:260] = 0.0
        return SimpleNamespace(spec_db=spec, mask_db=mask,
                               meta={"label": label, "config": {"seed": seed, "bandwidth": bandwidth,
                                                              "linear": linear, "amplifier": amplifier}})
    monkeypatch.setattr(ds, "sample", fake_sample)
    ds.generate(str(tmp_path), ["val_nl"], limit_seeds=2)
    return tmp_path, tmp_path / "val_nl"


def test_valid_resume_preserves_contents_and_fingerprint(generated):
    root, path = generated
    before = ds.split_fingerprint(path)
    timestamps = {p.name: p.stat().st_mtime_ns for p in path.glob("part-*.npz")}
    ds.generate(str(root), ["val_nl"], limit_seeds=2)
    manifest = ds.read_manifest(path)
    assert manifest["artifact_version"] == 2
    assert manifest["scenario_seeds"] == [200000, 200001]
    assert manifest["complete"] is False
    assert ds.split_fingerprint(path) == before
    assert {p.name: p.stat().st_mtime_ns for p in path.glob("part-*.npz")} == timestamps


def test_completed_resume_preserves_original_revision_after_head_change(generated, monkeypatch):
    root, path = generated
    manifest_path = path / "manifest.json"
    original_bytes = manifest_path.read_bytes()
    original_mtime = manifest_path.stat().st_mtime_ns
    original_fingerprint = ds.split_fingerprint(path)
    monkeypatch.setattr(ds, "_commit", lambda: "new-docs-only-revision")
    ds.generate(str(root), ["val_nl"], limit_seeds=2)
    assert manifest_path.read_bytes() == original_bytes
    assert manifest_path.stat().st_mtime_ns == original_mtime
    assert ds.split_fingerprint(path) == original_fingerprint


@pytest.mark.parametrize("limit", [1, 3, None])
def test_resume_rejects_changed_seed_request(generated, limit):
    root, path = generated
    before = (path / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="request changed"):
        ds.generate(str(root), ["val_nl"], limit_seeds=limit)
    assert (path / "manifest.json").read_bytes() == before


def test_resume_rejects_changed_generator(generated, monkeypatch):
    root, _ = generated
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"changed.py": "changed"})
    with pytest.raises(ValueError, match="request changed"):
        ds.generate(str(root), ["val_nl"], limit_seeds=2)


def test_resume_rejects_changed_physical_configuration(generated, monkeypatch):
    root, _ = generated
    monkeypatch.setitem(ds.SPLITS, "val_nl", replace(ds.SPLITS["val_nl"], bandwidth=72e6))
    with pytest.raises(ValueError, match="request changed"):
        ds.generate(str(root), ["val_nl"], limit_seeds=2)


@pytest.mark.parametrize("filename", ["part-00000.npz", "meta-00000.jsonl"])
def test_load_and_resume_reject_modified_content(generated, filename):
    root, path = generated
    with (path / filename).open("ab") as stream:
        stream.write(b"modified")
    for action in (lambda: ds.load_split(path), lambda: ds.read_manifest(path),
                   lambda: ds.split_fingerprint(path),
                   lambda: ds.generate(str(root), ["val_nl"], limit_seeds=2)):
        with pytest.raises(ValueError, match="modified dataset artifact"):
            action()


def test_load_rejects_extra_and_missing_shards(generated):
    _, path = generated
    extra = path / "part-00001.npz"
    extra.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="Unexpected or missing"):
        ds.load_split(path)
    extra.unlink()
    (path / "meta-00000.jsonl").unlink()
    with pytest.raises(ValueError, match="Unexpected or missing"):
        ds.load_split(path)


def test_load_rejects_wrong_manifest_counts(generated):
    _, path = generated
    m = json.loads((path / "manifest.json").read_text())
    m["n_samples"] += 1
    (path / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="sample counts"):
        ds.load_split(path)


def _make_legacy(path):
    m = json.loads((path / "manifest.json").read_text())
    for key in ("artifact_version", "scenario_seeds", "request", "request_fingerprint", "shards"):
        del m[key]
    (path / "manifest.json").write_text(json.dumps(m))
    (path / "request.json").unlink()
    for p in path.glob("shard-*.json"):
        p.unlink()


def test_legacy_read_only_compatibility(generated):
    root, path = generated
    _make_legacy(path)
    assert len(ds.load_split(path)["label"]) == 10
    assert len(ds.split_fingerprint(path)) == 64
    with pytest.raises(ValueError, match="Legacy/unverified"):
        ds.generate(str(root), ["val_nl"], limit_seeds=2)


def test_legacy_metadata_must_match_observations(generated):
    _, path = generated
    _make_legacy(path)
    p = path / "meta-00000.jsonl"
    records = [json.loads(line) for line in p.read_text().splitlines()]
    records[0]["config"]["seed"] += 99
    p.write_text("\n".join(json.dumps(m) for m in records) + "\n")
    with pytest.raises(ValueError, match="metadata label/seed"):
        ds.load_split(path)


def test_interrupted_generation_reuses_verified_shards(generated):
    root, path = generated
    (path / "manifest.json").unlink()
    before = (path / "part-00000.npz").stat().st_mtime_ns
    ds.generate(str(root), ["val_nl"], limit_seeds=2)
    assert (path / "part-00000.npz").stat().st_mtime_ns == before
    assert ds.read_manifest(path)["n_samples"] == 10


def test_interrupted_uncommitted_temporary_files_are_regenerated(generated):
    root, path = generated
    for pattern in ("manifest.json", "part-*.npz", "meta-*.jsonl", "shard-*.json"):
        for p in path.glob(pattern):
            p.unlink()
    (path / "part-00000.tmp.npz").write_bytes(b"interrupted write")
    (path / "meta-00000.jsonl.tmp").write_bytes(b"interrupted write")
    ds.generate(str(root), ["val_nl"], limit_seeds=2)
    assert ds.read_manifest(path)["n_samples"] == 10


def test_unexpected_simulation_errors_propagate(monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("broken filter")
    monkeypatch.setattr(ds, "sample", broken)
    with pytest.raises(ValueError, match="broken filter"):
        ds.generate_seed(ds.SPLITS["val_nl"], 200000)


def test_only_explicitly_infeasible_unauthorized_scene_is_skipped(monkeypatch):
    def sample(label, *args, **kwargs):
        if label == "unauthorized":
            raise InfeasibleCarrierError("no physical gap")
        return label
    monkeypatch.setattr(ds, "sample", sample)
    assert ds.generate_seed(ds.SPLITS["val_nl"], 200000) == ["clean", "cw", "swept_cw", "overdrive"]


@pytest.mark.parametrize("kwargs", [{"workers": 0}, {"limit_seeds": 0}, {"limit_seeds": -1},
                                    {"names": []}, {"names": ["wrong"]},
                                    {"names": ["val_nl", "val_nl"]}])
def test_invalid_generation_request_writes_nothing(tmp_path, kwargs):
    with pytest.raises(ValueError):
        ds.generate(str(tmp_path), **kwargs)
    assert not list(tmp_path.iterdir())
