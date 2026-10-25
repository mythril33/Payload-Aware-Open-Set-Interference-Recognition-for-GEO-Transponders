"""E18 synthetic ports: fake clock and resource readings, a fabricated-device attestor and a bounded fabricated-shard producer.

Nothing here is production code and nothing here can authorize anything. The attestor relabels a temporary workspace to the
roots and device numbers that the *plan* declares so that the E16 boundary report can be exercised over fabricated bytes; it is
exactly the kind of component a real deployment must replace with measured host facts. The lifecycle core never imports this
module (it receives these objects through ``SyntheticProfile``), and this module imports no generator, model or signer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e14_storage as S
import b2_e16_integration as I
import b2_e16_ledger as L

SYNTHETIC_PREFIX = b"E18-SYNTHETIC-NON-RF-FIXTURE\n"
START = "2026-10-30T12:05:00+00:00"
WORKING_DEVICE, BACKUP_DEVICE = 11, 22


class SyntheticClock:
    """Deterministic time that moves only when told to; ``monotonic`` is the same offset in seconds."""

    def __init__(self, start=START):
        self._start = datetime.fromisoformat(start).astimezone(timezone.utc)
        self._offset = 0.0

    def now(self):
        return (self._start + timedelta(seconds=int(self._offset))).isoformat()

    def monotonic(self):
        return self._offset

    def advance(self, seconds):
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0 <= seconds < 10 ** 7:
            raise ValueError("a bounded non-negative number of seconds is required")
        self._offset += float(seconds)


class SyntheticResources:
    """Injected CPU/RSS/disk readings derived from the synthetic clock. ``mutate`` is the fault-injection hook."""

    def __init__(self, clock, *, cpu_ratio=1.1458, peak_rss_gib=0.6, working_free_gib=400.0, backup_free_gb=90.0, base_wall_s=0.0, mutate=None):
        self.clock, self.cpu_ratio, self.peak_rss_gib = clock, cpu_ratio, peak_rss_gib
        self.working_free_gib, self.backup_free_gb, self.base_wall_s, self.mutate = working_free_gib, backup_free_gb, base_wall_s, mutate
        self.calls = 0

    def observe(self):
        self.calls += 1
        wall = self.base_wall_s + self.clock.monotonic()
        reading = {"collected_at": self.clock.now(), "elapsed_wall_s": wall, "cpu_core_s": wall * self.cpu_ratio,
                   "peak_rss_gib": self.peak_rss_gib, "working_free_gib": self.working_free_gib, "backup_free_gb": self.backup_free_gb}
        return reading if self.mutate is None else self.mutate(reading, self.calls)


def rewrite(value, mapping, devices):
    """Relabel path prefixes and ``st_dev`` numbers in a document tree (synthetic workspace -> plan-declared identities)."""
    if isinstance(value, dict):
        return {k: (devices.get(v, v) if k == "st_dev" and type(v) is int else rewrite(v, mapping, devices)) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v, mapping, devices) for v in value]
    if isinstance(value, str):
        for source, target in mapping:
            if value.startswith(source):
                return target + value[len(source):]
    return value


class SyntheticAttestor:
    """Fabricated host/storage/K17d attestations for a synthetic workspace. A real deployment replaces every method with measurements."""

    def __init__(self, plan, workspace, *, free_working_bytes=400 * 2 ** 30, free_backup_bytes=90 * 10 ** 9):
        self.plan, self.work, self.backup = plan, Path(workspace.work), Path(workspace.backup)
        self.free_working_bytes, self.free_backup_bytes = free_working_bytes, free_backup_bytes
        self.real_work, self.real_backup = os.stat(self.work).st_dev, os.stat(self.backup).st_dev
        self.k17d_override = None

    def stage_doc(self, stage, raw, now):
        root = raw["root"] if raw["root"] is not None else {"path": str(self.work / stage)}
        document = {"schema": I.SCHEMA_STAGE, "stage": stage, "collected_at": now, "root": root, "request_fingerprint": raw["request_fingerprint"],
                    "roles": raw["roles"], "unexpected_root_entries": raw["unexpected_root_entries"]}
        return rewrite(document, [(str(self.work), self.plan["working"]["root"])], {self.real_work: WORKING_DEVICE})

    def _device(self, side, now, free):
        section = self.plan["working"] if side == "working" else self.plan["backup"]
        inventory = {d["path"]: d for d in self.plan["host"]["inventory"]["inventory"]["disks"]}[section["root"]]
        return {"schema": S.DEVICE_SCHEMA, "host_id": self.plan["host"]["host_id"], "root": section["root"], "measured_at": now,
                "filesystem_device": WORKING_DEVICE if side == "working" else BACKUP_DEVICE, "filesystem_type": inventory["fstype"],
                "physical_storage_id": section["storage_id"], "physical_identity_evidence_sha256": hashlib.sha256(("e18-" + side).encode()).hexdigest(),
                "capacity_bytes": 500 * 2 ** 30 if side == "working" else 100 * 10 ** 9, "free_bytes": free}

    def backup_doc(self, stage, raw_backup, now):
        working, backup = self._device("working", now, self.free_working_bytes), self._device("backup", now, self.free_backup_bytes)
        document = {"schema": I.SCHEMA_BACKUP, "stage": stage, "collected_at": now, "devices": {}, "restores": raw_backup["restores"], "copies": raw_backup["copies"]}
        document = rewrite(document, [(str(self.backup), self.plan["backup"]["root"])], {self.real_backup: BACKUP_DEVICE})
        document["devices"] = {"working": working, "backup": backup, "observed_working": dict(working), "observed_backup": dict(backup)}
        return document

    def journal_location(self, identities):
        """A stand-in for ``ledger.check_independent_location``: the synthetic journal is a separate directory, never a proven independent volume."""
        return {"ok": True, "failures": [], "shares_device_with_backup": False, "physical_independence_proven": False,
                "authorizes_nothing": True, "execution_permitted": False}

    def k17d_report(self, plan):
        """Fabricated metadata-only comparison. It is NOT the production K17d cross-check and no production metadata exists to compare."""
        if self.k17d_override is not None:
            return json.loads(json.dumps(self.k17d_override))
        d1 = plan["scientific"]["d1_exposure"]
        return {"schema": I.K17D_SCHEMA, "verdict": "NO-GO", "metadata_status": "ACCEPTED_IDENTITY_METADATA_MATCH",
                "production_cross_verification_performed": True, "request_fingerprint": plan["source"]["known_request_fingerprint"],
                "source_head": plan["source"]["git_commit"], "counts": dict(I.K17D_COUNTS), "identity_sha256": plan["scientific"]["d8_k17d"]["identity_sha256"],
                "observation_reads": 0, "waveform_synthesis_calls": 0, "execution_authorized": False, "production_authorized": False,
                "benchmark_complete": False,
                "d1_obligations": {"existing_test_pristine": False, "exposed_test_ids": d1["exposed_test_ids"], "exposed_matched_ids": d1["exposed_matched_ids"],
                                   "exposure_excluded_groups": {"test": 498, "test-matched": 148}}}


class SyntheticShardProducer:
    """Fabricated bytes for one planned shard per call. Rows are explicitly synthetic; there is no waveform, array or model."""

    def __init__(self, clock=None, s_per_observation=4.4):
        self.clock, self.s_per_observation = clock, s_per_observation
        self.calls, self.requests = 0, []

    def __call__(self, request):
        self.calls += 1
        self.requests.append((request["stage"], request["role"], request["ordinal"]))
        if self.clock is not None:
            self.clock.advance(self.s_per_observation * request["observations"])
        tag = f"{request['stage']}/{request['role']}/{request['ordinal']}/{request['request_fingerprint']}".encode()
        payload = SYNTHETIC_PREFIX + hashlib.sha256(tag).hexdigest().encode() * 4
        rows = b"".join(json.dumps({"i": i, "synthetic": True, "stage": request["stage"], "role": request["role"], "groups": list(request["groups"])},
                                   sort_keys=True).encode() + b"\n" for i in range(request["observations"]))
        return {"payload": payload, "metadata": rows}


def expected_journal_kinds(entries):
    """Small helper for tests and docs: ledger kinds in order."""
    return [e["kind"] for e in entries]


assert L.STAGES == I.STAGES
