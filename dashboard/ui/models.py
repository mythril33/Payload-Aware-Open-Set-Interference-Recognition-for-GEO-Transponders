"""Model analysis: confusion matrices, ROC curves, FPR95, AUROC, training history and calibration, when stored."""
from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from geodash import evidence, results
from geodash import jobs as J

from .runner import _find_history
from .state import CLASS_LABELS, job_manager


def _class_of(path: str) -> str:
    for entry in evidence.inventory():
        if entry.path == path:
            return entry.evidence_class
    return evidence.UNCLASSIFIED


def _scalar_table(reads: list[results.Read]) -> pd.DataFrame:
    rows = []
    for read in reads:
        if isinstance(read, results.Read) and read.status == results.PRESENT:
            value = read.value
        elif isinstance(read, results.Read):
            value = f"not stored ({read.status})"
        else:
            value = read
        rows.append({"metric": read.label, "key path": read.path, "value": str(value)})
    return pd.DataFrame(rows)


def _plot_confusion(conf: results.Confusion):
    matrix = np.asarray(conf.matrix, dtype=float)
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(conf.labels)), labels=conf.labels, rotation=45, ha="right")
    ax.set_yticks(range(len(conf.labels)), labels=conf.labels)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, f"{int(matrix[i, j])}", ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() / 2 else "black", fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.8, label="count")
    fig.tight_layout()
    return fig


def _plot_roc(curves: list[results.RocCurve]):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    for curve in curves:
        ax.plot(curve.fpr, curve.tpr, label=curve.path.split(".")[1] if "." in curve.path else curve.path)
    ax.plot([0, 1], [0, 1], linestyle=":", color="grey", label="chance")
    ax.set_xlabel("False positive rate (as stored)")
    ax.set_ylabel("True positive rate (as stored)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig


def _plot_reliability(bins: list[results.Bin]):
    usable = [b for b in bins if b.confidence is not None and b.accuracy is not None and b.n > 0]
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    ax.plot([0, 1], [0, 1], linestyle=":", color="grey", label="perfect calibration")
    if usable:
        ax.scatter([b.confidence for b in usable], [b.accuracy for b in usable],
                   s=[10 + b.n for b in usable], alpha=0.8, label="stored bins (size = count)")
    ax.set_xlabel("mean confidence in bin (as stored)")
    ax.set_ylabel("accuracy in bin (as stored)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


def _render_record(spec: results.RecordSpec) -> None:
    data = results.read_record(spec)
    cls = _class_of(spec.file)
    st.subheader(spec.title)
    st.write(f"Source: `{spec.file}` · Evidence class: **{CLASS_LABELS.get(cls, cls)}**")
    if data["error"]:
        st.error(data["error"])
        return
    if data.get("notes"):
        st.caption(data["notes"])
    items = data["items"]
    scalars = [i for i in items if isinstance(i, results.Read) and i.label not in ("confusion", "ROC",
                                                                                 "training history",
                                                                                 "reliability bins")]
    if scalars:
        st.write("Scalar metrics (null or absent values are shown as stored or as not stored):")
        st.dataframe(_scalar_table(scalars), hide_index=True, width="stretch")
    confusions = [i for i in items if isinstance(i, results.Confusion)]
    if confusions:
        st.write("Confusion matrices (counts; the denominator is the total of each matrix):")
        cols = st.columns(min(3, len(confusions)))
        for index, conf in enumerate(confusions):
            with cols[index % len(cols)]:
                st.pyplot(_plot_confusion(conf))
                if conf.accuracy is not None:
                    caption = (f"`{conf.path}` · n = {conf.total} · overall accuracy over the stored matrix = "
                               f"{conf.accuracy:.3f}")
                else:
                    caption = f"`{conf.path}` · n = 0 · accuracy not defined"
                st.caption(caption)
                plt.close("all")
    curves = [i for i in items if isinstance(i, results.RocCurve)]
    if curves:
        st.write("ROC curves (points as stored):")
        st.pyplot(_plot_roc(curves))
        st.caption("; ".join(f"`{c.path}` ({len(c.fpr)} points)" for c in curves))
        plt.close("all")
    histories = [i for i in items if isinstance(i, tuple) and len(i) == 2 and isinstance(i[1], list)]
    for path, rows in histories:
        st.write(f"Training history `{path}` ({len(rows)} rows):")
        numeric = pd.DataFrame([{k: v for k, v in r.items() if isinstance(v, (int, float))} for r in rows])
        if not numeric.empty:
            st.line_chart(numeric)
    bins_items = [i for i in items if isinstance(i, tuple) and len(i) == 2 and isinstance(i[1], list)
                  and i[1] and isinstance(i[1][0], results.Bin)]
    for path, bins in bins_items:
        st.write(f"Reliability bins `{path}`:")
        st.pyplot(_plot_reliability(bins))
        st.dataframe(pd.DataFrame([{"lo": b.lo, "hi": b.hi, "n": b.n, "accuracy": b.accuracy,
                                    "confidence": b.confidence} for b in bins]), hide_index=True)
        plt.close("all")
    for item in items:
        if isinstance(item, results.Read) and item.label in ("confusion", "ROC", "training history",
                                                             "reliability bins") and item.status != results.PRESENT:
            st.info(f"Not stored: {item.label} at `{item.path}` ({item.note}).")


def _render_local_exercise() -> None:
    manager = job_manager()
    done = [j for j in manager.list_jobs() if j.key == "real-exercise" and j.state == J.SUCCEEDED]
    st.subheader("Local development exercise (outside the repository)")
    if not done:
        st.write("No completed local exercise. Run one from Development runner; it is labelled as a local development "
                 "run and is never a committed result.")
        return
    chosen = st.selectbox("Exercise job", [j.job_id for j in done], key="exercise-job")
    status = manager.status(chosen)
    report_path = status.job_dir / "exercise" / "exercise.json"
    st.caption(f"Class: **{CLASS_LABELS['DEVELOPMENT_RUN']}** · scope `BOUNDED_DEVELOPMENT`")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    history = _find_history(report)
    if history is not None:
        st.line_chart(pd.DataFrame(history))
    else:
        st.info("The exercise report stores no per-epoch training history. None is plotted.")
    st.write("Calibration and freeze fields exactly as stored:")
    st.json({k: report.get(k) for k in ("calibration", "freeze") if k in report}, expanded=False)


def render() -> None:
    st.title("Model analysis")
    st.caption("Reads saved results only. Each value comes from a named key path. Missing values are shown as not "
               "stored, never filled in.")
    names = [spec.title for spec in results.CATALOG]
    chosen = st.selectbox("Saved record", names)
    spec = next(s for s in results.CATALOG if s.title == chosen)
    try:
        _render_record(spec)
    except (results.RecordError, ValueError) as error:
        st.error(f"Record refused: {error}")
    st.divider()
    _render_local_exercise()
