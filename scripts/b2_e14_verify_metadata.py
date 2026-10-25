#!/usr/bin/env python3
"""E14 future-production K17d metadata verifier; no observations or authority.

``binding`` is trusted input from a separately admitted frozen run lock, NOT an
approval. This module cannot authenticate that lock. Production verification
always uses the fixed, accepted E12 identity in this checkout. It opens only
JSON/JSONL metadata and stats payload names; payload bytes, spectra, metrics and
model outputs are never opened. A separate checksum/restore audit is mandatory.
The explicit synthetic API cannot report production cross-verification.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from geosim import b2_k17d as K  # noqa: E402
from geosim import b2_protocol as P  # noqa: E402

BINDING_SCHEMA = "B2-E14-production-metadata-binding/1"
SYNTHETIC_SCHEMA = "B2-E14-fabricated-k17d-identity/1"
MAX_METADATA_BYTES = 4 * 1024 * 1024
IDENTITY = "docs/results/b2_e10_k17d_identity.json"
ACCEPTANCE = "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json"
COUNTS = {"headline": 500, "co_feed_missing": 35, "cross_feed_missing": 43,
          "missing_total": 78, "sensitivity": 465}
IDENTITY_FIELDS = ("headline_ids", "co_feed_missing_ids", "cross_feed_missing_ids",
                   "sensitivity_ids", "counts", "fingerprints")
SHA = re.compile(r"[0-9a-f]{64}\Z")
HEAD = re.compile(r"[0-9a-f]{40}\Z")


class MetadataError(ValueError):
    """Fail-closed refusal of a metadata claim; never a recoverable warning."""


def _require(condition, message):
    if not condition:
        raise MetadataError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise MetadataError("metadata is not finite strict JSON") from error


def _equal(left, right):
    return _canonical(left) == _canonical(right)


def _strict(raw):
    def pairs(items):
        output = {}
        for key, value in items:
            _require(key not in output, "duplicate JSON key")
            output[key] = value
        return output

    def number(value):
        result = float(value)
        _require(math.isfinite(result), "nonfinite JSON number")
        return result

    def nonfinite(_value):
        raise MetadataError("nonfinite JSON value")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise MetadataError("invalid strict JSON metadata") from error
    _require(isinstance(result, dict), "metadata document must be an object")
    return result


def _keys(value, names, label):
    _require(isinstance(value, dict) and set(value) == set(names), f"{label} fields differ")


def _hash(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _snapshot(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


class _MetadataReader:
    """Bounded, fd-relative, no-symlink metadata snapshot on POSIX.

    No writes or payload opens. Rechecks catch concurrent changes but cannot
    replace an immutable root or an external run lock against a hostile writer.
    """
    def __init__(self, root):
        _require(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
                 "platform lacks required no-follow directory operations")
        path = Path(root)
        _require(".." not in path.parts and "\\" not in str(path) and "\0" not in str(path),
                 "unsafe artifact root")
        path = path.absolute()
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in path.parts[1:]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        self.root_path = path
        self.seen = {}
        self.inodes = set()
        self.payload_stats = {}
        self.test_names = None

    def close(self):
        os.close(self.fd)

    def _parent(self, relative):
        pieces = relative.split("/")
        _require(all(re.fullmatch(r"[a-z0-9_.-]+", item) and item not in (".", "..") for item in pieces),
                 "unsafe metadata path")
        fd = os.dup(self.fd)
        try:
            for component in pieces[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd, pieces[-1]
        except BaseException:
            os.close(fd)
            raise

    def read(self, relative, *, recheck=False):
        _require(relative.endswith((".json", ".jsonl")), "only metadata opens are permitted")
        parent, name = self._parent(relative)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                     "metadata must be a unique regular file")
            _require(0 < before.st_size <= MAX_METADATA_BYTES, "metadata exceeds bounded size or is empty")
            key = (before.st_dev, before.st_ino)
            _require(recheck or key not in self.inodes, "metadata path aliases another artifact")
            chunks, remaining = [], MAX_METADATA_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            _require(len(raw) <= MAX_METADATA_BYTES and _snapshot(before) == _snapshot(os.fstat(fd)),
                     "metadata changed while reading or exceeds bounded size")
            observed = (_snapshot(before), _sha(raw))
            if recheck:
                _require(self.seen[relative] == observed, "metadata changed during verification")
            else:
                self.inodes.add(key)
                self.seen[relative] = observed
            return raw
        finally:
            os.close(fd)

    def payload_stat(self, relative, *, recheck=False):
        parent, name = self._parent(relative)
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        finally:
            os.close(parent)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size > 0,
                 "payload must be a nonempty unique regular file (bytes not verified)")
        observed = _snapshot(info)
        _require(recheck or (info.st_dev, info.st_ino) not in self.inodes, "payload aliases another artifact")
        if recheck:
            _require(self.payload_stats[relative] == observed, "payload stat changed during verification")
        else:
            self.inodes.add((info.st_dev, info.st_ino))
            self.payload_stats[relative] = observed

    def root_unchanged(self):
        current = _MetadataReader(self.root_path)
        try:
            before, after = os.fstat(self.fd), os.fstat(current.fd)
            _require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                     "artifact root pathname was replaced during verification")
        finally:
            current.close()

    def names(self):
        expected_root = sorted((*P.BASE_ROLES, "request.json", "manifest.json", "calibration.json", "receiver_calibration.npz"))
        _require(sorted(os.listdir(self.fd)) == expected_root, "unexpected or missing known-artifact root entries")
        for role in P.BASE_ROLES:
            role_fd = os.open(role, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
            os.close(role_fd)
        fd = os.open("test", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            actual = sorted(os.listdir(fd))
        finally:
            os.close(fd)
        expected = sorted(f"{kind}-{index:05d}.{extension}" for index in range(125)
                          for kind, extension in (("part", "npz"), ("meta", "jsonl"), ("shard", "json")))
        _require(actual == expected, "unexpected, incomplete or orphaned test-role shard files")
        if self.test_names is not None:
            _require(actual == self.test_names, "test directory changed during verification")
        self.test_names = actual

    def recheck(self):
        for relative in tuple(self.seen):
            self.read(relative, recheck=True)
        for relative in tuple(self.payload_stats):
            self.payload_stat(relative, recheck=True)
        self.names()
        self.root_unchanged()


def _accepted_identity():
    """Fixed repository acceptance, no alternative record/root argument."""
    name = "b2_e14_fixed_e12_identity"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/b2_e12_verify_k17d.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    try:
        report = verifier.verify_identity(acceptance_path=ACCEPTANCE, rederive=False)
        identity = _strict((ROOT / IDENTITY).read_bytes())
        _require(report["identity_sha256"] == _sha((ROOT / IDENTITY).read_bytes()), "identity changed during verification")
    except (K.K17dError, OSError) as error:
        raise MetadataError("fixed E12 identity/acceptance verification failed") from error
    return identity, report


def _binding(binding):
    _keys(binding, ("schema", "source_head", "request", "request_fingerprint"), "frozen binding")
    _require(binding["schema"] == BINDING_SCHEMA and isinstance(binding["source_head"], str)
             and HEAD.fullmatch(binding["source_head"]) is not None, "invalid source binding")
    request = binding["request"]
    keys = ("protocol", "parent_protocol", "artifact_stage", "benchmark_complete", "contract", "config",
            "roles", "scenario_groups", "limit_groups", "groups_per_shard", "source_sha256", "numpy_version",
            "scipy_version", "cancellation", "fifth_channel")
    _keys(request, keys, "known feature request")
    _require(_hash(binding["request_fingerprint"]) and binding["request_fingerprint"] == K.sha256_of(request),
             "request fingerprint differs from frozen binding")
    _require(request["protocol"] == P.FEATURE_PROTOCOL and request["parent_protocol"] == P.PROTOCOL
             and request["artifact_stage"] == P.FEATURE_STAGE and request["benchmark_complete"] is False
             and _equal(request["contract"], P.protocol_contract()) and _equal(request["fifth_channel"], P.FIFTH_CHANNEL),
             "request protocol or observation-only cancellation contract changed")
    _require(_equal(request["roles"], list(P.BASE_ROLES)) and request["limit_groups"] is None
             and type(request["groups_per_shard"]) is int and request["groups_per_shard"] == 4
             and _equal(request["scenario_groups"], {role: P.scenario_ids(role) for role in P.BASE_ROLES}),
             "full known-role inventory or four-group boundaries changed")
    for name in ("numpy_version", "scipy_version"):
        _require(isinstance(request[name], str) and re.fullmatch(r"[0-9]+(?:\.[0-9A-Za-z+_-]+)+", request[name]),
                 "missing exact numerical environment version")
    for field, filename in (("config", "configs/b2_base.json"), ("cancellation", "configs/cancellation.json")):
        _require(_equal(request[field], _strict((ROOT / filename).read_bytes())), "frozen configuration changed")
    sources = request["source_sha256"]
    _require(isinstance(sources, dict) and sources and all(isinstance(key, str) and _hash(value)
             for key, value in sources.items()), "malformed generator provenance")
    root = ROOT / "src/geosim"
    expected = {path.relative_to(root).as_posix(): _sha(path.read_bytes())
                for path in sorted(root.glob("*.py")) + sorted((root / "data").glob("*")) if path.is_file()}
    _require(_equal(sources, expected), "generator source/reference-data provenance differs from checkout")
    return request


def _project(record, group, label):
    _require(isinstance(record, dict), "sample metadata must be an object")
    _require(type(record.get("scenario_id")) is int and record["scenario_id"] == group
             and record.get("role") == "test" and record.get("label") == label,
             "sample metadata role/group/variant ordering differs")
    _require(record.get("protocol") == P.FEATURE_PROTOCOL and record.get("base_protocol") == P.BASE_PROTOCOL
             and record.get("parent_protocol") == P.PROTOCOL, "sample protocol provenance differs")
    _require(record.get("receiver_calibration_applied") is True, "uncalibrated sample metadata")
    _require(not set(record) & {"prediction", "predictions", "score", "scores", "accuracy", "metrics",
                                "embedding", "spec", "mask", "residual", "iq"}, "outcome/observation fields in metadata")
    _require(all(field in record for field in K.RECORD_KEYS), "missing K17d metadata field")
    projected = {key: record[key] for key in K.RECORD_KEYS}
    projected["protocol"] = P.BASE_PROTOCOL
    try:
        _, normalized = K._check_record(projected, group)
    except K.K17dError as error:
        raise MetadataError(str(error)) from error
    return normalized


def _verify(root, *, binding, identity, synthetic):
    request = _binding(binding)
    accepted_binding = _canonical(binding)
    reader = None
    try:
        reader = _MetadataReader(root)
        manifest = _strict(reader.read("manifest.json"))
        _keys(manifest, ("artifact_version", "protocol", "parent_protocol", "artifact_stage", "benchmark_complete",
                         "labels", "config", "request", "request_fingerprint", "commit", "calibration",
                         "calibration_artifact", "roles", "cancellation", "fifth_channel"), "known feature manifest")
        actual_request = _strict(reader.read("request.json"))
        _require(_equal(actual_request, request) and _equal(manifest.get("request"), request),
                 "manifest/request differs from frozen run binding")
        _require(type(manifest.get("artifact_version")) is int and manifest["artifact_version"] == 1
                 and manifest.get("protocol") == P.FEATURE_PROTOCOL
                 and manifest.get("artifact_stage") == P.FEATURE_STAGE
                 and manifest.get("parent_protocol") == P.PROTOCOL and manifest.get("benchmark_complete") is False
                 and manifest.get("commit") == binding["source_head"]
                 and manifest.get("request_fingerprint") == binding["request_fingerprint"]
                 and _equal(manifest.get("labels"), list(P.LABELS))
                 and _equal(manifest.get("config"), request["config"])
                 and _equal(manifest.get("cancellation"), request["cancellation"])
                 and _equal(manifest.get("fifth_channel"), request["fifth_channel"]),
                 "manifest stage/source/configuration provenance differs")
        roles = manifest.get("roles")
        _keys(roles, P.BASE_ROLES, "manifest roles")
        for role in P.BASE_ROLES:
            info, groups = roles[role], P.scenario_ids(role)
            _keys(info, ("scenario_seeds", "n_scenarios", "n_samples", "per_label", "shards"), "manifest role")
            _require(_equal(info["scenario_seeds"], groups)
                     and type(info["n_scenarios"]) is int and info["n_scenarios"] == len(groups)
                     and type(info["n_samples"]) is int and info["n_samples"] == len(groups) * len(P.LABELS)
                     and _equal(info["per_label"], {label: len(groups) for label in P.LABELS})
                     and isinstance(info["shards"], list) and len(info["shards"]) == (len(groups) + 3) // 4,
                     "manifest role inventory/counts differ")
        reader.names()
        projected, calibration = [], manifest.get("calibration")
        calibration_keys = ("artifact_version", "n_pilots", "max_condition", "reference_condition",
                            "response_condition", "residual_rms", "provenance", "response_real", "response_imag",
                            "parameter_sha256", "artifact_sha256")
        _keys(calibration, calibration_keys, "calibration provenance")
        _require(type(calibration["artifact_version"]) is int and calibration["artifact_version"] == 1
                 and type(calibration["n_pilots"]) is int and calibration["n_pilots"] == request["config"]["calibration_samples"]
                 and calibration["provenance"] == f"{P.FEATURE_PROTOCOL}:{binding['request_fingerprint']}:independent_pilots"
                 and _hash(calibration["parameter_sha256"]) and _hash(calibration["artifact_sha256"])
                 and calibration["artifact_sha256"] == K.sha256_of({key: value for key, value in calibration.items()
                                                                       if key != "artifact_sha256"}),
                 "independent calibration request/provenance checksum differs")
        calibration_artifact = _strict(reader.read("calibration.json"))
        _keys(calibration_artifact, ("file", "sha256", "metadata"), "calibration descriptor")
        _require(calibration_artifact["file"] == "receiver_calibration.npz" and _hash(calibration_artifact["sha256"])
                 and _equal(calibration_artifact["metadata"], calibration)
                 and _equal(manifest.get("calibration_artifact"), calibration_artifact), "calibration descriptor differs")
        reader.payload_stat("receiver_calibration.npz")
        for index, descriptor in enumerate(roles["test"]["shards"]):
            part, meta, commit = f"part-{index:05d}.npz", f"meta-{index:05d}.jsonl", f"shard-{index:05d}.json"
            groups = list(K.TEST_IDS)[4 * index:4 * (index + 1)]
            _keys(descriptor, ("part", "meta", "role", "scenario_seeds", "n_samples", "request_fingerprint", "sha256"),
                  "shard descriptor")
            _require(descriptor["part"] == part and descriptor["meta"] == meta and descriptor["role"] == "test"
                     and _equal(descriptor["scenario_seeds"], groups) and type(descriptor["n_samples"]) is int
                     and descriptor["n_samples"] == 32 and descriptor["request_fingerprint"] == binding["request_fingerprint"],
                     "shard role/group/count/request differs")
            _keys(descriptor["sha256"], (part, meta), "shard checksum")
            _require(all(_hash(value) for value in descriptor["sha256"].values()), "invalid shard checksum")
            _require(_equal(_strict(reader.read("test/" + commit)), descriptor), "commit descriptor differs from manifest")
            raw = reader.read("test/" + meta)
            _require(_sha(raw) == descriptor["sha256"][meta], "metadata checksum mismatch")
            rows = raw.splitlines()
            _require(len(rows) == 32, "incomplete or extra sample metadata rows")
            for position, group in enumerate(groups):
                scene = None
                for variant, label in enumerate(P.LABELS):
                    record = _strict(rows[position * 8 + variant])
                    _require(_equal(record.get("receiver_calibration"), calibration), "sample calibration binding differs")
                    normalized = _project(record, group, label)
                    _require(scene is None or _equal(scene, normalized), "paired variants disagree about K17d metadata")
                    scene = normalized
                projected.append(scene)
            reader.payload_stat("test/" + part)
        try:
            derived = K.derive(projected)
        except K.K17dError as error:
            raise MetadataError(str(error)) from error
        _require(_equal(derived["counts"], COUNTS), "production K17d 500/35/43/78/465 counts differ")
        for field in IDENTITY_FIELDS:
            _require(_equal(derived[field], identity[field]), f"accepted K17d {field} identity differs")
        reader.recheck()
        _require(_canonical(binding) == accepted_binding, "frozen binding changed during verification")
        _binding(binding)  # fail if source/config reference bytes changed during the metadata pass
        return {"schema": "B2-E14-K17d-production-metadata-verification/1", "verdict": "NO-GO",
                "metadata_status": "SYNTHETIC_FIXTURE_ONLY" if synthetic else "ACCEPTED_IDENTITY_METADATA_MATCH",
                "production_cross_verification_performed": not synthetic,
                "request_fingerprint": binding["request_fingerprint"], "source_head": binding["source_head"],
                "counts": derived["counts"], "fingerprints": derived["fingerprints"],
                "metadata_files_verified": len(reader.seen), "metadata_snapshot_sha256": K.sha256_of(
                    {key: value[1] for key, value in reader.seen.items()}),
                "payload_checksum_status": "NOT_VERIFIED_METADATA_ONLY_REQUIRES_SEPARATE_INTEGRITY_AUDIT",
                "observation_reads": 0, "waveform_synthesis_calls": 0, "execution_authorized": False,
                "production_authorized": False, "benchmark_complete": False,
                "d1_obligations": {"existing_test_pristine": False, "exposed_test_ids": [3200000, 3200001],
                                   "exposed_matched_ids": [3300000, 3300001], "exposure_excluded_groups": {"test": 498, "test-matched": 148}},
                "limitations": ["Trusted binding must come from a separately admitted frozen run lock; this API does not authenticate it.",
                                "Payload bytes, calibration arrays and non-test-role shard contents are not verified.",
                                "Immutable roots and an external run lock remain necessary against concurrent hostile writers."]}
    except (OSError, KeyError, TypeError, OverflowError, RecursionError) as error:
        raise MetadataError(f"invalid or unreadable production metadata ({type(error).__name__})") from error
    finally:
        if reader is not None:
            reader.close()


def verify_production_metadata(root, *, binding):
    """Read future production metadata against the fixed accepted E12 identity.

    ``binding`` must be supplied by a separately verified source/environment run
    lock. Matching metadata is neither permission to read observations nor proof
    of payload integrity, restore success or benchmark performance.
    """
    identity, accepted = _accepted_identity()
    report = _verify(root, binding=binding, identity=identity, synthetic=False)
    identity_after, accepted_after = _accepted_identity()
    _require(_equal(identity, identity_after) and _equal(accepted, accepted_after), "accepted identity changed during verification")
    report["identity_sha256"] = accepted["identity_sha256"]
    report["acceptance_record_sha256"] = accepted["acceptance_record_sha256"]
    _canonical(report)
    return report


def verify_synthetic_metadata(root, *, binding, identity):
    """Fabricated test-only contract; cannot assert a production cross-check."""
    _keys(identity, ("schema", *IDENTITY_FIELDS), "fabricated identity")
    _require(identity["schema"] == SYNTHETIC_SCHEMA, "synthetic API requires explicitly fabricated identity")
    report = _verify(root, binding=binding, identity=identity, synthetic=True)
    _canonical(report)
    return report
