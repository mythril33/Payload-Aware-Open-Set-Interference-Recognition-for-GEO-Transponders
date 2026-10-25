"""E16 release-boundary integration over a fully synthetic world.

Everything physical here is fabricated bytes in temporary directories laid out like the accepted generators' shards (no RF
array, no waveform, no model, no GPU, no held-out observation). Devices, the K17d comparison and resource readings are
fabricated documents returned by fake read-only adapters. A world in which every document is consistent still ends in
NO-GO: the integration cannot start anything.
"""
import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b2_e16_integration as I  # noqa: E402
from test_b2_e13_generation_plan import reference, decision_record, k17d_report, H, HEAD, APPROVER, RECORD  # noqa: E402,F401
from test_b2_e16_policy import approved, adapters as policy_adapters, CLOCK, SCOPE  # noqa: E402

D, L, P, C, G, S = I.D, I.L, I.P, I.C, I.G, I.S
WORKING, BACKUP = "/data/b2", "/mnt/backup/b2"
COLLECTED = "2026-10-30T12:04:00+00:00"
OBSERVED = "2026-10-30T12:04:30+00:00"
KNOWN_FP = H("request")                        # the fixture reference's known_request_fingerprint
FINGERPRINTS = {"known": KNOWN_FP, "test": H("deferred test request"), "matched": H("deferred matched request")}
_CACHE = {}


# ---- the physical world, built once --------------------------------------------------------------------------------

def rewrite(value, mapping, devices):
    if isinstance(value, dict):
        return {k: (devices.get(v, v) if k == "st_dev" and type(v) is int else rewrite(v, mapping, devices)) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v, mapping, devices) for v in value]
    if isinstance(value, str):
        for source, target in mapping:
            if value.startswith(source):
                return target + value[len(source):]
    return value


def write_shard(directory, stage, shard, fingerprint):
    part, meta, descriptor_name = D.shard_names(shard["ordinal"])
    payload = b"E16-SYNTHETIC-NON-RF-PAYLOAD " + f"{stage}/{shard['role']}/{shard['ordinal']}".encode() * 8
    lines = b"".join(json.dumps({"i": i, "synthetic": True}).encode() + b"\n" for i in range(shard["observations"]))
    (directory / part).write_bytes(payload)
    (directory / meta).write_bytes(lines)
    (directory / descriptor_name).write_text(json.dumps({
        "part": part, "meta": meta, "role": shard["role"], "scenario_seeds": shard["groups"], "n_samples": shard["observations"],
        "request_fingerprint": fingerprint,
        "sha256": {part: hashlib.sha256(payload).hexdigest(), meta: hashlib.sha256(lines).hexdigest()}}, indent=1))
    for step, name in enumerate((part, meta, descriptor_name)):
        os.utime(directory / name, ns=((1_700_000_000 + step) * 10 ** 9,) * 2)
        os.chmod(directory / name, 0o444)


def device(side, plan, device_id, free):
    section = plan["working"] if side == "working" else plan["backup"]
    return {"schema": S.DEVICE_SCHEMA, "host_id": plan["host"]["host_id"], "root": section["root"], "measured_at": COLLECTED,
            "filesystem_device": device_id, "filesystem_type": "xfs" if side == "working" else "ext4", "physical_storage_id": section["storage_id"],
            "physical_identity_evidence_sha256": H("evidence-" + side), "capacity_bytes": 500 * 2 ** 30 if side == "working" else 100 * 10 ** 9,
            "free_bytes": free}


def build_world(spec, plan, base):
    """Physical shards -> real durability reports -> relabelled to the plan's declared roots and devices."""
    work, backup = base / "work", base / "backup"
    world = {"stage": {}, "backup": {}, "manifests": {}}
    with mock.patch("os.fsync", lambda fd: None):                   # the barrier's own fsync order is tested in the durability suite
        for stage in spec["stages"]:
            name = stage["name"]
            roles = {}
            for shard in stage["shards"]:
                roles.setdefault(shard["role"], []).append(shard)
            doc_roles, restores, copies = {}, {}, {}
            for role, shards in roles.items():
                directory, copy_directory = work / name / role, backup / name / role
                directory.mkdir(parents=True)
                os.chmod(directory, 0o755)
                expected = {s["ordinal"]: {"role": role, "scenario_seeds": s["groups"], "n_samples": s["observations"],
                                           "request_fingerprint": FINGERPRINTS[name]} for s in shards}
                for s in shards:
                    write_shard(directory, name, s, FINGERPRINTS[name])
                classification = D.classify_directory(directory, expected)
                admissions = [D.admit_shard(directory, o, expected[o]) for o in sorted(expected)]
                manifest = D.build_manifest(directory, expected)
                immutability = D.immutable_publication_report(directory, sorted(expected))
                identity = D.directory_identity(directory)
                doc_roles[role] = {"exists": True, "directory": identity, "classification": classification, "admissions": admissions,
                                   "manifest": manifest, "immutability": immutability}
                shutil.copytree(directory, copy_directory)
                os.chmod(copy_directory, 0o755)
                restores[role] = D.verify_restore(copy_directory, manifest, expected)
                copies[role] = D.directory_identity(copy_directory)
            real = os.stat(work).st_dev
            maps = [(str(work), WORKING)]
            world["stage"][name] = rewrite({"schema": I.SCHEMA_STAGE, "stage": name, "collected_at": COLLECTED,
                                            "root": D.directory_identity(work / name), "request_fingerprint": FINGERPRINTS[name],
                                            "roles": doc_roles, "unexpected_root_entries": []}, maps, {real: 11})
            world["backup"][name] = rewrite({"schema": I.SCHEMA_BACKUP, "stage": name, "collected_at": COLLECTED,
                                             "devices": {}, "restores": restores, "copies": copies}, [(str(backup), BACKUP)], {real: 22})
            world["manifests"][name] = {role: entry["manifest"]["manifest_sha256"] for role, entry in doc_roles.items()}
    return world


@pytest.fixture
def world(reference, tmp_path_factory):
    plan, ref = approved(reference)
    spec = C.build_specification(plan)
    if "world" not in _CACHE:
        _CACHE["world"] = build_world(spec, plan, tmp_path_factory.mktemp("e16-world"))
    cached = _CACHE["world"]
    return World(plan, ref, spec, cached)


