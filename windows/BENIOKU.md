# Payload-Aware GEO Workbench — Windows Kurulum ve Kullanım Kılavuzu

Bu paket, GEO transponder girişim tanıma araştırma deposunun **yerel Windows
çalışma ortamıdır**. Yönetici hakkı gerektirmez; her şey kullanıcı hesabınız
altında kurulur. Paket **tek başına çalışan bir .exe içermez** — buradaki
başlatıcılar komut dosyalarıdır (.bat + PowerShell) ve uygulamalar yerel
Python sanal ortamlarında, tarayıcınızda çalışır.

## Paketin içinde ne var: iki AYRI uygulama

Bu paket iki ayrı izi kurar. **Bu iki iz asla karıştırılmamalıdır**: ayrı
sanal ortamları, ayrı başlatıcıları ve ayrı belgeleri vardır; aralarında
**hiçbir veri, model veya bilimsel iddia paylaşılmaz**.

| İz | Uygulama | Ne yapar |
|---|---|---|
| **İz A** | GEO Araştırma Panosu (`dashboard/app.py`) | Deponun **yönetişimli araştırma panosu**. Yalnızca simülasyon/pilot verisi gösterir; üretim, GPU ve ayrılmış (held-out) değerlendirme kapıları **kapalıdır**, kıyaslama (benchmark) **tamamlanmamıştır**. Pano hiçbir onay üretmez. |
| **İz B** | RF-ML Öğrenme Uygulaması (`learning/rfml-basics/app.py`) | Kendi içinde kapalı, **sentetik** RF makine öğrenmesi **öğrenme/alıştırma** uygulaması. Araştırma verisiyle veya İz A'nın sonuçlarıyla hiçbir bağı yoktur. |

## Sistem gereksinimleri (yerel yol)

- Windows 10 veya 11
- **Yönetici hakkı gerekmez** (her şey kullanıcı kapsamında kurulur)
- **GPU gerekmez** (her şey CPU üzerinde çalışır)
- **API anahtarı veya bulut hesabı gerekmez**
- Python 3.10–3.13 (3.12 tercih edilir; yoksa kurulum size yol gösterir)
- En az 5 GB boş disk (10 GB önerilir — PyTorch indirmesi büyüktür)
- 8 GB RAM önerilir
- Kurulum sırasında internet (pip paketleri için); çalıştırmak için gerekmez

İsteğe bağlı `xgb` ekstrası **kurulmaz**; iki uygulamanın da ona ihtiyacı yoktur.

## Kurulum

1. Paketi, **boşluk içermeyen ve OneDrive dışındaki** bir klasöre açın
   (ör. `C:\calisma\Payload-Aware-GEO-Workbench`).
2. `windows\KURULUM.bat` dosyasına **çift tıklayın**.
3. Ekrandaki `[OK] / [UYARI] / [HATA]` mesajlarını izleyin. Kurulum:
   - Python'u arar (yoksa python.org bağlantısı ve winget komutu önerir;
     winget ile kurulum **yalnızca siz açıkça onaylarsanız** yapılır),
   - depo kökünde `.venv-dashboard` ve `.venv-rfml` sanal ortamlarını kurar,
   - bağımlılıkları indirir (PyTorch CPU; ilk kurulum uzun sürebilir),
   - içe aktarma testleri yapar,
   - Masaüstü ve Başlat menüsü kısayollarını oluşturur.
4. Kurulum günlüğü: `windows\logs\install-<zaman>.log`.

