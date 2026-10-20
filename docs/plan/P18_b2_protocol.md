# P18 — B2/1: sekiz bilinen sınıflı, çift-pol, açık-küme benchmark protokolü

Durum: **TASLAK — KULLANICI ONAYI BEKLİYOR (K17); B2/1 ÜRETECİ YAZILMADI** · 2026-10-20 ·
K17 alt kararları (CuC aralığı, rol boyutları, downlink ASI grubu, LOKO tohumu) kullanıcıdan alındı ve aşağıya işlendi;
protokolün dondurulması hâlâ kullanıcıda. Uplink ASI üreteci `geosim.asi` hazır ve test edildi ·
Girdi: [P3](P3_taksonomi.md), [P5](P5_veri_protokol.md) (A1), [P12](P12_unknown_events.md),
[P14](P14_dual_polarization.md), [P15](P15_phase_noise_and_events.md), [P16](P16_literatur_duzeltme_programi.md)
(K5, K9, K14, K16), [P17](P17_r1_robustness_eval.md), [open-set önerisi](../research/open_set_protocol.md).

Bu belge onaylandığında **dondurulur**. Sonrasındaki her değişiklik §10'daki günlüğe gerekçesiyle
yazılır. Test sonuçları görüldükten sonra bölünme, sınıf, eşik ya da yakın/uzak gruplaması değiştirilmez.
A1, B1-dev, D1-dev, E1-dev ve R1-eval sürümleri değişmeden kalır.

Kapanış kriteri:
- her sınıf için giriş noktası, parametre dağılımı ve etiket kuralı yazılı;
- rol/tohum ayrımı, bilinmeyen aileleri, yakın/uzak gruplaması, metrikler, ablasyonlar ve istatistik
  **koddan önce** sabit;
- üç güçlü hakem itirazı yanıtlanmış.

## 1. Gözlem ve zincir

- **Zincir:** P14/P15 çift-pol motoru. Uplink Jones kuplajı → ortak uydu LO faz gürültüsü → iki ayrı
  IMUX/TWTA (`dvbs2_nl`)/OMUX yolu → downlink Jones kuplajı → (downlink olayı) → ortak alıcı LO faz
  gürültüsü → enstrüman yanıtı ve gürültü → bağımsız pilotlarla enstrüman kalibrasyonu.
- **Bant:** 36 MHz.
- **Model girdisi:** dört kanal, P14 sırasıyla:
  1. kalibre co-pol spektrum;
  2. kalibre karşı-pol spektrum;
  3. co-pol plan maskesi;
  4. karşı-pol plan maskesi.
  Seviye referansı co-pol planlı taşıyıcı seviyesidir. Simülatör gerçeği (XPD, IBO, C/I, linewidth)
  hiçbir zaman girdi olmaz.
- **Etiket kuralı:** tek etiket, kök neden (A1 karar B). Senaryo başına en fazla bir olay.

## 2. Bilinen sınıflar (8)

Ortak link: nominal IBO 9–13 dB, uplink/downlink C/N 15–30 dB (yol başına). Nominal uplink XPD 30 dB,
downlink 35 dB, alıcı enstrümanı 25 dB. Uydu linewidth 100 Hz, alıcı 50 Hz. Hepsi P14/P15 değerleridir.
Uplink XPD için Eutelsat EESS 502 ve Intelsat IESS-207 aralığına dayanak vardır (P14 kaynak notu);
diğerleri **[VARSAYIM]**dır.