class World:
    def __init__(self, plan, ref, spec, cached):
        self.plan, self.ref, self.spec, self.cached = plan, ref, spec, cached
        self.k17d = {"schema": I.K17D_SCHEMA, "verdict": "NO-GO", "metadata_status": "ACCEPTED_IDENTITY_METADATA_MATCH",
                     "production_cross_verification_performed": True, "request_fingerprint": plan["source"]["known_request_fingerprint"],
                     "source_head": plan["source"]["git_commit"], "counts": dict(I.K17D_COUNTS),
                     "identity_sha256": plan["scientific"]["d8_k17d"]["identity_sha256"], "observation_reads": 0, "waveform_synthesis_calls": 0,
                     "execution_authorized": False, "production_authorized": False, "benchmark_complete": False,
                     "d1_obligations": {"existing_test_pristine": False, "exposed_test_ids": plan["scientific"]["d1_exposure"]["exposed_test_ids"],
                                        "exposed_matched_ids": plan["scientific"]["d1_exposure"]["exposed_matched_ids"],
                                        "exposure_excluded_groups": {"test": 498, "test-matched": 148}},
                     "collected_at": COLLECTED}
        self.resource = {"schema": L.SCHEMA_OBSERVATION, "collected_at": OBSERVED, "elapsed_wall_s": 3600.0, "cpu_core_s": 4000.0,
                         "peak_rss_gib": 0.6, "working_free_gib": 400.0, "backup_free_gb": 90.0, "failed_attempts": 0, "interruptions": 0,
                         "total_attempts": 1, "observations_committed": 128, "observations_remaining": 1000, "admitted_shards_this_attempt": 4,
                         "first_shard": {"s_per_observation": 4.4, "observations": 32}}
        self.devices = {"working": device("working", plan, 11, 400 * 2 ** 30), "backup": device("backup", plan, 22, 90 * 10 ** 9)}
        self.devices.update(observed_working=dict(self.devices["working"], measured_at=OBSERVED),
                            observed_backup=dict(self.devices["backup"], measured_at=OBSERVED))

    def not_started(self, stage):
        roles = {role: {"exists": False, "directory": None, "classification": None, "admissions": None, "manifest": None, "immutability": None}
                 for role in I.STAGE_ROLES[stage]}
        return {"schema": I.SCHEMA_STAGE, "stage": stage, "collected_at": COLLECTED, "root": {"path": f"{WORKING}/{stage}"},
                "request_fingerprint": None, "roles": roles, "unexpected_root_entries": []}

    def stage_doc(self, stage, boundary):
        return copy.deepcopy(self.cached["stage"][stage]) if stage in I.BOUNDARIES[boundary] else self.not_started(stage)

    def backup_doc(self, stage):
        doc = copy.deepcopy(self.cached["backup"][stage])
        doc["devices"] = copy.deepcopy(self.devices)
        return doc

    def journal_entries(self, boundary):
        spec_sha = self.spec["specification_sha256"]
        identity = {"plan_fingerprint": self.plan["plan_fingerprint"], "specification_sha256": spec_sha}
        script = [("run_opened", None, identity), ("authorization_snapshot", None, {"record_sha256": self.plan["authorization"]["record_sha256"],
                                                                                    "expires_at": self.plan["authorization"]["expires_at"]})]
        for stage in I.BOUNDARIES[boundary]:
            if stage != "known":
                script.append(("stage_bound", stage, {"request_fingerprint": FINGERPRINTS[stage]}))
            script.append(("stage_completed", stage, {"manifests": self.cached["manifests"][stage]}))
            script.append(("backup_verified", stage, {"manifests": self.cached["manifests"][stage]}))
            if stage == "known":
                script.append(("k17d_check", None, {"identity_sha256": self.k17d["identity_sha256"]}))
        entries, previous = [], L.GENESIS
        for index, (kind, stage, data) in enumerate(script):
            entry = L.make_entry(index, previous, f"2026-10-30T09:{index:02d}:00+00:00", kind, stage, data)
            entries.append(entry)
            previous = entry["entry_sha256"]
        return entries

    def journal_doc(self, boundary, entries=None):
        entries = self.journal_entries(boundary) if entries is None else entries
        head = entries[-1]
        return {"schema": I.SCHEMA_JOURNAL, "collected_at": OBSERVED, "entries": entries,
                "anchor": {"seq": head["seq"], "entry_sha256": head["entry_sha256"]},
                "location": {"ok": True, "failures": [], "shares_device_with_backup": False, "physical_independence_proven": False,
                             "authorizes_nothing": True, "execution_permitted": False}}

    def adapters(self, boundary, **override):
        value = {"shard_state": lambda stage: self.stage_doc(stage, boundary), "backup_state": lambda stage: self.backup_doc(stage),
                 "journal_state": lambda: self.journal_doc(boundary), "k17d_metadata": lambda: copy.deepcopy(self.k17d),
                 "resource_state": lambda stage: copy.deepcopy(self.resource),
                 "consumer_declaration": lambda: copy.deepcopy(I.ALLOWED_CONSUMERS), **policy_adapters()}
        value.update(override)
        return value

    def run(self, boundary="after_matched", scope=None, now=CLOCK, **override):
        report = I.evaluate_release_boundary(self.plan, self.ref, self.spec, boundary=boundary, now=now,
                                             requested_scope=copy.deepcopy(SCOPE) if scope is None else scope,
                                             adapters=self.adapters(boundary, **override))
        assert_closed(report)
        return report


def assert_closed(report):
    assert report["verdict"] == "NO-GO" and report["execution_permitted"] is False and report["authorizes_nothing"] is True
    assert report["production_launch_enabled"] is False and report["executor_implemented"] is False and report["benchmark_complete"] is False
    assert report["execution_conditions_met"] is False
    assert report["scientific_approvals_modified"] is False and report["canonical_gates_modified"] is False
    assert report["mandatory_reporting"]["d1_existing_test_pristine"] is False
    assert report["mandatory_reporting"]["d1_exclusion_rows"] == {"test": 498, "test-matched": 148}
    permanent = {c["id"]: c for c in report["conditions"]}[I.PERMANENT]
    assert permanent["status"] == I.BLOCKED and permanent["details"]["permanent"] is True
    json.dumps(report, allow_nan=False)


def status(report):
    return {c["id"]: c["status"] for c in report["conditions"]}


def failing(report):
    return sorted(c["id"] for c in report["conditions"] if c["status"] == I.FAIL)


def mutate_stage(world, stage, change, boundary="after_matched"):
    def shard_state(requested):
        doc = world.stage_doc(requested, boundary)
        if requested == stage:
            change(doc)
        return doc
    return shard_state


# ---- the consistent world --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("boundary", list(I.BOUNDARIES))
def test_every_boundary_of_a_fully_consistent_world_meets_its_document_conditions_and_still_launches_nothing(world, boundary):
    report = world.run(boundary)
    assert report["document_conditions_met"] is True, [c for c in report["conditions"] if c["status"] not in (I.PASS, I.BLOCKED) and c["applicable"]]
    assert [c["id"] for c in report["conditions"] if c["status"] == I.BLOCKED] == [I.PERMANENT]
    assert report["boundary"] == boundary and report["next_stage"] == I.NEXT_STAGE[boundary]
    ids = {c["id"] for c in report["conditions"]}
    assert {"inventory.frozen", "spec.sealed", "sequence.stages", "plan.dr04", "identity.source_config_environment", "reporting.d1_d8",
            "authorization.scope", "authorization.policy", "durability.known", "durability.test", "durability.matched", "isolation.roles",
            "journal.external", "runtime.stop_conditions", I.PERMANENT} <= ids


