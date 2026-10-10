"""Stage A end to end: train the three models, run the CFAR baseline, write the result tables.

    python -m geoml.pipeline --data data/stageA --out runs/stageA --epochs 30 --seeds 0 1 2

Writes <out>/results.json and <out>/results.md. Definitions: docs/plan/P7_degerlendirme.md.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from geosim.classes import LABELS
from geosim.dataset import load_split
from geosim.plan import monitor_freqs

from . import cfar
from .data import select
from .metrics import cluster_ci, confusion, macro_f1, threshold_at_pfa
from .train import TrainConfig, fit, load, run, save

FOUR = tuple(lab for lab in LABELS if lab != "overdrive")
SHIFTS = ("test_ibo", "test_bw72", "test_amp_lin", "test_amp_saleh")
PFA = 0.05


def _bw(d):
    return np.array([m["config"]["bandwidth"] for m in d["meta"]])


def _mean_ci(correct, seeds):
    """Mean over training seeds and samples, with a 95 % interval over scenario seeds."""
    per_sample = np.mean(correct, axis=0)
    return {"mean": float(per_sample.mean()), "ci": cluster_ci(per_sample, seeds)}


def _classification(probs, d, n):
    """probs: list over training seeds of (N, n) arrays."""
    y = d["label"]
    preds = [p.argmax(1) for p in probs]
    f1 = [macro_f1(y, p, n) for p in preds]
    return {"n": int(len(y)), "accuracy": _mean_ci([p == y for p in preds], d["seed"]),
            "macro_f1": {"mean": float(np.mean(f1)), "std": float(np.std(f1))},
            "recall": [float(np.mean([np.mean(p[y == k] == k) for p in preds])) if np.any(y == k) else None
                       for k in range(n)],
            "confusion": np.sum([confusion(y, p, n) for p in preds], axis=0).tolist()}


def _detection(score_runs, val_runs, d, val, labels):
    """Threshold from validation clean scores at PFA; achieved Pfa and per-class Pd on d."""
    clean, vclean = d["label"] == 0, val["label"] == 0
    hits = [s > threshold_at_pfa(v[vclean], PFA) for s, v in zip(score_runs, val_runs)]
    out = {"pfa": _mean_ci([h[clean] for h in hits], d["seed"][clean]), "pd": {}}
    for k, lab in enumerate(labels):
        if k and np.any(d["label"] == k):
            sel = d["label"] == k
            out["pd"][lab] = _mean_ci([h[sel] for h in hits], d["seed"][sel])
    return out, hits


def main(data: str, out: str, epochs: int, seeds: list, level: str, time_pool: int = 2, reuse: bool = False,
         log=print) -> dict:
    data, out = Path(data), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    S = {p.name: load_split(p) for p in sorted(data.iterdir()) if (p / "manifest.json").exists()}
    need = {"train_nl", "train_lin", "val_nl", "val_lin", "test_id_nl", "test_id_lin"}
    assert need <= set(S), f"missing splits: {need - set(S)}"
    res = {"level": level, "epochs": epochs, "train_seeds": seeds, "pfa_target": PFA, "time_pool": time_pool,
           "protocol": json.loads((data / "train_nl" / "manifest.json").read_text())["protocol"],
           "sizes": {k: int(len(v["label"])) for k, v in S.items()}}
    models = {"M-lin": ("train_lin", "val_lin", FOUR), "M-nl4": ("train_nl", "val_nl", FOUR),
              "M-nl5": ("train_nl", "val_nl", LABELS)}
    fitted = {}
    for name, (tr, va, labels) in models.items():
        fitted[name] = []
        for seed in seeds:
            path = out / f"{name}_seed{seed}.pt"
            if reuse and path.exists():
                log(f"{name}, training seed {seed}: reusing {path.name}")
                fitted[name].append(load(path))
                continue
            log(f"{name}, training seed {seed}")
            t = time.time()
            f = fit(select(S[tr], labels, LABELS), select(S[va], labels, LABELS),
                    TrainConfig(labels=labels, level=level, epochs=epochs, seed=seed, time_pool=time_pool), log=log)
            f["train_seconds"] = time.time() - t
            save(f, path)
            fitted[name].append(f)
    res["model"] = {"parameters": fitted["M-nl5"][0]["n_parameters"],
                    "train_seconds_per_run": float(np.mean([f["train_seconds"] for v in fitted.values() for f in v])),
                    "best_val_macro_f1": {k: float(np.mean([max(h["val_macro_f1"] for h in f["history"]) for f in v]))
                                          for k, v in fitted.items()}}
    x = torch.zeros(1, 2, 128 // time_pool, 512)
    m = fitted["M-nl5"][0]["model"].to("cpu").eval()
    with torch.no_grad():
        t = time.time()
        for _ in range(20):
            m(x)
        res["model"]["cpu_ms_per_frame"] = (time.time() - t) / 20 * 1e3
    m.to(fitted["M-nl5"][0]["device"])

    # --- payload gap (claims 1-3): four shared classes
    four = {k: select(S[k], FOUR, LABELS) for k in ("test_id_lin", "test_id_nl")}
    gap = {}
    for name in ("M-lin", "M-nl4"):
        for split, d in four.items():
            probs = [run(f, d) for f in fitted[name]]
            c = _classification(probs, d, 4)
            clean = d["label"] == 0
            c["false_alarm_on_clean"] = _mean_ci([p.argmax(1)[clean] != 0 for p in probs], d["seed"][clean])
            gap[f"{name} on {split}"] = c
    over = select(S["test_id_nl"], ("overdrive",), LABELS)
    for name in ("M-lin", "M-nl4"):
        pred = np.concatenate([run(f, over).argmax(1) for f in fitted[name]])
        gap[f"{name} on overdrive"] = {lab: float(np.mean(pred == k)) for k, lab in enumerate(FOUR)}
    res["payload_gap"] = gap

    # --- five-class model in and out of distribution (claim 4)
    res["five_class"] = {k: _classification([run(f, S[k]) for f in fitted["M-nl5"]], S[k], 5)
                         for k in ("test_id_nl",) + SHIFTS if k in S}

    # --- detection against the energy detector (claim 5)
    freqs = monitor_freqs()
    val, test = S["val_nl"], S["test_id_nl"]
    det = {}
    nn_val = [1 - run(f, val)[:, 0] for f in fitted["M-nl5"]]
    nn_test = [1 - run(f, test)[:, 0] for f in fitted["M-nl5"]]
    det["M-nl5"], nn_hits = _detection(nn_test, nn_val, test, val, LABELS)
    hits = {"M-nl5": nn_hits}
    for key, use_plan in (("CA-CFAR", False), ("CA-CFAR + plan", True)):
        fv = cfar.features(val["spec"], val["mask"], freqs, _bw(val), use_plan)
        ft = cfar.features(test["spec"], test["mask"], freqs, _bw(test), use_plan)
        det[key], h = _detection([cfar.scores(ft, fv[val["label"] == 0])], [cfar.scores(fv, fv[val["label"] == 0])],
                                 test, val, LABELS)
        hits[key] = h
    res["detection"] = det
    ci_db = np.array([m["interferer"].get("c_over_i_db", np.nan) for m in test["meta"]])
    edges = [5, 15, 25, 35]
    res["pd_vs_ci"] = {"edges_db": edges, "classes": {}}
    for lab in ("cw", "swept_cw"):
        sel = test["label"] == LABELS.index(lab)
        res["pd_vs_ci"]["classes"][lab] = {
            k: [float(np.mean(np.mean(h, axis=0)[sel & (ci_db >= a) & (ci_db < b)])) for a, b in zip(edges[:-1], edges[1:])]
            for k, h in hits.items()}
    (out / "results.json").write_text(json.dumps(res, indent=1))
    (out / "results.md").write_text(report(res))
    log(f"wrote {out / 'results.md'}")
    return res


def _pct(v):
    return f"%{100 * v['mean']:.1f} (%{100 * v['ci'][0]:.1f}–%{100 * v['ci'][1]:.1f})"


def report(r: dict) -> str:
    L = [f"# Kademe A sonuçları", "",
         f"Protokol {r['protocol']} · seviye kipi `{r['level']}` · zaman havuzlama {r['time_pool']} · {r['epochs']} epok · "
         f"eğitim tohumları {r['train_seeds']}",
         "", "Parantez içi: senaryo tohumları üzerinden %95 güven aralığı.", "",
         "## Örnek sayıları", "", "| Bölünme | Örnek |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in r["sizes"].items()]
    L += ["", "## 1. Yük farkı (dört ortak sınıf)", "",
          "| Model, test kümesi | Doğruluk | Makro-F1 | Temizde yanlış alarm |", "|---|---|---|---|"]
    for k, v in r["payload_gap"].items():
        if "accuracy" in v:
            L.append(f"| {k} | {_pct(v['accuracy'])} | {v['macro_f1']['mean']:.3f} ± {v['macro_f1']['std']:.3f} | "
                     f"{_pct(v['false_alarm_on_clean'])} |")
    L += ["", "Aşırı sürme örneklerine dört sınıflı modellerin verdiği yanıt:", "",
          "| Model | clean | cw | swept_cw | unauthorized |", "|---|---|---|---|---|"]
    for name in ("M-lin", "M-nl4"):
        v = r["payload_gap"][f"{name} on overdrive"]
        L.append(f"| {name} | " + " | ".join(f"%{100 * v[lab]:.0f}" for lab in FOUR) + " |")
    L += ["", "## 2. Beş sınıflı model, dağılım içi ve kaymalar", "",
          "| Test kümesi | Doğruluk | Makro-F1 | " + " | ".join(LABELS) + " |", "|---|---|---|" + "---|" * 5]
    for k, v in r["five_class"].items():
        rec = " | ".join("—" if x is None else f"%{100 * x:.0f}" for x in v["recall"])
        L.append(f"| `{k}` | {_pct(v['accuracy'])} | {v['macro_f1']['mean']:.3f} ± {v['macro_f1']['std']:.3f} | {rec} |")
    L += ["", "Sınıf sütunları: o sınıfın geri çağırma oranı.", "",
          f"## 3. Algılama, hedef yanlış alarm %{100 * r['pfa_target']:.0f} (eşik doğrulama kümesinden)", "",
          "| Dedektör | Gerçekleşen yanlış alarm | " + " | ".join(LABELS[1:]) + " |", "|---|---|" + "---|" * 4]
    for k, v in r["detection"].items():
        L.append(f"| {k} | {_pct(v['pfa'])} | " + " | ".join(_pct(v["pd"][lab]) for lab in LABELS[1:]) + " |")
    e = r["pd_vs_ci"]["edges_db"]
    L += ["", "Algılama olasılığı, C/I aralığına göre:", "",
          "| Sınıf | Dedektör | " + " | ".join(f"{a}–{b} dB" for a, b in zip(e[:-1], e[1:])) + " |", "|---|---|" + "---|" * (len(e) - 1)]
    for lab, v in r["pd_vs_ci"]["classes"].items():
        L += [f"| {lab} | {k} | " + " | ".join(f"%{100 * x:.0f}" for x in vals) + " |" for k, vals in v.items()]
    m = r["model"]
    L += ["", "## 4. Model maliyeti", "",
          f"- Parametre: {m['parameters']:,}".replace(",", " "),
          f"- CPU'da çerçeve başına çıkarım: {m['cpu_ms_per_frame']:.0f} ms",
          f"- Eğitim süresi (koşu başına): {m['train_seconds_per_run'] / 60:.1f} dk",
          "- En iyi doğrulama makro-F1: " + ", ".join(f"{k} {v:.3f}" for k, v in m["best_val_macro_f1"].items()), ""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--level", choices=["carrier", "absolute"], default="carrier")
    ap.add_argument("--time-pool", type=int, default=2, help="average this many spectrogram rows (1, 2, 4, ...)")
    ap.add_argument("--reuse", action="store_true", help="load existing checkpoints instead of retraining")
    a = ap.parse_args()
    main(a.data, a.out, a.epochs, a.seeds, a.level, a.time_pool, a.reuse)
