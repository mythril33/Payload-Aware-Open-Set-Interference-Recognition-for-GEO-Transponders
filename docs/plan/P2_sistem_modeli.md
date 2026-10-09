# P2-A — Sinyal ve sistem modeli şartnamesi (Kademe A)

Durum: **KAPANDI** (A, B, C kararları onaylandı; §10'daki uygulama düzeltmeleriyle) · 2026-10-09 · Girdi: `P0_kapsam.md`

Kapanış kriteri: zincirin her bloğu için denklem, parametre aralığı, kaynak ve birim yazılı; sensör modeli (örnekleme hızı, süre, çıktı) sabit.

Etiketler: **[STANDART]** = EN 302 307-1 V1.4.1 metninden bu oturumda doğrulandı · **[HESAP]** = bu oturumda sayısal olarak hesaplandı · **[VARSAYIM]** = proje tercihi, kaynağı yok · **[DOĞRULANACAK]** = bilgiye dayalı, kaynaktan teyit edilmedi.

---

## 0. Onaylanan üç karar

| # | Karar | Neden | Reddedilirse |
|---|---|---|---|
| A | **Aralıklı anlık görüntü sensörü.** Spektrogramın her satırı 43 µs'lik kısa bir IQ kaydından hesaplanır; satırlar arası 10 ms boşluk vardır. 128 satır = 1,28 s gözlem. | Kesintisiz 1,28 s IQ, 288 MHz'te 3,7×10⁸ örnek eder; dizüstünde binlerce senaryo üretilemez. Aralıklı kayıt 1,6×10⁶ örnekle aynı zaman ölçeğini verir. Gerçek FFT tabanlı izleme alıcıları da böyle çalışır. | Kesintisiz kayıt: gözlem süresi ~0,7 ms'ye düşer; yavaş süpürülen CW ayırt edilemez. |
| B | **Sensör mutlak ve sabit:** 36 ve 72 MHz transponder için aynı 96 MHz örnekleme, aynı 187,5 kHz çözünürlük. | Sensör transponder genişliğiyle ölçeklenirse iki durum normalize birimlerde özdeş olur ve "görülmemiş bant genişliği" testi anlamını yitirir. | Ölçeklenen sensör: bant genişliği testi plandan çıkar. |
| C | **Kademe A'da yükselteç = Saleh modeli, IMUX/OMUX = parametrik süzgeç.** DVB-S2 Ek H.7 eğrileri kullanılmaz. | Ek H.7 eğrilerine sayısal tablo olarak ulaşamadım (standart PDF'inin yalnızca ilk bölümü okunabildi; ikincil kaynaklar eğrileri yalnızca şekil olarak veriyor). Saleh analitik ve tam yeniden üretilebilir. | Ek H.7 şekillerini elle sayısallaştırmak: Kademe B işi olarak park listesinde. |

---

## 1. Ortak kurallar

| Konu | Tanım |
|---|---|
| Gösterim | Karmaşık temel bant; merkez frekans = transponder merkezi |
| Simülasyon örnekleme hızı | f_s = 288 MHz, her iki transponder genişliği için **[VARSAYIM]** |
| Örtüşme payı | f_s = 8B (36 MHz) ve 4B (72 MHz). n. derece ürünün bant içine katlanmaması için f_s ≥ (n+1)B/2 gerekir; 4B, 7. dereceye kadar korur **[HESAP]** |
| Transponder | B ∈ {36, 72} MHz; kanal aralığı 40 / 80 MHz. 36/40 değeri ikincil kaynakta Ek H.7 referans tasarımı olarak geçiyor **[DOĞRULANACAK]** |
| Güç | P = E[\|x\|²]; genlikler Saleh'in normalize giriş birimiyle ifade edilir |
| Sayı tipi | complex64 |

---

## 2. Zincir blokları

Sıra: taşıyıcı üretici → uplink toplama (+ girişimci) → uplink gürültüsü → IMUX → kanal yükselteci → TWTA → OMUX → downlink gürültüsü → izleme alıcısı.

### 2.1 Taşıyıcı üretici

