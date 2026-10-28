"""Interactive learning app for the RF-ML project (Streamlit).

Run from the project folder:  streamlit run app.py

Four stages, each with its question, controls, a Çalıştır button, live status and
results. Nothing heavy runs on page load. Finished results are kept in
st.session_state, so a result stays visible when you switch stages. All data is
synthetic: simulated transmitters, not field recordings.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # `import rfml` works whatever the working directory is

import streamlit as st
import torch
from rfml import experiments as ex

PAGE_TITLE = "RF-ML öğrenme aracı"
STAGE_1 = "1 · Tensör ve gradyan"
STAGE_2 = "2 · Modülasyon sınıflandırma"
STAGE_3 = "3 · RF parmak izi"
STAGE_4 = "4 · Açık küme"
STAGES = (STAGE_1, STAGE_2, STAGE_3, STAGE_4)

RESULTS_KEY = "results"  # st.session_state key: finished runs, one slot per control set
SYNTHETIC_NOTE = (
    "Veriler simülasyondur (sentetik vericiler). Bu sonuçlar bir sistemin gerçek "
    "alan verisindeki başarımını göstermez; bir öğrenme aracıdır."
)
SCALE_LABELS = {
    "quick": "quick · duman testi",
    "standard": "standard · orta boy",
    "full": "full · ders varsayılanı",
}
# Measured here: one torch thread, four stages, machine under load from other processes.
SCALE_TIMES = {"quick": "yaklaşık 5 s", "standard": "yaklaşık 2,3 dk", "full": "yaklaşık 7,5 dk"}

QUESTION_1 = """
**Soru:** Doğrusal bir modelin iki parametresini (eğim *w* ve sabit *b*) gradyan inişiyle
öğrenebilir miyiz? Elle yazdığımız türev formülü, otomatik türevle (autograd) aynı sonucu veriyor mu?

**Bakılacaklar:** kayıp eğrisinin düşüşü; öğrenme oranı kararlılık sınırını aşınca kaybın
iraksaması; *gradyan kontrolü* satırında el ile ve otomatik türevin farkının küçük olması.
"""

QUESTION_1B = """
**Soru:** Bir IQ çerçevesi tensör olarak nasıl görünür? Zaman alanında, takımyıldızda
(konstelasyon) ve frekans alanında (güç spektrumu) ne görürüz?

**Bakılacaklar:** bozulmalar açıkken takımyıldızdaki noktaların ideal konumdan kayması. Spektrumun
genişliği darbe şekline bağlıdır: sembol hızı 1/8 döngü/örnek ve yuvarlanma β = 0,35 için
RRC darbesinin toplam genişliği yaklaşık 0,17 döngü/örnek.
"""

QUESTION_2 = """
**Soru:** Eğitimde görülmeyen cihazlardan gelen BPSK, QPSK, 8PSK ve 16QAM çerçevelerini,
sinyal-gürültü oranına (SNR) göre ne kadar doğru tanıyoruz?

**Bakılacaklar:** şans düzeyi 0,25 (4 sınıf). Eğitim aralığının altındaki −6 dB satırı. MLP ile
CNN1D arasındaki fark (CNN1D zamansal yapıyı kullanır). Her satırdaki *n*: aynı cihazın çerçeveleri
birbiriyle ilişkilidir, bu yüzden *n* bağımsız örnek sayısını olduğundan büyük gösterir.
"""

QUESTION_3 = """
**Soru:** Aynı QPSK sinyalini gönderen cihazlar yalnızca donanım kusurlarıyla (IQ dengesizliği,
PA doyumu, faz gürültüsü, DC ofseti) ayırt edilebilir mi?

**Önemli:** Bölme *çerçeve düzeyindedir*, çünkü bu aşamada etiket cihazın kendisidir. Her cihazın
çerçeveleri hem eğitimde hem testte bulunur. Sonuç, bilinen cihazları yeni çerçevelerden tanımayı
ölçer; yeni bir cihaza genellemeyi ölçmez.