def test_the_world_is_deterministic_and_inputs_are_not_modified(world):
    before = copy.deepcopy((world.plan, world.ref, world.spec))
    first, second = world.run("after_test"), world.run("after_test")
    assert first == second
    assert (world.plan, world.ref, world.spec) == before


def test_stage_sizes_match_the_frozen_inventory(world):
    sizes = {stage: sum(len(entry["admissions"]) for entry in world.stage_doc(stage, "after_matched")["roles"].values()) for stage in I.STAGES}
    assert sizes == {"known": 576, "test": 125, "matched": 38}
    assert sum(sizes.values()) == 739


# ---- the real, unapproved state ---------------------------------------------------------------------------------------

def test_the_unapproved_template_is_blocked_everywhere_with_no_adapters(reference):
    plan = G.make_template(reference)
    spec = C.build_specification(plan)
    report = I.evaluate_release_boundary(plan, reference, spec, boundary="pre_launch", requested_scope=copy.deepcopy(SCOPE), now=CLOCK)
    assert_closed(report)
    assert report["document_conditions_met"] is False
    found = status(report)
    assert found["authorization.policy"] == I.BLOCKED and found["plan.dr04"] == I.BLOCKED
    assert found["durability.known"] == I.NOT_RUN and found["journal.external"] == I.NOT_RUN and found["runtime.stop_conditions"] == I.BLOCKED
    assert found["inventory.frozen"] == I.PASS and found["spec.sealed"] == I.PASS and found["sequence.stages"] == I.PASS


@pytest.mark.parametrize("name", I.ADAPTER_NAMES)
def test_a_missing_adapter_is_a_missing_fact_not_a_pass(world, name):
    adapters = {k: v for k, v in world.adapters("after_known").items() if k != name}
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=copy.deepcopy(SCOPE), now=CLOCK, adapters=adapters)
    assert_closed(report)
    assert report["document_conditions_met"] is False
    if name == "consumer_declaration":
        assert status(report)["isolation.consumers"] == I.NOT_RUN           # applicable: absence of leakage evidence counts against
    if name in P.ADAPTER_NAMES:
        assert status(report)["authorization.policy"] == I.FAIL


# ---- sequencing and stage order ---------------------------------------------------------------------------------------

def test_later_stage_data_before_its_predecessor_is_a_stage_order_violation(world):
    for boundary, early in (("pre_launch", "known"), ("after_known", "test"), ("after_test", "matched")):
        def shard_state(stage, boundary=boundary, early=early):
            return copy.deepcopy(world.cached["stage"][stage]) if stage == early else world.stage_doc(stage, boundary)
        report = world.run(boundary, shard_state=shard_state)
        assert f"durability.{early}" in failing(report), (boundary, early)
        assert report["document_conditions_met"] is False


def test_a_complete_stage_that_is_expected_to_be_complete_but_has_no_data_fails(world):
    report = world.run("after_known", shard_state=lambda stage: world.not_started(stage))
    assert "durability.known" in failing(report)


def test_unknown_boundaries_scopes_and_arguments_produce_failed_conditions_not_crashes(world):
    for kwargs in ({"boundary": "after_everything"}, {"now": "soon"}, {"max_evidence_age_s": 0}, {"max_evidence_age_s": True}, {"adapters": {"launch": lambda: None}},
                   {"adapters": {"shard_state": "not callable"}}, {"adapters": []}):
        arguments = dict(boundary="after_known", requested_scope=copy.deepcopy(SCOPE), now=CLOCK, adapters=world.adapters("after_known"))
        arguments.update(kwargs)
        report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, **arguments)
        assert_closed(report)
        assert "input" in failing(report), kwargs
        assert report["document_conditions_met"] is False
    for bad in (None, [], "x", {}):
        report = I.evaluate_release_boundary(bad, world.ref, world.spec, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK)
        assert "input" in failing(report) and report["document_conditions_met"] is False
        report = I.evaluate_release_boundary(world.plan, world.ref, bad, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK)
        assert report["document_conditions_met"] is False


def test_specification_must_equal_the_one_sealed_from_the_plan(world):
    forged = copy.deepcopy(world.spec)
    forged["runtime_policy"]["production_launch_enabled"] = True
    report = I.evaluate_release_boundary(world.plan, world.ref, forged, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK)
    assert status(report)["spec.sealed"] == I.FAIL and report["document_conditions_met"] is False
    forged = copy.deepcopy(world.spec)
    forged["stages"][1]["requires_completed_stage"] = None
    assert status(I.evaluate_release_boundary(world.plan, world.ref, forged, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK))["spec.sealed"] == I.FAIL


def test_scientific_identity_or_source_mismatch_is_reported_where_it_belongs(world):
    world.ref["tree_clean"] = False
    report = world.run("after_known")
    assert status(report)["identity.source_config_environment"] == I.FAIL
    world.ref["tree_clean"] = True
    world.plan["scientific"]["d8_k17d"]["counts"]["headline"] = 499
    report = world.run("after_known")                 # an unsealed edit is refused outright (the fingerprint no longer matches)
    assert "input" in failing(report)
    world.plan["plan_fingerprint"] = G.plan_fingerprint(world.plan)
    world.spec = C.build_specification(world.plan)
    report = world.run("after_known")                 # a resealed edit is judged against the frozen D-8 identity
    assert status(report)["reporting.d1_d8"] == I.FAIL and status(report)["authorization.policy"] == I.FAIL


# ---- durability evidence ---------------------------------------------------------------------------------------------

