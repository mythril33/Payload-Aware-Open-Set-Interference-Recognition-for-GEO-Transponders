# Proje durumu ve eksik kaydı

Son güncelleme: 2026-10-20 (literatür taraması eki P16; temel deney durumu 2026-10-10) · Bu dosya "şu an neredeyiz, ne eksik" sorusunun tek yanıtıdır; her oturum sonunda güncellenir.

## Literatür taraması eki — 2026-10-20 (P16)

- **Numara notu:** bu ek önce P15 olarak yayımlandı; aynı gün main'e ayrı bir P15 (faz gürültüsü ve olaylar, E1-dev/1) girdi. Literatür programı artık [P16](P16_literatur_duzeltme_programi.md), B2/1 protokolü P17.
- **Çelişki (L16) çözüldü — K16:** E1-dev/1'in alıcı tarafındaki (TWTA'yı atlayan) olayı `adjacent_satellite_downlink` adıyla ayrı tutulacak; B2/1'deki `adjacent_satellite` sınıfı K5 gereği uplink-ASI olarak yeni kodlanacak. Kodda yeniden adlandırma henüz yapılmadı (P16 İP-3, tam test paketiyle).

- Kullanıcının verdiği literatür taraması okundu ve depo belgeleriyle karşılaştırıldı: [P16 düzeltme ve tamamlama programı](P16_literatur_duzeltme_programi.md). Yeni deney veya kod **yok**; yalnız belge, kaynakça ve plan.
- **Hüküm:** boşluk iddiası ayakta, ama yenilik "birlikte modelleyen ilk" biçiminde daraltılır (K10). Carrier-under-carrier ve ASI↔unauthorized ayırt edilemezlik bulgusu olarak tasarıma girer; gerçekçilik çapası yükselteç ailesi uyumsuzluğu + NPR + ölçülmüş PA olarak üç ayağa çıkar.
- Bu oturumda kapanan: P1'e tarama v2 eki ve planlanan/uygulanan boşluk matrisi; `open_set_protocol.md` CuC satırı; P9 yayın yeri adayları; `references.bib`'e 19 girdi (doğrulanmamışlar `note = {verify}`); aşağıdaki faz tablosu.
- Açık kalan çelişkiler (P16 §2): L1 Highway 2 lisansı (CC BY-SA mı BY-NC-SA mı), L2 OpenDPD kayıt adı (APA/DPA), L7 Daoud başlığı ve TR 102 376-2 başlığı, L10 XPD değerlerinin kaynağı, L12 yakın/uzak OOD gruplaması.
- **Kararlar alındı (2026-10-20):** K5 uplink-ASI (downlink veto), K9 iptal artığı + cyclic, K10 aşamalı cümle, K11 OpenDPD ölçüm aralığında, K12 sabit tarih yok, K13 şimdilik lisans yok, K14 vekil unknown yok. L2 kapandı: OpenDPD'de APA (GaN Doherty, 3,5 GHz) ve DPA (CMOS Doherty, 2,4 GHz) ikisi de var; [ön sonda](../results/opendpd_probe.md) sıkışmanın zayıf (p99'da ≤ 0,8 dB), belleğin belirgin olduğunu gösterdi. SmartSpace sitesi bu bulut ortamında ağ politikasınca engelli (S6).
- Yeni iş paketleri İP-0…İP-7 ve iş sırası P16 §3–§4'te; yeni sürüm adları **R1-eval/1** (yalnız test: IBO süpürmesi, yükselteç uyumsuzluğu) ve **B2/1** (nihai sekiz sınıflı benchmark). A1 değişmedi.

## Uygulama eki — 2026-10-20

