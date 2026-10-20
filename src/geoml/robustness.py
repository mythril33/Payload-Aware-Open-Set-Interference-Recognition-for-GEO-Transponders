"""R1-eval/1: evaluate trained Stage A checkpoints on test-only robustness splits.

    python -m geosim.dataset --protocol R1-eval/1 --out data/r1 --workers 4
    python -m geoml.robustness --data data/stageA --runs runs/stageA --r1 data/r1 --out runs/r1

Nothing here trains, selects weights or sets thresholds from R1 data. Checkpoints
and their configuration come from the Stage A pipeline run; detection thresholds
come from val_nl clean samples at the pipeline's false-alarm target. Intervals
resample scenario seeds at fixed trained weights and thresholds. Definitions:
docs/plan/P17_r1_robustness_eval.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from geosim import payload
from geosim.classes import LABELS
from geosim.dataset import R1_PROTOCOL, R1_SPLITS, load_split, read_manifest, split_fingerprint

from .data import select
from .metrics import cluster_ci, confusion, expected_calibration_error, macro_f1, threshold_at_pfa
from .openset_metrics import detection_ranking
from .pipeline import FOUR, PFA
from .train import TrainConfig, load, run

NOMINAL_TRAIN, OVERDRIVE_TRAIN = (9.0, 13.0), (1.0, 4.0)
GAP = (5.0, 8.0)                 # nominal back-off never generated in A1 (P3 decision A)
IBO_EDGES = tuple(float(e) for e in range(15))
MODELS = {"M-lin": ("train_lin", "val_lin", FOUR), "M-nl4": ("train_nl", "val_nl", FOUR),
          "M-nl5": ("train_nl", "val_nl", LABELS)}


def ibo_region(label: str, ibo_db: float) -> tuple[str, float]:
    """Where a sample's configured back-off lies relative to A1 training, and how far (dB)."""
    lo, hi = OVERDRIVE_TRAIN if label == "overdrive" else NOMINAL_TRAIN
    distance = float(max(lo - ibo_db, ibo_db - hi, 0.0))
    if distance == 0.0:
        return "train", 0.0
    if label != "overdrive" and GAP[0] <= ibo_db < GAP[1]:
        return "gap", distance
    return ("near" if distance <= 1.0 else "far"), distance


def _summary(values: np.ndarray, groups: np.ndarray) -> dict:
    """Mean with a scenario-bootstrap interval; empty selections are null with zero counts."""
    n = int(len(values))
    return {"mean": float(np.mean(values)) if n else None,
            "ci95": list(cluster_ci(np.asarray(values, float), groups)) if n else None,
            "n_samples": n, "n_scenarios": int(len(np.unique(groups)))}


def _classification(probs: list, d: dict, n: int) -> dict:
    y, preds = d["label"], [p.argmax(1) for p in probs]
    f1 = [macro_f1(y, p, n) for p in preds]
    ece = [expected_calibration_error(p, y)["ece"] for p in probs]
    return {"n": int(len(y)),
            "accuracy": _summary(np.mean([p == y for p in preds], axis=0), d["seed"]),
            "macro_f1": {"mean": float(np.mean(f1)), "std": float(np.std(f1)), "per_training_seed": f1},
            "ece": {"mean": float(np.mean(ece)), "std": float(np.std(ece)), "per_training_seed": ece,
                    "definition": "top-label, 15 equal-width bins"},
            "recall": [float(np.mean([np.mean(p[y == k] == k) for p in preds])) if np.any(y == k) else None
                       for k in range(n)],
            "confusion": np.sum([confusion(y, p, n) for p in preds], axis=0).tolist()}


