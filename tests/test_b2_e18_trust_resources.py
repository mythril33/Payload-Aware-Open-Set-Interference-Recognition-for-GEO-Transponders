"""E18: E17 trusted-evidence adapters and resource supervision exercised through the synthetic lifecycle.

Fabricated ssh keys sign fabricated revocation/CI snapshots in a temporary Git history; resource readings are injected fakes.
Every refusal here must leave the lifecycle halted, no shard produced beyond the point of refusal and no authority created.
"""
from datetime import datetime, timedelta
import copy
import dataclasses
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import e18_support as T  # noqa: E402
from test_b2_e17_evidence import custody, integrated  # noqa: E402,F401
from e18_support import admitted, make, scratch  # noqa: E402,F401

M, X, L, I, D, S, E, P, G, C = T.M, T.X, T.L, T.M.I, T.M.D, T.M.S, T.M.E, T.M.P, T.M.G, T.C
Sig = T.Sig


def refused_before_anything_ran(life, profile, state):
    assert life.state == state, life.events[-2:]
    assert profile.producer.calls == 0 and not life._ledger_exists()
    T.assert_no_authority(life.summary())


# ---- E17 evidence through the lifecycle ---------------------------------------------------------------------------------

def test_signed_evidence_is_verified_bound_to_the_record_and_its_challenge_is_consumed_exactly_once(make):
    life, _, authority = make()
    life.verify_evidence()
    assert life.state == "EVIDENCE_VERIFIED" and authority.calls == 1
    assert life.replay.consumed() == 1
    entries = life.journal_entries()
    snapshot = [e for e in entries if e["kind"] == "authorization_snapshot"]
    assert len(snapshot) == 1 and snapshot[0]["data"]["record_sha256"] == life.plan["authorization"]["record_sha256"]
    assert snapshot[0]["data"]["revocation_id"] == life._grant["revocation_id"]
    evidence = [e for e in entries if e["kind"] == "boundary_check"][0]["data"]
    assert evidence["evidence_scope"] == "SYNTHETIC_TEST_ROOT" and len(evidence["revocation_sha256"]) == len(evidence["ci_sha256"]) == 64


def tampers():
    forged = lambda key: (lambda ev: {**ev, key: b"forged-signature"})                        # noqa: E731
    return [
        ("revocation_signature_forged", BLOCKED, forged("revocation_signature")),
        ("ci_signature_forged", BLOCKED, forged("ci_signature")),
        ("authorization_signature_forged", BLOCKED, forged("authorization_signature")),
        ("authorization_signature_wrong_purpose", BLOCKED, lambda ev: {**ev, "authorization_signature": ev["ci_signature"]}),
        ("revocation_signed_with_the_ci_key", BLOCKED, lambda ev: {**ev, "revocation_signature": ev["ci_signature"]}),
        ("signer_policy_substituted", BLOCKED, lambda ev: {**ev, "policy": {**ev["policy"], "signers": [dict(s, principal="attacker") for s in ev["policy"]["signers"]]}}),
        ("revocation_bytes_altered", BLOCKED, lambda ev: {**ev, "revocation": ev["revocation"].replace(b"ACTIVE", b"ACTIVF")}),
        ("ci_bytes_altered", BLOCKED, lambda ev: {**ev, "ci": ev["ci"].replace(b"success", b"succes5", 1)}),
        ("unexpected_extra_evidence_key", BLOCKED, lambda ev: {**ev, "approved": True}),
        ("evidence_missing_a_part", BLOCKED, lambda ev: {k: v for k, v in ev.items() if k != "ci"}),
        ("evidence_is_not_a_mapping", BLOCKED, lambda ev: "approved"),
    ]


BLOCKED = "BLOCKED"


@pytest.mark.parametrize("name,state,tamper", tampers(), ids=[t[0] for t in tampers()])
def test_forged_substituted_or_malformed_evidence_blocks_before_any_shard_and_consumes_its_challenge(make, name, state, tamper):
    life, profile, authority = make()
    authority.tamper = tamper
    life.verify_evidence()
    refused_before_anything_ran(life, profile, state)
    assert life.replay.consumed() == 1                                                      # a failed answer still burns its one-time challenge


def test_stale_evidence_for_an_earlier_challenge_is_a_replay_and_is_refused(make):
    life, profile, authority = make()
    old = authority("d" * 64, 1, T.CLOCK)
    authority.tamper = lambda ev: old
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "BLOCKED")