- **M3 faz gürültüsü ve olay blokları kodlandı:** [P15](P15_phase_noise_and_events.md); ortak uydu/alıcı Wiener faz gürültüsü, uplink taşıyıcı-altı girişim ve alıcı tarafında komşu uydu girişimi eklendi. Uydu girişimi hedef yükün TWTA'sından geçmez. Sıfır linewidth eski sayısal çıktıları korur; A1 değiştirilmedi.
- Son birleşik doğrulama: **542 test geçti**. `E1-dev/1`, aynı planları, link ayarlarını ve faz süreçlerini paylaşan `clean` / `carrier_under_carrier` / `adjacent_satellite` geliştirme deneyidir. Veri, bağımsız pilot kalibrasyonu, kayıt kimlikleri ve ayrı model-seçimi/eşik-kalibrasyonu grupları denetlenir.
- E1 fiziksel pilotu: **54 gözlem**, iki giriş görünümü için üçer epok; doğrulanmış veri/model/eşik tekrar kullanımı tamamlandı. İki model de %33,3 doğruluk ve 0,167 macro-F1 verdi. Üç temiz örnekle eşik kurulması ve yüksek test yanlış alarmları nedeniyle sonuçlar çalışma doğrulamasıdır; tanıma avantajı göstermez. [Sonuçlar](../results/events_development.md) ve [18 eşleşmiş senaryonun fiziksel kontrolleri](../results/events_physics_check.json) kaydedildi.
- Fiziksel olay üreteçleri artık vardır; sekiz bilinen sınıfı tek çift-pol protokolünde birleştirme, çift-pol unknown reddi, tam veri/çok eğitim tohumu ve fiziksel kaynakların gözlemlerle ayırt edilebilirliği üzerindeki çalışma sürmektedir. PSD, komşu uydu kaynağını veya yetkilendirmeyi tek başına benzersiz belirlemez.
- **M3 çift-pol geliştirme dilimi kodlandı:** [P14](P14_dual_polarization.md); uplink kuplajı → iki ayrı IMUX/TWTA/OMUX yolu → downlink kuplajı → alıcı enstrüman yanıtı ve gürültüsü → bağımsız pilotlarla kalibrasyon. Fiziksel sızıntı kalibrasyonla kaldırılmaz. Ayrı planlar için dört model kanalı ve eşleşmiş co-only karşılaştırması vardır.
- M3 doğrulaması: **355 test geçti**. 36 çift-pol gözlem üretildi; iki giriş görünümü üçer epok eğitildi ve kayıt/üretim tekrar kullanımı doğrulandı. Her görünümde sınıflandırma doğruluğu %50; küçük koşu yalnız çalışma kanıtıdır. [Sonuçlar ve kalibrasyon kontrolü](../results/dual_development.md) kaydedildi.
- `D1-dev/1`, `clean`/`cross_pol` için kontrollü iki sınıflı geliştirme protokolüdür; sekiz sınıflı nihai open-set benchmark değildir. Birlikte yüklenmiş iki yolun toplam güç oranı XPD değildir; XPD doğrulaması izole kaynak testleriyle yapılır.
- **M2 geliştirme dilimi kodlandı:** [P12 unknown üreteçleri](P12_unknown_events.md), [P13 genişletilmiş deney](P13_extended_openset.md); periyodik darbeli CW, geniş bant gürültü ve aralıklı uzun burst aileleri test için üretilebilir. Mahalanobis yalnız eğitim embedding'leriyle uydurulur. AUROC/AP ve OSCR aile bazında ve birleşik raporlanır; eşikler yine ayrı bilinen kalibrasyon verisinden alınır.
- M2 doğrulaması: **226 test geçti**. Toplam 108 fiziksel simülasyon gözlemi üretildi; üç epok eğitim, yalnız 24 eğitim örneğinden Mahalanobis ve ayrı 12 bilinen örnekten eşik kalibrasyonu tamamlandı. Kayıtlı sonuç, eğitilmiş model ve üretim tekrar kullanımı doğrulandı. [Küçük koşu sonuçları](../results/openset_extended.md) zayıftır; bilimsel veya operasyonel başarı kanıtı değildir.
- Ajan görev tanımları `.agents/` ve depo geliştirme kuralları `AGENTS.md` altında sürümlendi. M0/M1 kaynak, test, kurulum ve ajan belgeleri GitHub'a `dcdc023` ile gönderildi.
- [P10 uygulama yapısı](P10_implementation_structure.md) ve [P11 geliştirme protokolü](P11_openset_development.md) eklendi.
- **M0 + ilk M1 dilimi kodlandı:** veri/çekirdek kayıtlarının kimlik ve bütünlük kontrolü, senaryo bazlı ayrım, bilinen doğrulama verisiyle MSP/energy eşikleri ve `known/unknown` tahmin/rapor hattı.
- `B1-dev/1`, mevcut beş sınıftan bir girişim ailesini dışarıda tutar; `clean` bilinen olarak kalır. Eğitim için doğrulama ve ret eşiği kalibrasyonu ayrı senaryo gruplarıdır. A1 protokolünün fiziksel örnekleme/sınıf/split tanımları değiştirilmedi.
- Altı tohum × üç kaynak split ile fiziksel üretim ve üç epok eğitim denemesi yapıldı. Küçük koşu yalnız çalışma kanıtıdır; model kalitesi zayıftır ve bilimsel sonuç değildir.
- Doğrulama: tam test paketi **141 test geçti**; son kaynak-rolü kontrolü sonrası yedi deney testi tekrar geçti. Veri ve checkpoint tekrar kullanımı da gerçek koşuda doğrulandı.
- Sekiz sınıflı nihai B benchmark'ı henüz uygulanmadı. Unknown üreteçleri, Mahalanobis, AUROC/OSCR, çift-pol geliştirme hattı, faz gürültüsü ve modüle girişim blokları vardır; tam bilimsel değerlendirme yapılmadı. Aşağıdaki eski faz/eksik tabloları temel Kademe A durumunu tarif eder; güncel uygulama durumu bu ektedir.

