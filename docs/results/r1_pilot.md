# R1-eval/1 pilotu — yükselteç ve geri çekilme kayması

Tarih 2026-10-20 · Protokol [P17](../plan/P17_r1_robustness_eval.md) · Ham sonuç: [r1_pilot.json](r1_pilot.json) ·
Aynı checkpoint'lerle plan bozma testi: [plan_shortcut_pilot.md](plan_shortcut_pilot.md).

**Bu bir pilottur, sonuç değildir.**
- **Veri:** planlanan A1 eğitim verisinin yaklaşık %6'sı.
- **Eğitim tohumu:** yalnız 0. Eğitim tohumu belirsizliği yoktur.
- **Aralıklar:** yalnız senaryo tohumu bootstrap'ı (ağırlık ve eşik sabit).
- **Örneklem:** kutu başına n küçük. Yorumlar yön gösterir, iddia taşımaz.

## Ne koşuldu

| Adım | Ayrıntı | Süre (bu kap) |
|---|---|---|
| A1 pilot verisi | eğitim 120, doğrulama 60, test 30 senaryo tohumu (`nl` ve `lin`) | 1111 s, R1 ile birlikte 4 paralel süreç |
| R1 verisi | 4 bölünme × 60 senaryo tohumu | aynı |
| Kademe A eğitimi | `geoml.pipeline`, 30 epok, eğitim tohumu 0, zaman havuzlama 2, CPU | 1947 s |
| R1 değerlendirmesi | `geoml.robustness`, yeniden eğitim ve kalibrasyon yok; eşikler `val_nl` temizden (hedef Pfa %5) | < 1 dk |