def damage_cases():
    yield "orphan_in_classification", lambda d: d["roles"]["train"]["classification"].update(unexpected_entries=["part-00001.tmp.npz"]), "known"
    yield "needs_quarantine", lambda d: d["roles"]["train"]["classification"].update(resume_state="NEEDS_QUARANTINE"), "known"
    yield "shard_corrupt", lambda d: d["roles"]["val-calib"]["classification"]["shards"]["3"].update(state="CORRUPT"), "known"
    yield "shard_partial", lambda d: d["roles"]["val-calib"]["classification"]["shards"]["3"].update(state="PARTIAL"), "known"
    yield "quarantine_listed", lambda d: d["roles"]["test"]["classification"].update(quarantine_required=["0"]), "known"
    yield "shallow_classification", lambda d: d["roles"]["train"]["classification"].update(deep=False), "known"
    yield "counts_disagree", lambda d: d["roles"]["train"]["classification"]["counts"].update(COMMITTED=374), "known"
    yield "deletes_evidence", lambda d: d["roles"]["train"]["classification"].update(cleanup_may_delete_evidence=True), "known"
    yield "missing_admission", lambda d: d["roles"]["train"]["admissions"].pop(), "known"
    yield "duplicate_admission", lambda d: d["roles"]["train"]["admissions"].__setitem__(5, copy.deepcopy(d["roles"]["train"]["admissions"][4])), "known"
    yield "admission_wrong_fingerprint", lambda d: d["roles"]["train"]["admissions"][7].update(request_fingerprint=H("other")), "known"
    yield "admission_wrong_groups", lambda d: d["roles"]["train"]["admissions"][7].update(scenario_seeds=[1, 2, 3, 4]), "known"
    yield "admission_wrong_count", lambda d: d["roles"]["train"]["admissions"][7].update(n_samples=31), "known"
    yield "admission_wrong_role", lambda d: d["roles"]["train"]["admissions"][7].update(role="test"), "known"
    yield "admission_media_claim", lambda d: d["roles"]["train"]["admissions"][7].update(media_verified=True), "known"
    yield "admission_no_barrier", lambda d: d["roles"]["train"]["admissions"][7].update(barrier="none"), "known"
    yield "admission_other_directory", lambda d: d["roles"]["train"]["admissions"][7].update(directory_identity={"st_dev": 11, "st_ino": 1}), "known"
    yield "admission_hash_not_in_manifest", lambda d: d["roles"]["train"]["admissions"][7]["files"]["part-00007.npz"].update(sha256="0" * 64), "known"
    yield "admission_extra_file", lambda d: d["roles"]["train"]["admissions"][7]["files"].update({"extra.bin": {"bytes": 1, "sha256": "0" * 64}}), "known"
    yield "manifest_missing_shard", lambda d: d["roles"]["train"]["manifest"].update(shards=list(range(374))), "known"
    yield "manifest_tampered", lambda d: d["roles"]["train"]["manifest"]["entries"][0].update(sha256="0" * 64), "known"
    yield "manifest_none", lambda d: d["roles"]["train"].update(manifest=None), "known"
    yield "writable_files", lambda d: d["roles"]["train"]["immutability"].update(ok=False, findings=["part-00001.npz still has a write permission bit"]), "known"
    yield "worm_claimed", lambda d: d["roles"]["train"]["immutability"].update(worm_proven=True), "known"
    yield "path_substitution_root", lambda d: d["root"].update(path="/data/other/known"), "known"
    yield "path_substitution_role", lambda d: d["roles"]["train"]["directory"].update(path="/data/b2/known/val-calib"), "known"
    yield "unexpected_root_entry", lambda d: d.update(unexpected_root_entries=["test"]), "known"
    yield "extra_role", lambda d: d["roles"].update(**{"test-matched": copy.deepcopy(d["roles"]["test"])}), "known"
    yield "missing_role", lambda d: d["roles"].pop("val-select"), "known"
    yield "stale", lambda d: d.update(collected_at="2026-10-30T09:00:00+00:00"), "known"
    yield "future", lambda d: d.update(collected_at="2026-10-30T13:00:00+00:00"), "known"
    yield "wrong_schema", lambda d: d.update(schema="other"), "known"
    yield "wrong_stage_name", lambda d: d.update(stage="test"), "known"
    yield "extra_field", lambda d: d.update(extra=1), "known"
    yield "fingerprint_unbound", lambda d: d.update(request_fingerprint=None), "known"
    yield "fingerprint_differs", lambda d: d.update(request_fingerprint=H("else")), "known"
    yield "test_fingerprint_aliases_known", lambda d: [d.update(request_fingerprint=KNOWN_FP)], "test"
    yield "matched_fingerprint_aliases_test", lambda d: [d.update(request_fingerprint=FINGERPRINTS["test"])], "matched"


@pytest.mark.parametrize("label,change,stage", list(damage_cases()), ids=[x[0] for x in damage_cases()])
def test_every_kind_of_damaged_or_inconsistent_shard_evidence_fails_its_stage(world, label, change, stage):
    report = world.run("after_matched", shard_state=mutate_stage(world, stage, change))
    assert f"durability.{stage}" in failing(report), label
    assert report["document_conditions_met"] is False


def test_role_aliasing_and_bind_mounts_are_found(world):
    def alias(stage_name, role_a, role_b, other_stage=None):
        def shard_state(stage):
            doc = world.stage_doc(stage, "after_matched")
            if stage == stage_name:
                source = world.stage_doc(other_stage or stage, "after_matched")
                doc["roles"][role_b]["directory"] = copy.deepcopy(source["roles"][role_a]["directory"])
            return doc
        return shard_state
    report = world.run("after_matched", shard_state=alias("known", "train", "val-calib"))
    assert "isolation.roles" in failing(report)
    # the known stage's held-out `test` role and the test-only stage's `test` role must be different directories
    def same_name(stage):
        doc = world.stage_doc(stage, "after_matched")
        if stage == "test":
            doc["roles"]["test"]["directory"] = copy.deepcopy(world.stage_doc("known", "after_matched")["roles"]["test"]["directory"])
        return doc
    assert "isolation.roles" in failing(world.run("after_matched", shard_state=same_name))
    def root_alias(stage):
        doc = world.stage_doc(stage, "after_matched")
        if stage == "matched":
            doc["root"] = copy.deepcopy(world.stage_doc("test", "after_matched")["root"])
            doc["root"]["path"] = f"{WORKING}/matched"
        return doc
    assert "isolation.roles" in failing(world.run("after_matched", shard_state=root_alias))


def test_shard_adapter_misbehaviour_fails_closed(world):
    def raises(stage):
        raise OSError("disk unavailable")
    def not_json(stage):
        return {"schema": float("nan")}
    def gives_object(stage):
        return object()
    for adapter in (raises, not_json, gives_object, lambda stage: None, lambda stage: []):
        report = world.run("after_known", shard_state=adapter)
        assert {"durability.known", "durability.test", "durability.matched"} <= set(failing(report))


# ---- backup evidence -------------------------------------------------------------------------------------------------

