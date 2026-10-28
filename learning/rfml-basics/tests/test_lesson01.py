"""Tests for lesson 01: load the script by file path (no package import) and run it."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import torch

LESSON_PATH = Path(__file__).resolve().parents[1] / "lessons" / "01_tensors_autograd.py"


def _load_lesson():
    spec = importlib.util.spec_from_file_location("lesson01_tensors_autograd", LESSON_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lesson = _load_lesson()


def test_main_runs_to_completion(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(lesson, "RESULTS", tmp_path)  # keep tracked results/ untouched
    lesson.main()
    out = capsys.readouterr().out
    for n in range(1, 7):
        assert f"== {n}." in out


def test_results_are_strict_json_and_png_written(monkeypatch, tmp_path):
    monkeypatch.setattr(lesson, "RESULTS", tmp_path)  # keep tracked results/ untouched
    lesson.main()
    text = (lesson.RESULTS / "01_tensors_autograd.json").read_text()

    def _reject(token: str):
        raise ValueError(f"non-strict JSON constant {token}")

    data = json.loads(text, parse_constant=_reject)
    assert abs(data["hand_w_b"][0] - data["nn_w_b"][0]) < 1e-4
    assert (lesson.RESULTS / "01_tensors_autograd.png").stat().st_size > 0


def test_hand_gradient_matches_autograd_on_random_data():
    torch.manual_seed(1)
    x, y = lesson.make_data(50)
    w = torch.tensor(0.7, requires_grad=True)
    b = torch.tensor(-0.3, requires_grad=True)
    ((w * x + b - y) ** 2).mean().backward()
    gw, gb = lesson.mse_grads_by_hand(w.detach(), b.detach(), x, y)
    assert torch.allclose(gw, w.grad, atol=1e-6)
    assert torch.allclose(gb, b.grad, atol=1e-6)


def test_hand_gradient_worked_example():
    # x=[1,2], y=[1,1], w=b=0 -> residual=[-1,-1]
    # dL/dw = mean(2*(-1)*[1,2]) = -3 ; dL/db = mean(2*(-1)) = -2
    x = torch.tensor([1.0, 2.0])
    y = torch.tensor([1.0, 1.0])
    gw, gb = lesson.mse_grads_by_hand(torch.tensor(0.0), torch.tensor(0.0), x, y)
    assert gw.item() == -3.0
    assert gb.item() == -2.0


def test_lesson_stands_alone():
    # AST check: the docstring may mention rfml, but no import statement may.
    tree = ast.parse(LESSON_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.split(".")[0] == "rfml" for name in imported)
