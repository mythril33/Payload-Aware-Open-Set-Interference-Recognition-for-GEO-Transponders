"""Shared fabricated world for the E18 lifecycle tests.

Every key, signature, record, device and shard here is fabricated and lives in a temporary directory. The signing keys come from
the E17 test custody (ephemeral ed25519 keys made by ssh-keygen for the test session only); they are not researcher credentials
and never reach a real entry point. The only thing built from them is a ``SyntheticProfile`` whose trust root is explicitly a
test root.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import b2_e14_launch_contract as C  # noqa: E402
import b2_e16_ledger as L  # noqa: E402
import b2_e17_signatures as Sig  # noqa: E402
import b2_e18_lifecycle as M  # noqa: E402
import b2_e18_synthetic as X  # noqa: E402

CLOCK = X.START
VALIDITY_S = 240


def encoded(document):
    return Sig.canonical(document).encode()


class Authority:
    """Fabricated issuer of fresh, challenge-bound revocation and CI snapshots; knobs let a test withdraw or damage them."""

    def __init__(self, custody, bundle):
        self.custody, self.bundle = custody, bundle
        base = bundle["evidence"]
        self.grant = json.loads(base["revocation"])["grant"]
        self.ci_base = json.loads(base["ci"])
        self.authorization_signature = base["authorization_signature"]
        self.status = "ACTIVE"                   # anything but ACTIVE is an explicit revocation answer
        self.validity_s = VALIDITY_S             # how long the signed answers state that they are valid (E17 accepts at most 300 s)
        self.available = True                    # False: the issuer cannot be reached
        self.ci_runs = None                      # replace the signed CI runs
        self.calls = 0
        self.after_calls = None                  # (n, status): from the n-th call on, answer with this status
        self.unreachable_from = None             # from the n-th call on the issuer cannot be reached
        self.tamper = None                       # callable(evidence) -> evidence, applied last

    def __call__(self, challenge, floor, now):
        self.calls += 1
        if not self.available or (self.unreachable_from is not None and self.calls >= self.unreachable_from):
            raise OSError("fabricated issuer unreachable")
        issued = datetime.fromisoformat(now)
        expires = (issued + timedelta(seconds=self.validity_s)).isoformat()
        status = self.status
        if self.after_calls is not None and self.calls >= self.after_calls[0]:
            status = self.after_calls[1]
        revocation = {"schema": "B2-E17-revocation-status/1", "issuer": self.custody["root"].revocation_principal, "grant": self.grant,
                      "status": status, "issued_at": now, "expires_at": expires, "sequence": floor, "challenge": challenge}
        ci = dict(self.ci_base, issued_at=now, expires_at=expires, sequence=floor, challenge=challenge)
        if self.ci_runs is not None:
            ci["runs"] = self.ci_runs
        rev_raw, ci_raw = encoded(revocation), encoded(ci)
        evidence = {"policy": self.custody["policy"], "authorization_signature": self.authorization_signature,
                    "revocation": rev_raw, "revocation_signature": self.custody["sign"](rev_raw, "revocation"),
                    "ci": ci_raw, "ci_signature": self.custody["sign"](ci_raw, "ci")}
        return evidence if self.tamper is None else self.tamper(evidence)


def make_workspace(base):
    paths = {}
    for name in M.Workspace.ROLES:
        path = Path(base) / name
        path.mkdir(parents=True)
        os.chmod(path, 0o755)
        paths[name] = path
    return M.Workspace(**paths)


def workspace_at(base):
    return M.Workspace(**{name: Path(base) / name for name in M.Workspace.ROLES})


def last_journal_instant(workspace):
    """Timestamp of the newest ledger entry of a copied workspace (a restarted process never runs its clock backwards)."""
    entries = L.verify_chain((Path(workspace.journal) / L.LEDGER_NAME).read_bytes())["entries"]
    return entries[-1]["at"]


def make_profile(base, custody, bundle, *, authority=None, s_per_observation=4.4, mutate=None, base_wall_s=0.0, plan=None, consumers=None,
                 workspace=None, start=CLOCK, reference_hook=None, producer_factory=None):
    """A complete synthetic profile on a fresh (or an existing, copied) temporary workspace."""
    plan = copy.deepcopy(bundle["plan"] if plan is None else plan)
    spec = C.build_specification(plan)
    workspace = make_workspace(base) if workspace is None else workspace
    clock = X.SyntheticClock(start)
    authority = Authority(custody, bundle) if authority is None else authority

    def reference_source(now):
        reference = copy.deepcopy(bundle["reference"])
        reference["evaluated_at"] = now
        return reference if reference_hook is None else reference_hook(reference)

    profile = M.SyntheticProfile(
        plan=plan, specification=spec, repo=bundle["repo"], trust_root=bundle["root"], reference_source=reference_source,
        evidence_source=authority, producer=X.SyntheticShardProducer(clock, s_per_observation) if producer_factory is None else producer_factory(clock), clock=clock,
        resources=X.SyntheticResources(clock, mutate=mutate, base_wall_s=base_wall_s), attestor=X.SyntheticAttestor(plan, workspace),
        workspace=workspace, consumers=consumers)
    return profile, authority


# ---- cached worlds: one complete run and one stage-boundary snapshot per test session ----------------------------------------

_WORLDS = {}


def world(name, tmp_path_factory, custody, bundle):
    """A finished synthetic workspace, built once and copied per test: ``known`` (stage 1 complete), ``complete`` (all three stages) or
    ``admitted`` (every known shard admitted, nothing verified, backed up or completed; the process then 'dies')."""
    if name not in _WORLDS:
        base = Path(tmp_path_factory.mktemp("e18-world-" + name))
        profile, authority = make_profile(base / "w", custody, bundle)
        life = M.SyntheticExecutorLifecycle(profile)
        if name == "admitted":
            life.verify_evidence()
            life.check_admission()
            life.run_stage()
            assert life.state == "SYNTHETIC_STAGE_RUNNING" and life._stage_fully_admitted() and not life.completed
        else:
            stages = {"known": 1, "complete": 3}[name]
            for _ in range(stages):
                life.advance()
            assert life.state in ("PREPARED", "SYNTHETIC_STAGE_COMPLETE") and len(life.completed) == stages, life.events[-3:]
        _WORLDS[name] = {"base": base / "w", "custody": custody, "bundle": bundle, "summary": life.summary(), "events": life.events,
                         "boundary_reports": life.boundary_reports, "plan": profile.plan}
        life.close()
    return _WORLDS[name]


def restart_profile(workspace, custody, bundle, plan, **kwargs):
    """A fresh profile (new clock, producer, resources) for a workspace that already holds a journal: time continues after its last entry."""
    last = datetime.fromisoformat(last_journal_instant(workspace))
    start = (last + timedelta(seconds=1)).isoformat()
    wall = (last - datetime.fromisoformat(CLOCK)).total_seconds() + 1
    kwargs.setdefault("start", start)
    kwargs.setdefault("base_wall_s", wall)
    return make_profile(None, custody, bundle, workspace=workspace, plan=plan, **kwargs)


def copy_world(name, source, destination, *, prepare=None, **kwargs):
    """An independent copy of a cached world and a recovery profile whose clock continues after the journal's last instant.

    ``prepare(workspace)`` runs on the copy before the profile (and so its clock) is derived, for out-of-band changes to the journal."""
    shutil.copytree(source["base"], destination, symlinks=True)
    workspace = workspace_at(destination)
    if prepare is not None:
        prepare(workspace)
    return restart_profile(workspace, source["custody"], source["bundle"], source["plan"], **kwargs)


def assert_no_authority(value):
    assert value["execution_permitted"] is False and value["authorizes_nothing"] is True
    assert value["production_launch_enabled"] is False and value["benchmark_complete"] is False
    assert value["production_running_state"] is False and value["verdict"] == "NO-GO"
    json.dumps(value, allow_nan=False)


def journal_of(life):
    return life.journal_entries()


def incidents(life):
    return [e["data"]["incident"] for e in life.journal_entries() if e["kind"] == "incident"]


def kinds(life):
    return [e["kind"] for e in life.journal_entries()]


def halted(life):
    return life.state in ("BLOCKED", "STOPPED", "QUARANTINED")


def tree_digest(path):
    """sha256 over every file name and byte below ``path`` (evidence must be preserved byte for byte)."""
    import hashlib
    digest = hashlib.sha256()
    for item in sorted(Path(path).rglob("*")):
        digest.update(str(item.relative_to(path)).encode() + b"\0")
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


# ---- fixtures shared by the E18 test modules (import them together with ``custody`` and ``integrated``) -----------------------

def discard(path):
    """Remove a scratch tree, including directories a test left read-only (symbolic links are unlinked, never followed)."""
    pending = [Path(path)]
    while pending:
        current = pending.pop()
        try:
            if not current.is_symlink() and current.is_dir():
                os.chmod(current, 0o755)
                pending.extend(current.iterdir())
        except OSError:
            pass
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def scratch(tmp_path, request):
    """Return each passing test's temporary tree (copied ~20 MB / ~5k-file worlds, journals, clones) as soon as the test is over.

    Pytest keeps every passing test's ``tmp_path`` for the whole session; a few hundred world copies exhausted the CI runner's disk
    quota and failed unrelated tests that run later in the same suite. The cached worlds live in ``tmp_path_factory`` and stay.
    A failing test's tree is kept for the post-mortem (the failure count is updated before teardown runs)."""
    failed_before = request.session.testsfailed
    yield tmp_path
    if request.session.testsfailed == failed_before:
        discard(tmp_path)


