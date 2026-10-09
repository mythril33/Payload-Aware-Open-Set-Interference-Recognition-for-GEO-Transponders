# P4-A — Simülatör mimarisi ve doğrulama (Kademe A)

Durum: **KAPANDI** (girişimci üreteçleri hariç; onlar P3-A'da) · 2026-10-09 · Girdi: `P2_sistem_modeli.md`

## 1. Depo yapısı

| Yol | İçerik |
|---|---|
| `src/geosim/waveform.py` | Takımyıldızlar, SRRC, tek taşıyıcı üretimi |
| `src/geosim/plan.py` | Rastgele taşıyıcı planı, plan maskesi |
| `src/geosim/payload.py` | IMUX, sabit kazanç, Saleh TWTA, doğrusal karşılık, OMUX |
| `src/geosim/sensor.py` | Gürültü, 96 MHz'e seyreltme, Welch spektrogramı |
| `src/geosim/scenario.py` | Uçtan uca tek senaryo: `simulate(ScenarioConfig)` |
| `tests/test_chain.py` | T1–T12 doğrulama testleri |
| `scripts/plot_linear_vs_twta.py` | Doğrusal ve TWTA zincirinin spektrum karşılaştırması |

Kurulum ve çalıştırma: `pip install -e .[dev]` · `pytest` · `python scripts/plot_linear_vs_twta.py`

## 2. Arayüz

```python
from geosim.scenario import ScenarioConfig, simulate
r = simulate(ScenarioConfig(bandwidth=36e6, ibo_db=6, cn_up_db=25, cn_dn_db=20, linear=False, seed=0))
r.spec_db   # (128, 512) float32
r.mask_db   # (512,) float32
r.meta      # konfigürasyon, taşıyıcı planı, gerçekleşen IBO ve OBO
```

- `linear=True` aynı senaryoyu TWTA yerine küçük sinyal kazancıyla çalıştırır (payload-gap deneyinin karşılaştırma kolu).
- `interferer=` bir çağrılabilir alır: `(rng, t0, n, fs) -> (n_snap, n)` karmaşık uplink örnekleri. Taşıyıcıların toplam uplink gücü 1 olduğundan girişimci gücü doğrudan 1/(C/I)'dır. P3-A bu kancayı doldurur.
- Tohumdan beş bağımsız rastgele akış türetilir (plan, taşıyıcılar, uplink gürültüsü, downlink gürültüsü, girişimci). Girişimci eklemek temiz senaryonun taşıyıcılarını ve gürültüsünü değiştirmez; böylece "aynı senaryo, girişimli ve girişimsiz" çiftleri üretilebilir.

## 3. Doğrulama sonucu

31 test geçti (T1–T12, süzgeç seçiciliği ve maske–spektrum uyumu). Ölçülen değerler:

| Test | Ölçüt | Ölçülen |
|---|---|---|
| T2 EVM | ≤ %1 | %0,10–0,14 |
| T8 IM3 eğimi (IBO 30→35 dB) | 2 ± 0,05 dB/dB | 1,98 |
| T10 örtüşme (IBO 3 dB) | ≤ 0,1 dB | geçti, 36 ve 72 MHz |
| Senaryo süresi | — | 1,9 s (36 MHz), 2,6 s (72 MHz), bulut makinesi, tek çekirdek |

Şartnameden sapmalar `P2_sistem_modeli.md` §10'da.

## 4. İlk gözlem

`docs/figures/psd_linear_vs_twta.png`: 6 taşıyıcılı 36 MHz planı, IBO 3 dB, C/N 40 dB. Taşıyıcı aralarındaki seviye doğrusal zincirde tepeye göre −39,9 dB, TWTA zincirinde −18,9 dB. Tek bir plan ve tek bir çalışma noktasıdır; genelleme değildir.

## 5. Açık konular

- PL çerçevesi anahtarı henüz yok (çerçevesiz sürüm doğrulandı).
- Dizüstünde süre ölçülmedi.
- Rastgele planın doluluğu hedefin biraz altına inebiliyor (2000 planda en düşük %45).