**Bakılacaklar:** bozulmasız (ideal) kontrolde doğruluğun şans düzeyi 1/N yakınında kalması beklenir.
"""

QUESTION_4 = """
**Soru:** Ağ yalnızca BPSK, QPSK, 8PSK ve 16QAM ile eğitildiğinde, hiç görmediği 64QAM ve 4PAM
çerçevelerini "bilinmeyen" diye reddedebilir mi?

**Kurallar:** Eşik yalnızca bilinen *doğrulama* çerçevelerinden, hedef bilinen-kabul oranına göre
hesaplanır. Bilinmeyen test çerçeveleri eşik belirlendikten sonra bir kez puanlanır; eğitimde,
seçimde ya da eşik hesabında kullanılmazlar. ξ ve λ yalnızca Objectosphere varyantını etkiler.

**Bakılacaklar:** birim-reddetme oranı ve AUROC (pozitif sınıf = bilinmeyen, şans = 0,5). Objectosphere
varyantı eğitimde 16PSK ve 8PAM dış-örneklerini kullanır; reddetme oranı bu yüzden iyimser bir üst sınırdır.
"""


# ---------------------------------------------------------------------------
# State and run helpers
# ---------------------------------------------------------------------------


def _results() -> dict:
    if RESULTS_KEY not in st.session_state:
        st.session_state[RESULTS_KEY] = {}
    return st.session_state[RESULTS_KEY]


def _store(slot: str, params: dict, result, elapsed: float) -> None:
    _results()[slot] = {"params": params, "result": result, "elapsed_s": elapsed}


def _stored(slot: str) -> dict | None:
    return _results().get(slot)


def _run(label: str, fn):
    """Run fn(progress) inside a status box. Returns (result, seconds), or None on error."""
    started = time.perf_counter()
    with st.status(label, expanded=False) as status:

        def progress(message: str) -> None:
            status.update(label=message)

        try:
            result = fn(progress)
        except Exception as exc:  # noqa: BLE001 - UI boundary: show the failure instead of a blank page
            status.update(label="Hata oluştu", state="error", expanded=True)
            st.exception(exc)
            return None
        elapsed = time.perf_counter() - started
        status.update(label=f"Tamamlandı · {elapsed:.1f} s", state="complete")
    return result, elapsed


def _acc(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _rate(k: int, n: int) -> str:
    return "tanımsız (0/0)" if n == 0 else f"{k / n:.3f} ({k}/{n})"


def _scale_selector(key: str) -> ex.Scale:
    name = st.selectbox("Ölçek", list(ex.SCALES), format_func=SCALE_LABELS.get, key=key)
    scale = ex.get_scale(name)
    st.caption(
        f"{scale.tx_train} cihaz/sınıf (eğitim) · {scale.frames_train} çerçeve/cihaz · "
        f"{scale.epochs} dönem · erken durdurma sabrı {scale.patience} · "
        f"tek iş parçacığında {SCALE_TIMES[name]} (dört aşama, bu makinede ölçüldü)"
    )
    return scale


def _params_caption(params: dict, elapsed: float) -> None:
    text = ", ".join(f"{k} = {v}" for k, v in params.items())
    st.caption(f"Bu sonuç şu ayarlarla üretildi: {text} · süre {elapsed:.1f} s")


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------


def _show_gradient(entry: dict) -> None:
    r = entry["result"]
    _params_caption(entry["params"], entry["elapsed_s"])
    if r["diverged"]:
        st.error(
            f"Adım {r['diverged_at_step']} civarında değerler sonsuza gitti: kayıp iraksadı. "
            "Öğrenme oranını azaltın."
        )
    c1, c2, c3 = st.columns(3)
    c1.metric("gradyan inişi · w", _acc(r["w"]), help=f"gerçek w = {r['true_w']}")
    c2.metric("gradyan inişi · b", _acc(r["b"]), help=f"gerçek b = {r['true_b']}")
    c3.metric("güncelleme sayısı", r["steps_run"], help="Kayıp, her güncellemeden sonra ölçülür.")
    c4, c5, c6 = st.columns(3)
    c4.metric("en küçük kareler · w", _acc(r["least_squares"]["w"]), help="Kapalı form çözüm (karşılaştırma).")
    c5.metric("en küçük kareler · b", _acc(r["least_squares"]["b"]))
    c6.metric(
        "gradyan kontrolü · maks |el − autograd|",
        f"{r['grad_check_max_abs_diff']:.2e}",
        help="Her adımda el ile yazılan gradyan ile autograd farkının en büyüğü. Küçük olmalıdır.",
    )
    st.info(
        f"Bu veri için kararlılık sınırı lr < {r['stability_lr_bound']:.3f} (2/λmax). "
        "Sınırın altında kayıp düşer; üstünde iraksar."
    )
    st.pyplot(ex.fig_gradient(r))
    st.download_button(
        "Sonucu JSON olarak indir",
        data=ex.to_strict_json(r),
        file_name="stage1_gradient.json",
        mime="application/json",
        key="dl_gradient",
    )


def _gradient_tab() -> None:
    left, mid, right = st.columns(3)
    lr = left.slider(
        "Öğrenme oranı (lr)",
        min_value=0.01,
        max_value=1.2,
        value=0.1,
        step=0.01,
        key="g_lr",
        help="Bu veri için kararlılık sınırı yaklaşık 1'dir. Sınırın üstünde kayıp iraksar.",
    )
    steps = mid.slider("Güncelleme sayısı", min_value=10, max_value=1000, value=200, step=10, key="g_steps")
    seed = right.number_input("Tohum (seed)", min_value=0, max_value=9999, value=0, step=1, key="g_seed")
    if st.button("Çalıştır", key="g_run", type="primary"):
        out = _run(
            "Gradyan inişi çalışıyor…",
            lambda _progress: ex.run_gradient_demo(float(lr), int(steps), int(seed)),
        )
        if out is not None:
            result, elapsed = out
            _store("gradient", {"lr": lr, "steps": steps, "seed": int(seed)}, result, elapsed)
    entry = _stored("gradient")
    if entry:
        _show_gradient(entry)


def _frames_tab() -> None:
    mods = st.multiselect(
        "Modülasyonlar",
        list(ex.MODULATIONS),
        default=["BPSK", "QPSK", "16QAM"],
        key="f_mods",
    )
    c1, c2, c3, c4 = st.columns(4)
    snr = c1.slider("SNR (dB)", min_value=-10.0, max_value=30.0, value=10.0, step=1.0, key="f_snr")
    n = c2.select_slider("Çerçeve uzunluğu (örnek)", options=[128, 256, 512, 1024], value=512, key="f_n")
    impaired = c3.checkbox("Donanım bozulmaları açık", value=True, key="f_imp")
    seed = c4.number_input("Tohum (seed)", min_value=0, max_value=9999, value=0, step=1, key="f_seed")
    if st.button("Çalıştır", key="f_run", type="primary"):
        if not mods:
            st.warning("En az bir modülasyon seçin.")
        else:
            started = time.perf_counter()
            frames = ex.show_frames(tuple(mods), float(snr), bool(impaired), int(n), int(seed))
            _store(
                "frames",
                {"modulations": mods, "snr_db": snr, "impaired": impaired, "n": n, "seed": int(seed)},
                frames,
                time.perf_counter() - started,
            )
    entry = _stored("frames")
    if entry:
        frames = entry["result"]
        _params_caption(entry["params"], entry["elapsed_s"])
        st.pyplot(ex.fig_frames(frames))
        st.markdown(
            "**Cihaz parametreleri** (simülatörün gerçek değerleri, yalnızca öğrenme için gösterilir; "
            "`pa_saturation` boş ise cihazda sıkıştırma yoktur)."
        )
        st.dataframe([f["device"] for f in frames["frames"]], hide_index=True)


def render_stage_1() -> None:
    st.subheader(STAGE_1)
    st.markdown(QUESTION_1)
    tab_grad, tab_frames = st.tabs(["Gradyan demosu", "IQ çerçevesi: tensör ve spektrum"])
    with tab_grad:
        _gradient_tab()
    with tab_frames:
        st.markdown(QUESTION_1B)
        _frames_tab()


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------


def _show_modulation(entry: dict) -> None:
    r = entry["result"]
    _params_caption(entry["params"], entry["elapsed_s"])
    cols = st.columns(len(r["models"]))
    for col, (name, run) in zip(cols, r["models"].items()):
        overall = run["overall"]
        col.metric(
            f"{name} · toplam doğruluk",
            _acc(overall["accuracy"]),
            help=(
                f"Olay: çerçevenin doğru sınıflandırılması. Payda: tüm test çerçeveleri, n = {overall['n']}. "
                f"Şans düzeyi = {r['chance_level']:.3f}."
            ),
        )
    names = list(r["models"])
    rows = []
    for i, snr in enumerate(r["test_snr_db"]):
        row = {
            "SNR (dB)": snr,
            "n": r["models"][names[0]]["per_snr"][i]["n"],
            "eğitim aralığında mı": snr >= min(r["train_snr_db"]),
        }
        for name in names:
            row[name] = r["models"][name]["per_snr"][i]["accuracy"]
        row["şans"] = r["chance_level"]
        rows.append(row)
    st.markdown("**Doğruluk, SNR'ye göre** (her satırda *n*: o SNR'deki test çerçeveleri, payda)")
    st.dataframe(rows, hide_index=True)

    chosen = st.selectbox("Karışıklık matrisi için model", names, key="m_cm_model")
    cm = r["models"][chosen]["confusion_overall"]
    st.markdown(f"**Karışıklık matrisi · {chosen}** (satır = gerçek sınıf, sütun = tahmin, tüm SNR'ler)")
    st.dataframe(
        [{"gerçek \\ tahmin": cls, **{f"tahmin {c}": cm[i][j] for j, c in enumerate(r["classes"])}}
         for i, cls in enumerate(r["classes"])],
        hide_index=True,
    )
    st.pyplot(ex.fig_modulation(r))
    st.download_button(
        "Sonucu JSON olarak indir",
        data=ex.to_strict_json(r),
        file_name="stage2_modulation.json",
        mime="application/json",
        key="dl_modulation",
    )


def render_stage_2() -> None:
    st.subheader(STAGE_2)
    st.markdown(QUESTION_2)
    st.info(SYNTHETIC_NOTE)
    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        scale = _scale_selector("m_preset")
    impaired = c2.checkbox("Donanım bozulmaları açık", value=True, key="m_imp",
                           help="Kapalıyken aynı modülasyondaki tüm cihazlar birebir aynıdır.")
    models = c3.multiselect("Modeller", list(ex.MODEL_BUILDERS), default=list(ex.MODULATION_MODELS), key="m_models")
    seed = st.number_input("Tohum (seed)", min_value=0, max_value=9999, value=2, step=1, key="m_seed")
    if st.button("Çalıştır", key="m_run", type="primary"):
        if not models:
            st.warning("En az bir model seçin.")
        else:
            out = _run(
                "Modülasyon sınıflandırma çalışıyor…",
                lambda progress: ex.run_modulation(scale, bool(impaired), int(seed), tuple(models), progress),
            )
            if out is not None:
                result, elapsed = out
                _store("modulation", {"ölçek": scale.name, "donanım": impaired, "seed": int(seed),
                                      "modeller": ", ".join(models)}, result, elapsed)
    entry = _stored("modulation")
    if entry:
        _show_modulation(entry)


# ---------------------------------------------------------------------------
# Stage 3
# ---------------------------------------------------------------------------


def _show_fingerprint(runs: list[dict], elapsed: float, params: dict) -> None:
    _params_caption(params, elapsed)
    cols = st.columns(len(runs))
    for col, run in zip(cols, runs):
        label = "bozulmalı cihazlar" if run["impaired"] else "ideal cihazlar (kontrol)"
        col.metric(
            f"{label} · toplam doğruluk",
            _acc(run["overall"]["accuracy"]),
            help=(
                f"Payda: test çerçeveleri, n = {run['overall']['n']}. Şans düzeyi = 1/{run['n_devices']} "
                f"= {run['chance_level']:.3f}. Cihaz sayısı: {run['n_devices']}."
            ),
        )
    for run in runs:
        label = "bozulmalı" if run["impaired"] else "ideal (kontrol)"
        rows = [
            {"SNR (dB)": r["snr_db"], "n": r["n"], "doğruluk": r["accuracy"], "şans": run["chance_level"]}
            for r in run["per_snr"]
        ]
        st.markdown(f"**{label}**: SNR'ye göre doğruluk (*n*: o SNR'deki test çerçeveleri)")
        st.dataframe(rows, hide_index=True)
    st.pyplot(ex.fig_fingerprint(runs))
    st.download_button(
        "Sonucu JSON olarak indir",
        data=ex.to_strict_json({"stage": "fingerprint", "runs": runs}),
        file_name="stage3_fingerprint.json",
        mime="application/json",
        key="dl_fingerprint",
    )


def render_stage_3() -> None:
    st.subheader(STAGE_3)
    st.markdown(QUESTION_3)
    st.info(SYNTHETIC_NOTE)
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        scale = _scale_selector("p_preset")
    impaired = c2.checkbox("Donanım bozulmaları açık", value=True, key="p_imp")
    control = c2.checkbox(
        "İdeal (bozulmasız) kontrolü de çalıştır",
        value=False,
        key="p_ctrl",
        disabled=not impaired,
        help="Aynı tohumla bozulmasız cihazlar da üretilir; doğruluk şans düzeyine yakın beklenir.",
    )
    seed = c3.number_input("Tohum (seed)", min_value=0, max_value=9999, value=3, step=1, key="p_seed")
    if st.button("Çalıştır", key="p_run", type="primary"):
        flags = [bool(impaired)] + ([False] if (control and impaired) else [])

        def _go(progress):
            runs = []
            for flag in flags:
                prefix = "bozulmalı" if flag else "ideal kontrol"
                runs.append(
                    ex.run_fingerprint(
                        scale, flag, int(seed),
                        progress=lambda message, p=prefix: progress(f"{p}: {message}"),
                    )
                )
            return runs

        out = _run("RF parmak izi çalışıyor…", _go)
        if out is not None:
            runs, elapsed = out
            _store("fingerprint", {"ölçek": scale.name, "donanım": impaired,
                                   "kontrol": bool(flags[1:]), "seed": int(seed)}, runs, elapsed)
    entry = _stored("fingerprint")
    if entry:
        _show_fingerprint(entry["result"], entry["elapsed_s"], entry["params"])


# ---------------------------------------------------------------------------
# Stage 4
# ---------------------------------------------------------------------------


def _show_open_set(entry: dict) -> None:
    r = entry["result"]
    _params_caption(entry["params"], entry["elapsed_s"])
    target = r["target_known_accept"]
    rows = []
    for name, v in r["variants"].items():
        rep = v["report"]
        rows.append(
            {
                "varyant": name,
                "eşik": round(v["threshold"], 4),
                "bilinen kabul (k/n)": _rate(v["known_accepted"], rep["n_known"]),
                "bilinmeyen reddi (k/n)": _rate(v["unknown_rejected"], rep["n_unknown"]),
                "AUROC (şans 0,5)": "tanımsız" if rep["auroc"] is None else round(rep["auroc"], 3),
                "kabul edilenlerde kapalı küme doğruluğu (k/n)": _rate(
                    v["closed_set_on_accepted"]["n_correct"], v["closed_set_on_accepted"]["n"]
                ),
            }
        )
    st.dataframe(rows, hide_index=True)

    for name, v in r["variants"].items():
        rep = v["report"]
        st.markdown(f"**{name}** · eşik = {v['threshold']:.4f} (bilinen doğrulama çerçevelerinin "
                    f"%{target * 100:.0f}'i kabul edilir)")
        st.markdown(
            f"- bilinen kabul oranı: bilinen **test** çerçeveleri üzerinden, n = {rep['n_known']}: "
            f"{_rate(v['known_accepted'], rep['n_known'])}\n"
            f"- birim-reddetme oranı: bilinmeyen **test** çerçeveleri (64QAM, 4PAM) üzerinden, "
            f"n = {rep['n_unknown']}: {_rate(v['unknown_rejected'], rep['n_unknown'])}\n"
            f"- AUROC (pozitif sınıf = bilinmeyen, şans = 0,5, n = {rep['n_known']} + {rep['n_unknown']}): "
            f"{_acc(rep['auroc'])}\n"
            f"- kapalı küme doğruluğu, yalnızca eşiği geçen bilinen çerçeveler üzerinden, "
            f"n = {v['closed_set_on_accepted']['n']}: "
            f"{_rate(v['closed_set_on_accepted']['n_correct'], v['closed_set_on_accepted']['n'])} "
            f"(şans = 0,250)"
        )
    st.pyplot(ex.fig_open_set(r))
    st.download_button(
        "Sonucu JSON olarak indir",
        data=ex.to_strict_json(r),
        file_name="stage4_open_set.json",
        mime="application/json",
        key="dl_open_set",
    )


def render_stage_4() -> None:
    st.subheader(STAGE_4)
    st.markdown(QUESTION_4)
    st.info(SYNTHETIC_NOTE + " Bu aşamada tüm cihazlar donanım bozulmalarıyla üretilir.")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        scale = _scale_selector("o_preset")
    seed = c2.number_input("Tohum (seed)", min_value=0, max_value=9999, value=4, step=1, key="o_seed")
    xi = c3.slider("ξ (Objectosphere)", min_value=1.0, max_value=30.0, value=ex.DEFAULT_XI, step=0.5, key="o_xi")
    lam = c4.slider("λ (Objectosphere)", min_value=0.0, max_value=1.0, value=ex.DEFAULT_LAM, step=0.01, key="o_lam")
    target = c5.slider("Hedef bilinen kabul", min_value=0.80, max_value=0.99,
                       value=ex.DEFAULT_TARGET_KNOWN_ACCEPT, step=0.01, key="o_target")
    if st.button("Çalıştır", key="o_run", type="primary"):
        out = _run(
            "Açık küme deneyi çalışıyor…",
            lambda progress: ex.run_open_set(scale, int(seed), float(xi), float(lam), float(target), progress),
        )
        if out is not None:
            result, elapsed = out
            _store("open_set", {"ölçek": scale.name, "seed": int(seed), "ξ": xi, "λ": lam,
                                "hedef": target}, result, elapsed)
    entry = _stored("open_set")
    if entry:
        _show_open_set(entry)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.sidebar.title(PAGE_TITLE)
    stage = st.sidebar.radio("Aşama", STAGES, key="stage")
    max_threads = max(1, os.cpu_count() or 1)
    threads = st.sidebar.slider(
        "Torch iş parçacığı",
        min_value=1,
        max_value=max_threads,
        value=min(4, max_threads),
        key="threads",
        help="Başka süreçler çalışırken bunu düşürün: yük altında çok iş parçacığı yavaşlayabilir.",
    )
    torch.set_num_threads(int(threads))
    st.sidebar.caption(SYNTHETIC_NOTE)

    if stage == STAGE_1:
        render_stage_1()
    elif stage == STAGE_2:
        render_stage_2()
    elif stage == STAGE_3:
        render_stage_3()
    else:
        render_stage_4()


main()