def backup_cases():
    yield "same_device", lambda d: d["devices"]["backup"].update(filesystem_device=11)
    yield "observed_backup_differs", lambda d: d["devices"]["observed_backup"].update(physical_storage_id="disk-X")
    yield "same_physical_id", lambda d: d["devices"]["backup"].update(physical_storage_id="disk-A")
    yield "volatile_backup_root", lambda d: d["devices"]["backup"].update(root="/tmp/backup")
    yield "volatile_filesystem", lambda d: d["devices"]["backup"].update(filesystem_type="tmpfs")
    yield "unreviewed_filesystem", lambda d: d["devices"]["backup"].update(filesystem_type="vfat")
    yield "nested_roots", lambda d: d["devices"]["backup"].update(root="/data/b2/backup")
    yield "backup_too_small", lambda d: d["devices"]["backup"].update(capacity_bytes=5 * 10 ** 9, free_bytes=5 * 10 ** 9)
    yield "free_space_too_small", lambda d: d["devices"]["observed_backup"].update(free_bytes=1 * 10 ** 9)
    yield "working_too_small", lambda d: d["devices"]["working"].update(capacity_bytes=10 * 2 ** 30, free_bytes=10 * 2 ** 30)
    yield "wrong_host", lambda d: d["devices"]["backup"].update(host_id="other-host")
    yield "not_planned_root", lambda d: d["devices"]["working"].update(root="/data/elsewhere")
    yield "device_differs_from_inventory", lambda d: d["devices"]["working"].update(filesystem_device=33)
    yield "stale_measurement", lambda d: d["devices"]["working"].update(measured_at="2026-10-01T00:00:00+00:00")
    yield "missing_device_key", lambda d: d["devices"]["working"].pop("capacity_bytes")
    yield "missing_observation", lambda d: d["devices"].pop("observed_working")
    yield "restore_manifest_differs", lambda d: d["restores"]["train"].update(manifest_sha256="0" * 64)
    yield "restore_not_reverified", lambda d: d["restores"]["train"].update(restore_reverified=False)
    yield "restore_not_ok", lambda d: d["restores"]["train"].update(ok=False)
    yield "restore_missing_role", lambda d: d["restores"].pop("train")
    yield "dr_qualification_claimed", lambda d: d["restores"]["train"].update(disaster_recovery_qualified=True)
    yield "restore_file_count", lambda d: d["restores"]["train"].update(files=1)
    yield "copy_on_working_device", lambda d: d["copies"]["train"].update(st_dev=11)
    yield "copy_wrong_path", lambda d: d["copies"]["train"].update(path="/mnt/backup/b2/known/val-calib")
    yield "copy_missing", lambda d: d["copies"].pop("train")
    yield "stale", lambda d: d.update(collected_at="2026-10-30T08:00:00+00:00")
    yield "wrong_stage", lambda d: d.update(stage="test")
    yield "extra_field", lambda d: d.update(extra=1)


@pytest.mark.parametrize("label,change", list(backup_cases()), ids=[x[0] for x in backup_cases()])
def test_every_kind_of_unsafe_or_unverified_backup_fails(world, label, change):
    def backup_state(stage):
        doc = world.backup_doc(stage)
        if stage == "known":
            change(doc)
        return doc
    report = world.run("after_known", backup_state=backup_state)
    assert "backup.known" in failing(report), label
    assert report["document_conditions_met"] is False


def test_backup_adapter_failure_and_missing_adapter(world):
    def raises(stage):
        raise ConnectionError("backup host down")
    assert "backup.known" in failing(world.run("after_known", backup_state=raises))
    adapters = {k: v for k, v in world.adapters("after_known").items() if k != "backup_state"}
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=SCOPE, now=CLOCK, adapters=adapters)
    assert status(report)["backup.known"] == I.NOT_RUN and report["document_conditions_met"] is False


# ---- external journal ------------------------------------------------------------------------------------------------

def journal_state_with(world, boundary, change):
    def journal_state():
        doc = world.journal_doc(boundary)
        change(doc)
        return doc
    return journal_state


def reanchor(doc):
    head = doc["entries"][-1]
    doc["anchor"] = {"seq": head["seq"], "entry_sha256": head["entry_sha256"]}


def rebuild(doc, edit):
    """Edit the entry list then re-chain it, so the journal is internally valid but the *content* is wrong."""
    script = [(e["kind"], e["stage"], copy.deepcopy(e["data"])) for e in doc["entries"]]
    script = edit(script)
    entries, previous = [], L.GENESIS
    for index, (kind, stage, data) in enumerate(script):
        entry = L.make_entry(index, previous, f"2026-10-30T09:{index:02d}:00+00:00", kind, stage, data)
        entries.append(entry)
        previous = entry["entry_sha256"]
    doc["entries"] = entries
    reanchor(doc)


def journal_cases():
    yield "truncated", lambda d: (d["entries"].pop(), None)[1]
    yield "edited_entry", lambda d: d["entries"][3]["data"].update(manifests={"x": "y"})
    yield "rewritten_history", lambda d: rebuild(d, lambda s: s) or d.update(anchor={"seq": 3, "entry_sha256": "0" * 64})
    yield "no_anchor", lambda d: d.update(anchor=None)
    yield "location_unverified", lambda d: d["location"].update(ok=False)
    yield "independence_claimed", lambda d: d["location"].update(physical_independence_proven=True)
    yield "stale", lambda d: d.update(collected_at="2026-10-30T08:00:00+00:00")
    yield "extra_field", lambda d: d.update(extra=1)
    yield "wrong_schema", lambda d: d.update(schema="other")
    yield "empty", lambda d: d.update(entries=[], anchor=None)
    yield "different_plan", lambda d: rebuild(d, lambda s: [(s[0][0], s[0][1], dict(s[0][2], plan_fingerprint=H("other")))] + s[1:])
    yield "different_specification", lambda d: rebuild(d, lambda s: [(s[0][0], s[0][1], dict(s[0][2], specification_sha256=H("other")))] + s[1:])
    yield "different_record", lambda d: rebuild(d, lambda s: s[:1] + [(s[1][0], s[1][1], dict(s[1][2], record_sha256=H("other")))] + s[2:])
    yield "no_authorization_snapshot", lambda d: rebuild(d, lambda s: s[:1] + s[2:])
    yield "double_run_opened", lambda d: rebuild(d, lambda s: s[:1] + s[:1] + s[1:])
    yield "no_stage_completed", lambda d: rebuild(d, lambda s: [x for x in s if x[0] != "stage_completed"])
    yield "no_backup_verified", lambda d: rebuild(d, lambda s: [x for x in s if x[0] != "backup_verified"])
    yield "backup_before_completion", lambda d: rebuild(d, lambda s: s[:2] + [s[3], s[2]] + s[4:])
    yield "manifests_differ_from_tree", lambda d: rebuild(d, lambda s: [(k, st, dict(da, manifests={"train": "0" * 64}) if k == "stage_completed" else da) for k, st, da in s])
    yield "no_k17d_check", lambda d: rebuild(d, lambda s: [x for x in s if x[0] != "k17d_check"])
    yield "k17d_check_other_identity", lambda d: rebuild(d, lambda s: [(k, st, dict(da, identity_sha256="0" * 64) if k == "k17d_check" else da) for k, st, da in s])
    yield "halting_incident", lambda d: rebuild(d, lambda s: s + [("incident", "known", L.incident_data("shard_corruption", {"role": "train", "ordinal": 1, "expected_sha256": "a" * 64, "observed_sha256": "b" * 64}))])
    yield "unresolved_interruption", lambda d: rebuild(d, lambda s: s + [("incident", "known", L.incident_data("interruption", {"attempt": 1, "signal": "SIGTERM"}))])
    yield "stop_entry", lambda d: rebuild(d, lambda s: s + [("stop", None, {"reason": "operator"})])
    yield "unexpected_later_stage_entry", lambda d: rebuild(d, lambda s: s + [("stage_completed", "test", {"manifests": {}})])


