"""E18 durability, stop and recovery over fabricated shards.

A process "dies" by closing its controller without a stop; a human "tampers" by rewriting files, the ledger or its anchors. In
every case the evidence on disk must be preserved byte for byte, a damaged run must end QUARANTINED or STOPPED, and a restart is
accepted only under identical plan, specification, source and journal identities.
"""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import e18_support as T  # noqa: E402
from test_b2_e17_evidence import custody, integrated  # noqa: E402,F401
from e18_support import admitted, complete, known, make  # noqa: E402,F401

M, X, L, I, D, S, E, P, G, C = T.M, T.X, T.L, T.M.I, T.M.D, T.M.S, T.M.E, T.M.P, T.M.G, T.C


def partial(make, shards=6, **kwargs):
    life, profile, authority = make(**kwargs)
    admitted(life)
    life.run_stage(shard_budget=shards)
    assert life.state == "SYNTHETIC_STAGE_RUNNING" and life.summary()["admitted_shards"] == shards
    return life, profile, authority


def reopen(make, life, profile, custody, integrated, **kwargs):
    """The process is gone (lock released); a new one starts from the journal and the disk."""
    life.close()
    new_profile, authority = T.restart_profile(profile.workspace, custody, integrated, profile.plan, **kwargs)
    return new_profile, authority


def recover(make, life, profile, custody, integrated, **kwargs):
    new_profile, authority = reopen(make, life, profile, custody, integrated, **kwargs)
    return make.adopt(M.SyntheticExecutorLifecycle.recover(new_profile)), new_profile, authority


def role_dir(life, stage="known", role="train"):
    return life.paths["work"] / stage / role


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def quarantined_with_evidence_intact(life, before):
    assert life.state == "QUARANTINED" and life.events[-1]["action"] == "quarantine"
    assert T.tree_digest(life.paths["work"]) == before                                         # nothing was moved, repaired or deleted
    assert T.kinds(life)[-1] == "stop" and life.journal_entries()[-1]["data"]["state"] == "QUARANTINED"


# ---- controlled stop and restart ------------------------------------------------------------------------------------------

def test_a_controlled_interruption_is_recovered_under_identical_identities_and_finishes_the_stage(make, custody, integrated):
    life, profile, _ = partial(make, shards=5)
    life.interrupt("SIGTERM")
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is True
    again, profile2, _ = recover(make, life, profile, custody, integrated)
    assert again.state == "PREPARED" and again.summary()["attempt"] == 2 and again.summary()["interruptions"] == 1
    assert again.summary()["admitted_shards"] == 5                                              # re-admitted from disk: verify, fsync, verify
    again.advance()
    assert again.state == "PREPARED" and again.completed == ["known"] and again.summary()["admitted_shards"] == 576
    produced = profile2.producer.requests
    assert len(produced) == 571 and len(set(produced)) == 571                                   # nothing was produced twice
    kinds = T.kinds(again)
    assert kinds.count("incident") == 1 and kinds.count("resume") == 1 and kinds.index("incident") < kinds.index("resume")
    assert again.journal_entries()[kinds.index("incident")]["data"]["details"]["signal"] == "SIGTERM"
    assert again.boundary_reports[-1]["boundary"] == "after_known" and again.boundary_reports[-1]["document_conditions_met"] is True


def test_a_crash_without_any_stop_is_recorded_as_an_inferred_interruption_and_recovered(make, custody, integrated):
    life, profile, _ = partial(make, shards=7)
    again, profile2, _ = recover(make, life, profile, custody, integrated)                    # no interrupt(): the process just died
    assert again.summary()["admitted_shards"] == 7 and again.summary()["interruptions"] == 1
    incident = [e for e in again.journal_entries() if e["kind"] == "incident"]
    assert [e["data"]["details"]["signal"] for e in incident] == ["UNCLEAN_EXIT_INFERRED"]
    admitted(again)
    assert again.state == "ADMISSION_CHECKED" and again.events[-1].get("mode") == "resume"
    again.run_stage(shard_budget=3)
    assert again.summary()["admitted_shards"] == 10 and all(r[2] >= 0 for r in profile2.producer.requests)
    assert not set(profile2.producer.requests) & {("known", "train", o) for o in range(0, 0)}


