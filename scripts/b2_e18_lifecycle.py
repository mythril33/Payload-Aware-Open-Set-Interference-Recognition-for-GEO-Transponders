"""E18 synthetic executor lifecycle: a production-executor *candidate* that can only move fabricated bytes.

The controller connects the existing contracts instead of re-implementing them: E13 plan validation and E14 sealed
specification (through E16's boundary report), E16 durable-admission barrier / external ledger / stop evaluator, and E17
signature, Git-lineage, revocation and CI-snapshot verification. A correctly shaped document is not an approval and a valid
approval is not permission to execute: this module has **no production-running state**, accepts no boolean, environment
variable or signed-looking record as permission, and its only entry for real work, ``production_gate``, can only end BLOCKED.

What the controller really does (synthetic ports only): verify trusted evidence, check admission at a stage boundary, ask an
injected *bounded* shard producer for one planned shard at a time, publish it descriptor-last, admit it through the E16
barrier, supervise resources with the E16 stop evaluator, verify the stage, copy it to a backup root and re-verify the copy,
and journal every step to an externally anchored hash-chained ledger. The journal is the durable state: a restarted process
rebuilds from it and from the bytes on disk (``recover``), or refuses. Fabricated signing keys, relabelling of the synthetic
workspace to the plan's declared identities and fabricated device/K17d attestations live in ``b2_e18_synthetic`` and in the
tests, never here. Nothing in this module imports a generator, spawns a process or reads the environment.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e13_generation_plan as G
import b2_e14_launch_contract as C
import b2_e14_storage as S
import b2_e16_durability as D
import b2_e16_integration as I
import b2_e16_ledger as L
import b2_e16_policy as P
import b2_e17_evidence as E
import b2_e17_git as Git

SCHEMA_SUMMARY = "B2-E18-lifecycle-summary/1"
SCHEMA_PRODUCTION_GATE = "B2-E18-production-gate/1"
STATES = ("PREPARED", "EVIDENCE_VERIFIED", "ADMISSION_CHECKED", "SYNTHETIC_STAGE_RUNNING", "SYNTHETIC_STAGE_VERIFIED",
          "SYNTHETIC_BACKUP_VERIFIED", "SYNTHETIC_STAGE_COMPLETE", "BLOCKED", "STOPPED", "QUARANTINED")
TRANSITIONS = {
    "PREPARED": {"EVIDENCE_VERIFIED", "BLOCKED", "STOPPED", "QUARANTINED"},
    "EVIDENCE_VERIFIED": {"ADMISSION_CHECKED", "BLOCKED", "STOPPED", "QUARANTINED"},
    "ADMISSION_CHECKED": {"SYNTHETIC_STAGE_RUNNING", "BLOCKED", "STOPPED", "QUARANTINED"},
    "SYNTHETIC_STAGE_RUNNING": {"SYNTHETIC_STAGE_VERIFIED", "STOPPED", "QUARANTINED"},
    "SYNTHETIC_STAGE_VERIFIED": {"SYNTHETIC_BACKUP_VERIFIED", "STOPPED", "QUARANTINED"},
    "SYNTHETIC_BACKUP_VERIFIED": {"SYNTHETIC_STAGE_COMPLETE", "BLOCKED", "STOPPED", "QUARANTINED"},
    "SYNTHETIC_STAGE_COMPLETE": {"PREPARED", "STOPPED", "QUARANTINED"},
    "BLOCKED": {"PREPARED", "EVIDENCE_VERIFIED", "ADMISSION_CHECKED", "SYNTHETIC_BACKUP_VERIFIED", "STOPPED", "QUARANTINED"},
    "STOPPED": set(),                        # leaving STOPPED is only possible by building a new controller with ``recover``
    "QUARANTINED": set(),                    # terminal: a human decides, a new run needs new evidence
}
STAGES = I.STAGES
BEFORE_BOUNDARY = {"known": "pre_launch", "test": "after_known", "matched": "after_test"}
AFTER_BOUNDARY = {"known": "after_known", "test": "after_test", "matched": "after_matched"}
SYNTHETIC_PREFIX = b"E18-SYNTHETIC-NON-RF-FIXTURE\n"
MAX_SYNTHETIC_PAYLOAD = 64 * 1024
MAX_SYNTHETIC_METADATA = 64 * 1024
PRODUCER_KEYS = frozenset({"payload", "metadata"})
MACHINE_KEYS = frozenset({"collected_at", "elapsed_wall_s", "cpu_core_s", "peak_rss_gib", "working_free_gib", "backup_free_gb"})
REFRESH_EVERY_SHARDS = 64
REFRESH_EVERY_SECONDS = 3600              # also by time: a revocation answer must never be older than this while shards are produced
TRUST_MAX_AGE_S = 300                      # E17 freshness bound for a signed answer; a stage may not start on an older verification
RESUMABLE_ACTION = "resume_only_under_identical_request"
LOCK_NAME = "controller.lock"
NO_AUTHORITY = {"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "production_launch_enabled": False,
                "benchmark_complete": False, "production_running_state": False}
CURRENT = object()                           # journal stage = the controller's current stage (None means a run-level entry)


class ProductionExecutionUnavailable(RuntimeError):
    """Real generation is unreachable from this module for every input."""


class InvalidTransition(RuntimeError):
    pass


class LifecycleRefused(ValueError):
    pass


class JournalUnavailable(RuntimeError):
    pass


def deny_production(*args, **kwargs):
    """Unconditional refusal, raised before any argument is inspected."""
    raise ProductionExecutionUnavailable("E18 has no production execution path; DR-04 NO-GO")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(canonical(value).encode())


class _DirectoryLock:
    """A directory opened without following symlinks, kept open for an advisory lock; creates and writes nothing."""

    def __init__(self, path):
        self._fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def fileno(self):
        return self._fd

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


# ---- custody ports with durable reference implementations ------------------------------------------------------

class ReplayStore:
    """One-time challenge custody on durable storage. The real custodian is external; this is the reference port.

    ``begin`` issues an unpredictable challenge and a strictly increasing sequence floor; ``finish`` marks it consumed
    whether or not verification succeeded, so evidence signed for it can never be accepted again.
    """

    def __init__(self, directory, entropy=secrets.token_bytes):
        self.directory = Path(directory)
        self._entropy = entropy

    def begin(self):
        fds = D._chain(self.directory)
        try:
            sequence = sum(1 for n in os.listdir(fds[-1]) if n.startswith("issue-")) + 1
            challenge = self._entropy(32).hex()
            S._publish(fds[-1], f"issue-{sequence:08d}.json", S._canonical({"sequence": sequence, "challenge": challenge}))
            return challenge, sequence
        finally:
            D._close(fds)

    def finish(self, challenge, sequence):
        fds = D._chain(self.directory)
        try:
            names = os.listdir(fds[-1])
            issue = f"issue-{sequence:08d}.json"
            if issue not in names or S._strict(D._read_regular(fds[-1], issue, 4096, keep=True)[3]) != {"sequence": sequence, "challenge": challenge}:
                raise LifecycleRefused("challenge was not issued by this custody")
            consumed = f"consumed-{sequence:08d}.json"
            if consumed in names:
                raise LifecycleRefused("challenge already consumed (replay)")
            S._publish(fds[-1], consumed, S._canonical({"sequence": sequence, "challenge": challenge}))
        finally:
            D._close(fds)

    def consumed(self):
        fds = D._chain(self.directory)
        try:
            return sum(1 for n in os.listdir(fds[-1]) if n.startswith("consumed-"))
        finally:
            D._close(fds)


class AnchorStore:
    """Independent custody of ledger heads, one immutable no-clobber file per head (reference implementation)."""

    def __init__(self, directory):
        self.directory = Path(directory)

    @staticmethod
    def _valid(head):
        return isinstance(head, dict) and set(head) == {"seq", "entry_sha256"} and type(head["seq"]) is int and head["seq"] >= 0

    def record(self, head):
        if not self._valid(head):
            raise LifecycleRefused("malformed ledger head")
        fds = D._chain(self.directory)
        try:
            name, raw = f"anchor-{head['seq']:08d}.json", S._canonical(head)
            if name in os.listdir(fds[-1]):
                if D._read_regular(fds[-1], name, 4096, keep=True)[3] != raw:
                    raise LifecycleRefused("a different head is already anchored at this sequence")
                return
            S._publish(fds[-1], name, raw)
        finally:
            D._close(fds)

    def latest(self):
        fds = D._chain(self.directory)
        try:
            names = sorted(n for n in os.listdir(fds[-1]) if n.startswith("anchor-"))
            if not names:
                return None
            head = S._strict(D._read_regular(fds[-1], names[-1], 4096, keep=True)[3])
            if not self._valid(head) or names[-1] != f"anchor-{head['seq']:08d}.json":
                raise LifecycleRefused("anchor file differs from its name")
            return head
        finally:
            D._close(fds)


@dataclass(frozen=True)
class Workspace:
    """Synthetic roots. None may equal or nest with another or with the plan's declared production roots."""
    work: Path
    backup: Path
    journal: Path
    anchors: Path
    replay: Path
    quarantine: Path

    ROLES = ("work", "backup", "journal", "anchors", "replay", "quarantine")

    def paths(self):
        try:
            return {name: S._absolute(getattr(self, name)) for name in self.ROLES}
        except S.StorageRefused as error:
            raise LifecycleRefused(str(error)) from error

    def validate(self, plan):
        paths = self.paths()
        declared = {Path(plan["working"]["root"]), Path(plan["backup"]["root"])}
        names = list(paths)
        for index, left in enumerate(names):
            if any(paths[left] == root or root in paths[left].parents or paths[left] in root.parents for root in declared):
                raise LifecycleRefused(f"synthetic root {left} touches a declared production root")
            for right in names[index + 1:]:
                a, b = paths[left], paths[right]
                if a == b or a in b.parents or b in a.parents:
                    raise LifecycleRefused(f"synthetic roots {left} and {right} overlap")
        try:
            identities = {name: D.directory_identity(path) for name, path in paths.items()}
        except (OSError, D.DurabilityRefused) as error:
            raise LifecycleRefused("a synthetic root is missing, a symlink or unreadable: " + type(error).__name__) from error
        if len({(i["st_dev"], i["st_ino"]) for i in identities.values()}) != len(identities):
            raise LifecycleRefused("synthetic roots alias one another")
        taken = {(i["st_dev"], i["st_ino"]) for i in identities.values()}
        for root in declared:
            try:
                status = os.stat(root)
            except OSError:
                continue
            if (status.st_dev, status.st_ino) in taken:
                raise LifecycleRefused("a synthetic root is the same directory as a declared production root (alias or bind mount)")
        return identities