def test_one_answer_cannot_be_used_twice(make):
    life, _, authority = make()
    kept = {}
    authority.tamper = lambda ev: kept.setdefault("first", ev)
    life.verify_evidence()
    assert life.state == "EVIDENCE_VERIFIED"
    again = life._trusted_check()                                                           # fresh challenge, the first answer replayed
    assert again["report"]["ok"] is False and life.replay.consumed() == 2


@pytest.mark.parametrize("status", ["REVOKED", "SUSPENDED", "", "active"])
def test_an_explicit_revocation_or_unknown_status_stops_the_run_and_is_never_read_as_active(make, status):
    life, profile, authority = make()
    authority.status = status
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "STOPPED")
    assert "revoked" in life.events[-1]["reason"] and life.events[-1]["resumable"] is False


@pytest.mark.parametrize("name", ["issuer_unreachable", "ci_failed", "ci_other_head", "ci_other_workflow", "ci_missing"])
def test_unavailable_or_unsuccessful_ci_and_issuer_evidence_blocks(make, name):
    life, profile, authority = make()
    run = copy.deepcopy(authority.ci_base["runs"][0])
    if name == "issuer_unreachable":
        authority.available = False
    elif name == "ci_failed":
        authority.ci_runs = [dict(run, conclusion="failure", job_conclusion="failure")]
    elif name == "ci_other_head":
        authority.ci_runs = [dict(run, head_sha="3" * 40)]
    elif name == "ci_other_workflow":
        authority.ci_runs = [dict(run, workflow=".github/workflows/attacker.yml")]
    else:
        authority.ci_runs = []
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "BLOCKED")


def test_a_blocked_run_can_retry_with_good_evidence_and_nothing_stale_survives(make):
    life, profile, authority = make()
    authority.available = False
    life.verify_evidence()
    assert life.state == "BLOCKED"
    authority.available = True
    life.retry()
    life.verify_evidence()
    life.check_admission()
    assert life.state == "ADMISSION_CHECKED" and life.replay.consumed() == 2


def test_an_expired_authorization_stops_the_run_before_anything_starts(make):
    life, profile, _ = make(start="2026-11-20T00:00:01+00:00")
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "STOPPED")
    assert "expired" in life.events[-1]["reason"]


def test_an_authorization_that_expires_mid_stage_stops_after_the_shard_that_crossed_it(make):
    # The fixture host report is 14-day fresh, so the expiry is crossed by one very slow synthetic shard (~26 days of fake time).
    life, profile, _ = make(s_per_observation=70_000.0)
    admitted(life)
    assert life.state == "ADMISSION_CHECKED"
    life.run_stage()
    assert life.state == "STOPPED" and profile.producer.calls == 1
    assert "authorization.expired" in life.events[-1]["reasons"] and T.incidents(life) == ["authorization_expired"]
    assert T.kinds(life)[-1] == "stop"


def test_a_revocation_that_arrives_mid_stage_is_noticed_at_the_next_scheduled_refresh_and_stops_the_run(make):
    life, profile, authority = make(s_per_observation=0.05)                                 # fast shards: the 64-shard schedule is what fires
    admitted(life)
    authority.after_calls = (2, "REVOKED")                                                  # call 1 was the stage-start evidence
    life.run_stage(shard_budget=200)
    assert life.state == "STOPPED" and profile.producer.calls == M.REFRESH_EVERY_SHARDS
    assert T.incidents(life) == ["authorization_revoked"] and life.replay.consumed() == 2
    with pytest.raises(M.InvalidTransition):
        life.run_stage()


def test_an_active_refresh_is_journaled_and_costs_one_challenge(make):
    life, profile, _ = make(s_per_observation=0.05)
    admitted(life)
    life.run_stage(shard_budget=M.REFRESH_EVERY_SHARDS * 2 + 3)
    assert life.state == "SYNTHETIC_STAGE_RUNNING" and life.replay.consumed() == 3
    phases = [e["data"]["phase"] for e in life.journal_entries() if e["kind"] == "boundary_check"]
    assert phases.count("revocation_refresh") == 2


def test_the_reference_checkout_must_equal_the_signed_source_identity_from_the_start(make, integrated):
    def drift(reference):
        reference["files_sha256"] = dict(reference["files_sha256"], **{next(iter(reference["files_sha256"])): "0" * 64})
        return reference
    life, profile, _ = make(reference_hook=drift)
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "BLOCKED")


