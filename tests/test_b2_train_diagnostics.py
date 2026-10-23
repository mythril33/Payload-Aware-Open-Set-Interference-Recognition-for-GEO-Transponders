"""K18 training diagnostics (E7a Phase 3): observation-only, training-batches-only, and provably inert.

Proof structure (nothing here is a recognition result; the fixture is random spectra with one tone per class):

1. GOLDEN values were captured from origin/main 755b474 with the *unmodified* ``geoml.train`` and
   ``geoml.b2_stream`` before the diagnostics were added. After the change the trainers must reproduce
   them exactly (history, final weights, selected epoch, validation logits).
2. ORACLES are verbatim copies of the pre-change training loops kept in this file. Floating point results
   depend on the CPU and the thread count, so the golden comparison is skipped for any case whose own oracle
   no longer reproduces the golden (a different machine); the live comparison against the oracle never
   skips and is the platform-independent proof of bit-identity.
3. An independent single-epoch replication of the ORIGINAL loss formula proves bit-equal parameter
   gradients and updates for every plan-head/center combination, and independently recomputes the
   diagnostics themselves.
"""
import hashlib
import json
import math
import time
from dataclasses import asdict, fields

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from torch import nn
from torch.optim.optimizer import register_optimizer_step_pre_hook

import geoml.train as tr
from geoml.b2_stream import (B2Source, _batches, _concat, _require, _small, fit_streaming, infer_streaming)
from geoml.b2_stream import _training_reference as stream_reference
from geoml.metrics import macro_f1
from geoml.model import CenterLoss, SmallResNet, n_parameters
from geoml.train import (DIAGNOSTICS_SCHEMA, TrainConfig, TrainDiagnostics, fit, infer, load, save)
from geosim.b2_protocol import LABELS, ROLE_STARTS

N_BINS = 512
N_TRAIN = 48
PLAN = [dict(f0=-9e6, symbol_rate=6e6, alpha=0.2, mod="QPSK", power=0.6, code_rate=None),
        dict(f0=7e6, symbol_rate=4.8e6, alpha=0.25, mod="8PSK", power=0.4, code_rate=None)]


def _quiet(*_args, **_kwargs):
    return None


@pytest.fixture(scope="module", autouse=True)
def pinned_threads():
    """Float results depend on the intra-op thread count; the goldens were captured with two threads."""
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


# ---------------------------------------------------------------------------------------------------
# fixture (identical to the helpers used for the golden capture)

def make_split(role, n_groups, seed):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(ROLE_STARTS[role], ROLE_STARTS[role] + n_groups), len(LABELS))
    labels = np.tile(np.arange(len(LABELS)), n_groups)
    n = len(labels)
    spec = rng.normal(-80, 2, (n, 2, 8, N_BINS)).astype(np.float16)
    for index in range(len(LABELS)):
        spec[labels == index, 0, :, 40 + 30 * index] += 20
    mask = np.full((n, 2, N_BINS), -60, np.float16)
    mask[:, :, 200:312] = 0
    residual = (spec[:, 0].astype(np.float32) - 12).astype(np.float16)
    return {"spec": spec, "mask": mask, "residual": residual, "label": labels.astype(np.int8),
            "seed": groups.astype(np.int64), "plan_consistency": (groups % 2).astype(np.int8),
            "meta": [{"scenario_id": int(g), "plans": [PLAN, PLAN]} for g in groups]}


def splits():
    return make_split("train", 6, 1), make_split("val-select", 2, 2)


CONFIGS = {
    "A_plan_center": dict(input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005,
                          plan_loss_weight=1.0, augment=True, epochs=6, batch=4, width=4, lr=0.03, seed=0),
    "B_plain": dict(input_mode="dual", plan_consistency=False, center_loss_weight=0.0, augment=True,
                    epochs=5, batch=5, width=4, lr=0.03, seed=3),
    "D_multi_window": dict(input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005,
                           plan_loss_weight=1.0, augment=True, epochs=6, batch=4, width=4, lr=0.03, seed=2),
    "C_plan_center_shift": dict(input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005,
                                plan_loss_weight=1.0, plan_shift_fraction=0.5, augment=True, epochs=6, batch=6,
                                width=4, lr=0.03, seed=1),
}


def cfg_of(name, **changes):
    return TrainConfig(labels=LABELS, **{**CONFIGS[name], **changes})


def multi_shard_source(split, role, n_shards=3):
    """The split cut into ``n_shards`` equal in-memory shards (two scenario groups each)."""
    size = len(split["label"]) // n_shards
    pieces = [{key: value[i * size:(i + 1) * size] for key, value in split.items()} for i in range(n_shards)]
    index = _concat([_small(piece, "known") for piece in pieces])
    return B2Source("known", index, [size] * n_shards, lambda order: iter([pieces[i] for i in order]), role=role,
                    has_residual=True)


def state_digest(model):
    h = hashlib.sha256()
    for key, value in sorted(model.state_dict().items()):
        array = value.detach().cpu().contiguous().numpy()
        h.update(key.encode() + str(array.dtype).encode() + repr(array.shape).encode() + array.tobytes())
    return h.hexdigest()


def array_digest(array):
    return hashlib.sha256(np.ascontiguousarray(array, dtype=np.float32).tobytes()).hexdigest()


def summarize(fitted, logits):
    return {"train_loss": [repr(r["train_loss"]) for r in fitted["history"]],
            "val_macro_f1": [repr(r["val_macro_f1"]) for r in fitted["history"]],
            "val_plan_accuracy": [repr(r["val_plan_accuracy"]) for r in fitted["history"] if "val_plan_accuracy" in r],
            "best_epoch": fitted["best_epoch"], "best_val_macro_f1": repr(fitted["best_val_macro_f1"]),
            "absolute_ref_db": repr(fitted["absolute_ref_db"]),
            "state_sha256": state_digest(fitted["model"]),
            "val_logits_sha256": array_digest(logits), "val_logits_row0": [repr(float(v)) for v in logits[0]]}