@pytest.mark.parametrize("label,change", list(journal_cases()), ids=[x[0] for x in journal_cases()])
def test_every_kind_of_inconsistent_or_unanchored_journal_fails(world, label, change):
    report = world.run("after_known", journal_state=journal_state_with(world, "after_known", change))
    assert "journal.external" in failing(report), label
    assert report["document_conditions_met"] is False


def test_a_resolved_interruption_is_allowed_only_under_the_identical_request(world):
    def with_interruption(resume):
        def change(doc):
            def edit(script):
                identity = dict(script[0][2])
                tail = [("incident", "known", L.incident_data("interruption", {"attempt": 1, "signal": "SIGTERM"}))]
                if resume == "identical":
                    tail.append(("resume", "known", identity))
                elif resume == "different":
                    tail.append(("resume", "known", dict(identity, plan_fingerprint=H("different plan"))))
                return script + tail
            rebuild(doc, edit)
        return change
    ok = world.run("after_known", journal_state=journal_state_with(world, "after_known", with_interruption("identical")))
    assert status(ok)["journal.external"] == I.PASS
    for resume in ("none", "different"):
        report = world.run("after_known", journal_state=journal_state_with(world, "after_known", with_interruption(resume)))
        assert "journal.external" in failing(report), resume


def test_stage_binding_in_the_journal_must_match_the_shards_and_precede_the_stage(world):
    def change_fingerprint(doc):
        rebuild(doc, lambda s: [(k, st, dict(da, request_fingerprint=H("another")) if k == "stage_bound" else da) for k, st, da in s])
    assert "journal.external" in failing(world.run("after_test", journal_state=journal_state_with(world, "after_test", change_fingerprint)))

    def bound_late(doc):
        def edit(script):
            bound = [x for x in script if x[0] == "stage_bound"]
            rest = [x for x in script if x[0] != "stage_bound"]
            return rest + bound
        rebuild(doc, edit)
    assert "journal.external" in failing(world.run("after_test", journal_state=journal_state_with(world, "after_test", bound_late)))

    def bound_before_known_is_backed_up(doc):
        def edit(script):
            bound = [x for x in script if x[0] == "stage_bound" and x[1] == "test"]
            rest = [x for x in script if not (x[0] == "stage_bound" and x[1] == "test")]
            return rest[:2] + bound + rest[2:]
        rebuild(doc, edit)
    assert "journal.external" in failing(world.run("after_test", journal_state=journal_state_with(world, "after_test", bound_before_known_is_backed_up)))


def test_journal_bound_before_the_known_stage_completes_is_refused(world):
    def premature(doc):
        rebuild(doc, lambda s: s + [("k17d_check", None, {"identity_sha256": world.k17d["identity_sha256"]})])
    assert "journal.external" in failing(world.run("pre_launch", journal_state=journal_state_with(world, "pre_launch", premature)))


def test_journal_adapter_failure_and_stage_evidence_dependency(world):
    def raises():
        raise OSError("ledger volume unavailable")
    assert "journal.external" in failing(world.run("after_known", journal_state=raises))
    report = world.run("after_known", shard_state=lambda stage: (_ for _ in ()).throw(OSError("x")))
    assert status(report)["journal.external"] == I.FAIL


# ---- K17d metadata comparison ---------------------------------------------------------------------------------------

def k17d_cases():
    yield "synthetic_fixture", lambda d: d.update(metadata_status="SYNTHETIC_FIXTURE_ONLY", production_cross_verification_performed=False)
    yield "not_performed", lambda d: d.update(production_cross_verification_performed=False)
    yield "status_mismatch", lambda d: d.update(metadata_status="IDENTITY_MISMATCH")
    yield "headline_count", lambda d: d["counts"].update(headline=499)
    yield "co_feed_count", lambda d: d["counts"].update(co_feed_missing=34)
    yield "sensitivity_count", lambda d: d["counts"].update(sensitivity=466)
    yield "extra_count", lambda d: d["counts"].update(extra=1)
    yield "identity_differs", lambda d: d.update(identity_sha256="0" * 64)
    yield "request_differs", lambda d: d.update(request_fingerprint=H("other request"))
    yield "source_head_differs", lambda d: d.update(source_head="c" * 40)
    yield "observations_read", lambda d: d.update(observation_reads=1)
    yield "waveforms_synthesized", lambda d: d.update(waveform_synthesis_calls=1)
    yield "claims_authority", lambda d: d.update(execution_authorized=True)
    yield "verdict_changed", lambda d: d.update(verdict="GO")
    yield "d1_pristine", lambda d: d["d1_obligations"].update(existing_test_pristine=True)
    yield "d1_rows", lambda d: d["d1_obligations"]["exposure_excluded_groups"].update(test=500)
    yield "d1_ids", lambda d: d["d1_obligations"].update(exposed_test_ids=[])
    yield "d1_missing", lambda d: d.pop("d1_obligations")
    yield "no_clock", lambda d: d.pop("collected_at")
    yield "stale", lambda d: d.update(collected_at="2026-10-30T06:00:00+00:00")
    yield "wrong_schema", lambda d: d.update(schema="B2-E14-fabricated-k17d-identity/1")


@pytest.mark.parametrize("label,change", list(k17d_cases()), ids=[x[0] for x in k17d_cases()])
def test_a_k17d_disagreement_or_fabricated_comparison_fails_closed(world, label, change):
    def k17d_metadata():
        doc = copy.deepcopy(world.k17d)
        change(doc)
        return doc
    report = world.run("after_known", k17d_metadata=k17d_metadata)
    assert "k17d.metadata" in failing(report), label
    assert report["document_conditions_met"] is False


def test_k17d_is_not_applicable_before_the_known_stage_and_mandatory_after(world):
    assert status(world.run("pre_launch"))["k17d.metadata"] == I.NOT_RUN
    adapters = {k: v for k, v in world.adapters("after_known").items() if k != "k17d_metadata"}
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=SCOPE, now=CLOCK, adapters=adapters)
    assert status(report)["k17d.metadata"] == I.NOT_RUN and report["document_conditions_met"] is False


def test_a_real_e14_synthetic_report_cannot_satisfy_the_production_cross_check(world, tmp_path):
    import b2_e14_verify_metadata as M
    synthetic_status = "SYNTHETIC_FIXTURE_ONLY"
    report = copy.deepcopy(world.k17d)
    report.update(metadata_status=synthetic_status, production_cross_verification_performed=False)
    assert M.SYNTHETIC_SCHEMA and "k17d.metadata" in failing(world.run("after_known", k17d_metadata=lambda: report))


# ---- runtime stop conditions ----------------------------------------------------------------------------------------