def test_source_drift_between_boundaries_stops_the_run_at_the_next_scheduled_check(make):
    state = {"drift": False}

    def hook(reference):
        if state["drift"]:
            reference["head"] = "0" * 40
        return reference
    life, profile, _ = make(reference_hook=hook, s_per_observation=0.05)
    admitted(life)
    state["drift"] = True
    life.run_stage(shard_budget=200)
    assert life.state == "STOPPED" and profile.producer.calls == M.REFRESH_EVERY_SHARDS
    assert T.incidents(life) == ["identity_mismatch"]


def test_an_untracked_importable_file_in_the_evidence_checkout_blocks_trust(make, integrated):
    stray = integrated["repo"] / "src" / "zz_e18_untracked.py"
    stray.write_text("X = 1\n")
    try:
        life, profile, _ = make()
        life.verify_evidence()
        refused_before_anything_ran(life, profile, "BLOCKED")
    finally:
        stray.unlink()


def test_a_closed_canonical_reference_cannot_be_used_to_claim_authorization(make):
    def closed(reference):
        for key, path in (("gates", P.pre.GATES_PATH), ("memo", P.pre.MEMO_PATH), ("scientific_protocol", G.PROTOCOL_JSON)):
            reference[key] = Sig.strict_json((ROOT / path).read_bytes())
        return reference
    life, profile, _ = make(reference_hook=closed)
    life.verify_evidence()
    refused_before_anything_ran(life, profile, "BLOCKED")


def test_replay_custody_issues_increasing_sequences_and_each_challenge_only_once(tmp_path):
    (tmp_path / "r").mkdir()
    store = M.ReplayStore(tmp_path / "r")
    (c1, s1), (c2, s2) = store.begin(), store.begin()
    assert (s1, s2) == (1, 2) and c1 != c2 and len(c1) == 64 and set(c1) <= set("0123456789abcdef")
    store.finish(c1, s1)
    with pytest.raises(M.LifecycleRefused, match="already consumed"):
        store.finish(c1, s1)
    with pytest.raises(M.LifecycleRefused, match="not issued"):
        store.finish("e" * 64, s2)
    with pytest.raises(M.LifecycleRefused, match="not issued"):
        store.finish(c2, 7)
    assert store.consumed() == 1
    again = M.ReplayStore(tmp_path / "r")                                                    # custody survives the controller
    assert again.begin()[1] == 3


def test_the_anchor_store_is_append_only_and_refuses_a_different_head_at_the_same_sequence(tmp_path):
    (tmp_path / "a").mkdir()
    anchors = M.AnchorStore(tmp_path / "a")
    assert anchors.latest() is None
    anchors.record({"seq": 0, "entry_sha256": "a" * 64})
    anchors.record({"seq": 0, "entry_sha256": "a" * 64})                                       # idempotent
    with pytest.raises(M.LifecycleRefused, match="different head"):
        anchors.record({"seq": 0, "entry_sha256": "b" * 64})
    anchors.record({"seq": 3, "entry_sha256": "c" * 64})
    assert anchors.latest() == {"seq": 3, "entry_sha256": "c" * 64}
    for bad in ({}, {"seq": -1, "entry_sha256": "a" * 64}, {"seq": True, "entry_sha256": "a" * 64}, {"seq": 1}, "head"):
        with pytest.raises(M.LifecycleRefused):
            anchors.record(bad)


# ---- resource supervision ----------------------------------------------------------------------------------------------------

def from_call(n, change):
    return lambda reading, call: change(dict(reading)) if call >= n else reading


def stale(reading):
    reading["collected_at"] = (datetime.fromisoformat(reading["collected_at"]) - timedelta(minutes=20)).isoformat()
    return reading


def future(reading):
    reading["collected_at"] = (datetime.fromisoformat(reading["collected_at"]) + timedelta(hours=1)).isoformat()
    return reading


def without(key):
    return lambda reading: {k: v for k, v in reading.items() if k != key}


def setting(**values):
    return lambda reading: {**reading, **values}


