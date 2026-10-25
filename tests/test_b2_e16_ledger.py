"""E16 ledger, incident specification and stop conditions: synthetic observations injected by the test, no host is read."""
import ast
import copy
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("b2_e16_ledger", ROOT / "scripts/b2_e16_ledger.py")
L = importlib.util.module_from_spec(SPEC)
sys.modules["b2_e16_ledger"] = L
SPEC.loader.exec_module(L)
D = L.D

NOW = "2026-11-01T12:00:00+00:00"
CEILINGS = {"wall_hours": 36, "core_hours": 42, "max_failed_attempts_per_stage": 2, "max_interruptions_per_stage": 20,
            "max_rss_gib": 2, "min_free_disk_gib": 25, "backup_disk_gb": 9, "grace_s": 60, "host_ram_gib": 8}
AUTH = {"expires_at": "2026-11-20T00:00:00+00:00", "revoked": False, "revocation_id": "rev-1"}


def observation(**override):
    value = {"schema": L.SCHEMA_OBSERVATION, "collected_at": "2026-11-01T11:59:30+00:00", "elapsed_wall_s": 3600.0, "cpu_core_s": 4000.0,
             "peak_rss_gib": 0.6, "working_free_gib": 200.0, "backup_free_gb": 100.0, "failed_attempts": 0, "interruptions": 0,
             "total_attempts": 1, "observations_committed": 128, "observations_remaining": 21350 - 128,
             "admitted_shards_this_attempt": 4, "first_shard": {"s_per_observation": 4.4, "observations": 32}}
    value.update(override)
    return value


UNSET = object()


def evaluate(obs=UNSET, ceilings=UNSET, auth=UNSET, **kwargs):
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("stage", "known")
    return L.evaluate_stop_conditions(observation() if obs is UNSET else obs, CEILINGS if ceilings is UNSET else ceilings,
                                      AUTH if auth is UNSET else auth, **kwargs)


def reasons(**kwargs):
    return evaluate(**kwargs)["reasons"]


# ---- stop conditions --------------------------------------------------------------------------------------------

def test_healthy_state_has_no_stop_reason_and_still_grants_nothing():
    report = evaluate()
    assert report["decision"] == "NO_STOP_CONDITION_TRIGGERED" and report["reasons"] == []
    assert report["absence_of_a_stop_reason_is_not_permission"] is True
    assert report["authorizes_nothing"] is True and report["execution_permitted"] is False
    assert report["projections"]["rate_is_measured"] is True
    assert report["restart_allowance"] == {"failed_attempts_left": 2, "interruptions_left": 20, "total_attempts_left": 59}
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("field,value,reason", [
    ("elapsed_wall_s", 36 * 3600.0, "ceiling.wall_hours"),
    ("cpu_core_s", 42 * 3600.0, "ceiling.core_hours"),
    ("peak_rss_gib", 2.01, "ceiling.max_rss_gib"),
    ("failed_attempts", 3, "ceiling.failed_attempts"),
    ("interruptions", 21, "ceiling.interruptions"),
    ("total_attempts", 61, "ceiling.total_attempts"),
])
def test_each_ceiling_stops_at_its_boundary(field, value, reason):
    assert reason in reasons(obs=observation(**{field: value}))


@pytest.mark.parametrize("field,value", [("elapsed_wall_s", 36 * 3600 - 1.0), ("cpu_core_s", 42 * 3600 - 1.0), ("peak_rss_gib", 2.0),
                                          ("failed_attempts", 2), ("interruptions", 20), ("total_attempts", 60)])
def test_values_just_inside_a_ceiling_do_not_stop(field, value):
    obs = observation(**{field: value})
    if field == "elapsed_wall_s":
        obs["observations_remaining"] = 0
    if field == "cpu_core_s":
        obs["observations_remaining"] = 0
    assert not [r for r in reasons(obs=obs) if r.startswith("ceiling.")]


def test_restart_allowance_is_checked_only_when_restarting():
    for field, value in (("failed_attempts", 2), ("interruptions", 20), ("total_attempts", 60)):
        obs = observation(**{field: value})
        assert "restart.allowance_exhausted" not in reasons(obs=obs)
        assert "restart.allowance_exhausted" in reasons(obs=obs, restarting=True)
    assert "restart.allowance_exhausted" not in reasons(restarting=True)


