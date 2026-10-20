# Uplink komşu uydu girişimi (ASI): geometriden C/I ve spektrumda görünürlük

Tarih 2026-10-20 · Komut: `python scripts/asi_visibility.py --out docs/results/asi_visibility.json` ·
Ham sonuç: [asi_visibility.json](asi_visibility.json) · Üreteç: `geosim.asi.adjacent_satellite_uplink` ·
Amaç: P18 (K5, K17) `adjacent_satellite` sınıfının parametrelerine kaynaklı dayanak.

## Model ve kaynaklar

Komşu GSO ağının yer istasyonu kendi uydusuna bakar. Ekseni dışındaki ışıması bizim uydumuzun alıcı antenine
girer; olay IMUX, TWTA ve OMUX'tan uplink sinyali gibi geçer. Tek kaynaklı uplink C/I'si (ITU BR yöntemi,
R19-WRS20-C-0013, eş. 11–12; ortak kapsama ve eşit yol kaybıyla):

    C/I_psd = Gmax − G(φ) − ΔEIRP_yoğunluk

| Parametre | Değer | Dayanak |
|---|---|---|
| Uydu aralığı (topo-merkezli) | 2,06–2,36° | FCC 47 CFR Part 25 iki derece aralığı. 2° yer-merkezli aralık, 2 × 42 164 km / eğik mesafe ile topo-merkezli açıya çevrilir. Brooker (AIAA): 10° yükselimde ±2,08° |
| Anten deseni | ITU-R S.1428-1 tam desen (ana lob Gmax − 2,5·10⁻³(Dφ/λ)², ilk yan lob platosu G1, sonra 29 − 25 log φ) ya da ITU-R S.465-6 zarfı (32 − 25 log φ, φ_min kuralıyla); her biri %50 | S.1428-1, S.580-6, S.465-6 |
| Gmax | 20 log(D/λ) + 7,7 dBi (D/λ > 100 için + 8,4) | S.1428-1 |
| İşaretleme hatası | 0–0,4 θ₃dB büyüklükte, rastgele yönde; θ₃dB = 69,3 λ/D | θ₃dB: ITU-R F.699-6 öneri 4.1. Üst sınır **[VARSAYIM]**: 0,75 m'de 0,78° eder; Brooker'ın elle ayarlanan metre altı Ku VSAT'ler için ≈0,8° değerine uyar. Girişimcinin kendi linkinde kaybı en çok 1,9 dB |
| Anten çapı | 0,75; 0,96; 1,2; 1,8; 2,4 m (14,25 GHz'de D/λ 35,6–114) | **[VARSAYIM]**: VSAT'tan SNG'ye |
| ΔEIRP yoğunluğu | −3…+6 dB (plan ortalamasına göre) | **[VARSAYIM]**: +6 dB yanlış ayarlı uplink |
| Plan örtüşmesi | girişimci bandının %20–80'i planlı taşıyıcılarda | **Sınıf tanımı, fizik değil**: örtüşme yoksa boş aralıktaki `unauthorized`, tamamen içerideyse `carrier_under_carrier` olur |

Karşılaştırma: bir FCC Ku başvurusunda koordine istasyonların uplink C/I'si 23,6–31,2 dB'dir. satsig
uplink ASI için 25–30 dB verir.

## Sabit link ve ölçü

- **Zincir:** tek polarizasyonlu A1 zinciri (DVB-S2 H.3 TWTA), 36 MHz.
- **Link:** IBO 11 dB, uplink/downlink C/N 25 dB **[VARSAYIM; A1 ortası]**.
- **Senaryolar:** 120 senaryo tohumu, 610000–610119. Hiçbir veri protokolüyle çakışmaz.
- **Ölçü:** ΔPSD = olaylı ve olaysız zaman ortalamalı PSD oranı. Girişimci bandının plan içi kutularında ve plan
  dışı kutularında ayrı hesaplanır.
  - Taşıyıcılar ve gürültü aynı olduğundan bu eşleşmiş fark bir **üst sınırdır**: operatörün olaysız ikizi yoktur.
  - σ = 128 anlık görüntüden bant ortalamasının 1σ tahmin gürültüsü (ortanca: plan içi 0,024 dB, plan dışı 0,043 dB).

## Geometriden çıkan C/I

- **Plan PSD'sine göre C/I_psd:** ortanca **20,3 dB**, %10–%90 aralığı 14,4–26,6 dB, en küçük 7,0, en büyük 31,8 dB.
  - Aynı üreteçten 2000 çekilişte (birim testi dışı denetim) aralık 2,5–32,9 dB çıktı.
  - Alt kuyruk: ana lob içinde yanlış işaretlenmiş 0,75 m antenler.
- **Toplam plana göre C/I:** ortanca 26,2 dB, %10–%90 aralığı 19,0–33,1 dB. Girişimci çoğu zaman planın
  toplamından dar olduğu için bu değer daha büyüktür.

| Çap | n | C/I_psd ortanca | %10–%90 |
|---|---|---|---|
| 0,75 m | 18 | 15,1 dB | 10,8–18,9 dB |
| 0,96 m | 30 | 17,6 dB | 13,3–20,7 dB |
| 1,2 m | 23 | 19,6 dB | 16,1–23,5 dB |
| 1,8 m | 20 | 22,5 dB | 20,2–27,2 dB |
| 2,4 m | 29 | 25,3 dB | 22,3–29,5 dB |

Desen bölgeleri (120 örnek):

| Bölge | n |
|---|---|
| S.465 zarfı | 50 |
| S.1428/S.580 yan lobu | 52 |
| ana lob | 14 |
| ilk yan lob platosu | 4 |

Sıralama literatürle uyumlu: rfessentials 2°'de 0,6 m için ≈15 dB, 1,2 m için ≈23 dB, 2,4 m için ≈30 dB verir.
O değerler downlink içindir; burada uplink ve ΔEIRP dağılımı var.

## Görünürlük

Örtüşme ortancası 0,65. Girişimci bandı ortanca 18 plan içi ve 11 plan dışı izleme kutusu kaplar (187,5 kHz).

| C/I_psd | n | Plan içi ΔPSD ortanca (%10–%90) | Plan içi > 3σ | Plan içi > 0,5 dB | Plan dışı ΔPSD ortanca (%10–%90) | Plan dışı > 3σ | Plan dışı > 0,5 dB | Plan dışı > 1 dB |
|---|---|---|---|---|---|---|---|---|
| < 10 dB | 1 | 1,01 dB | %100 | %100 | 4,72 dB | %100 | %100 | %100 |
| 10–15 dB | 15 | 0,18 (0,13–0,43) dB | %93 | %7 | 5,53 (3,85–9,66) dB | %100 | %100 | %100 |
| 15–20 dB | 41 | 0,07 (0,03–0,16) dB | %61 | %2 | 2,59 (1,92–4,08) dB | %100 | %100 | %100 |
| 20–25 dB | 43 | 0,03 (0,01–0,08) dB | %16 | %0 | 1,42 (0,76–2,41) dB | %100 | %98 | %67 |
| ≥ 25 dB | 20 | 0,005 (0,003–0,012) dB | %0 | %0 | 0,40 (0,18–0,88) dB | %95 | %35 | %10 |

## Yorum

1. **ASI'yi gösteren, plan dışına taşan kısmıdır.** Plan dışı kutularda C/I_psd < 20 dB olan her olay 1 dB'nin
   üstünde. 20–25 dB'de olayların üçte ikisi, ≥ 25 dB'de yalnız %10'u 1 dB'yi aşıyor.
2. **Plan içi kısım, kâhin ikizle bile neredeyse görünmez.** Ortanca ΔPSD 0,005–0,18 dB. 0,5–1 dB plan seviyesi
   belirsizliğinde **[VARSAYIM; CuC notu]** pratikte ölçülemez.
   - Dolayısıyla P18'deki "ASI ile `unauthorized` arasındaki fark planla örtüşmedir" kuralı spektrumda çok zayıf
     bir ipucuna dayanıyor. Bu ipucu, örtüşen kenarın plan maskesiyle hizasıdır.
3. **Asıl ayırıcı seviye olabilir.** `unauthorized` PSD'si plan ortalamasının −10…+3 dB'sidir, yani C/I_psd
   −3…10 dB. ASI ise kaynaklı geometride 7–32 dB (2000 çekilişte 2,5–33 dB).
   - İki sınıf yalnız ≈7–10 dB bölgesinde örtüşür. Model ikisini büyük ölçüde seviyeden ayırabilir.
   - Bu fiziksel bir farktır: ASI yan lobdan gelir, yetkisiz taşıyıcı ana lobdan yayın yapar. Yine de ön kayıtta
     ayrıca yazılmalıdır. P18 §6'ya seviye eşleşmiş alt kutu önerisi eklendi.
4. **≥ 25 dB'deki %17'lik dilim** spektrumdan zor algılanır. Bu bölge CuC'nin 20–25 dB bölgesine benzer.

## Sınırlar

- **Link ve zincir:** tek link noktası (IBO 11 dB, C/N 25 dB); tek polarizasyon; faz gürültüsü yok.
- **Geometri:** tek girişimci ve ortak kapsama. Uydu alıcı anteninin iki yöndeki kazanç farkı yok sayılır;
  bu fark C/I'yi yalnız büyütür.
- **Desen ve dağılımlar:**
  - S.465 zarfı tepe zarfıdır, gerçek antenlerin yan lob çukurları yoktur.
  - İşaretleme hatası, çap ve ΔEIRP dağılımları **[VARSAYIM]**dır.
- **Ölçü:** eşleşmiş fark bir üst sınırdır. Gerçek operatör plan beklentisine göre bakar.
- **Örneklem:** 120 senaryo. Kutu başına n küçük (özellikle < 10 dB: n = 1). Kutu yüzdeleri aralıksız
  verilmiştir; kesin değer değil, eğilimdir.
