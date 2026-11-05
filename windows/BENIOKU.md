# Payload-Aware GEO Workbench — Windows Kurulum ve Kullanım Kılavuzu

Bu paket, GEO transponder girişim tanıma araştırma deposunun **yerel Windows
çalışma ortamıdır**. Temel kurulum yönetici hakkı gerektirmez; her şey kullanıcı
hesabınız altında kurulur (yalnız isteğe bağlı WSL2 özelliğini ilk kez
etkinleştirmek, sizin onayınızla, bir kez yönetici onayı ister). Paket **tek başına çalışan bir .exe içermez** — buradaki
başlatıcılar komut dosyalarıdır (.bat + PowerShell) ve uygulamalar yerel
Python sanal ortamlarında, tarayıcınızda çalışır.

## Paketin içinde ne var: iki AYRI uygulama

Bu paket iki ayrı izi kurar. **Bu iki iz asla karıştırılmamalıdır**: ayrı
sanal ortamları, ayrı başlatıcıları ve ayrı belgeleri vardır; aralarında
**hiçbir veri, model veya bilimsel iddia paylaşılmaz**.

| İz | Uygulama | Ne yapar |
|---|---|---|
| **İz A** | GEO Workbench / GEO Araştırma Panosu (`dashboard/app.py`) | Deponun **yönetişimli araştırma panosu**. Yalnızca simülasyon/pilot verisi gösterir; üretim, GPU ve ayrılmış (held-out) değerlendirme kapıları **kapalıdır**, kıyaslama (benchmark) **tamamlanmamıştır**. Pano hiçbir onay üretmez. |
| **İz B** | RF-ML Öğrenme Uygulaması (`learning/rfml-basics/app.py`) | Kendi içinde kapalı, **sentetik** RF makine öğrenmesi **öğrenme/alıştırma** uygulaması. Araştırma verisiyle veya İz A'nın sonuçlarıyla hiçbir bağı yoktur. |

## Sistem gereksinimleri (yerel yol)

- Windows 10 veya 11
- **Yönetici hakkı gerekmez** (her şey kullanıcı kapsamında kurulur; isteğe
  bağlı WSL2 kurulumu hariç)
- **GPU gerekmez** (her şey CPU üzerinde çalışır)
- **API anahtarı veya bulut hesabı gerekmez**
- Python 3.10–3.13 (3.12 tercih edilir; yoksa kurulum size yol gösterir)
- En az 5 GB boş disk (10 GB önerilir — PyTorch indirmesi büyüktür)
- 8 GB RAM önerilir
- Kurulum sırasında internet (pip paketleri için); çalıştırmak için gerekmez
- Gerçek RF pilotu için ayrıca: WSL2 + Ubuntu (Windows 10 sürüm 2004 / derleme
  19041 veya üzeri, ya da Windows 11), Ubuntu içinde root olmayan bir Linux
  kullanıcısı, `python3 >= 3.10`, `git` (yoksa kurulum onayınızla kurar) ve WSL
  içinde yaklaşık 5 GB boş alan

İsteğe bağlı `xgb` ekstrası **kurulmaz**; iki uygulamanın da ona ihtiyacı yoktur.

## Kurulum

1. Paketi tercihen **OneDrive dışındaki** kısa bir klasöre açın
   (ör. `C:\calisma\Payload-Aware-GEO-Workbench`). Boşluklu veya Türkçe
   karakterli yollar desteklenir.
2. `windows\KURULUM.bat` dosyasına **çift tıklayın**.
3. Ekrandaki `[OK] / [UYARI] / [HATA]` mesajlarını izleyin. Python zaten
   kuruluysa kurulum hiç soru sormadan çalışır. Kurulum:
   - Python'u arar (yoksa python.org bağlantısı ve winget komutu önerir;
     winget ile kurulum **yalnızca siz açıkça onaylarsanız** yapılır),
   - depo kökünde `.venv-dashboard` ve `.venv-rfml` sanal ortamlarını kurar,
   - bağımlılıkları indirir (PyTorch CPU; ilk kurulum uzun sürebilir),
   - içe aktarma testleri yapar,
   - Masaüstü ve Başlat menüsü kısayollarını oluşturur.