## Araştırma eki — 2026-10-20

- **P1 literatür / yakın çalışmalar:** ilk kaynak-tabanlı denetim eklendi: [P1_literatur.md](P1_literatur.md). “GEO'da ilk DL” ve “önceki çalışmaların hepsi idealize” iddiaları **geçersiz**; doğrulanmış yenilik yerine test edilebilir aday katkı önerildi. Kapsamlı sistematik tarama veya bütün yakın makalelerin tam metin analizi henüz yapılmadı.
- **P8 dış kaynak:** veri temsilleri, SmartSpace araştırma amaçlı kullanım koşulu, GaN PA vs TWTA ve GNSS kayıtlarının görev farkı belgelendi: [P8_dis_veri.md](P8_dis_veri.md). Ham veri indirilip deney yapılmadı.
- **P9 ve B açık-küme protokolü:** [P9_yol_haritasi.md](P9_yol_haritasi.md) ve [open_set_protocol.md](../research/open_set_protocol.md) yayımlandı. Tam B benchmark'ı tasarım aşamasındadır; kodlanan/test edilen geliştirme dilimleri yukarıda ayrı sürümleriyle listelenir.
- **Kaynakça ve birincil kaynak yolları:** [references.bib](../../references/references.bib) ve [ORIGINALS.md](../../sources/ORIGINALS.md); özgün DOCX'in [Markdown transkripsiyonu](../../sources/original_proposal.md).
- **S1–S4, B0/B1b/B2/B3/B4/B7 ve tam benchmark** bu araştırma commit'leriyle kapanmadı. Eski pilot rakamları değişmedi.

## 1. Tek cümleyle

Kademe A'nın (ders projesi) bütün zinciri kodlandı ve uçtan uca çalışıyor: simülatör → etiketli veri → üç model + baseline → sonuç tabloları. Eksik olan, **tam boyutlu veriyle alınmış sonuç**; bu koşu sizin makinenizde yapılacak.

## 2. Fazlar