@pytest.fixture
def make(tmp_path, custody, integrated):
    created = []

    def build(name="w", **kwargs):
        profile, authority = make_profile(tmp_path / name, custody, integrated, **kwargs)
        life = M.SyntheticExecutorLifecycle(profile)
        created.append(life)
        return life, profile, authority

    def adopt(life):
        created.append(life)
        return life

    build.adopt = adopt
    yield build
    for life in created:
        life.close()


@pytest.fixture(scope="module")
def complete(tmp_path_factory, custody, integrated):
    return world("complete", tmp_path_factory, custody, integrated)


@pytest.fixture(scope="module")
def known(tmp_path_factory, custody, integrated):
    return world("known", tmp_path_factory, custody, integrated)


@pytest.fixture(scope="module")
def all_admitted(tmp_path_factory, custody, integrated):
    return world("admitted", tmp_path_factory, custody, integrated)


def admitted(life):
    life.verify_evidence()
    life.check_admission()
    return life


def append_entry(workspace, kind, stage, data):
    """Append a well-formed ledger entry out of band (a hostile or mistaken operator who can write the journal and its anchor)."""
    ledger, anchors = L.Ledger(workspace.journal), M.AnchorStore(workspace.anchors)
    at = (datetime.fromisoformat(last_journal_instant(workspace)) + timedelta(seconds=1)).isoformat()
    entry = ledger.append(kind, stage, data, at, expected_head=anchors.latest())
    anchors.record({"seq": entry["seq"], "entry_sha256": entry["entry_sha256"]})
    return entry


def writable(path):
    os.chmod(path, 0o644)
    return Path(path)


def append_unanchored(workspace, kind, stage, data):
    """Append a well-formed ledger entry *without* recording its head (a crash between the append and the anchor, or a forger without anchor access)."""
    at = (datetime.fromisoformat(last_journal_instant(workspace)) + timedelta(seconds=1)).isoformat()
    return L.Ledger(workspace.journal).append(kind, stage, data, at, expected_head=M.AnchorStore(workspace.anchors).latest())
