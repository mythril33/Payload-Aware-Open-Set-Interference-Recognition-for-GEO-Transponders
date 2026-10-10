"""Training and inference for the stage-A classifiers (P6 §4)."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn

from .data import preprocess, reference_level
from .metrics import macro_f1
from .model import SmallResNet, n_parameters


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


def _inputs(d: dict, cfg: TrainConfig, absolute_ref_db):
    return torch.from_numpy(preprocess(d["spec"], d["mask"], cfg.level, cfg.time_pool, absolute_ref_db))


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor, device: str, batch: int = 64) -> np.ndarray:
    """Class probabilities, (N, n_classes)."""
    model.eval()
    out = [torch.softmax(model(x[i:i + batch].to(device)), dim=1).cpu() for i in range(0, len(x), batch)]
    return torch.cat(out).numpy()


def fit(train: dict, val: dict, cfg: TrainConfig, device: str | None = None, log=print) -> dict:
    """Train on `train`, keep the weights with the best validation macro-F1.

    Returns {"model", "config", "absolute_ref_db", "history", "n_parameters"}.
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(cfg.seed)
    ref = float(reference_level(train["spec"], train["mask"]).mean())      # training data only
    xt, xv = _inputs(train, cfg, ref), _inputs(val, cfg, ref)
    yt = torch.from_numpy(train["label"])
    model = SmallResNet(len(cfg.labels), cfg.width).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = cfg.epochs * -(-len(xt) // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)
    gen = torch.Generator().manual_seed(cfg.seed)
    best, best_state, history = -1.0, None, []
    for epoch in range(cfg.epochs):
        model.train()
        t, loss_sum = time.time(), 0.0
        perm = torch.randperm(len(xt), generator=gen)
        for i in range(0, len(perm), cfg.batch):
            idx = perm[i:i + cfg.batch]
            xb = xt[idx]
            if cfg.augment:
                flip = torch.rand(len(idx), generator=gen) < 0.5
                xb = torch.where(flip[:, None, None, None], xb.flip(-1), xb)
                xb = xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)
            loss = nn.functional.cross_entropy(model(xb.to(device)), yt[idx].to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * len(idx)
        f1 = macro_f1(val["label"], predict(model, xv, device).argmax(1), len(cfg.labels))
        history.append({"epoch": epoch, "train_loss": loss_sum / len(xt), "val_macro_f1": f1})
        if f1 > best:
            best, best_state = f1, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        log(f"  epoch {epoch + 1:2d}/{cfg.epochs}  loss {loss_sum / len(xt):.3f}  val macro-F1 {f1:.3f}  "
            f"({time.time() - t:.0f} s)")
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "n_parameters": n_parameters(model), "device": device}


def save(fitted: dict, path) -> None:
    keep = {k: v for k, v in fitted.items() if k not in ("model", "device")}
    torch.save({"state": fitted["model"].state_dict(), **keep}, path)


def load(path, device: str | None = None) -> dict:
    ck = torch.load(path, map_location="cpu", weights_only=False)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = SmallResNet(len(ck["config"]["labels"]), ck["config"]["width"]).to(device)
    model.load_state_dict(ck.pop("state"))
    return {"model": model, "device": device, **ck}


def run(fitted: dict, d: dict) -> np.ndarray:
    cfg = TrainConfig(**{**fitted["config"], "labels": tuple(fitted["config"]["labels"])})
    return predict(fitted["model"], _inputs(d, cfg, fitted["absolute_ref_db"]), fitted["device"])