def test_timing_gate_slow_missing_and_fast_cases():
    assert "timing.too_slow" in reasons(obs=observation(first_shard={"s_per_observation": 6.3, "observations": 32}))
    assert "timing.too_slow" not in reasons(obs=observation(first_shard={"s_per_observation": 6.25, "observations": 32}))
    assert "timing.gate_measurement_missing" in reasons(obs=observation(first_shard=None, admitted_shards_this_attempt=1))
    assert "timing.gate_measurement_missing" not in reasons(obs=observation(first_shard=None, admitted_shards_this_attempt=0))
    fast = evaluate(obs=observation(first_shard={"s_per_observation": 0.5, "observations": 32}))
    assert fast["reasons"] == [] and fast["projections"]["seconds_per_observation_used"] == 0.5


def test_projections_stop_before_the_ceiling_is_reached():
    late = observation(elapsed_wall_s=20 * 3600.0, cpu_core_s=22 * 3600.0, observations_remaining=12000, first_shard=None, admitted_shards_this_attempt=0)
    found = reasons(obs=late)
    assert "projection.wall_hours" in found and not [r for r in found if r.startswith("ceiling.")]
    assert evaluate(obs=late)["projections"]["rate_is_measured"] is False          # the upper band edge is used until measured
    tight = dict(CEILINGS, core_hours=5)
    assert "projection.core_hours" in reasons(ceilings=tight)
    assert "projection.working_disk" in reasons(obs=observation(working_free_gib=30.0))
    assert "projection.working_disk" not in reasons(obs=observation(working_free_gib=40.0))
    assert "projection.backup_space" in reasons(obs=observation(backup_free_gb=5.0))


def test_expiry_revocation_and_stale_or_future_observations():
    assert "authorization.expired" in reasons(auth=dict(AUTH, expires_at=NOW))
    assert "authorization.expired" in reasons(auth=dict(AUTH, expires_at="2026-11-01T11:00:00Z"))
    assert "authorization.revoked" in reasons(auth=dict(AUTH, revoked=True))
    assert "observation.stale_or_from_the_future" in reasons(obs=observation(collected_at="2026-11-01T11:50:00+00:00"))
    assert "observation.stale_or_from_the_future" in reasons(obs=observation(collected_at="2026-11-01T12:00:05+00:00"))
    assert "observation.stale_or_from_the_future" not in reasons(obs=observation(collected_at=NOW))


def test_several_failures_are_all_reported():
    found = reasons(obs=observation(peak_rss_gib=9.0, failed_attempts=5, backup_free_gb=1.0), auth=dict(AUTH, revoked=True))
    assert {"ceiling.max_rss_gib", "ceiling.failed_attempts", "projection.backup_space", "authorization.revoked"} <= set(found)


def malformed_observations():
    base = observation()
    yield "missing", {k: v for k, v in base.items() if k != "cpu_core_s"}
    yield "extra", dict(base, extra=1)
    yield "schema", dict(base, schema="other")
    for field in ("elapsed_wall_s", "cpu_core_s", "peak_rss_gib", "working_free_gib", "backup_free_gb"):
        for bad in (float("nan"), float("inf"), -1.0, True, "1", None, [1]):
            yield f"{field}={bad!r}", dict(base, **{field: bad})
    for field in ("failed_attempts", "interruptions", "total_attempts", "observations_committed", "observations_remaining", "admitted_shards_this_attempt"):
        for bad in (-1, 1.5, True, "1", None, 2 ** 41):
            yield f"{field}={bad!r}", dict(base, **{field: bad})
    yield "first_shard_extra", dict(base, first_shard={"s_per_observation": 4.0, "observations": 4, "x": 1})
    yield "first_shard_zero", dict(base, first_shard={"s_per_observation": 4.0, "observations": 0})
    yield "first_shard_nan", dict(base, first_shard={"s_per_observation": math.nan, "observations": 4})
    yield "collected_naive", dict(base, collected_at="2026-11-01T11:59:30")
    yield "collected_text", dict(base, collected_at="yesterday")
    yield "not_a_dict", [base]
    yield "none", None