Tanı için kurulumdan bağımsız olarak `windows\preflight.ps1` çalıştırılabilir
(PowerShell'de: `powershell -NoProfile -ExecutionPolicy Bypass -File windows\preflight.ps1`).

## Uygulamaları başlatma

- **GEO Araştırma Panosu**: Masaüstündeki "GEO Arastirma Panosu" kısayolu
  (veya `windows\launch_dashboard.bat`). Port 8501 (doluysa 8502–8510).
- **RF-ML Öğrenme Uygulaması**: "RF-ML Ogrenme Uygulamasi" kısayolu
  (veya `windows\launch_rfml.bat`). Port 8511 (doluysa 8512–8520).

Başlatıcı boş bir port seçer, Streamlit'i yalnızca `127.0.0.1` üzerinde
(bilgisayarınızın dışına kapalı) başlatır, sağlık kontrolünü bekler ve
tarayıcınızı açar. Uygulama zaten çalışıyorsa yeni kopya açılmaz; mevcut
adres tarayıcıda açılır.

## Çıktılar ve günlükler nerede?

- **Başlatıcı günlükleri ve PID dosyaları**: `windows\logs\`
  (`dashboard.log`, `rfml.log`, `*.err.log`, `*.pid`, `install-*.log`).
- **Panonun iş çıktıları ve arayüz durumu** depo **dışında** tutulur
  (`dashboard/geodash/paths.py` içindeki `run_home()` bunu zorlar). Yerel
  Windows'ta varsayılan yol:

  ```
  C:\Users\<kullanıcı_adınız>\.local\share\geo-dashboard
  ```

  Evet, bu Unix tarzı bir klasör adıdır; kod `Path.home()/".local"/"share"/"geo-dashboard"`
  kullandığı için Windows'ta da birebir bu yol oluşur. `GEO_DASHBOARD_HOME`
  ortam değişkeniyle başka bir yere taşıyabilirsiniz; seçtiğiniz yol depo
  içinde olamaz (kod bunu reddeder).
- RF-ML öğrenme uygulaması kendi klasörü (`learning/rfml-basics/`) içinde
  ders/deney dosyalarıyla çalışır.

## Durdurma

Başlat menüsündeki **"Uygulamalari Durdur"** kısayolu veya
`windows\stop_apps.bat`. PID dosyalarındaki süreç ağaçlarını kapatır ve eski
kayıtları temizler. Alternatif: uygulamanın tarayıcı sekmesini kapatmak
uygulamayı durdurmaz; durdurma için bu kısayolu kullanın.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| "Bos port yok" hatası | `stop_apps.bat` çalıştırın; ayrıca 8501–8520 portlarını kullanan başka uygulamaları kapatın. |
| "Uygun Python bulunamadi" | python.org'dan 3.12 kurun ("Add python.exe to PATH" işaretli) veya `winget install --id Python.Python.3.12 --scope user`; sonra `KURULUM.bat`'ı yeniden çalıştırın. |
| pip SSL/proxy hataları | Kurumsal ağdaysanız proxy/SSL denetimi pip'i engelleyebilir. BT biriminizden pip için proxy ayarlarını (`HTTPS_PROXY` ortam değişkeni, gerekirse kurum kök sertifikası) isteyin; ev ağında yeniden deneyin. |
| İlk açılış çok yavaş | Antivirüs, binlerce yeni Python dosyasını ilk açılışta tarar. Birkaç dakika bekleyin; mümkünse depo klasörünü antivirüs istisnalarına ekletin. |
| `UnicodeEncodeError: 'charmap' codec ...` (örn. Track B derslerini komut satırından çalıştırırken) | Windows'un eski cp1252 konsol kodlaması Türkçe karakterleri yazamıyor. Komuttan önce `set PYTHONUTF8=1` çalıştırın (PowerShell'de `$env:PYTHONUTF8='1'`). Kısayollardan başlatılan uygulamalar bunu zaten otomatik ayarlar. |
| torch indirmesi çok büyük/yarıda kesildi | PyTorch CPU paketi yüzlerce MB'dir. Kararlı bağlantıda `KURULUM.bat`'ı yeniden çalıştırın; pip kaldığı önbellekten devam eder. |
| Sağlık kontrolü zaman aşımı (90 sn) | `windows\logs\<uygulama>.log` ve `.err.log` dosyalarının son satırlarına bakın; çoğu zaman uygulama sadece yavaş açılıyordur — tarayıcıda adresi elle deneyin. |
| OneDrive / boşluklu yol sorunları | Depoyu OneDrive eşitlemesi dışında, boşluk içermeyen kısa bir yola taşıyın (ör. `C:\calisma\...`) ve kurulumu yeniden çalıştırın. OneDrive, sanal ortam dosyalarını kilitleyip bozabilir. |

## Önemli sınır: `real-exercise` komutu Windows'ta çalışmaz

Panonun `real-exercise` (gerçek-fizik tatbikat) çalıştırma komutu **yerel
Windows'ta çalışmaz ve açık bir mesajla reddedilir**. Komutun kullandığı
betik zinciri yalnızca POSIX sistemlerde bulunan `fcntl` kilit modülünü
kullanır (`scripts/b2_real_generation.py`, `b2_e16_ledger.py`,
`b2_e18_lifecycle.py`, `b2_production_supervisor.py`). Bu akışı kullanmak
istiyorsanız **WSL2 (Ubuntu)** gerekir; adımlar için `dashboard/README.md`
dosyasına bakın. Bu sınır bilimsel yönetişimin parçasıdır: üretim/GPU/LOKO
ve ayrılmış değerlendirme kapıları kapalıdır ve bu paket hiçbirini açmaz.

## Sürüm ve destek

Sürüm bilgisi paket kökündeki `VERSION.json` dosyasında ve
`windows\SURUM_NOTLARI.md` içindedir. Sorun bildirirken `VERSION.json`
içeriğini ve ilgili `windows\logs\` günlüğünü ekleyin. Bu paket araştırma
deposunun yardımcı aracıdır; bilimsel durum için deponun
`docs/plan/DURUM.md` dosyası esastır.
