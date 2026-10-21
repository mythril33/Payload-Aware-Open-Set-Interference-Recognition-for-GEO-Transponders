"""Memory-bounded streaming of canonical B2 artifacts for ``geoml.b2_experiment`` (P23 E1).

Scope: the ``B2-base/1`` / ``B2-feat/1`` known roles, the bound ``B2-test/1`` and
``B2-match/1`` evaluation artifacts, and small in-memory splits (tests, parity
checks). The separate P21b ``B2-features/1`` stage keeps its own loader
(``geoml.b2_data``); the two stages are not interchangeable and nothing here
reads the other's format or replaces the P20 canceller.

Memory model. Every artifact is verified once, shard by shard, when it is opened
(descriptors, checksums, arrays, metadata; ``geosim.b2_dataset.read_b2_manifest``),
and only small per-sample arrays survive that pass: labels, scenario groups,
plan-consistency targets, families/bins and a projection of a few metadata
fields. Training then re-reads verified shards: at most ``window_shards`` raw
float16 shards plus their preprocessed float32 inputs and one mini-batch are
resident; inference holds one shard. ``numpy.load`` reads each NPZ member into
memory, so this is bounded reading, *not* memory mapping. Model outputs
(logits, embeddings, auxiliary logits) are materialized per role:
O(N × (n_classes + 1 + 16·width)) float32.

Scientific contract. ``fit_streaming`` is the same algorithm as ``geoml.train.fit``
(same model, optimizer, OneCycle schedule, losses, K17b plan shift, mirror/roll
augmentation, val-select macro-F1 checkpoint selection, training-only absolute
reference). Only the sample order differs when the data span more than one
window: whole shards are permuted per epoch, samples are permuted inside each
window, and mini-batches carry across windows so every epoch has exactly
``ceil(N / batch)`` optimizer steps. With a single window (``n_shards <=
window_shards``) the trainer reproduces the in-memory trainer bit for bit.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from functools import partial

import numpy as np
import torch
from torch import nn

from geosim.b2_dataset import _fingerprint, iter_b2_shards, read_b2_manifest
from geosim.b2_matched_dataset import iter_b2_matched_shards, read_b2_matched_manifest
from geosim.b2_protocol import LABELS, role_for_group
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES
from geosim.b2_test_dataset import iter_b2_test_shards, read_b2_test_manifest

from .data import CORE_DB, reference_level
from .model import CenterLoss, n_parameters
from .metrics import macro_f1
from .train import (TrainConfig, _apply_plan_shift, _forward, _inputs, _model, _plan_targets, _training_plans)

INDEX_KEYS = {"known": ("label", "seed", "plan_consistency"),
              "test": ("family", "seed", "plan_consistency"),
              "matched": ("label", "seed", "plan_consistency", "matched_bin")}
ARRAY_KEYS = ("spec", "mask", "residual")
DEFAULT_WINDOW_SHARDS = 4


def _project(record):
    """Keep only the small metadata fields the runner reports on; never model inputs."""
    if not isinstance(record, dict):
        return {}
    out = {}
    if "scenario_id" in record:
        out["scenario_id"] = record["scenario_id"]
    event = record.get("event")
    if isinstance(event, dict):
        out["event"] = {key: event[key] for key in ("kind", "c_over_i_psd_db", "effective_c_over_i_psd_db") if key in event}
    if isinstance(record.get("matched"), dict):
        out["matched"] = dict(record["matched"])
    return out


def _small(shard, kind):
    arrays = {}
    for key in INDEX_KEYS[kind]:
        if key not in shard:
            raise ValueError(f"B2 {kind} shard lacks the {key!r} array")
        values = np.asarray(shard[key])
        if values.ndim != 1 or values.dtype.kind not in "iu":
            raise ValueError(f"B2 {kind} {key} must be one integer per observation")
        arrays[key] = values.astype(np.int64)
    n = len(arrays["seed"])
    if any(len(values) != n for values in arrays.values()) or np.shape(shard["spec"])[0] != n:
        raise ValueError("B2 shard arrays disagree on the observation count")
    meta = shard.get("meta")
    if meta is not None and len(meta) != n:
        raise ValueError("B2 shard metadata count differs from its arrays")
    arrays["meta"] = [_project(record) for record in meta] if meta is not None else [{} for _ in range(n)]
    return arrays


def _check_index(kind, role, index):
    seeds = index["seed"]
    if not len(seeds):
        raise ValueError("B2 source has no observations")
    if kind == "test":
        pairs = list(zip(seeds.tolist(), index["family"].tolist()))
        if np.any(index["family"] < 0) or np.any(index["family"] >= len(TEST_FAMILIES)):
            raise ValueError("B2 test-only families contain an out-of-range family index")
    else:
        pairs = list(zip(seeds.tolist(), index["label"].tolist()))
        if np.any(index["label"] < 0) or np.any(index["label"] >= len(LABELS)):
            raise ValueError("B2 labels contain an out-of-range class index")
    if len(set(pairs)) != len(pairs):
        raise ValueError("duplicate scenario-group/label pairs across B2 shards")
    if not np.isin(index["plan_consistency"], [0, 1]).all():
        raise ValueError("B2 plan_consistency targets must be 0 or 1")
    if kind == "matched" and (np.any(index["matched_bin"] < 0) or np.any(index["matched_bin"] > 2)):
        raise ValueError("B2 matched bins must index the three frozen K17c bins")
    if role is not None:
        roles = {role_for_group(int(seed)) for seed in np.unique(seeds)}
        if kind == "matched":
            if roles != {"test-matched"}:
                raise ValueError("matched groups must belong to the frozen test-matched role")
        elif roles != {role}:
            raise ValueError(f"{role} contains scenario groups outside its frozen B2/1 range")


class B2Source:
    """One role (or evaluation artifact) streamed shard by shard with a small resident index.

    ``shards(order)`` yields verified shards (arrays + ``meta`` + ``offset``), each read
    exactly once per iteration; ``fetch(indices)`` returns the arrays of a few samples
    by reading only the shards that hold them.
    """

    def __init__(self, kind, index, shard_counts, reader, *, role=None, root=None, has_residual, extra=None):
        if kind not in INDEX_KEYS:
            raise ValueError(f"kind must be one of {tuple(INDEX_KEYS)}")
        counts = [int(count) for count in shard_counts]
        if not counts or any(count < 1 for count in counts) or sum(counts) != len(index["seed"]):
            raise ValueError("B2 shard counts do not match the sample index")
        _check_index(kind, role, index)
        self.kind, self.role, self.root = kind, role, None if root is None else str(root)
        self.index = {key: np.asarray(index[key], dtype=np.int64) for key in INDEX_KEYS[kind]}
        self.index["meta"] = list(index["meta"])
        self.shard_counts, self._reader = counts, reader
        self.has_residual, self.extra = bool(has_residual), dict(extra or {})
        self.groups = np.unique(self.index["seed"])
        self.n_samples = len(self.index["seed"])
        self.offsets = np.concatenate([[0], np.cumsum(counts)[:-1]]).astype(np.int64)

    def __len__(self):
        return self.n_samples

    @property
    def n_shards(self):
        return len(self.shard_counts)

    def split(self):
        """Small-array view with the keys the legacy metric code expects (no spectra)."""
        out = {key: self.index[key] for key in INDEX_KEYS[self.kind]}
        out["meta"] = self.index["meta"]
        out.update(self.extra)
        return out

    def shards(self, order=None):
        order = list(range(self.n_shards)) if order is None else [int(index) for index in order]
        if len(set(order)) != len(order) or any(not 0 <= index < self.n_shards for index in order):
            raise ValueError("shard order must list distinct shard indices")
        for position, shard in zip(order, self._reader(order)):
            if np.shape(shard["spec"])[0] != self.shard_counts[position]:
                raise ValueError("B2 shard sample count changed since the artifact was indexed")
            start = int(self.offsets[position])
            for key in INDEX_KEYS[self.kind]:
                if not np.array_equal(np.asarray(shard[key]).astype(np.int64), self.index[key][start:start + self.shard_counts[position]]):
                    raise ValueError(f"B2 shard {key} changed since the artifact was indexed")
            yield {**shard, "offset": start, "shard_index": position}

    def fetch(self, indices):
        """Arrays of the requested global sample indices (in the requested order), reading only their shards."""
        wanted = np.asarray(indices, dtype=np.int64)
        if wanted.ndim != 1 or np.any(wanted < 0) or np.any(wanted >= self.n_samples):
            raise ValueError("fetch indices must be valid sample positions")
        needed = sorted({int(np.searchsorted(self.offsets, i, side="right") - 1) for i in wanted.tolist()})
        rows = {}
        for shard in self.shards(needed):
            start, count = shard["offset"], self.shard_counts[shard["shard_index"]]
            for position in wanted.tolist():
                if start <= position < start + count:
                    rows[position] = {key: np.asarray(shard[key])[position - start] for key in ARRAY_KEYS if key in shard}
        return {key: np.stack([rows[int(i)][key] for i in wanted]) for key in rows[int(wanted[0])]} if len(wanted) else {}

    @classmethod
    def from_arrays(cls, split, *, kind="known", role=None):
        """A single in-memory shard (tests, parity checks, small diagnostics)."""
        if not isinstance(split, dict) or "spec" not in split or "mask" not in split:
            raise ValueError("an in-memory B2 split needs spec and mask arrays")
        spec = np.asarray(split["spec"])
        if spec.ndim != 4 or not len(spec):
            raise ValueError("an in-memory B2 split must hold nonempty [N,2,T,F] spectra")
        for key in ARRAY_KEYS:
            if key in split and (np.asarray(split[key]).shape[0] != len(spec) or not np.isfinite(np.asarray(split[key])).all()):
                raise ValueError(f"in-memory B2 {key} must be finite with one row per observation")
        index = _small(split, kind)
        extra = {}
        if kind == "test":
            extra["families"] = list(split.get("families", TEST_FAMILIES))
        if kind == "matched":
            extra["labels"] = list(split.get("labels", MATCHED_LABELS))
        shard = {key: split[key] for key in ARRAY_KEYS + INDEX_KEYS[kind] if key in split}
        shard["meta"] = split.get("meta", [{} for _ in range(len(spec))])
        return cls(kind, index, [len(spec)], lambda order: iter([shard]), role=role,
                   has_residual="residual" in split, extra=extra)


def open_b2_known(root):
    """Verify a B2-base/1 or B2-feat/1 artifact once and return (manifest, identity, {role: B2Source}).

    ``identity`` equals ``geosim.b2_dataset.b2_fingerprint(root)``; the index is built
    in the same bounded verification pass.
    """
    indexes, counts, residual = {}, {}, {}

    def on_shard(role, index, shard):
        indexes.setdefault(role, []).append(_small(shard, "known"))
        counts.setdefault(role, []).append(len(shard["seed"]))
        residual.setdefault(role, set()).add("residual" in shard)

    manifest = read_b2_manifest(root, on_shard)
    sources = {}
    for role in manifest["roles"]:
        if residual[role] != {True} and residual[role] != {False}:
            raise ValueError(f"{role} mixes shards with and without the stored residual")
        sources[role] = B2Source("known", _concat(indexes[role]), counts[role], partial(iter_b2_shards, root, role),
                                 role=role, root=root, has_residual=residual[role] == {True})
    return manifest, _fingerprint(manifest), sources


def open_b2_test(root):
    """Verify a B2-test/1 artifact once; return (manifest, identity, source) for the test-only families."""
    indexes, counts, residual = [], [], set()

    def on_shard(index, shard):
        indexes.append(_small(shard, "test"))
        counts.append(len(shard["seed"]))
        residual.add("residual" in shard)

    manifest = read_b2_test_manifest(root, on_shard)
    if len(residual) != 1:
        raise ValueError("test-only artifact mixes shards with and without the stored residual")
    source = B2Source("test", _concat(indexes), counts, partial(iter_b2_test_shards, root), role="test", root=root,
                      has_residual=residual == {True}, extra={"families": list(TEST_FAMILIES)})
    return manifest, _fingerprint(manifest), source


def open_b2_matched(root):
    """Verify a B2-match/1 artifact once; return (manifest, identity, source) for the test-matched role."""
    indexes, counts, residual = [], [], set()

    def on_shard(index, shard):
        indexes.append(_small(shard, "matched"))
        counts.append(len(shard["seed"]))
        residual.add("residual" in shard)

    manifest = read_b2_matched_manifest(root, on_shard)
    if len(residual) != 1:
        raise ValueError("matched artifact mixes shards with and without the stored residual")
    source = B2Source("matched", _concat(indexes), counts, partial(iter_b2_matched_shards, root), role="test-matched",
                      root=root, has_residual=residual == {True}, extra={"labels": list(MATCHED_LABELS)})
    return manifest, _fingerprint(manifest), source


def _concat(parts):
    if not parts:
        raise ValueError("B2 artifact has no shards")
    out = {key: np.concatenate([part[key] for part in parts]) for key in parts[0] if key != "meta"}
    out["meta"] = [record for part in parts for record in part["meta"]]
    return out


# ---------------------------------------------------------------------------
# streaming training and inference (same algorithm as geoml.train)


def _require(source, cfg, name):
    if not isinstance(source, B2Source):
        raise ValueError(f"{name} data must be a B2Source")
    if source.kind == "test":
        raise ValueError(f"{name} data must carry known labels, not test-only families")
    if cfg.input_mode == "dual_residual" and not source.has_residual:
        raise ValueError("input_mode 'dual_residual' requires the stored cancellation residual (B2-feat/1)")
    if cfg.plan_consistency and "plan_consistency" not in source.index:
        raise ValueError(f"{name} data lack the plan_consistency target required by this configuration")
    labels = source.index["label"]
    if np.any((labels < 0) | (labels >= len(cfg.labels))):
        raise ValueError(f"{name} labels contain an out-of-range class index")


def _shard_arrays(shard):
    return {key: shard[key] for key in ARRAY_KEYS if key in shard}


PREPROCESS_CHUNK = 16


def _inputs_chunked(arrays, cfg, ref, chunk=PREPROCESS_CHUNK):
    """``geoml.train._inputs`` applied in slices of ``chunk`` observations.

    Preprocessing is per sample, so the result is identical to one call on the whole
    shard; the float32 temporaries of ``preprocess_dual`` (several copies of the
    shard) are bounded by the chunk instead of the shard.
    """
    n = np.shape(arrays["spec"])[0]
    if n <= chunk:
        return _inputs(arrays, cfg, ref)
    return torch.cat([_inputs({key: value[start:start + chunk] for key, value in arrays.items()}, cfg, ref)
                      for start in range(0, n, chunk)])


def _training_reference(train, cfg):
    """Training co-pol reference from per-sample levels, identical to ``geoml.train._training_reference``."""
    values = []
    for shard in train.shards():
        spec, mask = np.asarray(shard["spec"]), np.asarray(shard["mask"])
        if cfg.input_mode != "single":
            if spec.ndim != 4 or spec.shape[1] != 2 or mask.ndim != 3 or mask.shape[1] != 2:
                raise ValueError("dual/co training requires [N,2,time,frequency] spec and [N,2,frequency] masks")
            spec, mask = spec[:, 0], mask[:, 0]
        if (spec.dtype.kind not in "iuf" or spec.ndim != 3 or not len(spec) or not spec.shape[1] or not spec.shape[2]
                or mask.dtype.kind not in "iuf" or mask.shape != (len(spec), spec.shape[2])):
            raise ValueError("training observations must have matching nonempty spectra and plan masks")
        if not np.isfinite(spec).all() or not np.isfinite(mask).all():
            raise ValueError("training observations must be finite")
        if np.any(~np.any(mask > CORE_DB, axis=1)):
            raise ValueError("each plan mask must contain at least one planned carrier core bin")
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
                values.append(reference_level(spec, mask))
        except FloatingPointError as error:
            raise ValueError("training reference exceeds supported finite range") from error
    ref = float(np.concatenate(values).mean())
    if not np.isfinite(ref):
        raise ValueError("training reference must be finite")
    return ref


def _window(shards, cfg, ref, with_plans):
    """Preprocess a list of verified shards into one window of model inputs and targets."""
    x = torch.cat([_inputs_chunked(_shard_arrays(shard), cfg, ref) for shard in shards])
    y = torch.from_numpy(np.concatenate([np.asarray(shard["label"]).astype(np.int64) for shard in shards]))
    seed = np.concatenate([np.asarray(shard["seed"]).astype(np.int64) for shard in shards])
    piece = {"x": x, "y": y, "seed": seed, "p": None, "spec": None, "residual": None, "plans": None}
    if cfg.plan_consistency:
        piece["p"] = torch.from_numpy(np.concatenate([_plan_targets(shard, "training") for shard in shards])).float()
    if with_plans:
        piece["spec"] = np.concatenate([np.asarray(shard["spec"]) for shard in shards])
        if cfg.input_mode == "dual_residual":
            piece["residual"] = np.concatenate([np.asarray(shard["residual"]) for shard in shards])
        piece["plans"] = [plan for shard in shards for plan in _training_plans(shard, cfg)]
    return piece


def _take(piece, idx):
    rows = idx.tolist()
    return {"x": piece["x"][idx], "y": piece["y"][idx], "seed": piece["seed"][rows],
            "p": None if piece["p"] is None else piece["p"][idx],
            "spec": None if piece["spec"] is None else piece["spec"][rows],
            "residual": None if piece["residual"] is None else piece["residual"][rows],
            "plans": None if piece["plans"] is None else [piece["plans"][row] for row in rows]}


def _cat(first, second):
    if first is None:
        return second
    return {"x": torch.cat([first["x"], second["x"]]), "y": torch.cat([first["y"], second["y"]]),
            "seed": np.concatenate([first["seed"], second["seed"]]),
            "p": None if first["p"] is None else torch.cat([first["p"], second["p"]]),
            "spec": None if first["spec"] is None else np.concatenate([first["spec"], second["spec"]]),
            "residual": None if first["residual"] is None else np.concatenate([first["residual"], second["residual"]]),
            "plans": None if first["plans"] is None else first["plans"] + second["plans"]}


def _batches(train, cfg, ref, gen, window_shards, with_plans, order):
    """Mini-batches of exactly ``cfg.batch`` rows (the last of the epoch may be shorter).

    Samples are permuted inside each window of ``window_shards`` shards; rows left
    over at the end of a window are carried into the first batch of the next one.
    """
    pending, buffer = None, []
    iterator = train.shards(order)
    exhausted = False
    while not exhausted:
        buffer = []
        while len(buffer) < window_shards:
            try:
                buffer.append(next(iterator))
            except StopIteration:
                exhausted = True
                break
        if not buffer:
            break
        piece = _window(buffer, cfg, ref, with_plans)
        perm = torch.randperm(len(piece["x"]), generator=gen)
        position = 0
        while position < len(perm):
            need = cfg.batch - (0 if pending is None else len(pending["x"]))
            idx = perm[position:position + need]
            position += len(idx)
            batch = _cat(pending, _take(piece, idx))
            pending = None
            if len(batch["x"]) < cfg.batch and not exhausted:
                pending = batch          # carry a short remainder into the next window
                break
            yield batch
        del piece
    if pending is not None:
        yield pending


def fit_streaming(train, val, cfg: TrainConfig, *, window_shards=DEFAULT_WINDOW_SHARDS, device=None, log=print) -> dict:
    """Train on streamed shards; keep the weights with the best val-select macro-F1.

    Returns the same dictionary as ``geoml.train.fit`` plus a ``streaming`` record of
    the sample-order policy; ``geoml.train.save``/``load`` apply unchanged.
    """
    if isinstance(window_shards, bool) or not isinstance(window_shards, int) or window_shards < 1:
        raise ValueError("window_shards must be a positive integer")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    _require(train, cfg, "training")
    _require(val, cfg, "validation")
    if np.intersect1d(train.groups, val.groups).size:
        raise ValueError("training and validation scenario groups must be disjoint")
    torch.manual_seed(cfg.seed)
    ref = _training_reference(train, cfg)
    with_plans = cfg.plan_shift_fraction > 0
    model = _model(cfg).to(device)
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
        t, loss_sum, n_steps = time.time(), 0.0, 0
        # One window reproduces geoml.train.fit exactly; more windows permute whole shards first.
        order = (torch.randperm(train.n_shards, generator=gen).tolist() if train.n_shards > window_shards
                 else list(range(train.n_shards)))
        orders.append(order)
        for batch in _batches(train, cfg, ref, gen, window_shards, with_plans, order):
            xb = batch["x"]
            if with_plans:        # K17b: label-preserving operator-plan shift, training only
                raw = {"spec": batch["spec"]}
                if batch["residual"] is not None:
                    raw["residual"] = batch["residual"]
                xb = _apply_plan_shift(xb, torch.arange(len(xb)), raw, batch["plans"], cfg, ref, gen)
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
        if n_steps != -(-n // cfg.batch):
            raise RuntimeError("streaming epoch produced an unexpected number of optimizer steps")
        outputs = infer_streaming({"model": model, "config": cfg, "absolute_ref_db": ref, "device": device}, val)
        f1 = macro_f1(val.index["label"], outputs["logits"].argmax(1), len(cfg.labels))
        record = {"epoch": epoch, "train_loss": loss_sum / n, "val_macro_f1": f1}
        if pv is not None:
            record["val_plan_accuracy"] = float(np.mean((outputs["plan_logits"][:, 0] > 0) == (pv == 1)))
        history.append(record)
        if f1 > best:
            best, best_epoch = f1, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        log(f"  epoch {epoch + 1:2d}/{cfg.epochs}  loss {loss_sum / n:.3f}  val macro-F1 {f1:.3f}  "
            f"({time.time() - t:.0f} s)")
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "best_epoch": best_epoch, "best_val_macro_f1": best,
            "n_parameters": n_parameters(model), "device": device,
            "streaming": {"window_shards": int(window_shards), "train_shard_counts": list(train.shard_counts),
                          "shard_orders": orders,
                          "policy": "shards permuted per epoch when n_shards > window_shards; samples permuted "
                                    "inside each window; short remainders carried into the next window"}}


@torch.no_grad()
def infer_streaming(fitted: dict, source, batch: int = 32) -> dict:
    """Logits, embeddings and plan logits in canonical sample order; one raw shard plus one preprocessed batch resident.

    The default batch of 32 halves the activation transient of the legacy 64-sample
    inference batches; eval-mode outputs do not depend on the batch composition.
    """
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    if not isinstance(source, B2Source):
        raise ValueError("inference data must be a B2Source")
    cfg = fitted["config"] if isinstance(fitted["config"], TrainConfig) else TrainConfig(**fitted["config"])
    if cfg.input_mode == "dual_residual" and not source.has_residual:
        raise ValueError("input_mode 'dual_residual' requires the stored cancellation residual (B2-feat/1)")
    outputs = {"logits": [], "embedding": [], "plan_logits": []}
    for shard in source.shards():
        arrays = _shard_arrays(shard)
        n = np.shape(arrays["spec"])[0]
        for start in range(0, n, batch):          # preprocess and run one inference batch at a time
            x = _inputs({key: value[start:start + batch] for key, value in arrays.items()}, cfg, fitted["absolute_ref_db"])
            result = _forward(fitted["model"], x, fitted["device"], batch)
            for key in outputs:
                if result[key] is not None:
                    outputs[key].append(result[key])
    if not outputs["logits"]:
        raise ValueError("inference requires at least one shard")
    return {"logits": np.concatenate(outputs["logits"]), "embedding": np.concatenate(outputs["embedding"]),
            "plan_logits": np.concatenate(outputs["plan_logits"]) if outputs["plan_logits"] else None}