@pytest.mark.parametrize("label,bad", list(malformed_observations()), ids=[x[0] for x in malformed_observations()])
def test_malformed_or_missing_resource_observations_always_stop(label, bad):
    report = evaluate(obs=bad)
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("ceilings", [None, {}, {k: v for k, v in CEILINGS.items() if k != "wall_hours"}, dict(CEILINGS, wall_hours=0),
                                       dict(CEILINGS, wall_hours=True), dict(CEILINGS, wall_hours=math.nan), dict(CEILINGS, max_failed_attempts_per_stage=1.5),
                                       dict(CEILINGS, max_rss_gib=-1), dict(CEILINGS, wall_hours=10 ** 400), dict(CEILINGS, core_hours=1e300)])
def test_malformed_ceilings_stop(ceilings):
    report = L.evaluate_stop_conditions(observation(), ceilings, AUTH, now=NOW, stage="known")
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")


@pytest.mark.parametrize("auth", [None, {}, dict(AUTH, revoked="no"), dict(AUTH, revoked=0), dict(AUTH, expires_at="2026"), dict(AUTH, extra=1),
                                   {k: v for k, v in AUTH.items() if k != "revocation_id"}])
def test_malformed_authorization_state_stops(auth):
    report = L.evaluate_stop_conditions(observation(), CEILINGS, auth, now=NOW, stage="known")
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")


@pytest.mark.parametrize("kwargs", [{"now": "soon"}, {"now": None}, {"now": {"x": 1}}, {"stage": "train"}, {"stage": None},
                                     {"max_observation_age_s": 0}, {"max_observation_age_s": True}, {"max_observation_age_s": 10 ** 6},
                                     {"timing": {}}, {"timing": {"band_s_per_observation": [5, 3], "tolerance": 0.25, "gate_shards": 1}},
                                     {"timing": {"band_s_per_observation": [3.8, 5.0], "tolerance": -1, "gate_shards": 1}},
                                     {"timing": {"band_s_per_observation": [3.8, 5.0], "tolerance": 0.25, "gate_shards": 0}},
                                     {"timing": {"band_s_per_observation": [3.8, math.nan], "tolerance": 0.25, "gate_shards": 1}}])
def test_malformed_arguments_stop_without_raising_or_reflecting_input(kwargs):
    report = evaluate(**kwargs)
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")
    json.dumps(report, allow_nan=False)
    assert report["evaluated_at"] in (NOW, None) and report["stage"] in L.STAGES + (None,)


def test_evaluation_does_not_mutate_its_inputs():
    obs, ceil, auth = observation(), copy.deepcopy(CEILINGS), copy.deepcopy(AUTH)
    before = copy.deepcopy((obs, ceil, auth))
    L.evaluate_stop_conditions(obs, ceil, auth, now=NOW, stage="test")
    assert (obs, ceil, auth) == before


# ---- incidents --------------------------------------------------------------------------------------------------

def test_every_incident_has_a_mandatory_action_and_unknown_incidents_stop():
    actions = {L.required_action(kind) for kind in L.INCIDENTS}
    assert actions <= {"stop", "stop_and_quarantine", "fail_closed_and_rederive_with_independent_review", "resume_only_under_identical_request"}
    for kind in ("shard_corruption", "orphan_files", "partial_commit", "backup_mismatch"):
        assert L.required_action(kind) == "stop_and_quarantine"
    assert L.required_action("interruption") == "resume_only_under_identical_request"
    assert L.required_action("k17d_mismatch").startswith("fail_closed")
    with pytest.raises(L.LedgerRefused):
        L.required_action("something_new")
    with pytest.raises(L.LedgerRefused):
        L.incident_data("something_new", {})


def test_incident_fields_are_exact_and_the_action_cannot_be_supplied():
    fields = {"role": "train", "ordinal": 3, "expected_sha256": "a" * 64, "observed_sha256": "b" * 64}
    data = L.incident_data("shard_corruption", fields)
    assert data["action"] == "stop_and_quarantine" and data["details"] == fields
    for bad in (dict(fields, action="continue"), {k: v for k, v in fields.items() if k != "role"}, {}, [], None):
        with pytest.raises(L.LedgerRefused):
            L.incident_data("shard_corruption", bad)
    with pytest.raises(L.LedgerRefused):
        L.incident_data("orphan_files", {"role": "train", "files": ["x" * 70000]})


