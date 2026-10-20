# R1-eval/1 — küçük fiziksel koşu (çalışma kanıtı)

Tarih 2026-10-20 · Protokol [P17](../plan/P17_r1_robustness_eval.md) · Ham sonuç: [r1_smoke.json](r1_smoke.json).
**Bu bir tanıma kalitesi sonucu değildir.** Modeller 30 örnekle 3 epok eğitildi ve dejenere
(her şeye tek sınıf diyorlar); amaç zincirin uçtan uca çalıştığını, kimlik denetimlerinin ve katı
JSON'un tuttuğunu göstermek.

## Ne koşuldu

| Adım | Ayrıntı | Süre (bu kap, 4 çekirdek) |
|---|---|---|
| A1 küçük veri | `train/val/test_id` × `nl/lin`, 6 senaryo tohumu her biri (30 / 24 örnek) | 163 s (R1 ile birlikte, 3 paralel süreç) |
| R1 küçük veri | 4 bölünme × 6 tohum: 30 + 30 + 24 + 24 örnek | aynı |
| Kademe A eğitimi | `geoml.pipeline`, 3 epok, eğitim tohumu 0 | 30 s |
| R1 değerlendirmesi | `geoml.robustness`, eğitimsiz, eşikler `val_nl` temizden | 9 s |
| Tekrar kullanım | R1 üretimi yeniden çağrıldı: dört bölünme "reusing verified dataset" | — |

Tek iş parçacığında örnek başına üretim süresi: A1 doğrusal olmayan ≈ 1,3 s, Rapp ≈ 1,5 s,
OpenDPD-APA ≈ 1,6 s, OpenDPD-DPA ≈ 2,8 s (17 bellek gecikmesi).

## Gözlenenler (yalnız çalışma kontrolü)

- M-nl5 bütün bölünmelerde tek sınıf (`overdrive`) tahmin ediyor: doğruluk %20 (5 sınıf) / %0 (aşırı sürmesiz
  4 sınıf). M-lin ve M-nl4 her şeye aynı girişim sınıfını diyor: doğruluk %25, temizde yanlış alarm %100.
  IBO kutularındaki yük farkı bu yüzden her kutuda 0; anlamsızdır.
- Ölçüm aralığı dışındaki giriş oranı (nominal IBO, 24'er örnek): APA ortalama 2,6·10⁻⁶ (en çok 3,5·10⁻⁵),
  DPA ortalama 5,1·10⁻⁵ (en çok 8,7·10⁻⁴).
- 6 tohumun nominal IBO'larından hiçbiri 5–8 dB `gap` bölgesine düşmedi (düzgün dağılımda olasılık ≈ %9);
  `gap` satırları bu yüzden boş.
- `results.json` katı JSON olarak okundu (NaN/Infinity yok); boş seçimler `null` ve sayımla.

## Sonuç

R1-eval/1 kodu ve değerlendirme hattı çalışıyor. Yük farkı eğrisi, yükselteç uyumsuzluğu ve ECE/FPR@95TPR
hakkında **hiçbir bilimsel çıkarım bu koşudan yapılamaz**; tam Kademe A modelleri ve tam R1 verisi gerekir
(komutlar P17 §5).