# ---------------------------------------------------------------------------------------------------
# GOLDEN: captured from origin/main 755b474 (unmodified src/geoml/train.py and src/geoml/b2_stream.py) BEFORE
# the K18 diagnostics edit. Environment of the capture: Python 3.13.17, torch 2.14.1+cu130 (CPU, 2 threads),
# numpy 2.5.4, Intel Xeon @ 2.10 GHz. Floats are stored with repr(); hashes cover the final best-epoch state_dict
# bytes and the float32 validation logits.

GOLDEN = {
    "A_plan_center/legacy": {
        "train_loss": ["4.355511367321014", "2.9214531977971396", "2.5472585161527", "2.484011948108673", "2.3764229814211526", "2.3645973205566406"],
        "val_macro_f1": ["0.027777777777777776", "0.027777777777777776", "0.0", "0.0", "0.125", "0.11904761904761904"],
        "val_plan_accuracy": ["0.5", "0.5", "0.5", "0.5", "0.5", "0.5"],
        "best_epoch": 4,
        "best_val_macro_f1": "0.125",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "d863c3bf041a6a027a35d2e2303c9c3a00f27e5e8b1345772a752caf56705865",
        "val_logits_sha256": "2d3590315e7cd3dfe54e9ec848541496096f256802ae1f3bd9eb1c6af7f7f8d6",
        "val_logits_row0": ["0.4328840970993042", "0.2053213268518448", "0.22612276673316956", "0.46954524517059326", "0.20233330130577087", "0.3749779164791107", "-1.6429722309112549", "-1.5481048822402954"],
    },
    "A_plan_center/streaming": {
        "train_loss": ["4.355511367321014", "2.9214531977971396", "2.5472585161527", "2.484011948108673", "2.3764229814211526", "2.3645973205566406"],
        "val_macro_f1": ["0.027777777777777776", "0.027777777777777776", "0.0", "0.0", "0.125", "0.11904761904761904"],
        "val_plan_accuracy": ["0.5", "0.5", "0.5", "0.5", "0.5", "0.5"],
        "best_epoch": 4,
        "best_val_macro_f1": "0.125",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "d863c3bf041a6a027a35d2e2303c9c3a00f27e5e8b1345772a752caf56705865",
        "val_logits_sha256": "2d3590315e7cd3dfe54e9ec848541496096f256802ae1f3bd9eb1c6af7f7f8d6",
        "val_logits_row0": ["0.4328840970993042", "0.2053213268518448", "0.22612276673316956", "0.46954524517059326", "0.20233330130577087", "0.3749779164791107", "-1.6429722309112549", "-1.5481048822402954"],
    },
    "B_plain/legacy": {
        "train_loss": ["2.600375160574913", "2.560570607582728", "2.2188536003232002", "2.045906201004982", "1.8165843908985455"],
        "val_macro_f1": ["0.027777777777777776", "0.027777777777777776", "0.027777777777777776", "0.11904761904761904", "0.15606060606060607"],
        "val_plan_accuracy": [],
        "best_epoch": 4,
        "best_val_macro_f1": "0.15606060606060607",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "205b6a0059fe73d10316ea8f350ba155fdce81ec26e956fddb7cb1ce06114424",
        "val_logits_sha256": "6fa950f1cbc1a0226f27ba228f625f9d45609dfebea97704e1d76e25ad4581db",
        "val_logits_row0": ["-0.05943145230412483", "0.13813331723213196", "-1.131443738937378", "0.30450478196144104", "0.2045198678970337", "0.39777904748916626", "-0.9222317934036255", "-1.4533772468566895"],
    },
    "B_plain/streaming": {
        "train_loss": ["2.600375160574913", "2.560570607582728", "2.2188536003232002", "2.045906201004982", "1.8165843908985455"],
        "val_macro_f1": ["0.027777777777777776", "0.027777777777777776", "0.027777777777777776", "0.11904761904761904", "0.15606060606060607"],
        "val_plan_accuracy": [],
        "best_epoch": 4,
        "best_val_macro_f1": "0.15606060606060607",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "205b6a0059fe73d10316ea8f350ba155fdce81ec26e956fddb7cb1ce06114424",
        "val_logits_sha256": "6fa950f1cbc1a0226f27ba228f625f9d45609dfebea97704e1d76e25ad4581db",
        "val_logits_row0": ["-0.05943145230412483", "0.13813331723213196", "-1.131443738937378", "0.30450478196144104", "0.2045198678970337", "0.39777904748916626", "-0.9222317934036255", "-1.4533772468566895"],
    },
    "C_plan_center_shift/legacy": {
        "train_loss": ["4.511035263538361", "3.2801409363746643", "2.8620698153972626", "2.5778234899044037", "2.602340430021286", "2.512856036424637"],
        "val_macro_f1": ["0.027777777777777776", "0.0", "0.0", "0.029411764705882353", "0.029411764705882353", "0.20833333333333331"],
        "val_plan_accuracy": ["0.5", "0.5", "0.5", "0.5", "0.5", "0.5"],
        "best_epoch": 5,
        "best_val_macro_f1": "0.20833333333333331",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "df08947f6a6dde4d636348d821afe1d8ffce9073651ed965bdab20845fcc846c",
        "val_logits_sha256": "4afd81c08c7e1c9b735fd1829153b5161a81a88e1b1fca1b0f7274b283abbbd0",
        "val_logits_row0": ["0.24618016183376312", "0.06168241798877716", "-0.011446155607700348", "0.18836982548236847", "-0.11488184332847595", "0.05646098405122757", "-0.95005202293396", "-0.00606176070868969"],
    },
    "C_plan_center_shift/streaming": {
        "train_loss": ["4.511035263538361", "3.2801409363746643", "2.8620698153972626", "2.5778234899044037", "2.602340430021286", "2.512856036424637"],
        "val_macro_f1": ["0.027777777777777776", "0.0", "0.0", "0.029411764705882353", "0.029411764705882353", "0.20833333333333331"],
        "val_plan_accuracy": ["0.5", "0.5", "0.5", "0.5", "0.5", "0.5"],
        "best_epoch": 5,
        "best_val_macro_f1": "0.20833333333333331",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "df08947f6a6dde4d636348d821afe1d8ffce9073651ed965bdab20845fcc846c",
        "val_logits_sha256": "4afd81c08c7e1c9b735fd1829153b5161a81a88e1b1fca1b0f7274b283abbbd0",
        "val_logits_row0": ["0.24618016183376312", "0.06168241798877716", "-0.011446155607700348", "0.18836982548236847", "-0.11488184332847595", "0.05646098405122757", "-0.95005202293396", "-0.00606176070868969"],
    },
    "D_multi_window/streaming_multi": {
        "train_loss": ["4.3048869371414185", "3.0871917009353638", "2.7902000745137534", "2.5236032803853354", "2.469398299853007", "2.4508201281229653"],
        "val_macro_f1": ["0.0", "0.027777777777777776", "0.027777777777777776", "0.027777777777777776", "0.08333333333333333", "0.2013888888888889"],
        "val_plan_accuracy": ["0.5", "0.5", "0.5", "0.5", "0.5", "0.4375"],
        "best_epoch": 5,
        "best_val_macro_f1": "0.2013888888888889",
        "absolute_ref_db": "-78.85132790103317",
        "state_sha256": "89329b679050e126ce67ef38731bd2c64e21aabaada630cae8b921c925eccb53",
        "val_logits_sha256": "3cb55c51f637a02968aeaba1178f1505c7f6118a56bbe22001f6249f7488e529",
        "val_logits_row0": ["0.22215647995471954", "0.2584116458892822", "0.15274934470653534", "0.23142163455486298", "0.23941418528556824", "0.30288150906562805", "-1.0588237047195435", "-1.257211446762085"],
        "shard_orders": [[0, 2, 1], [0, 1, 2], [1, 2, 0], [2, 0, 1], [1, 2, 0], [2, 1, 0]],
    },
}


