"""Bounded, CPU-only, read-only training-footprint probe for the B2 SmallResNet (E7a Phase 4).

    python scripts/b2_training_footprint.py --out runs/footprint/b2_training_footprint.json
    python scripts/b2_training_footprint.py --out runs/footprint/quick.json --views dual_residual \
        --widths 8 --batches 8 --time-cap-s 60
    python scripts/b2_training_footprint.py --out runs/footprint/analytic.json --no-measure

For every view in {co, dual, dual_residual} x width x batch it builds the *real* repository model
(``geoml.train._model`` on a ``TrainConfig`` with the pilot loss weights of ``configs/b2_feat.json``,
auxiliary plan head on) and reports

* ANALYTIC quantities: parameter counts, the embedding dimension ``D`` (= ``16 x width``), the P20-versus-P21b
  centre-term ratio ``D/2``, fp32 weight + gradient + AdamW-state bytes, autograd-saved activation bytes of one
  forward pass (tally of the real graph by ``saved_tensors_hooks``, de-duplicated by storage), forward
  multiply-accumulates per sample, an *analytic* GPU VRAM estimate and the streaming-window arithmetic
  (``geoml.b2_stream`` window of verified shards) from repository constants;
* MEASURED quantities (unless ``--no-measure``): wall time and peak resident memory of ONE cold and a few warm
  training steps (forward, loss, backward, AdamW) on a synthetic random batch of the real input shape, each
  configuration in a fresh subprocess (``resource.getrusage`` ``ru_maxrss``; ``VmHWM`` after a ``clear_refs``
  reset when the kernel allows it, so the step peak is separable from the ~550 MiB import footprint);
* ASSUMED quantities: the sample-pass budget (epochs, seeds, views and the 200-1000 samples/s band come from
  planning documents, not from a measurement).

Every number is a record ``{"value", "unit", "basis", "how"}`` with ``basis`` in ``measured | analytic |
assumed``; a value derived from several inputs carries the weakest basis (assumed, then measured, then
analytic). Only request/cap echoes and configuration identifiers are bare numbers.

What it never does: train a model, read B2 data or any dataset shard, use a GPU (children run with
``CUDA_VISIBLE_DEVICES=""`` on CPU tensors), write anywhere but the single new ``--out`` file (an existing file
is never overwritten), or exceed its caps (batch <= 64, width <= 32, a wall-clock cap per configuration and one
for the whole run). GPU VRAM is only ever an analytic estimate, not measured; it needs the authorized GPU probe.
It sits in ``scripts/`` on purpose: every ``src/**/*.py`` is hashed into checkpoint provenance.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

SCHEMA = "B2-training-footprint/1"
BASES = ("measured", "analytic", "assumed")
GPU_LABEL = "analytic estimate, not measured; needs the authorized GPU probe"
VIEW_NAMES = ("co", "dual", "dual_residual")

# Hard caps. They are constants on purpose: no flag can raise them.
MAX_BATCH = 64
MAX_WIDTH = 32
MAX_TIME_CAP_S = 600.0
DEFAULT_TIME_CAP_S = 180.0
MAX_TOTAL_CAP_S = 3600.0
DEFAULT_TOTAL_CAP_S = 1800.0
MAX_WARM_STEPS = 5
MAX_CONFIGS = 36
MAX_THREADS = 4
MAX_SHARD_PARAM = 64

# Stored B2-feat/1 layout: spec [n,2,128,512] float16, mask [n,2,512] float16, residual [n,128,512] float16
# (src/geosim/b2_dataset.py `_read_part`; the 128 snapshot rows are a literal there, not a named constant).
TIME_ROWS = 128
N_POL = 2
FP16_BYTES = 2
FP32_BYTES = 4
CHILD_PREFIX = "FOOTPRINT_RESULT "

# Bare numbers are allowed only in these top-level sections and under these identifier keys.
UNLABELLED_SECTIONS = ("schema", "request", "caps")
IDENTITY_KEYS = ("width", "batch", "groups_per_shard", "window_shards")


class FootprintError(ValueError):
    """Refused request or cap violation."""


# ---------------------------------------------------------------------------------------------------------
# metric records, strict JSON

def _plain(value):
    """numpy scalars/arrays and tuples -> JSON-able Python values; non-finite floats -> None."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a hard dependency of the repository
        np = None
    if np is not None:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            value = float(value)
        if isinstance(value, np.ndarray):
            return [_plain(item) for item in value.tolist()]
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def metric(value, unit, basis, how, **extra):
    """One labelled number. ``value`` None means unavailable; ``extra`` carries counts or notes."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}")
    record = {"value": _plain(value), "unit": unit, "basis": basis, "how": how}
    record.update(_plain(extra))
    return record


def combine_basis(*bases):
    """Weakest basis of a derived value: assumed, else measured, else analytic."""
    if any(b not in BASES for b in bases) or not bases:
        raise ValueError(f"bases must be a nonempty subset of {BASES}")
    for weakest in ("assumed", "measured"):
        if weakest in bases:
            return weakest
    return "analytic"


def derived_metric(value, unit, how, inputs, **extra):
    """A metric computed from other metric records; its basis is the weakest input basis."""
    return metric(value, unit, combine_basis(*[item["basis"] for item in inputs]), how, **extra)


def dumps_strict(document):
    return json.dumps(_plain(document), indent=2, allow_nan=False) + "\n"


def write_new_json(path, document):
    """Serialise strictly first (no file is touched on failure), then create ``path`` exclusively."""
    text = dumps_strict(document)
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} already exists; this tool never overwrites")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
        try:
            os.link(temporary, path)          # fails with FileExistsError if the path appeared meanwhile
        except FileExistsError:
            raise
        except OSError:                        # filesystem without hard links: exclusive create instead
            with open(path, "x") as stream:
                stream.write(text)
    finally:
        os.unlink(temporary)


def find_unlabelled_numbers(document):
    """Paths of numbers outside a metric record, a request/cap section or an identifier key (for tests)."""
    found = []

    def walk(node, path, labelled):
        if isinstance(node, dict):
            record = "value" in node and "basis" in node
            for key, item in node.items():
                walk(item, path + (key,), labelled or record or (not path and key in UNLABELLED_SECTIONS))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, path + (index,), labelled)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            if not labelled and not (path and path[-1] in IDENTITY_KEYS):
                found.append("/".join(str(part) for part in path))

    walk(document, (), False)
    return found


def find_bad_metrics(document):
    """Paths of ``value``-bearing records whose ``basis`` is missing or not one of BASES (for tests)."""
    bad = []

    def walk(node, path):
        if isinstance(node, dict):
            if "value" in node and ("basis" not in node or node["basis"] not in BASES or "unit" not in node):
                bad.append("/".join(str(part) for part in path))
            for key, item in node.items():
                walk(item, path + (key,))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, path + (index,))

    walk(document, ())
    return bad


# ---------------------------------------------------------------------------------------------------------
# request validation (all caps live here)

def _positive_int(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise FootprintError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _unique(values, name):
    values = list(values)
    if not values or len(set(values)) != len(values):
        raise FootprintError(f"{name} must be a nonempty list without duplicates")
    return values


def validate_request(views=VIEW_NAMES, widths=(8, 16, 32), batches=(8, 32), groups_per_shard=(4, 8),
                     window_shards=(1, 4), time_cap_s=DEFAULT_TIME_CAP_S, total_cap_s=DEFAULT_TOTAL_CAP_S,
                     warm_steps=2, threads=2, epochs_assumed=30, throughput_assumed=(200.0, 1000.0), seeds_assumed=3):
    views = _unique(views, "views")
    if any(view not in VIEW_NAMES for view in views):
        raise FootprintError(f"views must be chosen from {VIEW_NAMES}")
    widths = [_positive_int(w, "width", MAX_WIDTH) for w in _unique(widths, "widths")]
    batches = [_positive_int(b, "batch", MAX_BATCH) for b in _unique(batches, "batches")]
    groups_per_shard = [_positive_int(g, "groups_per_shard", MAX_SHARD_PARAM) for g in _unique(groups_per_shard, "groups_per_shard")]
    window_shards = [_positive_int(w, "window_shards", MAX_SHARD_PARAM) for w in _unique(window_shards, "window_shards")]
    if len(views) * len(widths) * len(batches) > MAX_CONFIGS:
        raise FootprintError(f"at most {MAX_CONFIGS} configurations per run")
    for name, value, maximum in (("time_cap_s", time_cap_s, MAX_TIME_CAP_S), ("total_cap_s", total_cap_s, MAX_TOTAL_CAP_S)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= maximum:
            raise FootprintError(f"{name} must be in (0, {maximum}] seconds")
    if isinstance(warm_steps, bool) or not isinstance(warm_steps, int) or not 0 <= warm_steps <= MAX_WARM_STEPS:
        raise FootprintError(f"warm_steps must be an integer in [0, {MAX_WARM_STEPS}]")
    _positive_int(threads, "threads", MAX_THREADS)
    _positive_int(epochs_assumed, "epochs_assumed", 1000)
    _positive_int(seeds_assumed, "seeds_assumed", 10)
    throughput = list(throughput_assumed)
    if (len(throughput) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                                    for v in throughput) or throughput[0] > throughput[1]):
        raise FootprintError("throughput_assumed must be two positive samples/s values, low then high")
    return {"views": views, "widths": widths, "batches": batches, "groups_per_shard": groups_per_shard,
            "window_shards": window_shards, "time_cap_s": float(time_cap_s), "total_cap_s": float(total_cap_s),
            "warm_steps": warm_steps, "threads": threads, "epochs_assumed": epochs_assumed,
            "seeds_assumed": seeds_assumed, "throughput_assumed": [float(v) for v in throughput]}


# ---------------------------------------------------------------------------------------------------------
# repository facts (imports are local so that --help and the validators stay light)

def _repo_constants():
    from geoml.data import VIEW_CHANNELS
    from geoml.train import TrainConfig
    from geosim.b2_protocol import LABELS, ROLE_COUNTS
    from geosim.plan import N_BINS
    defaults = {field.name: field.default for field in TrainConfig.__dataclass_fields__.values()}
    return {"VIEW_CHANNELS": dict(VIEW_CHANNELS), "LABELS": tuple(LABELS), "ROLE_COUNTS": dict(ROLE_COUNTS),
            "FREQ_BINS": int(N_BINS), "train_defaults": defaults}


def _pilot_loss_weights():
    """Center/plan loss weights of the committed pilot config; the probe step uses them as the real step would."""
    from geosim.event_dataset import _strict_json
    config = _strict_json((REPO / "configs" / "b2_feat.json").read_text())
    training = config["training"]
    return {"center_loss_weight": float(training["center_loss_weight"]),
            "plan_loss_weight": float(training.get("plan_loss_weight", 1.0)),
            "plan_shift_fraction": float(training.get("plan_shift_fraction", 0.0)),
            "plan_shift_max_hz": float(training.get("plan_shift_max_hz", 0.0)),
            "source": "configs/b2_feat.json"}


def _p21b_center_weight():
    import dataclasses
    from geoml.b2_train import B2TrainConfig
    return {field.name: field.default for field in dataclasses.fields(B2TrainConfig)}["center_weight"]


def build_real_model(view, width, batch=1):
    """The model a production fit of this view would build, through the repository's own constructor."""
    from geoml.train import TrainConfig, _model
    from geosim.b2_protocol import LABELS
    weights = _pilot_loss_weights()
    cfg = TrainConfig(labels=tuple(LABELS), input_mode=view, plan_consistency=True, width=width, batch=batch,
                      center_loss_weight=weights["center_loss_weight"], plan_loss_weight=weights["plan_loss_weight"])
    return cfg, _model(cfg)