| Parametre | Değer / aralık | Etiket |
|---|---|---|
| Modülasyon | QPSK, 8PSK, 16APSK (4+12), 32APSK (4+12+16) | [STANDART] |
| 16APSK halka oranı γ = R2/R1 | 3,15 (2/3) · 2,85 (3/4) · 2,75 (4/5) · 2,70 (5/6) · 2,60 (8/9) · 2,57 (9/10) | [STANDART] Tablo 9 |
| 32APSK γ1 = R2/R1, γ2 = R3/R1 | 2,84/5,27 (3/4) · 2,72/4,87 (4/5) · 2,64/4,64 (5/6) · 2,54/4,33 (8/9) · 2,53/4,30 (9/10) | [STANDART] Tablo 10 |
| Halka üzerindeki nokta açıları | Standart şekillerinden alınacak | [DOĞRULANACAK] |
| Darbe biçimi | Karekök yükseltilmiş kosinüs, α ∈ {0,20; 0,25; 0,35} | [STANDART] |
| Süzgeç uzunluğu | ±16 sembol | [VARSAYIM] |
| Sembol hızı R_s | f_s/R_s tamsayı ve ≥ 8 olan kümeden: 1 · 1,5 · 2 · 2,4 · 3 · 3,6 · 4 · 4,5 · 4,8 · 6 · 7,2 · 8 · 9 · 9,6 · 12 · 14,4 · 18 · 24 · 28,8 · 36 Mbaud | [VARSAYIM] |
| İşgal edilen bant | R_s(1+α) | tanım |
| Semboller | Düzgün dağılımlı rastgele (FEC yok, bkz. `P0_kapsam.md`) | karar |

Tamsayı örnek/sembol kısıtı yeniden örnekleyici yazmayı gereksiz kılar. Girişimci taşıyıcılar aynı kümeden çekilir; böylece sembol hızı etiketi ele vermez.

**PL çerçevesi (anahtarla açılır, ikinci adım):**

| Öğe | Değer | Etiket |
|---|---|---|
| PL başlığı | 90 sembol = 26 SOF + 64 PLS kodu, π/2-BPSK | [STANDART] 5.5.2 |
| Dilim | 90 sembol | [STANDART] |
| Pilot bloğu | 36 sembol, her 16 dilimde bir | [STANDART] |
| XFECFRAME (normal) | 32 400 / 21 600 / 16 200 / 12 960 sembol (QPSK / 8PSK / 16APSK / 32APSK) | [STANDART] 5.4 |
| XFECFRAME (kısa) | 8 100 / 5 400 / 4 050 / 3 240 sembol | [STANDART] 5.4 |
| PL karıştırma | Başlık karıştırılmaz; dizi tanımı 5.5.4'ten alınacak | [DOĞRULANACAK] |

### 2.2 Taşıyıcı planı (çok taşıyıcılı yükleme)

| Parametre | Değer / aralık | Etiket |
|---|---|---|
| Taşıyıcı sayısı | 1–8 (36 MHz), 1–12 (72 MHz) | [VARSAYIM] |
| Doluluk (işgal edilen bant / B) | %50–95 | [VARSAYIM] |
| Koruma aralığı | komşu taşıyıcılar arası ≥ 0,05 × küçük olanın R_s'i | [VARSAYIM] |
| Güç dağılımı | Eşit güç yoğunluğu (güç ∝ R_s), taşıyıcı başına ±2 dB düzgün sapma | [VARSAYIM] |
| Yerleşim | Tüm taşıyıcılar ±B/2 içinde | tanım |

Her iki transponder genişliği aynı mutlak sembol hızı kümesini kullanır: 72 MHz'lik transponder daha çok veya daha geniş taşıyıcı taşır.

Çıktı üst verisi: taşıyıcı başına merkez frekans, R_s, α, modülasyon, güç. Plan maskesi bundan üretilir (§3.3).

### 2.3 Uplink toplama ve gürültü

- x_up = Σ taşıyıcılar + girişimci (varsa) + n_up
- Girişimci giriş noktası: Kademe A'daki dış girişimcilerin tümü (CW, swept CW, unauthorized carrier) **uplink'ten** girer, yani IMUX ve TWTA'dan geçer. Parametreleri P3-A'da.
- n_up: karmaşık beyaz Gauss gürültüsü, varyans = N0_up · f_s
- Tanım: (C/N)_up = toplam taşıyıcı gücü / (N0_up · B)
- Aralık: (C/N)_up ∈ [15, 30] dB **[VARSAYIM]**