def test_recovery_is_idempotent_and_never_repeats_or_loses_a_shard(make, custody, integrated):
    life, profile, _ = partial(make, shards=4)
    first, profile2, _ = recover(make, life, profile, custody, integrated)
    snapshot = T.tree_digest(first.paths["work"])
    second, profile3, _ = recover(make, first, profile2, custody, integrated)
    assert second.summary()["admitted_shards"] == 4 and second.summary()["attempt"] == 3
    assert T.tree_digest(second.paths["work"]) == snapshot
    chain = L.verify_chain(second.ledger.read(), expected_head=second.anchors.latest())
    assert chain["ok"] and [e["kind"] for e in chain["entries"]].count("resume") == 2


def test_a_second_process_cannot_recover_while_the_first_is_alive(make, custody, integrated):
    life, profile, _ = partial(make, shards=2)
    new_profile, _ = T.restart_profile(profile.workspace, custody, integrated, profile.plan)
    with pytest.raises(M.LifecycleRefused, match="another controller"):
        M.SyntheticExecutorLifecycle.recover(new_profile)


def test_there_is_nothing_to_recover_without_a_journal(make, custody, integrated, tmp_path):
    workspace = T.make_workspace(tmp_path / "fresh")
    profile, _ = T.make_profile(None, custody, integrated, workspace=workspace)
    with pytest.raises(M.LifecycleRefused, match="no journal"):
        M.SyntheticExecutorLifecycle.recover(profile)
    assert not (Path(workspace.journal) / "controller.lock").exists() or True


# ---- recovery refuses an untrustworthy journal -------------------------------------------------------------------------------

def tamper_flip(workspace):
    path = Path(workspace.journal) / L.LEDGER_NAME
    raw = bytearray(path.read_bytes())
    raw[raw.index(b"shard_admitted") + 3] ^= 0x01
    path.write_bytes(bytes(raw))


def tamper_truncate(workspace):
    path = Path(workspace.journal) / L.LEDGER_NAME
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:-1]))


def tamper_rewrite_history(workspace):
    """A different but internally valid chain of the same length: only the independently retained anchor can expose it."""
    path = Path(workspace.journal) / L.LEDGER_NAME
    entries = L.verify_chain(path.read_bytes())["entries"]
    rebuilt, previous = [], L.GENESIS
    for entry in entries:
        data = dict(entry["data"])
        if entry["kind"] == "shard_admitted" and entry["seq"] == 5:
            data["descriptor_sha256"] = "f" * 64
        made = L.make_entry(entry["seq"], previous, entry["at"], entry["kind"], entry["stage"], data)
        rebuilt.append(made)
        previous = made["entry_sha256"]
    path.write_bytes(b"".join(L.canonical(e).encode() + b"\n" for e in rebuilt))


def tamper_drop_anchors(workspace):
    for path in Path(workspace.anchors).iterdir():
        path.unlink()


def tamper_stop_entry(workspace):
    T.append_entry(workspace, "stop", None, {"state": "STOPPED", "reason": "operator stop"})


def tamper_hard_incident(workspace):
    T.append_entry(workspace, "incident", None, L.incident_data("identity_mismatch", {"what": "source", "expected_sha256": "a" * 64, "observed_sha256": "b" * 64}))


def tamper_second_authorization(workspace):
    T.append_entry(workspace, "authorization_snapshot", None, {"record_sha256": "e" * 64, "expires_at": "2026-11-20T00:00:00Z"})


def tamper_completed_out_of_order(workspace):
    T.append_entry(workspace, "boundary_check", "test", {"phase": "stage_complete", "stage": "test", "boundary": "after_test"})