def _ibo_bins(d: dict, probs: dict, four: dict) -> list:
    """Per 1 dB back-off bin: five-class accuracy, clean false alarms and the payload gap."""
    labels = [m["label"] for m in d["meta"]]
    ibo = np.array([m["config"]["ibo_db"] for m in d["meta"]])
    y, groups = d["label"], d["seed"]
    nl5 = np.mean([p.argmax(1) == y for p in probs["M-nl5"]], axis=0)
    nl5_alarm = np.mean([p.argmax(1) != 0 for p in probs["M-nl5"]], axis=0)
    is4 = np.array([lab != "overdrive" for lab in labels])
    y4 = np.array([FOUR.index(lab) if lab in FOUR else -1 for lab in labels])
    pred4 = {name: [p.argmax(1) for p in four[name]] for name in ("M-lin", "M-nl4")}
    correct4 = {name: np.mean([p == y4 for p in preds], axis=0) for name, preds in pred4.items()}
    external = {name: np.mean([p != 0 for p in preds], axis=0) for name, preds in pred4.items()}
    clean, over = y == LABELS.index("clean"), y == LABELS.index("overdrive")
    rows = []
    for lo, hi in zip(IBO_EDGES[:-1], IBO_EDGES[1:]):
        b = (ibo >= lo) & ((ibo < hi) | ((hi == IBO_EDGES[-1]) & (ibo <= hi)))
        if not b.any():
            continue
        regions = sorted({ibo_region(labels[i], ibo[i])[0] for i in np.flatnonzero(b)})
        sel4, selc, selo = b & is4, b & clean, b & over
        rows.append({
            "ibo_lo_db": lo, "ibo_hi_db": hi, "regions": regions, "n_samples": int(b.sum()),
            "per_label": {lab: int(np.sum(b & (y == k))) for k, lab in enumerate(LABELS) if np.any(b & (y == k))},
            "M-nl5_accuracy": _summary(nl5[b], groups[b]),
            "M-nl5_clean_false_alarm": _summary(nl5_alarm[selc], groups[selc]),
            "M-lin_accuracy_four": _summary(correct4["M-lin"][sel4], groups[sel4]),
            "M-nl4_accuracy_four": _summary(correct4["M-nl4"][sel4], groups[sel4]),
            "payload_gap_accuracy_four": _summary(correct4["M-nl4"][sel4] - correct4["M-lin"][sel4], groups[sel4]),
            "M-lin_clean_false_alarm": _summary(external["M-lin"][selc], groups[selc]),
            "M-nl4_clean_false_alarm": _summary(external["M-nl4"][selc], groups[selc]),
            "M-lin_overdrive_called_external": _summary(external["M-lin"][selo], groups[selo]),
            "M-nl4_overdrive_called_external": _summary(external["M-nl4"][selo], groups[selo]),
        })
    return rows


def evaluate_split(d: dict, fitted: dict, val_scores: list) -> dict:
    """All R1 metrics for one split. val_scores: M-nl5 clean-detection scores on val_nl per training seed."""
    probs = {"M-nl5": [run(f, d) for f in fitted["M-nl5"]]}
    four_data = select(d, FOUR, LABELS)
    four = {name: [run(f, d) for f in fitted[name]] for name in ("M-lin", "M-nl4")}
    out = {"n_samples": int(len(d["label"])), "n_scenarios": int(len(np.unique(d["seed"]))),
           "per_label": {lab: int(np.sum(d["label"] == k)) for k, lab in enumerate(LABELS) if np.any(d["label"] == k)},
           "five_class": _classification(probs["M-nl5"], d, len(LABELS)), "four_class": {}}
    keep4 = np.isin(d["label"], [LABELS.index(lab) for lab in FOUR])
    for name, runs in four.items():
        c = _classification([p[keep4] for p in runs], four_data, len(FOUR))
        clean = four_data["label"] == 0
        c["false_alarm_on_clean"] = _summary(np.mean([p[keep4].argmax(1)[clean] != 0 for p in runs], axis=0),
                                             four_data["seed"][clean])
        out["four_class"][name] = c
    over = d["label"] == LABELS.index("overdrive")
    out["overdrive_as"] = ({name: {lab: float(np.mean([np.mean(p[over].argmax(1) == k) for p in runs]))
                                   for k, lab in enumerate(FOUR)} for name, runs in four.items()}
                           if over.any() else None)
    clean = d["label"] == 0
    scores = [1 - p[:, 0] for p in probs["M-nl5"]]
    hits = [s > threshold_at_pfa(v, PFA) for s, v in zip(scores, val_scores)]
    detection = {"pfa_target": PFA, "threshold_source": "val_nl clean samples, per training seed",
                 "pfa": _summary(np.mean([h[clean] for h in hits], axis=0), d["seed"][clean]), "pd": {}}
    for k, lab in enumerate(LABELS[1:], start=1):
        sel = d["label"] == k
        if sel.any():
            detection["pd"][lab] = _summary(np.mean([h[sel] for h in hits], axis=0), d["seed"][sel])
    if clean.any() and (~clean).any():
        ranking = [detection_ranking(s[clean], s[~clean]) for s in scores]
        detection["ranking"] = {"positive_population": "any non-clean label", "negative_population": "clean",
                                "auroc": float(np.mean([r["auroc"] for r in ranking])),
                                "fpr_at_95_tpr": float(np.mean([r["fpr_at_95_tpr"] for r in ranking])),
                                "per_training_seed": ranking}
    else:
        detection["ranking"] = None
    out["detection"] = detection
    beyond = [m["amplifier_input_beyond_measured"] for m in d["meta"] if "amplifier_input_beyond_measured" in m]
    out["amplifier_input_beyond_measured"] = ({"mean": float(np.mean(beyond)), "max": float(np.max(beyond)),
                                               "n_samples": len(beyond)} if beyond else None)
    regions = [ibo_region(m["label"], m["config"]["ibo_db"])[0] for m in d["meta"]]
    out["ibo_region_counts"] = {r: regions.count(r) for r in ("train", "near", "gap", "far") if r in regions}
    out["ibo_bins"] = _ibo_bins(d, probs, four)
    return out