| Sınıf | Giriş noktası | Üreteç | Değişen parametre (eşleşmiş senaryoda yalnız bu) |
|---|---|---|---|
| `clean` | — | yalnız planlar | — |
| `cw` | uplink, co-pol | A1 `cw` | C/I 5–35 dB, frekans ±0,48 B, kayma ±50 kHz/s |
| `swept_cw` | uplink, co-pol | A1 `swept_cw` | C/I 5–35 dB, genişlik 1 MHz–0,9 B, periyot 0,1–1,28 s |
| `unauthorized` | uplink, co-pol | A1 `unauthorized` (boş aralıkta) | PSD −10…+3 dB (plan ortalamasına göre) |
| `overdrive` | yük içi | sürüş seviyesi | IBO 1–4 dB (A1 ile aynı) |
| `cross_pol` | uplink anten | XPD bozulması | uplink XPD 10 dB (arıza değeri, P14) |
| `adjacent_satellite` | **uplink** (K5) | **`geosim.asi.adjacent_satellite_uplink`**: komşu ağ yer istasyonunun eksen dışı ışıması | C/I_psd = Gmax − G(φ) − ΔEIRP (ITU BR uplink yöntemi). Aralık 2,06–2,36° (FCC iki derece); desen ITU-R S.1428-1 (S.580 yan lobu) ya da S.465-6, %50; çap 0,75–2,4 m, işaretleme hatası 0–0,4 θ₃dB, ΔEIRP −3…+6 dB **[VARSAYIM]**. Sonuç: C/I_psd ortanca 20 dB, %10–%90 14–27 dB, kuyruk 2,5–33 dB. Plan örtüşmesi %20–80 (sınıf tanımı); sembol hızı ve konum plandan bağımsız. Ayrıntı ve kaynaklar: [ASI ölçümü](../results/asi_visibility.md) |
| `carrier_under_carrier` | uplink, co-pol | E1 `carrier_under_carrier` | Kurban taşıyıcının bandı içinde; C/I (toplam plana göre) **5–30 dB (K17, kullanıcı kararı)**; kutular 5–15, 15–25, 25–30 dB ([görünürlük ölçümü](../results/cuc_visibility.md): eşleşmiş ΔPSD ortancası 5 dB'de 5,6 dB, 20 dB'de 0,37 dB, 30 dB'de 0,04 dB); CID metacarrier'ın −27,5 dB referansı **[DOĞRULANACAK]** ayrı bir alt-kutuda raporlanır |

Kurallar:
- `adjacent_satellite` ile `unauthorized` arasındaki yerleşim farkı, ASI'nin planlı bir taşıyıcıyla
  **örtüşmesi**dir; yetkisiz taşıyıcı ise boş aralıktadır. İkisi spektral olarak benzer olduğundan
  "**tasarım gereği karışabilir çift**" olarak önceden kaydedilir (§6).
  - [ASI ölçümü](../results/asi_visibility.md): plan içi kısım kâhin ikizle bile neredeyse görünmez
    (ΔPSD ortancası 0,005–0,18 dB). Görünen, plan dışına taşan kısımdır.
  - İkinci fark seviyedir: `unauthorized` C/I_psd −3…10 dB, ASI ise kaynaklı geometride çoğunlukla 10 dB'nin
    üstünde. Bu fizikseldir (yan lob ve ana lob farkı), ama bir seviye kısa yolu olarak §6'da ayrıca sınanır.
- **Açık konu — aşırı sürme etiketi yükselteçten bağımsız değil** ([R1 pilotu](../results/r1_pilot.md)):
  - Rapp p = 2'de IBO 1–4 dB'nin IM düzeyi, TWTA'nın nominal IBO'sundaki kadar.
  - A1 modelleri bu örneklerin %90–98'ine `clean` diyor.
  - B2/1 tek TWTA kullandığı için etiket IBO'ya bağlı kalabilir. Ama yükselteç aktarımı (A6) raporlanırken bu
    örnekler "gözlemde nominal" alt kutusunda ayrıca verilmelidir **[ÖNERİ]**.
- `carrier_under_carrier` için C/I üst sınırı, P6 §6'daki görünürlük ölçümüne göre PSD'de neredeyse görünmez
  bölgeyi kapsar. Bu bilinçli bir seçimdir: ayırt edilebilirlik sınırını ölçmek için (K9).

## 3. Bilinmeyen aileler (yalnız test)

| Aile | Kaynak | Ön kayıtlı grup (L12) | Gerekçe |
|---|---|---|---|
| `pulsed` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, yalnız zaman kapılı |
| `intermittent_bursts` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, uzun ve düzensiz kapılı |
| `adjacent_satellite_downlink` | E1-dev/1 olayı (K16) | **yakın (K17, kullanıcı kararı)** | Bilinen `adjacent_satellite` ile aynı dalga biçimi; yalnız giriş noktası farklı (TWTA'dan geçmez). **[ÖNERİ]** C/I_psd aynı `geosim.asi.draw_geometry` ile, alıcı antenimiz için 11,7 GHz'de çekilir; böylece iki olay yalnız giriş noktasında ayrışır |
| `wideband_noise` | U1-dev/1 | **eşdeğerlik-sınırlı** | Yükseltilmiş uplink gürültü tabanıyla gözlemsel olarak eşdeğer olabilir (P12); ayrı raporlanır, birleşik sayıya ağırlıklı katılmaz |

Gruplama bu tabloda **sonuçtan önce** sabitlenir. "Uzak" bir aile yoktur: bu bir bulgudur, yani GEO'daki
olası bilinmeyenlerin çoğu bilinen bir mekanizmanın varyantıdır.

## 4. Roller ve tohumlar

| Rol | Senaryo grupları | Tohum başlangıcı | Kullanım |
|---|---|---|---|
| train | 1500 (K17, kullanıcı kararı) | 3 000 000 | Ağırlık optimizasyonu; Mahalanobis istatistikleri |
| val-select | 150 | 3 100 000 | Yalnız checkpoint seçimi |
| val-calib | 150 | 3 150 000 | Yalnız ret eşiği ve alarm eşiği kalibrasyonu (yalnız bilinen sınıflar, K14) |
| test | 500 | 3 200 000 | Bilinen test + aynı gruplarda bilinmeyen aileler |

- Bir senaryo grubunun bütün sınıf varyantları (aynı planlar, link, kuplaj, faz gürültüsü ve gürültü akışları)
  tek roldedir.
- Tohum aralıkları A1, R1, U1 (900000–), D1 (1000000–) ve E1 (2000000–) aralıklarıyla çakışmaz. Bu kodda
  testle denetlenir.
- Bilinmeyen aile örnekleri yalnız test gruplarında üretilir; ayrı RNG ad alanı kullanılır.
- Boyut ve süre: 2300 grup × (8 + 4) varyant ≈ 27 600 çift-pol örnek. Örnek başına ≈ 2,5–3 s **[TAHMİN]**
  ile ≈ 20 çekirdek-saat. Kullanıcı makinesinde koşar.

## 5. Modeller ve yöntemler

- **Ana model:** küçük ResNet, dört kanal; `co` görünümü eşleşmiş ablasyon olarak (iki kanal).
- **Sonradan skorlama:** MSP, energy, Mahalanobis (yalnız train embedding'leri).
- **Eğitim zamanı (D13):** ARPL ya da prototip/merkez kaybı. Vekil bilinmeyen kullanılmaz (K14).
- **Ek gözlem kanalı (K9):**
  1. gözlemden hesaplanan iptal artığı (planın sembol hızıyla karar yönlü yeniden modülasyon);
  2. ardından SCF dalı.
  Kâhin iptal yalnız etiketli üst sınırdır.
- **Baseline'lar:** CA-CFAR (planlı ve plansız), EDSC (iptal sonrası ED; aynı iptal kodu), uzman
  öznitelik + XGBoost.
- **Hiperparametreler:** P6 ayarları, arama yok; bütün yöntemler aynı eğitim bütçesi.

## 6. Ayırt edilebilirlik ön kaydı

Sonuçtan önce yazılan beklentiler. Her biri en az bir ablasyonla sınanır.

| Çift / sınıf | Beklenti | Sınayan ablasyon |
|---|---|---|
| `overdrive` ↔ gürültülü `clean` | Düşük downlink C/N'de karışır (P3 §4) | C/N kutularına göre karışıklık |
| `cross_pol` ↔ `unauthorized` | Karşı-pol kanalıyla ayrılır, co-pol tek başına ayırmaz | `co` vs `dual` |
| `adjacent_satellite` ↔ `unauthorized` | **Tasarım gereği karışabilir**; plan örtüşmesi zayıf ipucu, seviye güçlü ipucu | Plan maskesi var/yok, plan bozma; **[ÖNERİ]** seviye eşleşmiş alt kutu (C/I_psd 7–10 dB, her iki sınıf) ayrı raporlanır |
| `adjacent_satellite` ↔ `carrier_under_carrier` | Plan dışına taşan kısım ASI'yi ayırır; ≥ 25 dB ASI'de bu kısım da zayıf | C/I kutuları |
| `carrier_under_carrier` ↔ `clean` | Spektrumla yüksek C/I'de şans düzeyi; iptal artığı/SCF ile ayrılır | Ek kanal var/yok, C/I kutuları |
| `adjacent_satellite_downlink` (unknown) ↔ `adjacent_satellite` | Ayrım ancak yük süzgeci/IM izinden mümkün; zayıf ret beklenir | Aile başına AUROC |
| `unauthorized` | Maske kısa yolu riski | Bayat plan, ±kaydırılmış plan, eksik/fazla taşıyıcı |

## 7. Değerlendirme

| Metrik | Tanım |
|---|---|
| Kapalı küme | Doğruluk, makro-F1, karışıklık matrisi, ECE (15 kutu); eşik yok |
| Açık küme | Unknown pozitif AUROC/AP, OSCR, FPR@95TPR (payda: bilinen test olayları); aile başına ve ön kayıtlı grup başına; birleşik sayı yalnız "yakın" ailelerden |
| Eşikli işletim | val-calib'den sabitlenen ret eşiğinde bilinen kabul, kabul edilen bilinen doğruluğu, bilinmeyen reddi, temizde yanlış alarm |
| Algılama | val-calib temizde Pfa %5 ile sınıf başına Pd; C/I, I/N ve IBO kutularına göre |
| Leave-one-known-out | 7 temiz-dışı sınıfın her biri sırayla bilinmeyen; **3 eğitim tohumu (K17, kullanıcı kararı)**, yani 21 ek eğitim |
| Maliyet | Parametre, CPU ms/çerçeve |
| İstatistik | 3 eğitim tohumu; senaryo grubu bootstrap (ağırlık ve eşik sabit). Eğitim tohumu belirsizliği ayrı. Boş seçim `null` + sayım |

## 8. Ablasyonlar (her biri tek değişken)

1. **A0** co-only; **A1** + plan; **A2** + çift-pol (ana model).
2. **A3** doğrusal zincirle eğit, doğrusal olmayanda test (C3).
3. **A4** + iptal artığı; **A4b** + SCF.
4. **A5** plan bozma (bayat, kaydırılmış, eksik). Değerlendirme aracı A1 için hazır: `geoml.plan_shortcut` (bozmalar `shift_plus/minus`, `drop_one`, `phantom`, `authorize_intruder`); B2/1'e çift-pol maskelerle genişletilecek.
   - [A1 pilotu](../results/plan_shortcut_pilot.md): 0,5 MHz bayat plan temizde yanlış alarmı %3 → %93'e çıkarıyor.
   - **[ÖNERİ]** B2/1 eğitiminde plan sapması artırımı (±0,5 MHz kaydırma, eksik/fazla taşıyıcı). Ya da A5 ayrı
     bir değerlendirme kutusu olarak kalır. Karar dondurma öncesi kullanıcıda (K17).
5. **A6** R1 yükselteçlerine aktarım.
6. **A7** FiLM koşullaması (maske kanalı yerine).
7. **A8** unknown aileleri ve leave-one-known-out.

Veri, eğitim bütçesi, eşik seçimi ve tohum protokolü bütün ablasyonlarda eşittir.

## 9. Hakem itirazları

| İtiraz | Yanıt / sınır |
|---|---|
| "ASI ve unauthorized aynı şey; sekiz sınıf yapay." | Kabul edilen sınır, ön kayıtlı (§6). Sonuç "plan örtüşmesi dışında ayırt edilemez" çıkarsa böyle raporlanır; birleşik etiketle ikinci bir değerlendirme (7 sınıf) ek tablo olarak verilir. |
| "Bilinmeyenler bilinenlerin varyantı; open-set kolaylaştırılmış ya da zorlaştırılmış." | Gruplama sonuçtan önce sabit; aile başına rapor; ayrıca leave-one-known-out rotasyonu, aile seçiminden bağımsız bir ölçüt verir. |
| "Bütün sayılar simülatör varsayımlarına (XPD, linewidth, C/I aralıkları) bağlı." | Kabul. Yer istasyonu XPD'si için kaynak var, diğerleri [VARSAYIM]. Duyarlılık için R1 benzeri yalnız-test kayma kümeleri (XPD, linewidth, C/I) ayrı bir sürümde. Gerçek veri yok (DURUM §5.5). |

## 10. Değişiklik günlüğü

| Tarih | Değişiklik | Gerekçe |
|---|---|---|
| 2026-10-20 | Taslak | — |
| 2026-10-20 | K17 alt kararları işlendi: CuC 5–30 dB; roller 1500/150/150/500; downlink ASI yakın; LOKO 3 tohum | Kullanıcı yanıtları (dondurma öncesi) |
| 2026-10-20 | Aşırı sürme etiketi açık konusu ve A5 plan sapması artırımı önerisi eklendi | [R1 pilotu](../results/r1_pilot.md), [A5 pilotu](../results/plan_shortcut_pilot.md) |
| 2026-10-20 | `adjacent_satellite` parametreleri kaynaklı geometriyle değiştirildi (eski: örtüşme %20–80, PSD −15…−3 dB [VARSAYIM]) | ITU-R S.1428-1/S.580-6/S.465-6, FCC iki derece, ITU BR uplink C/I yöntemi; [ASI ölçümü](../results/asi_visibility.md) |
