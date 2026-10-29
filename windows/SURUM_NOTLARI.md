# Sürüm Notları / Release Notes — Payload-Aware GEO Workbench (Windows)

## Türkçe

### İlk Windows paketi

Bu, deponun ilk Windows kurulum paketidir. Paket, yönetici hakkı gerektirmeden
iki **ayrı** yerel Streamlit uygulamasını kurar ve başlatır:

- **İz A — GEO Araştırma Panosu** (`dashboard/app.py`, port 8501, yedek
  8502–8510): yönetişimli araştırma panosu; yalnızca simülasyon/pilot verisi,
  üretim/GPU/ayrılmış değerlendirme kapıları kapalı, kıyaslama tamamlanmamış.
- **İz B — RF-ML Öğrenme Uygulaması** (`learning/rfml-basics/app.py`, port
  8511, yedek 8512–8520): kendi içinde kapalı, sentetik RF-ML öğrenme aracı.

### Paket içeriği

- `windows/KURULUM.bat` — çift tıklamalı kurulum girişi
- `windows/install.ps1` — kurulum (ön kontrol, iki sanal ortam, bağımlılıklar,
  içe aktarma testleri, kısayollar, günlük)
- `windows/launch_dashboard.bat`, `windows/launch_rfml.bat`,
  `windows/launch_app.ps1` — başlatıcılar (port seçimi, sağlık kontrolü,
  tarayıcı açma, PID/günlük dosyaları)
- `windows/stop_apps.bat`, `windows/stop_apps.ps1` — durdurma
- `windows/preflight.ps1` — bağımsız tanı
- `windows/BENIOKU.md` — Türkçe kılavuz
- `scripts/build_windows_package.py` — paketleme betiği
- Depo kaynak ağacı (dışlama listesi uygulanmış) ve `VERSION.json`

### Nerede test edildi

- Paketleme betiği (`scripts/build_windows_package.py`) Linux üzerinde
  çalıştırılarak doğrulandı (zip içeriği, dışlamalar, CRLF ve sha256
  öz-denetimleri).
- PowerShell betikleri sözdizimi ve mantık açısından masa başında incelendi;
  uçtan uca Windows doğrulaması CI üzerinde yapılır.
- CI doğrulama: Bu ZIP'i üreten "Windows package CI" Actions çalıştırması,
  gerçek `windows-latest` üzerinde pano testlerini, Track B testlerini ve iki
  uygulamanın 127.0.0.1 smoke başlat/durdur kontrolünü geçmeden artifact
  yüklemez; kanıt, artifact'ı indirdiğiniz çalıştırma sayfasının kendisidir.
  `VERSION.json` içindeki commit SHA'sı o çalıştırmanın commit'idir.

### Bilinen sınırlar

- Panonun `real-exercise` komutu yalnızca POSIX'tir; yerel Windows'ta açık
  bir mesajla reddedilir ve WSL2 gerektirir (bkz. `dashboard/README.md`).
- İlk başlatma yavaştır (antivirüs taraması, PyTorch'un ilk yüklenmesi).
- İsteğe bağlı `xgb` ekstrası kurulmaz (iki uygulama da kullanmaz).
- PR birleşene kadar paket, birleşmemiş bir özellik dalından üretilmiştir.
- Tek başına çalışan bir .exe yoktur; başlatıcılar komut dosyalarıdır.
- Bilimsel kapılar değişmedi: üretim/GPU/LOKO/ayrılmış değerlendirme kapalı,
  `benchmark_complete=false`; bu paket hiçbir onay üretmez.

---

## English

### First Windows package

This is the repository's first Windows installation package. It installs and
launches two **separate** local Streamlit apps without administrator rights:

- **Track A — GEO Research Dashboard** (`dashboard/app.py`, port 8501,
  fallbacks 8502–8510): the governed research dashboard; simulated/pilot data
  only, production/GPU/held-out gates closed, benchmark incomplete.
- **Track B — RF-ML Learning App** (`learning/rfml-basics/app.py`, port 8511,
  fallbacks 8512–8520): a self-contained synthetic RF-ML learning tool.

### Package contents

- `windows/KURULUM.bat` — double-click installer entry
- `windows/install.ps1` — installer (preflight, two virtual environments,
  dependencies, import smoke tests, shortcuts, logging)
- `windows/launch_dashboard.bat`, `windows/launch_rfml.bat`,
  `windows/launch_app.ps1` — launchers (port selection, health check, browser
  opening, PID/log files)
- `windows/stop_apps.bat`, `windows/stop_apps.ps1` — stopping
- `windows/preflight.ps1` — standalone diagnostics
- `windows/BENIOKU.md` — Turkish quick-start guide
- `scripts/build_windows_package.py` — packaging script
- The repository source tree (exclusion list applied) and `VERSION.json`

### Where it was tested

- The packaging script (`scripts/build_windows_package.py`) was validated on
  Linux (zip contents, exclusions, CRLF and sha256 self-checks).
- The PowerShell scripts were desk-checked for syntax and logic; end-to-end
  Windows validation runs in CI.
- CI verification: the "Windows package CI" Actions run that produced this
  ZIP only uploads the artifact after the dashboard tests, the Track B tests
  and the 127.0.0.1 smoke start/stop checks of both apps pass on a real
  `windows-latest` runner; the evidence is the run page you downloaded the
  artifact from. The commit SHA in `VERSION.json` identifies that run's
  commit.

### Known limitations

- The dashboard's `real-exercise` command is POSIX-only; on native Windows it
  is clearly refused and requires WSL2 (see `dashboard/README.md`).
- First launch is slow (antivirus scanning, first PyTorch import).
- The optional `xgb` extra is not installed (neither app uses it).
- Until the PR merges, the package is built from an unmerged feature branch.
- No standalone .exe exists; the launchers are script wrappers.
- Scientific gates are unchanged: production/GPU/LOKO/held-out evaluation
  stay closed, `benchmark_complete=false`; this package manufactures no
  approvals.