@dataclass(frozen=True)
class SyntheticProfile:
    """Everything injected. There is deliberately no mode, flag or permission field."""
    plan: dict
    specification: dict
    repo: Path
    trust_root: object                   # E17 TrustRoot of a fabricated test authority; never a researcher key
    reference_source: object             # callable(now) -> E13 reference, re-collected at every boundary
    evidence_source: object              # callable(challenge, floor, now) -> E17 evidence bundle
    producer: object                     # callable(request) -> {"payload": bytes, "metadata": bytes}, one planned shard
    clock: object                        # now() -> ISO text, monotonic() -> float seconds
    resources: object                    # observe() -> machine readings
    attestor: object                     # maps the synthetic workspace to the plan's declared identities
    workspace: Workspace
    consumers: object = None             # optional callable() -> consumer declaration (default: the frozen allowed readers)

    def __post_init__(self):
        if not isinstance(self.trust_root, E.TrustRoot):
            raise LifecycleRefused("a configured E17 trust root object is required")
        for name in ("reference_source", "evidence_source", "producer"):
            if not callable(getattr(self, name)):
                raise LifecycleRefused(f"{name} must be callable")
        if self.consumers is not None and not callable(self.consumers):
            raise LifecycleRefused("consumers must be callable")
        for name, methods in (("clock", ("now", "monotonic")), ("resources", ("observe",)),
                              ("attestor", ("stage_doc", "backup_doc", "journal_location", "k17d_report"))):
            if not all(callable(getattr(getattr(self, name), m, None)) for m in methods):
                raise LifecycleRefused(f"{name} lacks {methods}")
        if not isinstance(self.workspace, Workspace):
            raise LifecycleRefused("workspace must be a Workspace")


def production_gate(plan, reference, *, repo, evidence, now, challenge, revocation_floor, ci_floor):
    """The only entry for real work. It reports E17's verdict on the public (unconfigured) root and always ends BLOCKED.

    No port is called, no shard is produced and no state beyond BLOCKED exists for this path, so neither a closed gate,
    a missing trust root nor a flawless approval can start generation.
    """
    trusted = E.evaluate_trusted_authorization(plan, reference, repo=repo, evidence=evidence, now=now, challenge=challenge,
                                               revocation_floor=revocation_floor, ci_floor=ci_floor)
    return {"schema": SCHEMA_PRODUCTION_GATE, "lifecycle_state": "BLOCKED", "reason": "PRODUCTION_EXECUTION_UNAVAILABLE",
            "trusted_evidence_status": trusted.get("status"), "trusted_evidence_scope": trusted.get("evidence_scope"),
            "trusted_evidence_state": trusted.get("state"),
            "trusted_evidence_ok": bool(trusted.get("ok")) and trusted.get("state") == P.STATE_VALID,      # a verified *closed* state is not an approval
            "closed_state_verified": bool(trusted.get("ok")) and trusted.get("state") == P.STATE_CLOSED,
            "trust_root_configured": E.PINNED_TRUST_ROOT is not None, "execution_boundary": I._execution_boundary()["status"],
            "production_launch_flag": G.sup.PRODUCTION_LAUNCH_ENABLED, "ports_called": 0,
            **{**NO_AUTHORITY, "production_launch_enabled": bool(G.sup.PRODUCTION_LAUNCH_ENABLED)}}


# ---- the controller -------------------------------------------------------------------------------------------