# ---- hash chain and ledger file ---------------------------------------------------------------------------------

def three_entries(tmp_path):
    ledger = L.Ledger(tmp_path)
    first = ledger.append("run_opened", None, {"plan": "p"}, "2026-11-01T10:00:00+00:00")
    second = ledger.append("stage_bound", "test", {"fingerprint": "f"}, "2026-11-01T10:01:00+00:00")
    third = ledger.append("incident", "known", L.incident_data("interruption", {"attempt": 1, "signal": "SIGTERM"}), "2026-11-01T10:02:00+00:00")
    return ledger, [first, second, third]


def test_append_and_verify_roundtrip(tmp_path):
    ledger, entries = three_entries(tmp_path)
    assert [e["seq"] for e in entries] == [0, 1, 2] and entries[0]["prev_sha256"] == L.GENESIS
    assert entries[1]["prev_sha256"] == entries[0]["entry_sha256"]
    report = L.verify_chain(ledger.read())
    assert report["ok"] and report["count"] == 3 and report["head"] == {"seq": 2, "entry_sha256": entries[2]["entry_sha256"]}
    assert report["append_only_enforced"] is False and report["authorizes_nothing"] is True
    assert (tmp_path / L.LEDGER_NAME).stat().st_mode & 0o777 == 0o600
    anchored = L.verify_chain(ledger.read(), expected_head={"seq": 1, "entry_sha256": entries[1]["entry_sha256"]})
    assert anchored["ok"]


def lines_of(tmp_path):
    return (tmp_path / L.LEDGER_NAME).read_bytes().split(b"\n")[:-1]


def rewrite(tmp_path, lines):
    (tmp_path / L.LEDGER_NAME).write_bytes(b"".join(line + b"\n" for line in lines))


def test_every_edit_reorder_or_gap_is_detected(tmp_path):
    ledger, entries = three_entries(tmp_path)
    good = lines_of(tmp_path)
    assert not L.verify_chain(b"\n".join([good[0], good[2], good[1]]) + b"\n")["ok"]
    assert not L.verify_chain(b"\n".join([good[0], good[2]]) + b"\n")["ok"]
    assert not L.verify_chain(b"\n".join([good[1], good[2]]) + b"\n")["ok"]
    assert not L.verify_chain(b"\n".join(good[:2] + [good[1]]) + b"\n")["ok"]
    edited = json.loads(good[1])
    edited["data"]["fingerprint"] = "tampered"
    assert not L.verify_chain(b"\n".join([good[0], json.dumps(edited).encode(), good[2]]) + b"\n")["ok"]
    edited["entry_sha256"] = L._digest({k: v for k, v in edited.items() if k != "entry_sha256"})
    assert not L.verify_chain(b"\n".join([good[0], json.dumps(edited).encode(), good[2]]) + b"\n")["ok"]      # chain breaks at entry 2
    assert not L.verify_chain(good[0] + b"\n\n" + good[1] + b"\n")["ok"]


@pytest.mark.parametrize("mutation", [
    lambda e: e.update(kind="unknown"), lambda e: e.update(stage="train"), lambda e: e.update(extra=1), lambda e: e.pop("data"),
    lambda e: e.update(data=[]), lambda e: e.update(at="soon"), lambda e: e.update(seq=True), lambda e: e.update(schema="x"),
])
def test_malformed_entries_are_refused_even_with_recomputed_checksums(mutation):
    entry = L.make_entry(0, L.GENESIS, NOW, "run_opened", None, {})
    mutation(entry)
    if "entry_sha256" in entry and isinstance(entry.get("data"), dict | list):
        entry["entry_sha256"] = L._digest({k: v for k, v in entry.items() if k != "entry_sha256"})
    assert not L.verify_chain(json.dumps(entry).encode() + b"\n")["ok"]