4. Kurulum günlüğü: `windows\logs\install-<zaman>.log`.
5. Gerçek RF pilotunu da kullanacaksanız ayrıca bir kez **GEO WSL Kurulumu**
   kısayolunu çalıştırın (aşağıya bakın). Bu adım isteğe bağlıdır; atlanırsa
   pano yerel Windows inceleme modunda çalışır.

Tanı için kurulumdan bağımsız olarak `windows\preflight.ps1` çalıştırılabilir
(PowerShell'de: `powershell -NoProfile -ExecutionPolicy Bypass -File windows\preflight.ps1`).

## Kısayollar

Kurulum, Masaüstüne ve Başlat menüsüne (`Payload-Aware GEO Workbench` klasörü)
aşağıdaki kısayolları koyar. Hepsi `windows\` klasöründeki küçük `.bat`
dosyalarını çalıştırır; `.bat` dosyaları PowerShell'i yalnızca o işlem için
`-ExecutionPolicy Bypass` ile çağırır (sistem ayarı değiştirilmez).

| Kısayol | Dosya | Ne yapar |
|---|---|---|
| **GEO Workbench** | `GEO_Workbench.bat` | İz A panosunu açar veya zaten açıksa aynı kopyayı yeniden kullanır. WSL2 arka ucu kuruluysa pano **WSL2 Ubuntu içinde** çalışır; kurulu değilse **yerel Windows inceleme modu** açılır. |
| **GEO Pilot Başlat** | `GEO_Pilot_Baslat.bat` | Ön kontrolden sonra **sınırlı geliştirme pilotunu** (`real-exercise`, rol başına 1 grup, yalnız train/val-select/val-calib, CPU) WSL2 içinde başlatır ve panoyu açar. Bir pilot zaten çalışıyorsa ikinci pilot başlatılmaz; mevcut iş kimliği (JOB_ID) gösterilir. |
| **GEO İşlem Durdur** | `GEO_Islem_Durdur.bat` | Çalışan pilotu güvenli biçimde iptal eder: yalnız workbench'in kendi işini, sahiplik (PID + başlangıç belirteci) doğrulandıktan sonra durdurur. Kısmi çıktılar ve günlük korunur; iptal edilen iş **başarılı sayılmaz**. |
| **GEO Workbench Kapat** | `GEO_Workbench_Kapat.bat` | Pano arayüzünü kapatır. Bir pilot çalışıyorsa önce uyarır ve onay ister; arayüz kapansa bile pilot WSL içinde sürer ve sonucu kaydedilir. Hiçbir kayıt veya çıktı silinmez. |
| **GEO WSL Kurulumu** | `GEO_WSL_Kurulumu.bat` | Gerçek RF pilotu için **tek seferlik, onaylı** WSL2 kurulumu (aşağıya bakın). |
| **RF-ML Ogrenme Uygulamasi** | `launch_rfml.bat` | İz B öğrenme uygulaması (port 8511, doluysa 8512–8520). Değişmedi; İz A'dan tamamen bağımsızdır. |
| **Uygulamalari Durdur** (yalnız Başlat menüsü) | `stop_apps.bat` | Yerel olarak başlatılmış iki uygulamayı (yerel pano ve İz B) durdurur. WSL2 içindeki pilota dokunmaz. |

Eski "GEO Arastirma Panosu" kısayolu artık **GEO Workbench** ile değiştirilmiştir;
kurulum, bu pakete ait eski kısayolu kendiliğinden kaldırır.
`windows\launch_dashboard.bat` yerel panoyu doğrudan açmak için hâlâ kullanılabilir.

## Pilot, benchmark değildir

**GEO Pilot Başlat**, sınırlı bir geliştirme alıştırmasıdır: gerçek fizik
zincirini (RF üretimi → eğitim → val-calib → dondurma → rapor) küçük ölçekte
uçtan uca çalıştırır ve `exercise.json` ile **işlevsel akışın** çalıştığını
kanıtlar. Bu pilot **benchmark değildir**: tanıma performansı sonucu üretmez,
21.350 gözlemlik benchmark'ı çalıştırmaz, held-out (ayrılmış test) verisine
erişmez, GPU kullanmaz ve hiçbir üretim kapısını açmaz
(`benchmark_complete=false`). Panodaki geçen süre / zaman aşımı çubuğu yalnız
**zamanı** ölçer, işin tamamlanma yüzdesi değildir.

## Gerçek RF pilotu için WSL2 kurulumu (GEO WSL Kurulumu)

Pilotun yönetişimli betik zinciri yalnızca POSIX sistemlerde bulunan `fcntl`
kilitlerini kullanır; bu yüzden pilot **yerel Windows'ta çalışmaz** ve **WSL2
Ubuntu** gerektirir. Kurulum bir kez yapılır ve her adımda ne yapılacağını
anlatır; hiçbir şey sizin `[E/H]` onayınız olmadan kurulmaz.

1. Paketi açtığınız klasörde **GEO WSL Kurulumu** kısayoluna çift tıklayın ve
   açıklamayı okuyup `E` ile onaylayın.
2. Paket denetlenir: kurulum yalnız CI tarafından üretilen ZIP paketinden
   yapılabilir. `VERSION.json` içindeki commit ile paket kökündeki
   `geo-source.bundle` dosyasının sha256 özeti ve başı (`source_bundle_head`)
   karşılaştırılır; tutarsızlıkta kurulum durur (kod 9).
3. `wsl.exe` ve bir Ubuntu dağıtımı aranır. Yoksa `wsl --install -d Ubuntu-24.04`
   **ayrıca onayınızla** başlatılır. WSL özelliği henüz etkin değilse Windows bir
   **yönetici onayı (UAC)** penceresi gösterir ve bilgisayarı yeniden başlatmanız
   gerekebilir. Yalnız `wsl --install` çıkış kodu 0 veya 3010 (yeniden başlatma
   gerekli) ise kurulum "başlatıldı" sayılır (kod 7); başka her kod bir hata
   olarak bildirilir (kod 1).
   **Linux kullanıcısı:** Ubuntu ilk açılışta sizden bir Linux kullanıcı adı ve
   parola oluşturmanızı ister. Hesabı oluşturduktan sonra o pencere bir Ubuntu
   komut satırında bekler: pencereyi kapatın veya `exit` yazıp Enter'a basın;
   kurulum penceresi ancak o zaman devam eder. Sonra **GEO WSL Kurulumu**
   kısayolunu yeniden çalıştırın.
4. Dağıtımın WSL2 olduğu (WSL1 ise `wsl --set-version <dağıtım> 2` önerilir),
   `python3 >= 3.10` bulunduğu ve varsayılan Linux kullanıcısının **root
   olmadığı** denetlenir. Dağıtım root (uid 0) olarak açılıyorsa (ilk açılıştaki
   kullanıcı oluşturma atlanmışsa) kurulum durur (kod 8): Başlat menüsünden
   Ubuntu'yu bir kez açıp Linux kullanıcınızı oluşturun, sonra kurulumu yeniden
   çalıştırın.
5. Kaynak, paketteki **Git paketinden** (`geo-source.bundle`) WSL ext4 ev
   dizinine, `~/geo-workbench-src` klasörüne **gerçek bir Git kopyası** olarak
   klonlanır (`/mnt/c` altına değil; `geo_wsl_setup.py install-git`). Klon önce
   bir geçici klasörde doğrulanır: `HEAD` paketin commit'i, sığ (shallow) değil,
   `git fsck --connectivity-only` temiz ve çalışma ağacı temiz olmalıdır;
   doğrulanamayan geçici klon silinmez, incelenmek üzere bırakılır (kod 20).
   Eğitim, kontrol noktası kaynağı olarak `git rev-parse HEAD` kaydettiği için
   pilot yalnız gerçek bir Git kopyasından çalışır. Ubuntu'da `git` yoksa (kod
   17), onayınızla görünür bir pencerede `sudo apt-get install -y git`
   çalıştırılır (Ubuntu kendi parolanızı sorabilir) ve klonlama **bir kez**
   yeniden denenir.
6. Farklı bir commit'e ait (veya Git kopyası olmayan) eski bir kopya varsa:
   eski kopyada bir pilot çalışıyorsa kurulum durur; eski kopyadan çalışan bir
   WSL pano arayüzü varsa önce **onayınızla** kapatılır (onay verilmezse kopya
   değiştirilmez); sonra **ikinci bir onayla** eski kopya
   `~/geo-workbench-src.previous-<zaman>` adıyla kenara taşınır; **asla
   silinmez**. Aynı commit'e ait bir Git kopyası varsa yeniden kullanılır.
7. `~/geo-workbench-src/.venv` sanal ortamı kurulur (PyTorch CPU dahil; birkaç
   GB indirme, uzun sürebilir). Ubuntu'da `python3-venv` eksikse, onayınızla
   görünür bir pencerede `sudo apt-get install -y python3-venv` çalıştırılır.
8. Pilot ön kontrolü bu paketin commit'iyle (`--expect-commit`) çalıştırılır.
   Yalnızca başarılı olursa kurulum kaydı yazılır:
   `%LOCALAPPDATA%\GEO-Workbench\wsl_backend.json` (dağıtım, kaynak klasörü,
   commit, `source_mode: git`, `linux_user` ve `uid` alanlarıyla).

### Git paketi (geo-source.bundle) hakkında

`geo-source.bundle`, paketlenen commit'in `git bundle create ... HEAD` ile
üretilmiş **tam Git geçmişini** taşır (sığ bir depodan paket üretilmez). Bu
nedenle ZIP, deponun **tüm commit geçmişini** içerir ve **depo kadar gizlidir**:
yalnız depoya erişimi olan kişilerle paylaşın. Geçmiş, WSL içindeki kopyanın
gerçek bir Git kopyası olması (sahte geçmiş yok, kimlik bilgisi gerekmez) ve
eğitimin doğru commit kimliğini kaydetmesi için gereklidir.

### Paket ile WSL kopyası eşleşmiyorsa

Her **GEO Workbench** ve **GEO Pilot Başlat** çalıştırmasında
`wsl_backend.json` içindeki commit, bu paketin `VERSION.json` commit'iyle
karşılaştırılır (`VERSION.json` yoksa, yani betikler bir Git klonundan
çalıştırılıyorsa, kurulumda kaydedilen commit beklenir):

- Eşleşmezse (ör. yeni bir ZIP açtınız ama **GEO WSL Kurulumu**'nu yeniden
  çalıştırmadınız) **GEO Workbench** WSL panosunu açmaz, yerel inceleme modunu
  açar ve kod 20 ile **GEO WSL Kurulumu**'nu yeniden çalıştırmanızı ister;
  **GEO Pilot Başlat** pilotu başlatmaz (kod 20).
- **GEO İşlem Durdur**, **GEO Workbench Kapat** ve durum komutu eşleşmezlikte de
  çalışır, böylece eski kopyadaki pilot veya arayüz her zaman durdurulabilir.
- WSL panosu, beklenen commit ile (`serve --expect-commit`) başlatılır; panodaki
  **GEO PİLOT BAŞLAT** düğmesi de aynı beklentiyle ön kontrol yapar. Çalışan bir
  arayüz başka bir commit için başlatılmışsa yeniden kullanılmaz (kod 20);
  önce **GEO Workbench Kapat** ile kapatın.

Güncelleme her zaman bu ayrı, açık adımdır; pilot öncesinde örtük bir
güncelleme yapılmaz. Bu denetim bir üretim kilidi değildir.

## Yerel Windows inceleme modu (WSL2 yoksa)

WSL2 kurulmamışsa **GEO Workbench** panoyu yerel Windows'ta
(`.venv-dashboard`, port 8501, doluysa 8502–8510) **inceleme modunda** açar:
tüm sayfalar ve salt-okur komutlar (`preflight-gates`, `host-inventory`,
`test-dashboard`, `test-cpu-execution`) çalışır, ancak gerçek RF pilotu açık bir
gerekçeyle devre dışıdır ve **GEO WSL Kurulumu** kısayoluna yönlendirir.
**GEO Pilot Başlat** bu durumda pilotu başlatmaz, açıklamayı gösterir ve
inceleme modundaki panoyu açar. Bu bir güvenli geri dönüştür; gizli bir üretim
yolu değildir.

## WSL2 ile kullanım

- WSL2 panosu `127.0.0.1` üzerinde 8531 portunda (doluysa 8532–8540) çalışır;
  WSL2'nin localhost yönlendirmesi sayesinde Windows tarayıcınızdan açılır.
  Dışarıya açık bir dinleyici veya güvenlik duvarı kuralı eklenmez.
- **GEO Workbench** ikinci kez tıklandığında yeni kopya açılmaz; çalışan
  kopyanın adresi tarayıcıda açılır.
- Pano içinde de **GEO PİLOT BAŞLAT / DURUMU YENİLE / GÜVENLİ İPTAL**
  düğmeleri, aşama zinciri, geçen süre, çıktı klasörü, `exercise.json` ve
  `pilot.json` indirmeleri ile günlük bulunur.
- Tarayıcı sekmesini kapatmak pilotu durdurmaz; durum panodan veya
  **GEO Workbench** ile yeniden görülebilir.

## Çıktılar ve günlükler nerede?

- **Windows tarafı günlükleri**: `windows\logs\` klasörü.
  - `geo_workbench.log`: tüm GEO kısayollarının (açma, pilot, durdurma, kapatma,
    WSL kurulumu) ayrıntılı günlüğü.
  - `geo_ui.pid` (WSL2 panosu), `geo_pilot.pid` (son başlatılan pilot
    denetçisi; yalnız bilgi amaçlıdır, hiçbir süreç bu dosyaya bakılarak
    sonlandırılmaz).
  - `dashboard.log`, `rfml.log`, `*.err.log`, `*.pid`, `install-*.log`
    (yerel uygulamalar ve kurulum).
- **WSL2 pilotu çıktıları** depo kopyasının **dışında**, WSL içinde:
  `~/.local/share/geo-dashboard` (`jobs/<JOB_ID>/` altında `job.json`,
  `log.txt`, `pilot.json`, `exercise/exercise.json`; pano ve denetçi günlükleri
  `workbench/` altında). Windows Gezgini'nden `\\wsl$\<dağıtım>\home\<kullanıcı>\.local\share\geo-dashboard`
  yoluyla da açılabilir.
- **Yerel pano çıktıları**, yine depo **dışında**:

  ```
  C:\Users\<kullanıcı_adınız>\.local\share\geo-dashboard
  ```

  Evet, bu Unix tarzı bir klasör adıdır; kod `Path.home()/".local"/"share"/"geo-dashboard"`
  kullandığı için Windows'ta da birebir bu yol oluşur. `GEO_DASHBOARD_HOME`
  ortam değişkeniyle başka bir yere taşıyabilirsiniz; seçtiğiniz yol depo
  içinde olamaz (kod bunu reddeder).
- RF-ML öğrenme uygulaması kendi klasörü (`learning/rfml-basics/`) içinde
  ders/deney dosyalarıyla çalışır.

## Çıkış kodları

Kısayol penceresi yalnızca bir sorun olduğunda açık kalır ve Türkçe açıklamayı
gösterir. En sık kodlar:

| Kod | Anlamı |
|---|---|
| 0 | Başarılı (pilot için: pilot başlatıldı) |
| 1 | Beklenmeyen hata; ayrıca `wsl --install` 0/3010 dışında bir kodla bitti (Ubuntu kurulmadı) |
| 2 | WSL2 arka ucu kurulmamış; **GEO WSL Kurulumu** çalıştırın (pano inceleme modunda açılır) |
| 3 | WSL/Ubuntu veya WSL içindeki kopya bulunamadı; durdurma için: çalışan pilot yok |
| 4 | Pano 90 saniyede sağlık kontrolüne yanıt vermedi |
| 5 | İşlem onaylanmadı (ör. pilot çalışırken kapatma reddedildi) |
| 6 | Pilot denetçisi başladı ama iş kimliği 60 saniyede görülmedi |
| 7 | WSL/Ubuntu kurulumu başlatıldı (`wsl --install` kodu 0 veya 3010); bitince (gerekirse yeniden başlatıp) kurulumu tekrar çalıştırın |
| 8 | Dağıtım uygun değil (WSL1, python3 < 3.10 veya varsayılan Linux kullanıcısı root) |
| 9 | Paket dosyaları eksik veya tutarsız (`VERSION.json`, `geo-source.bundle`; yalnız CI ZIP paketi kullanılabilir) |
| 10 | Bir pilot zaten çalışıyor; mevcut JOB_ID gösterilir |
| 11 / 12 | Pano zaten çalışıyor / port dolu |
| 13 / 14 / 15 / 16 | WSL kopyası zaten var / hedef `/mnt` altında / `python3-venv` eksik / pip hatası |
| 17 | WSL içinde `git` yok (kurulum onayınızla `sudo apt-get install -y git` çalıştırıp bir kez yeniden dener) |
| 18 | Pilot olmayan başka bir GEO işi çalışıyor; JOB_ID ve komutu gösterilir, yeni pilot başlatılmaz |
| 19 | Bir iş kaydı (`job.json`) okunamıyor; adı verilen klasör kenara taşınana kadar yeni iş başlatılmaz |
| 20 | Kaynak kimliği doğrulanamadı: WSL kopyası bu paketin commit'iyle eşleşmiyor (`wsl_backend.json` ≠ `VERSION.json`), değiştirilmiş veya Git klonu doğrulanamadı |
| 21 / 22 / 23 / 24 | Platform POSIX değil / bağımlılık eksik / disk yetersiz (en az 5 GiB) / grup sayısı reddedildi (yalnız 1 veya 2) |
| 25 | WSL kaynağı doğrulanmış ama bir Git kopyası değil (eski anlık görüntü kurulumu); **GEO WSL Kurulumu**'nu yeniden çalıştırın |
| 30 / 31 / 32 | Pilot başarısız / iptal edildi / zaman aşımı (hiçbiri başarılı sayılmaz) |
| 33 / 34 | Pilot sonucu kaydedilmeden bitti / iş kaydı okunamıyor (başarı varsayılmaz) |
| 40 / 41 | Komut güvenlik katmanınca reddedildi / sahiplik doğrulanamadı (hiçbir süreç sonlandırılmadı) |
| 42 | Pano arayüzü 30 saniyede kapanmadı (STOP_TIMEOUT); **GEO Workbench Kapat**'ı biraz sonra yeniden deneyin |

## Durdurma

- **GEO İşlem Durdur**: çalışan pilotu güvenli iptal eder (yukarıya bakın).
- **GEO Workbench Kapat**: pano arayüzünü kapatır (WSL2 panosu ve/veya yerel
  inceleme modu panosu); pilotu durdurmaz, kayıt silmez.
- **Uygulamalari Durdur** (Başlat menüsü) veya `windows\stop_apps.bat`: yerel
  olarak başlatılmış uygulamaların (yerel pano, İz B) süreç ağaçlarını kapatır
  ve eski kayıtları temizler. WSL2 içindeki pilota dokunmaz.

Tarayıcı sekmesini kapatmak uygulamayı durdurmaz; durdurma için bu kısayolları
kullanın.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| "Bos port yok" hatası | `stop_apps.bat` / **GEO Workbench Kapat** çalıştırın; ayrıca 8501–8540 portlarını kullanan başka uygulamaları kapatın. |
| "Uygun Python bulunamadi" | python.org'dan 3.12 kurun ("Add python.exe to PATH" işaretli) veya `winget install --id Python.Python.3.12 --scope user`; sonra `KURULUM.bat`'ı yeniden çalıştırın. |
| pip SSL/proxy hataları | Kurumsal ağdaysanız proxy/SSL denetimi pip'i engelleyebilir. BT biriminizden pip için proxy ayarlarını (`HTTPS_PROXY` ortam değişkeni, gerekirse kurum kök sertifikası) isteyin; ev ağında yeniden deneyin. |
| İlk açılış çok yavaş | Antivirüs, binlerce yeni Python dosyasını ilk açılışta tarar. Birkaç dakika bekleyin; mümkünse depo klasörünü antivirüs istisnalarına ekletin. |
| `UnicodeEncodeError: 'charmap' codec ...` (örn. Track B derslerini komut satırından çalıştırırken) | Windows'un eski cp1252 konsol kodlaması Türkçe karakterleri yazamıyor. Komuttan önce `set PYTHONUTF8=1` çalıştırın (PowerShell'de `$env:PYTHONUTF8='1'`). Kısayollardan başlatılan uygulamalar bunu zaten otomatik ayarlar. |
| torch indirmesi çok büyük/yarıda kesildi | PyTorch CPU paketi yüzlerce MB'dir. Kararlı bağlantıda `KURULUM.bat`'ı (WSL için **GEO WSL Kurulumu**'nu) yeniden çalıştırın; pip kaldığı önbellekten devam eder. |
| Sağlık kontrolü zaman aşımı (90 sn) | `windows\logs\geo_workbench.log`, `windows\logs\<uygulama>.log` ve WSL içinde `~/.local/share/geo-dashboard/workbench/ui.log` dosyalarının son satırlarına bakın; çoğu zaman uygulama sadece yavaş açılıyordur — tarayıcıda adresi elle deneyin. |
| Pilot "kaynak kimliği doğrulanamadı" (kod 20) diyor | Yeni bir ZIP açtıysanız veya WSL kopyası değiştiyse **GEO WSL Kurulumu**'nu yeniden çalıştırın; eski kopya silinmez, kenara taşınır. |
| Kurulum "root (uid 0)" diyor | Ubuntu'nun ilk açılışındaki Linux kullanıcısı oluşturulmamış. Başlat menüsünden Ubuntu'yu bir kez açın, kullanıcı adı ve parolayı oluşturun, `exit` yazın ve **GEO WSL Kurulumu**'nu yeniden çalıştırın. |
| `git` kurulamadı (kod 17) | Ubuntu penceresinde `sudo apt-get update` ve `sudo apt-get install -y git` komutlarını elle çalıştırıp kurulumu yeniden başlatın; kurum ağında apt için proxy gerekebilir. |
| "iş kaydı okunamıyor" (kod 19) | Bildirilen `jobs/<JOB_ID>` klasörünü silmeden başka bir yere taşıyın (ör. `jobs-incelenecek/`); sonra yeniden deneyin. |
| WSL kurulumu yönetici onayı istiyor | WSL özelliğini ilk kez etkinleştirmek Windows'ta yönetici onayı gerektirir; bu yalnız sizin onayınızla ve bir kez istenir. Onaylamak istemezseniz pano inceleme modunda çalışmaya devam eder. |
| OneDrive / boşluklu yol sorunları | Betikler boşluklu ve Türkçe karakterli yolları destekler; yine de depoyu OneDrive eşitlemesi dışında kısa bir yola (ör. `C:\calisma\...`) koymanız önerilir. OneDrive, sanal ortam dosyalarını kilitleyip bozabilir. |

## Bilimsel yönetişim sınırı

Üretim (21.350 gözlem), GPU, LOKO ve held-out değerlendirme kapıları
**kapalıdır**; bu paketteki hiçbir kısayol, düğme veya ayar bunları açmaz ve
`benchmark_complete=false` kalır. Pilot sonuçları "YALNIZ PİLOT" olarak
gösterilir ve makale sonuçlarına girmez.

## Sürüm ve destek

Sürüm bilgisi paket kökündeki `VERSION.json` dosyasında ve
`windows\SURUM_NOTLARI.md` içindedir. Sorun bildirirken `VERSION.json`
içeriğini ve ilgili `windows\logs\` günlüğünü ekleyin. Bu paket araştırma
deposunun yardımcı aracıdır; bilimsel durum için deponun
`docs/plan/DURUM.md` dosyası esastır.