RESOURCE_FAULTS = [
    ("rss_over_ceiling", setting(peak_rss_gib=2.5), "ceiling_breach"),
    ("wall_over_ceiling", setting(elapsed_wall_s=36 * 3600 + 5.0, cpu_core_s=100.0), "ceiling_breach"),
    ("core_hours_over_ceiling", setting(elapsed_wall_s=20000.0, cpu_core_s=42 * 3600 + 5.0), "ceiling_breach"),
    ("working_disk_insufficient", setting(working_free_gib=1.0), "projection_breach"),
    ("backup_space_insufficient", setting(backup_free_gb=0.001), "projection_breach"),
    ("field_missing", without("peak_rss_gib"), "resource_observation_missing"),
    ("field_extra", setting(gpu_util=0.5), "resource_observation_missing"),
    ("nan", setting(elapsed_wall_s=float("nan")), "resource_observation_missing"),
    ("infinity", setting(cpu_core_s=float("inf")), "resource_observation_missing"),
    ("negative", setting(peak_rss_gib=-1.0), "resource_observation_missing"),
    ("boolean_instead_of_number", setting(working_free_gib=True), "resource_observation_missing"),
    ("text_instead_of_number", setting(elapsed_wall_s="5"), "resource_observation_missing"),
    ("null", setting(peak_rss_gib=None), "resource_observation_missing"),
    ("stale_by_twenty_minutes", stale, "resource_observation_missing"),
    ("dated_an_hour_ahead", future, "resource_observation_missing"),
    ("more_cpu_than_cores_exist", lambda r: {**r, "cpu_core_s": r["elapsed_wall_s"] * 100 + 10_000}, "resource_observation_missing"),
]


@pytest.mark.parametrize("name,change,incident", RESOURCE_FAULTS, ids=[f[0] for f in RESOURCE_FAULTS])
def test_a_bad_resource_reading_stops_the_run_after_the_shard_it_follows(make, name, change, incident):
    life, profile, _ = make(mutate=from_call(2, change))
    admitted(life)
    life.run_stage(shard_budget=5)
    assert life.state == "STOPPED" and profile.producer.calls == 1 and life.summary()["admitted_shards"] == 1
    assert T.incidents(life) == [incident] and T.kinds(life)[-1] == "stop"
    assert life.events[-1]["resumable"] is False


@pytest.mark.parametrize("not_a_reading", [None, [], "readings", 3])
def test_a_reading_that_is_not_a_mapping_is_a_missing_reading(make, not_a_reading):
    life, profile, _ = make(mutate=lambda reading, call: not_a_reading if call >= 2 else reading)
    admitted(life)
    life.run_stage(shard_budget=2)
    assert life.state == "STOPPED" and T.incidents(life) == ["resource_observation_missing"]


def test_counters_that_run_backwards_are_an_inconsistent_observer(make):
    life, profile, _ = make(mutate=lambda reading, call: {**reading, "elapsed_wall_s": 10_000.0 if call == 2 else 5.0, "cpu_core_s": 0.0} if call >= 2 else reading)
    admitted(life)
    life.run_stage(shard_budget=5)
    assert life.state == "STOPPED" and life.summary()["admitted_shards"] == 2 and T.incidents(life) == ["resource_observation_missing"]


@pytest.mark.parametrize("name,change", [(n, c) for n, c, _ in RESOURCE_FAULTS if n in ("rss_over_ceiling", "wall_over_ceiling", "working_disk_insufficient", "stale_by_twenty_minutes")])
def test_the_same_faults_refuse_admission_before_the_first_shard(make, name, change):
    life, profile, _ = make(mutate=from_call(1, change))
    life.verify_evidence()
    life.check_admission()
    assert life.state == "STOPPED" and profile.producer.calls == 0
    assert T.kinds(life)[-1] == "stop" and len(T.incidents(life)) == 1


@pytest.mark.parametrize("name", ["nan", "infinity", "negative", "boolean_instead_of_number", "text_instead_of_number", "null"])
def test_a_malformed_reading_at_admission_is_a_missing_fact_and_blocks_before_anything_runs(make, name):
    change = dict((n, c) for n, c, _ in RESOURCE_FAULTS)[name]
    life, profile, _ = make(mutate=from_call(1, change))
    life.verify_evidence()
    life.check_admission()
    assert life.state == "BLOCKED" and profile.producer.calls == 0 and "could not be assembled" in life.events[-1]["reason"]


def test_a_first_shard_that_is_too_slow_stops_the_run(make):
    life, profile, _ = make(s_per_observation=6.5)                                           # band 3.8..5.0, tolerance 25 % -> limit 6.25
    admitted(life)
    life.run_stage(shard_budget=3)
    assert life.state == "STOPPED" and profile.producer.calls == 1 and T.incidents(life) == ["timing_gate_failure"]
    assert life._first_shard["s_per_observation"] == pytest.approx(6.5)