def test_truncation_needs_an_independent_anchor_and_is_detected_with_one(tmp_path):
    ledger, entries = three_entries(tmp_path)
    anchor = {"seq": 2, "entry_sha256": entries[2]["entry_sha256"]}
    good = lines_of(tmp_path)
    rewrite(tmp_path, good[:2])
    assert L.verify_chain(ledger.read())["ok"] is True                         # honest limit: a prefix is a valid chain
    assert not L.verify_chain(ledger.read(), expected_head=anchor)["ok"]
    rewrite(tmp_path, good[:1] + [good[1].replace(b"fingerprint", b"fingerprinT")])
    assert not L.verify_chain(ledger.read())["ok"]
    forged = L.make_entry(2, entries[1]["entry_sha256"], "2026-11-01T10:02:00+00:00", "stop", None, {"forged": True})
    rewrite(tmp_path, good[:2] + [canonical_line(forged)])
    assert L.verify_chain(ledger.read())["ok"]
    assert not L.verify_chain(ledger.read(), expected_head=anchor)["ok"]       # rewritten history differs from the anchor
    for bad in ({"seq": -1, "entry_sha256": "x"}, {"seq": 0}, [], {"seq": True, "entry_sha256": "x"}):
        assert not L.verify_chain(ledger.read(), expected_head=bad)["ok"]


def canonical_line(entry):
    return L.canonical(entry).encode()


def test_torn_write_nonstrict_json_and_oversize_are_refused(tmp_path):
    ledger, _ = three_entries(tmp_path)
    raw = ledger.read()
    assert not L.verify_chain(raw[:-5])["ok"]
    assert not L.verify_chain(raw[:-1])["ok"]
    assert not L.verify_chain(b'{"a":NaN}\n')["ok"]
    assert not L.verify_chain(b'{"a":1,"a":2}\n')["ok"]
    assert not L.verify_chain(b"x" * (L.MAX_ENTRY_BYTES + 2) + b"\n")["ok"]
    assert not L.verify_chain("text")["ok"]
    assert not L.verify_chain(b"x" * (L.MAX_LEDGER_BYTES + 1))["ok"]
    assert L.verify_chain(b"")["ok"] is True and L.verify_chain(b"")["head"] is None


def test_timestamps_may_not_run_backwards(tmp_path):
    ledger = L.Ledger(tmp_path)
    ledger.append("run_opened", None, {}, "2026-11-01T10:00:00+00:00")
    with pytest.raises(L.LedgerRefused):
        ledger.append("stop", "known", {}, "2026-11-01T09:59:59+00:00")
    assert len(lines_of(tmp_path)) == 1
    first = L.make_entry(0, L.GENESIS, "2026-11-01T10:00:00+00:00", "run_opened", None, {})
    second = L.make_entry(1, first["entry_sha256"], "2026-11-01T09:00:00+00:00", "stop", None, {})
    assert not L.verify_chain(canonical_line(first) + b"\n" + canonical_line(second) + b"\n")["ok"]


def test_append_refuses_a_corrupt_ledger_and_never_repairs_it(tmp_path):
    ledger, _ = three_entries(tmp_path)
    good = lines_of(tmp_path)
    rewrite(tmp_path, [good[0], good[2]])
    before = (tmp_path / L.LEDGER_NAME).read_bytes()
    with pytest.raises(L.LedgerRefused):
        ledger.append("stop", None, {}, "2026-11-01T11:00:00+00:00")
    assert (tmp_path / L.LEDGER_NAME).read_bytes() == before


def test_append_validates_kind_stage_and_size(tmp_path):
    ledger = L.Ledger(tmp_path)
    for kind, stage, data in (("bogus", None, {}), ("stop", "train", {}), ("stop", None, []), ("stop", None, {"x": "y" * 70000})):
        with pytest.raises(L.LedgerRefused):
            ledger.append(kind, stage, data, NOW)
    with pytest.raises(L.LedgerRefused):
        ledger.append("stop", None, {}, "not a time")
    assert not (tmp_path / L.LEDGER_NAME).exists() or (tmp_path / L.LEDGER_NAME).read_bytes() == b""


def test_append_syncs_file_and_directory_and_serializes_writers(tmp_path, monkeypatch):
    events = []
    real = os.fsync
    monkeypatch.setattr(L.os, "fsync", lambda fd: (events.append(os.fstat(fd).st_mode & 0o170000), real(fd))[1])
    L.Ledger(tmp_path).append("run_opened", None, {}, NOW)
    assert events == [0o100000, 0o040000]
    monkeypatch.undo()
    holder = os.open(tmp_path / L.LEDGER_NAME, os.O_RDWR)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
        with pytest.raises(OSError):
            L.Ledger(tmp_path).append("stop", None, {}, "2026-11-01T12:30:00+00:00")
    finally:
        os.close(holder)


