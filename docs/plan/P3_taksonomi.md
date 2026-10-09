# P3-A — Sınıf taksonomisi ve girişimci üreteçleri (Kademe A)

Durum: **KAPANDI** (iki varsayılan karar veto edilebilir, §0) · 2026-10-09 · Girdi: `P2_sistem_modeli.md`

Kapanış kriteri: her sınıf için giriş noktası, parametre dağılımı ve etiket kuralı yazılı; ayırt edilemeyen durumlar belirlenmiş.

## 0. Varsayılan olarak aldığım iki karar

| # | Karar | Gerekçe | Alternatif |
|---|---|---|---|
| A | **Aşırı sürme sınırı:** nominal IBO 8–14 dB, aşırı sürme IBO 0–5 dB; 5–8 dB arası hiç üretilmez. | İki sınıf birbirine değmesin diye boş bant bırakıldı. Sayılar §3'te. | Sınırı C/IM ile tanımlamak; taşıyıcı planına bağlı olduğu için etiket kuralı karmaşıklaşır. |
| B | **Tek etiket, kök neden kuralı.** Her senaryoda en fazla bir neden vardır ve etiket odur. Uplink girişimcisi yükselteci doyuma itip intermodülasyon üretse bile etiket girişimcinin sınıfıdır. | Kademe A kapsamı. | Çok etiketli veya frekans konumlu çıktı: Kademe B. |

## 1. Sınıflar

| Sınıf | Giriş noktası | Ne üretilir | Etiket kuralı |
|---|---|---|---|
| `clean` | — | Yalnızca planlı taşıyıcılar, nominal IBO | Girişimci yok, IBO nominal aralıkta |
| `cw` | Uplink, IMUX öncesi | Sabit genlikli tek ton, hafif frekans kayması | Gözlem boyunca frekans değişimi < 1 çözünürlük kutusu |
| `swept_cw` | Uplink | Periyodik doğrusal süpürülen ton (testere dişi veya üçgen) | Gözlem içinde en az bir tam süpürme, genişlik ≥ 1 MHz |
| `unauthorized` | Uplink | Planda olmayan modüleli taşıyıcı, boş bir aralıkta | Planlı hiçbir taşıyıcıyla örtüşmez |
| `overdrive` | Yük içi | Dış girişimci yok; yükselteç nominalden fazla sürülür | IBO aşırı sürme aralığında |

Bütün dış girişimciler uplink'ten girer, yani IMUX, TWTA ve OMUX'tan geçer.

## 2. Parametre dağılımları

Hepsi düzgün dağılımlı; `geosim.classes.Ranges` içinde tek yerde tanımlı. P5-A bunları bölünmeye göre daraltır. Tümü **[VARSAYIM]**.

