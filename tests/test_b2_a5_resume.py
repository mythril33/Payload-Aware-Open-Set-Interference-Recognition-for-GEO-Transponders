"""An interrupted A5 invocation continues from verified per-scene state instead of restarting (P28 §11).

Interruptions are simulated at every place a process can die: between scenes, during an array write, between
the last scene and the final result, and between the result and its checksum. Verified progress is reused;
anything unverifiable is rejected rather than silently recomputed over.
"""
import fcntl
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import b2_a5_support as support
from geoml import b2_a5 as a5
from geoml.artifacts import fingerprint

ROOT = Path(__file__).parent.parent
IGNORED = ("cost", "reproduction_command", "resume")


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    support.install_fakes(monkeypatch)


def _config(**overrides):
    base = {"perturbation": "drop_one", "scope": "co_only", "n_groups": 2, "labels": ("clean", "unauthorized"),
            "views": ("co", "dual_residual")}
    return a5.A5Config(**{**base, **overrides})


def _run(out, config=None, logs=None):
    ws = support.workspace()
    return a5.run_a5(config or _config(), ws / "known", ws / "runs", out, log=(logs.append if logs is not None else (lambda *_: None)))


def _same(first, second):
    return {k: v for k, v in first.items() if k not in IGNORED} == {k: v for k, v in second.items() if k not in IGNORED}


def _interrupt_after(monkeypatch, scenes):
    real, calls = a5.replay_scene, {"n": 0}

    def replay(*args, **kwargs):
        if calls["n"] >= scenes:
            raise KeyboardInterrupt("simulated process death")
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(a5, "replay_scene", replay)
    return real


