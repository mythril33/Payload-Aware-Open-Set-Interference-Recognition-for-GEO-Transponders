"""E7a training-footprint probe: parameter counts, D = 16 x width, byte accounting, strict JSON, caps, no overwrite
and honest basis labels. Everything runs on tiny models/batches; the probe never trains or touches B2 data."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from geoml.data import VIEW_CHANNELS, preprocess_dual
from geoml.model import CenterLoss, SmallResNet, n_parameters

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("b2_training_footprint", ROOT / "scripts" / "b2_training_footprint.py")
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

VIEWS = ("co", "dual", "dual_residual")


def strict(text):
    def reject(constant):
        raise ValueError(constant)
    return json.loads(text, parse_constant=reject)


def expected_parameters(width, in_ch, n_classes=8, aux=1):
    """Independent closed form of the SmallResNet parameter count (bias-free convolutions, BatchNorm affine)."""
    w = width

    def conv(cin, cout, k):
        return cin * cout * k * k

    def bn(c):
        return 2 * c

    total = conv(in_ch, w, 5) + bn(w)
    for cin, cout in ((w, w), (w, 2 * w), (2 * w, 4 * w), (4 * w, 8 * w)):
        total += conv(cin, cout, 3) + bn(cout) + conv(cout, cout, 3) + bn(cout)
        total += conv(cin, cout, 1) + bn(cout)          # every block has a 1x1 skip: stride (1,2) or 2 in all four stages
    return total + 16 * w * n_classes + n_classes + 16 * w * aux + aux


def inprocess_run(request_spec, cap_s):
    """Stand-in for the subprocess runner: the same probe, same process, host high-water mark untouched."""
    result = fp.probe(request_spec["view"], request_spec["width"], request_spec["batch"], warm_steps=request_spec["warm_steps"],
                      measure=request_spec["measure"], threads=1, reset_hwm=False)
    return fp._plain(result), "ok", None


def tiny_request(**overrides):
    values = dict(views=["co"], widths=[2], batches=[2], groups_per_shard=[4], window_shards=[4], warm_steps=1, threads=1)
    values.update(overrides)
    return fp.validate_request(**values)


# --------------------------------------------------------------------------------------------- model facts

@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("width", [1, 2, 4, 8])
def test_parameter_counts_match_torch_and_an_independent_formula(view, width):
    record = fp.analytic_model_record(view, width, 2)
    torch_count = n_parameters(SmallResNet(8, width, in_ch=VIEW_CHANNELS[view], aux_outputs=1))
    assert record["n_parameters_model"]["value"] == torch_count == expected_parameters(width, VIEW_CHANNELS[view])
    assert record["n_parameters_center_loss"]["value"] == 8 * 16 * width
    assert record["n_parameters_optimized"]["value"] == torch_count + 8 * 16 * width
    assert sum(record["n_parameters_by_block"]["value"].values()) == torch_count
    assert set(record["n_parameters_by_block"]["value"]) == {"stem", "stages", "head", "aux_head"}


def test_pilot_and_candidate_widths_have_the_documented_sizes():
    # width 8 dual_residual: the ~80 k-parameter ResNet of the production budget; width 16 co: P6's ~310 k.
    assert fp.analytic_model_record("dual_residual", 8, 8)["n_parameters_model"]["value"] == 79377
    assert 300_000 < fp.analytic_model_record("co", 16, 32)["n_parameters_model"]["value"] < 320_000


@pytest.mark.parametrize("width", [1, 2, 8, 16, 32])
def test_embedding_dimension_is_sixteen_times_width_and_matches_the_real_embedding(width):
    record = fp.analytic_model_record("co", width, 2)
    assert record["embedding_dim_D"]["value"] == 16 * width
    assert record["embedding_dim_D"]["equals_16_x_width"] is True
    if width <= 2:
        model = SmallResNet(8, width, in_ch=2, aux_outputs=1)
        model.eval()
        assert model.embed(torch.zeros(1, 2, 8, 16)).shape == (1, 16 * width)


@pytest.mark.parametrize("width,ratio", [(8, 64.0), (16, 128.0), (32, 256.0)])
def test_p20_over_p21b_center_term_ratio_is_d_over_two(width, ratio):
    # K18 packet section 2: 64 at the pilot width 8 (D = 128) and 128 at width 16 (D = 256).
    record = fp.analytic_model_record("dual_residual", width, 8)
    d = record["embedding_dim_D"]["value"]
    assert record["p20_over_p21b_center_term_ratio"]["value"] == pytest.approx(d / 2) == pytest.approx(ratio)
    assert record["p20_weight_times_D"]["value"] == pytest.approx(0.005 * d)


def test_byte_accounting_matches_a_real_adamw_step():
    width, batch = 2, 2
    record = fp.analytic_model_record("dual_residual", width, batch)
    cfg, model = fp.build_real_model("dual_residual", width, batch)
    center = CenterLoss(8, model.embedding_dim)
    params = list(model.parameters()) + list(center.parameters())
    opt = torch.optim.AdamW(params, lr=cfg.lr, weight_decay=cfg.weight_decay)
    x = torch.randn(batch, 5, 8, 16)
    logits, aux, embedding = model.forward_all(x)
    y = torch.zeros(batch, dtype=torch.long)
    loss = torch.nn.functional.cross_entropy(logits, y) + center(embedding, y) + aux.sum()
    loss.backward()
    opt.step()
    weights = sum(p.numel() * p.element_size() for p in params)
    grads = sum(p.grad.numel() * p.grad.element_size() for p in params)
    adam = sum(s["exp_avg"].numel() * 4 + s["exp_avg_sq"].numel() * 4 for s in opt.state.values())
    buffers = sum(b.numel() * b.element_size() for b in model.buffers())
    assert record["fp32_weight_bytes"]["value"] == weights
    assert record["fp32_gradient_bytes"]["value"] == grads
    assert record["fp32_adamw_state_bytes"]["value"] == adam
    assert record["batchnorm_buffer_bytes"]["value"] == buffers
    assert record["fp32_static_training_state_bytes"]["value"] == weights + grads + adam + buffers
    assert record["checkpoint_state_dict_bytes"]["value"] == sum(v.numel() * v.element_size() for v in model.state_dict().values())


@pytest.mark.parametrize("view", VIEWS)
def test_input_shape_and_bytes_use_the_real_preprocessing_output(view):
    rng = np.random.default_rng(0)
    spec_db = rng.normal(-20, 3, (1, 2, 128, 512)).astype(np.float16)
    mask_db = np.full((1, 2, 512), -40.0, np.float16)
    mask_db[:, :, 100:200] = 0.0
    residual = rng.normal(-40, 3, (1, 128, 512)).astype(np.float16) if view == "dual_residual" else None
    x = preprocess_dual(spec_db, mask_db, "carrier", 2, None, view=view, residual_db=residual)
    window = fp.streaming_window_record(view, 4, 4)
    assert window["preprocessed_bytes_per_observation"]["value"] == x.nbytes
    assert fp.input_shape(view) == list(x.shape[1:])
    record = fp.analytic_model_record(view, 2, 5)
    assert record["input_shape_per_sample"]["value"] == list(x.shape[1:])
    assert record["input_batch_bytes"]["value"] == 5 * x.nbytes


def test_streaming_window_arithmetic_matches_the_stored_layout_and_e1_numbers():
    raw = (np.zeros((2, 128, 512), np.float16).nbytes + np.zeros((2, 512), np.float16).nbytes
           + np.zeros((128, 512), np.float16).nbytes)
    record = fp.streaming_window_record("dual_residual", 4, 4)
    assert raw == 395_264 == record["raw_bytes_per_observation"]["value"]
    assert record["shard_observations"]["value"] == 32                       # 4 groups x 8 labels
    assert record["shard_raw_bytes"]["value"] == 12_648_448                  # the 12.06 MiB of the E6 audit
    assert record["shard_preprocessed_bytes"]["value"] == 20_971_520         # exactly 20.0 MiB
    assert record["window_observations"]["value"] == 128 and record["window_scenario_groups"]["value"] == 16
    assert record["window_steady_resident_bytes"]["value"] == 128 * (655_360 + 262_144 + 131_072)
    assert record["window_build_peak_bytes"]["value"] == 128 * (395_264 + 2 * 655_360)    # raw shards + two float32 copies (torch.cat)
    assert (record["train_observations"]["value"], record["train_shards_per_epoch"]["value"],
            record["train_windows_per_epoch"]["value"]) == (12_000, 375, 94)
    assert record["train_bytes_read_per_epoch_double_read"]["value"] == 2 * 12_000 * 395_264
    default = fp.streaming_window_record("co", 8, 1, plan_shift=False)         # generator default of eight groups
    assert (default["train_shards_per_epoch"]["value"], default["train_windows_per_epoch"]["value"]) == (188, 188)
    assert default["plan_shift_copy_bytes_per_observation"]["value"] == 0
    assert default["window_scenario_groups"]["value"] == 8


def test_stored_layout_literal_still_matches_the_generator_source():
    source = (ROOT / "src" / "geosim" / "b2_dataset.py").read_text()
    assert "(n, 2, 128, 512)" in source and "(n, 128, 512)" in source          # TIME_ROWS = 128, 512 bins, 2 polarizations
    assert fp.TIME_ROWS == 128 and fp.input_shape("dual_residual", 2)[1:] == [64, 512]


# --------------------------------------------------------------------------------------------- the probe

def test_saved_activations_scale_with_batch_and_macs_are_per_sample():
    small = fp.probe("dual", 2, 2, measure=False, threads=1)
    large = fp.probe("dual", 2, 4, measure=False, threads=1)
    assert small["forward_macs_per_sample"] == large["forward_macs_per_sample"] > 0
    assert 1.8 < large["saved_activation_bytes"] / small["saved_activation_bytes"] < 2.1
    assert small["measured"] is None and small["saved_activation_tensors"] > 10


def test_measured_probe_reports_cold_and_warm_steps_without_resetting_the_host_peak():
    result = fp.probe("co", 2, 2, warm_steps=2, measure=True, threads=1, reset_hwm=False)
    measured = result["measured"]
    assert measured["cold_step_wall_s"] > 0 and measured["warm_steps_completed"] == 2
    assert measured["warm_step_wall_s_median"] > 0 and measured["hwm_reset_available"] is False
    assert measured["cold_step_peak_rss_kib"] is None and measured["warm_step_peak_rss_kib_max"] is None
    assert measured["process_ru_maxrss_kib"] > 0 and measured["rss_baseline_kib"] > 0


def test_child_subprocess_roundtrip_hides_cuda_and_reports_step_peaks():
    result, status, note = fp.run_child({"view": "co", "width": 2, "batch": 2, "warm_steps": 1, "measure": True,
                                         "threads": 1, "soft_deadline_s": 60}, 120)
    assert status == "ok" and note is None
    assert result["measured"]["warm_steps_completed"] == 1 and result["saved_activation_bytes"] > 0
    assert result["measured"]["process_ru_maxrss_kib"] >= (result["measured"]["cold_step_peak_rss_kib"] or 0)


def test_child_environment_hides_cuda_and_pins_threads(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=fp.CHILD_PREFIX + json.dumps({"view": "co", "measured": None}) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fp.run_child({"view": "co", "width": 2, "batch": 2, "warm_steps": 0, "measure": False, "threads": 3}, 5)
    assert seen["env"]["CUDA_VISIBLE_DEVICES"] == "" and seen["timeout"] == 5
    assert {seen["env"][k] for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")} == {"3"}


def test_wall_clock_cap_kills_the_child_and_error_is_reported():
    result, status, note = fp.run_child({"view": "dual_residual", "width": 8, "batch": 8, "warm_steps": 1, "measure": True,
                                         "threads": 1}, 0.05)
    assert result is None and status == "timeout" and "wall-clock cap" in note
    result, status, note = fp.run_child({"view": "bogus", "width": 2, "batch": 2, "warm_steps": 0, "measure": False,
                                         "threads": 1}, 120)
    assert result is None and status == "error" and note


def test_timeout_and_error_records_keep_labels_and_null_metrics(monkeypatch):
    record = fp.configuration_record("co", 2, 2, tiny_request(), True, run=lambda spec, cap: (None, "timeout", "killed"))
    assert record["status"] == "timeout"
    assert record["measured"]["cold_step_wall_s"]["value"] is None and record["measured"]["cold_step_wall_s"]["basis"] == "measured"
    assert record["gpu_vram"]["lower_bound_bytes"]["value"] is None and record["gpu_vram"]["label"] == fp.GPU_LABEL
    assert record["analytic"]["n_parameters_model"]["value"] == expected_parameters(2, 2)       # analytic part survives
    document = {"configurations": [record]}
    assert fp.find_bad_metrics(document) == [] and fp.find_unlabelled_numbers(document) == []


# --------------------------------------------------------------------------------------------- document honesty

@pytest.fixture(scope="module")
def document():
    request = tiny_request(views=["co", "dual_residual"], widths=[2], batches=[2], groups_per_shard=[4, 8], window_shards=[1, 4])
    return fp.build_document(request, measure=True, run=inprocess_run)


def test_every_number_is_a_labelled_metric_and_every_basis_is_known(document):
    assert fp.find_unlabelled_numbers(document) == []
    assert fp.find_bad_metrics(document) == []
    bases = set()

    def collect(node):
        if isinstance(node, dict):
            if "value" in node and "basis" in node:
                bases.add(node["basis"])
            for item in node.values():
                collect(item)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(document)
    assert bases == {"measured", "analytic", "assumed"}


def test_basis_matches_the_section_it_lives_in(document):
    def metrics(node):
        if isinstance(node, dict):
            if "value" in node and "basis" in node:
                yield node
            else:
                for item in node.values():
                    yield from metrics(item)
        elif isinstance(node, list):
            for item in node:
                yield from metrics(item)

    for record in document["configurations"]:
        assert {m["basis"] for m in metrics(record["analytic"])} == {"analytic"}
        assert {m["basis"] for m in metrics(record["forward_graph"])} == {"analytic"}
        assert {m["basis"] for m in metrics(record["gpu_vram"])} == {"analytic"}       # VRAM is never "measured"
        assert {m["basis"] for m in metrics(record["measured"])} == {"measured"}
        assert record["gpu_vram"]["label"] == "analytic estimate, not measured; needs the authorized GPU probe"
        assert "needs the authorized GPU probe" in record["gpu_vram"]["upper_bound_bytes"]["how"]
        assert record["gpu_vram"]["upper_bound_bytes"]["value"] > record["gpu_vram"]["lower_bound_bytes"]["value"] > 0
    for window in document["streaming_windows"]:
        assert {m["basis"] for m in metrics({k: v for k, v in window.items() if isinstance(v, dict)})} == {"analytic"}
    budget = document["assumed_budget"]
    for key in ("epochs", "seeds", "fits", "assumed_throughput_low", "assumed_throughput_high"):
        assert budget[key]["basis"] == "assumed"
    for key in ("training_sample_passes_total", "pure_training_hours_at_low_throughput", "pure_training_hours_at_high_throughput"):
        assert budget[key]["basis"] == "assumed"                    # derived from an assumed epoch count / throughput
    assert budget["train_observations"]["basis"] == "analytic"
    assert budget["training_sample_passes_total"]["value"] == 12_000 * 30 * 2 * 3   # 2 views x 3 assumed seeds x 30 epochs
    assert budget["pure_training_hours_at_low_throughput"]["value"] == pytest.approx(12_000 * 30 * 6 / 200 / 3600)


def test_document_is_strict_json_and_benchmark_complete_stays_false(document):
    text = fp.dumps_strict(document)
    parsed = strict(text)
    assert parsed["benchmark_complete"] is False and parsed["schema"] == "B2-training-footprint/1"
    assert parsed["status"] == "READ_ONLY_FOOTPRINT_NOT_A_TRAINING_RESULT"
    assert "NaN" not in text and "Infinity" not in text
    assert fp.dumps_strict({"x": float("nan"), "y": [float("inf")], "z": np.float32(1.5)}) == strict_text({"x": None, "y": [None], "z": 1.5})
    assert parsed["environment"]["device"].startswith("cpu")
    assert parsed["request"]["measure"] is True


def strict_text(value):
    return json.dumps(value, indent=2, allow_nan=False) + "\n"


def test_label_checker_catches_mislabelled_or_unlabelled_numbers(document):
    broken = copy.deepcopy(document)
    broken["configurations"][0]["analytic"]["n_parameters_model"]["basis"] = "guess"
    assert fp.find_bad_metrics(broken) == ["configurations/0/analytic/n_parameters_model"]
    broken = copy.deepcopy(document)
    broken["configurations"][0]["analytic"]["stray_number"] = 12345
    assert fp.find_unlabelled_numbers(broken) == ["configurations/0/analytic/stray_number"]
    broken = copy.deepcopy(document)
    del broken["configurations"][0]["analytic"]["embedding_dim_D"]["unit"]
    assert "configurations/0/analytic/embedding_dim_D" in fp.find_bad_metrics(broken)
    with pytest.raises(ValueError):
        fp.metric(1, "x", "estimated", "bad basis")


def test_derived_values_take_the_weakest_basis():
    a, m, s = (fp.metric(1, "u", basis, "") for basis in ("analytic", "measured", "assumed"))
    assert fp.derived_metric(1, "u", "", [a, a])["basis"] == "analytic"
    assert fp.derived_metric(1, "u", "", [a, m])["basis"] == "measured"
    assert fp.derived_metric(1, "u", "", [a, m, s])["basis"] == "assumed"
    with pytest.raises(ValueError):
        fp.combine_basis()


# --------------------------------------------------------------------------------------------- caps and writing

def test_hard_caps_are_constants_and_the_boundary_is_accepted():
    assert (fp.MAX_BATCH, fp.MAX_WIDTH) == (64, 32)
    ok = fp.validate_request(widths=[32], batches=[64])
    assert ok["widths"] == [32] and ok["batches"] == [64]


@pytest.mark.parametrize("override", [
    {"widths": [33]}, {"widths": [0]}, {"batches": [65]}, {"batches": [0]}, {"views": ["triple"]}, {"views": []},
    {"widths": [8, 8]}, {"time_cap_s": 601}, {"time_cap_s": 0}, {"time_cap_s": float("nan")}, {"total_cap_s": 3601},
    {"warm_steps": 6}, {"warm_steps": -1}, {"threads": 5}, {"threads": True}, {"epochs_assumed": 0},
    {"throughput_assumed": (1000.0, 200.0)}, {"throughput_assumed": (0.0, 5.0)},
    {"widths": [1, 2, 3, 4], "batches": [1, 2, 3, 4]},                                    # 3 x 4 x 4 = 48 > 36 configurations
])
def test_requests_beyond_the_caps_are_refused(override):
    with pytest.raises(fp.FootprintError):
        fp.validate_request(**override)


def test_cli_refuses_cap_violations_with_exit_code_two_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(fp, "build_document", lambda *a, **k: pytest.fail("must refuse before measuring"))
    for flags in (["--widths", "33"], ["--batches", "65"], ["--time-cap-s", "601"], ["--views", "nope"]):
        out = tmp_path / "x.json"
        assert fp.main(["--out", str(out), *flags]) == 2
        assert not out.exists()
    assert "refused" in capsys.readouterr().err


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    out = tmp_path / "footprint.json"
    out.write_text('{"keep": "me"}\n')
    monkeypatch.setattr(fp, "build_document", lambda *a, **k: pytest.fail("must refuse before measuring"))
    assert fp.main(["--out", str(out), "--views", "co", "--widths", "2", "--batches", "2"]) == 2
    assert out.read_text() == '{"keep": "me"}\n'
    with pytest.raises(FileExistsError):
        fp.write_new_json(out, {"a": 1})
    assert out.read_text() == '{"keep": "me"}\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["footprint.json"]          # no temporary file left behind


def test_unserialisable_document_leaves_no_file(tmp_path):
    out = tmp_path / "bad.json"
    with pytest.raises(TypeError):
        fp.write_new_json(out, {"x": object()})
    assert list(tmp_path.iterdir()) == []


def test_cli_end_to_end_writes_one_new_strict_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "run_child", inprocess_run)
    out = tmp_path / "runs" / "nested" / "footprint.json"
    argv = ["--out", str(out), "--views", "co", "--widths", "2", "--batches", "2", "--groups-per-shard", "4",
            "--window-shards", "4", "--warm-steps", "1", "--threads", "1", "--time-cap-s", "60"]
    assert fp.main(argv) == 0
    parsed = strict(out.read_text())
    assert parsed["configurations"][0]["status"] == "ok" and parsed["configurations"][0]["measured"]["status"] == "ok"
    assert fp.find_unlabelled_numbers(parsed) == [] and fp.find_bad_metrics(parsed) == []
    assert fp.main(argv) == 2                                                    # the second run refuses to overwrite
    assert strict(out.read_text()) == parsed
    out2 = tmp_path / "analytic.json"
    assert fp.main([*argv[:1], str(out2), *argv[2:], "--no-measure"]) == 0
    assert strict(out2.read_text())["configurations"][0]["measured"]["status"] == "not_requested"


def test_whole_run_cap_skips_remaining_configurations():
    request = tiny_request(views=["co", "dual"], total_cap_s=1e-9)
    document = fp.build_document(request, measure=True, run=lambda *a: pytest.fail("cap must stop the run"))
    assert [c["status"] for c in document["configurations"]] == ["skipped_total_cap"] * 2


# --------------------------------------------------------------------------------------------- scope guarantees

def test_source_neither_trains_nor_reads_datasets():
    source = (ROOT / "scripts" / "b2_training_footprint.py").read_text()
    for forbidden in ("fit_streaming(", "open_b2_known(", "open_b2_test(", "open_b2_matched(", "iter_b2_shards(", "np.load(",
                      "numpy.load(", "torch.load(", ".to(\"cuda\")", "cuda()", "device=\"cuda\""):
        assert forbidden not in source, forbidden
    assert "CUDA_VISIBLE_DEVICES=\"\"" in source


def test_probe_never_leaves_cpu():
    cfg, model = fp.build_real_model("co", 2, 2)
    assert {p.device.type for p in model.parameters()} == {"cpu"}


# --------------------------------------------------------------------------------------------- the E7a proposal file

PROPOSAL = ROOT / "docs" / "plan" / "b2_e7_training_proposal.json"
REQUIRED_FIELDS = ("value", "basis", "source", "needs_researcher_approval", "alternatives", "consequence", "approval")
PARAM_BASES = ("existing_config", "repository_default", "plan_assumption", "engineering_recommendation")


@pytest.fixture(scope="module")
def proposal():
    return strict(PROPOSAL.read_text())


def test_proposal_is_an_unfrozen_unapproved_candidate(proposal):
    assert proposal["schema"] == "B2-training-proposal/1"
    assert proposal["status"] == "PROPOSAL_NOT_FROZEN"
    assert proposal["frozen"] is False and proposal["approved"] is False
    assert proposal["benchmark_complete"] is False and proposal["configs_touched"] is False
    assert "does not authorize" in proposal["statement"]
    gates = strict((ROOT / "docs" / "plan" / "b2_readiness_gates_2026-10-21.json").read_text())["decisions"]
    assert set(proposal["gates"]) == {"K18", "K17d", "OBS-CANCEL-2", "full_generation", "full_gpu_training", "full_loko_sweep"}
    # The proposal is a historical snapshot (E7a, before the researcher's 2026-10-24 scientific approvals): its recorded gate states are
    # fixed, it authorizes nothing, and the live gates must not have moved on the compute side.
    assert proposal["gates"] == {"K18": "PENDING_RESEARCHER", "K17d": "PENDING_RESEARCHER", "OBS-CANCEL-2": "PENDING_RESEARCHER",
                                 "full_generation": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED", "full_loko_sweep": "NOT_AUTHORIZED"}
    for name in ("full_generation", "full_gpu_training", "full_loko_sweep"):
        assert gates[name]["status"] == proposal["gates"][name] and gates[name]["approval"] is None, name
    for name in ("K18", "K17d", "OBS-CANCEL-2"):                                    # approved since, with a complete record; still no compute
        assert gates[name]["status"] == "APPROVED" and set(gates[name]["approval"]) >= {"approved_by", "approved_at", "decision", "record"}, name


def test_every_parameter_record_is_complete_and_unapproved(proposal):
    for name, record in proposal["parameters"].items():
        assert all(key in record for key in REQUIRED_FIELDS), name
        assert record["basis"] in PARAM_BASES, name
        assert record["approval"] is None and isinstance(record["needs_researcher_approval"], bool), name
        assert isinstance(record["alternatives"], list) and record["source"].strip() and record["consequence"].strip(), name
        for alternative in record["alternatives"]:
            assert alternative["basis"] in PARAM_BASES + ("not_in_repository",), name
    decisions = {d["id"]: d for d in proposal["researcher_decisions"]}
    for name, record in proposal["parameters"].items():
        group = record.get("approval_group")
        if record["needs_researcher_approval"] and group and group.startswith("R"):
            assert name in decisions[group]["parameters"], (name, group)
    for decision in decisions.values():
        assert decision["sentence"].startswith(decision["id"] + ":") and all(p in proposal["parameters"] for p in decision["parameters"])


def test_scientific_and_compute_choices_are_flagged_and_assumptions_are_named(proposal):
    parameters = proposal["parameters"]
    for name in ("views", "training_seed_values", "model_width", "time_pool", "epochs", "epochs_selection_procedure", "batch_size",
                 "optimizer", "learning_rate_schedule", "gradient_clipping", "center_loss_weight", "plan_loss_weight",
                 "streaming_groups_per_shard", "streaming_window_shards", "test_evaluation_coupling", "interruption_policy",
                 "expected_cpu_ram", "expected_gpu_vram", "expected_sample_passes_and_wall_clock", "compute_hardware"):
        assert parameters[name]["needs_researcher_approval"] is True, name
    for name in ("plan_shift_augmentation", "checkpoint_selection_rule", "loss_composition", "training_seed_count"):
        assert parameters[name]["basis"] == "existing_config" and parameters[name]["needs_researcher_approval"] is False, name
    for name in ("mahalanobis_fit", "calibration"):          # stated in P20 prose and the pilot config, not as P18 numbers: confirm (R10)
        assert parameters[name]["basis"] == "existing_config" and parameters[name]["needs_researcher_approval"] is True, name
        assert parameters[name]["approval_group"] == "R10" and "P18" in parameters[name]["consequence"]
    assert parameters["precision_and_determinism"]["needs_researcher_approval"] is True
    assert parameters["precision_and_determinism"]["approval_group"] == "R6"
    assert parameters["epochs"]["basis"] in ("repository_default", "plan_assumption") and "ASSUMPTION" in parameters["epochs"]["consequence"]
    assert "analytic estimate, not measured; needs the authorized GPU probe" == parameters["expected_gpu_vram"]["value"]["label"]
    assert parameters["compute_hardware"]["value"].startswith("not decided")
    assert "Approval of this proposal" in proposal["not_decided_here"][0]


def test_defaults_quoted_in_the_proposal_are_the_real_repository_values(proposal):
    import inspect
    from geoml import b2_loko, b2_stream
    from geoml.train import TrainConfig
    from geosim import b2_dataset
    defaults = {field.name: field.default for field in TrainConfig.__dataclass_fields__.values()}
    parameters = proposal["parameters"]
    assert parameters["model_width"]["value"] == defaults["width"] == 16
    assert parameters["epochs"]["value"] == defaults["epochs"] == 30
    assert parameters["batch_size"]["value"] == defaults["batch"] == 32
    assert parameters["time_pool"]["value"] == defaults["time_pool"] and parameters["level"]["value"] == defaults["level"]
    assert parameters["optimizer"]["value"]["peak_lr"] == defaults["lr"] and parameters["optimizer"]["value"]["weight_decay"] == defaults["weight_decay"]
    assert parameters["mirror_roll_augmentation"]["value"]["enabled"] is defaults["augment"]
    assert parameters["streaming_window_shards"]["value"] == b2_stream.DEFAULT_WINDOW_SHARDS
    assert parameters["training_seed_values"]["value"] == list(inspect.signature(b2_loko.build_plan).parameters["seeds"].default)
    assert any(a["value"] == b2_dataset.GROUPS_PER_SHARD for a in parameters["streaming_groups_per_shard"]["alternatives"])
    assert parameters["training_seed_count"]["value"] == len(parameters["training_seed_values"]["value"]) == 3
    schedule = parameters["learning_rate_schedule"]["value"]
    signature = inspect.signature(torch.optim.lr_scheduler.OneCycleLR.__init__).parameters
    for key in ("pct_start", "anneal_strategy", "div_factor", "final_div_factor", "three_phase", "cycle_momentum", "base_momentum", "max_momentum"):
        assert schedule[key] == signature[key].default, key              # torch-version dependent: the lock must pin torch
    assert schedule["initial_lr"] == pytest.approx(schedule["max_lr"] / schedule["div_factor"])
    assert schedule["final_lr"] == pytest.approx(schedule["initial_lr"] / schedule["final_div_factor"])
    adam = torch.optim.AdamW.__init__
    assert tuple(parameters["optimizer"]["value"]["betas"]) == inspect.signature(adam).parameters["betas"].default
    assert parameters["optimizer"]["value"]["eps"] == inspect.signature(adam).parameters["eps"].default


def test_pilot_config_values_in_the_proposal_match_the_committed_config(proposal):
    config = strict((ROOT / "configs" / "b2_feat.json").read_text())
    training, parameters = config["training"], proposal["parameters"]
    assert parameters["center_loss_weight"]["value"] == training["center_loss_weight"] == 0.005
    assert parameters["plan_loss_weight"]["value"] == training["plan_loss_weight"] == 1.0
    shift = parameters["plan_shift_augmentation"]["value"]
    assert (shift["fraction"], shift["max_hz"]) == (training["plan_shift_fraction"], training["plan_shift_max_hz"])
    assert parameters["views"]["value"] == config["views"]
    assert parameters["calibration"]["value"]["acceptance_target"] == config["target_acceptance"]
    assert parameters["calibration"]["value"]["clean_alarm_pfa"] == config["pfa"]
    assert parameters["mahalanobis_fit"]["value"]["regularization"] == config["mahalanobis_regularization"]
    assert [a["value"] for a in parameters["model_width"]["alternatives"] if a["basis"] == "existing_config"] == [training["width"]]
    assert [a["value"] for a in parameters["batch_size"]["alternatives"] if a["basis"] == "existing_config"] == [training["batch"]]
    assert "3 epochs" in parameters["epochs"]["source"] and training["epochs"] == 3


def test_width_table_and_footprint_rows_match_the_tool(proposal):
    widths = proposal["evidence"]["footprint_run"]["widths"]
    assert set(widths) == {"8", "16", "32"}
    for key, row in widths.items():
        width = int(key)
        for view, count in row["n_parameters_by_view"].items():
            assert count == fp.analytic_model_record(view, width, 8)["n_parameters_model"]["value"] == expected_parameters(width, VIEW_CHANNELS[view])
        assert row["embedding_dim_D"] == 16 * width and row["p20_over_p21b_center_term_ratio"] == 8 * width
    assert widths["16"]["n_parameters_by_view"]["co"] // 1000 == 310                      # P6 section 3: about 310,000
    assert 3.0 < widths["16"]["forward_gmacs_per_sample_dual_residual"] / widths["8"]["forward_gmacs_per_sample_dual_residual"] < 3.6
    rows = proposal["evidence"]["footprint_run"]["rows"]
    assert len(rows) == 18 and {r["status"] for r in rows} == {"ok"}
    for r in rows:
        analytic = fp.analytic_model_record(r["view"], r["width"], r["batch"])
        assert r["n_parameters_model"] == analytic["n_parameters_model"]["value"] and r["embedding_dim_D"] == analytic["embedding_dim_D"]["value"]
        assert r["input_batch_mib"] == round(analytic["input_batch_bytes"]["value"] / 2 ** 20, 2)
        assert 0 < r["gpu_vram_analytic_lower_mib"] < r["gpu_vram_analytic_upper_mib"]
        assert r["cpu_cold_step_peak_over_baseline_mib"] > 0 and r["cpu_warm_samples_per_s"] > 0


def test_streaming_numbers_and_budget_arithmetic_in_the_proposal(proposal):
    window = proposal["evidence"]["footprint_run"]["streaming_window_dual_residual"]["4_groups_x_4_shards"]
    expected = fp.streaming_window_record("dual_residual", 4, 4)
    assert all(window[key] == expected[key]["value"] for key in window)
    passes = proposal["parameters"]["expected_sample_passes_and_wall_clock"]["value"]
    assert passes["sample_passes_per_fit"] == 12_000 * 30 and passes["sample_passes_total"] == 12_000 * 30 * 9 == 3_240_000
    assert passes["assumed_pure_training_gpu_hours"] == [pytest.approx(3_240_000 / 1000 / 3600, abs=0.05), pytest.approx(3_240_000 / 200 / 3600, abs=0.05)]
    loader = passes["synchronous_loader_estimate"]
    assert loader["seconds_per_epoch"] == pytest.approx(34 + 12_000 / 270, abs=0.1)
    assert loader["hours_for_nine_fits"] == pytest.approx(loader["seconds_per_epoch"] * 30 * 9 / 3600, abs=0.01)


def test_repository_facts_cited_as_engineering_only_still_hold():
    import inspect
    from geoml import b2_experiment, b2_production_training, train as geoml_train
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        text = path.read_text()
        for token in ("clip_grad", "autocast", "GradScaler", "DataLoader", "num_workers", "use_deterministic_algorithms", "cudnn.deterministic",
                      "allow_tf32", "set_float32_matmul_precision"):
            # PR49's separate R6 adapter explicitly disables autocast/TF32.
            # Keep the historical kernel audit and every other prohibition.
            if path == ROOT / "src/geoml/b2_production_training.py" and token in {"autocast", "use_deterministic_algorithms", "allow_tf32"}:
                continue
            assert token not in text, (path.name, token)
    with b2_production_training.r6_fp32():
        assert not torch.is_autocast_enabled() and not torch.is_autocast_enabled("cpu")
        assert not torch.backends.cuda.matmul.allow_tf32 and not torch.backends.cudnn.allow_tf32
        assert not torch.are_deterministic_algorithms_enabled()
    save_source = inspect.getsource(geoml_train.save)
    assert not any(word in save_source.lower() for word in ("optim", "sched", "rng_state", "opt."))      # no restartable snapshot
    runner = inspect.signature(b2_experiment.run_b2_experiment).parameters
    assert not {"train_only", "skip_test", "skip_evaluation"} & set(runner)
    assert runner["device"].default == "cpu"


# ---- E7a review regressions: absolute pins instead of relative ones, the hidden child mode, honest build peak -------------

@pytest.mark.parametrize("width,macs", [(8, 96_732_288), (16, 321_390_848), (32, 1_154_486_784)])
def test_forward_macs_and_saved_activations_match_independent_closed_forms(width, macs):
    result = fp.probe("dual_residual", width, 4, measure=False, threads=1)
    assert result["forward_macs_per_sample"] == macs                                # per-layer closed form, exact
    assert result["saved_activation_bytes"] == pytest.approx(4 * 4 * 219_136 * width, rel=2e-3)


def test_vram_bounds_are_the_documented_sums():
    analytic = fp.analytic_model_record("dual_residual", 16, 8)
    result = fp.probe("dual_residual", 16, 8, measure=False, threads=1)
    record = fp.gpu_vram_record(analytic, result)
    saved = result["saved_activation_bytes"]
    lower = analytic["fp32_static_training_state_bytes"]["value"] + analytic["input_batch_bytes"]["value"] + saved
    assert record["lower_bound_bytes"]["value"] == lower and record["upper_bound_bytes"]["value"] == lower + saved


def test_the_r2_width_table_matches_the_tool(proposal):
    table = proposal["parameters"]["model_width"]["by_width"]
    assert set(table) == {"8", "16", "32"}
    for key, row in table.items():
        width = int(key)
        for view, count in row["n_parameters_by_view"].items():
            assert count == fp.analytic_model_record(view, width, 8)["n_parameters_model"]["value"]
        analytic = fp.analytic_model_record("dual_residual", width, 8)
        assert row["n_parameters_optimized_dual_residual"] == analytic["n_parameters_optimized"]["value"]
        assert row["embedding_dim_D"] == analytic["embedding_dim_D"]["value"] == 16 * width
        assert row["p20_over_p21b_center_term_ratio"] == analytic["p20_over_p21b_center_term_ratio"]["value"]
        assert row["p20_weight_times_D"] == analytic["p20_weight_times_D"]["value"]
        assert row["fp32_static_training_state_mib"] == round(analytic["fp32_static_training_state_bytes"]["value"] / 2 ** 20, 2)
        macs = fp.probe("dual_residual", width, 1, measure=False, threads=1)["forward_macs_per_sample"]
        assert row["forward_gmacs_per_sample_dual_residual"] == round(macs / 1e9, 3)


def test_the_proposal_states_the_p18_search_rule_and_the_unfrozen_constants(proposal):
    decisions = {d["id"]: d for d in proposal["researcher_decisions"]}
    assert [d["id"] for d in proposal["researcher_decisions"]] == [f"R{i}" for i in range(1, 11)]
    for key in ("R2", "R4", "R5", "R6"):
        assert decisions[key]["p18_section_10_if_not_p6_default"] is True and "section 10" in decisions[key]["p18_note"]
    assert "section 10" in proposal["parameters"]["epochs_selection_procedure"]["consequence"]
    assert "precision_and_determinism" in decisions["R6"]["parameters"] and "allow_tf32" in decisions["R6"]["sentence"]
    assert decisions["R10"]["parameters"] == ["mahalanobis_fit", "calibration"] and "0.95" in decisions["R10"]["sentence"]
    optimizer = proposal["parameters"]["optimizer"]["value"]
    assert "0.95 -> 0.85 -> 0.95" in optimizer["effective_beta1_with_OneCycleLR"]
    flags = proposal["parameters"]["precision_and_determinism"]["value"]
    assert flags["repository_sets_tf32_flags"] is False and "True" in flags["cudnn_allow_tf32"]
    assert torch.backends.cudnn.allow_tf32 is True and torch.backends.cuda.matmul.allow_tf32 is False       # torch defaults the text quotes


def test_onecycle_overwrites_the_constructor_beta1():
    model = torch.nn.Linear(2, 2)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    assert optimizer.param_groups[0]["betas"][0] == 0.9
    torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=1e-3, total_steps=100)
    assert optimizer.param_groups[0]["betas"][0] == 0.95                              # cycle_momentum=True, max_momentum default


@pytest.mark.parametrize("override", [{"width": 33}, {"batch": 65}, {"threads": 64}, {"warm_steps": 6}, {"view": "bogus"},
                                      {"measure": "yes"}, {"soft_deadline_s": 1e9}])
def test_the_hidden_child_mode_obeys_the_same_caps(override, capsys):
    spec = {"view": "co", "width": 2, "batch": 1, "warm_steps": 0, "measure": False, "threads": 1, **override}
    assert fp.main(["--child", json.dumps(spec)]) == 2
    captured = capsys.readouterr()
    assert fp.CHILD_PREFIX not in captured.out and "refused child spec" in captured.err
    assert fp.main(["--child", "{not json"]) == 2 and fp.main(["--child", "[]"]) == 2


def test_a_malformed_child_line_is_an_error_record_not_a_crash(monkeypatch):
    fake = SimpleNamespace(returncode=0, stdout=fp.CHILD_PREFIX + "{not json", stderr="")
    monkeypatch.setattr(fp.subprocess, "run", lambda *args, **kwargs: fake)
    result, status, note = fp.run_child({"threads": 1}, 5)
    assert result is None and status == "error" and "malformed child output" in note


def test_the_window_build_peak_counts_both_float32_copies_and_the_proposal_says_so(proposal):
    record = fp.streaming_window_record("dual_residual", 4, 4)
    assert record["window_build_peak_bytes"]["value"] == 128 * 1_705_984 == 218_365_952
    assert "torch.cat" in record["window_build_peak_bytes"]["how"] and "two float32 copies" in record["window_build_peak_bytes"]["how"]
    window = proposal["evidence"]["footprint_run"]["streaming_window_dual_residual"]
    assert window["4_groups_x_4_shards"]["window_build_peak_bytes"] == 218_365_952
    assert window["8_groups_x_4_shards"]["window_build_peak_bytes"] == 436_731_904
