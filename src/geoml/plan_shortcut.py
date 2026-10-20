"""Plan-mask shortcut test (ablation A5): perturb the operator plan at evaluation time.

    python -m geoml.plan_shortcut --data data/stageA --runs runs/stageA --out runs/plan_shortcut

The spectra are unchanged; only the plan-mask input is rebuilt from a modified
operator plan with geosim.plan.plan_mask_db. Trained Stage A checkpoints are
reloaded with their identity checks and nothing is retrained or recalibrated.
Perturbations (P16 IP-4.4, P18 A5):

- ``shift_plus`` / ``shift_minus``: every planned carrier is listed 0.5 MHz off (stale plan).
- ``drop_one``: one planned carrier is missing from the plan (it is still transmitted).
- ``phantom``: the plan lists one extra carrier in a free gap that is not transmitted.
- ``authorize_intruder``: the unauthorized carrier is listed in the plan (unauthorized samples only).

If the classifier reads ``unauthorized`` from energy outside the mask, ``drop_one``
turns clean scenes into unauthorized and ``authorize_intruder`` hides the intruder.
The plan comes from operator metadata (already a model input); simulator truth such
as C/I or back-off is never used to build a perturbed input except to place the
intruder in ``authorize_intruder``, which models an operator plan that wrongly
authorizes it.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from geosim.classes import LABELS
from geosim.dataset import load_split, split_fingerprint
from geosim.interferers import InfeasibleCarrierError, random_unauthorized
from geosim.plan import plan_mask_db
from geosim.waveform import Carrier

from .robustness import _summary, load_stage_a
from .train import run

SHIFT_HZ = 0.5e6              # stale-plan frequency error [assumption]
PERTURBATIONS = ("none", "shift_plus", "shift_minus", "drop_one", "phantom", "authorize_intruder")
STORED_MASK_TOLERANCE_DB = 0.1


def _plan(meta: dict) -> list[Carrier]:
    return [Carrier(**c) for c in meta["plan"]]


def perturbed_plan(meta: dict, kind: str, seed: int) -> list[Carrier] | None:
    """Operator plan after one perturbation; None when it does not apply to this sample."""
    plan = _plan(meta)
    rng = np.random.default_rng([seed, 9100, PERTURBATIONS.index(kind)])
    if kind == "none":
        return plan
    if kind in ("shift_plus", "shift_minus"):
        step = SHIFT_HZ if kind == "shift_plus" else -SHIFT_HZ
        return [replace(c, f0=c.f0 + step) for c in plan]
    if kind == "drop_one":
        if len(plan) < 2:
            return None
        drop = int(rng.integers(len(plan)))
        return [c for i, c in enumerate(plan) if i != drop]
    if kind == "phantom":
        try:
            return plan + [random_unauthorized(rng, plan, meta["config"]["bandwidth"], 0.0)]
        except InfeasibleCarrierError:
            return None
    if kind == "authorize_intruder":
        info = meta.get("interferer", {})
        if meta["label"] != "unauthorized" or "symbol_rate" not in info:
            return None
        return plan + [Carrier(f0=info["f0"], symbol_rate=info["symbol_rate"], alpha=info["alpha"],
                               mod=info["mod"], power=10 ** (-info["c_over_i_db"] / 10))]
    raise ValueError(f"unknown perturbation {kind!r}")


def perturb(d: dict, kind: str) -> tuple[dict, np.ndarray]:
    """Copy of d with rebuilt masks; returns the subset where the perturbation applies."""
    masks, keep = [], []
    for meta, seed in zip(d["meta"], d["seed"]):
        plan = perturbed_plan(meta, kind, int(seed))
        keep.append(plan is not None)
        if plan is not None:
            masks.append(plan_mask_db(plan))
    keep = np.array(keep)
    out = {"spec": d["spec"][keep], "mask": np.stack(masks) if masks else np.zeros((0, d["mask"].shape[1]), np.float32),
           "label": d["label"][keep], "seed": d["seed"][keep], "meta": [m for m, k in zip(d["meta"], keep) if k]}
    return out, keep


def check_stored_masks(d: dict) -> float:
    """Largest difference between the stored masks and masks rebuilt from metadata plans (dB)."""
    rebuilt = np.stack([plan_mask_db(_plan(m)) for m in d["meta"]])
    worst = float(np.max(np.abs(rebuilt - d["mask"].astype(np.float32))))
    if worst > STORED_MASK_TOLERANCE_DB:
        raise ValueError(f"stored plan masks differ from metadata plans by {worst:.3f} dB")
    return worst


def evaluate(d: dict, fitted: list) -> dict:
    base_pred = [run(f, d).argmax(1) for f in fitted]
    y, groups = d["label"], d["seed"]
    clean, unauth = y == LABELS.index("clean"), y == LABELS.index("unauthorized")
    results = {}
    for kind in PERTURBATIONS:
        p, keep = perturb(d, kind)
        if not len(p["label"]):
            results[kind] = {"n_samples": 0}
            continue
        preds = [run(f, p).argmax(1) for f in fitted]
        yk, gk = p["label"], p["seed"]
        ck, uk = clean[keep], unauth[keep]
        results[kind] = {
            "n_samples": int(len(yk)),
            "accuracy": _summary(np.mean([q == yk for q in preds], axis=0), gk),
            "changed_vs_unperturbed": _summary(np.mean([q != b[keep] for q, b in zip(preds, base_pred)], axis=0), gk),
            "recall": {lab: (float(np.mean([np.mean(q[yk == k] == k) for q in preds])) if np.any(yk == k) else None)
                       for k, lab in enumerate(LABELS)},
            "clean_called_unauthorized": _summary(np.mean([q[ck] == LABELS.index("unauthorized") for q in preds], axis=0), gk[ck]),
            "clean_false_alarm": _summary(np.mean([q[ck] != 0 for q in preds], axis=0), gk[ck]),
            "unauthorized_recall": _summary(np.mean([q[uk] == LABELS.index("unauthorized") for q in preds], axis=0), gk[uk]),
            "confusion_per_training_seed": [[[int(np.sum((yk == t) & (q == c))) for c in range(len(LABELS))]
                                             for t in range(len(LABELS))] for q in preds],
        }
    return results


def main(data: str, runs: str, out: str, split: str = "test_id_nl", log=print) -> dict:
    data, runs, out = Path(data), Path(runs), Path(out)
    stage_a, data_ids, implementation, fitted = load_stage_a(data, runs)
    d = load_split(data / split)
    worst = check_stored_masks(d)
    log(f"{split}: {len(d['label'])} samples, stored-mask agreement {worst:.4f} dB")
    res = {"ablation": "A5 plan-mask perturbation", "split": split, "data_fingerprint": split_fingerprint(data / split),
           "stage_a_protocol": stage_a["protocol"], "train_seeds": stage_a["train_seeds"],
           "stage_a_complete_data": stage_a["complete_data"], "stage_a_data_fingerprints": data_ids,
           "implementation": implementation, "shift_hz": SHIFT_HZ, "stored_mask_max_error_db": worst,
           "model": "M-nl5", "perturbations": evaluate(d, fitted["M-nl5"])}
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, allow_nan=False))
    (out / "results.md").write_text(report(res))
    log(f"wrote {out / 'results.md'}")
    return res


def _pct(v):
    if not v or v.get("mean") is None:
        return "—"
    return f"%{100 * v['mean']:.1f} (%{100 * v['ci95'][0]:.1f}–%{100 * v['ci95'][1]:.1f}; n={v['n_samples']})"


def report(r: dict) -> str:
    L = ["# Plan maskesi kısa yolu testi (A5)", "",
         f"Model M-nl5 (Kademe A {r['stage_a_protocol']}, eğitim tohumları {r['train_seeds']}; tam veri: `{r['stage_a_complete_data']}`), "
         f"bölünme `{r['split']}`. Spektrumlar aynı; yalnız plan maskesi bozulmuş plandan yeniden kuruldu. "
         f"Kaydırma {r['shift_hz'] / 1e6:.1f} MHz. Parantez içi: senaryo tohumları üzerinden %95 aralık.", "",
         "| Bozma | n | Doğruluk | Tahmini değişen | Temiz → unauthorized | Temizde yanlış alarm | Unauthorized geri çağırma |",
         "|---|---|---|---|---|---|---|"]
    for kind, v in r["perturbations"].items():
        if not v["n_samples"]:
            L.append(f"| `{kind}` | 0 | — | — | — | — | — |")
            continue
        L.append(f"| `{kind}` | {v['n_samples']} | {_pct(v['accuracy'])} | {_pct(v['changed_vs_unperturbed'])} | "
                 f"{_pct(v['clean_called_unauthorized'])} | {_pct(v['clean_false_alarm'])} | {_pct(v['unauthorized_recall'])} |")
    L += ["", "`authorize_intruder` yalnız `unauthorized` örneklerine uygulanır; `phantom` için boş aralık bulunamayan örnekler "
          "ve `drop_one` için tek taşıyıcılı planlar dışarıda kalır.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="test_id_nl")
    a = ap.parse_args()
    main(a.data, a.runs, a.out, a.split)