def test_interrupted_run_resumes_with_only_the_missing_scenes_and_equals_an_uninterrupted_run(tmp_path, monkeypatch):
    reference = _run(tmp_path / "reference")
    real = _interrupt_after(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out")
    assert not (tmp_path / "out" / "results.json").exists()
    assert sorted(p.name for p in (tmp_path / "out" / "state").glob("scene-*.json")) == [
        "scene-3200000-clean.json", "scene-3200000-unauthorized.json"]
    monkeypatch.setattr(a5, "replay_scene", real)
    calls, logs = [], []
    monkeypatch.setattr(a5, "replay_scene", lambda *a, **k: calls.append(1) or real(*a, **k))
    resumed = _run(tmp_path / "out", logs=logs)
    assert len(calls) == 2                                                   # only the two missing scenes are replayed
    assert resumed["resume"]["scenes_from_state"] == 2 and resumed["resume"]["scenes_computed_now"] == 2
    assert resumed["resume"]["replays_now"] == 2 and resumed["counts"]["physical_replays"] == 4   # logical total is unchanged
    assert any("resumed 2/4 scenes" in line for line in logs)
    assert _same(resumed, reference) and resumed["experiment_fingerprint"] == reference["experiment_fingerprint"]
    assert resumed["parity_summary"]["n_scenes_checked"] == 4 and resumed["parity_summary"]["all_exact"] is True


def test_completed_state_rebuilds_the_result_without_any_replay(tmp_path, monkeypatch):
    reference = _run(tmp_path / "out")
    (tmp_path / "out" / "results.json.sha256").unlink()                      # died between the result and its checksum
    monkeypatch.setattr(a5, "replay_scene", lambda *a, **k: pytest.fail("replayed despite complete verified state"))
    logs = []
    rebuilt = _run(tmp_path / "out", logs=logs)
    assert any("interrupted" in line for line in logs) and rebuilt["resume"]["scenes_from_state"] == 4
    assert _same(rebuilt, reference) and (tmp_path / "out" / "results.json.sha256").exists()
    again = _run(tmp_path / "out")                                           # now complete: plain reuse
    assert again == rebuilt


def test_interrupted_writes_are_discarded_not_trusted(tmp_path, monkeypatch):
    reference = _run(tmp_path / "reference")
    real = _interrupt_after(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out")
    state = tmp_path / "out" / "state"
    (state / "scene-3200000-unauthorized.npz.tmp").write_bytes(b"half written")             # died during an array write
    (state / "scene-3200001-clean.npz").write_bytes(b"arrays committed, json never written")
    (tmp_path / "out" / "results.json.tmp").write_text("{")
    monkeypatch.setattr(a5, "replay_scene", real)
    logs = []
    resumed = _run(tmp_path / "out", logs=logs)
    assert sum("discarded" in line for line in logs) == 3 and _same(resumed, reference)
    assert not list((tmp_path / "out").rglob("*.tmp"))


def test_modified_committed_state_fails_closed(tmp_path, monkeypatch):
    real = _interrupt_after(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out")
    monkeypatch.setattr(a5, "replay_scene", real)
    state = tmp_path / "out" / "state"
    pristine = tmp_path / "pristine"
    shutil.copytree(tmp_path / "out", pristine)
    data = bytearray((state / "scene-3200000-unauthorized.npz").read_bytes())
    data[len(data) // 2] ^= 0xFF
    (state / "scene-3200000-unauthorized.npz").write_bytes(bytes(data))
    with pytest.raises(ValueError, match="missing or modified"):
        _run(tmp_path / "out")
    shutil.rmtree(tmp_path / "out")
    shutil.copytree(pristine, tmp_path / "out")
    path = tmp_path / "out" / "state" / "scene-3200000-clean.json"
    meta = json.loads(path.read_text())
    meta["scenario_id"] = 3200001
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="different scene or experiment identity"):
        _run(tmp_path / "out")
    shutil.rmtree(tmp_path / "out")
    shutil.copytree(pristine, tmp_path / "out")
    path = tmp_path / "out" / "state" / "scene-3200000-clean.json"
    meta = json.loads(path.read_text())
    meta["record"]["corrupted_identity"] = "0" * 64
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="payload digest"):                       # any edit of the JSON payload is detected
        _run(tmp_path / "out")
    meta["payload_sha256"] = fingerprint({key: meta[key] for key in a5.STATE_KEYS})   # a consistent re-sign is caught by the recomputation
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="no longer matches its recomputed corruption"):
        _run(tmp_path / "out")


def test_state_is_bound_to_the_experiment_identity(tmp_path, monkeypatch):
    real = _interrupt_after(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out")
    monkeypatch.setattr(a5, "replay_scene", real)
    with pytest.raises(ValueError, match="different experiment identity"):
        _run(tmp_path / "out", _config(perturbation="phantom"))
    other_runs = tmp_path / "runs"
    shutil.copytree(support.workspace() / "runs", other_runs)
    reported = json.loads((other_runs / "results.json").read_text())
    reported["note"] = "edited"
    (other_runs / "results.json").write_text(json.dumps(reported))        # any frozen-run file change is a new identity
    with pytest.raises(ValueError, match="different experiment identity"):
        a5.run_a5(_config(), support.workspace() / "known", other_runs, tmp_path / "out", log=lambda *_: None)


def test_orphan_checksum_without_result_is_rejected(tmp_path):
    _run(tmp_path / "out")
    (tmp_path / "out" / "results.json").unlink()
    with pytest.raises(ValueError, match="has no results.json"):
        _run(tmp_path / "out")


def test_not_applicable_scenes_are_recorded_as_progress_too(tmp_path, monkeypatch):
    config = _config(perturbation="authorize_intruder")
    reference = _run(tmp_path / "reference", config)
    real = _interrupt_after(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out", config)
    monkeypatch.setattr(a5, "replay_scene", real)
    resumed = _run(tmp_path / "out", config)
    assert _same(resumed, reference) and resumed["resume"]["scenes_from_state"] >= 3


def _crashed_state(tmp_path, monkeypatch, scenes=2):
    real = _interrupt_after(monkeypatch, scenes)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path / "out")
    monkeypatch.setattr(a5, "replay_scene", real)
    return tmp_path / "out" / "state"


def _edit(path, edit):
    meta = json.loads(path.read_text())
    edit(meta)
    path.write_text(json.dumps(meta))


def test_every_field_of_a_committed_scene_state_is_covered_by_its_digest(tmp_path, monkeypatch):
    state = _crashed_state(tmp_path, monkeypatch)
    pristine = tmp_path / "pristine"
    shutil.copytree(tmp_path / "out", pristine)
    edits = {"parity": lambda m: m["parity"]["spec"].update(exact=not m["parity"]["spec"]["exact"], max_abs_diff_db=0.1),
             "work": lambda m: m["work"].update(replays=m["work"]["replays"] + 7),
             "flags": lambda m: m["record"]["flags"].update(co_dropped_carrier_transmitted="edited"),
             "recomputed": lambda m: m["record"].update(residual_recomputed="edited"),
             "descriptors": lambda m: m["record"]["descriptors"]["co"].update(removed_indices=[99])}
    for name, edit in edits.items():
        shutil.rmtree(tmp_path / "out")
        shutil.copytree(pristine, tmp_path / "out")
        _edit(tmp_path / "out" / "state" / "scene-3200000-unauthorized.json", edit)
        with pytest.raises(ValueError, match="payload digest"):
            _run(tmp_path / "out")


def test_array_presence_must_match_the_applied_status_even_when_resigned(tmp_path, monkeypatch):
    state = _crashed_state(tmp_path, monkeypatch)

    def drop_arrays(meta):
        meta["arrays_sha256"] = None
        meta["payload_sha256"] = fingerprint({key: meta[key] for key in a5.STATE_KEYS})

    _edit(state / "scene-3200000-unauthorized.json", drop_arrays)
    with pytest.raises(ValueError, match="arrays must exist exactly for applied scenes"):
        _run(tmp_path / "out")


def test_malformed_state_raises_value_errors_not_tracebacks(tmp_path, monkeypatch):
    state = _crashed_state(tmp_path, monkeypatch)
    pristine = tmp_path / "pristine"
    shutil.copytree(tmp_path / "out", pristine)
    cases = {"scene-3200000-clean.json": ["[]", "{}", "not json", json.dumps({"experiment_fingerprint": "x"})],
             "identity.json": ["[]", "not json"]}
    for name, contents in cases.items():
        for content in contents:
            shutil.rmtree(tmp_path / "out")
            shutil.copytree(pristine, tmp_path / "out")
            (tmp_path / "out" / "state" / name).write_text(content)
            with pytest.raises(ValueError):
                _run(tmp_path / "out")


def test_state_written_under_another_environment_is_refused(tmp_path, monkeypatch):
    state = _crashed_state(tmp_path, monkeypatch)
    _edit(state / "identity.json", lambda m: m["environment"].update(numpy="0.0.0"))
    with pytest.raises(ValueError, match="different library/platform environment"):
        _run(tmp_path / "out")


def test_only_own_temporaries_are_removed_and_only_from_a_matching_directory(tmp_path):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "someone_elses.tmp").write_text("keep")
    (foreign / "results.json").write_text(json.dumps({"experiment_fingerprint": "x" * 64}))
    (foreign / "results.json.tmp").write_text("{")
    with pytest.raises(ValueError, match="different experiment identity"):
        _run(foreign)
    assert (foreign / "someone_elses.tmp").read_text() == "keep" and (foreign / "results.json.tmp").exists()   # refused before any cleanup
    stranger = tmp_path / "stranger"
    (stranger / "state").mkdir(parents=True)
    (stranger / "state" / "notes.txt").write_text("not ours")
    with pytest.raises(ValueError, match="not an A5 state directory"):
        _run(stranger)
    assert (stranger / "state" / "notes.txt").exists()
    (tmp_path / "mixed").mkdir()
    (tmp_path / "mixed" / "someone_elses.tmp").write_text("keep")
    _run(tmp_path / "mixed")
    assert (tmp_path / "mixed" / "someone_elses.tmp").read_text() == "keep"          # foreign temporaries are never touched


def test_output_must_be_separate_from_the_inputs(tmp_path):
    ws = support.workspace()
    config = _config()
    for out in (ws / "runs", ws / "known", ws / "known" / "inner", ws):
        with pytest.raises(ValueError, match="separate from the input directory"):
            a5.run_a5(config, ws / "known", ws / "runs", out, log=lambda *_: None)


def test_concurrent_invocation_on_the_same_output_is_refused_and_the_lock_is_released(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with open(out / ".a5.lock", "a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)                   # another process holds the invocation
        with pytest.raises(ValueError, match="another process is running this invocation"):
            _run(out)
    result = _run(out)                                                      # the lock died with its holder: normal run
    assert result["counts"]["physical_replays"] == 4
    again = _run(out)                                                       # and it was released after this run too
    assert again == result


def test_matrix_driver_fails_loudly_instead_of_hiding_failed_or_missing_invocations(tmp_path):
    script = ROOT / "scripts" / "run_b2_a5_pilot_matrix.sh"
    text = script.read_text()
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    assert "set -u -o pipefail" in text and "PIPESTATUS" in text and "MISSING" in text
    assert "unrestricted" not in text and "--train" not in text and "--generate" not in text
    for stand_in, expectation in (("/bin/false", "FAILED"), ("/bin/true", "MISSING")):   # fails loudly / exits 0 without producing results
        done = subprocess.run(["bash", str(script), "none", "none", "none", str(tmp_path / Path(stand_in).name)],
                              env={"PATH": "/usr/bin:/bin", "PYTHON": stand_in}, cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 1 and expectation in done.stdout
        assert done.stdout.count("MISSING") == 25 and "MATRIX_DONE expected=25 failed=1" in done.stdout