Veri (`data/pilot-a1`, `data/pilot-r1`) ve checkpoint'ler (`runs/pilot-a1`) Git dışında. Kimlik denetimleri
geçti (veri parmak izleri ve uygulama özetleri JSON'da).

## Dağılım içi referans (`test_id_nl`, A1)

- **M-nl5:** doğruluk %85,2 (%80,5–%89,8; n = 149). Eşikli temizde yanlış alarm %3,3 (n = 30).
- **Dört sınıf (`test_id_nl`):**
  - M-lin %82,4, M-nl4 %84,9 doğruluk;
  - temizde yanlış alarm M-lin %6,7, M-nl4 %0.

## R1 bölünmeleri (M-nl5, beş sınıf)

| Bölünme | Yükselteç | n | Doğruluk | ECE | Eşikli temizde yanlış alarm (n = 60) | AUROC (girişim pozitif) | FPR@95TPR |
|---|---|---|---|---|---|---|---|
| `r1_ibo_sweep` | `dvbs2_nl` | 299 | %81,9 (%77,2–%86,2) | 0,035 | %26,7 (%16,7–%38,3) | 0,921 | 0,533 |
| `r1_amp_rapp` | `rapp_p2` | 298 | %66,1 (%62,9–%69,3) | 0,141 | %25,0 (%15,0–%36,7) | 0,775 | 0,867 |
| `r1_amp_opendpd_apa` | `opendpd_apa` | 239 | %80,3 (%76,4–%84,5) | 0,034 | %18,3 (%10,0–%28,3) | 0,914 | 0,633 |
| `r1_amp_opendpd_dpa` | `opendpd_dpa` | 239 | %77,4 (%73,3–%81,6) | 0,045 | %21,7 (%11,7–%31,7) | 0,869 | 0,817 |

- **AUROC / FPR@95TPR:** pozitif = herhangi bir temiz-dışı etiket; negatif = temiz (n = 60).
- **Aşırı sürme yok:** OpenDPD bölünmelerinde aşırı sürme yoktur (K11).
- **Ölçüm dışı giriş oranı:**
  - APA: ortalama 2,7·10⁻⁵, en çok 1,1·10⁻³;
  - DPA: ortalama 2,2·10⁻⁴, en çok 6,3·10⁻³.
  - Nominal IBO'da ölçüm aralığı korunuyor.

## Okuma

1. **Rapp'te aşırı sürme sınıfı çöküyor, ama bu büyük olasılıkla bir tanımlanabilirlik sorunu.**
   - **Karışıklık:** M-nl5, Rapp aşırı sürme örneklerinin 59/60'ına `clean` diyor. Aşırı sürme sınıfı olmayan
     M-lin ve M-nl4 de bu örneklerin %90 ve %97'sine `clean` diyor.
   - **Fizik:** [NPR kontrolü](npr_check.md)ne göre Rapp p = 2'nin NPR'si IBO 2–4 dB'de 17–20 dB. Bu, TWTA'nın
     nominal IBO 9–13 dB'deki 15–19 dB'si kadardır.
   - **Sonuç:** IBO'yla tanımlanan "aşırı sürme" etiketi yükselteçten bağımsız değildir. Rapp aşırı sürmesi,
     gözlemde nominal bir TWTA sahnesine benzer.
   - **Diğer sınıflar sağlam:** dört ortak sınıfta Rapp doğruluğu dağılım içiyle aynı (M-lin %84,9, M-nl4 %84,9).
   - **B2/1 için:** etiketin sürüş seviyesine mi, gözlenebilir IM düzeyine mi bağlanacağı yazılmalıdır. P18 §2'de
     açık konu olarak not edildi.
2. **Ölçülmüş PA'larda (OpenDPD) kayıp CW ↔ temiz karışmasında.**
   - CW örneklerinin 21/60'ı `clean` sayılıyor.
   - Temiz örneklerin 12–13/60'ı `cw` sayılıyor.
   - Belleğin yarattığı spektral yapı dar bantlı girişimle karışıyor olabilir **[YORUM, sınanmadı]**.
   - ECE düşük kalıyor (0,034–0,045), yani model bu kaymada kendinden aşırı emin değil.
3. **Dağılım içi eşik kaymaya taşınmıyor.**
   - `val_nl`'den %5 hedefle konan eşik, dağılım içinde %3,3 veriyor; dört R1 bölünmesinin hepsinde %18–27.
   - Aynı TWTA'lı IBO süpürmesi de dahil.
   - Süpürmedeki fazlalığın bir kısmı A1'de hiç üretilmeyen 5–8 dB boşluğundan geliyor. 5–6 dB kutusunda temiz
     örneklerin 7/9'u alarm.
   - Kutu başına n = 1–11 olduğu için dağılım kesin değil.
   - Operasyonel eşik, yükselteç ailesi ve IBO'ya göre yeniden kalibrasyon gerektiriyor. Bu, P18 val-calib
     rolünün kapsamıyla ilgili bir soru.
4. **Yük farkı yanlış alarmda ve yanlış atfetmede görünüyor, doğrulukta zayıf.** IBO süpürmesinde dört sınıf için:

   | Model | Temizde yanlış alarm | Doğruluk |
   |---|---|---|
   | M-lin | %23,3 | %79,1 |
   | M-nl4 | %1,7 | %83,7 |

   - **IBO kutuları:** aralığı sıfırı dışlayan tek kutu 5–6 dB boşluğu, +11,1 yp (+2,8…+19,4; n = 36).
   - **Aşırı sürme örnekleri (IBO 0–5 dB):** M-lin bunları dış girişim sayıyor:

     | IBO kutusu | M-lin | M-nl4 |
     |---|---|---|
     | 0–3 dB | %88–100 | %44–75 |
     | 3–4 dB | %31 | %23 |
     | 4–5 dB | %79 | %43 |

   - Bu, [ilk pilotun](pilot_A.md) "intermodülasyon dış girişim olarak etiketlenir" yönüyle tutarlı.
   - Rapp ve OpenDPD'de yük farkı yok, aralıklar örtüşüyor. DPA'da M-nl4'ün temizde yanlış alarmı daha yüksek
     (%11,7'ye karşı %3,3; aralıklar örtüşüyor). Bu cihazlar nominal IBO'da TWTA'dan daha doğrusal olduğundan
     beklenen bir durum.

## Sınırlar

- **Tek eğitim tohumu, %6 veri:** modeller zayıf eğitilmiş olabilir. Tam koşu S1/S2/S8'de (kullanıcı makinesi).
- **OpenDPD varsayımları:**
  - ölçülen giriş RMS'i IBO 11 dB'ye yerleştirildi;
  - bellek gecikmeleri bant genişliğine göre ölçeklendi.
  - İkisi de **[VARSAYIM]**dır (P17).
- **Rapp p = 2:** **[VARSAYIM]**dır.
- **OpenDPD cihazları:** katı-hal Doherty PA'dır, TWTA değildir.
- **Boşluk bölgesi:** IBO süpürmesinin `gap` bölgesinde (5–8 dB nominal) etiket kuralı A1'de tanımsızdır. Bu
  kutulardaki "doğruluk", A1 etiket kuralının bu bölgeye uzatılmasıdır.
