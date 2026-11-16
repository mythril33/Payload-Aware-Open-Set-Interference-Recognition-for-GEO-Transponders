"""Campaign boundary checks; no RF generation, fitting or test inference."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.cpu_delivery.run import ROOT, prepare


@pytest.fixture(autouse=True)
def adequate_disk_for_metadata_tests(monkeypatch):
    # These tests write only small JSON metadata, not the generated RF data.
    monkeypatch.setattr("research.cpu_delivery.run.shutil.disk_usage",
                        lambda _: SimpleNamespace(free=2 * 2**30))


def test_all_fit_recipes_are_frozen_before_execution_and_resume_is_identical(tmp_path):
    cfg, out = prepare(tmp_path / "campaign")
    frozen = (out / "campaign.json").read_bytes()
    assert [json.loads((out / f"config-{s}.json").read_text())["training"]["seed"]
            for s in cfg["training_seeds"]] == [0, 1, 2]
    assert not (out / "known").exists()
    prepare(out, resume=True)
    assert (out / "campaign.json").read_bytes() == frozen
    with pytest.raises(ValueError, match="already exists"):
        prepare(out)


@pytest.mark.parametrize("file", ["campaign.json", "config-1.json"])
def test_resume_refuses_changed_source_or_fit_recipe(tmp_path, file):
    _, out = prepare(tmp_path / "campaign")
    path = out / file
    data = json.loads(path.read_text())
    if file == "campaign.json":
        data["scientific_sources_sha256"]["geoml/train.py"] = "0" * 64
    else:
        data["training"]["epochs"] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        prepare(out, resume=True)


def test_refuse_repository_outputs_and_nonexistent_resume(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        prepare(ROOT / "data" / "cpu-delivery")
    with pytest.raises(ValueError, match="absent"):
        prepare(tmp_path / "missing", resume=True)


def test_resource_floor_refuses_before_creating_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr("research.cpu_delivery.run.shutil.disk_usage",
                        lambda _: SimpleNamespace(free=2**30 - 1))
    with pytest.raises(ValueError, match="free disk"):
        prepare(tmp_path / "campaign")
    assert not (tmp_path / "campaign").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process group cleanup")
def test_interrupt_stops_and_reaps_the_whole_process_group(monkeypatch):
    from research.cpu_delivery import run
    calls = []
    process = SimpleNamespace(pid=123, wait=lambda: calls.append("reaped"))
    monkeypatch.setattr(run.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    run.stop_process_tree(process, None)
    assert calls == [(123, run.signal.SIGKILL), "reaped"]
