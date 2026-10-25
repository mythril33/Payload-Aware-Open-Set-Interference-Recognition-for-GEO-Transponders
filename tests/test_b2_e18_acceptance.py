"""E18 acceptance: the ten demonstrations of the synthetic lifecycle, ending in the permanent rejection of real production.

1 fabricated dataset, 2 test-only admission with fabricated isolated evidence, 3 stage transitions, 4 durable synthetic publication,
5 synthetic backup/restore verification, 6 verified external journal chain, 7 controlled stop and restart, 8 expired or revoked
evidence, 9 altered source or data, 10 real production generation stays unreachable even when every fabricated record is valid.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import e18_support as T  # noqa: E402
from test_b2_e17_evidence import custody, integrated  # noqa: E402,F401
from e18_support import admitted, complete, known, make  # noqa: E402,F401

M, X, L, I, D, S, E, P, G, C = T.M, T.X, T.L, T.M.I, T.M.D, T.M.S, T.M.E, T.M.P, T.M.G, T.C


@pytest.fixture(scope="module")
def test_stage(known, tmp_path_factory):
    """The test-only stage run from the finished known stage, with a SIGTERM after ten shards and a restart from the journal."""
    base = tmp_path_factory.mktemp("e18-acceptance") / "w"
    profile, _ = T.copy_world("known", known, base)
    first = M.SyntheticExecutorLifecycle.recover(profile)                                       # a clean restart between the stages
    admitted(first)
    admission = first.boundary_reports[0]
    first.run_stage(shard_budget=10)
    first.interrupt("SIGTERM")
    stopped = {"state": first.state, "events": first.events, "requests": list(profile.producer.requests), "resumable": first.events[-1]["resumable"]}
    first.close()
    profile2, _ = T.restart_profile(profile.workspace, known["custody"], known["bundle"], known["plan"])
    second = M.SyntheticExecutorLifecycle.recover(profile2)
    second.advance()
    facts = {"base": base, "profile": profile2, "admission": admission, "stopped": stopped, "second": second, "events": second.events,
             "requests_after": list(profile2.producer.requests), "reports": second.boundary_reports}
    yield facts
    second.close()


def test_01_a_fabricated_dataset_is_prepared_inside_the_frozen_inventory(make):
    life, profile, _ = make()
    stages = {s["name"]: s["shards"] for s in profile.specification["stages"]}
    assert {name: len(shards) for name, shards in stages.items()} == {"known": 576, "test": 125, "matched": 38}
    assert sum(s["observations"] for shards in stages.values() for s in shards) == 21350
    assert len({g for shards in stages.values() for s in shards for g in s["groups"]}) == 2450       # B2-test/1 re-uses the 500 known-test scenario groups
    assert not [p for p in life.paths["work"].rglob("*") if p.is_file()]                           # nothing exists before the run
    assert G.sup.FIXTURE_MAX_GROUPS == 2 and M.MAX_SYNTHETIC_PAYLOAD <= 64 * 1024 and profile.plan["working"]["root"] == "/data/b2"
    assert str(life.paths["work"]).startswith(str(Path(life.paths["journal"]).parent))             # the synthetic roots are not the declared production roots
    assert not str(life.paths["work"]).startswith("/data/b2")


def test_02_test_only_admission_uses_isolated_fabricated_evidence(test_stage, known):
    report = test_stage["admission"]
    assert report["boundary"] == "after_known" and report["document_conditions_met"] is True
    states = report["conditions"]
    for identifier in ("durability.known", "durability.test", "durability.matched", "backup.known", "k17d.metadata", "journal.external", "isolation.roles",
                       "isolation.consumers", "authorization.policy", "runtime.stop_conditions", "plan.dr04", "identity.source_config_environment", "reporting.d1_d8"):
        assert states[identifier] == I.PASS, identifier
    assert states[I.PERMANENT] == I.BLOCKED
    assert ("known", "test") in I.HELD_OUT and ("test", "test") in I.HELD_OUT and ("matched", "test-matched") in I.HELD_OUT
    assert all(tuple(v) not in I.HELD_OUT for readers in I.ALLOWED_CONSUMERS.values() for v in readers)
    entries = test_stage["second"].journal_entries()
    bound = [e for e in entries if e["kind"] == "stage_bound"]
    assert [e["stage"] for e in bound] == ["test"] and bound[0]["data"]["request_fingerprint"] != known["plan"]["source"]["known_request_fingerprint"]


def test_03_the_stage_follows_the_state_machine_across_a_stop_and_a_restart(test_stage):
    before = [(e["action"], e["to"]) for e in test_stage["stopped"]["events"] if e["action"] != "init"]
    assert before[-3:] == [("check_admission", "ADMISSION_CHECKED"), ("start_stage", "SYNTHETIC_STAGE_RUNNING"), ("stop", "STOPPED")]
    after = [(e["action"], e["to"]) for e in test_stage["events"] if e["action"] not in ("init", "recover")]
    assert after == [("verify_evidence", "EVIDENCE_VERIFIED"), ("check_admission", "ADMISSION_CHECKED"), ("start_stage", "SYNTHETIC_STAGE_RUNNING"),
                     ("verify_stage", "SYNTHETIC_STAGE_VERIFIED"), ("backup_stage", "SYNTHETIC_BACKUP_VERIFIED"),
                     ("complete_stage", "SYNTHETIC_STAGE_COMPLETE"), ("next_stage", "PREPARED")]
    assert [e for e in test_stage["events"] if e["action"] == "check_admission"][0]["mode"] == "resume"
    second = test_stage["second"]
    assert second.completed == ["known", "test"] and second.stage == "matched" and second.state == "PREPARED"


def test_04_publication_is_durable_synthetic_descriptor_last_and_read_only(test_stage):
    second = test_stage["second"]
    directory = second.paths["work"] / "test" / "test"
    sample = [0, 1, 57, 124]
    for ordinal in sample:
        part, meta, descriptor = (directory / name for name in D.shard_names(ordinal))
        assert all(p.stat().st_mode & 0o777 == 0o444 and p.stat().st_nlink == 1 for p in (part, meta, descriptor))
        assert descriptor.stat().st_mtime_ns >= max(part.stat().st_mtime_ns, meta.stat().st_mtime_ns)
        assert part.read_bytes().startswith(M.SYNTHETIC_PREFIX)
        record = second._admissions[("test", "test")][ordinal]
        assert record["barrier"] == "fsync_files_then_directory_chain_then_reverify" and record["media_verified"] is False
        assert record["authorizes_nothing"] is True and record["execution_permitted"] is False
    assert len(second._admissions[("test", "test")]) == 125 and D.immutable_publication_report(directory, list(range(125)))["ok"]
    assert not [p for p in second.paths["work"].rglob("*") if p.name.startswith(".") or p.name.endswith(".tmp")]


def test_05_the_test_stage_backup_restores_byte_for_byte_without_claiming_qualification(test_stage, known):
    second = test_stage["second"]
    spec_stage = [s for s in second.spec["stages"] if s["name"] == "test"][0]
    expected = second._expected_role("test", "test")
    manifest = D.build_manifest(second.paths["work"] / "test" / "test", expected)
    restored = D.verify_restore(second.paths["backup"] / "test" / "test", manifest, expected)
    assert restored["ok"] and restored["files"] == 3 * len(spec_stage["shards"]) and restored["disaster_recovery_qualified"] is False
    backup = second._raw_backup["test"]["restores"]["test"]
    assert backup["manifest_sha256"] == manifest["manifest_sha256"]
    assert second.boundary_reports[-1]["conditions"]["backup.test"] == I.PASS


def test_06_the_external_journal_is_a_verified_anchored_chain_bound_to_the_working_tree(test_stage):
    second = test_stage["second"]
    anchor = second.anchors.latest()
    chain = L.verify_chain(second.ledger.read(), expected_head=anchor)
    assert chain["ok"] and anchor["seq"] == chain["count"] - 1
    assert test_stage["reports"][-1]["conditions"]["journal.external"] == I.PASS and test_stage["reports"][-1]["boundary"] == "after_test"
    kinds = [e["kind"] for e in chain["entries"]]
    assert kinds.count("run_opened") == 1 and kinds.count("stage_completed") == 2 and kinds.count("backup_verified") == 2 and kinds.count("k17d_check") == 1
    assert kinds.count("shard_admitted") == 576 + 125
    manifests = {e["stage"]: e["data"]["manifests"] for e in chain["entries"] if e["kind"] == "stage_completed"}
    assert manifests["test"] == {"test": second.manifests["test"]["test"]}


def test_07_a_controlled_stop_between_shards_restarts_without_repeating_or_losing_work(test_stage):
    stopped = test_stage["stopped"]
    assert stopped["state"] == "STOPPED" and stopped["resumable"] is True and len(stopped["requests"]) == 10
    after = test_stage["requests_after"]
    assert len(after) == 125 - 10 and not set(after) & set(stopped["requests"])
    assert set(after) | set(stopped["requests"]) == {("test", "test", o) for o in range(125)}
    entries = test_stage["second"].journal_entries()
    sigterm = [i for i, e in enumerate(entries) if e["kind"] == "incident" and e["data"]["details"]["signal"] == "SIGTERM"]
    resumes = [i for i, e in enumerate(entries) if e["kind"] == "resume"]
    assert len(sigterm) == 1 and resumes[-1] > sigterm[0]
    assert entries[resumes[-1]]["data"] == entries[0]["data"]                                    # identical plan and specification identities


def test_08a_revoked_evidence_stops_the_run_before_the_next_stage_produces_anything(known, tmp_path):
    profile, authority = T.copy_world("known", known, tmp_path / "w")
    authority.status = "REVOKED"
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        life.verify_evidence()
        assert life.state == "STOPPED" and profile.producer.calls == 0 and "revoked" in life.events[-1]["reason"]
        assert life.stage == "test" and life.completed == ["known"]
    finally:
        life.close()


def test_08b_expired_authorization_stops_the_run_before_the_next_stage_produces_anything(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w", start="2026-11-20T00:00:30+00:00")
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        life.verify_evidence()
        assert life.state == "STOPPED" and profile.producer.calls == 0 and "expired" in life.events[-1]["reason"]
    finally:
        life.close()


def test_09a_altered_source_identity_fails_closed(known, tmp_path):
    def drift(reference):
        reference["tools_sha256"] = dict(reference["tools_sha256"], **{next(iter(reference["tools_sha256"])): "0" * 64})
        return reference
    profile, _ = T.copy_world("known", known, tmp_path / "w", reference_hook=drift)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        life.verify_evidence()
        assert life.state == "BLOCKED" and profile.producer.calls == 0
    finally:
        life.close()


def test_09b_altered_data_fails_closed_and_the_evidence_stays_untouched(known, tmp_path):
    profile, _ = T.copy_world("known", known, tmp_path / "w")
    victim = Path(profile.workspace.work) / "known" / "val-calib"
    path = T.writable(victim / "part-00000.npz")
    path.write_bytes(path.read_bytes()[:-1] + b"\x00")
    before = T.tree_digest(profile.workspace.work)
    life = M.SyntheticExecutorLifecycle.recover(profile)
    try:
        assert life.state == "QUARANTINED" and T.tree_digest(profile.workspace.work) == before and profile.producer.calls == 0
    finally:
        life.close()


def test_10_real_production_generation_is_unreachable_even_when_every_fabricated_record_is_valid(complete):
    # Everything fabricated is valid: signed record, lineage, revocation, CI, devices, K17d comparison, journal, three finished stages.
    summary = complete["summary"]
    assert summary["state"] == "SYNTHETIC_STAGE_COMPLETE" and summary["admitted_shards"] == 739
    assert all(r["document_conditions_met"] for r in complete["boundary_reports"])
    T.assert_no_authority(summary)
    bundle, authority = complete["bundle"], T.Authority(complete["custody"], complete["bundle"])
    gate = M.production_gate(bundle["plan"], bundle["reference"], repo=bundle["repo"], evidence=authority("c" * 64, 9, T.CLOCK), now=T.CLOCK,
                             challenge="c" * 64, revocation_floor=9, ci_floor=9)
    T.assert_no_authority(gate)
    assert gate["lifecycle_state"] == "BLOCKED" and gate["ports_called"] == 0 and gate["trusted_evidence_ok"] is False
    # The public E17 root is unconfigured and no state of the machine is, or leads to, a production run.
    public = E.evaluate_trusted_authorization(bundle["plan"], bundle["reference"], repo=bundle["repo"], evidence=authority("c" * 64, 9, T.CLOCK), now=T.CLOCK,
                                              challenge="c" * 64, revocation_floor=9, ci_floor=9)
    assert public["status"] == "BLOCKED_TRUST_ROOT_MISSING" and public["ok"] is False and public["execution_permitted"] is False
    reachable, frontier = {"PREPARED"}, ["PREPARED"]
    while frontier:
        for target in M.TRANSITIONS[frontier.pop()]:
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    assert reachable == set(M.STATES) and not [s for s in reachable if "PRODUCTION" in s]
    # The existing guards still refuse, and the permanent boundary condition still cannot be satisfied by any document.
    assert G.sup.PRODUCTION_LAUNCH_ENABLED is False and G.sup.FIXTURE_MAX_GROUPS == 2 and E.PINNED_TRUST_ROOT is None
    assert complete["boundary_reports"][-1]["conditions"][I.PERMANENT] == I.BLOCKED
    for refusal, call in ((M.ProductionExecutionUnavailable, M.deny_production), (I.ExecutionUnavailable, I.deny_execution),
                          (C.ExecutionUnavailable, C.deny_execution), (G.e9.ExecutionNotAuthorized, lambda: G.e9.guard_execution("generation"))):
        with pytest.raises(refusal):
            call()
    probe = Path("/nonexistent-e18-final")
    with pytest.raises(G.sup.SupervisorError):
        G.sup.stage_argv("known", G.sup.build_plan(probe, mode="production", groups_per_shard=4), probe)