### 2.4 IMUX

Parametrik alçak geçiren eşdeğer: eliptik, 6. derece, 0,1 dB dalgalanma, 40 dB durdurma, kesim ±B/2. İkinci derece bölümler halinde, nedensel uygulanır (grup gecikmesi korunur).

| Frekans kayması | Göreli grup gecikmesi, B = 36 MHz | B = 72 MHz | Genlik |
|---|---|---|---|
| 0 | 0 ns | 0 ns | −0,1 dB |
| ±0,25 B | +6,8 ns | +3,6 ns | −0,1 dB |
| ±0,40 B | +28,7 ns | +15,0 ns | 0 dB |
| ±0,45 B | +48,1 ns | +25,6 ns | −0,1 dB |
| ±0,50 B (bant kenarı) | +136,5 ns | +75,4 ns | −0,1 dB |
| ±0,555 B (komşu kanal kenarı) | — | — | −15,3 / −17,6 dB |

Tüm değerler **[HESAP]** (f_s = 288 MHz'te tasarlanan sayısal süzgeçten). Bu bir proje modelidir; DVB-S2 Ek H.7 eğrisi değildir. Derece, dalgalanma ve kesim konfigürasyondan değiştirilebilir.

### 2.5 Kanal yükselteci

- Kademe A: sabit kazanç kipi (FGM). Kazanç, **girişimsiz nominal yükleme** için hedef IBO'yu verecek şekilde bir kez ayarlanır ve senaryo boyunca sabit kalır.
- Sonuç: uplink girişimcisi toplam giriş gücünü artırır, TWTA'yı doyuma iter ve istenen taşıyıcılarla intermodülasyon üretir. Projenin "payload-aware" iddiasının fiziksel dayanağı budur.
- Otomatik seviye denetimi (ALC) Kademe B'ye bırakıldı.

### 2.6 TWTA (Saleh, belleksiz)

- A(r) = α_a r / (1 + β_a r²) · Φ(r) = α_φ r² / (1 + β_φ r²) · y = A(\|x\|) · exp(j(∠x + Φ(\|x\|)))
- Katsayılar: α_a = 2,1587 · β_a = 1,1517 · α_φ = 4,0033 · β_φ = 9,1040 — Saleh 1981'in yaygın aktarılan değerleri **[DOĞRULANACAK: makaleden]**

| Büyüklük | Değer | Etiket |
|---|---|---|
| Doyum giriş genliği r_sat = 1/√β_a | 0,9318 | [HESAP] |
| Doyum çıkış genliği A_max | 1,0058 | [HESAP] |
| Doyumda AM/PM | 22,4° | [HESAP] |
| AM/PM asimptotu α_φ/β_φ | 25,2° | [HESAP] |
| Doyumdaki kazanç sıkışması | 6,02 dB | [HESAP] |

Geri çekilme tanımları (tek taşıyıcı doyumuna göre):
- IBO = 10 log₁₀( r_sat² / E[\|x\|²] ) · OBO = 10 log₁₀( A_max² / E[\|y\|²] )

Sabit zarflı tek ton için IBO → OBO: 0 → 0,00 dB · 3 → 0,51 dB · 6 → 1,93 dB · 10 → 4,81 dB · 15 → 9,25 dB **[HESAP]**. Çok taşıyıcılı sinyalde OBO farklı çıkar; P4-A'da ölçülecek.

- IBO süpürme aralığı: [0, 15] dB **[VARSAYIM]**. "Nominal" ve "overdrive" sınırı P3-A'da belirlenir.
- **Doğrusal karşılaştırma zinciri** (payload-gap deneyi için): aynı zincir, TWTA yerine küçük sinyal kazancı α_a ile doğrusal yükselteç; IMUX/OMUX yerinde kalır.

### 2.7 OMUX

Parametrik alçak geçiren eşdeğer: Chebyshev tip I, 4. derece, 0,1 dB dalgalanma, kesim ±0,55 B.

| Frekans kayması | Göreli grup gecikmesi, B = 36 MHz | B = 72 MHz |
|---|---|---|
| ±0,25 B | +2,1 ns | +1,3 ns |
| ±0,40 B | +4,4 ns | +2,8 ns |
| ±0,50 B | +10,8 ns | +6,8 ns |

**[HESAP]**; IMUX ile aynı uyarı geçerli.

### 2.8 Downlink gürültüsü

- y_mon = y_OMUX + n_dn, varyans = N0_dn · f_s
- Tanım: (C/N)_dn = OMUX çıkışında ±B/2 içindeki toplam güç / (N0_dn · B)
- Aralık: [10, 25] dB **[VARSAYIM]**
- Kademe A'da downlink'ten giren girişimci yok.

---

## 3. İzleme alıcısı (sensör) modeli

### 3.1 Kayıt

| Parametre | Değer | Etiket |
|---|---|---|
| Alıcı örnekleme hızı | 96 MHz (simülasyon hızından 3'e seyreltme, örtüşme önleyici süzgeçle) | [VARSAYIM] |
| Anlık görüntü uzunluğu | 4096 alıcı örneği = 42,7 µs = 12 288 simülasyon örneği | [VARSAYIM] |
| Isınma payı | Her görüntünün başına 2048 simülasyon örneği eklenir ve atılır (süzgeç geçici rejimi) | [VARSAYIM] |
| Görüntü sayısı | 128 | [VARSAYIM] |
| Görüntüler arası süre Δt | 10 ms (konfigüre edilebilir) → 1,28 s gözlem | [VARSAYIM] |

Yavaş zaman: taşıyıcı sembolleri her görüntüde bağımsız çekilir. Girişimcinin frekansı ve açık/kapalı durumu görüntüden görüntüye t_k = k·Δt'ye göre evrilir; görüntü içinde de sürekli evrilir.

### 3.2 Spektrogram

| Parametre | Değer | Etiket |
|---|---|---|
| Satır başına kestirim | Welch: 512 noktalı FFT, Hann, %50 örtüşme, 15 ortalama | [VARSAYIM] |
| Frekans çözünürlüğü | 187,5 kHz | [HESAP] |
| Çıktı | 128 × 512, dB, float32; frekans ekseni −48…+48 MHz | tanım |
| Normalizasyon | P6-A'da belirlenir | — |

### 3.3 Plan maskesi

1 × 512 vektör, 128 satıra yinelenir: her frekans kutusu için planlı taşıyıcının beklenen güç yoğunluğu (dB), plansız kutularda taban değer. Yalnızca §2.2'deki **planlı** taşıyıcılardan üretilir; girişimci maskeye girmez.

### 3.4 Senaryo başına çıktı

- Spektrogram (128 × 512) ve plan maskesi
- Üst veri: tüm blok parametreleri, taşıyıcı planı, girişimci parametreleri, sınıf etiketi, rastgele tohum
- IQ anlık görüntüleri isteğe bağlı saklanır (128 × 4096 complex64 ≈ 4,2 MB/senaryo)

### 3.5 Maliyet

| Büyüklük | Değer | Etiket |
|---|---|---|
| Senaryo başına simülasyon örneği | 1,57 × 10⁶ (12,6 MB complex64) | [HESAP] |
| IMUX + TWTA + OMUX süresi | 0,19 s (bu oturumdaki bulut makinesinde, tek çekirdek) | [HESAP] |
| Tüm zincir, dizüstünde | < 1 s/senaryo bekleniyor; P4-A'da ölçülecek | [VARSAYIM] |
| Saklanan spektrogram | 256 KB/senaryo → 20 000 senaryo ≈ 5 GB | [HESAP] |

---

## 4. Blok başına doğrulama testleri (P4-A'ya girdi)

| # | Test | Geçme ölçütü |
|---|---|---|
| T1 | Tek taşıyıcı, doğrusal, gürültüsüz: −3 dB bant genişliği ve işgal edilen bant | R_s ve R_s(1+α) değerlerinden sapma ≤ %2 |
| T2 | Aynı sinyal, eşleşmiş süzgeç sonrası EVM | ≤ %1 |
| T3 | Ölçülen (C/N)_up ve (C/N)_dn | Konfigürasyondan sapma ≤ 0,2 dB |
| T4 | IMUX/OMUX grup gecikmesi (faz türevinden) | §2.4 ve §2.7 tablolarından sapma ≤ 1 ns |
| T5 | Tek ton süpürmesi: AM/AM ve AM/PM | Saleh denkleminden sapma ≤ 0,01 dB ve ≤ 0,1° |
| T6 | Tek ton IBO → OBO | §2.6'daki beş değerden sapma ≤ 0,02 dB |
| T7 | İki ton: IM3 ürünleri 2f₁−f₂ ve 2f₂−f₁'de | Frekans hatası ≤ 1 kutu |
| T8 | İki ton, küçük sinyal bölgesi (IBO 30–35 dB): C/IM3 eğimi | 2 ± 0,05 dB/dB; çalışma aralığında (IBO 3–8 dB) 1,0–1,5 dB/dB |
| T9 | Çok taşıyıcı, çentikli yükleme: C/IM'in IBO'ya göre değişimi | Tekdüze artan |
| T10 | Örtüşme: f_s = 288 ve 576 MHz'te bant içi spektrum farkı | ≤ 0,1 dB |
| T11 | Seyreltme ve Welch: bilinen güçte beyaz gürültü | Kestirilen yoğunluk hatası ≤ 0,2 dB |
| T12 | Tohum tekrarlanabilirliği | Aynı tohum → bit düzeyinde aynı çıktı |

---

## 5. Hakem itirazları ve yanıtlar

| İtiraz | Yanıt |
|---|---|
| "Saleh belleksizdir ve tek bir tüpe uydurulmuştur; gerçek TWTA'yı temsil etmez." | Kabul. Kademe A iddiası "doğrusal olmayan zincirin etkisi"dir, belirli bir tüpün değil. Kademe B: Ek H.7 eğrileri ve ölçülmüş yükselteç verisiyle "görülmemiş yükselteç" testi. |
| "43 µs'lik anlık görüntü, taşıyıcı istatistiğini yakalamaz." | 1 Mbaud'luk en yavaş taşıyıcı görüntü başına yalnızca ~43 sembol verir; spektral kestirim gürültülü olur. Risk kaydına alındı; T11'e ek olarak P4-A'da en düşük R_s için kestirim varyansı ölçülecek, gerekirse alt sınır 2 Mbaud'a çekilir veya görüntü uzatılır. |
| "Tek transponder modeli komşu kanal sızıntısını yok sayar; 36 MHz durumunda 96 MHz'lik görüş alanının çoğu boştur." | Kabul edilen sınırlama. Komşu transponderler Kademe B park listesinde. |

---

## 6. Kararlar

| Karar | Gerekçe | Reddedilen alternatif |
|---|---|---|
| f_s = 288 MHz, iki genişlik için ortak | Tek kod yolu; 7. dereceye kadar örtüşme koruması | Genişliğe göre ölçeklenen f_s |
| Tamsayı örnek/sembol kümesi | Yeniden örnekleyici gerekmez, kesin | Keyfi sembol hızı (çok fazlı yeniden örnekleyici) |
| Sabit kazanç kipi | Girişimcinin yükselteci doyuma itmesi modellenir | ALC: bu etkiyi kısmen gizler |
| Uplink girişimi | Girişimci doğrusal olmayan zincirden geçer; C3 için gerekli | Downlink girişi: Kademe B |
| Tek transponder (ana plan K3) | Kademe A kapsamı | Çok transponderli görünüm |

## 7. Açık sorular

- §0'daki A, B, C kararlarının onayı
- Halka nokta açıları, PL karıştırma dizisi, Saleh katsayıları: kaynaktan teyit
- En düşük sembol hızı (1 Mbaud) kısa görüntüde yeterli mi: P4-A ölçümü

## 8. Park listesi (bu fazın dışında)

- Ek H.7 eğrilerinin sayısallaştırılması; standardın tam PDF'i gerekiyor
- Faz gürültüsü maskesi (Ek H.8), çift polarizasyon, ALC, komşu transponderler
- Cyclic dalı için daha uzun kesintisiz IQ kaydı gereksinimi

## 9. Sonraki fazın bu fazdan aldığı girdi

P4-A: §1–§3 modül sınırlarını, §4 test listesini verir. P3-A: girişimci giriş noktası (uplink, IMUX öncesi), yavaş zaman modeli (§3.1) ve IBO tanımı (§2.6).

## 10. Uygulama sırasında yapılan düzeltmeler (2026-10-09)

| Madde | Şartnamedeki | Uygulanan | Neden |
|---|---|---|---|
| T8 | Eğim 2 dB/dB, IBO ≥ 15 dB | 2 dB/dB yalnızca IBO ≳ 30 dB'de; ölçülen: 15→20 dB arası 1,50, 20→25 arası 1,81, 30→35 arası 1,98, çalışma aralığında (3→8 dB) 1,25 dB/dB | Saleh'in AM/PM terimi (β_φ = 9,1) yüksek dereceli ürünleri geç söndürüyor. "Geri çekilme başına 2 dB" kuralı çalışma aralığında geçerli değil. |
| §3.1 ısınma payı | 2048 simülasyon örneği | 2304 (= 768 alıcı örneği) | 3'e seyreltmede tamsayı olması için |
| §2.8 (C/N)_dn | ±B/2 içindeki güç | OMUX çıkışındaki toplam güç | OMUX bant dışını zaten bastırıyor; ölçüm basitleşiyor |
| §2.5 nominal güç | Girişimsiz yükleme | Yalnızca taşıyıcı gücü (gürültü hariç); gerçekleşen IBO üst veriye yazılır | Belirlenimci kazanç |
| §5, 2. itiraz | 1 Mbaud taşıyıcıda kestirim gürültülü olabilir | Ölçüldü: kutu başına sapma 0,92 dB (beyaz gürültüde 1,16 dB); bant gücü sapması 0,45 dB (12 Mbaud'da 0,17 dB) | 1 Mbaud alt sınırı korunur |
| §3.5 süre | < 1 s/senaryo bekleniyor | Bulut makinesinde ölçülen: 1,9 s (36 MHz), 2,6 s (72 MHz) | Dizüstü ölçümü hâlâ yok |

## 11. Kaynak taraması sonrası değişiklikler (2026-10-09)

Ayrıntı: `kaynak_transponder_modeli.md`.

- **§2.4 ve §2.7 değişti.** Varsayılan süzgeçler artık TR 102 376-2 referans süzgeçlerinin yayımlanmış Chebyshev II yaklaşımı (Dimitrov 2016), frekansta B/36 ile ölçeklenir. Önceki eliptik ve Chebyshev I süzgeçler `filter_model="generic"` olarak duruyor; §2.4 ve §2.7'deki tablolar o modele aittir.

| Kayma | IMUX grup gecikmesi, 36 MHz | 72 MHz | OMUX, 36 MHz | 72 MHz |
|---|---|---|---|---|
| ±0,25 B | +4,9 ns | +2,4 ns | +4,0 ns | +1,7 ns |
| ±0,40 B | +20,4 ns | +9,5 ns | +16,2 ns | +6,7 ns |
| ±0,45 B | +35,8 ns | +16,4 ns | — | — |
| ±0,50 B | +64,7 ns | +30,9 ns | +30,8 ns | +15,1 ns |

  36 MHz'te genlik: IMUX ±18 MHz'te −1,2 dB, ±23 MHz'te −34 dB; OMUX ±18 MHz'te −2,1 dB, ±28,6 MHz'te −38 dB **[HESAP]**. Makale örnekleme hızını vermiyor; sayısal tasarım 288 MHz'te yapıldığı için bant kenarı değerleri yazarınkinden biraz farklı olabilir (144 ve 576 MHz'te IMUX'un ±18 MHz kazancı −0,7 ve −1,3 dB çıkıyor).
- **Etiketi [STANDART]'a yükselenler:** PL başlığının karıştırılmaması (5.5.4), APSK halka açıları, 36/40 MHz referansı ve ölçekleme kuralı (H.7, TR 102 376-2 4.4.1.2).
- **TWTA değişmedi:** referans eğriler yalnızca şekil olarak yayımlanmış; Saleh katsayıları hâlâ **[DOĞRULANACAK]**.