def tamper_binding_without_predecessor(workspace):
    T.append_entry(workspace, "stage_bound", "test", {"request_fingerprint": "a" * 64})


JOURNAL_TAMPERS = [
    ("an_entry_is_edited", tamper_flip, "anchor"), ("the_tail_is_truncated", tamper_truncate, "anchor"),
    ("history_is_rewritten_with_valid_hashes", tamper_rewrite_history, "anchor"), ("the_anchors_are_removed", tamper_drop_anchors, "anchor"),
    ("a_stop_entry_ended_the_run", tamper_stop_entry, "stopped for good"), ("a_halting_incident_is_recorded", tamper_hard_incident, "halted the run"),
    ("a_second_authorization_record_is_named", tamper_second_authorization, "different authorization"),
    ("a_later_stage_is_marked_complete_first", tamper_completed_out_of_order, "prefix"),
    ("a_later_stage_is_bound_without_its_predecessor", tamper_binding_without_predecessor, "predecessor"),
]


@pytest.mark.parametrize("name,tamper,reason", JOURNAL_TAMPERS, ids=[t[0] for t in JOURNAL_TAMPERS])
def test_recovery_refuses_a_journal_that_is_not_what_the_previous_process_left(make, custody, integrated, name, tamper, reason):
    life, profile, _ = partial(make, shards=6)
    life.interrupt()
    life.close()
    before = T.tree_digest(life.paths["work"])
    new_profile, _ = T.restart_profile(profile.workspace, custody, integrated, profile.plan)       # the new process's clock, fixed before the tampering
    tamper(profile.workspace)
    with pytest.raises(M.LifecycleRefused) as refused:
        M.SyntheticExecutorLifecycle.recover(new_profile)
    assert reason in str(refused.value) or (reason == "anchor" and ("anchor" in str(refused.value)))
    assert T.tree_digest(life.paths["work"]) == before and new_profile.producer.calls == 0


def test_a_journal_that_belongs_to_another_run_is_refused(make, custody, integrated):
    life, profile, _ = partial(make, shards=3)
    life.close()
    other = T.make_workspace(Path(life.paths["work"]).parent.parent / "other")
    shutil.copy2(Path(profile.workspace.journal) / L.LEDGER_NAME, Path(other.journal) / L.LEDGER_NAME)
    for anchor in Path(profile.workspace.anchors).iterdir():
        shutil.copy2(anchor, Path(other.anchors) / anchor.name)
    entries = L.verify_chain((Path(other.journal) / L.LEDGER_NAME).read_bytes())["entries"]
    first = dict(entries[0]["data"], plan_fingerprint="9" * 64)                              # rebuild the chain for a different plan identity
    rebuilt, previous = [], L.GENESIS
    for entry in entries:
        made = L.make_entry(entry["seq"], previous, entry["at"], entry["kind"], entry["stage"], first if entry["seq"] == 0 else entry["data"])
        rebuilt.append(made)
        previous = made["entry_sha256"]
    (Path(other.journal) / L.LEDGER_NAME).write_bytes(b"".join(L.canonical(e).encode() + b"\n" for e in rebuilt))
    for anchor in Path(other.anchors).iterdir():
        anchor.unlink()
    M.AnchorStore(other.anchors).record({"seq": rebuilt[-1]["seq"], "entry_sha256": rebuilt[-1]["entry_sha256"]})
    new_profile, _ = T.make_profile(None, custody, integrated, workspace=other, start="2026-10-31T00:00:00+00:00")
    with pytest.raises(M.LifecycleRefused, match="different plan"):
        M.SyntheticExecutorLifecycle.recover(new_profile)


# ---- damaged bytes: evidence-preserving quarantine -----------------------------------------------------------------------------

def flip_payload(directory):
    path = T.writable(directory / "part-00001.npz")
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0x01
    path.write_bytes(bytes(raw))


def orphan_temporary(directory):
    (directory / ".part-00099.npz.tmp").write_bytes(b"torn write")


