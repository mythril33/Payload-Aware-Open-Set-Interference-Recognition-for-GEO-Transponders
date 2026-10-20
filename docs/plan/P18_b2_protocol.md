# P18 — B2/1: sekiz bilinen sınıflı, çift-pol, açık-küme benchmark protokolü

Durum: **TASLAK — KULLANICI ONAYI BEKLİYOR (K17); KOD YAZILMADI** · 2026-10-20 ·
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
| `adjacent_satellite` | **uplink** (K5) | **yeni:** komşu sistem yer istasyonu yan lobu | Planlı bir taşıyıcıyla kısmen örtüşen modüleli taşıyıcı; örtüşme %20–80, PSD −15…−3 dB, farklı sembol hızı **[VARSAYIM]** |
| `carrier_under_carrier` | uplink, co-pol | E1 `carrier_under_carrier` | Kurban taşıyıcının bandı içinde; C/I (toplam plana göre) 5–25 dB **[VARSAYIM]**; CID metacarrier'ın −27,5 dB referansı **[DOĞRULANACAK]** ayrı bir alt-kutuda raporlanır |

Kurallar:
- `adjacent_satellite` ile `unauthorized` arasındaki tek tasarımsal fark, ASI'nin planlı bir
  taşıyıcıyla **örtüşmesi**dir; yetkisiz taşıyıcı ise boş aralıktadır. İkisi spektral olarak benzer olduğundan
  "**tasarım gereği karışabilir çift**" olarak önceden kaydedilir (§6).
- `carrier_under_carrier` için C/I üst sınırı, P6 §6'daki görünürlük ölçümüne göre PSD'de neredeyse görünmez
  bölgeyi kapsar. Bu bilinçli bir seçimdir: ayırt edilebilirlik sınırını ölçmek için (K9).

## 3. Bilinmeyen aileler (yalnız test)

| Aile | Kaynak | Ön kayıtlı grup (L12) | Gerekçe |
|---|---|---|---|
| `pulsed` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, yalnız zaman kapılı |
| `intermittent_bursts` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, uzun ve düzensiz kapılı |
| `adjacent_satellite_downlink` | E1-dev/1 olayı (K16) | **yakın** | Bilinen `adjacent_satellite` ile aynı dalga biçimi; yalnız giriş noktası farklı (TWTA'dan geçmez) |
| `wideband_noise` | U1-dev/1 | **eşdeğerlik-sınırlı** | Yükseltilmiş uplink gürültü tabanıyla gözlemsel olarak eşdeğer olabilir (P12); ayrı raporlanır, birleşik sayıya ağırlıklı katılmaz |

Gruplama bu tabloda **sonuçtan önce** sabitlenir. "Uzak" bir aile yoktur: bu bir bulgudur, yani GEO'daki
olası bilinmeyenlerin çoğu bilinen bir mekanizmanın varyantıdır.

## 4. Roller ve tohumlar

| Rol | Senaryo grupları | Tohum başlangıcı | Kullanım |
|---|---|---|---|
| train | 1500 **[VARSAYIM]** | 3 000 000 | Ağırlık optimizasyonu; Mahalanobis istatistikleri |
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
| `adjacent_satellite` ↔ `unauthorized` | **Tasarım gereği karışabilir**; yalnız plan örtüşmesi ipucu | Plan maskesi var/yok, plan bozma |
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
| Leave-one-known-out | 7 temiz-dışı sınıfın her biri sırayla bilinmeyen; 1 eğitim tohumu **[VARSAYIM]** |
| Maliyet | Parametre, CPU ms/çerçeve |
| İstatistik | 3 eğitim tohumu; senaryo grubu bootstrap (ağırlık ve eşik sabit). Eğitim tohumu belirsizliği ayrı. Boş seçim `null` + sayım |

## 8. Ablasyonlar (her biri tek değişken)

1. **A0** co-only; **A1** + plan; **A2** + çift-pol (ana model).
2. **A3** doğrusal zincirle eğit, doğrusal olmayanda test (C3).
3. **A4** + iptal artığı; **A4b** + SCF.
4. **A5** plan bozma (bayat, kaydırılmış, eksik).
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