class SyntheticExecutorLifecycle:
    """One controller per synthetic workspace. ``recover`` is the only way to continue a run after a stop or a crash."""

    def __init__(self, profile, *, _recovering=False):
        if not isinstance(profile, SyntheticProfile):
            raise LifecycleRefused("a SyntheticProfile is required; there is no other construction path")
        self._profile = profile
        self.plan = C._check_plan(profile.plan)
        self.spec = C._document(profile.specification)
        if C.canonical(self.spec) != C.canonical(C.build_specification(self.plan)):
            raise LifecycleRefused("specification differs from the one sealed from the plan")
        self.identities = profile.workspace.validate(self.plan)
        self.paths = profile.workspace.paths()
        self._lock = self._acquire_lock()
        self.ledger = L.Ledger(self.paths["journal"])
        self.anchors = AnchorStore(self.paths["anchors"])
        self.replay = ReplayStore(self.paths["replay"])
        self.identity = {"plan_fingerprint": self.plan["plan_fingerprint"], "specification_sha256": self.spec["specification_sha256"]}
        self.layout = {s["name"]: I._layout(s) for s in self.spec["stages"]}
        self.state = "PREPARED"
        self.stage_index = 0
        self.completed = []
        self._events = []
        self.manifests = {}                      # stage -> {role: manifest_sha256}
        self.stage_fingerprints = {"known": self.plan["source"]["known_request_fingerprint"]}
        self._bound = {"known"}
        self._admitted_marker = set()
        self._journaled = set()                  # (stage, kind) of the once-only ledger entries already written
        self._admissions = {}                    # (stage, role) -> {ordinal: admission}
        self._raw_backup = {}
        self._trusted = None
        self._grant = None
        self._record = None
        self._blocked_from = None
        self._pending_interruption = False
        self._anchor_seen = None                  # (seq, sha) of the newest head this process anchored: custody may never move away from it
        self._run_opened_at = None
        self._last_refresh_at = None
        self._journal_open = False
        self._journal_ok = True
        self._attempt = 1
        self._failed_attempts = 0
        self._interruptions = 0
        self._shards_this_attempt = 0
        self._first_shard = None
        self._last_machine = None
        self._last_refresh = 0
        self._last_k17d = None
        self._reports = []
        exists = self._ledger_exists()
        if exists and not _recovering:
            self.close()
            raise LifecycleRefused("a journal already exists for this workspace: use recover(), never overwrite a run")
        if _recovering and not exists:
            self.close()
            raise LifecycleRefused("there is no journal to recover from")
        self._event("init", None, "PREPARED", shards=sum(len(s["shards"]) for s in self.spec["stages"]))

    # ---- construction helpers ---------------------------------------------------------------------------
    @classmethod
    def recover(cls, profile):
        """Rebuild a run from its journal and the bytes on disk, or refuse. Never trusts memory of a previous process."""
        self = cls(profile, _recovering=True)
        try:
            self._load_journal()
            self._rebuild_disk()
            if self.state != "QUARANTINED":
                self._record_restart()
        except JournalUnavailable as error:
            self.close()
            raise LifecycleRefused("the journal cannot be extended at restart (" + str(error) + "): refusing to continue") from error
        except BaseException:
            self.close()
            raise
        return self

    def _acquire_lock(self):
        """Exclusive locks on the journal directory (a lock file) and on the work and backup roots (their directory descriptors)."""
        held = []
        try:
            fds = D._chain(self.paths["journal"])
            try:
                held.append(os.fdopen(os.open(LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fds[-1]), "r+b"))
            finally:
                D._close(fds)
            for name in ("work", "backup"):
                held.append(_DirectoryLock(self.paths[name]))
            for handle in held:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            for handle in held:
                handle.close()
            raise LifecycleRefused("another controller holds this workspace") from error
        return held

    def close(self):
        for handle in getattr(self, "_lock", None) or []:
            handle.close()
        self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _ledger_exists(self):
        fds = D._chain(self.paths["journal"])
        try:
            return L.LEDGER_NAME in os.listdir(fds[-1])
        finally:
            D._close(fds)

    # ---- bookkeeping ------------------------------------------------------------------------------------
    @property
    def profile(self):
        return self._profile

    @property
    def stage(self):
        return STAGES[self.stage_index] if self.stage_index < len(STAGES) else None

    @property
    def events(self):
        return copy.deepcopy(self._events)

    @property
    def boundary_reports(self):
        """Compact record of every E16 boundary report this controller evaluated (id -> status), oldest first."""
        return copy.deepcopy(self._reports)

    def _event(self, action, before, after, **detail):
        self._events.append({"n": len(self._events), "action": action, "from": before, "to": after, "stage": self.stage, **detail})

    def _move(self, new, action, **detail):
        if new not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state} -> {new} is not an allowed transition ({action})")
        before, self.state = self.state, new
        self._event(action, before, new, **detail)
        return self

    def _require(self, *states):
        if self.state not in states:
            raise InvalidTransition(f"operation requires {states} but the state is {self.state}")

    def _block(self, reason, **detail):
        self._blocked_from = self.state
        self._move("BLOCKED", "block", reason=reason, **detail)
        self._journal_best_effort("boundary_check", {"phase": "blocked", "reason": reason[:150]})
        return self

    def _stop(self, reason, *, resumable=False, incident=None, **detail):
        resumable = bool(resumable) and self._journal_ok
        self._move("STOPPED", "stop", reason=reason, resumable=resumable, **detail)
        if incident is not None:
            self._journal_best_effort("incident", L.incident_data(*incident))
        if not resumable:
            self._journal_best_effort("stop", {"state": "STOPPED", "reason": reason[:150]})
        return self

    def _quarantine(self, reason, role_dir=None, incident=None, **detail):
        notes = self._write_notes([role_dir] if role_dir is not None else [], reason)
        self._move("QUARANTINED", "quarantine", reason=reason, quarantine_notes=notes, **detail)
        if incident is not None:
            self._journal_best_effort("incident", L.incident_data(*incident))
        self._journal_best_effort("stop", {"state": "QUARANTINED", "reason": reason[:150]})
        return self

    def _write_notes(self, role_dirs, reason):
        """Evidence-preserving notes outside the data tree; moves, deletes and repairs nothing."""
        notes = []
        for directory, expected in role_dirs:
            try:
                report = D.classify_directory(directory, expected)
                if report["quarantine_required"] or report["unexpected_entries"]:
                    notes.append(D.write_quarantine_note(self.paths["quarantine"], directory, report, reason=reason[:150],
                                                         recorded_at=self.profile.clock.now())["note_name"])
            except (OSError, D.DurabilityRefused, S.StorageRefused, ValueError):
                continue
        return notes

    def _damaged_roles(self):
        return [(self.paths["work"] / s / r, self._expected_role(s, r)) for s in STAGES[:self.stage_index + 1] if s in self._bound
                for r in I.STAGE_ROLES[s] if (self.paths["work"] / s / r).is_dir()]

    # ---- external journal ---------------------------------------------------------------------------------
    def _journal(self, kind, data, stage=CURRENT):
        if not self._journal_ok:
            raise JournalUnavailable("the journal already failed")
        try:
            seen = self._anchor_seen
            if self.anchors.latest() != seen:        # deleted, rolled back, advanced or replaced custody is never "healed" by carrying on
                raise LifecycleRefused("anchor custody changed while the run was in progress")
            entry = self.ledger.append(kind, self.stage if stage is CURRENT else stage, data, self.profile.clock.now(), expected_head=seen)
            if entry["seq"] != (0 if seen is None else seen["seq"] + 1) or (seen is not None and entry["prev_sha256"] != seen["entry_sha256"]):
                raise LifecycleRefused("the ledger holds entries that were never anchored")
            head = {"seq": entry["seq"], "entry_sha256": entry["entry_sha256"]}
            self.anchors.record(head)
            self._anchor_seen = head
            if kind == "run_opened":
                self._run_opened_at = entry["at"]
            return entry
        except Exception as error:               # unavailable, corrupt, forged, anchor mismatch: nothing may continue unjournaled
            self._journal_ok = False
            self._event("journal_failure", self.state, self.state, error=type(error).__name__)
            raise JournalUnavailable(type(error).__name__) from error

    def _journal_best_effort(self, kind, data, stage=CURRENT):
        if not self._journal_open:               # nothing was ever run: events are the only record, the journal must begin with run_opened
            return None
        try:
            return self._journal(kind, data, stage)
        except JournalUnavailable:
            return None

    def _journal_once(self, stage, kind, data):
        if (stage, kind) not in self._journaled:
            self._journal(kind, data, stage=stage)
            self._journaled.add((stage, kind))

    def _fail_journal(self):
        """Journal storage is unavailable: stop in memory; no further step may rely on the ledger."""
        self._journal_ok = False                             # a journal that cannot be verified or written is never trusted again by this controller
        if self.state not in ("STOPPED", "QUARANTINED"):
            self._move("STOPPED", "stop", reason="journal unavailable", resumable=False)
        return self

    # ---- E17 trusted evidence + E13/E16 revalidation -------------------------------------------------------
    def _trusted_check(self):
        """One fresh E17 evaluation under a one-time challenge. Any failure of the sources is a refusal, never a pass."""
        now = self.profile.clock.now()
        challenge, floor = self.replay.begin()
        try:
            reference = self.profile.reference_source(now)
            evidence = self.profile.evidence_source(challenge, floor, now)
            report = E._evaluate_with_root(copy.deepcopy(self.profile.plan), reference, repo=self.profile.repo, evidence=evidence,
                                           now=now, challenge=challenge, revocation_floor=floor, ci_floor=floor,
                                           requested_scope=copy.deepcopy(P.GRANTED_SCOPE), root=self.profile.trust_root, test_root=True)
        except Exception as error:
            raise LifecycleRefused("trusted evidence could not be evaluated: " + type(error).__name__) from error
        finally:
            self.replay.finish(challenge, floor)
        self._last_refresh_at = self.profile.clock.monotonic()
        return {"report": report, "reference": reference, "now": now, "evidence": evidence, "challenge": challenge, "floor": floor}

    def _trust_fresh(self):
        """The verification a stage starts on is at most as old as the signed answers it relied on may be."""
        if self._trusted is None:
            return False
        age = (S._instant(self.profile.clock.now()) - S._instant(self._trusted["now"])).total_seconds()
        return 0 <= age <= TRUST_MAX_AGE_S

    @staticmethod
    def _trust_ok(report):
        return (report.get("ok") is True and report.get("state") == P.STATE_VALID and report.get("evidence_scope") == "SYNTHETIC_TEST_ROOT"
                and report.get("execution_permitted") is False and report.get("replay_state_updated") is False)

    def _trust_failure(self, trusted, where):
        """Closed gates and unknown evidence BLOCK; an explicit revocation or an expiry STOPS the run."""
        report = trusted["report"]
        if report.get("state") == P.STATE_CLOSED:
            return self._block("the canonical gates are closed: nothing authorizes", trusted_state=report["state"])
        revoked = False
        try:
            self._read_grant()
            evidence = trusted["evidence"]
            rev = E.verify_revocation(evidence["revocation"], evidence["revocation_signature"], policy=evidence["policy"], root=self.profile.trust_root,
                                      expected=self._grant, now=trusted["now"], challenge=trusted["challenge"], sequence_floor=trusted["floor"])
            revoked = any("revoked or unknown grant" in f for f in rev["failures"])
        except Exception:                        # unreadable record or evidence: unknown, not revoked
            revoked = False
        expired = any(i["id"] == "authorization.unexpired" and i["status"] == P.FAIL for i in (report.get("policy_report") or {}).get("findings", []))
        if revoked:
            return self._stop(where + ": authorization revoked", incident=("authorization_revoked", {"revocation_id": self._grant["revocation_id"]}))
        if expired:
            return self._stop(where + ": authorization expired", incident=("authorization_expired", {"expires_at": self.plan["authorization"]["expires_at"]}))
        return self._block(where + ": trusted authorization refused", trusted_status=report.get("status"), failures=report.get("failures", [])[:3])

    def verify_evidence(self):
        """PREPARED -> EVIDENCE_VERIFIED, or BLOCKED / STOPPED when the signed evidence is not good."""
        self._require("PREPARED")
        if self.stage is None:
            raise InvalidTransition("all stages are complete")
        try:
            trusted = self._trusted_check()
        except (LifecycleRefused, OSError, S.StorageRefused, D.DurabilityRefused) as error:
            return self._block("trusted evidence could not be evaluated", error=type(error).__name__, detail=str(error)[:120])
        report = trusted["report"]
        if not self._trust_ok(report):
            return self._trust_failure(trusted, "evidence")
        try:
            self._trusted = trusted
            self._remember_grant()
            if not self._journal_open:
                self._journal("run_opened", dict(self.identity), stage=None)
                self._journal("authorization_snapshot", {"record_sha256": self.plan["authorization"]["record_sha256"],
                                                         "expires_at": self.plan["authorization"]["expires_at"],
                                                         "revocation_id": self._grant["revocation_id"]}, stage=None)
                self._journal_open = True
            self._journal("boundary_check", {"phase": "evidence", "stage": self.stage, "evidence_scope": report["evidence_scope"],
                                             "revocation_sha256": report["revocation"]["evidence_sha256"], "ci_sha256": report["ci"]["evidence_sha256"]})
        except JournalUnavailable:
            return self._fail_journal()
        except (OSError, KeyError, ValueError, LifecycleRefused) as error:
            return self._block("authorization record could not be read", error=type(error).__name__)
        return self._move("EVIDENCE_VERIFIED", "verify_evidence", revocation_checked_at=report["revocation"]["checked_at"])

    def _read_grant(self):
        auth = self.plan["authorization"]
        raw = Git.read_blob(self.profile.repo, self.plan["source"]["git_commit"], auth["record"])
        blocks = P._blocks_of(raw.decode("utf-8"), P.SCHEMA_BLOCK)
        if len(blocks) != 1:
            raise LifecycleRefused("exactly one operational block is required")
        block = blocks[0]
        self._grant = {"revocation_id": block["revocation_id"], "record_sha256": _sha(raw), "approved_plan_digest": block["approved_plan_digest"],
                       "reviewed_code_commit": block["reviewed_code_commit"], "approval_commit": self.plan["source"]["git_commit"]}
        self._record = (raw, block)

    def _remember_grant(self):
        self._read_grant()

    # ---- E16 boundary adapters -------------------------------------------------------------------------
    def _policy_adapters(self):
        report, (raw, block) = self._trusted["report"], self._record
        researcher = self._trusted["reference"]["scientific_protocol"]["approved_by"]
        head, lineage, rev = self.plan["source"]["git_commit"], report["lineage"], report["revocation"]
        return {
            "signature_verifier": lambda sha, principal, signature: (report["ok"] is True and sha == _sha(raw) and principal == researcher
                                                                      and signature == block["signature"]),
            "ancestry_checker": lambda reviewed, approval: {"is_ancestor": lineage["is_ancestor"] and reviewed == block["reviewed_code_commit"]
                                                            and approval == head, "changed_paths": lineage["changed_paths"]},
            "revocation_checker": lambda grant: {"revoked": grant != block["revocation_id"], "checked_at": rev["checked_at"]},
        }

    def _expected(self, stage, role, shard):
        return {"role": role, "scenario_seeds": list(shard["groups"]), "n_samples": shard["observations"],
                "request_fingerprint": self.stage_fingerprints[stage]}

    def _expected_role(self, stage, role):
        return {o: self._expected(stage, role, s) for o, s in self.layout[stage][role].items()}

    def _raw_stage(self, stage):
        """What the work tree really holds for one stage (classification, admissions, manifests, immutability)."""
        root = self.paths["work"] / stage
        raw = {"stage": stage, "root": None, "roles": {}, "unexpected_root_entries": [],
               "request_fingerprint": self.stage_fingerprints.get(stage) if stage in self._bound else None}
        try:
            fds = D._chain(root)
        except FileNotFoundError:
            fds = None
        if fds is not None:
            try:
                raw["root"] = D.directory_identity(root)
                raw["unexpected_root_entries"] = sorted(n for n in os.listdir(fds[-1]) if n not in I.STAGE_ROLES[stage])
            finally:
                D._close(fds)
        for role in I.STAGE_ROLES[stage]:
            directory = root / role
            entry = {"exists": False, "directory": None, "classification": None, "admissions": None, "manifest": None, "immutability": None}
            if directory.is_dir() and not directory.is_symlink() and stage in self._bound:
                expected = self._expected_role(stage, role)
                classification = D.classify_directory(directory, expected)
                entry.update(exists=True, directory=D.directory_identity(directory), classification=classification)
                if classification["resume_state"] == "COMPLETE":
                    admitted = self._admissions.get((stage, role), {})
                    entry["admissions"] = [admitted[o] for o in sorted(expected) if o in admitted]
                    entry["manifest"] = D.build_manifest(directory, expected)
                    entry["immutability"] = D.immutable_publication_report(directory, sorted(expected))
            elif directory.is_dir() and not directory.is_symlink():          # not yet admitted: it must hold nothing at all
                names = sorted(os.listdir(directory))
                entry.update(exists=True, directory=D.directory_identity(directory),
                             classification={"schema": D.SCHEMA_CLASSIFICATION, "resume_state": "NOT_STARTED" if not names else "NEEDS_QUARANTINE",
                                             "unexpected_entries": names, "planned": 0})
            raw["roles"][role] = entry
        return raw

    def _machine(self):
        """Machine readings from the injected port, strictly shaped. Anything else is a missing reading."""
        reading = self.profile.resources.observe()
        if not (isinstance(reading, dict) and set(reading) == MACHINE_KEYS):
            raise LifecycleRefused("resource reading fields differ from the contract")
        return dict(reading)

    def _check_machine_consistency(self, machine):
        for key in ("elapsed_wall_s", "cpu_core_s", "peak_rss_gib", "working_free_gib", "backup_free_gb"):
            value = machine[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise LifecycleRefused(f"{key} is not a finite non-negative number")
        previous = self._last_machine
        if previous is not None:
            for key in ("elapsed_wall_s", "cpu_core_s"):
                if machine[key] < previous[key]:
                    raise LifecycleRefused(f"{key} decreased between readings")
        cpus = self.plan["host"]["inventory"]["inventory"]["cpu"]["schedulable_cpus"]
        if machine["cpu_core_s"] > machine["elapsed_wall_s"] * cpus * 1.05 + 1:
            raise LifecycleRefused("accumulated CPU time exceeds what the host's cores could deliver")
        if self._run_opened_at is not None:
            span = (S._instant(self.profile.clock.now()) - S._instant(self._run_opened_at)).total_seconds()
            if machine["elapsed_wall_s"] + 10 < span:
                raise LifecycleRefused("elapsed wall time is shorter than the span the journal itself records")
        self._last_machine = machine

    def _committed(self):
        return sum(self.layout[s][r][o]["observations"] for (s, r), admitted in self._admissions.items() for o in admitted)

    def _resource_state(self):
        machine = self._machine()
        self._check_machine_consistency(machine)
        committed = self._committed()
        return {"schema": L.SCHEMA_OBSERVATION, **machine, "failed_attempts": self._failed_attempts, "interruptions": self._interruptions,
                "total_attempts": self._attempt, "observations_committed": committed, "observations_remaining": G.pre.PLAN_TOTAL - committed,
                "admitted_shards_this_attempt": self._shards_this_attempt,
                "first_shard": None if self._first_shard is None else dict(self._first_shard)}

    def _verified_ledger(self):
        """The ledger exactly as this process left it: anchored at the head it last recorded, with nothing added or removed."""
        seen = self._anchor_seen
        if seen is None or self.anchors.latest() != seen:
            raise LifecycleRefused("anchor custody changed while the run was in progress")
        verified = L.verify_chain(self.ledger.read(), expected_head=seen)
        if not verified["ok"]:
            raise LifecycleRefused("journal failed verification: " + "; ".join(verified["failures"][:2]))
        if verified["count"] != seen["seq"] + 1:
            raise LifecycleRefused("the ledger holds entries that were never anchored")
        return verified

    def _journal_doc(self, moment):
        verified = self._verified_ledger()
        return {"schema": I.SCHEMA_JOURNAL, "collected_at": moment, "entries": verified["entries"], "anchor": dict(self._anchor_seen),
                "location": self.profile.attestor.journal_location(self.identities)}

    def _boundary(self, boundary):
        """One E16 report for this boundary, with every adapter answering from one consistent instant."""
        resource = self._resource_state()
        moment = self.profile.clock.now()
        attestor = self.profile.attestor
        k17d = attestor.k17d_report(self.plan)
        self._last_k17d = k17d
        declaration = self.profile.consumers() if self.profile.consumers is not None else copy.deepcopy(I.ALLOWED_CONSUMERS)
        adapters = {
            "shard_state": lambda stage: attestor.stage_doc(stage, self._raw_stage(stage), moment),
            "backup_state": lambda stage: attestor.backup_doc(stage, self._verify_backup(stage), moment),
            "journal_state": lambda: self._journal_doc(moment),
            "k17d_metadata": lambda: dict(k17d, collected_at=moment),
            "resource_state": lambda stage: copy.deepcopy(resource),
            "consumer_declaration": lambda: copy.deepcopy(declaration),
            **self._policy_adapters(),
        }
        report = I.evaluate_release_boundary(copy.deepcopy(self.profile.plan), self._trusted["reference"], copy.deepcopy(self.profile.specification),
                                             boundary=boundary, requested_scope=copy.deepcopy(P.GRANTED_SCOPE), now=moment, adapters=adapters)
        self._reports.append({"boundary": boundary, "at": moment, "synthetic": True, "evidence_scope": "SYNTHETIC_TEST_ROOT",
                              "attestations": "FABRICATED_SYNTHETIC",
                              "document_conditions_met": report["document_conditions_met"],
                              "conditions": {c["id"]: c["status"] for c in report["conditions"]}})
        return report

    def _dispose(self, report):
        """Map unmet boundary conditions to a disposition: integrity -> QUARANTINED; tampering/stop -> STOPPED; missing facts -> BLOCKED."""
        permanent = [c for c in report["conditions"] if c["id"] == I.PERMANENT]
        if len(permanent) != 1 or permanent[0]["status"] != I.BLOCKED or (permanent[0].get("details") or {}).get("permanent") is not True:
            return self._stop("the E16 execution boundary changed: it must stay permanently BLOCKED", incident=(
                "identity_mismatch", {"what": "execution.boundary", "expected_sha256": _digest({"status": I.BLOCKED, "permanent": True}),
                                      "observed_sha256": _digest(permanent)}))
        unmet = [c for c in report["conditions"] if c["applicable"] and c["id"] != I.PERMANENT and c["status"] != I.PASS]
        if not unmet:
            return None
        failing = {c["id"]: c for c in unmet if c["status"] == I.FAIL}
        ids = sorted(failing)
        current = self.stage_index
        later = [i for i in ids if i.startswith("durability.") and i.split(".", 1)[1] in STAGES and STAGES.index(i.split(".", 1)[1]) > current]
        if later:
            return self._stop("stage-order violation: data exists for a stage that has not been admitted", incident=(
                "stage_order_violation", {"stage": later[0].split(".", 1)[1], "required_predecessor": STAGES[current]}), failing=ids)
        if any(i.startswith(("durability.", "backup.")) for i in ids):
            incident = ("backup_mismatch", {"role": "backup", "manifest_sha256": _digest(self.manifests.get(self.stage, {}))}) \
                if any(i.startswith("backup.") for i in ids) else None
            notes = self._write_notes(self._damaged_roles(), "boundary integrity failure")
            self._quarantine("boundary integrity failure: " + ", ".join(ids[:4]), incident=incident, failing=ids, evidence_notes=notes)
            return self
        if "k17d.metadata" in failing:                       # first: a wrong K17d identity also makes the journal's k17d_check disagree
            return self._stop("K17d identity mismatch", incident=("k17d_mismatch", {
                "expected_sha256": self.plan["scientific"]["d8_k17d"]["identity_sha256"],
                "observed_sha256": str((self._last_k17d or {}).get("identity_sha256", "0" * 64))}), failing=ids)
        if "journal.external" in failing:
            return self._fail_journal()
        isolation = [i for i in ids if i.startswith("isolation.")]
        if isolation:
            return self._stop("role-isolation violation", incident=("identity_mismatch", {
                "what": ",".join(isolation)[:60], "expected_sha256": _digest(I.ALLOWED_CONSUMERS), "observed_sha256": _digest(failing[isolation[0]]["message"])}),
                failing=ids)
        if "runtime.stop_conditions" in failing:
            details = failing["runtime.stop_conditions"]["details"]
            reasons = details.get("reasons", [])
            return self._stop("stop condition at the boundary: " + ", ".join(reasons[:3]), incident=self._incident_for(
                reasons[0] if reasons else "input.malformed", details.get("projections", {}), self._last_machine or {}), failing=ids)
        if ids:
            return self._stop("identity or authorization failure at the boundary: " + ", ".join(ids[:4]), incident=(
                "identity_mismatch", {"what": ids[0][:60], "expected_sha256": self.plan["plan_fingerprint"], "observed_sha256": _digest(failing[ids[0]]["message"])}),
                failing=ids)
        return self._block("missing boundary facts: " + ", ".join(sorted(c["id"] for c in unmet)[:6]), failing=sorted(c["id"] for c in unmet))

    # ---- admission -------------------------------------------------------------------------------------
    def check_admission(self):
        """EVIDENCE_VERIFIED -> ADMISSION_CHECKED after the E16 boundary report for the coming stage is complete and consistent."""
        self._require("EVIDENCE_VERIFIED")
        stage = self.stage
        if not self._trust_fresh():
            return self._block("the trusted verification is older than its signed answers may be: verify again", stale_after_s=TRUST_MAX_AGE_S)
        try:
            if stage in self._admitted_marker:
                return self._admit_resume()
            if self._attempt > 1 and self._restart_exhausted():
                return self._stop("restart refused: the restart allowance is exhausted", incident=self._incident_for("restart.allowance_exhausted", {}, {}))
            self._ensure_dirs(self.paths["work"], stage)
            self._derive_binding(stage)
            report = self._boundary(BEFORE_BOUNDARY[stage])
            if self._dispose(report) is not None:
                return self
            self._journal("boundary_check", {"phase": "admission", "stage": stage, "boundary": BEFORE_BOUNDARY[stage]})
            self._admitted_marker.add(stage)
            self._bind(stage)
        except JournalUnavailable:
            return self._fail_journal()
        except (OSError, LifecycleRefused, D.DurabilityRefused, S.StorageRefused, ValueError, KeyError) as error:
            return self._block("admission evidence could not be assembled", error=type(error).__name__, detail=str(error)[:120])
        return self._move("ADMISSION_CHECKED", "check_admission", boundary=BEFORE_BOUNDARY[stage], conditions=len(report["conditions"]))

    def _restart_exhausted(self):
        stop = L.evaluate_stop_conditions(self._resource_state(), self.plan["ceilings"], self._authorization_state(), now=self.profile.clock.now(),
                                          stage=self.stage, restarting=True, timing=self.plan["timing"])
        return "restart.allowance_exhausted" in stop["reasons"]

    def _derive_binding(self, stage):
        """Later request identities are derived from the completed predecessor artifacts, never taken from a fixture."""
        if stage == "known" or stage in self.stage_fingerprints:
            return
        previous = {s: self.manifests.get(s) for s in STAGES[:STAGES.index(stage)]}
        if not all(previous.values()):
            raise LifecycleRefused("predecessor stage manifests are missing")
        self.stage_fingerprints[stage] = _digest({"schema": "B2-E18-synthetic-deferred-request/1", "stage": stage,
                                                  "plan_fingerprint": self.plan["plan_fingerprint"],
                                                  "known_request_fingerprint": self.plan["source"]["known_request_fingerprint"],
                                                  "predecessor_manifests": previous})

    def _bind(self, stage):
        if stage != "known":
            self._journal_once(stage, "stage_bound", {"request_fingerprint": self.stage_fingerprints[stage]})
        self._bound.add(stage)

    @staticmethod
    def _ensure_dirs(base, stage):
        fds = D._chain(base)
        try:
            if stage not in os.listdir(fds[-1]):
                os.mkdir(stage, 0o755, dir_fd=fds[-1])
                os.fsync(fds[-1])
            child = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1])
            try:
                for role in I.STAGE_ROLES[stage]:
                    if role not in os.listdir(child):
                        os.mkdir(role, 0o755, dir_fd=child)
                os.fsync(child)
            finally:
                os.close(child)
        finally:
            D._close(fds)

    def _admit_resume(self):
        """Mid-stage re-admission: identities and journal were rebuilt in ``recover``; here the evidence is fresh and the budget is rechecked."""
        stage = self.stage
        try:
            self._check_identities()
            self._derive_binding(stage)
            self._bind(stage)
            observation = self._resource_state()
        except JournalUnavailable:
            return self._fail_journal()
        except (OSError, LifecycleRefused, D.DurabilityRefused, S.StorageRefused, KeyError, ValueError) as error:
            return self._stop("restart refused: " + type(error).__name__ + ": " + str(error)[:100], incident=(
                "identity_mismatch", {"what": "restart", "expected_sha256": self.plan["plan_fingerprint"], "observed_sha256": _digest(str(error))}))
        stop = L.evaluate_stop_conditions(observation, self.plan["ceilings"], self._authorization_state(), now=self.profile.clock.now(),
                                          stage=stage, restarting=True, timing=self.plan["timing"])
        if stop["decision"] == "STOP":
            return self._stop("restart refused: " + ", ".join(stop["reasons"][:3]), incident=self._incident_for(stop["reasons"][0], stop["projections"], observation))
        return self._move("ADMISSION_CHECKED", "check_admission", mode="resume")

    # ---- the stage run ----------------------------------------------------------------------------------
    def run_stage(self, shard_budget=None):
        """ADMISSION_CHECKED (or a run in progress) -> SYNTHETIC_STAGE_RUNNING; at most ``shard_budget`` new shards per call."""
        if shard_budget is not None and (type(shard_budget) is not int or shard_budget < 0):
            raise LifecycleRefused("shard_budget must be a non-negative integer")
        if self.state == "ADMISSION_CHECKED":
            if not self._trust_fresh():
                return self._block("the trusted verification went stale before the stage started: verify again", stale_after_s=TRUST_MAX_AGE_S)
            self._move("SYNTHETIC_STAGE_RUNNING", "start_stage", stage=self.stage)
        self._require("SYNTHETIC_STAGE_RUNNING")
        stage, done = self.stage, 0
        for role, shards in self.layout[stage].items():
            for ordinal in sorted(shards):
                if ordinal in self._admissions.get((stage, role), {}):
                    continue
                if shard_budget is not None and done >= shard_budget:
                    return self
                if not self._one_shard(stage, role, shards[ordinal]):
                    return self
                done += 1
        return self

    def _stage_fully_admitted(self):
        stage = self.stage
        return stage is not None and all(len(self._admissions.get((stage, r), {})) == len(self.layout[stage][r]) for r in I.STAGE_ROLES[stage])

    def _one_shard(self, stage, role, shard):
        request = {"stage": stage, "role": role, "ordinal": shard["ordinal"], "observations": shard["observations"],
                   "max_payload_bytes": MAX_SYNTHETIC_PAYLOAD, "max_metadata_bytes": MAX_SYNTHETIC_METADATA}   # no scenario seeds, no request identity
        started = self.profile.clock.monotonic()
        try:
            payload, metadata = self._validate_produced(self.profile.producer(copy.deepcopy(request)), shard)
        except Exception as error:
            self._failed_attempts += 1
            self._stop("synthetic producer failed or broke its contract", resumable=True, producer_error=type(error).__name__,
                       incident=("interruption", {"attempt": self._attempt, "signal": "PRODUCER_FAILURE"}))
            return False
        directory, expected = self.paths["work"] / stage / role, self._expected(stage, role, shard)
        try:
            self._publish(directory, shard, payload, metadata, expected)
            admission = D.admit_shard(directory, shard["ordinal"], expected)
        except (OSError, D.DurabilityRefused, S.StorageRefused) as error:
            self._quarantine("publication or admission failed: " + type(error).__name__, role_dir=(directory, self._expected_role(stage, role)),
                             incident=("partial_commit", {"role": role, "ordinal": shard["ordinal"]}))
            return False
        part, meta, _ = D.shard_names(shard["ordinal"])
        if (admission["files"][part] != {"bytes": len(payload), "sha256": _sha(payload)}
                or admission["files"][meta] != {"bytes": len(metadata), "sha256": _sha(metadata)}):
            self._quarantine("the admitted bytes differ from the bytes this controller published", role_dir=(directory, self._expected_role(stage, role)),
                             incident=("shard_corruption", {"role": role, "ordinal": shard["ordinal"], "expected_sha256": _sha(payload),
                                                            "observed_sha256": admission["files"][part]["sha256"]}))
            return False
        self._admissions.setdefault((stage, role), {})[shard["ordinal"]] = admission
        self._shards_this_attempt += 1
        elapsed = max(self.profile.clock.monotonic() - started, 1e-9)
        if self._first_shard is None:
            self._first_shard = {"s_per_observation": elapsed / shard["observations"], "observations": shard["observations"]}
        try:
            floor = {} if self._last_machine is None else {"wall_s": self._last_machine["elapsed_wall_s"], "cpu_s": self._last_machine["cpu_core_s"]}
            self._journal("shard_admitted", {"role": role, "ordinal": shard["ordinal"], "descriptor_sha256": admission["descriptor_sha256"], **floor})
        except JournalUnavailable:
            self._fail_journal()
            return False
        return self._supervise()

    @staticmethod
    def _validate_produced(produced, shard):
        if not (isinstance(produced, dict) and set(produced) == PRODUCER_KEYS and type(produced["payload"]) is bytes and type(produced["metadata"]) is bytes):
            raise LifecycleRefused("producer must return exactly payload and metadata bytes")
        return SyntheticExecutorLifecycle._check_synthetic(produced["payload"], produced["metadata"], shard)

    @staticmethod
    def _check_synthetic(payload, metadata, shard):
        """The fabricated-bytes-only contract. Applied to produced shards and again to every shard adopted at recovery."""
        if not payload.startswith(SYNTHETIC_PREFIX):
            raise LifecycleRefused("payload lacks the synthetic marker")
        if len(payload) > MAX_SYNTHETIC_PAYLOAD or len(metadata) > MAX_SYNTHETIC_METADATA:
            raise LifecycleRefused("payload exceeds the synthetic bound")
        lines = metadata.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()
        if len(lines) != shard["observations"]:
            raise LifecycleRefused("metadata line count differs from the planned observations")
        for line in lines:
            row = S._strict(line)
            if not (isinstance(row, dict) and row.get("synthetic") is True):
                raise LifecycleRefused("every metadata row must be explicitly synthetic")
        return payload, metadata

    @staticmethod
    def _publish(directory, shard, payload, metadata, expected):
        part, meta, descriptor_name = D.shard_names(shard["ordinal"])
        descriptor = {"part": part, "meta": meta, "role": expected["role"], "scenario_seeds": expected["scenario_seeds"],
                      "n_samples": expected["n_samples"], "request_fingerprint": expected["request_fingerprint"],
                      "sha256": {part: _sha(payload), meta: _sha(metadata)}}
        fd = S._open_root(directory)
        try:
            S._publish(fd, part, payload)
            S._publish(fd, meta, metadata)
            S._publish(fd, descriptor_name, S._canonical(descriptor))      # the descriptor is always last
        finally:
            os.close(fd)

    # ---- resource supervision ---------------------------------------------------------------------------
    def _supervise(self):
        """After every admitted shard: recheck identity and revocation on schedule, read resources, evaluate the E16 stop logic."""
        try:
            due = (self._shards_this_attempt - self._last_refresh >= REFRESH_EVERY_SHARDS
                   or (self._last_refresh_at is not None and self.profile.clock.monotonic() - self._last_refresh_at >= REFRESH_EVERY_SECONDS))
            if due and self._refresh() is not None:
                return False
            observation = self._resource_state()
        except JournalUnavailable:
            self._fail_journal()
            return False
        except Exception as error:
            self._stop("stop condition: resource observation missing or inconsistent", incident=(
                "resource_observation_missing", {"field": ("reading: " + type(error).__name__)[:60]}))
            return False
        stop = L.evaluate_stop_conditions(observation, self.plan["ceilings"], self._authorization_state(), now=self.profile.clock.now(),
                                          stage=self.stage, restarting=False, timing=self.plan["timing"])
        if stop["decision"] != "STOP":
            return True
        self._stop("stop condition: " + ", ".join(stop["reasons"][:3]), incident=self._incident_for(stop["reasons"][0], stop["projections"], observation),
                   reasons=stop["reasons"])
        return False

    def _authorization_state(self):
        return {"expires_at": self.plan["authorization"]["expires_at"], "revoked": False, "revocation_id": self._grant["revocation_id"]}

    def _incident_for(self, reason, projections, observation):
        ceilings = self.plan["ceilings"]
        number = lambda value: value if type(value) in (int, float) and abs(value) < 1e15 else 0        # noqa: E731
        if reason.startswith("ceiling."):
            name = reason.split(".", 1)[1]
            key = {"wall_hours": "wall_hours", "core_hours": "core_hours", "max_rss_gib": "max_rss_gib",
                   "failed_attempts": "max_failed_attempts_per_stage", "interruptions": "max_interruptions_per_stage",
                   "total_attempts": "max_failed_attempts_per_stage"}.get(name, name)
            return "ceiling_breach", {"ceiling": reason, "limit": number(ceilings.get(key, 0)), "observed": number(observation.get("elapsed_wall_s", 0))}
        if reason.startswith("projection."):
            return "projection_breach", {"projection": reason, "limit": number(ceilings["wall_hours"]), "projected": number(projections.get("projected_wall_hours", 0))}
        if reason.startswith("timing."):
            first = observation.get("first_shard") or {}
            return "timing_gate_failure", {"s_per_observation": number(first.get("s_per_observation", 0)), "band": list(self.plan["timing"]["band_s_per_observation"])}
        if reason == "authorization.expired":
            return "authorization_expired", {"expires_at": self.plan["authorization"]["expires_at"]}
        if reason == "authorization.revoked":
            return "authorization_revoked", {"revocation_id": self._grant["revocation_id"]}
        if reason == "restart.allowance_exhausted":
            return "ceiling_breach", {"ceiling": reason, "limit": number(ceilings["max_failed_attempts_per_stage"]), "observed": self._failed_attempts}
        return "resource_observation_missing", {"field": reason[:60]}

    def _refresh(self):
        """Scheduled mid-stage revalidation: source identity and a fresh signed revocation answer. Returns None when everything holds."""
        try:
            self._check_identities()
        except (LifecycleRefused, OSError, D.DurabilityRefused, S.StorageRefused, KeyError) as error:
            self._stop("identity changed while running: " + str(error)[:100], incident=(
                "identity_mismatch", {"what": "source", "expected_sha256": self.plan["source"]["source_tree_sha256"], "observed_sha256": _digest(str(error))}))
            return "identity"
        now = self.profile.clock.now()
        challenge, floor = self.replay.begin()
        try:
            evidence = self.profile.evidence_source(challenge, floor, now)
            rev = E.verify_revocation(evidence["revocation"], evidence["revocation_signature"], policy=evidence["policy"], root=self.profile.trust_root,
                                      expected=self._grant, now=now, challenge=challenge, sequence_floor=floor)
        except Exception as error:
            rev = {"ok": False, "unavailable": True, "failures": ["revocation evidence unavailable: " + type(error).__name__]}
        finally:
            self.replay.finish(challenge, floor)
        self._last_refresh = self._shards_this_attempt
        if not rev["ok"]:
            revoked = any("revoked or unknown grant" in f for f in rev.get("failures", []))
            if rev.get("unavailable"):               # an outage is an interruption to recover from under fresh evidence, not a verdict
                self._interruptions += 1
                self._stop("revocation source unavailable", resumable=True, incident=(
                    "interruption", {"attempt": self._attempt, "signal": "REVOCATION_UNAVAILABLE"}))
                return "revocation"
            self._stop("revocation refresh failed" + (": revoked" if revoked else ""), incident=(
                ("authorization_revoked", {"revocation_id": self._grant["revocation_id"]}) if revoked
                else ("resource_observation_missing", {"field": "revocation_evidence"})))
            return "revocation"
        self._last_refresh_at = self.profile.clock.monotonic()
        self._journal("boundary_check", {"phase": "revocation_refresh", "revocation_sha256": rev["evidence_sha256"]})
        return None

    # ---- verification, backup, completion ---------------------------------------------------------------
    def verify_stage(self):
        """SYNTHETIC_STAGE_RUNNING -> SYNTHETIC_STAGE_VERIFIED when every planned shard is admitted, complete and read-only."""
        self._require("SYNTHETIC_STAGE_RUNNING")
        if not self._stage_fully_admitted():
            raise InvalidTransition("the stage still has planned shards that are not admitted")
        stage, manifests = self.stage, {}
        for role in I.STAGE_ROLES[stage]:
            directory, expected = self.paths["work"] / stage / role, self._expected_role(stage, role)
            try:
                report = D.classify_directory(directory, expected)
                if report["resume_state"] != "COMPLETE":
                    return self._quarantine("stage classification is " + report["resume_state"], role_dir=(directory, expected),
                                            incident=("orphan_files", {"role": role, "files": (report["unexpected_entries"] + report["quarantine_required"])[:8]}))
                manifest = D.build_manifest(directory, expected)
                if not D.immutable_publication_report(directory, sorted(expected))["ok"]:
                    return self._quarantine("published files are not read-only", role_dir=(directory, expected))
            except (OSError, D.DurabilityRefused, S.StorageRefused) as error:
                return self._quarantine("stage verification failed: " + type(error).__name__, role_dir=(directory, expected))
            admitted_files = {(n, i["bytes"], i["sha256"]) for a in self._admissions.get((stage, role), {}).values() for n, i in a["files"].items()}
            if admitted_files != {(e["name"], e["bytes"], e["sha256"]) for e in manifest["entries"]}:
                return self._quarantine("the role holds bytes other than the ones this controller admitted", role_dir=(directory, expected), incident=(
                    "shard_corruption", {"role": role, "ordinal": 0, "expected_sha256": _digest(sorted(admitted_files)), "observed_sha256": manifest["manifest_sha256"]}))
            if stage in self.manifests and manifest["manifest_sha256"] != self.manifests[stage].get(role):
                return self._quarantine("a verified role no longer equals its journaled manifest", role_dir=(directory, expected), incident=(
                    "shard_corruption", {"role": role, "ordinal": 0, "expected_sha256": self.manifests[stage].get(role, "0" * 64), "observed_sha256": manifest["manifest_sha256"]}))
            manifests[role] = manifest["manifest_sha256"]
        try:
            self._journal_once(stage, "stage_completed", {"manifests": manifests})
        except JournalUnavailable:
            return self._fail_journal()
        self.manifests[stage] = manifests
        return self._move("SYNTHETIC_STAGE_VERIFIED", "verify_stage", manifests=manifests)

    def backup_stage(self):
        """SYNTHETIC_STAGE_VERIFIED -> SYNTHETIC_BACKUP_VERIFIED after a byte-checked restore of every role."""
        self._require("SYNTHETIC_STAGE_VERIFIED")
        stage = self.stage
        try:
            self._raw_backup[stage] = self._copy_and_verify(stage)
        except (D.DurabilityRefused, S.StorageRefused, LifecycleRefused) as error:
            return self._quarantine("backup copy or restore verification failed: " + type(error).__name__,
                                    incident=("backup_mismatch", {"role": "backup", "manifest_sha256": _digest(self.manifests[stage])}))
        except OSError as error:
            return self._stop("the backup device is unavailable: " + type(error).__name__, incident=(
                "backup_unavailable", {"reason": f"{type(error).__name__} errno {error.errno}"}))
        k17d = None
        if stage == "known":
            k17d = dict(self.profile.attestor.k17d_report(self.plan), collected_at=self.profile.clock.now())
            self._last_k17d = k17d
        try:
            self._journal_once(stage, "backup_verified", {"manifests": self.manifests[stage]})
            if k17d is not None:
                if I._k17d_problems(k17d, self.plan, self.profile.clock.now(), 3600):
                    return self._stop("the K17d metadata comparison failed before it could be journaled", incident=("k17d_mismatch", {
                        "expected_sha256": self.plan["scientific"]["d8_k17d"]["identity_sha256"], "observed_sha256": str(k17d.get("identity_sha256", "0" * 64))}))
                self._journal_once(None, "k17d_check", {"identity_sha256": k17d["identity_sha256"]})
        except JournalUnavailable:
            return self._fail_journal()
        return self._move("SYNTHETIC_BACKUP_VERIFIED", "backup_stage", roles=sorted(self._raw_backup[stage]["restores"]))

    def _copy_and_verify(self, stage):
        self._ensure_dirs(self.paths["backup"], stage)
        restores, copies = {}, {}
        for role in I.STAGE_ROLES[stage]:
            source, target = self.paths["work"] / stage / role, self.paths["backup"] / stage / role
            expected = self._expected_role(stage, role)
            manifest = D.build_manifest(source, expected)
            if stage in self.manifests and manifest["manifest_sha256"] != self.manifests[stage].get(role):
                raise LifecycleRefused("the working role changed after it was verified and journaled")
            self._copy(source, target, sorted(expected))
            restores[role] = D.verify_restore(target, manifest, expected)
            copies[role] = D.directory_identity(target)
        return {"restores": restores, "copies": copies}

    def _verify_backup(self, stage):
        """Read-only: the existing backup must equal the manifests of the working roles. Nothing is copied, completed or repaired."""
        restores, copies = {}, {}
        for role in I.STAGE_ROLES[stage]:
            source, target = self.paths["work"] / stage / role, self.paths["backup"] / stage / role
            expected = self._expected_role(stage, role)
            manifest = D.build_manifest(source, expected)
            if stage in self.manifests and manifest["manifest_sha256"] != self.manifests[stage].get(role):
                raise LifecycleRefused("the working role no longer equals its journaled manifest")
            restores[role] = D.verify_restore(target, manifest, expected)
            copies[role] = D.directory_identity(target)
        return {"restores": restores, "copies": copies}

    @staticmethod
    def _copy(source, target, ordinals):
        """Copy descriptor-last without overwriting; a file that already exists must be byte-identical (idempotent retry)."""
        source_fds, target_fd = D._chain(source), S._open_root(target)
        try:
            present = set(os.listdir(target_fd))
            for ordinal in ordinals:
                part, meta, descriptor = D.shard_names(ordinal)
                for name, cap in ((part, D.MAX_PAYLOAD_BYTES), (meta, D.MAX_METADATA_BYTES), (descriptor, D.MAX_DESCRIPTOR_BYTES)):
                    raw = D._read_regular(source_fds[-1], name, cap, keep=True)[3]
                    if name in present:
                        if D._read_regular(target_fd, name, cap, keep=True)[3] != raw:
                            raise LifecycleRefused("backup already holds different bytes under this name")
                        continue
                    S._publish(target_fd, name, raw)
        finally:
            D._close(source_fds)
            os.close(target_fd)

    def complete_stage(self):
        """SYNTHETIC_BACKUP_VERIFIED -> SYNTHETIC_STAGE_COMPLETE after fresh trusted evidence and the E16 after-boundary report."""
        self._require("SYNTHETIC_BACKUP_VERIFIED")
        stage = self.stage
        try:
            trusted = self._trusted_check()
            if not self._trust_ok(trusted["report"]):
                return self._trust_failure(trusted, "stage boundary")
            self._trusted = trusted
            self._remember_grant()
            self._journal("boundary_check", {"phase": "complete", "stage": stage, "revocation_sha256": trusted["report"]["revocation"]["evidence_sha256"]})
            boundary = self._boundary(AFTER_BOUNDARY[stage])
            if self._dispose(boundary) is not None:
                return self
            self._journal("boundary_check", {"phase": "stage_complete", "stage": stage, "boundary": AFTER_BOUNDARY[stage]})
        except JournalUnavailable:
            return self._fail_journal()
        except (OSError, LifecycleRefused, D.DurabilityRefused, S.StorageRefused, ValueError, KeyError) as error:
            return self._block("completion evidence could not be assembled", error=type(error).__name__, detail=str(error)[:120])
        self.completed.append(stage)
        self._move("SYNTHETIC_STAGE_COMPLETE", "complete_stage", boundary=AFTER_BOUNDARY[stage], conditions=len(boundary["conditions"]))
        self.stage_index += 1
        self._shards_this_attempt, self._first_shard, self._last_refresh = 0, None, 0
        if self.stage is not None:
            self._move("PREPARED", "next_stage", next=self.stage)
        return self

    # ---- driving the cycle ---------------------------------------------------------------------------------
    def retry(self):
        """BLOCKED -> PREPARED (evidence is verified again from scratch), or back to the backup-verified state when only the stage-end check blocked."""
        self._require("BLOCKED")
        return self._move("SYNTHETIC_BACKUP_VERIFIED" if self._blocked_from == "SYNTHETIC_BACKUP_VERIFIED" else "PREPARED", "retry")

    def step(self):
        """Exactly one lifecycle method, chosen by the state. Halted states do nothing."""
        action = {"PREPARED": self.verify_evidence, "EVIDENCE_VERIFIED": self.check_admission, "ADMISSION_CHECKED": self.run_stage,
                  "SYNTHETIC_STAGE_RUNNING": lambda: self.verify_stage() if self._stage_fully_admitted() else self.run_stage(),
                  "SYNTHETIC_STAGE_VERIFIED": self.backup_stage, "SYNTHETIC_BACKUP_VERIFIED": self.complete_stage}.get(self.state)
        if action is not None and self.stage is not None:
            action()
        return self

    def advance(self):
        """Run the current stage through its full cycle, stopping at the first refusal."""
        target = self.stage_index
        while self.stage_index == target and self.state not in ("BLOCKED", "STOPPED", "QUARANTINED"):
            self.step()
        return self

    def run_all(self):
        while self.stage is not None and self.state not in ("BLOCKED", "STOPPED", "QUARANTINED"):
            self.advance()
        return self

    # ---- interruption and recovery ------------------------------------------------------------------------
    def interrupt(self, signal="SIGTERM"):
        """Controlled stop between shards. Recoverable only by a new controller under identical request/source identities."""
        if self.state in ("STOPPED", "QUARANTINED"):
            raise InvalidTransition("already halted")
        if not isinstance(signal, str) or not 0 < len(signal) <= 40 or signal == "PRODUCER_FAILURE":
            raise LifecycleRefused("a signal name is required")
        self._interruptions += 1
        return self._stop("controlled interruption", resumable=True, incident=("interruption", {"attempt": self._attempt, "signal": signal}), signal=signal)

    def _check_identities(self):
        if self.profile.workspace.validate(self.plan) != self.identities:
            raise LifecycleRefused("a synthetic root was replaced or aliased")
        reference = self.profile.reference_source(self.profile.clock.now())
        source = self.plan["source"]
        if reference["head"] != source["git_commit"] or reference["files_sha256"] != source["files_sha256"] or reference["tools_sha256"] != source["tools_sha256"]:
            raise LifecycleRefused("source identity changed")
        self._verified_ledger()

    def _load_journal(self):
        anchor = self.anchors.latest()
        verified = L.verify_chain(self.ledger.read(), expected_head=anchor)
        if anchor is None or not verified["ok"]:
            raise LifecycleRefused("the journal does not verify against an independently retained anchor")
        if verified["count"] not in (anchor["seq"] + 1, anchor["seq"] + 2):     # a crash between append and anchor can leave exactly one entry ahead
            raise LifecycleRefused("the ledger holds more than one entry that was never anchored")
        entries = verified["entries"]
        head = {"seq": entries[-1]["seq"], "entry_sha256": entries[-1]["entry_sha256"]}
        if head != anchor:
            self.anchors.record(head)               # adopt the single trailing entry only after the whole chain verified
        self._anchor_seen = head
        self._run_opened_at = entries[0]["at"]
        if not entries or entries[0]["kind"] != "run_opened" or entries[0]["data"] != self.identity:
            raise LifecycleRefused("the journal belongs to a different plan or specification")
        completed, pending, floors = [], False, {}
        for entry in entries:
            kind, stage, data = entry["kind"], entry["stage"], entry["data"]
            if kind == "stop":
                raise LifecycleRefused("the run was stopped for good (" + str(data.get("reason"))[:80] + "); a human decision and new evidence are required")
            if kind == "incident":
                if data["action"] != RESUMABLE_ACTION:
                    raise LifecycleRefused("incident " + data["incident"] + " halted the run; it cannot be resumed")
                if data["details"]["signal"] == "PRODUCER_FAILURE":
                    self._failed_attempts += 1
                else:
                    self._interruptions += 1
                pending = True
            elif kind == "resume":
                self._attempt += 1
                pending = False
            elif kind == "authorization_snapshot":
                if data.get("record_sha256") != self.plan["authorization"]["record_sha256"]:
                    raise LifecycleRefused("the journal names a different authorization record")
            elif kind == "stage_bound":
                self.stage_fingerprints[stage] = data["request_fingerprint"]
                self._bound.add(stage)
                self._journaled.add((stage, kind))
            elif kind == "shard_admitted":
                for key, name in (("wall_s", "elapsed_wall_s"), ("cpu_s", "cpu_core_s")):
                    value = data.get(key)
                    if type(value) in (int, float) and value >= 0:
                        floors[name] = max(floors.get(name, 0.0), float(value))
            elif kind in ("stage_completed", "backup_verified"):
                self._journaled.add((stage, kind))
                if kind == "stage_completed":
                    self.manifests[stage] = data["manifests"]
            elif kind == "k17d_check":
                self._journaled.add((None, kind))
            elif kind == "boundary_check":
                if data.get("phase") == "stage_complete":
                    completed.append(stage)
                elif data.get("phase") == "admission":
                    self._admitted_marker.add(stage)
        if completed != list(STAGES[:len(completed)]):
            raise LifecycleRefused("completed stages are not a prefix of known -> test -> matched")
        for stage in completed:
            if (stage, "stage_completed") not in self._journaled or (stage, "backup_verified") not in self._journaled or stage not in self.manifests:
                raise LifecycleRefused("a stage is marked complete without its journaled verification and backup")
        for stage in STAGES[1:]:
            if stage in self._bound:
                predecessors = {s: self.manifests.get(s) for s in STAGES[:STAGES.index(stage)]}
                if not all(predecessors.values()):
                    raise LifecycleRefused("a later stage is bound without its predecessor's manifests (stage order)")
                kept = self.stage_fingerprints.pop(stage)
                self._derive_binding(stage)
                if self.stage_fingerprints[stage] != kept:
                    raise LifecycleRefused("a journaled request binding differs from the one derived from the completed predecessors")
        self.completed, self.stage_index = completed, len(completed)
        self._journal_open = True
        self._pending_interruption = pending
        if floors:                                   # the resource port must continue from the journaled counters, never restart from zero
            self._last_machine = {"elapsed_wall_s": floors.get("elapsed_wall_s", 0.0), "cpu_core_s": floors.get("cpu_core_s", 0.0)}

    def _rebuild_disk(self):
        """Re-admit every committed shard (verify, fsync, verify) and compare with what the journal recorded."""
        journaled = {}
        for entry in L.verify_chain(self.ledger.read(), expected_head=self.anchors.latest())["entries"]:
            if entry["kind"] == "shard_admitted":
                journaled[(entry["stage"], entry["data"]["role"], entry["data"]["ordinal"])] = entry["data"]["descriptor_sha256"]
        for stage in STAGES[:min(self.stage_index + 1, len(STAGES))]:
            if stage not in self._bound or (stage not in self._admitted_marker and stage not in self.completed):
                continue                             # never admitted: nothing was produced, the admission boundary will judge the directories
            for role in I.STAGE_ROLES[stage]:
                directory, expected = self.paths["work"] / stage / role, self._expected_role(stage, role)
                try:
                    report = D.classify_directory(directory, expected)
                except (OSError, D.DurabilityRefused) as error:
                    return self._quarantine("recovery cannot classify a role directory: " + type(error).__name__)
                if report["resume_state"] == "NEEDS_QUARANTINE":
                    return self._quarantine("orphaned or damaged shard state at recovery", role_dir=(directory, expected), incident=(
                        "orphan_files", {"role": role, "files": (report["unexpected_entries"] + report["quarantine_required"])[:8]}))
                admitted = {}
                for ordinal in sorted(int(o) for o, s in report["shards"].items() if s["state"] == "COMMITTED"):
                    admission = D.admit_shard(directory, ordinal, expected[ordinal])
                    try:
                        self._check_adopted(directory, ordinal, self.layout[stage][role][ordinal])
                    except (LifecycleRefused, D.DurabilityRefused) as error:
                        return self._quarantine("a committed shard breaks the fabricated-bytes-only contract: " + str(error)[:100], role_dir=(directory, expected),
                                                incident=("shard_corruption", {"role": role, "ordinal": ordinal,
                                                                               "expected_sha256": journaled.get((stage, role, ordinal), "0" * 64),
                                                                               "observed_sha256": admission["descriptor_sha256"]}))
                    recorded = journaled.get((stage, role, ordinal))
                    if recorded is not None and recorded != admission["descriptor_sha256"]:
                        return self._quarantine("on-disk shard differs from its journaled admission", role_dir=(directory, expected), incident=(
                            "shard_corruption", {"role": role, "ordinal": ordinal, "expected_sha256": recorded, "observed_sha256": admission["descriptor_sha256"]}))
                    admitted[ordinal] = admission
                missing = sorted(o for (s, r, o) in journaled if s == stage and r == role and o not in admitted)
                if missing:
                    return self._quarantine("journaled shards are missing from disk", role_dir=(directory, expected), incident=(
                        "shard_corruption", {"role": role, "ordinal": missing[0], "expected_sha256": journaled[(stage, role, missing[0])], "observed_sha256": "0" * 64}))
                self._admissions[(stage, role)] = admitted
                if stage in self.manifests and D.build_manifest(directory, expected)["manifest_sha256"] != self.manifests[stage].get(role):
                    return self._quarantine("a completed role no longer matches its journaled manifest", role_dir=(directory, expected), incident=(
                        "shard_corruption", {"role": role, "ordinal": 0, "expected_sha256": self.manifests[stage].get(role, "0" * 64), "observed_sha256": "0" * 64}))
        for stage in self.completed:
            try:
                self._raw_backup[stage] = self._verify_backup(stage)
            except (OSError, D.DurabilityRefused, S.StorageRefused, LifecycleRefused) as error:
                return self._quarantine("backup of a completed stage no longer verifies: " + type(error).__name__,
                                        incident=("backup_mismatch", {"role": "backup", "manifest_sha256": _digest(self.manifests.get(stage, {}))}))

    def _check_adopted(self, directory, ordinal, shard):
        part, meta, _ = D.shard_names(ordinal)
        fds = D._chain(directory)
        try:
            payload = D._read_regular(fds[-1], part, MAX_SYNTHETIC_PAYLOAD, keep=True)[3]
            metadata = D._read_regular(fds[-1], meta, MAX_SYNTHETIC_METADATA, keep=True)[3]
        finally:
            D._close(fds)
        self._check_synthetic(payload, metadata, shard)

    def _record_restart(self):
        """Journal the restart: an unresolved interruption is closed by ``resume``; an unannounced exit is recorded as one first."""
        if not self._pending_interruption:
            self._interruptions += 1
            self._journal("incident", L.incident_data("interruption", {"attempt": self._attempt, "signal": "UNCLEAN_EXIT_INFERRED"}), stage=None)
        self._attempt += 1
        self._journal("resume", dict(self.identity), stage=None)
        self._event("recover", None, "PREPARED", attempt=self._attempt, admitted=sum(len(a) for a in self._admissions.values()))

    # ---- observation ------------------------------------------------------------------------------------
    def journal_entries(self):
        return L.verify_chain(self.ledger.read(), expected_head=self.anchors.latest())["entries"]

    def summary(self):
        return {"schema": SCHEMA_SUMMARY, "state": self.state, "stage": self.stage, "completed_stages": list(self.completed),
                "attempt": self._attempt, "failed_attempts": self._failed_attempts, "interruptions": self._interruptions,
                "admitted_shards": sum(len(a) for a in self._admissions.values()), "events": len(self._events),
                "journal_ok": self._journal_ok, "synthetic": True, "evidence_scope": "SYNTHETIC_TEST_ROOT",
                "k17d_production_cross_check": "NOT_RUN", "attestations": "FABRICATED_SYNTHETIC", "production_gate": "BLOCKED",
                **{**NO_AUTHORITY, "production_launch_enabled": bool(G.sup.PRODUCTION_LAUNCH_ENABLED)}}
