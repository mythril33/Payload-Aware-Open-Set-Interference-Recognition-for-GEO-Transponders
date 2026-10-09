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
| Donanım | GPU var; alt sınır standart bir dizüstü. Üretim ve eğitim dizüstünde çalışacak boyutta tasarlanır | Kullanıcı |
| Transponder genişliği | 36 MHz ve 72 MHz; genişlik bir konfigürasyon parametresidir | Kullanıcı |

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
- DVB-S2 FEC zinciri (BBFRAME, BCH, LDPC, bit serpiştirme): yapılmaz. Yük sembolleri rastgele üretilir.

**DVB-S2 dalga biçimi kararı (2026-10-09):** "FEC'siz fiziksel katman çerçevesi". Yapılır: takımyıldız eşleme, PL başlığı (SOF + PLS kodu), isteğe bağlı pilot blokları, PL karıştırma, SRRC. Gerekçe: izleme alıcısı demodülasyon yapmaz; kodlanmış ve karıştırılmış bitler istatistiksel olarak rastgele bitlerden ayırt edilemez, bu yüzden FEC spektrumu ve zarf dağılımını (dolayısıyla TWTA tepkisini) değiştirmez. Çerçeve yapısı ise döngüsel-durağan imza bırakır ve Kademe B'deki cyclic dalı için gereklidir. Sıra: önce çerçevesiz sürüm doğrulanır, PL çerçevesi bir anahtar olarak eklenir. Sembol sayıları P2-A'da EN 302 307-1'e karşı doğrulanacak **[DOĞRULANACAK]**.

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

- Bant: Ku varsayılıyor **[VARSAYIM]**. Karmaşık temel bant modelinde bant yalnızca gürültü ve faz gürültüsü parametrelerini etkiler; P2-A'da sabitlenir.
- 36/72 MHz ayrımı "görülmemiş bant genişliği" testini doğrudan verir (birinde eğit, diğerinde test et); P5-A'da karara bağlanır.

## 8. P2-A'nın bu fazdan aldığı girdi

Zincir blokları (§3), tek pol, çok taşıyıcı, IBO süpürmesi, IQ çıktısı, DVB-S2 çerçevelemesiz dalga biçimi varsayımı.