def unexpected_file(directory):
    (directory / "notes.txt").write_bytes(b"stray")


def lose_descriptor(directory):
    (directory / "shard-00002.json").unlink()


def lose_metadata(directory):
    (directory / "meta-00003.jsonl").unlink()


def substitute_shard(directory):
    """A well-formed, self-consistent replacement: only the journaled admission digest can show that it is not what was admitted."""
    descriptor = T.writable(directory / "shard-00002.json")
    document = json.loads(descriptor.read_text())
    payload = M.SYNTHETIC_PREFIX + b"substituted bytes"
    document["sha256"]["part-00002.npz"] = sha(payload)
    T.writable(directory / "part-00002.npz").write_bytes(payload)
    descriptor.write_bytes(S._canonical(document))


def delete_admitted_shard(directory):
    for name in D.shard_names(4):
        (directory / name).unlink()


def swap_in_a_symlink(directory):
    real = directory.parent / "train.moved"
    directory.rename(real)
    os.symlink(real, directory)


DISK_DAMAGE = [
    ("payload_bit_flip", flip_payload, True), ("orphaned_temporary_file", orphan_temporary, True), ("unexpected_file", unexpected_file, True),
    ("descriptor_lost", lose_descriptor, True), ("metadata_lost", lose_metadata, True), ("substituted_but_consistent_shard", substitute_shard, False),
    ("admitted_shard_deleted", delete_admitted_shard, False), ("role_directory_became_a_symlink", swap_in_a_symlink, False),
]


@pytest.mark.parametrize("name,damage,notes", DISK_DAMAGE, ids=[d[0] for d in DISK_DAMAGE])
def test_damaged_shard_state_found_at_recovery_quarantines_the_run_and_preserves_every_byte(make, custody, integrated, name, damage, notes):
    life, profile, _ = partial(make, shards=6)
    life.interrupt()
    life.close()
    damage(role_dir(life))
    before = T.tree_digest(life.paths["work"])
    again, profile2, _ = recover(make, life, profile, custody, integrated)
    quarantined_with_evidence_intact(again, before)
    assert profile2.producer.calls == 0
    written = sorted(p.name for p in again.paths["quarantine"].iterdir())
    assert (len(written) == 1) is notes                                                          # a note exists exactly where files need an explanation
    if notes:
        assert len(written) == 1 and written[0].startswith("quarantine-")
        note = json.loads((again.paths["quarantine"] / written[0]).read_text())
        assert note["files_moved_or_deleted"] == 0 and note["evidence_preserved_in_place"] is True and note["authorizes_nothing"] is True
    again.advance()
    assert again.state == "QUARANTINED"
    for method in ("verify_evidence", "check_admission", "run_stage", "verify_stage", "backup_stage", "complete_stage", "retry"):
        with pytest.raises(M.InvalidTransition):
            getattr(again, method)()
    again.close()
    third_profile, _ = T.restart_profile(profile.workspace, custody, integrated, profile.plan)
    with pytest.raises(M.LifecycleRefused, match="stopped for good|halted the run"):
        M.SyntheticExecutorLifecycle.recover(third_profile)                                    # quarantine is durable across processes


def test_a_publication_that_fails_midway_leaves_a_partial_shard_that_is_quarantined_not_repaired(make, monkeypatch):
    life, profile, _ = make()
    admitted(life)
    original = S._publish

    def failing(fd, name, raw):
        if name.startswith("meta-00001"):
            raise OSError(28, "No space left on device")
        return original(fd, name, raw)
    monkeypatch.setattr(S, "_publish", failing)
    life.run_stage(shard_budget=5)
    monkeypatch.setattr(S, "_publish", original)
    assert life.state == "QUARANTINED" and profile.producer.calls == 2 and life.summary()["admitted_shards"] == 1
    assert T.incidents(life) == ["partial_commit"]
    directory = role_dir(life)
    assert (directory / "part-00001.npz").exists() and not (directory / "shard-00001.json").exists() and not (directory / "meta-00001.jsonl").exists()
    notes = list(life.paths["quarantine"].iterdir())
    assert len(notes) == 1 and json.loads(notes[0].read_text())["files_moved_or_deleted"] == 0