def input_shape(view, time_pool=None):
    consts = _repo_constants()
    pool = consts["train_defaults"]["time_pool"] if time_pool is None else time_pool
    return [consts["VIEW_CHANNELS"][view], TIME_ROWS // pool, consts["FREQ_BINS"]]


# ---------------------------------------------------------------------------------------------------------
# analytic model record (parent process; cheap, no forward pass)

def analytic_model_record(view, width, batch):
    import torch
    from geoml.model import CenterLoss, n_parameters
    cfg, model = build_real_model(view, width, batch)
    n_classes = len(cfg.labels)
    center = CenterLoss(n_classes, model.embedding_dim)
    p_model = n_parameters(model)
    p_center = n_parameters(center)
    p_opt = p_model + p_center
    buffer_bytes = sum(b.numel() * b.element_size() for b in model.buffers())
    state_bytes = sum(v.numel() * v.element_size() for v in model.state_dict().values())
    d = model.embedding_dim
    shape = input_shape(view, cfg.time_pool)
    input_bytes = batch * shape[0] * shape[1] * shape[2] * FP32_BYTES
    weights = _pilot_loss_weights()
    p21b = _p21b_center_weight()
    breakdown = {name: n_parameters(module) for name, module in model.named_children() if module is not None}
    base = "analytic"
    return {
        "n_parameters_model": metric(p_model, "parameters", base, "sum(p.numel()) of the repository SmallResNet incl. aux plan head"),
        "n_parameters_by_block": metric(breakdown, "parameters per top-level block", base, "named_children() of the model"),
        "n_parameters_center_loss": metric(p_center, "parameters", base, f"CenterLoss centers: {n_classes} classes x D"),
        "n_parameters_optimized": metric(p_opt, "parameters", base, "model + center-loss centers: the AdamW parameter list of fit/fit_streaming"),
        "embedding_dim_D": metric(d, "dimensions", base, "model.embedding_dim (= head.in_features)",
                                  equals_16_x_width=bool(d == 16 * width)),
        "p20_weight_times_D": metric(weights["center_loss_weight"] * d, "weight on the per-dimension mean square", base,
                                     "pilot centre weight (request.pilot_loss_weights) x D: the P20 'sum_d' convention expressed per mean-square-per-dimension"),
        "p20_over_p21b_center_term_ratio": metric(weights["center_loss_weight"] * d / p21b, "ratio", base,
                                                  "(pilot centre weight x D) / P21b centre weight (request.p21b_center_weight) = D/2 for 0.005 and 0.01 (K18 packet, section 2); this is the P20-to-P21b ratio, not centre-versus-BCE"),
        "fp32_weight_bytes": metric(FP32_BYTES * p_opt, "bytes", base, "4 B x optimized parameters"),
        "fp32_gradient_bytes": metric(FP32_BYTES * p_opt, "bytes", base, "4 B x optimized parameters (one .grad each)"),
        "fp32_adamw_state_bytes": metric(2 * FP32_BYTES * p_opt, "bytes", base,
                                         "exp_avg + exp_avg_sq, 8 B x optimized parameters; per-tensor step counters excluded"),
        "fp32_static_training_state_bytes": metric(4 * FP32_BYTES * p_opt + buffer_bytes, "bytes", base,
                                                   "weights + gradients + AdamW state (16 B/param) + BatchNorm buffers"),
        "batchnorm_buffer_bytes": metric(buffer_bytes, "bytes", base, "running mean/var + num_batches_tracked"),
        "checkpoint_state_dict_bytes": metric(state_bytes, "bytes", base, "model.state_dict() tensor bytes (what geoml.train.save stores; centers are not saved)"),
        "input_shape_per_sample": metric(shape, "channels x time rows x frequency bins", base,
                                         "VIEW_CHANNELS[view] x 128/time_pool x 512 (geoml.data, TrainConfig.time_pool default)"),
        "input_batch_bytes": metric(input_bytes, "bytes", base, "batch x channels x rows x bins x 4 B (float32)"),
    }


# ---------------------------------------------------------------------------------------------------------
# streaming window arithmetic (repository constants only)

def streaming_window_record(view, groups_per_shard, window_shards, time_pool=None, plan_shift=True):
    consts = _repo_constants()
    pool = consts["train_defaults"]["time_pool"] if time_pool is None else time_pool
    n_labels = len(consts["LABELS"])
    f, t = consts["FREQ_BINS"], TIME_ROWS
    spec_bytes = N_POL * t * f * FP16_BYTES
    mask_bytes = N_POL * f * FP16_BYTES
    residual_bytes = t * f * FP16_BYTES
    raw = spec_bytes + mask_bytes + residual_bytes
    pre = consts["VIEW_CHANNELS"][view] * (t // pool) * f * FP32_BYTES
    copy = (spec_bytes + (residual_bytes if view == "dual_residual" else 0)) if plan_shift else 0
    shard_obs = groups_per_shard * n_labels
    window_obs = shard_obs * window_shards
    train_obs = consts["ROLE_COUNTS"]["train"] * n_labels
    select_obs = consts["ROLE_COUNTS"]["val-select"] * n_labels
    shards = -(-consts["ROLE_COUNTS"]["train"] // groups_per_shard)
    windows = -(-shards // window_shards)
    base = "analytic"
    return {
        "view": view, "groups_per_shard": groups_per_shard, "window_shards": window_shards,
        "shard_observations": metric(shard_obs, "observations", base, "groups_per_shard x 8 labels"),
        "window_observations": metric(window_obs, "observations", base, "shard observations x window_shards"),
        "window_scenario_groups": metric(groups_per_shard * window_shards, "groups", base,
                                         "blocked-shuffle bound: distinct groups a mini-batch can draw from; the 8 variants of a group always share a window"),
        "raw_bytes_per_observation": metric(raw, "bytes", base,
                                            "float16 spec[2,128,512] + mask[2,512] + residual[128,512]; excludes label/seed/plan_consistency arrays and JSON metadata"),
        "preprocessed_bytes_per_observation": metric(pre, "bytes", base, "float32 channels x (128/time_pool) x 512"),
        "plan_shift_copy_bytes_per_observation": metric(copy, "bytes", base,
                                                        "float16 spec (+ residual for dual_residual) kept per window only while K17b plan shift is on (b2_stream._window)"),
        "shard_raw_bytes": metric(shard_obs * raw, "bytes", base, "shard observations x raw bytes"),
        "shard_preprocessed_bytes": metric(shard_obs * pre, "bytes", base, "shard observations x preprocessed bytes"),
        "window_steady_resident_bytes": metric(window_obs * (pre + copy), "bytes", base,
                                               "float32 window inputs + plan-shift float16 copy; excludes per-sample Carrier plan objects, one mini-batch and its augmented copy"),
        "window_build_peak_bytes": metric(window_obs * (raw + pre), "bytes", base,
                                          "upper bound while a window is built: all raw shards plus the float32 inputs; preprocessing temporaries are bounded by PREPROCESS_CHUNK=16 observations and not added"),
        "train_observations": metric(train_obs, "observations", base, "ROLE_COUNTS['train'] groups x 8 labels"),
        "train_shards_per_epoch": metric(shards, "shards", base, "ceil(1500 groups / groups_per_shard)"),
        "train_windows_per_epoch": metric(windows, "windows", base, "ceil(shards / window_shards)"),
        "train_raw_bytes_per_epoch": metric(train_obs * raw, "bytes", base, "train observations x raw bytes"),
        "train_bytes_read_per_epoch_double_read": metric(2 * train_obs * raw, "bytes", base,
                                                         "each shard part is read twice per pass (sha256, then numpy.load; P24 section 2)"),
        "val_select_bytes_read_per_epoch_double_read": metric(2 * select_obs * raw, "bytes", base,
                                                              "val-select inference pass after every epoch, same double read"),
    }


# ---------------------------------------------------------------------------------------------------------
# assumed sample-pass budget

def assumed_budget_record(request, batches):
    consts = _repo_constants()
    n_labels = len(consts["LABELS"])
    train_obs = consts["ROLE_COUNTS"]["train"] * n_labels
    select_obs = consts["ROLE_COUNTS"]["val-select"] * n_labels
    epochs, seeds, views = request["epochs_assumed"], request["seeds_assumed"], len(request["views"])
    low, high = request["throughput_assumed"]
    fits = views * seeds
    passes = train_obs * epochs * fits
    n_obs = metric(train_obs, "observations", "analytic", "ROLE_COUNTS['train'] x 8 labels")
    e = metric(epochs, "epochs", "assumed", "P6 section 4 / TrainConfig default; tagged assumption in P6, not frozen in any config")
    s = metric(seeds, "seeds", "assumed", "P18 section 7 fixes three training seeds (K17); this value is the planning count, seed values 0,1,2 are a harness choice (P25)")
    f = metric(fits, "fits", "assumed", "views x seeds")
    steps = {}
    for batch in batches:
        per_epoch = -(-train_obs // batch)
        steps[str(batch)] = {
            "steps_per_epoch": metric(per_epoch, "optimizer steps", "analytic", "ceil(12000 / batch)"),
            "steps_per_fit": derived_metric(per_epoch * epochs, "optimizer steps", "steps per epoch x assumed epochs = OneCycleLR total_steps", [e]),
        }
    return {
        "train_observations": n_obs,
        "epochs": e, "seeds": s, "views": metric(views, "views", "analytic", "requested views"), "fits": f,
        "training_sample_passes_total": derived_metric(passes, "sample passes", "train observations x epochs x fits", [n_obs, e, f]),
        "val_select_forward_passes_total": derived_metric(select_obs * epochs * fits, "forward-only samples",
                                                          "val-select inference after every epoch (1,200 observations)", [e, f]),
        "assumed_throughput_low": metric(low, "samples/s", "assumed", "planning assumption (E5 plan, budget section 2.1): not measured on any GPU"),
        "assumed_throughput_high": metric(high, "samples/s", "assumed", "planning assumption (E5 plan, budget section 2.1): not measured on any GPU"),
        "pure_training_hours_at_low_throughput": derived_metric(passes / low / 3600.0, "hours", "sample passes / low throughput / 3600; excludes data I/O, evaluation and restarts",
                                                                [e, f, metric(low, "samples/s", "assumed", "")]),
        "pure_training_hours_at_high_throughput": derived_metric(passes / high / 3600.0, "hours", "sample passes / high throughput / 3600; excludes data I/O, evaluation and restarts",
                                                                 [e, f, metric(high, "samples/s", "assumed", "")]),
        "per_batch": steps,
    }


# ---------------------------------------------------------------------------------------------------------
# the probe (runs in a fresh subprocess per configuration; importable for tests)

def _status_kib(key):
    try:
        with open("/proc/self/status") as stream:
            for line in stream:
                if line.startswith(key + ":"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _ru_maxrss_kib():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak // 1024 if sys.platform == "darwin" else peak


def _reset_hwm():
    """Reset the kernel resident-set high-water mark (Linux clear_refs=5); False when unavailable."""
    try:
        with open("/proc/self/clear_refs", "w") as stream:
            stream.write("5")
        return True
    except OSError:
        return False


def probe(view, width, batch, warm_steps=2, measure=True, soft_deadline_s=None, threads=2, reset_hwm=True):
    """Forward-graph tally and (optionally) timed/peak-measured training steps on a synthetic batch. CPU only.

    Returns plain numbers (no labels); ``configuration_record`` wraps them into metric records. ``reset_hwm=False``
    (in-process tests) leaves the host process's resident-set high-water mark alone; step-only peaks are then null.
    """
    started = time.perf_counter()
    import torch
    from torch import nn
    from geoml.model import CenterLoss

    torch.set_num_threads(threads)
    torch.manual_seed(0)
    cfg, model = build_real_model(view, width, batch)
    consts = _repo_constants()
    n_classes = len(cfg.labels)
    center = CenterLoss(n_classes, model.embedding_dim)
    parameters = list(model.parameters()) + list(center.parameters())
    opt = torch.optim.AdamW(parameters, lr=cfg.lr, weight_decay=cfg.weight_decay)
    shape = input_shape(view, cfg.time_pool)
    gen = torch.Generator().manual_seed(0)
    x = torch.randn(batch, *shape, generator=gen)
    y = torch.randint(n_classes, (batch,), generator=gen)
    plan_target = torch.randint(2, (batch,), generator=gen).float()
    persistent = {t.untyped_storage().data_ptr() for t in list(model.parameters()) + list(model.buffers()) + list(center.parameters())}

    def augmented():
        flip = torch.rand(batch, generator=gen) < 0.5
        xb = torch.where(flip[:, None, None, None], x.flip(-1), x)
        return xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)

    def forward_loss(xb):
        logits, aux, embedding = model.forward_all(xb)
        loss = nn.functional.cross_entropy(logits, y)
        loss = loss + cfg.center_loss_weight * center(embedding, y)
        return loss + cfg.plan_loss_weight * nn.functional.binary_cross_entropy_with_logits(aux[:, 0], plan_target)

    def train_step(tally=False):
        xb = augmented()
        saved, macs = {}, [0]
        handles = []
        if tally:
            input_ptr = xb.untyped_storage().data_ptr()

            def pack(tensor):
                storage = tensor.untyped_storage()
                pointer = storage.data_ptr()
                if pointer and pointer not in persistent and pointer != input_ptr:
                    saved[pointer] = storage.nbytes()
                return tensor

            def count(module, _inputs, output):
                if isinstance(module, nn.Conv2d):
                    macs[0] += output.numel() // batch * (module.in_channels // module.groups) * module.kernel_size[0] * module.kernel_size[1]
                else:
                    macs[0] += module.in_features * module.out_features

            handles = [m.register_forward_hook(count) for m in model.modules() if isinstance(m, (nn.Conv2d, nn.Linear))]
            try:
                with torch.autograd.graph.saved_tensors_hooks(pack, lambda tensor: tensor):
                    loss = forward_loss(xb)
            finally:
                for handle in handles:
                    handle.remove()
        else:
            loss = forward_loss(xb)
        if measure:
            opt.zero_grad()
            loss.backward()
            opt.step()
        return saved, macs[0]

    result = {"view": view, "width": width, "batch": batch, "measured": None}
    if not measure:
        saved, macs = train_step(tally=True)
        result.update(saved_activation_bytes=sum(saved.values()), saved_activation_tensors=len(saved), forward_macs_per_sample=macs)
        return result

    rss_baseline = _status_kib("VmRSS")
    reset = _reset_hwm() if reset_hwm else False
    before_cold = _status_kib("VmRSS")
    t0 = time.perf_counter()
    saved, macs = train_step(tally=True)
    cold_wall = time.perf_counter() - t0
    cold_peak = _status_kib("VmHWM") if reset else None
    cold_ru = _ru_maxrss_kib()
    result.update(saved_activation_bytes=sum(saved.values()), saved_activation_tensors=len(saved), forward_macs_per_sample=macs)
    warm_walls, warm_peaks = [], []
    for _ in range(warm_steps):
        if soft_deadline_s is not None and time.perf_counter() - started > soft_deadline_s:
            break
        if reset:
            reset = _reset_hwm()
        t0 = time.perf_counter()
        train_step()
        warm_walls.append(time.perf_counter() - t0)
        warm_peaks.append(_status_kib("VmHWM") if reset else None)
    result["measured"] = {
        "hwm_reset_available": bool(reset),
        "rss_baseline_kib": rss_baseline,
        "rss_before_cold_step_kib": before_cold,
        "cold_step_wall_s": cold_wall,
        "cold_step_peak_rss_kib": cold_peak,
        "cold_step_peak_rss_ru_maxrss_kib": cold_ru,
        "warm_steps_completed": len(warm_walls),
        "warm_step_wall_s_median": statistics.median(warm_walls) if warm_walls else None,
        "warm_step_peak_rss_kib_max": max(p for p in warm_peaks if p is not None) if any(p is not None for p in warm_peaks) else None,
        "process_ru_maxrss_kib": _ru_maxrss_kib(),
        "probe_wall_s": time.perf_counter() - started,
    }
    return result


# ---------------------------------------------------------------------------------------------------------
# parent: subprocess per configuration, record assembly

def run_child(spec, cap_s):
    """One configuration in a fresh subprocess with a wall-clock cap. Returns ({probe result}|None, status, note)."""
    env = dict(os.environ)
    threads = str(spec["threads"])
    env.update(OMP_NUM_THREADS=threads, OPENBLAS_NUM_THREADS=threads, MKL_NUM_THREADS=threads,
               CUDA_VISIBLE_DEVICES="", PYTHONHASHSEED="0")
    try:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", json.dumps(spec)],
                                   capture_output=True, text=True, timeout=cap_s, env=env, cwd=str(REPO))
    except subprocess.TimeoutExpired:
        return None, "timeout", f"killed after the {cap_s:g} s wall-clock cap"
    lines = [line for line in completed.stdout.splitlines() if line.startswith(CHILD_PREFIX)]
    if completed.returncode != 0 or not lines:
        return None, "error", (completed.stderr or "no output").strip()[-400:]
    return json.loads(lines[-1][len(CHILD_PREFIX):]), "ok", None


def _none_metric(unit, how, note):
    return metric(None, unit, "measured", how, note=note)


def measured_records(probe_result, status, note, measure):
    if not measure:
        return {"status": "not_requested", "note": "--no-measure: no training step was run"}
    unit_kib = "KiB"
    if probe_result is None or probe_result["measured"] is None:
        why = note or "no measurement"
        return {"status": status, "note": why,
                **{name: _none_metric(unit, "unavailable", why) for name, unit in (
                    ("rss_baseline_kib", unit_kib), ("cold_step_wall_s", "s"), ("cold_step_peak_rss_kib", unit_kib),
                    ("warm_step_wall_s_median", "s"), ("warm_step_samples_per_s", "samples/s"))}}
    m = probe_result["measured"]
    batch = probe_result["batch"]
    peak_over = None if m["cold_step_peak_rss_kib"] is None or m["rss_baseline_kib"] is None else m["cold_step_peak_rss_kib"] - m["rss_baseline_kib"]
    warm_over = None if m["warm_step_peak_rss_kib_max"] is None or m["rss_baseline_kib"] is None else m["warm_step_peak_rss_kib_max"] - m["rss_baseline_kib"]
    ok = "measured"
    reset_note = ("VmHWM after clear_refs reset" if m["hwm_reset_available"] else
                  "clear_refs reset unavailable: only the lifetime ru_maxrss is recorded, step-only peaks are null")
    return {
        "status": "ok", "note": "synthetic random batch of the real input shape; CPU; excludes data loading, preprocessing and K17b re-preprocessing",
        "hwm_reset_available": m["hwm_reset_available"],
        "rss_baseline_kib": metric(m["rss_baseline_kib"], unit_kib, ok, "VmRSS after imports, model, optimizer and synthetic batch were built, before any step"),
        "cold_step_wall_s": metric(m["cold_step_wall_s"], "s", ok, "first forward+backward+AdamW step incl. lazy kernel/oneDNN initialisation and the saved-tensor tally hooks"),
        "cold_step_peak_rss_kib": metric(m["cold_step_peak_rss_kib"], unit_kib, ok, f"{reset_note}; absolute process peak during the cold step"),
        "cold_step_peak_over_baseline_kib": metric(peak_over, unit_kib, ok, "cold-step peak minus baseline RSS: step cost incl. one-off library workspaces"),
        "cold_step_ru_maxrss_kib": metric(m["cold_step_peak_rss_ru_maxrss_kib"], unit_kib, ok, "resource.getrusage ru_maxrss after the cold step (lifetime peak incl. imports)"),
        "warm_steps_completed": metric(m["warm_steps_completed"], "steps", ok, "warm steps finished inside the soft deadline"),
        "warm_step_wall_s_median": metric(m["warm_step_wall_s_median"], "s", ok, "median wall time of the warm steps on this CPU under whatever load existed"),
        "warm_step_samples_per_s": metric(None if not m["warm_step_wall_s_median"] else batch / m["warm_step_wall_s_median"], "samples/s", ok,
                                          "batch / median warm step wall time; CPU, single step loop, no data I/O: says nothing about GPU throughput"),
        "warm_step_peak_rss_kib_max": metric(m["warm_step_peak_rss_kib_max"], unit_kib, ok, f"{reset_note}; largest absolute peak over the warm steps"),
        "warm_step_peak_over_baseline_kib": metric(warm_over, unit_kib, ok, "warm-step peak minus baseline RSS (steady-state step cost; retained allocator memory included)"),
        "process_ru_maxrss_kib": metric(m["process_ru_maxrss_kib"], unit_kib, ok, "resource.getrusage ru_maxrss at the end of the probe process"),
        "probe_wall_s": metric(m["probe_wall_s"], "s", ok, "wall time inside the child after imports"),
    }


def gpu_vram_record(analytic, probe_result):
    """Analytic GPU memory estimate: static state + saved activations + input (+ activation gradients bound)."""
    static = analytic["fp32_static_training_state_bytes"]
    inputs = analytic["input_batch_bytes"]
    if probe_result is None:
        return {"label": GPU_LABEL, "lower_bound_bytes": metric(None, "bytes", "analytic", "graph tally unavailable for this configuration", note=GPU_LABEL),
                "upper_bound_bytes": metric(None, "bytes", "analytic", "graph tally unavailable for this configuration", note=GPU_LABEL)}
    saved = metric(probe_result["saved_activation_bytes"], "bytes", "analytic",
                   "autograd saved tensors of one forward pass, de-duplicated by storage, fp32, parameters/buffers/input excluded")
    lower = static["value"] + inputs["value"] + saved["value"]
    upper = lower + saved["value"]
    return {
        "label": GPU_LABEL,
        "saved_activation_bytes": saved,
        "saved_activation_tensors": metric(probe_result["saved_activation_tensors"], "storages", "analytic", "distinct storages kept alive for backward"),
        "lower_bound_bytes": metric(lower, "bytes", "analytic", "static state + input batch + saved activations; " + GPU_LABEL,
                                    excludes="CUDA context, cuDNN/cuBLAS workspaces, allocator fragmentation, mixed-precision effects"),
        "upper_bound_bytes": metric(upper, "bytes", "analytic",
                                    "lower bound + activation gradients, bounded by the saved-activation bytes (gradients have the shape of the activations); " + GPU_LABEL,
                                    excludes="CUDA context, cuDNN/cuBLAS workspaces, allocator fragmentation, mixed-precision effects"),
    }


def configuration_record(view, width, batch, request, measure, run=None):
    run = run or run_child          # resolved at call time so that tests can substitute the runner
    analytic = analytic_model_record(view, width, batch)
    spec = {"view": view, "width": width, "batch": batch, "warm_steps": request["warm_steps"], "measure": measure,
            "threads": request["threads"], "soft_deadline_s": 0.85 * request["time_cap_s"]}
    result, status, note = run(spec, request["time_cap_s"])
    graph = {}
    if result is not None:
        graph = {
            "saved_activation_bytes_per_batch": metric(result["saved_activation_bytes"], "bytes", "analytic",
                                                       "autograd saved-tensor tally of the real graph at this batch (see gpu_vram.saved_activation_bytes)"),
            "forward_macs_per_sample": metric(result["forward_macs_per_sample"], "multiply-accumulates", "analytic",
                                              "Conv2d + Linear output size x kernel fan-in, from forward hooks on the real model"),
        }
    return {"view": view, "width": width, "batch": batch, "status": status,
            "analytic": analytic, "forward_graph": graph, "gpu_vram": gpu_vram_record(analytic, result),
            "measured": measured_records(result, status, note, measure)}


def environment_record(start_load):
    def first_line(path, prefix):
        try:
            with open(path) as stream:
                for line in stream:
                    if line.startswith(prefix):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
        return None

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    def version(name):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    mem = first_line("/proc/meminfo", "MemTotal")
    status = git("status", "--porcelain")
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(), "platform": platform.platform(),
        "torch": version("torch"), "numpy": version("numpy"),
        "cpu_model": first_line("/proc/cpuinfo", "model name"),
        "cpu_count": metric(os.cpu_count(), "cpus", "measured", "os.cpu_count()"),
        "host_ram_kib": metric(int(mem.split()[0]) if mem else None, "KiB", "measured", "/proc/meminfo MemTotal"),
        "load_average_before": metric(start_load, "1-minute load", "measured", "os.getloadavg() at start; concurrent load disturbs the timings"),
        "load_average_after": metric(os.getloadavg()[0] if hasattr(os, "getloadavg") else None, "1-minute load", "measured", "os.getloadavg() at the end"),
        "git_head": git("rev-parse", "HEAD"), "git_working_tree_dirty": None if status is None else bool(status),
        "device": "cpu (children run with CUDA_VISIBLE_DEVICES='')",
    }


def build_document(request, measure=True, run=None, log=lambda message: None):
    started = time.monotonic()
    start_load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
    consts = _repo_constants()
    configs = []
    for view in request["views"]:
        for width in request["widths"]:
            for batch in request["batches"]:
                if time.monotonic() - started > request["total_cap_s"]:
                    configs.append({"view": view, "width": width, "batch": batch, "status": "skipped_total_cap",
                                    "note": f"whole-run wall-clock cap of {request['total_cap_s']:g} s reached before this configuration"})
                    continue
                log(f"  {view} width {width} batch {batch}")
                configs.append(configuration_record(view, width, batch, request, measure, run))
    windows = [streaming_window_record(view, gps, ws) for view in request["views"]
               for gps in request["groups_per_shard"] for ws in request["window_shards"]]
    return {
        "schema": SCHEMA,
        "status": "READ_ONLY_FOOTPRINT_NOT_A_TRAINING_RESULT",
        "benchmark_complete": False,
        "purpose": "Resource footprint of the B2 SmallResNet for the E7a candidate training specification. No model was trained, no data was read, no GPU was used.",
        "basis_definitions": {
            "measured": "observed on this CPU in this run; depends on machine, load and library build",
            "analytic": "deterministic function of repository constants, shapes or the real model object; no resource was observed",
            "assumed": "taken from a planning document or a stated assumption; not measured here",
            "derived": "a value computed from several records carries the weakest basis: assumed, then measured, then analytic",
        },
        "request": {**request, "pilot_loss_weights": _pilot_loss_weights(), "p21b_center_weight": _p21b_center_weight(),
                    "probe_optimizer": {"name": "AdamW", "lr": consts["train_defaults"]["lr"], "weight_decay": consts["train_defaults"]["weight_decay"]},
                    "measure": bool(measure)},
        "caps": {"max_batch": MAX_BATCH, "max_width": MAX_WIDTH, "max_time_cap_s": MAX_TIME_CAP_S, "max_total_cap_s": MAX_TOTAL_CAP_S,
                 "max_warm_steps": MAX_WARM_STEPS, "max_configurations": MAX_CONFIGS, "max_threads": MAX_THREADS},
        "environment": environment_record(start_load),
        "configurations": configs,
        "streaming_windows": windows,
        "assumed_budget": assumed_budget_record(request, request["batches"]),
        "limitations": [
            "One synthetic random batch of the real input shape; no data, no loss landscape, no recognition quality.",
            "Measured peaks are CPU host memory including allocator retention; they are not GPU memory.",
            "The probe step omits data loading, preprocessing, K17b plan-shift re-preprocessing and window handling; those are analytic (streaming_windows) or measured elsewhere (docs/results/b2_streaming_memory.md).",
            "GPU VRAM entries are analytic estimates, not measured; the authorized GPU probe (DR-05) must replace them.",
            "Wall times are single-step CPU timings under whatever load existed (see environment.load_average_*); they do not support the 200-1000 samples/s GPU assumption in either direction.",
        ],
    }


# ---------------------------------------------------------------------------------------------------------
# CLI

def _child_main(raw):
    spec = json.loads(raw)
    result = probe(spec["view"], spec["width"], spec["batch"], warm_steps=spec["warm_steps"], measure=spec["measure"],
                   soft_deadline_s=spec.get("soft_deadline_s"), threads=spec["threads"])
    print(CHILD_PREFIX + json.dumps(_plain(result), allow_nan=False))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--child":
        return _child_main(argv[1])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="new JSON file; an existing file is never overwritten")
    parser.add_argument("--views", nargs="+", default=list(VIEW_NAMES))
    parser.add_argument("--widths", nargs="+", type=int, default=[8, 16, 32])
    parser.add_argument("--batches", nargs="+", type=int, default=[8, 32])
    parser.add_argument("--groups-per-shard", nargs="+", type=int, default=[4, 8])
    parser.add_argument("--window-shards", nargs="+", type=int, default=[1, 4])
    parser.add_argument("--time-cap-s", type=float, default=DEFAULT_TIME_CAP_S, help=f"per configuration, max {MAX_TIME_CAP_S:g}")
    parser.add_argument("--total-cap-s", type=float, default=DEFAULT_TOTAL_CAP_S, help=f"whole run, max {MAX_TOTAL_CAP_S:g}")
    parser.add_argument("--warm-steps", type=int, default=2)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--epochs-assumed", type=int, default=30)
    parser.add_argument("--seeds-assumed", type=int, default=3)
    parser.add_argument("--throughput-assumed", nargs=2, type=float, default=[200.0, 1000.0], metavar=("LOW", "HIGH"))
    parser.add_argument("--no-measure", action="store_true", help="skip training steps; keep the forward-graph tally and analytic parts")
    args = parser.parse_args(argv)
    try:
        request = validate_request(args.views, args.widths, args.batches, args.groups_per_shard, args.window_shards,
                                   args.time_cap_s, args.total_cap_s, args.warm_steps, args.threads, args.epochs_assumed,
                                   args.throughput_assumed, args.seeds_assumed)
        if Path(args.out).exists():
            raise FileExistsError(f"{args.out} already exists; this tool never overwrites")
        document = build_document(request, measure=not args.no_measure, log=lambda message: print(message, file=sys.stderr))
        write_new_json(args.out, document)
    except (FootprintError, FileExistsError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