# ---------------------------------------------------------------------------------------------------
# oracles: VERBATIM copies of the pre-change training loops (origin/main 755b474), minus timing/logging

def reference_fit(train, val, cfg, device="cpu"):
    tr._labels(train, len(cfg.labels), "training")
    tr._labels(val, len(cfg.labels), "validation")
    if not len(train["spec"]) or not len(val["spec"]):
        raise ValueError("training and validation data must be nonempty")
    torch.manual_seed(cfg.seed)
    ref = tr._training_reference(train, cfg)      # training co-pol data only
    xt, xv = tr._inputs(train, cfg, ref), tr._inputs(val, cfg, ref)
    yt = torch.from_numpy(tr._labels(train, len(cfg.labels), "training"))
    pt = pv = None
    if cfg.plan_consistency:
        pt = torch.from_numpy(tr._plan_targets(train, "training")).float()
        pv = tr._plan_targets(val, "validation")
    train_plans = tr._training_plans(train, cfg) if cfg.plan_shift_fraction > 0 else None
    model = tr._model(cfg).to(device)
    center = CenterLoss(len(cfg.labels), model.embedding_dim).to(device) if cfg.center_loss_weight > 0 else None
    parameters = list(model.parameters()) + ([] if center is None else list(center.parameters()))
    opt = torch.optim.AdamW(parameters, lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = cfg.epochs * -(-len(xt) // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)
    gen = torch.Generator().manual_seed(cfg.seed)
    best, best_state, best_epoch, history = -1.0, None, None, []
    for epoch in range(cfg.epochs):
        model.train()
        loss_sum = 0.0
        perm = torch.randperm(len(xt), generator=gen)
        for i in range(0, len(perm), cfg.batch):
            idx = perm[i:i + cfg.batch]
            xb = xt[idx]
            if train_plans is not None:        # K17b: label-preserving operator-plan shift, training only
                xb = tr._apply_plan_shift(xb, idx, train, train_plans, cfg, ref, gen)
            if cfg.augment:
                flip = torch.rand(len(idx), generator=gen) < 0.5
                xb = torch.where(flip[:, None, None, None], xb.flip(-1), xb)
                xb = xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)
            logits, aux, embedding = model.forward_all(xb.to(device))
            targets = yt[idx].to(device)
            loss = nn.functional.cross_entropy(logits, targets)
            if center is not None:
                loss = loss + cfg.center_loss_weight * center(embedding, targets)
            if aux is not None:
                loss = loss + cfg.plan_loss_weight * nn.functional.binary_cross_entropy_with_logits(
                    aux[:, 0], pt[idx].to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * len(idx)
        outputs = tr._forward(model, xv, device)
        f1 = macro_f1(val["label"], outputs["logits"].argmax(1), len(cfg.labels))
        record = {"epoch": epoch, "train_loss": loss_sum / len(xt), "val_macro_f1": f1}
        if pv is not None:
            record["val_plan_accuracy"] = float(np.mean((outputs["plan_logits"][:, 0] > 0) == (pv == 1)))
        history.append(record)
        if f1 > best:
            best, best_epoch = f1, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "best_epoch": best_epoch, "best_val_macro_f1": best,
            "n_parameters": n_parameters(model), "device": device}


def reference_fit_streaming(train, val, cfg, *, window_shards, device="cpu"):
    _require(train, cfg, "training", "train")
    _require(val, cfg, "validation", "val-select")
    if np.intersect1d(train.groups, val.groups).size:
        raise ValueError("training and validation scenario groups must be disjoint")
    torch.manual_seed(cfg.seed)
    ref = stream_reference(train, cfg)
    with_plans = cfg.plan_shift_fraction > 0
    model = tr._model(cfg).to(device)
    center = CenterLoss(len(cfg.labels), model.embedding_dim).to(device) if cfg.center_loss_weight > 0 else None
    parameters = list(model.parameters()) + ([] if center is None else list(center.parameters()))
    opt = torch.optim.AdamW(parameters, lr=cfg.lr, weight_decay=cfg.weight_decay)
    n = len(train)
    steps = cfg.epochs * -(-n // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)
    gen = torch.Generator().manual_seed(cfg.seed)
    pv = val.index["plan_consistency"] if cfg.plan_consistency else None
    best, best_state, best_epoch, history, orders = -1.0, None, None, [], []
    for epoch in range(cfg.epochs):
        model.train()
        loss_sum, n_steps = 0.0, 0
        order = (torch.randperm(train.n_shards, generator=gen).tolist() if train.n_shards > window_shards
                 else list(range(train.n_shards)))
        orders.append(order)
        for batch in _batches(train, cfg, ref, gen, window_shards, with_plans, order):
            xb = batch["x"]
            if with_plans:
                raw = {"spec": batch["spec"]}
                if batch["residual"] is not None:
                    raw["residual"] = batch["residual"]
                xb = tr._apply_plan_shift(xb, torch.arange(len(xb)), raw, batch["plans"], cfg, ref, gen)
            if cfg.augment:
                flip = torch.rand(len(xb), generator=gen) < 0.5
                xb = torch.where(flip[:, None, None, None], xb.flip(-1), xb)
                xb = xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)
            logits, aux, embedding = model.forward_all(xb.to(device))
            targets = batch["y"].to(device)
            loss = nn.functional.cross_entropy(logits, targets)
            if center is not None:
                loss = loss + cfg.center_loss_weight * center(embedding, targets)
            if aux is not None:
                loss = loss + cfg.plan_loss_weight * nn.functional.binary_cross_entropy_with_logits(
                    aux[:, 0], batch["p"].to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * len(xb)
            n_steps += 1
        outputs = infer_streaming({"model": model, "config": cfg, "absolute_ref_db": ref, "device": device}, val)
        f1 = macro_f1(val.index["label"], outputs["logits"].argmax(1), len(cfg.labels))
        record = {"epoch": epoch, "train_loss": loss_sum / n, "val_macro_f1": f1}
        if pv is not None:
            record["val_plan_accuracy"] = float(np.mean((outputs["plan_logits"][:, 0] > 0) == (pv == 1)))
        history.append(record)
        if f1 > best:
            best, best_epoch = f1, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "best_epoch": best_epoch, "best_val_macro_f1": best,
            "n_parameters": n_parameters(model), "device": device,
            "streaming": {"shard_orders": orders}}


_RUNS = {}


def run(key, impl):
    """(fitted, validation logits, global RNG digest) for a golden key with the instrumented ('new') or the oracle."""
    cache_key = (key, impl)
    if cache_key in _RUNS:
        return _RUNS[cache_key]
    name, path = key.split("/")
    cfg = cfg_of(name)
    train, val = splits()
    new = impl == "new"
    if path == "legacy":
        fitted = (fit(train, val, cfg, device="cpu", log=_quiet) if new else reference_fit(train, val, cfg))
        digest = hashlib.sha256(torch.get_rng_state().numpy().tobytes()).hexdigest()
        logits = infer(fitted, val)["logits"]
    else:
        val_source = B2Source.from_arrays(val, role="val-select")
        if path == "streaming":
            source, window = B2Source.from_arrays(train, role="train"), 1
        else:
            source, window = multi_shard_source(train, "train"), 2
        fitted = (fit_streaming(source, val_source, cfg, window_shards=window, device="cpu", log=_quiet) if new
                  else reference_fit_streaming(source, val_source, cfg, window_shards=window))
        digest = hashlib.sha256(torch.get_rng_state().numpy().tobytes()).hexdigest()
        logits = infer_streaming(fitted, val_source)["logits"]
    _RUNS[cache_key] = (fitted, logits, digest)
    return _RUNS[cache_key]


KEYS = list(GOLDEN)
STREAMING_KEYS = [key for key in KEYS if not key.endswith("/legacy")]


def same_state(a, b):
    return all(torch.equal(a.state_dict()[k], b.state_dict()[k]) for k in a.state_dict()) and \
        a.state_dict().keys() == b.state_dict().keys()


# ---------------------------------------------------------------------------------------------------
# 1. nothing about training changed

@pytest.mark.parametrize("key", KEYS)
def test_golden_origin_main_values_are_reproduced_exactly(key):
    oracle_fitted, oracle_logits, _ = run(key, "oracle")
    if summarize(oracle_fitted, oracle_logits) != {k: v for k, v in GOLDEN[key].items() if k != "shard_orders"}:
        pytest.skip("this machine/torch build does not reproduce the origin/main capture even with the verbatim "
                    "original loop; test_instrumented_trainers_are_bit_identical_to_the_original_loops still applies")
    fitted, logits, _ = run(key, "new")
    assert summarize(fitted, logits) == {k: v for k, v in GOLDEN[key].items() if k != "shard_orders"}
    if "shard_orders" in GOLDEN[key]:
        assert fitted["streaming"]["shard_orders"] == GOLDEN[key]["shard_orders"]


@pytest.mark.parametrize("key", KEYS)
def test_instrumented_trainers_are_bit_identical_to_the_original_loops(key):
    """Live proof, independent of the machine: history, weights, selection, logits and global RNG state."""
    new, new_logits, new_rng = run(key, "new")
    old, old_logits, old_rng = run(key, "oracle")
    assert new["history"] == old["history"]                  # exact float equality of train_loss and val metrics
    assert new["best_epoch"] == old["best_epoch"] and new["best_val_macro_f1"] == old["best_val_macro_f1"]
    assert new["absolute_ref_db"] == old["absolute_ref_db"] and new["n_parameters"] == old["n_parameters"]
    assert same_state(new["model"], old["model"])
    assert np.array_equal(new_logits, old_logits)
    assert new_rng == old_rng                                # no extra draw from the global torch generator
    assert new["config"] == old["config"]
    if "streaming" in new:
        assert new["streaming"]["shard_orders"] == old["streaming"]["shard_orders"]     # the shard-order draws too
    assert set(old) <= set(new) and set(new) - set(old) == {"train_diagnostics"}      # the only additive key


def test_selection_is_nontrivial_in_the_fixtures():
    """Guard against a vacuous golden: some run selects an epoch that is neither the first nor the last."""
    selected = {key: (run(key, "new")[0]["best_epoch"], len(run(key, "new")[0]["history"])) for key in KEYS}
    assert any(0 < best < total - 1 for best, total in selected.values())
    assert any(len({r["val_macro_f1"] for r in run(key, "new")[0]["history"]}) > 2 for key in KEYS)


def test_train_config_has_no_new_field_and_history_keeps_its_keys():
    assert [f.name for f in fields(TrainConfig)] == [
        "labels", "level", "time_pool", "width", "epochs", "batch", "lr", "augment", "weight_decay", "seed",
        "input_mode", "plan_consistency", "plan_loss_weight", "center_loss_weight", "plan_shift_fraction",
        "plan_shift_max_hz"]
    assert "train_diagnostics" not in asdict(cfg_of("A_plan_center"))
    with_plan = run("A_plan_center/legacy", "new")[0]["history"][0]
    without_plan = run("B_plain/legacy", "new")[0]["history"][0]
    assert set(with_plan) == {"epoch", "train_loss", "val_macro_f1", "val_plan_accuracy"}
    assert set(without_plan) == {"epoch", "train_loss", "val_macro_f1"}


# ---------------------------------------------------------------------------------------------------
# 2. gradients and updates against an independent replication of the ORIGINAL loss formula

def manual_epoch(train, cfg):
    """One epoch of the original algorithm (no augmentation), written independently of both trainers.

    Returns the gradient of every parameter at every step, independently recomputed loss components,
    the final model and the number of ``CenterLoss`` evaluations.
    """
    assert cfg.epochs == 1 and not cfg.augment and cfg.plan_shift_fraction == 0
    torch.manual_seed(cfg.seed)
    ref = tr._training_reference(train, cfg)
    xt = tr._inputs(train, cfg, ref)
    yt = torch.from_numpy(tr._labels(train, len(cfg.labels), "training"))
    pt = torch.from_numpy(tr._plan_targets(train, "training")).float() if cfg.plan_consistency else None
    model = tr._model(cfg)
    center = CenterLoss(len(cfg.labels), model.embedding_dim) if cfg.center_loss_weight > 0 else None
    parameters = list(model.parameters()) + ([] if center is None else list(center.parameters()))
    opt = torch.optim.AdamW(parameters, lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=-(-len(xt) // cfg.batch))
    gen = torch.Generator().manual_seed(cfg.seed)
    model.train()
    perm = torch.randperm(len(xt), generator=gen)
    grads, parts = [], []
    for i in range(0, len(perm), cfg.batch):
        idx = perm[i:i + cfg.batch]
        logits, aux, embedding = model.forward_all(xt[idx])
        targets = yt[idx]
        # the ORIGINAL loss formula, as it stood before K18
        loss = nn.functional.cross_entropy(logits, targets)
        if center is not None:
            loss = loss + cfg.center_loss_weight * center(embedding, targets)
        if aux is not None:
            loss = loss + cfg.plan_loss_weight * nn.functional.binary_cross_entropy_with_logits(aux[:, 0], pt[idx])
        opt.zero_grad()
        loss.backward()
        grads.append([None if p.grad is None else p.grad.detach().clone() for p in parameters])
        with torch.no_grad():       # independent component values from the same forward tensors
            part = {"n": len(idx), "loss": loss.item(), "ce": nn.functional.cross_entropy(logits, targets).item(),
                    "emb_sq": float(embedding.float().pow(2).sum()), "emb_n": embedding.numel(),
                    "center": None, "center_w": None, "plan": None, "plan_w": None}
            if center is not None:
                term = center(embedding, targets)
                part.update(center=term.item(), center_w=(cfg.center_loss_weight * term).item())
            if aux is not None:
                term = nn.functional.binary_cross_entropy_with_logits(aux[:, 0], pt[idx])
                part.update(plan=term.item(), plan_w=(cfg.plan_loss_weight * term).item())
        parts.append(part)
        opt.step()
        sched.step()
    return grads, parts, model


def weighted_mean(parts, key):
    total = 0.0                       # explicit sequential accumulation (Python >= 3.12 sum() is compensated)
    for part in parts:
        total += part[key] * part["n"]
    return total / sum(part["n"] for part in parts)


def sequential_sum(values):
    total = 0.0
    for value in values:
        total += value
    return total


@pytest.mark.parametrize("plan,center", [(True, True), (True, False), (False, True), (False, False)])
def test_gradients_update_and_components_match_the_original_formula(plan, center):
    cfg = cfg_of("A_plan_center", plan_consistency=plan, center_loss_weight=0.013 if center else 0.0,
                 plan_loss_weight=0.7, input_mode="dual_residual", epochs=1, batch=5, augment=False, seed=7)
    train, val = splits()
    captured = []

    def record(optimizer, args, kwargs):
        captured.append([None if p.grad is None else p.grad.detach().clone()
                         for group in optimizer.param_groups for p in group["params"]])

    handle = register_optimizer_step_pre_hook(record)
    try:
        fitted = fit(train, val, cfg, device="cpu", log=_quiet)
    finally:
        handle.remove()
    grads, parts, manual_model = manual_epoch(train, cfg)

    assert len(captured) == len(grads) == 10                    # 48 samples, batch 5: nine full batches and one of 3
    for step, (a, b) in enumerate(zip(captured, grads)):
        assert len(a) == len(b)
        assert all((x is None and y is None) or torch.equal(x, y) for x, y in zip(a, b)), f"gradient differs at step {step}"
    assert all(x is not None for x in captured[0])
    assert len(captured[0]) == len(list(manual_model.parameters())) + (1 if center else 0)   # the class centers are trained too
    assert same_state(fitted["model"], manual_model)            # identical parameter update (weights and BN buffers)

    # the diagnostics equal an independent recomputation of the same quantities
    record0 = fitted["train_diagnostics"]["epochs"][0]
    assert record0["n_batches"] == 10 and record0["n_samples"] == N_TRAIN
    assert record0["mean_total_loss"] == weighted_mean(parts, "loss") == fitted["history"][0]["train_loss"]
    assert record0["mean_cross_entropy"] == weighted_mean(parts, "ce")
    if center:
        assert record0["mean_center_loss_unweighted"] == weighted_mean(parts, "center")
        assert record0["mean_center_loss_weighted"] == weighted_mean(parts, "center_w")
        assert record0["n_center_samples"] == N_TRAIN
    else:
        assert record0["mean_center_loss_unweighted"] is None and record0["mean_center_loss_weighted"] is None
        assert record0["n_center_samples"] == 0
    if plan:
        assert record0["mean_plan_bce_unweighted"] == weighted_mean(parts, "plan")
        assert record0["mean_plan_bce_weighted"] == weighted_mean(parts, "plan_w")
        assert record0["n_plan_samples"] == N_TRAIN
    else:
        assert record0["mean_plan_bce_unweighted"] is None and record0["mean_plan_bce_weighted"] is None
        assert record0["n_plan_samples"] == 0
    emb_rms = math.sqrt(sequential_sum(part["emb_sq"] for part in parts) / sum(part["emb_n"] for part in parts))
    assert record0["embedding_rms"] == emb_rms and record0["n_embedding_values"] == N_TRAIN * manual_model.embedding_dim
    assert emb_rms > 0 and math.isfinite(emb_rms)


def test_losses_are_evaluated_once_per_training_batch(monkeypatch):
    """The diagnostics reuse the loss tensors: no second center evaluation and no second training forward pass."""
    calls = {"center": 0, "forward_train": 0}
    center_forward, forward_all = CenterLoss.forward, SmallResNet.forward_all

    def counting_center(self, embedding, labels):
        calls["center"] += 1
        return center_forward(self, embedding, labels)

    def counting_forward(self, x):
        calls["forward_train"] += int(self.training)
        return forward_all(self, x)

    monkeypatch.setattr(CenterLoss, "forward", counting_center)
    monkeypatch.setattr(SmallResNet, "forward_all", counting_forward)
    train, val = splits()
    cfg = cfg_of("A_plan_center", epochs=2, batch=5, augment=False)
    fit(train, val, cfg, device="cpu", log=_quiet)
    assert calls == {"center": 2 * 10, "forward_train": 2 * 10}
    calls.update(center=0, forward_train=0)
    fit_streaming(B2Source.from_arrays(train, role="train"), B2Source.from_arrays(val, role="val-select"), cfg,
                  window_shards=1, device="cpu", log=_quiet)
    assert calls == {"center": 2 * 10, "forward_train": 2 * 10}


# ---------------------------------------------------------------------------------------------------
# 3. the diagnostics themselves

@pytest.mark.parametrize("key", KEYS)
def test_provenance_block_counts_and_strict_json(key):
    fitted = run(key, "new")[0]
    block, cfg = fitted["train_diagnostics"], cfg_of(key.split("/")[0])
    assert block["schema"] == DIAGNOSTICS_SCHEMA == "B2-train-diagnostics/1"
    assert block["observation_only"] is True and block["affects_training"] is False and block["split"] == "train"
    assert block["trainer"] == ("geoml.train.fit" if key.endswith("/legacy") else "geoml.b2_stream.fit_streaming")
    assert "center_loss_weight * center(embedding, y)" in block["loss_convention"] and "0.005" in block["loss_convention"]
    assert block["weights"] == {
        "cross_entropy": 1.0, "center_loss_weight": cfg.center_loss_weight,
        "center_loss_enabled": cfg.center_loss_weight > 0, "plan_loss_weight": 1.0 if cfg.plan_consistency else None,
        "plan_head_enabled": cfg.plan_consistency}
    assert len(block["epochs"]) == cfg.epochs
    for epoch, record in enumerate(block["epochs"]):
        assert record["epoch"] == epoch
        assert record["n_samples"] == N_TRAIN            # the 48 training samples, never the 16 validation ones
        assert record["n_batches"] == -(-N_TRAIN // cfg.batch)
        assert record["n_embedding_values"] == N_TRAIN * fitted["model"].embedding_dim
        assert record["n_nonfinite_batches"] == 0 and record["embedding_rms"] > 0
    assert json.loads(json.dumps(block, allow_nan=False)) == block


@pytest.mark.parametrize("key", KEYS)
def test_loss_accounting_weights_and_ratio_arithmetic(key):
    fitted = run(key, "new")[0]
    cfg = cfg_of(key.split("/")[0])
    for record, history in zip(fitted["train_diagnostics"]["epochs"], fitted["history"]):
        assert record["mean_total_loss"] == history["train_loss"]            # same accumulation as the history
        center = record["mean_center_loss_weighted"] or 0.0
        plan = record["mean_plan_bce_weighted"] or 0.0
        assert record["mean_cross_entropy"] + center + plan == pytest.approx(record["mean_total_loss"], rel=1e-6)
        if cfg.center_loss_weight > 0:
            assert record["mean_center_loss_weighted"] == pytest.approx(
                cfg.center_loss_weight * record["mean_center_loss_unweighted"], rel=1e-6)
            assert record["center_to_ce_ratio"] == record["mean_center_loss_weighted"] / record["mean_cross_entropy"]
            assert record["center_to_ce_ratio_n_samples"] == N_TRAIN and record["center_to_ce_ratio_unavailable"] is None
            assert record["n_center_samples"] == N_TRAIN
        else:
            assert record["center_to_ce_ratio"] is None and record["center_to_ce_ratio_n_samples"] == 0
        if cfg.plan_consistency:
            assert record["mean_plan_bce_weighted"] == pytest.approx(
                cfg.plan_loss_weight * record["mean_plan_bce_unweighted"], rel=1e-6)
            assert record["n_plan_samples"] == N_TRAIN


def test_weighted_terms_are_exactly_weight_times_unweighted_for_power_of_two_weights():
    train, val = splits()
    cfg = cfg_of("A_plan_center", center_loss_weight=0.5, plan_loss_weight=0.25, epochs=2, batch=5, augment=False)
    block = fit(train, val, cfg, device="cpu", log=_quiet)["train_diagnostics"]
    assert block["weights"]["center_loss_weight"] == 0.5 and block["weights"]["plan_loss_weight"] == 0.25
    for record in block["epochs"]:
        assert record["mean_center_loss_weighted"] == 0.5 * record["mean_center_loss_unweighted"]
        assert record["mean_plan_bce_weighted"] == 0.25 * record["mean_plan_bce_unweighted"]
        assert record["center_to_ce_ratio"] == record["mean_center_loss_weighted"] / record["mean_cross_entropy"]


@pytest.mark.parametrize("path", ["legacy", "streaming"])
def test_plan_off_and_center_off_report_nulls_with_counts(path):
    fitted = run(f"B_plain/{path}", "new")[0]
    block = fitted["train_diagnostics"]
    assert block["weights"]["center_loss_enabled"] is False and block["weights"]["plan_head_enabled"] is False
    assert block["weights"]["plan_loss_weight"] is None and block["weights"]["center_loss_weight"] == 0.0
    for record in block["epochs"]:
        for name in ("mean_center_loss_unweighted", "mean_center_loss_weighted", "mean_plan_bce_unweighted",
                     "mean_plan_bce_weighted", "center_to_ce_ratio"):
            assert name in record and record[name] is None
        assert record["n_center_samples"] == 0 and record["n_plan_samples"] == 0
        assert record["center_to_ce_ratio_n_samples"] == 0
        assert record["center_to_ce_ratio_unavailable"] == "center_loss_disabled"
        assert record["mean_cross_entropy"] == record["mean_total_loss"] > 0      # CE is the whole loss here


@pytest.mark.parametrize("name", ["A_plan_center", "B_plain", "C_plan_center_shift"])
def test_single_window_streaming_diagnostics_equal_the_in_memory_trainer(name):
    legacy = run(f"{name}/legacy", "new")[0]["train_diagnostics"]
    streamed = run(f"{name}/streaming", "new")[0]["train_diagnostics"]
    assert legacy["epochs"] == streamed["epochs"]
    assert {**legacy, "trainer": None} == {**streamed, "trainer": None}
    assert legacy["trainer"] != streamed["trainer"]


def test_multi_window_streaming_covers_every_training_sample_once_per_epoch():
    fitted = run("D_multi_window/streaming_multi", "new")[0]
    assert fitted["streaming"]["window_shards"] == 2 and len(fitted["streaming"]["train_shard_counts"]) == 3
    for record in fitted["train_diagnostics"]["epochs"]:
        assert record["n_samples"] == N_TRAIN and record["n_batches"] == 12      # 48 / batch 4, carried across windows


@pytest.mark.parametrize("path", ["legacy", "streaming"])
def test_validation_data_never_enters_the_diagnostics(path):
    base = run(f"A_plan_center/{path}", "new")[0]
    train, _ = splits()
    altered = make_split("val-select", 2, 99)                  # other observations and shifted labels
    altered["label"] = ((altered["label"].astype(np.int64) + 3) % len(LABELS)).astype(np.int8)
    cfg = cfg_of("A_plan_center")
    if path == "legacy":
        other = fit(train, altered, cfg, device="cpu", log=_quiet)
    else:
        other = fit_streaming(B2Source.from_arrays(train, role="train"), B2Source.from_arrays(altered, role="val-select"),
                              cfg, window_shards=1, device="cpu", log=_quiet)
    assert [r["val_macro_f1"] for r in other["history"]] != [r["val_macro_f1"] for r in base["history"]]   # effective change
    assert other["train_diagnostics"] == base["train_diagnostics"]
    assert [r["train_loss"] for r in other["history"]] == [r["train_loss"] for r in base["history"]]


def _unit_config(**changes):
    return cfg_of("A_plan_center", **changes)


def test_accumulator_arithmetic_is_batch_size_weighted_and_resets_per_epoch():
    d = TrainDiagnostics(_unit_config(center_loss_weight=0.5, plan_loss_weight=2.0), "unit")
    # (loss, ce, embedding, center, center_w, plan, plan_w) for a batch of 3 and a batch of 1
    d.update(3, torch.tensor(5.0), torch.tensor(1.0), torch.full((3, 4), 2.0),
             torch.tensor(4.0), torch.tensor(2.0), torch.tensor(0.5), torch.tensor(1.0))
    d.update(1, torch.tensor(3.0), torch.tensor(2.0), torch.full((1, 4), 1.0),
             torch.tensor(2.0), torch.tensor(1.0), torch.tensor(0.25), torch.tensor(0.5))
    record = d.end_epoch(0)
    assert record["n_batches"] == 2 and record["n_samples"] == 4
    assert record["mean_total_loss"] == (5.0 * 3 + 3.0 * 1) / 4
    assert record["mean_cross_entropy"] == 1.25
    assert record["mean_center_loss_unweighted"] == 3.5 and record["mean_center_loss_weighted"] == 1.75
    assert record["mean_plan_bce_unweighted"] == 0.4375 and record["mean_plan_bce_weighted"] == 0.875
    assert record["center_to_ce_ratio"] == 1.4 and record["center_to_ce_ratio_n_samples"] == 4
    assert record["embedding_rms"] == math.sqrt((3 * 4 * 4.0 + 1 * 4 * 1.0) / 16) and record["n_embedding_values"] == 16
    again = d.end_epoch(1)                                      # nothing accumulated since the reset
    assert again["n_batches"] == again["n_samples"] == 0 and again["mean_cross_entropy"] is None
    assert again["embedding_rms"] is None and again["center_to_ce_ratio_unavailable"] == "center_loss_disabled"
    assert d.block()["epochs"][0] == record and len(d.block()["epochs"]) == 2


def test_ratio_is_null_when_cross_entropy_is_zero_or_values_are_not_finite():
    zero = TrainDiagnostics(_unit_config(), "unit")
    zero.update(2, torch.tensor(0.5), torch.tensor(0.0), torch.ones(2, 3), torch.tensor(100.0), torch.tensor(0.5))
    record = zero.end_epoch(0)
    assert record["mean_center_loss_weighted"] == 0.5 and record["mean_cross_entropy"] == 0.0
    assert record["center_to_ce_ratio"] is None and record["center_to_ce_ratio_n_samples"] == 0
    assert record["center_to_ce_ratio_unavailable"] == "mean_cross_entropy_is_zero"
    bad = TrainDiagnostics(_unit_config(), "unit")
    bad.update(2, torch.tensor(float("nan")), torch.tensor(float("nan")), torch.ones(2, 3),
               torch.tensor(1.0), torch.tensor(0.5))
    record = bad.end_epoch(0)
    assert record["mean_cross_entropy"] is None and record["mean_total_loss"] is None
    assert record["center_to_ce_ratio"] is None and record["center_to_ce_ratio_unavailable"] == "nonfinite_mean"
    assert record["n_nonfinite_batches"] == 1 and record["n_samples"] == 2
    json.dumps(bad.block(), allow_nan=False)                   # strict JSON: no NaN anywhere


def test_update_only_reads_detached_values_and_leaves_the_autograd_graph_intact():
    def graph():
        w = torch.tensor([1.0, 2.0, 3.0], requires_grad=True)
        embedding = w * 2
        ce = (embedding ** 2).sum()
        center_term = embedding.sum()
        center_weighted = 0.5 * center_term
        return w, embedding, ce, center_term, center_weighted, ce + center_weighted

    w, embedding, ce, center_term, center_weighted, loss = graph()
    tensors = (w, embedding, ce, center_term, center_weighted, loss)
    versions = [t._version for t in tensors]
    TrainDiagnostics(_unit_config(), "unit").update(3, loss, ce, embedding, center_term, center_weighted)
    assert [t._version for t in tensors] == versions and w.grad is None      # nothing modified in place
    loss.backward()                                                          # graph was not consumed or altered
    control = graph()
    control[-1].backward()
    assert torch.equal(w.grad, control[0].grad) and torch.equal(w.grad, 8 * w.detach() + 1)


# ---------------------------------------------------------------------------------------------------
# 4. checkpoints

@pytest.mark.parametrize("key", ["A_plan_center/legacy", "A_plan_center/streaming", "B_plain/legacy"])
def test_checkpoint_round_trip_carries_the_diagnostics(key, tmp_path):
    fitted = {**run(key, "new")[0], "provenance": {"protocol": "test", "train": "a"}}
    path = tmp_path / "model.pt"
    save(fitted, path)
    loaded = load(path, device="cpu", expected_config=cfg_of(key.split("/")[0]), expected_provenance=fitted["provenance"])
    assert loaded["train_diagnostics"] == fitted["train_diagnostics"] and loaded["history"] == fitted["history"]
    json.dumps(loaded["train_diagnostics"], allow_nan=False)
    _, val = splits()
    assert np.array_equal(infer(loaded, val)["logits"], infer(fitted, val)["logits"])


def test_historical_checkpoints_without_the_new_key_still_load_and_infer_identically(tmp_path):
    fitted = {**run("A_plan_center/legacy", "new")[0], "provenance": {"protocol": "test", "train": "a"}}
    current = tmp_path / "current.pt"
    save(fitted, current)
    raw = torch.load(current, weights_only=True)
    assert "train_diagnostics" in raw
    del raw["train_diagnostics"]                       # a checkpoint written before this change: same fingerprint rules
    historical = tmp_path / "historical.pt"
    torch.save(raw, historical)
    cfg = cfg_of("A_plan_center")
    loaded = load(historical, device="cpu", expected_config=cfg, expected_provenance=fitted["provenance"])
    assert "train_diagnostics" not in loaded and loaded["history"] == fitted["history"]
    _, val = splits()
    assert np.array_equal(infer(loaded, val)["logits"], infer(fitted, val)["logits"])
    for key in ("artifact_version", "metadata_fingerprint", "provenance"):      # and a pre-provenance legacy file
        raw.pop(key)
    legacy = tmp_path / "legacy.pt"
    torch.save(raw, legacy)
    older = load(legacy, device="cpu", expected_config=cfg)
    assert "train_diagnostics" not in older and np.array_equal(infer(older, val)["logits"], infer(fitted, val)["logits"])
