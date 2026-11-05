"""Dashboard: the one-click bounded pilot workbench, then repository version, environment, datasets, models,
records and execution gates."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from geodash import commands as C
from geodash import diagnostics, evidence, pilot, repo_status
from geodash import jobs as J
from geodash.paths import REPO_ROOT, LocationError, run_home

from .state import CLASS_LABELS, job_manager

HEADER = "GEO PAYLOAD AWARE — RESEARCH WORKBENCH"
GROUP_LABELS = {1: "1 grup (varsayılan)", 2: "2 grup (sınırlı)"}
START_LABEL = "GEO PİLOT BAŞLAT"
REFRESH_LABEL = "DURUMU YENİLE"
CANCEL_LABEL = "GÜVENLİ İPTAL"
PROFILE_NOTE = "Geliştirme profili: CPU, yalnız train/val-select/val-calib, held-out erişimi yok"
STAGES = ("RF üretimi", "eğitim", "val-calib", "dondurma", "rapor")
# infer_stage() labels -> indexes into STAGES that the pilot is in. Training and val-calib share one output
# folder, so the files cannot tell them apart; both are shown as current.
STAGE_INDEX = {"starting": (0,), "RF generation": (0,), "training and calibration": (1, 2),
               "freeze written": (4,), "complete": ()}
WINDOWS_GUIDANCE = "Gerçek RF pilotu WSL2 Ubuntu gerektirir; 'GEO WSL Kurulumu' kısayolunu çalıştırın"
STATIC_NOTES = (
    "Araştırma sonuçları: YALNIZ PİLOT (21.350 gözlemlik benchmark değil)",
    "Üretim 21.350 / GPU / LOKO / held-out: KİLİTLİ",
    "exercise.json işlevsel akışı kanıtlar, tanıma performansını değil",
)
NOT_GIT_GUIDANCE = ("Kaynak bir Git deposu değil: eğitim Git commit kimliğini kaydeder, bu yüzden pilot bu "
                    "kopyadan çalışamaz; 'GEO WSL Kurulumu' kısayolunu yeniden çalıştırın")
PREFLIGHT_TR = {
    "PILOT_ALREADY_RUNNING": "Bir pilot zaten çalışıyor",
    "OTHER_JOB_RUNNING": "Başka bir iş çalışıyor; bitmesini bekleyin veya iptal edin",
    "PLATFORM_NOT_POSIX": "Bu platform pilotu çalıştıramaz (WSL2 Ubuntu veya Linux gerekir)",
    "GROUPS_REFUSED": "Grup sayısı reddedildi (yalnız 1 veya 2)",
    "DEPENDENCIES_MISSING": "Gerekli paketler eksik (torch, numpy, scipy)",
    "SOURCE_NOT_VERIFIED": "Kaynak doğrulanamadı",
    "SOURCE_NOT_GIT": "Kaynak bir Git deposu değil",
    "JOB_RECORD_UNREADABLE": "Bir iş kaydı (job.json) okunamıyor; klasörü kenara taşıyın",
    "DISK_INSUFFICIENT": "Çıktı klasöründe disk alanı yetersiz",
}
CANCEL_TR = {
    pilot.EXIT_OK: "İptal edildi: yalnız bu pilotun süreç ağacı durduruldu; günlük ve çıktılar korundu.",
    pilot.EXIT_NONE: "Çalışan pilot yok; hiçbir süreç durdurulmadı.",
    pilot.EXIT_OWNERSHIP: ("Sahiplik doğrulanamadı: kayıtlı süreç kimliği artık başka bir sürece ait; "
                           "sinyal gönderilmedi."),
}
FINAL_TR = {
    J.SUCCEEDED: "Pilot tamamlandı (çıkış durumu 0).",
    J.FAILED: "Pilot başarısız oldu.",
    J.CANCELLED: "Pilot iptal edildi; günlük ve çıktılar korundu.",
    J.TIMED_OUT: "Pilot zaman sınırını aştı ve durduruldu.",
    J.FINISHED_UNRECORDED: ("Süreç bitti, fakat çıkış durumu kaydedilmedi (başlatan süreç yok); "
                            "başarı varsayılmaz."),
    J.RECORD_UNREADABLE: "job.json okunamıyor; kayıt değiştirilmeden bırakıldı. Başarı değildir.",
}


def _disabled_reasons(eng: dict, source: dict) -> list[str]:
    reasons = []
    if not eng.get("pilot_capable"):
        reasons.append(WINDOWS_GUIDANCE if eng.get("id") == "native-windows"
                       else f"Bu motor pilotu çalıştıramaz: {eng.get('label_tr')}. {WINDOWS_GUIDANCE}")
    else:
        available, why = C.is_available(C.REGISTRY[pilot.PILOT_KEY])
        if not available:
            reasons.append(f"{WINDOWS_GUIDANCE} ({why})")
    if not source.get("verified"):
        problems = source.get("problems") or ["kaynak tanımlanamadı"]
        reasons.append("Kaynak doğrulanmadı: " + "; ".join(str(p) for p in problems))
    elif source.get("mode") != "git":
        reasons.append(NOT_GIT_GUIDANCE)
    return reasons


def _status_line(eng: dict, source: dict) -> str:
    commit = (source.get("commit") or "unknown")[:12]
    verified = "verified" if source.get("verified") else "unverified"
    return (f"Engine: {eng.get('label')}  |  Source: {source.get('mode')} {commit} ({verified})  |  "
            "Benchmark: INCOMPLETE")


def _stage_chain(status: J.JobStatus) -> str:
    current = STAGE_INDEX.get(status.stage, ())
    done_before = min(current) if current else (len(STAGES) if status.stage == "complete" else 0)
    parts = []
    for index, name in enumerate(STAGES):
        if index in current:
            parts.append(f"**{name} (şu an, çıkarım)**" if not status.is_final else f"**{name} (burada durdu)**")
        elif index < done_before:
            parts.append(f"{name} (tamam)")
        else:
            parts.append(name)
    return " → ".join(parts)


def _final_message(status: J.JobStatus, verified: bool) -> None:
    text = FINAL_TR.get(status.state, status.state)
    if status.state == J.SUCCEEDED and verified:
        st.success(f"{text} exercise.json sınır alanları doğrulandı. {STATIC_NOTES[2]}.")
    elif status.state == J.SUCCEEDED:
        st.error(f"{text} Ancak exercise.json doğrulanmadı: {status.reason}")
    elif status.state == J.CANCELLED:
        st.warning(f"{text} {status.reason}")
    else:
        st.error(f"{text} {status.reason}")


def _job_details(status: J.JobStatus) -> None:
    info = pilot.pilot_status_dict(status)
    st.markdown(f"Pilot işi `{status.job_id}`  ·  durum `{status.state}`  ·  grup {info['groups']}")
    st.markdown("Aşama: " + _stage_chain(status))
    if status.stage_detail:
        st.caption(f"Aşama çıkarımı çıktı dosyalarından yapılır: {status.stage_detail}")
    if not status.is_final:
        st.progress(min(1.0, status.elapsed_s / max(1, status.timeout_s)),
                    text=f"geçen süre: {status.elapsed_s:.0f} s / {status.timeout_s} s sınır (bu çubuk zamanı "
                         f"ölçer, tamamlanmayı değil — time, not completion)")
    else:
        st.write(f"Geçen süre: {status.elapsed_s:.0f} s (zaman, tamamlanma değil). "
                 f"Çıkış durumu: {status.returncode}")
        _final_message(status, info["verified"])
    st.write(f"Çıktı klasörü (deponun dışında): `{status.job_dir / 'exercise'}`")
    st.caption(f"İş klasörü: `{status.job_dir}`")
    d1, d2 = st.columns(2)
    report = status.job_dir / "exercise" / "exercise.json"
    record = status.job_dir / "pilot.json"
    if report.is_file():
        d1.download_button("exercise.json indir", report.read_bytes(), file_name="exercise.json",
                           key=f"pilot-dl-exercise-{status.job_id}")
    else:
        d1.caption("exercise.json henüz yazılmadı.")
    if record.is_file():
        d2.download_button("pilot.json indir", record.read_bytes(), file_name="pilot.json",
                           key=f"pilot-dl-record-{status.job_id}")
    else:
        d2.caption("pilot.json henüz yazılmadı.")
    with st.expander("Günlük (son satırlar)"):
        if status.generator_log_tail:
            st.write("RF üreteci günlüğü:")
            st.code("\n".join(status.generator_log_tail), language="text")
        st.write("Komut çıktısı:")
        st.code("\n".join(status.log_tail[-60:]) or "(henüz çıktı yok)", language="text")


def _start(groups: int, manager: J.JobManager) -> None:
    # serve exported the Windows package identity; the click and the supervisor both check it.
    commit, manifest = pilot.expected_identity()
    pre = pilot.preflight(groups, commit, manifest, manager=manager)
    if not pre["ok"]:
        lines = [f"- {PREFLIGHT_TR.get(code, code)} (`{code}`): {reason}"
                 for code, reason in zip(pre["codes"], pre["reasons"])]
        if pre.get("running_job"):
            key = pre.get("running_job_key")
            lines.append(f"- Çalışan iş: `{pre['running_job']}`" + (f" (`{key}`)" if key else ""))
        st.error(f"Ön kontrol pilotu başlatmadı (çıkış kodu {pre['exit_code']}):\n\n" + "\n".join(lines))
        return
    try:
        proc = pilot.spawn_supervisor(groups, expect_commit=commit, expect_manifest_sha256=manifest)
    except (C.CommandRefused, LocationError, OSError) as error:
        st.error(f"Pilot başlatılamadı: {error}")
        return
    st.success(f"Pilot gözetmeni başlatıldı (süreç {proc.pid}, {groups} grup). İş kimliği birkaç saniye içinde "
               f"görünür; '{REFRESH_LABEL}' ile güncelleyin.")


def _cancel(job_id: str, manager: J.JobManager) -> None:
    lines: list[str] = []
    code = pilot.cancel_pilot(job_id, manager=manager, out=lines.append)
    message = CANCEL_TR.get(code, f"Beklenmeyen sonuç {code}")
    detail = (" " + " ".join(lines)) if lines else ""
    (st.success if code == pilot.EXIT_OK else st.warning)(f"{message}{detail}")


@st.fragment(run_every=5)
def _workbench() -> None:
    manager = job_manager()
    eng = pilot.engine()
    commit, manifest = pilot.expected_identity()
    source = pilot.source_identity(expect_commit=commit, expect_manifest_sha256=manifest)
    latest = pilot.latest_pilot(manager)
    gpu_present = "device_nodes" in diagnostics.gpu_facts()
    states = pilot.workbench_states(engine=eng, source=source, latest=latest,
                                    gate_rows=repo_status.gate_rows(), gpu_present=gpu_present)

    st.markdown(_status_line(eng, source))
    if commit or manifest:
        st.caption(f"Beklenen paket kimliği: commit `{(commit or '-')[:12]}`, manifest `{(manifest or '-')[:12]}`")
    st.markdown("**Research gates: CLOSED / NO PRODUCTION AUTHORITY**")
    st.markdown("  ".join(f"`{state}`" for state in states))

    st.subheader("Sınırlı GEO pilotu")
    st.caption(PROFILE_NOTE)
    running = latest if latest is not None and latest.state == J.RUNNING else None
    reasons = _disabled_reasons(eng, source)
    groups = st.radio("Grup sayısı (her geliştirme rolü için)", list(GROUP_LABELS), format_func=GROUP_LABELS.get,
                      horizontal=True, key="pilot-groups", disabled=running is not None)
    b1, b2, b3 = st.columns(3)
    if running is not None:
        b1.info(f"Pilot çalışıyor: iş `{running.job_id}`. İkinci başlatma yok.")
        start = False
    else:
        start = b1.button(START_LABEL, type="primary", key="pilot-start", disabled=bool(reasons),
                          help="; ".join(reasons) or None)
    b2.button(REFRESH_LABEL, key="pilot-refresh")
    cancel = b3.button(CANCEL_LABEL, key="pilot-cancel", disabled=running is None)
    for reason in reasons:
        st.warning(reason)
    if start:
        _start(groups, manager)
    if cancel and running is not None:
        _cancel(running.job_id, manager)
        latest = manager.status(running.job_id)

    if latest is None:
        st.write("Henüz pilot çalıştırılmadı. Aşamalar: " + " → ".join(STAGES))
    else:
        _job_details(latest)
    for note in STATIC_NOTES:
        st.markdown(f"- {note}")
    if "HOST_NOT_QUALIFIED" in states:
        st.caption("Bu makine üretim için nitelikli bir ana makine değildir; kapılar bu uygulamadan açılamaz.")


def render() -> None:
    st.title(HEADER)
    _workbench()
    st.divider()

    st.header("GEO research dashboard")
    st.caption("Simulation-only research repository. There is no field data (see DURUM section 5.5). "
               "Nothing on this page is a recognition-performance claim.")

    git = repo_status.git_state()
    version = repo_status.project_version()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Package version", version or "unknown")
    c2.metric("Branch", git.get("branch") or "unknown")
    c3.metric("Commit", git.get("head") or "unknown")
    dirty = git.get("uncommitted_files")
    c4.metric("Uncommitted files", "unknown" if dirty is None else dirty)
    if git.get("head_subject"):
        st.caption(f"HEAD: {git['head_subject']} ({git.get('head_date')})")

    st.subheader("Execution gates")
    rows = repo_status.gate_rows()
    st.info(repo_status.gate_summary(rows))
    runtime, source = repo_status.runtime_permitted()
    st.write(f"Execution contract: `{source}` returns **{runtime}**." if runtime is not None
             else f"Execution contract: {source}.")
    gate_table = pd.DataFrame(rows)
    gate_table["value"] = gate_table["value"].astype(str)
    st.dataframe(gate_table, hide_index=True, width="stretch")
    st.caption("Values are copied from the committed gate records. This application cannot change them, and it has "
               "no production launch control.")

    st.subheader("Environment readiness")
    deps = diagnostics.dependency_versions()
    ready = diagnostics.readiness(deps)
    e1, e2 = st.columns(2)
    e1.metric("Dashboard runs here", "yes" if ready["gui_ready"] else "missing: " + ", ".join(ready["gui_missing"]))
    e2.metric("Development runner", "yes" if ready["runner_ready"] else "missing: " + ", ".join(ready["runner_missing"]))
    st.caption(ready["note"])

    st.subheader("Datasets")
    data_dir = REPO_ROOT / "data"
    if data_dir.exists():
        st.write(f"`data/` exists in this checkout ({sum(1 for _ in data_dir.iterdir())} entries). Not tracked by Git.")
    else:
        st.write("No generated dataset in this checkout: `data/` is absent. Datasets produced by the development "
                 "runner are listed under Development runner, in the run folder outside the repository.")
    st.write(f"Run folder (outside the repository): `{run_home()}`")

    st.subheader("Models and experiment records")
    inventory = evidence.inventory()
    counts = evidence.counts_by_class(inventory)
    table = pd.DataFrame([{"class": CLASS_LABELS.get(k, k), "files": v} for k, v in counts.items()])
    st.dataframe(table, hide_index=True, width="stretch")
    protected = [e for e in inventory if e.evidence_class == evidence.PROTECTED_PRODUCTION]
    st.write(f"Protected production evaluations recorded: **{len(protected)}**. None exists, and none is "
             "authorized (gates above).")
    local_models = [j for j in job_manager().list_jobs() if j.key == "real-exercise" and j.stage == "complete"]
    st.write(f"Completed local development exercises (committed records are not affected): **{len(local_models)}**.")

    with st.expander("How to read these labels"):
        for key, legend in evidence.classes_legend().items():
            st.write(f"**{CLASS_LABELS.get(key, key)}** (`{key}`): {legend}")