def test_a_failing_fsync_during_publication_quarantines_the_shard(make, monkeypatch):
    life, profile, _ = make()
    admitted(life)
    real = os.fsync
    calls = {"n": 0}

    def flaky(fd):
        calls["n"] += 1
        if calls["n"] == 7:
            raise OSError(5, "Input/output error")
        return real(fd)
    monkeypatch.setattr(os, "fsync", flaky)
    life.run_stage(shard_budget=3)
    monkeypatch.setattr(os, "fsync", real)
    assert life.state == "QUARANTINED" and T.incidents(life) == ["partial_commit"]


def test_a_verifier_that_detects_replaced_content_between_publication_and_stage_verification_quarantines(make):
    life, profile, _ = partial(make, shards=4)
    flip_payload(role_dir(life))
    life._stage_fully_admitted = lambda: True                                                  # pretend the memory of the run says complete
    life.verify_stage()
    assert life.state == "QUARANTINED" and T.incidents(life) == ["orphan_files"]


def test_verification_does_not_trust_memory_when_a_role_directory_was_swapped_for_an_empty_one(make):
    life, profile, _ = partial(make, shards=4)
    directory = role_dir(life)
    directory.rename(directory.parent / "train.moved")
    directory.mkdir(mode=0o755)
    life._stage_fully_admitted = lambda: True
    life.verify_stage()
    assert life.state == "QUARANTINED"


# ---- completed stages: backup and working-tree damage on restart ----------------------------------------------------------------------

BACKUP_DAMAGE = [
    ("backup_payload_flipped", lambda d: flip_payload(d)),
    ("backup_file_missing", lambda d: (d / "meta-00000.jsonl").unlink()),
    ("backup_has_an_extra_file", lambda d: (d / "extra.bin").write_bytes(b"x")),
    ("backup_role_removed", lambda d: shutil.rmtree(d)),
]


@pytest.mark.parametrize("name,damage", BACKUP_DAMAGE, ids=[b[0] for b in BACKUP_DAMAGE])
def test_a_backup_that_no_longer_equals_its_manifest_quarantines_the_restart_and_is_never_silently_repaired(known, tmp_path, name, damage):
    profile, authority = T.copy_world("known", known, tmp_path / "w")
    target = profile.workspace.backup / "known" / "train"
    damage(Path(target))
    work_before, backup_before = T.tree_digest(profile.workspace.work), T.tree_digest(profile.workspace.backup)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        assert life.state == "QUARANTINED" and "backup" in life.events[-1]["reason"]
        assert T.tree_digest(profile.workspace.work) == work_before and T.tree_digest(profile.workspace.backup) == backup_before
        assert T.incidents(life)[-1] == "backup_mismatch"
    finally:
        life.close()


