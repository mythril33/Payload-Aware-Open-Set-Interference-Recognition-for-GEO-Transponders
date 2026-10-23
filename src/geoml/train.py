"""Training and inference for the stage-A classifiers (P6 §4)."""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .artifacts import fingerprint
from geosim.plan import plan_mask_db
from geosim.waveform import Carrier

from .data import CORE_DB, SCALE_DB, VIEW_CHANNELS, preprocess, preprocess_dual, reference_level
from .metrics import macro_f1
from .model import CenterLoss, SmallResNet, n_parameters


@dataclass
class TrainConfig:
    labels: tuple
    level: str = "carrier"       # "carrier" or "absolute", see data.preprocess
    time_pool: int = 2
    width: int = 16
    epochs: int = 30
    batch: int = 32
    lr: float = 1e-3
    augment: bool = True         # random frequency mirror and circular time shift
    weight_decay: float = 1e-4
    seed: int = 0
    input_mode: str = "single"  # single: [N,T,F]; dual/co: [N,2,T,F]; dual_residual: + residual [N,T,F]
    plan_consistency: bool = False   # independent binary auxiliary head (B2/1, P18 §7a)
    plan_loss_weight: float = 1.0    # BCE weight of the auxiliary head
    center_loss_weight: float = 0.0  # prototype/center loss weight; 0 disables (frozen before training)
    plan_shift_fraction: float = 0.0   # K17b: fraction of training samples whose plan masks are shifted
    plan_shift_max_hz: float = 0.5e6   # K17b: shift ~ U(-max, +max), continuous; validation/test never shifted

    def __post_init__(self):
        if (not isinstance(self.labels, (tuple, list)) or len(self.labels) < 2
                or any(not isinstance(label, str) or not label for label in self.labels)
                or len(set(self.labels)) != len(self.labels)):
            raise ValueError("labels must contain at least two distinct nonempty names")
        if self.level not in ("carrier", "absolute"):
            raise ValueError("level must be 'carrier' or 'absolute'")
        if self.input_mode not in VIEW_CHANNELS:
            raise ValueError(f"input_mode must be one of {tuple(VIEW_CHANNELS)}")
        if not isinstance(self.plan_consistency, bool):
            raise ValueError("plan_consistency must be a boolean")
        for name in ("plan_loss_weight", "center_loss_weight", "plan_shift_fraction", "plan_shift_max_hz"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite nonnegative number")
            object.__setattr__(self, name, float(value))
        if self.plan_shift_fraction > 1:
            raise ValueError("plan_shift_fraction must be in [0, 1]")
        for name in ("time_pool", "width", "epochs", "batch"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not np.isfinite(self.lr) or self.lr <= 0:
            raise ValueError("lr must be finite and positive")
        if not np.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("weight_decay must be finite and nonnegative")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if not isinstance(self.augment, bool):
            raise ValueError("augment must be a boolean")


def _inputs(d: dict, cfg: TrainConfig, absolute_ref_db):
    spec, mask = np.asarray(d["spec"]), np.asarray(d["mask"])
    if cfg.input_mode != "single":
        residual = None
        if cfg.input_mode == "dual_residual":
            if "residual" not in d:
                raise ValueError("input_mode 'dual_residual' requires the stored cancellation residual (B2-feat/1)")
            residual = np.asarray(d["residual"])
        x = preprocess_dual(spec, mask, cfg.level, cfg.time_pool, absolute_ref_db, view=cfg.input_mode,
                            residual_db=residual)
        return torch.from_numpy(x)
    if (spec.dtype.kind not in "iuf" or spec.ndim != 3 or not len(spec)
            or not spec.shape[1] or not spec.shape[2]):
        raise ValueError("spec must be a nonempty (N, time, frequency) array")
    if mask.dtype.kind not in "iuf" or mask.shape != (len(spec), spec.shape[2]):
        raise ValueError("mask must match the sample and frequency dimensions of spec")
    if spec.shape[1] % cfg.time_pool:
        raise ValueError("time_pool must divide the spectrogram time dimension")
    if not np.isfinite(spec).all() or not np.isfinite(mask).all():
        raise ValueError("model inputs must be finite")
    if np.any(~np.any(mask > CORE_DB, axis=1)):
        raise ValueError("each plan mask must contain at least one planned carrier core bin")
    x = preprocess(spec, mask, cfg.level, cfg.time_pool, absolute_ref_db)
    if not np.isfinite(x).all():
        raise ValueError("preprocessed model inputs must be finite")
    return torch.from_numpy(x)


def _training_reference(d: dict, cfg: TrainConfig) -> float:
    """Absolute reference from known training co-pol observations only."""
    spec, mask = np.asarray(d["spec"]), np.asarray(d["mask"])
    if cfg.input_mode != "single":
        if spec.ndim != 4 or spec.shape[1] != 2 or mask.ndim != 3 or mask.shape[1] != 2:
            raise ValueError("dual/co training requires [N,2,time,frequency] spec and [N,2,frequency] masks")
        spec, mask = spec[:, 0], mask[:, 0]
    if (spec.dtype.kind not in "iuf" or spec.ndim != 3 or not len(spec)
            or not spec.shape[1] or not spec.shape[2]
            or mask.dtype.kind not in "iuf" or mask.shape != (len(spec), spec.shape[2])):
        raise ValueError("training observations must have matching nonempty spectra and plan masks")
    if not np.isfinite(spec).all() or not np.isfinite(mask).all():
        raise ValueError("training observations must be finite")
    if np.any(~np.any(mask > CORE_DB, axis=1)):
        raise ValueError("each plan mask must contain at least one planned carrier core bin")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            ref = float(reference_level(spec, mask).mean())
    except FloatingPointError as error:
        raise ValueError("training reference exceeds supported finite range") from error
    if not np.isfinite(ref):
        raise ValueError("training reference must be finite")
    return ref


def _labels(d: dict, n_classes: int, name: str) -> np.ndarray:
    labels = np.asarray(d["label"])
    if labels.shape != (len(d["spec"]),) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError(f"{name} labels must be one integer class index per sample")
    if np.any((labels < 0) | (labels >= n_classes)):
        raise ValueError(f"{name} labels contain an out-of-range class index")
    return labels.astype(np.int64, copy=False)


def _plan_targets(d: dict, name: str) -> np.ndarray:
    if "plan_consistency" not in d:
        raise ValueError(f"{name} data lack the plan_consistency target required by this configuration")
    targets = np.asarray(d["plan_consistency"])
    if (targets.shape != (len(d["spec"]),) or not np.issubdtype(targets.dtype, np.integer)
            or not np.isin(targets, [0, 1]).all()):
        raise ValueError(f"{name} plan_consistency must be one 0/1 integer per sample")
    return targets.astype(np.int64, copy=False)


MASK_CHANNELS = {"single": (1,), "co": (1,), "dual": (2, 3), "dual_residual": (2, 3)}


def _training_plans(d: dict, cfg: TrainConfig) -> list:
    """Operator plans per training sample, needed to rebuild shifted plan masks (K17b)."""
    meta = d.get("meta")
    if not isinstance(meta, list) or len(meta) != len(d["spec"]):
        raise ValueError("plan-shift augmentation requires one metadata record per training sample")
    plans = []
    for record in meta:
        if cfg.input_mode == "single":
            raw = None if record.get("plan") is None else [record["plan"]]
        else:
            raw = record.get("plans")              # both feeds; the co view simply ignores the cross mask
        if (not isinstance(raw, list) or len(raw) != (1 if cfg.input_mode == "single" else 2)
                or any(not isinstance(plan, list) or not plan for plan in raw)):
            raise ValueError("plan-shift augmentation requires the operator plans in training metadata")
        plans.append([[Carrier(**carrier) for carrier in plan] for plan in raw])
    return plans


def shifted_mask_db(plans: list, shift_hz: float) -> np.ndarray:
    """Plan masks in dB ``[n_pol, F]`` for operator plans whose carriers moved by ``shift_hz``.

    This models an operator plan whose frequency reference is wrong by ``shift_hz``;
    the transmitted signal is unchanged (K17b). Zero shift reproduces the stored mask
    up to float16 rounding. Carriers may spill past the transponder edge; the mask is
    simply truncated at the monitor grid, as for any wrong plan.
    """
    rows = []
    for plan in plans:
        moved = [Carrier(c.f0 + float(shift_hz), c.symbol_rate, c.alpha, c.mod, c.power, c.code_rate) for c in plan]
        rows.append(plan_mask_db(moved).astype(np.float32))
    return np.stack(rows)


def shifted_mask_channels(plans: list, shift_hz: float) -> np.ndarray:
    """Normalized mask channels ``[n_pol, F]`` (dB / SCALE_DB) for shifted operator plans."""
    return shifted_mask_db(plans, shift_hz) / SCALE_DB


def _apply_plan_shift(xb: torch.Tensor, idx: torch.Tensor, raw: dict, plans: list, cfg: TrainConfig,
                      absolute_ref_db, gen: torch.Generator) -> torch.Tensor:
    """K17b: rebuild the plan masks of the selected rows and re-run the full preprocessing.

    Re-running ``_inputs`` keeps the train-time transform identical to the A5 test-time
    corruption (``geoml.plan_shortcut``), where the carrier-level reference also follows
    the shifted plan. Selection is Bernoulli per sample per epoch (expected fraction
    ``plan_shift_fraction``), the shift is continuous U(-max, +max).
    """
    selected = torch.rand(len(idx), generator=gen) < cfg.plan_shift_fraction
    shifts = (torch.rand(len(idx), generator=gen) * 2 - 1) * cfg.plan_shift_max_hz
    if not selected.any():
        return xb
    rows = torch.nonzero(selected).flatten()
    global_rows = idx[rows].tolist()
    masks = np.stack([shifted_mask_db(plans[g], float(shifts[r])) for r, g in zip(rows.tolist(), global_rows)])
    subset = {"spec": np.asarray(raw["spec"])[global_rows],
              "mask": masks[:, 0] if cfg.input_mode == "single" else masks}
    if "residual" in raw:
        subset["residual"] = np.asarray(raw["residual"])[global_rows]
    xb = xb.clone()
    xb[rows] = _inputs(subset, cfg, absolute_ref_db)
    return xb


def _model(cfg: TrainConfig) -> SmallResNet:
    return SmallResNet(len(cfg.labels), cfg.width, in_ch=VIEW_CHANNELS[cfg.input_mode],
                       aux_outputs=1 if cfg.plan_consistency else 0)


DIAGNOSTICS_SCHEMA = "B2-train-diagnostics/1"
DIAGNOSTICS_LOSS_CONVENTION = (
    "loss = cross_entropy(logits, y) + center_loss_weight * center(embedding, y) "
    "+ plan_loss_weight * BCE_with_logits(plan_logit, plan_target); center(embedding, y) = batch mean of "
    "sum_d (embedding_d - center_y,d)^2; P20 convention values center_loss_weight 0.005 and plan_loss_weight 1.0 "
    "(the weights actually used are recorded under 'weights'); cross_entropy and BCE are batch means; the center "
    "and plan terms exist only when enabled")


def _finite_or_none(value):
    return float(value) if value is not None and math.isfinite(value) else None


class TrainDiagnostics:
    """K18 loss-component diagnostics: observation only, training mini-batches only.

    ``update`` reads detached values of the tensors the loss is already built from; it makes no
    forward pass, no ``center(...)`` call and no random draw, and nothing it records flows back
    into the loss, the optimizer, the schedule or checkpoint selection (``affects_training`` is
    false). Statistics are batch-size weighted means over the training batches of one epoch
    (train mode, augmentation applied); validation, calibration and test data never enter.
    Unavailable quantities are ``None`` with counts, never NaN.

    Source identity. Adding this class to ``geoml/train.py`` (and its use in
    ``geoml/b2_stream.py``) changes those files' hashes in the ``source_files_sha256`` bound into
    checkpoint provenance (``geoml.b2_a5.check_source_rule``, P28 section 6). Checkpoints trained
    before this change must not be relabelled as source-compatible; they are not modified, and
    they simply carry no ``train_diagnostics`` key.
    """

    def __init__(self, cfg: TrainConfig, trainer: str):
        self.cfg, self.trainer, self.epochs = cfg, trainer, []
        self.start_epoch()

    def start_epoch(self):
        self.n_batches = self.n_samples = self.n_center = self.n_plan = 0
        self.n_embedding_values = self.n_nonfinite = 0
        self.sums = dict.fromkeys(("loss", "ce", "center", "center_w", "plan", "plan_w", "emb_sq"), 0.0)

    def update(self, n, loss, ce, embedding, center_term=None, center_weighted=None, plan_term=None,
               plan_weighted=None):
        """Accumulate one training batch of ``n`` samples; every argument is a tensor of the loss graph."""
        parts = [loss, ce, embedding.detach().float().pow(2).sum()]
        if center_term is not None:
            parts += [center_term, center_weighted]
        if plan_term is not None:
            parts += [plan_term, plan_weighted]
        values = torch.stack([part.detach().float() for part in parts]).tolist()   # one device sync, no graph
        self.n_batches += 1
        self.n_samples += n
        self.n_embedding_values += embedding.numel()
        self.sums["loss"] += values[0] * n
        self.sums["ce"] += values[1] * n
        self.sums["emb_sq"] += values[2]
        position = 3
        if center_term is not None:
            self.n_center += n
            self.sums["center"] += values[position] * n
            self.sums["center_w"] += values[position + 1] * n
            position += 2
        if plan_term is not None:
            self.n_plan += n
            self.sums["plan"] += values[position] * n
            self.sums["plan_w"] += values[position + 1] * n
        self.n_nonfinite += int(not all(math.isfinite(value) for value in values))

    def end_epoch(self, epoch: int) -> dict:
        def mean(key, count):
            return _finite_or_none(self.sums[key] / count) if count else None

        ce = mean("ce", self.n_samples)
        center_weighted = mean("center_w", self.n_center)
        ratio, reason = None, None
        if not self.n_center:
            reason = "center_loss_disabled"
        elif ce is None or center_weighted is None:
            reason = "nonfinite_mean"
        elif ce == 0.0:
            reason = "mean_cross_entropy_is_zero"
        else:
            ratio = _finite_or_none(center_weighted / ce)
            reason = None if ratio is not None else "nonfinite_ratio"
        record = {
            "epoch": epoch, "n_batches": self.n_batches, "n_samples": self.n_samples,
            "mean_total_loss": mean("loss", self.n_samples), "mean_cross_entropy": ce,
            "mean_center_loss_unweighted": mean("center", self.n_center),
            "mean_center_loss_weighted": center_weighted, "n_center_samples": self.n_center,
            "mean_plan_bce_unweighted": mean("plan", self.n_plan),
            "mean_plan_bce_weighted": mean("plan_w", self.n_plan), "n_plan_samples": self.n_plan,
            "center_to_ce_ratio": ratio, "center_to_ce_ratio_n_samples": self.n_samples if ratio is not None else 0,
            "center_to_ce_ratio_unavailable": reason,
            "embedding_rms": (_finite_or_none(math.sqrt(self.sums["emb_sq"] / self.n_embedding_values))
                              if self.n_embedding_values else None),
            "n_embedding_values": self.n_embedding_values, "n_nonfinite_batches": self.n_nonfinite}
        self.epochs.append(record)
        self.start_epoch()
        return record

    def block(self) -> dict:
        cfg = self.cfg
        return {"schema": DIAGNOSTICS_SCHEMA, "observation_only": True, "affects_training": False,
                "split": "train", "trainer": self.trainer, "loss_convention": DIAGNOSTICS_LOSS_CONVENTION,
                "weights": {"cross_entropy": 1.0, "center_loss_weight": cfg.center_loss_weight,
                            "center_loss_enabled": cfg.center_loss_weight > 0,
                            "plan_loss_weight": cfg.plan_loss_weight if cfg.plan_consistency else None,
                            "plan_head_enabled": cfg.plan_consistency},
                "aggregation": "batch-size weighted means over the training mini-batches of each epoch (train "
                               "mode, augmentation applied); validation, calibration and test data never enter",
                "epochs": [dict(record) for record in self.epochs]}


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor, device: str, batch: int = 64) -> np.ndarray:
    """Class probabilities, (N, n_classes)."""
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    if not len(x):
        raise ValueError("prediction requires at least one sample")
    model.eval()
    out = [torch.softmax(model(x[i:i + batch].to(device)), dim=1).cpu() for i in range(0, len(x), batch)]
    return torch.cat(out).numpy()


def fit(train: dict, val: dict, cfg: TrainConfig, device: str | None = None, log=print) -> dict:
    """Train on `train`, keep the weights with the best validation macro-F1.

    Returns {"model", "config", "absolute_ref_db", "history", "best_epoch", "best_val_macro_f1",
    "n_parameters", "device", "train_diagnostics"}. ``train_diagnostics`` is the observation-only
    K18 block of ``TrainDiagnostics`` (training batches only; see its note on source hashes).
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    _labels(train, len(cfg.labels), "training")
    _labels(val, len(cfg.labels), "validation")
    if not len(train["spec"]) or not len(val["spec"]):
        raise ValueError("training and validation data must be nonempty")
    torch.manual_seed(cfg.seed)
    ref = _training_reference(train, cfg)      # training co-pol data only
    xt, xv = _inputs(train, cfg, ref), _inputs(val, cfg, ref)
    yt = torch.from_numpy(_labels(train, len(cfg.labels), "training"))
    pt = pv = None
    if cfg.plan_consistency:
        pt = torch.from_numpy(_plan_targets(train, "training")).float()
        pv = _plan_targets(val, "validation")
    train_plans = _training_plans(train, cfg) if cfg.plan_shift_fraction > 0 else None
    model = _model(cfg).to(device)
    center = CenterLoss(len(cfg.labels), model.embedding_dim).to(device) if cfg.center_loss_weight > 0 else None
    parameters = list(model.parameters()) + ([] if center is None else list(center.parameters()))
    opt = torch.optim.AdamW(parameters, lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = cfg.epochs * -(-len(xt) // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)
    gen = torch.Generator().manual_seed(cfg.seed)
    best, best_state, best_epoch, history = -1.0, None, None, []
    diagnostics = TrainDiagnostics(cfg, "geoml.train.fit")
    for epoch in range(cfg.epochs):
        model.train()
        t, loss_sum = time.time(), 0.0
        perm = torch.randperm(len(xt), generator=gen)
        for i in range(0, len(perm), cfg.batch):
            idx = perm[i:i + cfg.batch]
            xb = xt[idx]
            if train_plans is not None:        # K17b: label-preserving operator-plan shift, training only
                xb = _apply_plan_shift(xb, idx, train, train_plans, cfg, ref, gen)
            if cfg.augment:
                flip = torch.rand(len(idx), generator=gen) < 0.5
                xb = torch.where(flip[:, None, None, None], xb.flip(-1), xb)
                xb = xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)
            logits, aux, embedding = model.forward_all(xb.to(device))
            targets = yt[idx].to(device)
            # Same operations in the same order as the original three-line loss; the intermediate
            # terms are named only so the K18 diagnostics can read them (K18, observation only).
            ce = loss = nn.functional.cross_entropy(logits, targets)
            center_term = center_weighted = plan_term = plan_weighted = None
            if center is not None:
                center_term = center(embedding, targets)
                center_weighted = cfg.center_loss_weight * center_term
                loss = loss + center_weighted
            if aux is not None:
                plan_term = nn.functional.binary_cross_entropy_with_logits(aux[:, 0], pt[idx].to(device))
                plan_weighted = cfg.plan_loss_weight * plan_term
                loss = loss + plan_weighted
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * len(idx)
            diagnostics.update(len(idx), loss, ce, embedding, center_term, center_weighted, plan_term, plan_weighted)
        diagnostics.end_epoch(epoch)       # training batches only: validation has not run yet
        # Checkpoint selection uses known-class macro-F1 only; the auxiliary head is monitored, not selected on.
        outputs = _forward(model, xv, device)
        f1 = macro_f1(val["label"], outputs["logits"].argmax(1), len(cfg.labels))
        record = {"epoch": epoch, "train_loss": loss_sum / len(xt), "val_macro_f1": f1}
        if pv is not None:
            record["val_plan_accuracy"] = float(np.mean((outputs["plan_logits"][:, 0] > 0) == (pv == 1)))
        history.append(record)
        if f1 > best:
            best, best_epoch = f1, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        log(f"  epoch {epoch + 1:2d}/{cfg.epochs}  loss {loss_sum / len(xt):.3f}  val macro-F1 {f1:.3f}  "
            f"({time.time() - t:.0f} s)")
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "best_epoch": best_epoch, "best_val_macro_f1": best,
            "n_parameters": n_parameters(model), "device": device, "train_diagnostics": diagnostics.block()}


@torch.no_grad()
def _forward(model: nn.Module, x: torch.Tensor, device: str, batch: int = 64) -> dict:
    model.eval()
    logits, plans, embeddings = [], [], []
    for start in range(0, len(x), batch):
        out, aux, features = model.forward_all(x[start:start + batch].to(device))
        logits.append(out.cpu())
        embeddings.append(features.cpu())
        if aux is not None:
            plans.append(aux.cpu())
    result = {"logits": torch.cat(logits).numpy(), "embedding": torch.cat(embeddings).numpy()}
    result["plan_logits"] = torch.cat(plans).numpy() if plans else None
    return result


def save(fitted: dict, path) -> None:
    keep = {k: v for k, v in fitted.items() if k not in ("model", "device")}
    keep["artifact_version"] = 1
    keep["metadata_fingerprint"] = _metadata_fingerprint(keep)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({"state": fitted["model"].state_dict(), **keep}, temporary)
    temporary.replace(path)


def _metadata_fingerprint(artifact: dict) -> str:
    return fingerprint({"config": artifact["config"], "provenance": artifact.get("provenance"),
                        "absolute_ref_db": artifact["absolute_ref_db"]})


def load(path, device: str | None = None, expected_config: TrainConfig | dict | None = None,
         expected_provenance: dict | None = None) -> dict:
    """Load a trusted local checkpoint, optionally enforcing experiment compatibility.

    Existing checkpoints remain readable without expectations. Reuse with provenance
    requirements deliberately rejects legacy checkpoints that cannot establish identity.
    """
    ck = torch.load(path, map_location="cpu", weights_only=True)
    if ck.get("artifact_version") is not None:
        if ck["artifact_version"] != 1 or ck.get("metadata_fingerprint") != _metadata_fingerprint(ck):
            raise ValueError("checkpoint artifact metadata is invalid or has changed")
    if expected_config is not None:
        config = asdict(expected_config) if isinstance(expected_config, TrainConfig) else expected_config
        # Check the original metadata fingerprint above before filling defaults.
        # Historical A1 checkpoints omit input_mode, which means single-pol.
        actual_config = asdict(TrainConfig(**ck["config"]))
        expected = asdict(TrainConfig(**config))
        if fingerprint(actual_config) != fingerprint(expected):
            raise ValueError("checkpoint training configuration does not match this experiment")
    if expected_provenance is not None:
        if "provenance" not in ck or fingerprint(ck["provenance"]) != fingerprint(expected_provenance):
            raise ValueError("checkpoint provenance does not match this experiment's data")
    cfg = TrainConfig(**ck["config"])
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = _model(cfg).to(device)
    model.load_state_dict(ck.pop("state"))
    return {"model": model, "device": device, **ck}


def run(fitted: dict, d: dict) -> np.ndarray:
    cfg = TrainConfig(**{**fitted["config"], "labels": tuple(fitted["config"]["labels"])})
    return predict(fitted["model"], _inputs(d, cfg, fitted["absolute_ref_db"]), fitted["device"])


@torch.no_grad()
def infer(fitted: dict, d: dict, batch: int = 64) -> dict:
    """Return known-class logits, embeddings and (if trained) plan-consistency logits.

    ``plan_logits`` is ``[N,1]`` with positive values meaning ``planned_carrier_missing``,
    or ``None`` for models without the auxiliary head.
    """
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    cfg = TrainConfig(**fitted["config"])
    x = _inputs(d, cfg, fitted["absolute_ref_db"])
    return _forward(fitted["model"], x, fitted["device"], batch)