def _implementation() -> dict:
    here = Path(__file__)
    return {name: hashlib.sha256(here.with_name(name).read_bytes()).hexdigest()
            for name in ("model.py", "train.py", "data.py")}


def load_stage_a(data: Path, runs: Path) -> tuple[dict, dict, dict, dict]:
    """Stage A checkpoints, reloaded only if their configuration, data and source identity match."""
    stage_a = json.loads((runs / "results.json").read_text())
    data_ids = {name: split_fingerprint(data / name) for name in ("train_nl", "train_lin", "val_nl", "val_lin")}
    for name, identity in data_ids.items():
        if stage_a["data_fingerprints"].get(name) != identity:
            raise ValueError(f"{name} differs from the data the Stage A run was trained on")
    implementation = _implementation()
    fitted = {}
    for name, (tr, va, labels) in MODELS.items():
        fitted[name] = []
        for seed in stage_a["train_seeds"]:
            cfg = TrainConfig(labels=labels, level=stage_a["level"], epochs=stage_a["epochs"], seed=seed,
                              time_pool=stage_a["time_pool"])
            provenance = {"protocol": stage_a["protocol"], "train": data_ids[tr], "validation": data_ids[va],
                          "implementation": implementation}
            fitted[name].append(load(runs / f"{name}_seed{seed}.pt", expected_config=asdict(cfg),
                                     expected_provenance=provenance))
    return stage_a, data_ids, implementation, fitted


def main(data: str, runs: str, r1: str, out: str, log=print) -> dict:
    data, runs, r1, out = Path(data), Path(runs), Path(r1), Path(out)
    stage_a, data_ids, implementation, fitted = load_stage_a(data, runs)
    val = load_split(data / "val_nl")
    val_scores = [1 - run(f, val)[:, 0][val["label"] == 0] for f in fitted["M-nl5"]]
    names = [p.name for p in sorted(r1.iterdir()) if (p / "manifest.json").exists()]
    if not names or any(name not in R1_SPLITS for name in names):
        raise ValueError(f"{r1} must contain only {R1_PROTOCOL} splits")
    res = {"protocol": R1_PROTOCOL, "stage_a_protocol": stage_a["protocol"], "train_seeds": stage_a["train_seeds"],
           "level": stage_a["level"], "time_pool": stage_a["time_pool"], "epochs": stage_a["epochs"],
           "stage_a_complete_data": stage_a["complete_data"],
           "stage_a_data_fingerprints": data_ids, "implementation": implementation,
           "assumptions": {"opendpd_ibo_ref_db": payload.OPENDPD_IBO_REF_DB,
                           "opendpd_reference_bandwidth_hz": payload.REFERENCE_BANDWIDTH, "rapp_p": payload.RAPP_P,
                           "nominal_train_ibo_db": NOMINAL_TRAIN, "overdrive_train_ibo_db": OVERDRIVE_TRAIN,
                           "gap_ibo_db": GAP},
           "splits": {}}
    for name in names:
        manifest = read_manifest(r1 / name)
        if manifest["protocol"] != R1_PROTOCOL:
            raise ValueError(f"{name} is not an {R1_PROTOCOL} artifact")
        log(f"evaluating {name}")
        result = evaluate_split(load_split(r1 / name), fitted, val_scores)
        result.update(amplifier=manifest["split"]["amplifier"], complete=manifest["complete"],
                      data_fingerprint=split_fingerprint(r1 / name))
        res["splits"][name] = result
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, allow_nan=False))
    (out / "results.md").write_text(report(res))
    log(f"wrote {out / 'results.md'}")
    return res


def _pct(v: dict | None) -> str:
    if v is None or v["mean"] is None:
        return "—"
    return f"%{100 * v['mean']:.1f} (%{100 * v['ci95'][0]:.1f}–%{100 * v['ci95'][1]:.1f}; n={v['n_samples']})"


def _gap(v: dict) -> str:
    if v["mean"] is None:
        return "—"
    return f"{100 * v['mean']:+.1f} ({100 * v['ci95'][0]:+.1f}…{100 * v['ci95'][1]:+.1f})"