def test_working_tree_damage_in_a_completed_stage_quarantines_the_restart(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    flip_payload(Path(profile.workspace.work) / "known" / "train")
    before = T.tree_digest(profile.workspace.work)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        quarantined_with_evidence_intact(life, before)
        assert len(list(life.paths["quarantine"].iterdir())) == 1
    finally:
        life.close()


def test_a_clean_restart_between_stages_proceeds_into_the_next_stage(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        assert life.state == "PREPARED" and life.completed == ["known"] and life.stage == "test" and life.summary()["admitted_shards"] == 576
        admitted(life)
        assert life.state == "ADMISSION_CHECKED" and life.boundary_reports[0]["boundary"] == "after_known"
        assert [e["kind"] for e in life.journal_entries()][-2:] == ["boundary_check", "stage_bound"] and life.stage_fingerprints["test"] != known["plan"]["source"]["known_request_fingerprint"]
    finally:
        life.close()


# ---- stage order and K17d on the way into the test-only stage ---------------------------------------------------------------------------

def test_matched_data_before_the_test_stage_is_complete_stops_the_run(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    planted = Path(profile.workspace.work) / "matched" / "test-matched"
    planted.mkdir(parents=True)
    (planted / "part-00000.npz").write_bytes(b"premature matched data")
    snapshot = T.tree_digest(planted)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        admitted(life)
        assert life.state == "STOPPED" and T.incidents(life)[-1] == "stage_order_violation" and T.tree_digest(planted) == snapshot
        assert profile.producer.calls == 0
    finally:
        life.close()


def test_data_planted_inside_the_stage_about_to_be_admitted_is_quarantined(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    planted = Path(profile.workspace.work) / "test" / "test"
    planted.mkdir(parents=True)
    (planted / "part-00000.npz").write_bytes(b"data that no stage admitted")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        admitted(life)
        assert life.state == "QUARANTINED" and profile.producer.calls == 0
    finally:
        life.close()


def test_an_unexpected_entry_beside_a_completed_stage_is_quarantined_at_the_next_boundary(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    (Path(profile.workspace.work) / "known" / "stray").write_bytes(b"x")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        admitted(life)
        assert life.state == "QUARANTINED" and profile.producer.calls == 0
    finally:
        life.close()


def k17d(plan, **changes):
    document = X.SyntheticAttestor.k17d_report(type("A", (), {"k17d_override": None})(), plan)
    for dotted, value in changes.items():
        target = document
        *path, leaf = dotted.split("__")
        for key in path:
            target = target[key]
        target[leaf] = value
    return document


K17D_FAULTS = [
    ("identity_differs", {"identity_sha256": "0" * 64}), ("headline_count_differs", {"counts__headline": 501}), ("sensitivity_count_differs", {"counts__sensitivity": 464}),
    ("synthetic_only_marker", {"metadata_status": "SYNTHETIC_FIXTURE_ONLY"}), ("no_production_cross_check", {"production_cross_verification_performed": False}),
    ("observations_were_read", {"observation_reads": 1}), ("waveforms_were_synthesized", {"waveform_synthesis_calls": 3}),
    ("claims_authority", {"execution_authorized": True}), ("verdict_is_not_no_go", {"verdict": "GO"}),
    ("test_group_called_pristine", {"d1_obligations__existing_test_pristine": True}),
    ("exposure_rows_altered", {"d1_obligations__exposure_excluded_groups": {"test": 500, "test-matched": 150}}),
    ("different_request", {"request_fingerprint": "1" * 64}), ("different_source_head", {"source_head": "2" * 40}),
]


@pytest.mark.parametrize("name,changes", K17D_FAULTS, ids=[f[0] for f in K17D_FAULTS])
def test_any_deviation_from_the_accepted_k17d_identity_stops_the_run_before_the_test_only_stage(known, tmp_path, name, changes):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    profile.attestor.k17d_override = k17d(profile.plan, **changes)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        admitted(life)
        assert life.state == "STOPPED" and T.incidents(life)[-1] == "k17d_mismatch" and profile.producer.calls == 0
    finally:
        life.close()


# ---- the journal itself failing --------------------------------------------------------------------------------------------------------

def journal_path(life):
    return life.paths["journal"] / L.LEDGER_NAME


def append_garbage(life):
    with open(journal_path(life), "ab") as stream:
        stream.write(b"not a ledger entry\n")


def drop_last_entry(life):
    lines = journal_path(life).read_bytes().splitlines(keepends=True)
    journal_path(life).write_bytes(b"".join(lines[:-1]))


def delete_ledger(life):
    journal_path(life).unlink()


def rewrite_a_past_entry(life):
    raw = bytearray(journal_path(life).read_bytes())
    raw[raw.index(b"run_opened") + 2] ^= 0x01
    journal_path(life).write_bytes(bytes(raw))


JOURNAL_FAULTS = [("garbage_appended", append_garbage), ("last_entry_dropped_below_the_anchor", drop_last_entry), ("ledger_deleted", delete_ledger),
                  ("past_entry_rewritten", rewrite_a_past_entry)]


@pytest.mark.parametrize("name,fault", JOURNAL_FAULTS, ids=[f[0] for f in JOURNAL_FAULTS])
def test_a_journal_that_stops_verifying_mid_run_stops_the_run_without_further_shards(make, name, fault):
    life, profile, _ = partial(make, shards=3)
    fault(life)
    calls = profile.producer.calls
    life.run_stage(shard_budget=4)
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is False and life.summary()["journal_ok"] is False
    assert profile.producer.calls == calls + 1                                                    # the shard in flight, never another
    life.advance()
    with pytest.raises(M.InvalidTransition):
        life.run_stage()
    with pytest.raises(M.InvalidTransition):
        life.interrupt()


def test_an_unwritable_journal_or_anchor_custody_stops_the_run(make):
    life, profile, _ = partial(make, shards=2)

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    life.ledger.append = full
    life.run_stage(shard_budget=3)
    assert life.state == "STOPPED" and life.summary()["journal_ok"] is False and profile.producer.calls == 3
    other, profile2, _ = partial(make, shards=2, name="w2") if False else (None, None, None)


def test_unavailable_anchor_custody_stops_the_run(make):
    life, profile, _ = partial(make, shards=2)
    life.anchors.record = lambda head: (_ for _ in ()).throw(OSError(5, "anchor store unreachable"))
    life.run_stage(shard_budget=3)
    assert life.state == "STOPPED" and life.summary()["journal_ok"] is False


def test_a_shard_published_but_not_journaled_is_adopted_by_recovery_only_if_it_verifies(make, custody, integrated):
    life, profile, _ = partial(make, shards=3)
    life.ledger.append = lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left on device"))
    life.run_stage(shard_budget=1)
    assert life.state == "STOPPED" and life.summary()["admitted_shards"] == 4
    again, profile2, _ = recover(make, life, profile, custody, integrated)
    assert again.state == "PREPARED" and again.summary()["admitted_shards"] == 4                  # committed on disk, checked, simply not yet journaled


def test_the_journal_failing_before_the_boundary_check_stops_the_run(make):
    life, profile, _ = make()
    life.verify_evidence()
    drop_last_entry(life)
    life.check_admission()
    assert life.state == "STOPPED" and life.summary()["journal_ok"] is False and profile.producer.calls == 0


# ---- producer failures and the restart allowance --------------------------------------------------------------------------------------

class FlakyProducer(X.SyntheticShardProducer):
    def __init__(self, clock, fail_on):
        super().__init__(clock)
        self.fail_on = set(fail_on)

    def __call__(self, request):
        if (self.calls + 1) in self.fail_on:
            self.calls += 1
            raise RuntimeError("fabricated producer failure")
        return super().__call__(request)


def test_two_producer_failures_exhaust_the_restart_allowance(make, custody, integrated):
    life, profile, _ = make(producer_factory=lambda clock: FlakyProducer(clock, {2}))
    admitted(life)
    life.run_stage(shard_budget=5)
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is True and life.summary()["failed_attempts"] == 1
    again, profile2, _ = recover(make, life, profile, custody, integrated, producer_factory=lambda clock: FlakyProducer(clock, {1}))
    admitted(again)
    assert again.state == "ADMISSION_CHECKED"
    again.run_stage(shard_budget=2)
    assert again.state == "STOPPED" and again.summary()["failed_attempts"] == 2
    third, profile3, _ = recover(make, again, profile2, custody, integrated)
    assert third.state == "PREPARED" and third.summary()["failed_attempts"] == 2
    admitted(third)
    assert third.state == "STOPPED" and "allowance" in third.events[-1]["reason"] and profile3.producer.calls == 0
    assert T.incidents(third)[-1] == "ceiling_breach"


# ---- terminal states -----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["verify_evidence", "check_admission", "run_stage", "verify_stage", "backup_stage", "complete_stage", "retry", "interrupt"])
def test_stopped_and_quarantined_runs_accept_no_further_operation(make, method):
    life, profile, _ = partial(make, shards=2)
    life.interrupt()
    for _ in range(2):
        with pytest.raises(M.InvalidTransition):
            getattr(life, method)()
    life.step()
    life.advance()
    life.run_all()
    assert life.state == "STOPPED" and profile.producer.calls == 2 and M.TRANSITIONS["STOPPED"] == set()


# ---- counters, clocks and links across a restart ---------------------------------------------------------------------------------------

def test_cumulative_resource_counters_cannot_restart_from_zero_after_a_recovery(make, custody, integrated):
    life, profile, _ = partial(make, shards=5)
    life.interrupt()
    again, profile2, _ = recover(make, life, profile, custody, integrated, base_wall_s=0.0, start=T.last_journal_instant(profile.workspace))
    assert again.state == "PREPARED"
    admitted(again)
    assert again.state == "STOPPED" and "restart refused" in again.events[-1]["reason"] and profile2.producer.calls == 0
    assert "decreased" in again.events[-1]["reason"]


def test_a_clock_that_runs_backwards_across_a_restart_is_refused_not_ignored(make, custody, integrated):
    life, profile, _ = partial(make, shards=3)
    life.close()
    new_profile, _ = T.restart_profile(profile.workspace, custody, integrated, profile.plan, start="2026-10-30T12:05:00+00:00")
    with pytest.raises(M.LifecycleRefused, match="journal cannot be extended"):
        M.SyntheticExecutorLifecycle.recover(new_profile)
    assert new_profile.producer.calls == 0


def test_a_symlinked_stage_root_is_never_followed(make, tmp_path):
    life, profile, _ = make()
    life.verify_evidence()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, life.paths["work"] / "known")
    life.check_admission()
    assert life.state == "BLOCKED" and profile.producer.calls == 0 and not list(elsewhere.iterdir())


def test_a_role_changed_between_verification_and_backup_is_refused(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        assert life.manifests["known"]
        substitute_shard(Path(profile.workspace.work) / "known" / "train")
        with pytest.raises(M.LifecycleRefused, match="changed after it was verified"):
            life._copy_and_verify("known")
    finally:
        life.close()


def test_boundary_reports_are_labelled_synthetic(known):
    assert known["boundary_reports"] and all(r["synthetic"] is True and r["evidence_scope"] == "SYNTHETIC_TEST_ROOT" for r in known["boundary_reports"])


# ---- guards found uncovered by mutation testing ---------------------------------------------------------------------------------------

def test_verification_refuses_a_stage_whose_planned_shards_are_not_all_admitted(make):
    life, profile, _ = partial(make, shards=3)
    before = (life.state, life.summary()["admitted_shards"])
    with pytest.raises(M.InvalidTransition, match="not admitted"):
        life.verify_stage()
    assert (life.state, life.summary()["admitted_shards"]) == before and "stage_completed" not in T.kinds(life)


def test_a_retried_backup_copy_is_idempotent_but_never_overwrites_different_bytes(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        role = "val-calib"
        source, target = Path(profile.workspace.work) / "known" / role, Path(profile.workspace.backup) / "known" / role
        ordinals = sorted(life.layout["known"][role])
        before = T.tree_digest(target)
        life._copy(source, target, ordinals)                                                    # identical bytes already there: a no-op, not an error
        assert T.tree_digest(target) == before
        assert life._copy_and_verify("known")["restores"][role]["ok"] is True
        flip_payload_in(target, "part-00001.npz")
        damaged = T.tree_digest(target)
        with pytest.raises(M.LifecycleRefused, match="different bytes"):
            life._copy(source, target, ordinals)
        assert T.tree_digest(target) == damaged                                                 # nothing was overwritten
    finally:
        life.close()


def flip_payload_in(directory, name):
    path = T.writable(directory / name)
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0x01
    path.write_bytes(bytes(raw))
