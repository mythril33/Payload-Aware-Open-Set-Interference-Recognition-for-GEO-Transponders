"""Readers for saved result records.

Every value shown in the dashboard is resolved from an explicit key path in a committed or generated
record. A missing key is reported as ABSENT and a JSON null as NULL, with counts where they apply.
Nothing is interpolated, smoothed or filled in. Records are parsed strictly: NaN and Infinity are refused.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT

MAX_RECORD_BYTES = 20 * 2 ** 20
PRESENT, NULL, ABSENT = "present", "null", "absent"


class RecordError(ValueError):
    """A record that cannot be read as a valid result."""


def _refuse_constant(name: str):
    raise RecordError(f"non-finite JSON constant {name} is not allowed in a result record")


def load_record(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_RECORD_BYTES:
        raise RecordError(f"{path.name} is {size} bytes, above the {MAX_RECORD_BYTES}-byte reader limit")
    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=_refuse_constant)
    if not isinstance(data, dict):
        raise RecordError(f"{path.name} is not a JSON object")
    return data


def _join(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def resolve(obj: Any, template: str) -> list[tuple[str, Any]]:
    """Resolve a dotted template. A segment '*' expands to every key of a mapping, in sorted order."""
    nodes: list[tuple[str, Any]] = [("", obj)]
    for segment in template.split("."):
        nxt: list[tuple[str, Any]] = []
        for prefix, node in nodes:
            if not isinstance(node, dict):
                continue
            if segment == "*":
                nxt.extend((_join(prefix, key), node[key]) for key in sorted(node))
            elif segment in node:
                nxt.append((_join(prefix, segment), node[segment]))
        nodes = nxt
    return nodes


@dataclass(frozen=True)
class Read:
    label: str
    path: str
    status: str                 # PRESENT, NULL or ABSENT
    value: Any = None
    note: str = ""


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def scalar_reads(record: dict, label: str, template: str) -> list[Read]:
    """Read one scalar metric. A wildcard template yields one Read per matching key."""
    matches = resolve(record, template)
    if not matches:
        return [Read(label, template, ABSENT, note="key path not stored in this record")]
    reads = []
    for path, value in matches:
        if value is None:
            reads.append(Read(label, path, NULL, note="stored as null"))
        elif _finite_number(value):
            reads.append(Read(label, path, PRESENT, float(value)))
        else:
            reads.append(Read(label, path, ABSENT, note=f"not a finite number ({type(value).__name__})"))
    return reads


@dataclass(frozen=True)
class Confusion:
    path: str
    labels: tuple[str, ...]
    matrix: tuple[tuple[int, ...], ...]

    @property
    def total(self) -> int:
        return sum(sum(row) for row in self.matrix)

    @property
    def accuracy(self) -> float | None:
        """Overall accuracy over the stored matrix. Shown with its denominator (total), never alone."""
        if self.total == 0:
            return None
        return sum(self.matrix[i][i] for i in range(len(self.matrix))) / self.total


def confusion_reads(record: dict, template: str, labels_path: str | None) -> list[Confusion | Read]:
    labels = None
    if labels_path:
        found = resolve(record, labels_path)
        if found and isinstance(found[0][1], list):
            labels = tuple(str(item) for item in found[0][1])
    out: list[Confusion | Read] = []
    for path, value in resolve(record, template):
        if value is None:
            out.append(Read("confusion", path, NULL, note="stored as null"))
            continue
        if not isinstance(value, list) or not value or not all(isinstance(row, list) for row in value):
            out.append(Read("confusion", path, ABSENT, note="not a matrix"))
            continue
        size = len(value)
        if any(len(row) != size for row in value):
            raise RecordError(f"{path}: confusion matrix is not square")
        if not all(isinstance(c, int) and not isinstance(c, bool) and c >= 0 for row in value for c in row):
            raise RecordError(f"{path}: confusion entries must be non-negative integers")
        names = labels if labels is not None and len(labels) == size else tuple(str(i) for i in range(size))
        out.append(Confusion(path, names, tuple(tuple(row) for row in value)))
    if not out:
        out.append(Read("confusion", template, ABSENT, note="key path not stored in this record"))
    return out


@dataclass(frozen=True)
class RocCurve:
    path: str
    fpr: tuple[float, ...]
    tpr: tuple[float, ...]


def roc_reads(record: dict, template: str) -> list[RocCurve | Read]:
    out: list[RocCurve | Read] = []
    for path, value in resolve(record, template):
        if not isinstance(value, dict) or "fpr" not in value or "tpr" not in value:
            out.append(Read("ROC", path, ABSENT, note="no fpr/tpr arrays stored"))
            continue
        fpr, tpr = value["fpr"], value["tpr"]
        if not (isinstance(fpr, list) and isinstance(tpr, list)) or len(fpr) != len(tpr) or not fpr:
            raise RecordError(f"{path}: fpr and tpr must be non-empty lists of equal length")
        if not all(_finite_number(v) and 0.0 <= v <= 1.0 for v in fpr + tpr):
            raise RecordError(f"{path}: ROC coordinates must be finite numbers in [0, 1]")
        out.append(RocCurve(path, tuple(map(float, fpr)), tuple(map(float, tpr))))
    if not out:
        out.append(Read("ROC", template, ABSENT, note="key path not stored in this record"))
    return out


def history_reads(record: dict, template: str) -> list[tuple[str, list[dict]] | Read]:
    out: list[tuple[str, list[dict]] | Read] = []
    for path, value in resolve(record, template):
        if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
            out.append(Read("training history", path, ABSENT, note="no per-epoch rows stored"))
            continue
        out.append((path, value))
    if not out:
        out.append(Read("training history", template, ABSENT, note="key path not stored in this record"))
    return out


@dataclass(frozen=True)
class Bin:
    lo: float | None
    hi: float | None
    n: int
    accuracy: float | None
    confidence: float | None


def calibration_reads(record: dict, template: str) -> list[tuple[str, list[Bin]] | Read]:
    out: list[tuple[str, list[Bin]] | Read] = []
    for path, value in resolve(record, template):
        if not isinstance(value, list) or not value:
            out.append(Read("reliability bins", path, ABSENT, note="no bins stored"))
            continue
        bins = []
        for row in value:
            if not isinstance(row, dict):
                raise RecordError(f"{path}: each calibration bin must be an object")
            n = row.get("n")
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise RecordError(f"{path}: bin count must be a non-negative integer")
            acc, conf = row.get("accuracy"), row.get("confidence")
            bins.append(Bin(row.get("lo"), row.get("hi"), n,
                            float(acc) if _finite_number(acc) else None,
                            float(conf) if _finite_number(conf) else None))
        out.append((path, bins))
    if not out:
        out.append(Read("reliability bins", template, ABSENT, note="key path not stored in this record"))
    return out


@dataclass(frozen=True)
class RecordSpec:
    """Where to find the metrics of one committed record. Templates are reviewed against the files."""
    file: str
    title: str
    labels: str | None = None
    confusion: tuple[str, ...] = ()
    roc: tuple[str, ...] = ()
    history: tuple[str, ...] = ()
    calibration: tuple[str, ...] = ()
    scalars: tuple[tuple[str, str], ...] = ()
    notes: str = ""


CATALOG: tuple[RecordSpec, ...] = (
    RecordSpec(
        file="docs/results/b2_feat_pilot.json", title="B2-feat/1 pilot (development)", labels="labels",
        confusion=("methods.*.confusion",), history=("methods.*.history",),
        scalars=(("ECE", "methods.*.ece.ece"), ("Alarm threshold", "methods.*.alarm.threshold"),
                 ("FPR@95TPR (unknown)", "methods.*.open_set.fpr_at_95_tpr"),
                 ("AUROC (unknown)", "methods.*.open_set.unknown_auroc")),
        notes="Two test-role groups; open-set block is null in this record."),
    RecordSpec(
        file="docs/results/b2_observed_pilot.json", title="Observed-receiver pilot (development)",
        labels="experiment.labels",
        confusion=("experiment.methods.*.classification.confusion",),
        history=("experiment.methods.*.history",),
        calibration=("experiment.methods.*.classification.calibration.bins",),
        scalars=(("ECE", "experiment.methods.*.classification.calibration.ece"),
                 ("Event threshold", "experiment.methods.*.event_detector.threshold"))),
    RecordSpec(
        file="docs/results/b2_full_pilot.json", title="B2 full pilot (development)",
        scalars=(("ECE", "methods.*.ece.ece"), ("Alarm threshold", "methods.*.alarm.threshold"),
                 ("AUROC pooled near (msp)", "methods.*.rejection.msp.pooled_near.ranking.unknown_auroc"),
                 ("AUROC pooled near (energy)", "methods.*.rejection.energy.pooled_near.ranking.unknown_auroc")),
        notes="No top-level confusion matrix is stored in this record; the per-family rejection matrices are not shown."),
    RecordSpec(
        file="docs/results/b2_test_pilot.json", title="B2 test-only pilot (development)",
        scalars=(("ECE", "methods.*.ece.ece"), ("Alarm threshold", "methods.*.alarm.threshold")),
        notes="No confusion matrix or per-epoch history is stored in this record."),
    RecordSpec(
        file="docs/results/openset_extended.json", title="Open-set extended (development)",
        roc=("methods.*.ranking.curves.unknown_roc",), history=("training_history",),
        scalars=(("AUROC (unknown)", "methods.*.ranking.unknown_auroc"),
                 ("OSCR AUC", "methods.*.ranking.oscr_auc"), ("Threshold", "methods.*.threshold"))),
    RecordSpec(
        file="docs/results/openset_development.json", title="Open-set development run",
        history=("training_history",),
        scalars=(("Threshold", "methods.*.threshold"),)),
    RecordSpec(
        file="docs/results/r1_pilot.json", title="R1 pilot (development, five-class)",
        confusion=("splits.*.five_class.confusion",),
        scalars=(("AUROC (detection)", "splits.*.detection.ranking.auroc"),
                 ("FPR@95TPR (detection)", "splits.*.detection.ranking.fpr_at_95_tpr"),
                 ("ECE mean", "splits.*.five_class.ece.mean"))),
    RecordSpec(
        file="docs/results/b2_xgb_baseline.json", title="XGBoost baseline (bounded, verified historical)",
        confusion=("classifier.*.confusion",),
        scalars=(("Binary threshold", "binary.xgboost.threshold"),)),
    RecordSpec(
        file="docs/results/b2_edsc_baseline.json", title="EDSC baseline (bounded, verified historical)",
        scalars=(("Threshold", "methods.edsc.threshold"),
                 ("AUROC (unknown, pooled near)", "methods.edsc.unknown.pooled_near.ranking.unknown_auroc"),
                 ("FPR@95TPR (unknown, pooled near)", "methods.edsc.unknown.pooled_near.ranking.unknown_fpr_at_95_tpr"))),
    RecordSpec(
        file="docs/results/public_data_baselines.json", title="Public-data baselines (verified historical)",
        roc=("datasets.*.experiment.results.native_level.roc",),
        scalars=(("AUROC (native level)", "datasets.*.experiment.results.native_level.auroc"),
                 ("FPR@95TPR (native level)", "datasets.*.experiment.results.native_level.fpr_at_95_tpr"))),
)


def read_record(spec: RecordSpec, repo_root: Path = REPO_ROOT) -> dict:
    """Everything the catalog can show for one record. Each item is a Read or a typed view."""
    path = repo_root / spec.file
    if not path.is_file():
        return {"file": spec.file, "title": spec.title, "error": "file is absent", "items": []}
    record = load_record(path)
    items: list = []
    for label, template in spec.scalars:
        items.extend(scalar_reads(record, label, template))
    for template in spec.confusion:
        items.extend(confusion_reads(record, template, spec.labels))
    for template in spec.roc:
        items.extend(roc_reads(record, template))
    for template in spec.history:
        items.extend(history_reads(record, template))
    for template in spec.calibration:
        items.extend(calibration_reads(record, template))
    return {"file": spec.file, "title": spec.title, "error": None, "notes": spec.notes, "items": items}


def catalog_coverage(repo_root: Path = REPO_ROOT) -> list[dict]:
    """For each catalog record, how many of its templates resolve. Used by the tests and the UI."""
    report = []
    for spec in CATALOG:
        path = repo_root / spec.file
        if not path.is_file():
            report.append({"file": spec.file, "present": False, "resolved": 0, "templates": 0})
            continue
        record = load_record(path)
        templates = list(spec.confusion) + list(spec.roc) + list(spec.history) + list(spec.calibration)
        templates += [template for _, template in spec.scalars]
        resolved = sum(1 for template in templates if resolve(record, template))
        report.append({"file": spec.file, "present": True, "resolved": resolved, "templates": len(templates)})
    return report


__all__ = ["RecordError", "Read", "Confusion", "RocCurve", "Bin", "RecordSpec", "CATALOG", "read_record",
           "load_record", "resolve", "catalog_coverage", "PRESENT", "NULL", "ABSENT"]