def test_reading_does_not_create_a_ledger_and_aliases_are_refused(tmp_path):
    with pytest.raises(OSError):
        L.Ledger(tmp_path).read()
    assert not (tmp_path / L.LEDGER_NAME).exists()
    target = tmp_path / "elsewhere"
    target.write_bytes(b"")
    (tmp_path / L.LEDGER_NAME).symlink_to(target)
    with pytest.raises(OSError):
        L.Ledger(tmp_path).append("run_opened", None, {}, NOW)
    (tmp_path / L.LEDGER_NAME).unlink()
    (tmp_path / L.LEDGER_NAME).write_bytes(b"")
    os.link(tmp_path / L.LEDGER_NAME, tmp_path / "second-name")
    with pytest.raises(L.LedgerRefused):
        L.Ledger(tmp_path).append("run_opened", None, {}, NOW)


def test_independent_location_rules(tmp_path, monkeypatch):
    working, backup, ledger = tmp_path / "w", tmp_path / "b", tmp_path / "j"
    for path in (working, backup, ledger):
        path.mkdir()
    report = L.check_independent_location(ledger, working, backup)
    assert report["ok"] is False and any("shares a filesystem" in f for f in report["failures"])   # one tmp filesystem
    assert report["physical_independence_proven"] is False
    nested = working / "journal"
    nested.mkdir()
    assert any("nested" in f for f in L.check_independent_location(nested, working, backup)["failures"])
    assert any("nested" in f for f in L.check_independent_location(ledger, working, ledger)["failures"])
    identities = {"j": 3, "w": 1, "b": 2}
    real = D.directory_identity
    monkeypatch.setattr(D, "directory_identity", lambda path: dict(real(path), st_dev=identities[Path(path).name], path="/srv/e16/" + Path(path).name))
    monkeypatch.setattr(L, "_mount_type", lambda path: "ext4")
    ok = L.check_independent_location(ledger, working, backup)
    assert ok["ok"] is True and ok["shares_device_with_backup"] is False
    identities["j"] = 2
    assert L.check_independent_location(ledger, working, backup)["shares_device_with_backup"] is True
    monkeypatch.setattr(D, "directory_identity", lambda path: dict(real(path), st_dev=identities[Path(path).name], path="/dev/shm/" + Path(path).name))
    volatile = L.check_independent_location(ledger, working, backup)
    assert volatile["ok"] is False and any("volatile" in failure for failure in volatile["failures"])
    monkeypatch.undo()
    with pytest.raises(OSError):
        L.check_independent_location(tmp_path / "missing", working, backup)


