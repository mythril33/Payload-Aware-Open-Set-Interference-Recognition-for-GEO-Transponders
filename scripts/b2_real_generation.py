"""Real RF command adapter, reusing E13--E18 contracts and the owned process runner.

The development entry is deliberately known-only and capped at two groups per
role. It never creates a test role. Production is a separate API: E17 verifies
real signed authority and E16 verifies the supplied host/custody observations;
current committed gates and the missing pinned trust root refuse that API.
A byte-consistent local backup is reported as such, never as independent DR.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import b2_e14_launch_contract as C
import b2_e14_storage as S
import b2_e16_durability as D
import b2_e16_integration as I
import b2_e16_ledger as L
import b2_e16_policy as P
import b2_e17_evidence as E
from b2_e18_lifecycle import AnchorStore, ReplayStore
import b2_production_preflight as pre
import b2_production_supervisor as sup

DEVELOPMENT_ROLES = ("train", "val-select", "val-calib")


class GenerationRefused(RuntimeError):
    pass


def _publish_json(directory, name, value):
    fds = D._chain(directory)
    try:
        S._publish(fds[-1], name, S._canonical(value))
    finally:
        D._close(fds)


def _copy_verified(source, target, names):
    """No-clobber durable copy through the existing no-follow storage primitives."""
    target.mkdir(exist_ok=True)
    src, dst = D._chain(source), D._chain(target)
    try:
        for name in names:
            raw = D._read_regular(src[-1], name, D.MAX_PAYLOAD_BYTES, keep=True)[3]
            if name in os.listdir(dst[-1]):
                if D._read_regular(dst[-1], name, D.MAX_PAYLOAD_BYTES, keep=True)[3] != raw:
                    raise GenerationRefused("existing backup differs; preserve and investigate")
            else:
                S._publish(dst[-1], name, raw)
    finally:
        D._close(src)
        D._close(dst)


def _metadata_hashes(directory, names):
    fds = D._chain(directory)
    try:
        return {name: D._read_regular(fds[-1], name, D.MAX_METADATA_BYTES)[0] for name in names}
    finally:
        D._close(fds)


class DurableStage:
    """Actual file admission, anchored E16 journal, backup and restart verification.

    This port does not fabricate storage identities or claim DR qualification.
    The stage inventory and request digest are supplied by the sealed request.
    """
    def __init__(self, root, backup, journal, anchors, expected, identity, *, stage="known"):
        self.root, self.backup = Path(root), Path(backup)
        self.expected, self.identity, self.stage = expected, identity, stage
        self.ledger, self.anchors = L.Ledger(journal), AnchorStore(anchors)
        self.admitted = {}
        self.entries = []
        if (Path(journal) / L.LEDGER_NAME).exists():
            if self.anchors.latest() is None:
                raise GenerationRefused("retained journal anchor missing")
            report = L.verify_chain(self.ledger.read(), expected_head=self.anchors.latest())
            if not report["ok"] or not report["entries"] or report["entries"][0]["data"] != identity:
                raise GenerationRefused("journal identity/integrity mismatch")
            self.entries = report["entries"]
            if any(e["kind"] == "stop" for e in self.entries):
                raise GenerationRefused("a retained stop entry ends this authorization")
            for entry in self.entries:
                if entry["kind"] == "shard_admitted" and entry["stage"] == stage:
                    self.admitted[(entry["data"]["role"], entry["data"]["ordinal"])] = entry["data"]["admission"]
        else:
            if self.anchors.latest() is not None:
                raise GenerationRefused("journal missing behind retained anchor")
            self.append("run_opened", identity)
        self.reverify()

    def append(self, kind, data):
        entry = self.ledger.append(kind, None if kind in ("run_opened", "authorization_snapshot", "k17d_check") else self.stage, data, sup.utc_now(), expected_head=self.anchors.latest())
        self.anchors.record({"seq": entry["seq"], "entry_sha256": entry["entry_sha256"]})
        self.entries.append(entry)

    def reverify(self):
        for role, expected in self.expected.items():
            directory = self.root / role
            if not directory.exists():
                if any(r == role for r, _ in self.admitted):
                    raise GenerationRefused("previously admitted role directory is missing")
                continue
            report = D.classify_directory(directory, expected)
            if report["resume_state"] not in ("NOT_STARTED", "RESUMABLE", "COMPLETE"):
                # The E16 note preserves evidence in place; never repair/regenerate.
                raise GenerationRefused("unsafe shard state; preserve evidence: " + report["resume_state"])
            for ordinal in expected:
                key = (role, ordinal)
                if key in self.admitted:
                    observed = D.verify_shard(directory, ordinal, expected[ordinal])
                    if any(observed[k] != self.admitted[key].get(k) for k in observed):
                        raise GenerationRefused("previously admitted shard changed")

        completed = [e for e in self.entries if e["stage"] == self.stage and e["kind"] == "stage_completed"]
        backed_up = any(e["stage"] == self.stage and e["kind"] == "backup_verified" for e in self.entries)
        if completed:
            previous = completed[-1]["data"]
            if _metadata_hashes(self.root, previous["root_files_sha256"]) != previous["root_files_sha256"]:
                raise GenerationRefused("completed dataset metadata changed or disappeared")
            if backed_up and _metadata_hashes(self.backup, previous["root_files_sha256"]) != previous["root_files_sha256"]:
                raise GenerationRefused("verified backup metadata changed or disappeared")
            if backed_up:
                fds = D._chain(self.ledger.directory)
                try:
                    for role, name in previous["manifest_files"].items():
                        expected_name = f"manifest-{self.stage}-{role}-{previous['manifests'][role]}.json"
                        if name != expected_name:
                            raise GenerationRefused("retained manifest name differs from digest")
                        manifest = D._strict_json(D._read_regular(fds[-1], name, D.MAX_METADATA_BYTES, keep=True)[3])
                        D._manifest_check(manifest)
                        if manifest["manifest_sha256"] != previous["manifests"][role]:
                            raise GenerationRefused("retained manifest digest changed")
                        D.verify_restore(self.backup / role, manifest, self.expected[role])
                finally:
                    D._close(fds)

    def admit_ready(self):
        for role, expected in self.expected.items():
            directory = self.root / role
            for ordinal, shard in expected.items():
                key = (role, ordinal)
                if key in self.admitted or not (directory / D.shard_names(ordinal)[2]).exists():
                    continue
                admission = D.admit_shard(directory, ordinal, shard)
                self.append("shard_admitted", {"role": role, "ordinal": ordinal, "admission": admission})
                self.admitted[key] = admission
        return sum(x["n_samples"] for x in self.admitted.values())

    def finish(self):
        self.admit_ready()
        if len(self.admitted) != sum(len(v) for v in self.expected.values()):
            raise GenerationRefused("generator exited without every planned admitted shard")
        self.reverify()
        manifests, restores = {}, {}
        self.backup.mkdir(exist_ok=True)
        for role, expected in self.expected.items():
            manifest = D.build_manifest(self.root / role, expected)
            _copy_verified(self.root / role, self.backup / role, [x["name"] for x in manifest["entries"]])
            for name in (x["name"] for x in manifest["entries"]):
                os.chmod(self.root / role / name, 0o444)
            restores[role] = D.verify_restore(self.backup / role, manifest, expected)
            manifests[role] = manifest
        # Include request/calibration/final manifest so the backup can load as a dataset.
        root_names = ["request.json", "calibration.json", "receiver_calibration.npz", "manifest.json"]
        top = _metadata_hashes(self.root, root_names)
        _copy_verified(self.root, self.backup, root_names)
        if _metadata_hashes(self.root, root_names) != top or _metadata_hashes(self.backup, root_names) != top:
            raise GenerationRefused("dataset metadata changed across durable backup")
        if not any(e["stage"] == self.stage and e["kind"] == "stage_completed" for e in self.entries):
            manifest_files = {}
            fds = D._chain(self.ledger.directory)
            try:
                for role, manifest in manifests.items():
                    name = f"manifest-{self.stage}-{role}-{manifest['manifest_sha256']}.json"
                    manifest_files[role] = name
                    raw = S._canonical(manifest)
                    if name in os.listdir(fds[-1]):
                        if D._read_regular(fds[-1], name, D.MAX_METADATA_BYTES, keep=True)[3] != raw:
                            raise GenerationRefused("retained manifest file changed")
                    else:
                        S._publish(fds[-1], name, raw)
            finally:
                D._close(fds)
            self.append("stage_completed", {"manifests": {r: m["manifest_sha256"] for r, m in manifests.items()},
                "manifest_files": manifest_files, "root_files_sha256": top})
        if not any(e["stage"] == self.stage and e["kind"] == "backup_verified" for e in self.entries):
            self.append("backup_verified", {"manifests": {r: m["manifest_sha256"] for r, m in manifests.items()}, "restores": restores, "independent_device_verified": False})
        return {"manifests": manifests, "restores": restores, "root_files_sha256": top,
                "independent_device_verified": False, "dr_qualified": False}


def _roots(work, backup, journal, anchors):
    paths = [Path(x).absolute() for x in (work, backup, journal, anchors)]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1:]):
        raise GenerationRefused("work, backup, journal and anchor roots must be disjoint")
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        D._close(D._chain(path))
    return paths


def _known_request(groups):
    from geosim.b2_dataset import _request, _fingerprint, B2Config
    from geosim.cancellation import CancellationConfig
    config = B2Config.from_file(REPO / "configs/b2_base.json")
    cancel = CancellationConfig(**pre._read_json(REPO / "configs/cancellation.json"))
    request = _request(config, list(DEVELOPMENT_ROLES), groups, 1, cancel)
    expected = {}
    for role, seeds in request["scenario_groups"].items():
        expected[role] = {i: {"role": role, "scenario_seeds": [seed], "n_samples": 8,
                              "request_fingerprint": _fingerprint(request)} for i, seed in enumerate(seeds)}
    return request, expected


def run_development(work, backup, journal, anchors, *, groups=1):
    """Run actual RF generation for development roles only, then durably admit/copy.

    Repeating the identical command verifies and reuses a complete run. Unsafe
    partial shards refuse; complete shards are re-admitted through E16 on restart.
    No user option can remove the two-group cap or add a held-out role.
    """
    if type(groups) is not int or not 1 <= groups <= 2:
        raise GenerationRefused("development generation is capped at 1..2 groups per role")
    source = D.source_identity_impact(REPO)
    if not source["unchanged"]:
        raise GenerationRefused("accepted GEO generator identity changed; D-8 reacceptance required")
    work, backup, journal, anchors = _roots(work, backup, journal, anchors)
    lock = os.open(work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        request, expected = _known_request(groups)
        root = work / "known"
        identity = {"schema": "B2-real-development-generation/1", "scope": "DEVELOPMENT_ONLY",
                    "request": request, "generator_identity": source,
                    "adapter_sha256": pre._file_hash(Path(__file__)),
                    "supervisor_sha256": pre._file_hash(HERE / "b2_production_supervisor.py")}
        durable = DurableStage(root, backup / "known", journal, anchors, expected, identity)
        if not (root / "manifest.json").exists():
            argv = [sys.executable, "-m", "geosim.b2_dataset", "--out", str(root),
                    "--config", str(REPO / "configs/b2_base.json"), "--cancellation", str(REPO / "configs/cancellation.json"),
                    "--roles", *DEVELOPMENT_ROLES, "--limit-groups", str(groups), "--groups-per-shard", "1"]
            env = dict(os.environ, PYTHONPATH=str(REPO / "src"), OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
            attempt = sum(e["kind"] == "resume" for e in durable.entries) + 1
            durable.append("resume", {"attempt": attempt, "scope": "DEVELOPMENT_ONLY"})
            def poll(elapsed):
                durable.admit_ready()
                if shutil.disk_usage(work).free < 2 ** 30 or shutil.disk_usage(backup).free < 2 ** 30:
                    return "disk_floor"
                return None
            outcome = sup.run_child(argv, cwd=REPO, env=env, log_path=work / f"generator-{attempt}.log",
                                    timeout_s=1800, cpu_budget_s=3600, rss_limit_kib=4 * 2 ** 20,
                                    grace_s=5, interrupted=lambda: False, on_poll=poll)
            if outcome["exit_code"] != 0 or outcome["reason"] != "exited" or sup.rss_exceeded(outcome, 4 * 2 ** 20):
                durable.append("stop", {"outcome": outcome})
                raise GenerationRefused("real generator failed; preserve artifacts and inspect log")
        else:
            outcome = {"reused_complete_generation": True}
        report = durable.finish()
        return {"schema": "B2-real-development-exercise/1", "data_root": str(root), "roles": list(DEVELOPMENT_ROLES),
                "observations": 24 * groups, "groups_per_role": groups, "outcome": outcome, **report,
                "journal_head": durable.anchors.latest(), "production_execution_permitted": False,
                "protected_observation_reads": 0, "benchmark_complete": False}
    finally:
        os.close(lock)


def sealed_stage_argv(plan, specification, stage):
    """Command built only from an exactly recomputed E14 specification (no argv input)."""
    plan = C._check_plan(plan)
    if specification != C.build_specification(plan) or stage not in I.STAGES:
        raise GenerationRefused("stage/specification differs from sealed plan")
    options = plan["stages"][stage]["options"]
    root = Path(plan["working"]["root"])
    argv = [sys.executable, "-m", sup.MODULES[stage], "--out", str(root / stage),
            "--config", str(REPO / options["config"]), "--cancellation", str(REPO / options["cancellation"]),
            "--groups-per-shard", str(options["groups_per_shard"])]
    if stage != "known":
        argv += ["--known", str(root / "known")]
    return argv


def _production_authority(plan, *, reference, evidence, replay_directory, adapters):
    """Recompute real E17 and E16 checks. Supplied verdict dictionaries are never authority.

    The host/custody adapters must return measured E16 evidence; fabricated E18
    synthetic ports cannot qualify this API. Current gates and trust root close it.
    """
    gates = pre._read_json(REPO / pre.GATES_PATH)
    memo = pre._read_json(REPO / pre.MEMO_PATH)
    ok, reasons = sup.authorization(gates, memo)
    if not ok:
        raise GenerationRefused("DR-04 remains closed: " + "; ".join(reasons))
    replay = ReplayStore(replay_directory)
    challenge, sequence = replay.begin()
    now = sup.utc_now()
    try:
        trusted = E.evaluate_trusted_authorization(plan, reference, repo=REPO, evidence=evidence(challenge, sequence, now),
                 now=now, challenge=challenge, revocation_floor=sequence, ci_floor=sequence)
    finally:
        replay.finish(challenge, sequence)
    if not trusted["ok"] or trusted["state"] != P.STATE_VALID or trusted.get("evidence_scope") != "PRODUCTION_ROOT":
        raise GenerationRefused("real E17 authority refused: " + trusted.get("status", "unknown"))
    raw = reference["record_texts"][plan["authorization"]["record"]].encode()
    block = P._blocks_of(raw.decode(), P.SCHEMA_BLOCK)[0]
    concrete = dict(adapters)
    concrete.update({
        "signature_verifier": lambda sha, principal, signature: sha == hashlib.sha256(raw).hexdigest()
            and principal == reference["scientific_protocol"]["approved_by"] and signature == block["signature"],
        "ancestry_checker": lambda reviewed, approval: {
            "is_ancestor": trusted["lineage"]["is_ancestor"] and reviewed == block["reviewed_code_commit"]
                and approval == plan["source"]["git_commit"], "changed_paths": trusted["lineage"]["changed_paths"]},
        "revocation_checker": lambda grant: {"revoked": grant != block["revocation_id"], "checked_at": trusted["revocation"]["checked_at"]},
    })
    return trusted, concrete


def require_production_admission(plan, specification, *, reference, evidence, replay_directory, boundary, adapters):
    trusted, concrete = _production_authority(plan, reference=reference, evidence=evidence,
                                             replay_directory=replay_directory, adapters=adapters)
    report = I.evaluate_release_boundary(plan, reference, specification, boundary=boundary,
                 requested_scope=P.GRANTED_SCOPE, now=sup.utc_now(), adapters=concrete)
    if not report["document_conditions_met"]:
        raise GenerationRefused("E13--E18 host/durability/journal/backup boundary refused")
    return trusted, report




def _retained_stage_admission(entries, stage):
    """Recover a durable admission even if the process died before attempt-start."""
    retained = [e for e in entries if e["stage"] == stage and e["kind"] == "boundary_check"
                and "admission_report_file" in e["data"]]
    attempted = any(e["stage"] == stage and e["kind"] == "resume" for e in entries)
    if not retained and not attempted:
        return None
    if len(retained) != 1:
        raise GenerationRefused("no unique retained admission boundary for recovery")
    return retained[0]


def run_production_stage(plan, specification, *, reference, evidence, replay_directory,
                         boundary, adapters, journal, anchors, resource_source):
    # Authorization is checked before touching declared production paths.
    ok, reasons = sup.authorization(pre._read_json(REPO / pre.GATES_PATH), pre._read_json(REPO / pre.MEMO_PATH))
    if not ok:
        raise GenerationRefused("DR-04 remains closed: " + "; ".join(reasons))
    custody = [Path(plan["working"]["root"]), Path(plan["backup"]["root"]), Path(journal), Path(anchors), Path(replay_directory)]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(custody) for b in custody[i + 1:]):
        raise GenerationRefused("production work/backup/journal/anchors/replay custody roots overlap")
    for path in custody:
        if not path.is_absolute() or any(path == Path(p) or Path(p) in path.parents for p in L.VOLATILE_PREFIXES):
            raise GenerationRefused("production custody requires absolute persistent roots")
        D._close(D._chain(path))
    fd = os.open(plan["working"]["root"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    caught = [None]
    old = {}
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in (signal.SIGINT, signal.SIGTERM):
            old[name] = signal.signal(name, lambda number, frame: caught.__setitem__(0, signal.Signals(number).name))
        return _run_production_stage(plan, specification, reference=reference, evidence=evidence,
            replay_directory=replay_directory, boundary=boundary, adapters=adapters,
            journal=journal, anchors=anchors, resource_source=resource_source, caught=caught)
    finally:
        for name, handler in old.items():
            signal.signal(name, handler)
        os.close(fd)


def _run_production_stage(plan, specification, *, reference, evidence, replay_directory,
                         boundary, adapters, journal, anchors, resource_source, caught):
    """Run one sealed real stage after independent generation authorization.

    Host-specific evidence/custody and cumulative resource observations are
    required ports. No production authority/host is configured in this checkout.
    This API cannot be activated by the bounded command-line entry.
    """
    trusted, concrete = _production_authority(plan, reference=reference, evidence=evidence,
                    replay_directory=replay_directory, adapters=adapters)
    stage = I.NEXT_STAGE[boundary]
    if stage is None:
        raise GenerationRefused("all stages already complete")
    # Bind this adapter itself to the exact reviewed Git object, not just geosim.
    import b2_e17_git as Git
    raw = Git.read_blob(REPO, plan["source"]["git_commit"], "scripts/b2_real_generation.py")
    if hashlib.sha256(raw).hexdigest() != pre._file_hash(Path(__file__)):
        raise GenerationRefused("execution adapter differs from reviewed source commit")
    work, backup = Path(plan["working"]["root"]), Path(plan["backup"]["root"])
    if not L.check_independent_location(journal, work, backup)["ok"]:
        raise GenerationRefused("external journal is not independently located")
    argv = sealed_stage_argv(plan, specification, stage)
    expected = {}
    layout = next(s for s in specification["stages"] if s["name"] == stage)
    # The later-stage request is derived from verified known metadata, not a
    # caller-provided fingerprint and not observation arrays.
    fingerprint = plan["source"]["known_request_fingerprint"]
    if stage != "known":
        from geosim.b2_dataset import _fingerprint, _stage, B2Config
        from geosim.cancellation import CancellationConfig
        import importlib
        known = pre._read_json(work / "known" / "manifest.json")
        if known["request_fingerprint"] != fingerprint:
            raise GenerationRefused("known request changed before dependent stage")
        config = B2Config.from_file(REPO / "configs/b2_base.json")
        cancel = CancellationConfig(**pre._read_json(REPO / "configs/cancellation.json"))
        binding = {"known_protocol": _stage(known["request"])[0], "known_data_fingerprint": _fingerprint(known),
                   "known_request_fingerprint": fingerprint, "known_calibration": known["calibration"]}
        if stage == "test":
            binding["known_test_groups"] = known["roles"]["test"]["scenario_seeds"]
        else:
            binding["known_roles"] = sorted(known["roles"])
        module = importlib.import_module(sup.MODULES[stage])
        fingerprint = _fingerprint(module._request(config, None, 4, cancel, binding))
    for shard in layout["shards"]:
        role = shard["role"]
        expected.setdefault(role, {})[shard["ordinal"]] = {"role": role, "scenario_seeds": shard["groups"],
                    "n_samples": shard["observations"], "request_fingerprint": fingerprint}
    identity = {"schema": "B2-real-production-generation/1", "plan_fingerprint": plan["plan_fingerprint"],
                "specification_sha256": specification["specification_sha256"]}
    durable = DurableStage(work / stage, backup / stage, journal, anchors, expected, identity, stage=stage)
    if not any(e["kind"] == "authorization_snapshot" for e in durable.entries):
        durable.append("authorization_snapshot", {"record_sha256": plan["authorization"]["record_sha256"]})
    def journal_state():
        verified = L.verify_chain(durable.ledger.read(), expected_head=durable.anchors.latest())
        if not verified["ok"]:
            raise GenerationRefused("actual external journal verification failed")
        return {"schema": I.SCHEMA_JOURNAL, "collected_at": sup.utc_now(), "entries": verified["entries"],
                "anchor": durable.anchors.latest(), "location": L.check_independent_location(journal, work, backup)}
    concrete["journal_state"] = journal_state
    retained = _retained_stage_admission(durable.entries, stage)
    restarting = retained is not None
    if restarting:
        data = retained["data"]
        fds = D._chain(journal)
        try:
            raw = D._read_regular(fds[-1], data["admission_report_file"], C.MAX_BYTES, keep=True)[3]
        finally:
            D._close(fds)
        prior = D._strict_json(raw)
        if hashlib.sha256(raw).hexdigest() != data["admission_report_sha256"] or prior.get("document_conditions_met") is not True:
            raise GenerationRefused("retained admission boundary changed or was not passing")
        # The anchored journal prefix is historical evidence of initial admission,
        # not a claim that current partial files are NOT_STARTED. Fresh E16
        # source/host/predecessor/backup/resource conditions are all rechecked.
        prefix = durable.entries[:durable.entries.index(retained)]
        prefix_head = data["boundary_prefix_head"]
        if not L.verify_chain(b"".join((L.canonical(e) + "\n").encode() for e in prefix), expected_head=prefix_head)["ok"]:
            raise GenerationRefused("retained admission prefix integrity failed")
        anchor_path = Path(anchors) / f"anchor-{prefix_head['seq']:08d}.json"
        if pre._read_json(anchor_path) != prefix_head:
            raise GenerationRefused("retained admission prefix anchor missing")
        def original_boundary_journal():
            doc = journal_state()
            return dict(doc, entries=prefix, anchor=prefix_head)
        concrete["journal_state"] = original_boundary_journal
    report = I.evaluate_release_boundary(plan, reference, specification, boundary=boundary,
                 requested_scope=P.GRANTED_SCOPE, now=sup.utc_now(), adapters=concrete)
    if restarting:
        required = [c for c in report["conditions"] if c["applicable"] and c["id"] not in
                    (I.PERMANENT, f"durability.{stage}")]
        if not required or any(c["status"] != I.PASS for c in required):
            raise GenerationRefused("fresh E16 source/host/predecessor/resource recovery conditions refused")
        durable.reverify()
        durable.admit_ready()
    elif not report["document_conditions_met"]:
        raise GenerationRefused("E13--E18 measured boundary refused")
    else:
        raw = S._canonical(report)
        name = f"admission-{stage}-{hashlib.sha256(raw).hexdigest()}.json"
        _publish_json(journal, name, report)
        durable.append("boundary_check", {"admission_report_file": name, "admission_report_sha256": hashlib.sha256(raw).hexdigest(),
                                         "boundary_prefix_head": durable.anchors.latest()})
    if stage != "known" and not any(e["stage"] == stage and e["kind"] == "stage_bound" for e in durable.entries):
        durable.append("stage_bound", {"request_fingerprint": fingerprint})
    durable.append("boundary_check", {"boundary": boundary, "document_conditions_met": True})
    attempt = sum(e["kind"] == "resume" and e["stage"] == stage for e in durable.entries) + 1
    durable.append("resume", dict(identity, attempt=attempt, process_status="STARTING"))
    ceilings = plan["ceilings"]
    pid = [None]
    last_refresh = [time.monotonic()]
    def poll(elapsed):
        durable.admit_ready()
        # resource_source owns cumulative counters across restarts, under E16.
        observation = resource_source(stage, pid[0], elapsed, durable.admitted)
        now = sup.utc_now()
        authorization = {"expires_at": plan["authorization"]["expires_at"], "revoked": False,
                         "revocation_id": P._blocks_of(reference["record_texts"][plan["authorization"]["record"]], P.SCHEMA_BLOCK)[0]["revocation_id"]}
        stop = L.evaluate_stop_conditions(observation, ceilings, authorization, now=now, stage=stage, timing=plan["timing"])
        if stop["decision"] == "STOP":
            durable.append("stop", {"stop_evaluation": stop})
            return "e16_stop"
        if time.monotonic() - last_refresh[0] >= 60:
            replay = ReplayStore(replay_directory)
            challenge, seq = replay.begin()
            try:
                fresh = E.evaluate_trusted_authorization(plan, reference, repo=REPO,
                    evidence=evidence(challenge, seq, now), now=now, challenge=challenge,
                    revocation_floor=seq, ci_floor=seq)
            finally:
                replay.finish(challenge, seq)
            if not fresh["ok"] or fresh["state"] != P.STATE_VALID:
                return "authorization_refresh_refused"
            last_refresh[0] = time.monotonic()
        return None
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"), OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2")
    outcome = sup._run_owned_child(argv, cwd=REPO, env=env,
                log_path=work / f"{stage}-{time.time_ns()}.log", timeout_s=ceilings["wall_hours"] * 3600,
                cpu_budget_s=ceilings["core_hours"] * 3600, rss_limit_kib=ceilings["max_rss_gib"] * 2 ** 20,
                grace_s=ceilings["grace_s"], interrupted=lambda: caught[0] is not None, on_poll=poll,
                on_start=lambda process: pid.__setitem__(0, process),
                on_heartbeat=lambda reading: durable.append("boundary_check", {"attempt": attempt, "heartbeat": reading}), heartbeat_s=30)
    # A fast final shard can finish between polls: enforce the post-wait4 result.
    # Persist wait4 counters before the resource port rebuilds cumulative usage.
    durable.append("boundary_check", {"attempt": attempt, "outcome": outcome})
    last_refresh[0] = time.monotonic() - 61
    final_stop = poll(outcome["elapsed_s"])
    if caught[0] is not None:
        durable.append("incident", L.incident_data("interruption", {"attempt": attempt, "signal": caught[0]}))
        raise GenerationRefused("interrupted production stage; resume only under identical identity")
    if (outcome["exit_code"] != 0 or outcome["reason"] != "exited" or final_stop
            or sup.rss_exceeded(outcome, ceilings["max_rss_gib"] * 2 ** 20)
            or outcome["cpu_user_s"] + outcome["cpu_sys_s"] >= ceilings["core_hours"] * 3600):
        durable.append("stop", {"outcome": outcome})
        raise GenerationRefused("production stage stopped; preserve evidence")
    result = durable.finish()
    if stage == "known" and not any(e["kind"] == "k17d_check" for e in durable.entries):
        import b2_e14_verify_metadata as K
        request = pre._read_json(work / "known" / "request.json")
        check = K.verify_production_metadata(work / "known", binding={"schema": K.BINDING_SCHEMA,
            "source_head": plan["source"]["git_commit"], "request": request,
            "request_fingerprint": plan["source"]["known_request_fingerprint"]})
        durable.append("k17d_check", {"identity_sha256": check["identity_sha256"]})
    return {"outcome": outcome, **result, "benchmark_complete": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--groups", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_development(args.work, args.backup, args.journal, args.anchors, groups=args.groups), indent=2, allow_nan=False))
    except (GenerationRefused, OSError, ValueError) as error:
        parser.exit(2, f"REFUSED: {error}\n")


if __name__ == "__main__":
    main()