def report(r: dict) -> str:
    L = [f"# {r['protocol']} sonuçları", "",
         f"Kademe A modelleri ({r['stage_a_protocol']}), eğitim tohumları {r['train_seeds']}, seviye `{r['level']}`. "
         f"Kademe A tam veri: `{r['stage_a_complete_data']}`.",
         "R1 verisi yalnız testtir: eğitim, ağırlık seçimi ve eşik ayarına girmez. Eşikler `val_nl` temiz örneklerinden.",
         "Parantez içi: senaryo tohumları üzerinden %95 aralık (eğitilmiş ağırlık ve eşik sabit).", "",
         "## Bölünme özeti", "",
         "| Bölünme | Yükselteç | Örnek | M-nl5 doğruluk | Makro-F1 | ECE | Temizde yanlış alarm (M-nl5, eşikli) | "
         "AUROC (girişim pozitif) | FPR@95TPR | Ölçüm dışı giriş |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in r["splits"].items():
        f5, det = s["five_class"], s["detection"]
        rank = det["ranking"]
        beyond = s["amplifier_input_beyond_measured"]
        L.append(f"| `{name}` | `{s['amplifier']}` | {s['n_samples']} | {_pct(f5['accuracy'])} | "
                 f"{f5['macro_f1']['mean']:.3f} | {f5['ece']['mean']:.3f} | {_pct(det['pfa'])} | "
                 + (f"{rank['auroc']:.3f} | {rank['fpr_at_95_tpr']:.3f} | " if rank else "— | — | ")
                 + ("—" if beyond is None else f"ort. {beyond['mean']:.2e}, en çok {beyond['max']:.2e}") + " |")
    L += ["", "FPR@95TPR: girişimlerin en az %95'ini bulan ilk (eşit skorlar gruplanmış) eşikte temiz örneklerin girişim sayılma oranı; "
          "test sıralamasını özetler, işletim eşiği değildir.", "",
          "## Yük farkı (dört ortak sınıf)", "",
          "| Bölünme | M-lin doğruluk | M-nl4 doğruluk | M-lin temizde yanlış alarm | M-nl4 temizde yanlış alarm |",
          "|---|---|---|---|---|"]
    for name, s in r["splits"].items():
        a, b = s["four_class"]["M-lin"], s["four_class"]["M-nl4"]
        L.append(f"| `{name}` | {_pct(a['accuracy'])} | {_pct(b['accuracy'])} | {_pct(a['false_alarm_on_clean'])} | "
                 f"{_pct(b['false_alarm_on_clean'])} |")
    for name, s in r["splits"].items():
        if not s["ibo_bins"] or "r1_ibo" not in name:
            continue
        L += ["", f"## `{name}`: geri çekilmeye göre", "",
              "Bölge: `train` A1 eğitim aralığı, `near` en çok 1 dB dışı, `gap` A1'de hiç üretilmeyen 5–8 dB nominal bölge "
              "(etiket kuralı tanımsız), `far` daha uzak. Yük farkı = M-nl4 − M-lin doğruluğu (yüzde puan), aynı örneklerde.", "",
              "| IBO (dB) | Bölge | n | M-nl5 doğruluk | M-nl5 temizde alarm | Yük farkı (4 sınıf) | "
              "M-lin aşırı sürmeye dış girişim | M-nl4 aşırı sürmeye dış girişim |", "|---|---|---|---|---|---|---|---|"]
        for row in s["ibo_bins"]:
            L.append(f"| {row['ibo_lo_db']:.0f}–{row['ibo_hi_db']:.0f} | {', '.join(row['regions'])} | {row['n_samples']} | "
                     f"{_pct(row['M-nl5_accuracy'])} | {_pct(row['M-nl5_clean_false_alarm'])} | "
                     f"{_gap(row['payload_gap_accuracy_four'])} | {_pct(row['M-lin_overdrive_called_external'])} | "
                     f"{_pct(row['M-nl4_overdrive_called_external'])} |")
    a = r["assumptions"]
    L += ["", "## Varsayımlar", "",
          f"- OpenDPD ölçülen giriş RMS'i IBO {a['opendpd_ibo_ref_db']} dB'ye yerleştirildi; bellek gecikmeleri "
          f"{a['opendpd_reference_bandwidth_hz'] / 1e6:.0f} MHz transponder için bant genişliğine göre ölçeklendi [VARSAYIM].",
          f"- Rapp p = {a['rapp_p']} [VARSAYIM]. OpenDPD cihazları katı-hal Doherty PA'dır, TWTA değildir.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="Stage A data directory used to train --runs")
    ap.add_argument("--runs", required=True, help="Stage A pipeline output (checkpoints and results.json)")
    ap.add_argument("--r1", required=True, help="R1-eval/1 data directory")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    main(a.data, a.runs, a.r1, a.out)