def test_module_reads_no_clock_environment_or_process_apis():
    tree = ast.parse((ROOT / "scripts/b2_e16_ledger.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"subprocess", "multiprocessing", "socket", "shutil", "ctypes", "time", "platform", "psutil", "resource"}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"now", "utcnow", "today", "time", "environ", "getenv", "system", "popen", "Popen", "run", "execv", "fork",
                              "unlink", "remove", "rename", "rmtree", "truncate", "ftruncate"}


# ---- review findings E16-02, E16-03, E16-07 -----------------------------------------------------------------------------

def forged_incident_line(index, previous, data):
    """An entry written without incident_data(): chained and checksummed correctly, content not following the specification."""
    entry = {"schema": L.SCHEMA_ENTRY, "seq": index, "prev_sha256": previous, "at": f"2026-11-01T10:0{index}:00+00:00", "kind": "incident",
             "stage": "known", "data": data}
    entry["entry_sha256"] = L._digest(entry)
    return entry


@pytest.mark.parametrize("data", [
    {"incident": "shard_corruption", "action": "resume_only_under_identical_request",
     "details": {"role": "train", "ordinal": 1, "expected_sha256": "a" * 64, "observed_sha256": "b" * 64}},
    {"incident": "shard_corruption", "action": "stop", "details": {"role": "train", "ordinal": 1, "expected_sha256": "a", "observed_sha256": "b"}},
    {"incident": "made_up", "action": "stop", "details": {}},
    {"incident": "shard_corruption", "action": "stop_and_quarantine", "details": {"role": "train"}},
    {"incident": "shard_corruption", "action": "stop_and_quarantine", "details": {"role": "train", "ordinal": 1, "expected_sha256": "a", "observed_sha256": "b", "x": 1}},
    {"incident": "shard_corruption", "action": "stop_and_quarantine", "details": []},
    {"action": "stop", "details": {}},
    {"note": "free text"},
])
def test_an_incident_entry_must_follow_the_specification_wherever_it_was_written(tmp_path, data):
    first = L.make_entry(0, L.GENESIS, "2026-11-01T10:00:00+00:00", "run_opened", None, {})
    forged = forged_incident_line(1, first["entry_sha256"], data)
    raw = L.canonical(first).encode() + b"\n" + L.canonical(forged).encode() + b"\n"
    report = L.verify_chain(raw)
    assert report["ok"] is False and "incident" in " ".join(report["failures"])
    with pytest.raises(L.LedgerRefused):
        L.make_entry(1, first["entry_sha256"], "2026-11-01T10:01:00+00:00", "incident", "known", data)
    ledger = L.Ledger(tmp_path)
    ledger.append("run_opened", None, {}, "2026-11-01T10:00:00+00:00")
    with pytest.raises(L.LedgerRefused):
        ledger.append("incident", "known", data, "2026-11-01T10:01:00+00:00")
    (tmp_path / L.LEDGER_NAME).write_bytes(raw)                       # an already-forged ledger is also refused for further appends
    with pytest.raises(L.LedgerRefused):
        ledger.append("stop", None, {}, "2026-11-01T11:00:00+00:00")


def test_only_the_interruption_incident_is_resumable():
    assert [kind for kind, (action, _) in L.INCIDENTS.items() if action == "resume_only_under_identical_request"] == ["interruption"]


@pytest.mark.parametrize("field,value", [
    ("elapsed_wall_s", 10 ** 400), ("cpu_core_s", -10 ** 400), ("peak_rss_gib", 1e308), ("working_free_gib", 1e16), ("backup_free_gb", 10 ** 30),
    ("observations_remaining", 2 ** 41), ("observations_committed", 10 ** 400),
])
def test_huge_or_overflowing_readings_are_malformed_stop_reasons_and_never_raise(field, value):
    report = evaluate(obs=observation(**{field: value}))
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")
    json.dumps(report, allow_nan=False)


def test_extreme_but_individually_valid_rates_cannot_make_projections_infinite():
    for rate in (1e300, 1e308, 1e16):
        report = evaluate(obs=observation(first_shard={"s_per_observation": rate, "observations": 32}))
        assert report["decision"] == "STOP"
        json.dumps(report, allow_nan=False)
    huge = evaluate(obs=observation(first_shard={"s_per_observation": 1e15, "observations": 32}, observations_remaining=21350 - 128))
    assert huge["decision"] == "STOP" and json.dumps(huge, allow_nan=False)


def test_a_zero_measured_rate_or_an_overfull_plan_is_malformed():
    assert evaluate(obs=observation(first_shard={"s_per_observation": 0.0, "observations": 32}))["reasons"][0].startswith("input.malformed")
    assert evaluate(obs=observation(observations_committed=21000, observations_remaining=1000))["reasons"][0].startswith("input.malformed")
    assert evaluate(obs=observation(observations_committed=0, observations_remaining=21350))["reasons"] == []


def test_parser_limits_are_refusals_not_stray_exceptions(tmp_path):
    big = b'{"seq": ' + b"9" * 5000 + b"}\n"
    report = L.verify_chain(big)
    assert report["ok"] is False
    with pytest.raises(L.LedgerRefused):
        L.strict_json(b"9" * 5000)
    assert L.verify_chain(b'{"a": [' * 3000 + b"\n")["ok"] is False


# ---- re-review findings N-02, N-03, N-05, N-07 ------------------------------------------------------------------------------

@pytest.mark.parametrize("kind,refused_text", [("tmpfs", "durable"), ("overlay", "durable"), ("", "unknown"), ("vfat", "durable")])
def test_the_journal_volume_must_be_a_reviewed_durable_filesystem(tmp_path, monkeypatch, kind, refused_text):
    for name in ("w", "b", "j"):
        (tmp_path / name).mkdir()
    real = D.directory_identity
    ids = {"j": 3, "w": 1, "b": 2}
    monkeypatch.setattr(D, "directory_identity", lambda path: dict(real(path), st_dev=ids[Path(path).name], path="/srv/e16/" + Path(path).name))
    monkeypatch.setattr(L, "_mount_type", lambda path: kind)
    report = L.check_independent_location(tmp_path / "j", tmp_path / "w", tmp_path / "b")
    assert report["ok"] is False and any(refused_text in failure for failure in report["failures"])
    monkeypatch.setattr(L, "_mount_type", lambda path: "xfs")
    assert L.check_independent_location(tmp_path / "j", tmp_path / "w", tmp_path / "b")["ok"] is True


def test_the_real_mount_lookup_returns_a_type_or_empty():
    assert isinstance(L._mount_type(Path("/")), str)
    assert L._mount_type(Path("/nonexistent/e16/path")) in ("",) or isinstance(L._mount_type(Path("/nonexistent/e16/path")), str)


@pytest.mark.parametrize("value", ["9999-12-31T23:59:59-01:00", "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59.999999-23:59", "0001-01-01T00:00:00+23:59"])
def test_timestamps_at_the_datetime_limits_are_refusals_not_overflows(value):
    with pytest.raises(L.LedgerRefused):
        L.instant(value)
    with pytest.raises(L.LedgerRefused):
        L.make_entry(0, L.GENESIS, value, "run_opened", None, {})
    entry = {"schema": L.SCHEMA_ENTRY, "seq": 0, "prev_sha256": L.GENESIS, "at": value, "kind": "run_opened", "stage": None, "data": {}}
    entry["entry_sha256"] = L._digest(entry)
    assert L.verify_chain(L.canonical(entry).encode() + b"\n")["ok"] is False
    for kwargs in ({"now": value}, {"auth": dict(AUTH, expires_at=value)}, {"obs": observation(collected_at=value)}):
        report = evaluate(**kwargs)
        assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")


@pytest.mark.parametrize("timing", [
    {"band_s_per_observation": [10 ** 400, 10 ** 401], "tolerance": 0.25, "gate_shards": 1},
    {"band_s_per_observation": [3.8, 5.0], "tolerance": 10 ** 400, "gate_shards": 1},
    {"band_s_per_observation": [3.8, 5.0], "tolerance": 0.25, "gate_shards": 10 ** 400},
])
def test_overflowing_timing_policy_is_malformed(timing):
    report = evaluate(timing=timing)
    assert report["decision"] == "STOP" and report["reasons"][0].startswith("input.malformed")


@pytest.mark.parametrize("name", [[], {}, ["x"], 5, None, True, "not_an_incident"])
def test_an_unhashable_or_foreign_incident_name_is_a_refusal(name):
    data = {"incident": name, "action": "stop", "details": {}}
    with pytest.raises(L.LedgerRefused):
        L.check_incident_entry(data)
    with pytest.raises(L.LedgerRefused):
        L.make_entry(0, L.GENESIS, "2026-11-01T10:00:00+00:00", "incident", "known", data)
    entry = {"schema": L.SCHEMA_ENTRY, "seq": 0, "prev_sha256": L.GENESIS, "at": "2026-11-01T10:00:00+00:00", "kind": "incident", "stage": "known", "data": data}
    entry["entry_sha256"] = L._digest(entry)
    assert L.verify_chain(L.canonical(entry).encode() + b"\n")["ok"] is False


@pytest.mark.parametrize("kind", [k for k in L.KINDS if k != "incident"])
def test_incident_fields_are_reserved_for_incident_entries(kind):
    for data in ({"incident": "shard_corruption", "action": "resume_only_under_identical_request"}, {"action": "stop"}, {"incident": "x"}):
        with pytest.raises(L.LedgerRefused):
            L.make_entry(0, L.GENESIS, "2026-11-01T10:00:00+00:00", kind, None, data)
        entry = {"schema": L.SCHEMA_ENTRY, "seq": 0, "prev_sha256": L.GENESIS, "at": "2026-11-01T10:00:00+00:00", "kind": kind, "stage": None, "data": data}
        entry["entry_sha256"] = L._digest(entry)
        assert L.verify_chain(L.canonical(entry).encode() + b"\n")["ok"] is False
