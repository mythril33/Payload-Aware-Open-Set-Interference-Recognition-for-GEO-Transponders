# Sürüm Notları / Release Notes — Payload-Aware GEO Workbench (Windows)

## Türkçe

### Tek tıkla GEO Workbench (bu sürüm)

- Yeni kısayollar: **GEO Workbench**, **GEO Pilot Başlat**, **GEO İşlem
  Durdur**, **GEO Workbench Kapat**, **GEO WSL Kurulumu** (Masaüstü ve Başlat
  menüsü). Eski "GEO Arastirma Panosu" kısayolu **GEO Workbench** ile
  değiştirildi ve kurulumca kaldırılır. **RF-ML Ogrenme Uygulamasi** ve
  **Uygulamalari Durdur** değişmedi.
- Yeni dosyalar: `windows/geo_workbench.ps1` (open / pilot / stop-pilot /
  close / status), `windows/geo_common.ps1` (ortak yardımcılar),
  `windows/setup_wsl_backend.ps1` (onaylı, tek seferlik WSL2 kurulumu),
  `windows/GEO_*.bat` sarmalayıcıları, `windows/tests/geo_common_tests.ps1`
  (bağımlılıksız PowerShell yardımcı testleri).
- **GEO Pilot Başlat**, mevcut izinli `real-exercise` komutunu (rol başına 1
  grup, yalnız train/val-select/val-calib, CPU) WSL2 Ubuntu içinde, kalıcı bir
  denetçi süreciyle ve aynı JobManager üzerinden başlatır. İkinci tıklama ikinci
  pilot başlatmaz; mevcut iş kimliğini gösterir. İptal, sahiplik doğrulandıktan
  sonra yalnız workbench'in kendi işini durdurur; kayıtlar ve kısmi çıktılar
  korunur.
- WSL2 yoksa pano **yerel Windows inceleme modunda** açılır ve pilot açık bir
  Türkçe açıklamayla engellenir (çıkış kodu 2).
- `install.ps1`, Python zaten kuruluysa tamamen soru sormadan çalışır (CI bunu
  doğrular); `launch_app.ps1` ve `geo_workbench.ps1` CI için `-NoBrowser`
  anahtarı alır (varsayılan davranış değişmedi).
- Pilot bir **geliştirme pilotudur, benchmark değildir**: 21.350 gözlemlik
  benchmark, GPU, LOKO ve held-out kapıları kapalı kalır,
  `benchmark_complete=false`.

Nerede test edildi: betikler Linux'ta statik testlerle
(`tests/test_windows_oneclick_scripts.py`) ve Windows CI'de PowerShell 5.1 /
7 ayrıştırıcısı, yardımcı testleri ve WSL'siz (güvenli reddetme) yol ile
denetlenir. GitHub `windows-latest` gerçek WSL2 sanallaştırmasını doğrulayamaz;
gerçek WSL2 uçtan uca pilot doğrulaması fiziksel bir Windows bilgisayarda ayrıca
yapılmalı ve kaydedilmelidir.

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

### One-click GEO Workbench (this release)

- New shortcuts: **GEO Workbench**, **GEO Pilot Başlat**, **GEO İşlem
  Durdur**, **GEO Workbench Kapat**, **GEO WSL Kurulumu** (Desktop and Start
  menu). The old "GEO Arastirma Panosu" shortcut is superseded by **GEO
  Workbench** and removed by the installer. **RF-ML Ogrenme Uygulamasi** and
  **Uygulamalari Durdur** are unchanged.
- New files: `windows/geo_workbench.ps1` (open / pilot / stop-pilot / close /
  status), `windows/geo_common.ps1` (shared helpers),
  `windows/setup_wsl_backend.ps1` (consent-gated one-time WSL2 setup), the
  `windows/GEO_*.bat` wrappers and `windows/tests/geo_common_tests.ps1`
  (dependency-free PowerShell helper tests).
- **GEO Pilot Başlat** starts the existing allowlisted `real-exercise` command
  (one group per role, train/val-select/val-calib only, CPU) inside WSL2 Ubuntu
  under a persistent supervisor through the same JobManager. A second click
  never starts a second pilot; it shows the running job id. Cancellation stops
  only the workbench-owned job after an ownership check; records and partial
  outputs are kept.
- Without WSL2 the dashboard opens in **native Windows inspection mode** and
  the pilot is refused with a clear Turkish explanation (exit code 2).
- `install.ps1` runs fully non-interactively when Python is already present
  (CI checks this); `launch_app.ps1` and `geo_workbench.ps1` take a
  `-NoBrowser` switch for CI (default behaviour unchanged).
- The pilot is a **development pilot, not the benchmark**: the
  21,350-observation benchmark, GPU, LOKO and held-out gates stay closed,
  `benchmark_complete=false`.

Where it was tested: the scripts are checked statically on Linux
(`tests/test_windows_oneclick_scripts.py`) and, in Windows CI, by the
PowerShell 5.1 / 7 parsers, the helper tests and the WSL-absent fail-closed
path. GitHub `windows-latest` cannot validate real WSL2 virtualization; a true
WSL2 end-to-end pilot validation must be done and recorded separately on a
physical Windows PC.

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