def resource_cases():
    yield "wall", lambda d: d.update(elapsed_wall_s=36 * 3600.0)
    yield "core", lambda d: d.update(cpu_core_s=42 * 3600.0)
    yield "rss", lambda d: d.update(peak_rss_gib=2.5)
    yield "failed", lambda d: d.update(failed_attempts=3)
    yield "interruptions", lambda d: d.update(interruptions=21)
    yield "disk", lambda d: d.update(working_free_gib=25.2)
    yield "backup_space", lambda d: d.update(backup_free_gb=0.1)
    yield "slow_first_shard", lambda d: d.update(first_shard={"s_per_observation": 9.0, "observations": 32})
    yield "gate_unmeasured", lambda d: d.update(first_shard=None)
    yield "projection", lambda d: d.update(elapsed_wall_s=30 * 3600.0, observations_remaining=20000)
    yield "stale", lambda d: d.update(collected_at="2026-10-30T11:00:00+00:00")
    yield "malformed", lambda d: d.update(cpu_core_s=float("nan")) or d.pop("peak_rss_gib")
    yield "missing_field", lambda d: d.pop("working_free_gib")


@pytest.mark.parametrize("label,change", list(resource_cases()), ids=[x[0] for x in resource_cases()])
def test_resource_exhaustion_or_unknown_resources_stop_admission(world, label, change):
    def resource_state(stage):
        doc = copy.deepcopy(world.resource)
        change(doc)
        return doc
    report = world.run("after_known", resource_state=resource_state)
    assert status(report)["runtime.stop_conditions"] == I.FAIL, label
    assert report["document_conditions_met"] is False


def test_stop_conditions_wait_for_a_valid_authorization_and_see_the_next_stage(world):
    seen = []
    report = world.run("after_known", resource_state=lambda stage: (seen.append(stage), copy.deepcopy(world.resource))[1])
    assert seen == ["test"] and status(report)["runtime.stop_conditions"] == I.PASS
    seen.clear()
    world.run("pre_launch", resource_state=lambda stage: (seen.append(stage), copy.deepcopy(world.resource))[1])
    assert seen == ["known"]
    denied = world.run("after_known", signature_verifier=lambda *a: False)
    assert status(denied)["authorization.policy"] == I.FAIL and status(denied)["runtime.stop_conditions"] == I.BLOCKED


def test_resource_adapter_failure_fails_closed(world):
    def raises(stage):
        raise OSError("cannot read cgroup")
    assert status(world.run("after_known", resource_state=raises))["runtime.stop_conditions"] == I.FAIL


# ---- authorization is part of the boundary ---------------------------------------------------------------------------

def test_expired_revoked_or_unsigned_authorization_denies_the_boundary(world):
    report = world.run("after_known", now="2026-11-21T00:00:00+00:00")
    assert status(report)["authorization.policy"] == I.FAIL and report["document_conditions_met"] is False
    revoked = world.run("after_known", revocation_checker=lambda rid: {"revoked": True, "checked_at": CLOCK})
    assert status(revoked)["authorization.policy"] == I.FAIL
    unsigned = world.run("after_known", signature_verifier=lambda *a: False)
    assert status(unsigned)["authorization.policy"] == I.FAIL and unsigned["document_conditions_met"] is False


@pytest.mark.parametrize("scope", [{"gate": "full_gpu_training", "stages": ["known", "test", "matched"]}, {"gate": "gpu_probe", "stages": []},
                                   {"gate": "full_generation", "stages": ["known"]}, None])
def test_any_other_scope_fails_the_scope_condition(world, scope):
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=scope, now=CLOCK,
                                         adapters=world.adapters("after_known"))
    assert_closed(report)
    assert status(report)["authorization.scope"] == I.FAIL and report["document_conditions_met"] is False


# ---- consumer isolation ----------------------------------------------------------------------------------------------

def declaration(**change):
    value = copy.deepcopy(I.ALLOWED_CONSUMERS)
    value.update(change)
    return value


@pytest.mark.parametrize("label,value", [
    ("train_reads_known_test", declaration(train=[["known", "train"], ["known", "test"]])),
    ("train_reads_test_only", declaration(train=[["test", "test"]])),
    ("train_reads_matched", declaration(train=[["known", "train"], ["matched", "test-matched"]])),
    ("val_select_reads_held_out", declaration(val_select=[["known", "test"]])),
    ("calibration_reads_held_out", declaration(val_calib=[["known", "val-calib"], ["matched", "test-matched"]])),
    ("calibration_reads_train", declaration(val_calib=[["known", "train"]])),
    ("train_reads_val_calib", declaration(train=[["known", "train"], ["known", "val-calib"]])),
    ("empty_train", declaration(train=[])),
    ("missing_consumer", {"train": [["known", "train"]]}),
    ("extra_consumer", dict(declaration(), evaluation=[["known", "test"]])),
    ("malformed_entry", declaration(train=[["known"]])),
    ("not_a_list", declaration(train="known/train")),
    ("not_a_dict", [["known", "train"]]),
])
def test_test_and_matched_data_never_reach_training_selection_or_calibration(world, label, value):
    report = world.run("after_matched", consumer_declaration=lambda: value)
    assert status(report)["isolation.consumers"] == I.FAIL, label
    assert report["document_conditions_met"] is False


def test_the_exact_allowed_consumer_mapping_passes():
    assert I.check_consumer_isolation(I.ALLOWED_CONSUMERS) == []
    assert all(tuple(v) not in I.HELD_OUT for values in I.ALLOWED_CONSUMERS.values() for v in values)


# ---- no execution surface --------------------------------------------------------------------------------------------

def test_no_input_can_obtain_execution_and_the_refusals_hold(world):
    with pytest.raises(I.ExecutionUnavailable):
        I.deny_execution(world.plan, world.spec, world.ref, execute=True, approval=world.plan["authorization"])
    with mock.patch("subprocess.Popen", side_effect=AssertionError("a process was started")), \
            mock.patch("os.system", side_effect=AssertionError("a shell was started")), \
            mock.patch("os.execv", side_effect=AssertionError("exec")), mock.patch("os.fork", side_effect=AssertionError("fork")):
        for boundary in I.BOUNDARIES:
            assert_closed(world.run(boundary))
    assert G.sup.PRODUCTION_LAUNCH_ENABLED is False and G.sup.FIXTURE_MAX_GROUPS == 2


def test_a_changed_execution_boundary_is_reported_as_a_failure(world, monkeypatch):
    def evaluate():
        report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="pre_launch", requested_scope=copy.deepcopy(SCOPE), now=CLOCK)
        assert report["verdict"] == "NO-GO" and report["execution_permitted"] is False and report["document_conditions_met"] is False
        return next(c for c in report["conditions"] if c["id"] == I.PERMANENT)
    monkeypatch.setattr(G.sup, "PRODUCTION_LAUNCH_ENABLED", True)
    condition = evaluate()
    assert condition["status"] == I.FAIL and "PRODUCTION_LAUNCH_ENABLED" in condition["message"]
    monkeypatch.undo()
    monkeypatch.setattr(G.sup, "FIXTURE_MAX_GROUPS", 3)
    assert evaluate()["status"] == I.FAIL
    monkeypatch.undo()
    monkeypatch.setattr(G.e9, "guard_execution", lambda action: None)
    assert evaluate()["status"] == I.FAIL


