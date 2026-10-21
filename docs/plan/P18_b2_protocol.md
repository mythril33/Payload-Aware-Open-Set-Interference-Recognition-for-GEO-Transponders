# P18 — B2/1: sekiz bilinen sınıflı, çift-pol, açık-küme benchmark protokolü

Durum: **DONDURULDU — 2026-10-20 (K17, kullanıcı onayı)**; bilinen fiziksel gözlem aşaması
`B2-base/1` [P19](P19_b2_base_observations.md)'da, iptal artığı (beşinci kanal) ve iki çıktılı model
arayüzü `B2-feat/1` [P20](P20_b2_cancellation_residual.md)'de uygulandı; nihai B2/1 hattı tamamlanmadı ·
Bütün K17 kararları aşağıya işlendi (§10). Hazır ve test edilmiş üreteçler: uplink ASI `geosim.asi`,
DVB-CID `geosim.cid` ·
Girdi: [P3](P3_taksonomi.md), [P5](P5_veri_protokol.md) (A1), [P12](P12_unknown_events.md),
[P14](P14_dual_polarization.md), [P15](P15_phase_noise_and_events.md), [P16](P16_literatur_duzeltme_programi.md)
(K5, K9, K14, K16), [P17](P17_r1_robustness_eval.md), [open-set önerisi](../research/open_set_protocol.md).

Bu belge **dondurulmuştur**. Sonrasındaki her değişiklik §10'daki günlüğe gerekçesiyle
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
- **Model girdisi:** beş kanal (K17, K9). İlk dördü P14 sırasıyla:
  1. kalibre co-pol spektrum;
  2. kalibre karşı-pol spektrum;
  3. co-pol plan maskesi;
  4. karşı-pol plan maskesi;
  5. co-pol iptal artığı (§5).
  Seviye referansı co-pol planlı taşıyıcı seviyesidir. Simülatör gerçeği (XPD, IBO, C/I, linewidth)
  hiçbir zaman girdi olmaz.
