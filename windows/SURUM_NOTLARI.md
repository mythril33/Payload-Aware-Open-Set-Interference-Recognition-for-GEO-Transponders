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
- **WSL kaynağı artık gerçek bir Git kopyasıdır.** Paket kökünde
  `geo-source.bundle` bulunur: paketlenen commit'in `git bundle create ...
  HEAD` ile üretilmiş **tam Git geçmişi** (sığ depodan paket üretilmez).
  Bu yüzden ZIP, deponun tüm commit geçmişini taşır ve **depo kadar gizlidir**.
  `VERSION.json` buna `source_bundle`, `source_bundle_sha256` ve
  `source_bundle_head` alanlarını ekler. **GEO WSL Kurulumu** paketi
  `geo_wsl_setup.py install-git` ile `~/geo-workbench-src` içine klonlar ve
  `HEAD`, sığ olmama, `git fsck` ve temiz çalışma ağacını doğrular. Gerekçe:
  eğitim, kontrol noktası kaynağı olarak `git rev-parse HEAD` kaydeder; bir
  anlık görüntü kopyası bunu sağlayamaz (pilot böyle bir kaynakta kod 25 ile
  durur).
- WSL içinde `git` gerekir; yoksa kurulum onayınızla görünür bir pencerede
  `sudo apt-get install -y git` çalıştırır ve bir kez yeniden dener (kod 17).
- Kurulum, varsayılan Linux kullanıcısı root (uid 0) ise durur: Ubuntu'nun ilk
  açılışında Linux kullanıcısını oluşturun. `wsl_backend.json` artık
  `linux_user`, `uid` ve `source_mode: git` alanlarını kaydeder (eski kayıtlar
  geçersiz sayılır; kurulumu yeniden çalıştırın). `wsl --install` yalnız 0 veya
  3010 koduyla biterse "başlatıldı" sayılır; Ubuntu penceresi hesap
  oluşturulduktan sonra kapatılmalı (`exit`).
- Eski kopya kenara taşınmadan önce, o kopyadan çalışan bir WSL pano arayüzü
  onayınızla kapatılır (onay yoksa kopya değiştirilmez).
- **Eşleşmezlik:** `wsl_backend.json` commit'i paketin `VERSION.json` commit'iyle
  eşleşmezse **GEO Workbench** yerel inceleme moduna düşer ve **GEO Pilot
  Başlat** başlamaz (ikisi de kod 20); durdurma ve kapatma yine çalışır.
  `VERSION.json` yoksa (geliştirici modu) kurulumda kaydedilen commit beklenir.
  Pano `serve --expect-commit` ile başlatılır; panodaki pilot düğmesi ve
  denetçi aynı beklentiyi denetler; başka bir commit için çalışan arayüz yeniden
  kullanılmaz.
- Yeni çıkış kodları: 17 (git yok), 18 (pilot olmayan başka bir iş çalışıyor),
  19 (okunamayan iş kaydı yeni işleri engeller), 25 (kaynak Git kopyası değil),
  42 (arayüz 30 sn içinde kapanmadı); 8 artık root kullanıcıyı da kapsar.
  Bir iş çalışırken ön kontrol her zaman `JOB_ID` gösterir.
- `wsl -l -v` ayrıştırması birden çok kelimeli yerelleştirilmiş durumları
  (ör. "Wird ausgefuehrt") doğru okur; PID kayıt dosyası yazılamazsa yalnız
  uyarı verilir, başlatılmış pilot veya arayüzün sonucu değişmez.

Nerede test edildi: betikler Linux'ta statik testlerle
(`tests/test_windows_oneclick_scripts.py`) ve Windows CI'de PowerShell 5.1 /
7 ayrıştırıcısı, yardımcı testleri, WSL'siz (güvenli reddetme) yol ve sahte
bir `wsl.exe` (`windows/tests/fake_wsl.cmd`, `tests/test_windows_oneclick_fakewsl.py`:
ön kontrol 10/20/23, tek `run` çağrısı, iptal 41, kapatma reddi 5, commit
eşleşmezliği 20) ile denetlenir. GitHub `windows-latest` gerçek WSL2 sanallaştırmasını doğrulayamaz;
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
- **The WSL source is now a genuine Git checkout.** The package root carries
  `geo-source.bundle`, the packaged commit's **full Git history** made with
  `git bundle create ... HEAD` (a shallow repository is refused). The ZIP
  therefore contains the repository's whole commit history and is **as private
  as the repository itself**. `VERSION.json` adds `source_bundle`,
  `source_bundle_sha256` and `source_bundle_head`. **GEO WSL Kurulumu** clones
  it into `~/geo-workbench-src` with `geo_wsl_setup.py install-git` and checks
  `HEAD`, non-shallowness, `git fsck` and a clean work tree. Reason: training
  records `git rev-parse HEAD` as checkpoint provenance, which a snapshot copy
  cannot provide (the pilot stops on such a source with code 25).
- `git` is required inside WSL; when it is missing, setup runs
  `sudo apt-get install -y git` in a visible window with consent and retries
  once (code 17).
- Setup refuses a root (uid 0) default Linux user: create the Linux user on
  Ubuntu's first launch. `wsl_backend.json` now records `linux_user`, `uid` and
  `source_mode: git` (older records are treated as invalid; rerun setup).
  `wsl --install` counts as started only on exit code 0 or 3010; close the
  Ubuntu window (`exit`) after creating the account.
- Before an old copy is moved aside, a WSL dashboard served from it is stopped
  with consent (without consent the copy is left unchanged).
- **Mismatch:** when the `wsl_backend.json` commit differs from the package's
  `VERSION.json` commit, **GEO Workbench** falls back to native inspection and
  **GEO Pilot Başlat** does not start (both code 20); stop and close still
  work. Without `VERSION.json` (developer mode) the commit recorded by setup is
  expected. The dashboard is served with `serve --expect-commit`; the in-app
  pilot button and the supervisor check the same expectation, and a UI served
  for another commit is not reused.
- New exit codes: 17 (git missing), 18 (another, non-pilot job is running),
  19 (an unreadable job record blocks new jobs), 25 (source is not a Git
  checkout), 42 (the UI did not stop within 30 s); 8 now also covers a root
  user. Preflight always prints `JOB_ID` while a job runs.
- `wsl -l -v` parsing handles multi-word localized states (e.g. "Wird
  ausgefuehrt"); a pid file that cannot be written only warns and never
  changes the outcome of a pilot or UI that already started.

Where it was tested: the scripts are checked statically on Linux
(`tests/test_windows_oneclick_scripts.py`) and, in Windows CI, by the
PowerShell 5.1 / 7 parsers, the helper tests, the WSL-absent fail-closed path
and a scripted `wsl.exe` (`windows/tests/fake_wsl.cmd`,
`tests/test_windows_oneclick_fakewsl.py`: preflight 10/20/23, exactly one `run`
call, cancel 41, declined close 5, commit mismatch 20). GitHub `windows-latest` cannot validate real WSL2 virtualization; a true
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