# ---- review findings E16-02, E16-03, E16-04, E16-08 and the two untested guards ------------------------------------------

def forge(entries, index, **changes):
    """Change an entry's content and re-chain everything after it, bypassing make_entry's checks (a hostile writer)."""
    out, previous = [], L.GENESIS
    for position, entry in enumerate(entries):
        entry = copy.deepcopy(entry)
        if position == index:
            entry.update(changes)
        entry["prev_sha256"] = previous
        entry.pop("entry_sha256", None)
        entry["entry_sha256"] = L._digest(entry)
        previous = entry["entry_sha256"]
        out.append(entry)
    return out


def test_a_mislabelled_incident_cannot_make_a_halting_incident_resumable(world):
    entries = world.journal_entries("after_known")
    identity = dict(entries[0]["data"])
    corruption = {"incident": "shard_corruption", "action": "resume_only_under_identical_request",
                  "details": {"role": "train", "ordinal": 1, "expected_sha256": "a" * 64, "observed_sha256": "b" * 64}}
    tail = [{"kind": "incident", "stage": "known", "data": corruption}, {"kind": "resume", "stage": "known", "data": identity}]
    previous = entries[-1]["entry_sha256"]
    for index, item in enumerate(tail, start=len(entries)):
        entry = {"schema": L.SCHEMA_ENTRY, "seq": index, "prev_sha256": previous, "at": f"2026-10-30T10:{index:02d}:00+00:00", **item}
        entry["entry_sha256"] = L._digest(entry)
        entries.append(entry)
        previous = entry["entry_sha256"]
    doc = world.journal_doc("after_known", entries)
    report = world.run("after_known", journal_state=lambda: doc)
    assert "journal.external" in failing(report)
    assert "incident" in next(c["message"] for c in report["conditions"] if c["id"] == "journal.external")


def test_a_forged_content_change_is_visible_even_if_the_chain_is_rebuilt(world):
    entries = world.journal_entries("after_known")
    forged = forge(entries, 2, data={"manifests": {"train": "0" * 64}})
    doc = world.journal_doc("after_known", forged)
    doc["anchor"] = {"seq": entries[-1]["seq"], "entry_sha256": entries[-1]["entry_sha256"]}      # the independently kept anchor differs
    assert "journal.external" in failing(world.run("after_known", journal_state=lambda: doc))


@pytest.mark.parametrize("field,value", [("observation_reads", False), ("observation_reads", 0.0), ("waveform_synthesis_calls", False),
                                         ("waveform_synthesis_calls", 0.0), ("observation_reads", None)])
def test_a_k17d_report_must_state_integer_zero_reads(world, field, value):
    def k17d_metadata():
        doc = copy.deepcopy(world.k17d)
        doc[field] = value
        return doc
    assert "k17d.metadata" in failing(world.run("after_known", k17d_metadata=k17d_metadata))


@pytest.mark.parametrize("field,value", [("elapsed_wall_s", 10 ** 400), ("first_shard", {"s_per_observation": 1e308, "observations": 32})])
def test_overflowing_resource_readings_stop_and_still_yield_a_report(world, field, value):
    def resource_state(stage):
        doc = copy.deepcopy(world.resource)
        doc[field] = value
        return doc
    report = world.run("after_known", resource_state=resource_state)
    assert status(report)["runtime.stop_conditions"] == I.FAIL


def test_unserializable_details_degrade_a_condition_to_a_failure_instead_of_raising(world, monkeypatch):
    real = L.evaluate_stop_conditions

    def hostile(*args, **kwargs):
        result = real(*args, **kwargs)
        result["projections"] = {"projected_wall_hours": float("inf")}
        return result
    monkeypatch.setattr(L, "evaluate_stop_conditions", hostile)
    report = world.run("after_known")                              # must return a report, not raise ValueError
    assert status(report)["runtime.stop_conditions"] == I.FAIL and report["document_conditions_met"] is False
    monkeypatch.undo()
    monkeypatch.setattr(I.C, "canonical", lambda value: (_ for _ in ()).throw(ValueError("not strict")) if isinstance(value, dict) and "conditions" in value else json.dumps(value, sort_keys=True))
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK)
    assert report["verdict"] == "NO-GO" and report["document_conditions_met"] is False and report["execution_permitted"] is False


def test_held_out_roles_are_named_as_such_not_merely_as_a_wrong_mapping():
    for consumer in I.ALLOWED_CONSUMERS:
        for held_out in I.HELD_OUT:
            declaration = copy.deepcopy(I.ALLOWED_CONSUMERS)
            declaration[consumer] = declaration[consumer] + [list(held_out)]
            assert any("held-out" in problem for problem in I.check_consumer_isolation(declaration)), (consumer, held_out)


def rewrite_devices(value, devices):
    return rewrite(value, [], devices)


def test_a_consistently_shifted_device_record_still_must_equal_the_measured_host_inventory(world):
    def backup_state(stage):
        doc = world.backup_doc(stage)
        for key in ("working", "observed_working"):          # both records agree with each other but not with the approved inventory
            doc["devices"][key]["filesystem_type"] = "ext4"
        return doc
    report = world.run("after_known", backup_state=backup_state)
    assert "backup.known" in failing(report)
    assert "measured host inventory" in next(c["message"] for c in report["conditions"] if c["id"] == "backup.known")


def test_the_working_directory_must_sit_on_the_working_device(world):
    def shard_state(stage):
        doc = world.stage_doc(stage, "after_known")
        if stage == "known":
            doc["roles"]["train"] = rewrite_devices(doc["roles"]["train"], {11: 99})      # self-consistent evidence on another device
        return doc
    report = world.run("after_known", shard_state=shard_state)
    assert "durability.known" not in failing(report)
    assert "backup.known" in failing(report)
    assert "planned backup device" in next(c["message"] for c in report["conditions"] if c["id"] == "backup.known")


def test_a_deferred_request_fingerprint_may_not_equal_the_known_one_even_when_the_stage_is_self_consistent(world):
    def shard_state(stage):
        doc = world.stage_doc(stage, "after_test")
        if stage == "test":
            doc["request_fingerprint"] = KNOWN_FP
            for entry in doc["roles"].values():
                for admission in entry["admissions"]:
                    admission["request_fingerprint"] = KNOWN_FP
        return doc
    report = world.run("after_test", shard_state=shard_state)
    assert "durability.test" in failing(report)
    assert "request aliasing" in next(c["message"] for c in report["conditions"] if c["id"] == "durability.test")