| Faz | Konu | Durum | Dosya |
|---|---|---|---|
| P0 | Kapsam | Kapandı | `P0_kapsam.md` |
| P2-A | Sistem modeli | Kapandı | `P2_sistem_modeli.md` |
| P4-A | Simülatör | Kapandı, 55+ test | `P4_simulator_tasarim.md` |
| P3-A | Sınıflar ve girişimciler | Kapandı | `P3_taksonomi.md` |
| P5-A | Veri protokolü | Donduruldu (A1) | `P5_veri_protokol.md` |
| P6-A | Model ve baseline | Kapandı | `P6_modeller.md` |
| P7-A | Değerlendirme | Kapandı; yalnızca pilot sonuç var | `P7_degerlendirme.md`, `../results/pilot_A.md` |
| P1 | Literatür ve yenilik | Tarama v2 eklendi; **tam metin okuması yok, kapanmadı** | `P1_literatur.md` §7 |
| P8 | Dış veri denetimi | Kaynak sayfaları denetlendi; veri indirilmedi; L1/L2 açık | `P8_dis_veri.md` |
| P9 | Yol haritası, hedef yayın | Öneri; takvim P16 §4'te, onaysız (K12) | `P9_yol_haritasi.md` |
| P16 | Literatür sonrası düzeltme programı | Plan; İP-0…İP-7 | `P16_literatur_duzeltme_programi.md` |
| Kademe B | Çift pol, 8 sınıf, open-set | Geliştirme dilimleri var (B1-dev/1–2, D1-dev/1); nihai B2/1 benchmark yok | `P11`–`P14` |

## 3. Elde ne var

- **Simülatör (`src/geosim/`):** DVB-S2 referans transponderi. IMUX/OMUX resmi ETSI tablolarından, TWTA standardın şekillerinden sayısallaştırıldı. 36 ve 72 MHz, üç yükselteç modeli, doğrusal karşılaştırma zinciri.
- **Beş sınıf:** clean, cw, swept_cw, unauthorized, overdrive; aynı tohumda eşleştirilmiş örnekler.
- **Veri üreticisi:** 10 bölünme, parçalı ve kaldığı yerden süren üretim; senaryo başına yaklaşık 1 s.
- **Öğrenme hattı (`src/geoml/`):** küçük ResNet (≈ 310 000 parametre), CA-CFAR baseline (planlı ve plansız), tek komutla eğitim + değerlendirme + rapor.
- **Belgeler:** her faz için karar, gerekçe, reddedilen alternatif ve hakem itirazları.

## 4. Şimdiye kadarki bulgular

| Bulgu | Kaynak |
|---|---|
| TWTA, hiçbir dış girişim yokken taşıyıcı aralarını dolduruyor: IBO 3 dB'de −39,9 dB'den −16,9 dB'ye | P4 §4 |
| Saleh'in klasik katsayıları DVB-S2 referans tüpünden belirgin farklı (doyumda faz 22° ve 42°) | Kaynak notu |
| "Geri çekilme başına 2 dB" kuralı çalışma aralığında geçerli değil (ölçülen 1,25 dB/dB) | P2 §10 |
| Aşırı sürme ile gürültülü temiz transponder aynı aralık seviyesini verebiliyor | P3 §4 |
| Mutlak güç aşırı sürmeyi tek başına ele veriyor; iki zincirin seviyesi de farklı → seviye denetimi zorunlu | P5 §5 |
| C/I 25 dB üstündeki taşıyıcı üstü CW spektrumda neredeyse görünmez (0,2 dB tepe) | P6 §6 |

Bunların hiçbiri henüz tam veriyle alınmış bir model sonucu değil.