| Parametre | Aralık | Kimde |
|---|---|---|
| Nominal IBO | 8–14 dB | overdrive dışındaki sınıflar |
| Aşırı sürme IBO | 0–5 dB | overdrive |
| (C/N) uplink | 15–30 dB | hepsi |
| (C/N) downlink | 15–30 dB (P2'de 10–25 idi; izleme istasyonu büyük antenli varsayıldı) | hepsi |
| C/I (toplam taşıyıcı gücüne göre) | 5–35 dB | cw, swept_cw |
| CW frekansı | ±0,48 B içinde | cw |
| CW kayması | ±50 kHz/s | cw |
| Süpürme genişliği | 1 MHz – 0,9 B | swept_cw |
| Süpürme periyodu | 0,1–1,28 s | swept_cw |
| Plansız taşıyıcının güç yoğunluğu | planın ortalamasına göre −10…+3 dB | unauthorized |
| Plansız taşıyıcının sembol hızı, α, modülasyon | planlı taşıyıcılarla aynı kümeler | unauthorized |

- Plansız taşıyıcı, iki yanında koruma payıyla sığdığı boş aralıklardan birine yerleşir. 600 rastgele planın 19'unda hiçbir aralık yetmedi; üreteç bu durumda hata verir ve veri kümesi oluşturucu başka tohum dener.
- Her girişimci için üst veriye C/I, frekans aralığı, kendi bandındaki uplink gürültüsüne oranı ve planlı bir taşıyıcının üstüne düşüp düşmediği yazılır.

**Eşleştirilmiş senaryolar:** aynı tohum ve bant genişliği için plan, taşıyıcı sembolleri, gürültü ve bağlantı parametreleri beş sınıfta da aynıdır; yalnızca neden değişir. `docs/figures/class_examples.png` bunu gösteriyor (şekildeki girişimciler göstermek için bilerek güçlü seçildi).

## 3. Aşırı sürme sınırının dayanağı

Taşıyıcı çekirdeğindeki güç yoğunluğunun, taşıyıcı aralarındaki güç yoğunluğuna oranı (dB); referans TWTA, gürültüsüz, 36 MHz, 40 rastgele plan:

| IBO | %10 | Ortanca | %90 | Sınıf |
|---|---|---|---|---|
| 0 dB | 11,0 | 12,1 | 13,6 | overdrive |
| 2,5 dB | 12,4 | 13,5 | 15,0 | overdrive |
| 5 dB | 13,9 | 15,2 | 16,7 | overdrive |
| 8 dB | 16,1 | 17,5 | 19,2 | clean |
| 11 dB | 18,1 | 20,2 | 22,5 | clean |
| 14 dB | 20,0 | 23,1 | 26,1 | clean |

İki sınıfın dağılımları sınırda yaklaşık 1 dB örtüşüyor (IBO 5'in %90'ı 16,7; IBO 8'in %10'u 16,1).

## 4. Ayırt edilebilirlik bulgusu: aşırı sürme ile gürültülü temiz transponder

Uplink gürültüsü de taşıyıcı aralarını doldurur. Aynı oran yalnızca uplink gürültüsünden (doğrusal zincir): C/N 15 dB'de ortanca 16,9 dB, 22,5 dB'de 22,6 dB.

Sonuç: **aralık seviyesi tek başına iki durumu ayırmıyor.** Ölçülen iki örnek aynı aralık seviyesini veriyor:

| Durum | Aralık oranı | Bant dışı omuz (20,5–22 MHz) oranı | Fark |
|---|---|---|---|
| clean, IBO 8, C/N uplink 15 dB | 14,4 dB | 26,7 dB | 12,4 dB |
| overdrive, IBO 3,5, C/N uplink 30 dB | 14,1 dB | 23,5 dB | 9,6 dB |

- Ayırt edici ipucu bant dışı omuz: intermodülasyon IMUX bandının dışına taşar ve yalnızca OMUX'ta süzülür; uplink gürültüsü IMUX'ta zaten kesilmiştir. Fark gürültüsüz downlink'te yaklaşık 3 dB.
- Downlink C/N 20 dB'ye inince bu fark 0,7 dB'ye düşüyor (omuz downlink gürültüsüne gömülüyor).
- İkinci ipucu mutlak seviye: aşırı sürmede çıkış gücü yaklaşık 2 dB artar. Bu ancak spektrogram örnek başına normalize edilmezse ve plan beklenen mutlak seviyeyi verirse kullanılabilir. Karar P6-A'ya bırakıldı.

Beklenti: `overdrive` Kademe A'nın en zor sınıfı olacak ve düşük C/N'de `clean` ile karışacak. Bu bir hata değil, raporlanacak bir sonuç; projenin "hangi sınıf hangi gözlemi gerektirir" sorusunun ilk somut örneği.

## 5. Sabit kazanç etkisi

Toplam taşıyıcı gücüne eşit bir CW (C/I = 0 dB) gerçekleşen IBO'yu 3,0 dB düşürüyor (testle doğrulandı). Dağılımdaki en güçlü girişimci (C/I = 5 dB) IBO'yu yaklaşık 1,2 dB düşürür; nominal aralığın alt ucunda bu, senaryoyu boş banda (5–8 dB) iter. Etiket yine girişimcinin sınıfıdır (karar B).

## 6. Doğrulama

9 yeni test (toplam 50): CW frekansı ve gücü, süpürmenin tanımlanan yolu izlemesi, plansız taşıyıcının boş aralığa oturması ve gücü, eşleştirme, güçlü CW'nin zincir sonunda doğru kutuda görünmesi, sabit kazanç etkisi, parametre aralıkları.

Senaryo süresi FIR süzgeçlerle 3,3 s'ye çıkmıştı; P5-A'da taşıyıcı üreteci hızlandırılarak 1,05 s'ye indirildi.

## 7. Hakem itirazları

| İtiraz | Yanıt |
|---|---|
| "Girişimci her zaman tüm gözlem boyunca açık; gerçek girişim kesiklidir." | Kabul. Kesikli girişim Kademe B'nin bilinmeyen sınıflarında. |
| "Plansız taşıyıcı hep boş aralıkta; planlı taşıyıcının üstüne binen durum yok." | O durum carrier-under-carrier sınıfıdır, Kademe B. |
| "IBO 5–8 dB arası üretilmiyor; gerçek dünya süreklidir." | Kabul edilen sadeleştirme. P7'de bu aralık ayrı bir test kümesi olarak raporlanabilir. |

## 8. Açık sorular ve park listesi

- §0'daki iki kararın onayı
- Spektrogram normalizasyonu ve mutlak seviye bilgisinin maskeye eklenmesi (P6-A)
- Doğrusal karşılaştırma zincirinde `overdrive` sınıfı tanımsızdır (intermodülasyon yok); payload-gap deneyinde bu sınıfın nasıl ele alınacağı P5-A/P7-A'da
- Park: hızlı süpürücüler (tek anlık görüntü içinde geniş bant tarayan), darbeli ve kesikli girişim, çoklu girişimci

## 9. Sonraki faza girdi

P5-A: `geosim.classes.sample(label, bandwidth, seed, ranges)` ve `Ranges`; eşleştirme özelliği; plansız taşıyıcıda yeniden deneme gereği; süre bütçesi.