def test_a_passing_first_shard_timing_gate_cannot_override_an_insufficient_remaining_budget(make):
    life, profile, _ = make(s_per_observation=5.5, base_wall_s=15_000.0)                      # 5.5 s/obs is inside the 6.25 tolerance
    admitted(life)
    assert life.state == "ADMISSION_CHECKED"                                                 # at the conservative band rate the budget still fits
    life.run_stage(shard_budget=3)
    assert life.state == "STOPPED" and profile.producer.calls == 1
    reasons = life.events[-1]["reasons"]
    assert "projection.wall_hours" in reasons and not [r for r in reasons if r.startswith("timing.")]
    assert T.incidents(life) == ["projection_breach"]
    assert life._first_shard["s_per_observation"] == pytest.approx(5.5)


def test_a_budget_that_cannot_finish_even_at_the_best_case_rate_is_refused_at_admission(make):
    life, profile, _ = make(base_wall_s=40_000.0)
    life.verify_evidence()
    life.check_admission()
    assert life.state == "STOPPED" and profile.producer.calls == 0 and T.incidents(life) == ["projection_breach"]


def test_a_fast_first_shard_is_measured_not_trusted_and_the_run_continues(make):
    life, profile, _ = make(s_per_observation=1.0)
    admitted(life)
    life.run_stage(shard_budget=4)
    assert life.state == "SYNTHETIC_STAGE_RUNNING" and profile.producer.calls == 4
    assert life._first_shard["s_per_observation"] == pytest.approx(1.0)


def test_the_observation_reports_committed_and_remaining_work_exactly(make):
    life, profile, _ = make()
    admitted(life)
    life.run_stage(shard_budget=2)
    done = sum(life.layout[s][r][o]["observations"] for (s, r), a in life._admissions.items() for o in a)
    observation = life._resource_state()
    assert observation["observations_committed"] == done > 0
    assert observation["observations_remaining"] == 21350 - done and observation["admitted_shards_this_attempt"] == 2
    assert observation["failed_attempts"] == observation["interruptions"] == 0 and observation["total_attempts"] == 1
    assert observation["first_shard"]["observations"] > 0


def test_resource_ports_are_read_only_and_no_reading_is_cached_across_decisions(make):
    life, profile, _ = make()
    admitted(life)
    before = profile.resources.calls
    life.run_stage(shard_budget=3)
    assert profile.resources.calls == before + 3


# ---- review remediation: refresh by time, outage handling -----------------------------------------------------------------------------

def test_a_revocation_is_rechecked_by_elapsed_time_even_when_few_shards_were_produced(make):
    life, profile, authority = make()                                                       # nominal 4.4 s/observation: ~141 s per 32-observation shard
    admitted(life)
    authority.after_calls = (2, "REVOKED")
    life.run_stage(shard_budget=200)
    shard_seconds = 4.4 * 32
    assert life.state == "STOPPED" and T.incidents(life) == ["authorization_revoked"]
    assert profile.producer.calls * shard_seconds >= M.REFRESH_EVERY_SECONDS > (profile.producer.calls - 1) * shard_seconds
    assert profile.producer.calls < M.REFRESH_EVERY_SHARDS


def test_the_time_schedule_costs_one_challenge_per_interval_and_keeps_the_run_going_while_the_grant_is_active(make):
    life, profile, _ = make()
    admitted(life)
    life.run_stage(shard_budget=60)
    refreshes = [e for e in life.journal_entries() if e["kind"] == "boundary_check" and e["data"].get("phase") == "revocation_refresh"]
    assert life.state == "SYNTHETIC_STAGE_RUNNING" and len(refreshes) == int(60 * 4.4 * 32 // M.REFRESH_EVERY_SECONDS)
    assert life.replay.consumed() == 1 + len(refreshes)


def test_an_unreachable_revocation_source_mid_run_is_a_resumable_interruption_not_a_verdict(make, custody, integrated):
    life, profile, authority = make(s_per_observation=0.05)
    admitted(life)
    authority.unreachable_from = 2
    life.run_stage(shard_budget=200)
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is True and profile.producer.calls == M.REFRESH_EVERY_SHARDS
    incident = [e for e in life.journal_entries() if e["kind"] == "incident"][-1]["data"]
    assert incident["incident"] == "interruption" and incident["details"]["signal"] == "REVOCATION_UNAVAILABLE"
    assert life.summary()["interruptions"] == 1


def test_a_bad_but_reachable_revocation_answer_is_a_hard_stop(make):
    life, profile, authority = make(s_per_observation=0.05)
    admitted(life)
    authority.tamper = lambda ev: {**ev, "revocation_signature": b"forged"}
    life.run_stage(shard_budget=200)
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is False and T.incidents(life) == ["resource_observation_missing"]