**Pilot koşu** (verinin %6'sı, `docs/results/pilot_A.md`): boru hattı uçtan uca çalışıyor. Beş sınıflı model dağılım içinde %83,4. Yük farkı nominal geri çekilmede küçük çıktı (doğruluk %78,7 → %76,8, aralıklar içinde); en belirgin etki, doğrusal eğitilen modelin aşırı sürme örneklerinin %84'üne dış girişim demesi. Model CW'de planlı CFAR'ı geçemiyor.

## 5. Eksik kaydı

### 5.1 Bu oturumda kapananlar

| Eksik | Nasıl kapandı |
|---|---|
| Model, baseline ve değerlendirme kodu yoktu | `src/geoml/` yazıldı; P6-A ve P7-A belgelendi |
| Seviye kısa yolu denetlenmiyordu | Taşıyıcıya göre normalizasyon; 7,5 dB kaymaya duyarsızlık testle doğrulandı |
| Şekil H.3'ün çizilen aralığın üstündeki uzatması varsayımdı | Ölçüldü: IBO 0 dB'de örneklerin %1,6'sı aralığın üstünde; iki farklı uzatma kuralı arasında aralık seviyesi farkı en çok 0,08 dB, IBO ≥ 2,5 dB'de sıfır. Varsayım sonuçları etkilemiyor. |
| Saleh katsayıları kaynaktan teyitsizdi | MathWorks belgesi aynı dört değeri Saleh 1981'e atıfla varsayılan olarak veriyor (ikincil kaynak; makalenin kendisine bakılmadı) |
| İlk model taşıyıcı üstündeki CW'leri kaçırıyordu | Gövde tam frekans çözünürlüğüne alındı, zaman havuzlama güç ortalamasına çevrildi, artırma eklendi |

### 5.2 Açık — sizde

| # | Eksik | Ne gerekiyor |
|---|---|---|
| S1 | Tam veri kümesi üretilmedi | `python -m geosim.dataset --out data/stageA --workers 4` (≈ 9 çekirdek-saat, 4,1 GB) |
| S2 | Tam sonuç yok | `python -m geoml.pipeline --data data/stageA --out runs/stageA --epochs 30 --seeds 0 1 2`, sonra `runs/stageA/results.md` dosyasını bana gönderin |
| S3 | Dizüstünde süre ölçülmedi | S1'i önce `--limit-seeds 10` ile deneyip süreyi yazın |
| S4 | Üç varsayılan karar onaysız | Aşırı sürme sınırı (P3 §0-A), tek etiket kuralı (P3 §0-B), doğrusal zincirde aşırı sürme (P5 §0) |
| S5 | ~~P16 kararları~~ — **2026-10-20 yanıtlandı** (P16 §5): uplink-ASI, iptal artığı + cyclic, aşamalı yenilik cümlesi, OpenDPD ölçüm aralığında, sabit tarih yok, lisans şimdilik yok, vekil unknown yok | — |
| S6 | SmartSpace verisi bulutta işlenecek | Ortam ayarlarında **Network access → Allowed domains**'e `fnr-smartspace-project.uni.lu` ekleyin (paket yöneticileri kutusu işaretli kalsın) ve araştırma-amaçlı, ticari olmayan kullanım koşulunu kabul ettiğinizi yazın |

### 5.3 Açık — bende, sıradaki işler

| # | Eksik | Önem | Not |
|---|---|---|---|
| B0 | **Ana iddianın biçimi.** Pilotta yük farkı doğrulukta görünmedi | Yüksek | Tam veriyle teyit; gerekirse iddia yanlış alarm ve yanlış etiketleme üzerinden kurulur veya daha düşük geri çekilme eklenir (protokol değişikliği, günlüğe yazılır) |
| B1 | **Literatür ve yenilik denetimi (P1)** başlandı, bitmedi | Yüksek | Aday çalışmalar listelendi (SnT ICASSP 2023, Henarejos ve ark. 2019, GNSS ve radar open-set çalışmaları); hiçbiri okunup karşılaştırılmadı |
| B1b | Model dar bantlı girişimde (CW) zayıf | Orta | Tam veriyle yeniden bakılacak; gerekirse zaman ortalamalı spektrum ek kanal olarak verilir |
| B2 | Sonuç şekilleri (ROC, C/I eğrileri, karışıklık matrisi) | Orta | Tam sonuç gelince |
| B3 | Mutlak seviye ablasyonu | Orta | `--level absolute`; tam veriyle |
| B4 | Parametre aralıklarının hiçbiri kaynaklı değil (C/N, C/I, taşıyıcı sayısı) | Orta | B1 ile birlikte literatürden dayanak aranacak |
| B5 | Dış veri denetiminin kalanı: RF WebLab, OpenDPD'nin yükselteç teknolojisi, DARCY dosya biçimi | Düşük (Kademe B) | |
| B6 | Proje talimat belgesi hâlâ ilk hâlinde (zincir tarifi, veri kaynağı rolleri hatalı; "Roadmap, risks and venues" boş) | Orta | P9 ile birlikte düzeltilmiş metin önerilecek |
| B7 | Gerçek sinyalle akıl sağlığı denetimi (Zenodo'daki Intelsat 37e kaydı) | Düşük | |
| B8 | Proje skill'leri eski (faz sırası, Saleh'in birincil model olduğu varsayımı) | Düşük | Güncelleme önerisi sunuldu |
| B9 | P16 İP-0: en yakın 6 çalışmanın tam metin okuması; L1, L2, L7, L10 | Yüksek | P1 kapanışının ön koşulu |
| B10 | P16 İP-1: FPR@95TPR, ECE, gecikme metrikleri; C3'ün IBO-eğrisi (R1-eval/1) | Yüksek | Kod + test; tam üretim sizde |
| B11 | P16 İP-2: Rapp ve bellek polinomu yükselteçleri, OpenDPD türetmesi, NPR kontrolü | Yüksek | A1 regresyon testi zorunlu |
| B12 | P16 İP-3/4: ASI, CuC, faz gürültüsü, PL çerçeve; iptal artığı, plan bozma testleri | Yüksek | K5, K9 kararlarına bağlı |
| B13 | P16 İP-5/6: B2/1 protokolü (`P16`), eğitim-zamanı OSR, EDSC ve XGBoost baseline'ları | Orta | B2/1 kod yazılmadan dondurulur |

### 5.4 Bilinçli olarak ertelenenler (Kademe B)

- DVB-S2 PL çerçevesi anahtarı (P0'da "ikinci adım" olarak sözü verilmişti; Kademe A iddialarının hiçbiri gerektirmiyor, cyclic dalıyla birlikte yapılacak)
- Çift polarizasyon, cross-pol, komşu uydu, carrier-under-carrier sınıfları
- Open-set reddi ve bilinmeyen sınıflar
- Faz gürültüsü, ALC, komşu transponderler
- Uzman özellikli baseline, transformer, hiperparametre araması
- Görülmemiş süzgeç kümesi (26/33 MHz tabloları), IBO 5–8 dB bölgesi

### 5.5 Çözülemeyecek sınırlar

- **Gerçek veri yok.** Çalışma bir simülasyon çalışmasıdır; yük farkı iki simülatör arasındaki farktır. Ölçüm imkânı olmadığı için bu, makalede açıkça yazılacak bir sınırdır.
- **Doğrusallaştırılmış TWTA eğrisi seyrek** (dB başına bir nokta, basamaklı faz); bu modeldeki ayrıntılara güvenilmemeli.
- **ETSI ham dosyaları depoda değil**; yeniden üretmek isteyen kendisi indirmeli.

## 6. Önerilen sıra

1. Siz: S3 → S1 → S2 (veri ve tam koşu); S5 kararları.
2. Ben, aynı anda: B9 (tam metin + açık L-maddeleri), B10 (metrikler, R1-eval/1 kodu), B4.
3. Sonuç gelince: B0, B2, B3, B11 ve ders raporu taslağı.
4. Ardından B12–B13 (Kademe B); haftalık sıra P16 §4.
