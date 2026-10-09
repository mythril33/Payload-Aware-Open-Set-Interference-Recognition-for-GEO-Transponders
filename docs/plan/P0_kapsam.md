# P0 — Kapsam ve çerçeve

Durum: **KAPANDI** · 2026-10-09 · Girdi: `00_ana_plan.md` v0.3

## 1. Onaylanan çerçeve

| Konu | Karar | Kaynak |
|---|---|---|
| Çıktı | Ders projesi, sonra makaleye genişletme | Kullanıcı |
| Takvim | Sabit teslim tarihi yok; öncelik en kısa sürede anlamaya ve üretmeye başlamak | Kullanıcı |
| Depo | `mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders` | Kullanıcı |
| Gerçek veri | Operatör verisi yok, masaüstü ölçüm yok | Kullanıcı |
| Veri biçimi | Simülatör IQ üretir; model girdisi IQ'dan türetilen spektrogram | Karar (açık veri taraması sonucu) |
| Donanım | Tek GPU'lu iş istasyonu | **[VARSAYIM]** |

## 2. Ana katkı

- **Ana bulgu: C3 (payload gap).** Doğrusal olmayan zincir olmadan eğitilen modelin, zincir varken ne kadar bozulduğu.
- **Altyapı: C1 (üretici).** C3'ün ön koşulu.
- **Yöntem: C2.** Kademe A'da yalnızca plan maskesi; çapraz pol, open-set ve identifiability analizi Kademe B'de.

## 3. Kademe A kapsamı (ilk üretilecek şey)

| Öğe | Kademe A |
|---|---|
| Zincir | Tek polarizasyon, tek transponder: taşıyıcı üretici → uplink gürültüsü → IMUX → TWTA → OMUX → downlink gürültüsü |
| Yükleme | Çok taşıyıcılı FDM, IBO süpürmesi |
| Sınıflar | clean, CW, swept CW, unauthorized carrier, overdrive IM |
| Girdi | 2 kanal: spektrogram + taşıyıcı planı maskesi |
| Model | Tek ResNet |
| Baseline | CA-CFAR enerji dedektörü |
| Deney | Doğrusal zincirle eğit → doğrusal olmayan zincirde test et; görülmemiş IBO'da test et |

**Düzeltme (ana plan v0.3'e göre):** plan maskesi Kademe B'den Kademe A'ya alındı. Maske olmadan "unauthorized carrier" planlı bir taşıyıcıdan ayırt edilemez; sınıf tanımsız kalır. Maske, senaryo üst verisinden üretildiği için maliyeti düşüktür.

## 4. Kademe A'da yapılmayacaklar

- Çift polarizasyon, cross-pol sınıfı
- Adjacent-satellite ve carrier-under-carrier sınıfları
- Faz gürültüsü
- Open-set reddi (MSP, energy, Mahalanobis) ve bilinmeyen sınıflar
- Spektrogram transformer, cyclic özellik dalı
- Dış veri setleriyle karşılaştırma (SnT, OpenDPD, DARCY, TorchSig)
- Tam DVB-S2 çerçeveleme (BBFRAME, LDPC/BCH, PL başlığı): yalnızca modülasyon + SRRC şekillendirme **[VARSAYIM — P2'de doğrulanacak]**

## 5. Hızlı yol — faz sırası değişti

Ana plandaki sıra tüm planlamayı koddan önce bitiriyordu. Yeni sıra, her fazın yalnızca Kademe A dilimini planlayıp hemen uygular:

1. **P2-A** sistem modeli şartnamesi (yalnızca Kademe A blokları)
2. **P4-A** simülatör iskeleti + doğrulama testleri → **kod: doğrusal tek taşıyıcı, sonra IMUX/OMUX, TWTA, çok taşıyıcı**
3. **P3-A** beş sınıfın parametre ve etiket kuralları → **kod: girişimci üreteçleri**
4. **P5-A** split protokolü — eğitimden önce dondurulur
5. **P6-A / P7-A** ResNet + CA-CFAR + ilk payload-gap ölçümü
6. Kademe B'den önce: P1 (literatür), P8 (dış veri), sonra P2–P7'nin B dilimleri, P9

Kabul edilen risk: P1 ertelendiği için benzer bir çalışmanın varlığı Kademe A bitene kadar bilinmeyecek. Kademe A ders çıktısı olarak her durumda geçerli; risk yalnızca makale iddiasını etkiler.

## 6. Kararlar

| Karar | Gerekçe | Reddedilen alternatif |
|---|---|---|
| C3 ana bulgu | En az bileşenle ölçülebilir, özgün sonuç | C2'yi (tam tanıyıcı) ana katkı yapmak: 8 sınıf + çift pol gerektirir |
| Hızlı yol sırası | Kullanıcı önceliği: erken üretim; her dilim küçük ve doğrulanabilir | Tüm P1–P9 planlamasını koddan önce bitirmek |
| Plan maskesi Kademe A'da | "Unauthorized carrier" sınıfı maskesiz tanımsız | Sınıfı Kademe B'ye ertelemek |
| Makale "simülasyon çalışması" olarak konumlanır | Gerçek veri ve ölçüm yok | Operasyonel performans iddiası |

## 7. Açık sorular

- GPU belleği ve disk alanı (veri seti boyut bütçesi için; P5-A'da gerekli)
- Hedeflenen bant ve transponder genişliği (Ku, 36 MHz varsayılacak **[VARSAYIM]**; P2-A'da sabitlenir)

## 8. P2-A'nın bu fazdan aldığı girdi

Zincir blokları (§3), tek pol, çok taşıyıcı, IBO süpürmesi, IQ çıktısı, DVB-S2 çerçevelemesiz dalga biçimi varsayımı.
