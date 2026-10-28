"""Lessons 02-04 against the shared experiments module.

Each lesson runs as a subprocess with --quick into a temporary results directory, so the
committed results/ stay untouched. The JSON must parse strictly, and the lesson's numbers
must equal the stage functions called directly with the quick preset and the lesson's own
seed. That keeps the lessons and the Streamlit app from drifting apart.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from rfml import experiments as ex

ROOT = Path(__file__).resolve().parents[1]
LESSON_DIR = ROOT / "lessons"
M02 = "02_modulation_classification"
M03 = "03_rf_fingerprint"
M04 = "04_open_set"
LESSON_NAMES = (M02, M03, M04)
EXPECTED_KEYS = {
    M02: {"lesson", "mode", "stage", "scale", "seed", "classes", "chance_level", "models"},
    M03: {"lesson", "mode", "runs"},
    M04: {"lesson", "mode", "stage", "scale", "seed", "target_known_accept", "objectosphere", "chance", "variants"},
}


def _load_lesson(name: str):
    """Import a lesson file by path. Importing runs no main(), so no output is written."""
    spec = importlib.util.spec_from_file_location(f"lesson_{name}", LESSON_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reject_constant(token: str):
    raise ValueError(f"non-strict JSON constant {token}")


def _strict_load(path: Path) -> dict:
    return json.loads(path.read_text(), parse_constant=_reject_constant)


def _direct(result: dict) -> dict:
    """A stage result as the lesson writes it: JSON-strict, with no NaN or inf."""
    return json.loads(ex.to_strict_json(result))


def _without_lesson_keys(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in ("lesson", "mode")}


@pytest.fixture(scope="module")
def quick_results(tmp_path_factory) -> Path:
    """Run each lesson once with --quick. The lessons write to this temporary directory only."""
    out_dir = tmp_path_factory.mktemp("lesson_results")
    env = {**os.environ, "RFML_RESULTS_DIR": str(out_dir)}
    for name in LESSON_NAMES:
        proc = subprocess.run(
            [sys.executable, str(LESSON_DIR / f"{name}.py"), "--quick"],
            cwd=out_dir,  # the lessons must work from any working directory
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, f"{name} exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return out_dir


@pytest.fixture
def four_threads():
    """The lessons call torch.set_num_threads(4) in main(); match it here so the numbers compare exactly."""
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("name", LESSON_NAMES)
def test_quick_json_is_strict_and_has_expected_keys(quick_results, name):
    data = _strict_load(quick_results / f"{name}.json")  # raises on NaN, Infinity or -Infinity
    assert EXPECTED_KEYS[name] <= data.keys()
    assert data["lesson"] == name
    assert data["mode"] == "quick"
    assert (quick_results / f"{name}.png").stat().st_size > 0


def test_default_results_dir_is_the_repo_results_directory(monkeypatch):
    """Without the override, the lessons write to the committed results/ directory."""
    monkeypatch.delenv("RFML_RESULTS_DIR", raising=False)
    for name in LESSON_NAMES:
        assert _load_lesson(name).RESULTS_DIR == ROOT / "results"


def test_lesson02_quick_equals_run_modulation(quick_results, four_threads):
    lesson = _load_lesson(M02)
    got = _strict_load(quick_results / f"{M02}.json")
    assert got["seed"] == lesson.SEED
    expected = _direct(ex.run_modulation(ex.get_scale("quick"), impaired=True, seed=lesson.SEED))
    assert _without_lesson_keys(got) == expected


def test_lesson03_quick_equals_run_fingerprint(quick_results, four_threads):
    lesson = _load_lesson(M03)
    got = _strict_load(quick_results / f"{M03}.json")
    assert set(got["runs"]) == {"impaired", "ideal_ablation"}
    scale = ex.get_scale("quick")
    assert got["runs"]["impaired"] == _direct(ex.run_fingerprint(scale, impaired=True, seed=lesson.SEED))
    assert got["runs"]["ideal_ablation"] == _direct(ex.run_fingerprint(scale, impaired=False, seed=lesson.SEED))


def test_lesson04_quick_equals_run_open_set(quick_results, four_threads):
    lesson = _load_lesson(M04)
    got = _strict_load(quick_results / f"{M04}.json")
    assert got["seed"] == lesson.SEED
    expected = _direct(
        ex.run_open_set(
            ex.get_scale("quick"),
            lesson.SEED,
            ex.DEFAULT_XI,
            ex.DEFAULT_LAM,
            ex.DEFAULT_TARGET_KNOWN_ACCEPT,
        )
    )
    assert _without_lesson_keys(got) == expected
