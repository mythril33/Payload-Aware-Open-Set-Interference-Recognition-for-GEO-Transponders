"""E7b role-scoped reads on canonical artifacts with deterministic stand-in physics.

No real held-out population, RF generation, fitting or model selection is used.
"""
import builtins
import json
from pathlib import Path

import numpy as np
import pytest

from geosim import b2_dataset as ds
from geosim.b2_protocol import BASE_ROLES, ROLE_STARTS
from geosim.cancellation import CancellationConfig
from geoml.b2_stream import open_b2_known, open_b2_known_roles
from test_b2_artifacts import feature_generator, generator  # noqa: F401


@pytest.fixture
def artifact(tmp_path, feature_generator):
    root = tmp_path / "role-scoped"
    ds.generate_b2_dataset(root, limit_groups=2, groups_per_shard=1,
                           cancellation=CancellationConfig())
    return root


def _refuse_unrequested_reads(monkeypatch, root, roles):
    """Guard the actual file boundary, not just the caller's declared source roles."""
    original_open = builtins.open
    original_path_open = Path.open
    seen = []

    def check(path):
        try:
            relative = Path(path).relative_to(root)
        except (TypeError, ValueError):
            return
        if relative.parts and relative.parts[0] in BASE_ROLES:
            if relative.suffix in (".npz", ".jsonl"):
                assert relative.parts[0] in roles, f"unrequested observation content read: {relative}"
                seen.append(relative.parts[0])

    def guarded_open(file, *args, **kwargs):
        check(file)
        return original_open(file, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        check(path)
        return original_path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    return seen


@pytest.mark.parametrize("roles", [("train", "val-select"), ("val-calib",), ("test",)])
def test_scoped_reader_never_opens_other_observation_contents(artifact, monkeypatch, roles):
    seen = _refuse_unrequested_reads(monkeypatch, artifact, roles)
    manifest, identity, sources = open_b2_known_roles(artifact, roles)
    assert tuple(sources) == roles and identity == ds._fingerprint(manifest)
    for role, source in sources.items():
        assert len(source) == 16 and source.role == role and source.has_residual
        assert source.groups.tolist() == [ROLE_STARTS[role], ROLE_STARTS[role] + 1]
        assert sum(len(shard["seed"]) for shard in source.shards()) == 16
    assert set(seen) == set(roles)


def test_scoped_and_legacy_all_role_values_and_identity_match(artifact):
    manifest, identity, legacy = open_b2_known(artifact)
    scoped_manifest, scoped_identity, scoped = open_b2_known_roles(artifact, BASE_ROLES)
    assert scoped_manifest == manifest and scoped_identity == identity == ds.b2_fingerprint(artifact)
    for role in BASE_ROLES:
        assert scoped[role].shard_counts == legacy[role].shard_counts == [8, 8]
        for key in ("label", "seed", "plan_consistency"):
            np.testing.assert_array_equal(scoped[role].index[key], legacy[role].index[key])
        for selected, original in zip(scoped[role].shards(), legacy[role].shards()):
            for key in ("spec", "mask", "residual", "label", "seed", "plan_consistency"):
                np.testing.assert_array_equal(selected[key], original[key])


@pytest.mark.parametrize("roles", [(), [], "train", {"train"}, None, ["train", "train"],
                                  ["test-matched"], ["train", "foreign"], [True]])
def test_invalid_role_requests_fail_before_any_artifact_read(tmp_path, roles):
    with pytest.raises(ValueError, match="roles"):
        open_b2_known_roles(tmp_path / "does-not-exist", roles)


@pytest.mark.parametrize("suffix", [".npz", ".jsonl"])
def test_corrupt_unrequested_test_content_is_not_read_or_certified(artifact, suffix):
    path = next((artifact / "test").glob("*" + suffix))
    path.write_bytes(b"deliberately corrupted held-out content")
    _, _, sources = open_b2_known_roles(artifact, ("train", "val-select"))
    assert set(sources) == {"train", "val-select"}
    # The staged training read is intentionally no certificate of held-out bytes.
    with pytest.raises(ValueError):
        open_b2_known_roles(artifact, ("test",))
    with pytest.raises(ValueError):
        open_b2_known(artifact)


@pytest.mark.parametrize("suffix", [".npz", ".jsonl"])
def test_corrupt_requested_observation_contents_fail_closed(artifact, suffix):
    path = next((artifact / "train").glob("*" + suffix))
    path.write_bytes(b"corrupted selected content")
    with pytest.raises(ValueError):
        open_b2_known_roles(artifact, ("train", "val-select"))


def test_scope_does_not_allow_foreign_role_manifest_or_missing_files(artifact):
    path = artifact / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["roles"]["val-select"]["scenario_seeds"] = manifest["roles"]["train"]["scenario_seeds"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        open_b2_known_roles(artifact, ("train",))


def test_unrequested_role_is_still_required_to_be_structurally_complete(artifact):
    next((artifact / "test").glob("*.npz")).unlink()
    with pytest.raises(ValueError):
        open_b2_known_roles(artifact, ("train",))


def test_requested_role_must_have_been_generated(tmp_path, feature_generator):
    root = tmp_path / "train-only-artifact"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, cancellation=CancellationConfig())
    with pytest.raises(ValueError, match="roles"):
        open_b2_known_roles(root, ("train", "val-select"))


def test_base_stage_scope_keeps_its_original_no_residual_contract(tmp_path, generator):
    root = tmp_path / "base"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1)
    manifest, identity, sources = open_b2_known_roles(root, ("train",))
    assert manifest["protocol"] == "B2-base/1" and not sources["train"].has_residual
    assert identity == ds.b2_fingerprint(root)


def _replace_selected_arrays_and_rebind_checksums(root, mutate):
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    descriptor = manifest["roles"]["train"]["shards"][0]
    part = root / "train" / descriptor["part"]
    with np.load(part, allow_pickle=False) as archive:
        arrays = {key:archive[key] for key in archive.files}
    mutate(arrays)
    np.savez(part, **arrays)
    descriptor["sha256"][part.name] = ds._file_hash(part)
    ds._paths(root, "train", 0)[2].write_text(json.dumps(descriptor))
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("case", ["duplicate_label", "foreign_group", "nonfinite_residual"])
def test_checksummed_but_semantically_invalid_selected_rows_are_rejected(artifact, case):
    def mutate(arrays):
        if case == "duplicate_label": arrays["label"][1] = arrays["label"][0]
        if case == "foreign_group": arrays["seed"][0] = ROLE_STARTS["val-calib"]
        if case == "nonfinite_residual": arrays["residual"][0, 0, 0] = np.nan
    _replace_selected_arrays_and_rebind_checksums(artifact, mutate)
    with pytest.raises(ValueError):
        open_b2_known_roles(artifact, ("train",))


def test_streamed_role_refuses_a_consistently_resigned_artifact_change(artifact):
    _, identity, sources = open_b2_known_roles(artifact, ("train",))
    _replace_selected_arrays_and_rebind_checksums(artifact, lambda a:a["spec"].__iadd__(np.float16(1.0)))
    # This is a valid new artifact with unchanged labels/group index, not a byte flip.
    _, changed, _ = open_b2_known_roles(artifact, ("train",))
    assert changed != identity
    with pytest.raises(ValueError, match="identity changed"):
        list(sources["train"].shards())