- **Etiket kuralı:** tek etiket, kök neden (A1 karar B). Senaryo başına en fazla bir olay.
  - Ek olarak bağımsız ikinci çıktı `plan_consistency` vardır (§7a, K17b).

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
| `carrier_under_carrier` | uplink, co-pol | E1 `carrier_under_carrier` | Kurban taşıyıcının bandı içinde; C/I (toplam plana göre) **5–30 dB (K17, kullanıcı kararı)**; kutular 5–15, 15–25, 25–30 dB ([görünürlük ölçümü](../results/cuc_visibility.md): eşleşmiş ΔPSD ortancası 5 dB'de 5,6 dB, 20 dB'de 0,37 dB, 30 dB'de 0,04 dB); CID seviyesi **doğrulandı** (ETSI TS 103 129 V1.1.2 Tablo 6; ITU-R S.2062-0 Tablo 3). Gerçek DVB-CID, ayrı yalnız-test ailesi `cid_overlay` olarak üretilir (§3) |

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
  - B2/1 tek TWTA kullandığı için etiket IBO'ya bağlı kalır. Yükselteç aktarımı (A6) raporlanırken bu örnekler
    "gözlemde nominal" alt kutusunda ayrıca verilir (**K17a, kullanıcı kararı**; kural §7a).
- `carrier_under_carrier` için C/I üst sınırı, P6 §6'daki görünürlük ölçümüne göre PSD'de neredeyse görünmez
  bölgeyi kapsar. Bu bilinçli bir seçimdir: ayırt edilebilirlik sınırını ölçmek için (K9).

## 3. Bilinmeyen aileler (yalnız test)

| Aile | Kaynak | Ön kayıtlı grup (L12) | Gerekçe |
|---|---|---|---|
| `pulsed` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, yalnız zaman kapılı |
| `intermittent_bursts` | U1-dev/1 | **yakın** | Bilinen `cw` dalga biçimi, uzun ve düzensiz kapılı |
| `adjacent_satellite_downlink` | E1-dev/1 olayı (K16) | **yakın (K17, kullanıcı kararı)** | Bilinen `adjacent_satellite` ile aynı dalga biçimi; yalnız giriş noktası farklı (TWTA'dan geçmez). C/I_psd, bilinen uplink ASI ile **aynı dağılımdan** çekilir (seviye sabit, geometri değil; **K17d**, §7a) |
| `cid_overlay` | `geosim.cid` (ETSI TS 103 129) | **meşru — beklenen karar `clean`** | Bütün planlı taşıyıcıların altında yasal DVB-CID [VARSAYIM: hepsinde]. Girişim değildir; birleşik open-set sayısına girmez. Raporlananlar: `clean` kabulü, `carrier_under_carrier` deme oranı ve temizde yanlış alarm (CuC dedektörünün meşru taşıyıcı altı sinyale yanlış alarmı) |
| `wideband_noise` | U1-dev/1 | **eşdeğerlik-sınırlı** | Yükseltilmiş uplink gürültü tabanıyla gözlemsel olarak eşdeğer olabilir (P12); ayrı raporlanır, birleşik sayıya ağırlıklı katılmaz |

Gruplama bu tabloda **sonuçtan önce** sabitlenir. "Uzak" bir aile yoktur: bu bir bulgudur, yani GEO'daki
olası bilinmeyenlerin çoğu bilinen bir mekanizmanın varyantıdır.

## 4. Roller ve tohumlar

| Rol | Senaryo grupları | Tohum başlangıcı | Kullanım |
|---|---|---|---|
| train | 1500 (K17, kullanıcı kararı) | 3 000 000 | Ağırlık optimizasyonu; Mahalanobis istatistikleri |
| val-select | 150 | 3 100 000 | Yalnız checkpoint seçimi |
| val-calib | 150 | 3 150 000 | Yalnız ret eşiği ve alarm eşiği kalibrasyonu (yalnız bilinen sınıflar, K14) |
| test | 500 | 3 200 000 | Bilinen test + aynı gruplarda bilinmeyen aileler ve `cid_overlay` |
| test-matched | 150 | 3 300 000 | Yalnız seviye eşleşmiş ASI ↔ `unauthorized` kümesi (K17c, §7a); yalnız bu iki sınıf ve `clean` |

- Bir senaryo grubunun bütün sınıf varyantları (aynı planlar, link, kuplaj, faz gürültüsü ve gürültü akışları)
  tek roldedir.
- Tohum aralıkları A1, R1, U1 (900000–), D1 (1000000–) ve E1 (2000000–) aralıklarıyla çakışmaz. Bu kodda
  testle denetlenir.
- Bilinmeyen aile örnekleri yalnız test gruplarında üretilir; ayrı RNG ad alanı kullanılır.
- **Boyut:**
  - 2300 grup × 8 bilinen varyant;
  - test gruplarında + 5 test-yalnız varyant (4 bilinmeyen + `cid_overlay`);
  - 150 eşleşmiş grup × 3 varyant.
  - Toplam ≈ 21 300 çift-pol örnek, artı seviye eşleşmiş küme.
- **Süre:** örnek başına ≈ 2,5–3 s **[TAHMİN]**, yani ≈ 15–20 çekirdek-saat.
- **Çalıştırma (K17):** üretim bulutta (bu kap, parçalı ve doğrulanarak sürdürülebilir), eğitim kullanıcının
  GPU makinesinde. Veri Git dışında kalır; aktarım parmak iziyle doğrulanır.

## 5. Modeller ve yöntemler

- **Ana model:** küçük ResNet, beş kanal (§1); `co` görünümü eşleşmiş ablasyon olarak.
- **Sonradan skorlama:** MSP, energy, Mahalanobis (yalnız train embedding'leri).
- **Eğitim zamanı (D13, K17):** softmax çapraz entropi + prototip/merkez kaybı. ARPL kullanılmaz.
  - Merkez kaybı ağırlığı P6 ayarlarıyla sabit; arama yok.
  - Vekil bilinmeyen kullanılmaz (K14).
- **Ek gözlem kanalı (K9, K17):**
  1. Gözlemden hesaplanan iptal artığı (planın sembol hızıyla karar yönlü yeniden modülasyon). **Ana modelin
     girdisidir.**
  2. SCF dalı yalnız ablasyon A4b'dir.
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
| `adjacent_satellite` ↔ `unauthorized` | **Tasarım gereği karışabilir**; plan örtüşmesi zayıf ipucu, seviye güçlü ipucu | Plan maskesi var/yok, plan bozma; seviye eşleşmiş alt kutu C/I_psd 7–10 dB, komşuları 4–7 ve 10–13 dB (**K17c**, §7a) |
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

## 7a. Ön kayıtlı alt kutular ve plan sapması (K17a–d, kullanıcı kararları 2026-10-20)

Bu bölüm sonuçlardan **önce** yazıldı. Dilim sınırları test sonuçlarına bakılarak değiştirilmez.

**K17a — "Gözlemde nominal" aşırı sürme alt kutusu.** Amaç etiketin sınırını göstermek.
- Gözlenebilir: plan dışı spektral büyüme oranı, yani plan dışı kutulardaki güç / planlı taşıyıcı gücü.
  Eşik val-calib temiz sahnelerinin %95'lik değeridir; test verisi kullanılmaz.
- Bu eşiğin altında kalan `overdrive` örnekleri alt kutuya girer. Aynı tabloda şunlar yan yana verilir:
  - aynı gruplardaki `clean` örnekleri;
  - eşiğin hemen üstündeki `overdrive` örnekleri.
- Örnek başına sayısal tablo: IBO, OBO (yükselteç tablosundan), AM/PM çalışma noktası, plan dışı büyüme oranı
  ve model tahmini. EVM ve ACPR hesaplanmaz (zincirde yok); hesaplanmadığı yazılır.
- Temsilî spektrumlar için seçim kuralı: sabit tohumla rastgele 3 + 3 örnek. "En temiz" seçimi yapılmaz.
  Spektrumlar aynı eksen, ölçek ve çözünürlükle verilir; tam liste ekte.
- Kutu sayısı, n ve güven aralığıyla birlikte raporlanır.

**K17b — Plan sapması.** Simülatörde sapma operatör planındadır (model girdisi); yayınlanan sinyal değişmez.
- **Kaydırma, etiketi koruyan artırım:**
  - Eğitim örneklerinin %15'inde plan maskesi Δf ~ U(−0,5, +0,5) MHz kaydırılır. Sürekli dağılımlıdır;
    üç sabit ofset değildir.
  - İzleme kutusu 187,5 kHz olduğundan 0,5 MHz ≈ 2,7 kutudur. Kayma çözünürlükte görünür.
  - Doğrulama ve test maskeleri bozulmaz. A5 dilimleri ayrıca raporlanır.
- **"Fazla taşıyıcı" (yayında, planda yok):** spektrum ve plan bakımından `unauthorized` ile **gözlemsel
  olarak aynıdır**; operatör tanımında planda olmayan yayın yetkisizdir. Ayrı etiket tanımlanamaz (aynı girdi,
  iki etiket). `unauthorized` anlamı korunur; A5 `drop_one` dilimi olarak raporlanır.
- **"Eksik taşıyıcı" (planda var, yayında yok; taşıyıcı düşmesi):** gerçek bir arıza ve gözlemden ayırt
  edilebilir. Kullanıcının çok etiketli önerisine göre ikinci bir çıktıyla öğrenilir:
  `plan_consistency ∈ {tutarlı, planlı taşıyıcı yok}`. Bu çıktı ana etiketten bağımsızdır; her kombinasyon
  eğitimde temsil edilir. Toplam sapmalı örnek oranı %10–20.
  - Etki: tek etiket kuralı (A1 karar B) B2/1'de iki çıktıya genişler. Bu bir protokol değişikliğidir;
    A1 değişmez.
  - **Onaylandı (K17b, 2026-10-20):** fazla taşıyıcı `unauthorized` anlamını korur; eksik taşıyıcı ikinci
    çıktı `plan_consistency` ile öğrenilir.
  - Yükün sürüşü **sabit kazançtır (FGM; K17b, kullanıcı kararı)**: düşen taşıyıcı toplam giriş gücünü
    azaltır, IBO büyür ve IM azalır. Gerçekleşen IBO metadata'ya yazılır.

**K17c — Seviye eşleşmiş ASI ↔ `unauthorized` alt kutusu.**
- **Dilimler:** C/I_psd 7–10 dB ana dilim; 4–7 ve 10–13 dB komşu dilimler. Hepsi sonuçtan önce sabit.
- **Ana dağılım yetmez:** 500 test grubunda ana dağılımla 7–10 dB'ye ≈ 12 ASI örneği düşer (2000 çekilişten
  %2,5). `unauthorized` ise 10 dB'nin üstüne hiç çıkmaz. Bu yüzden ayrı bir **yalnız-test eşleşmiş küme**
  tanımlanır:
  - 150 grup, ayrı tohum ad alanı;
  - her grupta iki sınıf aynı C/I_psd ~ U(4, 13) dB, aynı sembol hızı ve roll-off, aynı modülasyon, aynı link C/N.
  - Eşleştirilemeyen tek değişken frekans yerleşimidir: ASI planla örtüşür, `unauthorized` boş aralıktadır.
    Bu sınıf tanımının kendisidir ve raporda yazılır.
  - Ana dağılımın 7–10 dB dilimi de n ile birlikte ayrıca verilir.
- **Raporlanacaklar:**
  - 2×2 ve tam karışıklık matrisi;
  - sınıf başına recall ve precision;
  - n ve senaryo bootstrap %95 aralığı;
  - aynı eksenli temsilî spektrumlar;
  - ana dağılım ve komşu dilimlerle karşılaştırma.
- **Kesişimler:** A5 plan bozmalı örnekler bu dilimde ayrıca raporlanır. `drop_one` ile `unauthorized`
  gözlemsel olarak aynıdır.
- **Rol:** bu küme eğitime, checkpoint seçimine ve eşik kalibrasyonuna girmez.

**K17d — `adjacent_satellite_downlink` bilinmeyeni: seviye sabit, geometri değil.**
- **Dağılım:** C/I_psd, bilinen uplink ASI ile aynı dağılımdan çekilir (`geosim.asi.draw_geometry`,
  14,25 GHz aralıkları). Böylece iki olay yalnız giriş noktasında ayrışır.
- **11,7 GHz geometrisi:** ayrıca bir duyarlılık satırı olarak raporlanır ve ölçülen C/I_psd dağılımı verilir.
  - Ön koşul: mevcut çap kümesinde 0,75 m, 11,7 GHz'de D/λ = 29 verir. Bu, S.465-6 uygulamasının 33,3 sınırının
    altındadır. Bu satır için çap kümesi 0,96 m'den başlar ya da Note 5 eklenir.
- **Simülatörde frekans:** model RF frekansını görmez; girdi transponder taban bandıdır. Frekans yalnız anten
  kazancından C/I'ye girer.
  - Bu yüzden "bilinmeyen frekans" ekseni bu simülatörde **tanımlı değildir**: LNB/filtre cevabı, yağmur
    sönümü ve bant kenarı modellenmez. Bu ayrıca yazılır.
  - Raporlanan tek eksen "bilinmeyen kaynak/giriş noktası"dır.
- **Kontrol:** aynı test gruplarındaki bilinen uplink ASI örnekleri. Senaryo, plan, link ve C/I_psd eşleşmiştir.
- **Koşul tablosu:** alt kutuya çap, desen, işaretleme hatası ve ΔEIRP yazılır.
- **Rol:** küme yalnız testtir; eşik ve ayarlar ona bakılarak seçilmez.

## 8. Ablasyonlar (her biri tek değişken)

1. **A0** co-only; **A1** + plan; **A2** + çift-pol (ana model).
2. **A3** doğrusal zincirle eğit, doğrusal olmayanda test (C3).
3. **A4** ana model − iptal artığı (dört kanal); **A4b** ana model + SCF.
4. **A5** plan bozma (bayat, kaydırılmış, eksik). Değerlendirme aracı A1 için hazır: `geoml.plan_shortcut` (bozmalar `shift_plus/minus`, `drop_one`, `phantom`, `authorize_intruder`); B2/1'e çift-pol maskelerle genişletilecek.
   - [A1 pilotu](../results/plan_shortcut_pilot.md): 0,5 MHz bayat plan temizde yanlış alarmı %3 → %93'e çıkarıyor.
   - B2/1 eğitiminde plan sapması: kaydırma etiketi koruyan artırımdır; eksik/fazla taşıyıcı ayrı ele alınır
     (**K17b**, §7a). A5 bozmaları test dilimleri olarak ayrıca raporlanır.
5. **A6** R1 yükselteçlerine aktarım.
6. **A7** FiLM koşullaması (maske kanalı yerine).
7. **A8** unknown aileleri ve leave-one-known-out.

Veri, eğitim bütçesi, eşik seçimi ve tohum protokolü bütün ablasyonlarda eşittir.

## 9. Hakem itirazları

| İtiraz | Yanıt / sınır |
|---|---|
| "ASI ve unauthorized aynı şey; sekiz sınıf yapay." | Kabul edilen sınır, ön kayıtlı (§6). Sonuç "plan örtüşmesi dışında ayırt edilemez" çıkarsa böyle raporlanır; birleşik etiketle ikinci bir değerlendirme (7 sınıf) ek tablo olarak verilir. |
| "Bilinmeyenler bilinenlerin varyantı; open-set kolaylaştırılmış ya da zorlaştırılmış." | Gruplama sonuçtan önce sabit; aile başına rapor; ayrıca leave-one-known-out rotasyonu, aile seçiminden bağımsız bir ölçüt verir. |
| "Bütün sayılar simülatör varsayımlarına (XPD, linewidth, C/I aralıkları) bağlı." | Kabul. Yer istasyonu XPD'si için kaynak var, diğerleri [VARSAYIM]. Duyarlılık kümeleri ayrı yalnız-test sürümü **R2-eval/1**'dedir (K17). B2/1 değişmez. Önerilen varyasyonlar (değerler R2-eval/1 kendi protokolüyle dondurulurken kesinleşir): uplink XPD (20, 25, 35 dB), uydu/alıcı linewidth (×0,1, ×10), CuC ve CW C/I kaydırması (±5 dB), ASI ΔEIRP = 0 dB ve işaretleme hatası = 0. Gerçek veri yok (DURUM §5.5). |

## 10. Değişiklik günlüğü

| Tarih | Değişiklik | Gerekçe |
|---|---|---|
| 2026-10-21 | Ayrı gözlem-alıcısı geliştirme kolu [P21](P21_b2_observed_receiver.md): `B2-features/1` + `B2-observed-dev/1`; kısa FIR alıcısı, iki-logit CE yardımcı çıktı, boyut başına ortalama merkez kaybı 0,01; %15 maskeye ±0,5 MHz artırımı ve shard akışı | PR #5'in `B2-feat/1`/P20 sürümü ve K18 adayı 0,005 toplam-boyut kaybı korunur; katsayılar farklı tanımlıdır, birbirinin yerine geçmez. Ayrı geliştirme ayarları pilot öncesi yazıldı; nihai B2 fiziksel/test protokolü değişmez |
| 2026-10-21 | Beşinci kanal gözlemden iptal artığı olarak `B2-feat/1` aşamasında kodlandı ([P20](P20_b2_cancellation_residual.md)): yalnız kalibre co-pol IQ + co-pol operatör planı girdi; karar yönlü yeniden modülasyon, `obs-cancel/1` ayarları isteğe bağlanır. **Belirtilmemiş hiperparametre tamamlandı (K18 adayı, araştırmacı onayı bekler):** merkez kaybı ağırlığı **0,005**, plan-tutarlılık BCE ağırlığı 1,0; her ikisi B2 eğitiminden önce `configs/b2_feat.json`'da donduruldu, arama yapılmadı. Checkpoint seçimi yalnız bilinen sınıf makro-F1 ile; yardımcı çıktı seçime girmez. Bölünme, sınıf, eşik ve gruplama değişmedi | §5 K9 ve §7a K17b'nin uygulanması; P6 merkez kaybı değeri vermiyordu, P19 bunun eğitimden önce yazılmasını istiyordu |
| 2026-10-21 | Bilinen fiziksel gözlem aşaması `B2-base/1` olarak ayrıldı; iptal/unknown/model tamamlanmadan B2/1 tamamlandı denmez. K17b'nin %10–20 aralığı içinde taşıyıcı düşmesi Bernoulli olasılığı %15 seçildi; iki feed'den tek taşıyıcı, tek kalan co taşıyıcı hariç; CuC kurbanı aktif olmalı. Bütün sınıflar için ortak plan yalnız açık yerleşim olanaksızlığında en çok 64 çekilişle yenilenir; koşullama metadata'ya yazılır | Dondurulmuş fiziksel olayları tam eşleşmiş sekizli sahnelere bağlamak; nominal kazancı ve tarihsel sürümleri korumak. Sayısal uygulama seçimleri fiziksel pilot sonuçlarından önce kaydedildi |
| 2026-10-20 | Taslak | — |
| 2026-10-20 | **Donduruldu (K17).** Son kararlar: prototip/merkez kaybı; iptal artığı ana girdide (SCF yalnız A4b); CID için gerçek DVB-CID üreteci ve yalnız-test `cid_overlay` ailesi (beklenen `clean`); ASI dağılımları olduğu gibi + R2-eval/1 duyarlılığı; üretim bulutta, eğitim kullanıcıda | Kullanıcı yanıtları; CID seviyesi ETSI TS 103 129 Tablo 6 ile doğrulandı |
| 2026-10-20 | K17 alt kararları işlendi: CuC 5–30 dB; roller 1500/150/150/500; downlink ASI yakın; LOKO 3 tohum | Kullanıcı yanıtları (dondurma öncesi) |
| 2026-10-20 | K17a–d kararları §7a'ya yazıldı: gözlemde nominal aşırı sürme alt kutusu; kaydırma artırımı (%15, sürekli ±0,5 MHz); fazla taşıyıcı = `unauthorized` (gözlemsel olarak aynı); eksik taşıyıcı için ikinci çıktı `plan_consistency` ve sabit kazanç (onaylandı); seviye eşleşmiş ASI/unauthorized kümesi; downlink ASI'de seviye sabit | Kullanıcı yanıtları; ana dağılımda 7–10 dB ASI sayısı ≈ 12/500 |
| 2026-10-20 | Aşırı sürme etiketi açık konusu ve A5 plan sapması artırımı önerisi eklendi | [R1 pilotu](../results/r1_pilot.md), [A5 pilotu](../results/plan_shortcut_pilot.md) |
| 2026-10-20 | `adjacent_satellite` parametreleri kaynaklı geometriyle değiştirildi (eski: örtüşme %20–80, PSD −15…−3 dB [VARSAYIM]) | ITU-R S.1428-1/S.580-6/S.465-6, FCC iki derece, ITU BR uplink C/I yöntemi; [ASI ölçümü](../results/asi_visibility.md) |
