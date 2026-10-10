# Küçük ölçekli deneme koşusu (pilot) — Kademe A

2026-10-10 · **Bu bir boru hattı denemesidir, sonuç değildir.** Planlanan verinin yaklaşık %6'sı (120 eğitim tohumu, 2000 yerine), 2 eğitim tohumu (3 yerine), CPU'da zaman havuzlama 2. Güven aralıkları geniş; aşağıdaki yorumlar yön gösterir, iddia taşımaz.

## Okuma

| İddia (P5 §1) | Pilotta görülen | Değerlendirme |
|---|---|---|
| İ1 Doğrusal eğitilen model doğrusal olmayan zincirde bozulur | Doğruluk %78,7 → %76,8; temizde yanlış alarm %10,6 → %18,1 | **Desteklenmiyor.** Doğruluk farkı aralıkların içinde; yanlış alarm artışı yönlü ama aralıklar örtüşüyor. |
| İ2 Doğrusal olmayan eğitim farkı kapatır | M-nl4 aynı testte %80,6, yanlış alarm %11,9 | Yönü doğru, fark küçük ve aralıklar örtüşüyor. |
| İ3 M-lin intermodülasyonu dış girişim sanar | M-lin aşırı sürme örneklerinin %84'üne dış girişim diyor (%53 plansız taşıyıcı); M-nl4 %58'ine | En belirgin etki bu. Ancak iki modelin de aşırı sürme sınıfı yok; karşılaştırma dikkatle yorumlanmalı. |
| İ4 Görülmemiş koşullara genelleme | Dağılım içi %83,4; görülmemiş IBO %75,4, 72 MHz %81,8, H.2 tüpü %73,5, Saleh %77,8 | Düşüş var ama çöküş yok. En çok etkilenen: görülmemiş yükselteçte aşırı sürme (%96 → %75–83) ve görülmemiş IBO'da temiz (%93 → %76). |
| İ5 Model enerji dedektöründen iyi | Plansız taşıyıcı %100'e karşı %84; aşırı sürme %97,5'e karşı %4. CW %47'ye karşı %46; süpürülen CW %78'e karşı %84 | **Kısmen.** Model dar bantlı girişimde planlı CFAR'ı geçemiyor; üstünlüğü geniş bantlı ve yapısal nedenlerde. |

Öne çıkanlar:

- **Nominal geri çekilmede (IBO 9–13 dB) yük farkı küçük görünüyor.** Seviye normalizasyonu mutlak güç farkını zaten gizliyor ve bu aralıkta intermodülasyon ılımlı. Tam veri bunu doğrularsa projenin ana iddiası "sınıflandırma doğruluğu düşer" biçiminde değil, "intermodülasyon dış girişim olarak etiketlenir ve yanlış alarm artar" biçiminde kurulmalı; ya da fark daha düşük geri çekilmede aranmalı.
- **Aşırı sürme, korkulduğu kadar zor çıkmadı** (%96), mutlak güç gizlendiği hâlde. Görülmemiş yükselteçte düşüyor.
- **CW en zayıf sınıf** (%52). Taşıyıcı üstündeki zayıf CW'lerin bir kısmı fiziksel olarak görünmez (P6 §6), ama C/I 5–15 dB'de plansız CFAR %94 bulurken model %66'da kalıyor: modelin eksiği, verinin değil.
- Plansız CFAR'ın gerçekleşen yanlış alarmı %12,5 (hedef %5); eşik 30 doğrulama örneğinden konduğu için kararsız.

## Ham tablolar

Protokol A1, frozen 2026-10-09 · seviye kipi `carrier` · zaman havuzlama 2 · 30 epok · eğitim tohumları [0, 1]

Parantez içi: senaryo tohumları üzerinden %95 güven aralığı.

## Örnek sayıları

| Bölünme | Örnek |
|---|---|
| `test_amp_lin` | 245 |
| `test_amp_saleh` | 250 |
| `test_bw72` | 250 |
| `test_ibo` | 250 |
| `test_id_lin` | 315 |
| `test_id_nl` | 395 |
| `train_lin` | 473 |
| `train_nl` | 593 |
| `val_lin` | 119 |
| `val_nl` | 149 |

## 1. Yük farkı (dört ortak sınıf)

| Model, test kümesi | Doğruluk | Makro-F1 | Temizde yanlış alarm |
|---|---|---|---|
| M-lin on test_id_lin | %78.7 (%75.2–%82.2) | 0.790 ± 0.035 | %10.6 (%5.6–%16.2) |
| M-lin on test_id_nl | %76.8 (%73.2–%80.5) | 0.775 ± 0.028 | %18.1 (%11.9–%25.6) |
| M-nl4 on test_id_lin | %81.0 (%77.9–%84.0) | 0.814 ± 0.001 | %14.4 (%8.1–%21.2) |
| M-nl4 on test_id_nl | %80.6 (%77.4–%83.8) | 0.810 ± 0.004 | %11.9 (%6.9–%17.5) |

Aşırı sürme örneklerine dört sınıflı modellerin verdiği yanıt:

| Model | clean | cw | swept_cw | unauthorized |
|---|---|---|---|---|
| M-lin | %16 | %24 | %7 | %53 |
| M-nl4 | %42 | %40 | %8 | %9 |

## 2. Beş sınıflı model, dağılım içi ve kaymalar

| Test kümesi | Doğruluk | Makro-F1 | clean | cw | swept_cw | unauthorized | overdrive |
|---|---|---|---|---|---|---|---|
| `test_id_nl` | %83.4 (%80.7–%86.1) | 0.836 ± 0.038 | %93 | %52 | %77 | %100 | %96 |
| `test_ibo` | %75.4 (%71.6–%78.8) | 0.748 ± 0.062 | %76 | %43 | %62 | %100 | %96 |
| `test_bw72` | %81.8 (%78.2–%85.4) | 0.818 ± 0.054 | %84 | %56 | %71 | %99 | %99 |
| `test_amp_lin` | %73.5 (%70.1–%76.9) | 0.749 ± 0.013 | %87 | %41 | %67 | %100 | %75 |
| `test_amp_saleh` | %77.8 (%74.0–%81.6) | 0.782 ± 0.028 | %91 | %46 | %69 | %100 | %83 |

Sınıf sütunları: o sınıfın geri çağırma oranı.

## 3. Algılama, hedef yanlış alarm %5 (eşik doğrulama kümesinden)

| Dedektör | Gerçekleşen yanlış alarm | cw | swept_cw | unauthorized | overdrive |
|---|---|---|---|---|---|
| M-nl5 | %4.4 (%1.2–%8.1) | %46.9 (%38.8–%55.0) | %78.1 (%70.0–%85.6) | %100.0 (%100.0–%100.0) | %97.5 (%95.0–%99.4) |
| CA-CFAR | %12.5 (%6.2–%20.0) | %58.8 (%47.5–%70.0) | %76.2 (%66.2–%85.0) | %10.7 (%4.0–%18.7) | %5.0 (%1.2–%10.0) |
| CA-CFAR + plan | %5.0 (%1.2–%10.0) | %46.2 (%35.0–%57.5) | %83.8 (%75.0–%91.2) | %84.0 (%76.0–%92.0) | %3.8 (%0.0–%8.8) |

Algılama olasılığı, C/I aralığına göre:

| Sınıf | Dedektör | 5–15 dB | 15–25 dB | 25–35 dB |
|---|---|---|---|---|
| cw | M-nl5 | %66 | %50 | %20 |
| cw | CA-CFAR | %94 | %39 | %32 |
| cw | CA-CFAR + plan | %59 | %57 | %20 |
| swept_cw | M-nl5 | %89 | %98 | %43 |
| swept_cw | CA-CFAR | %92 | %100 | %30 |
| swept_cw | CA-CFAR + plan | %100 | %95 | %48 |

## 4. Model maliyeti

- Parametre: 309 477
- CPU'da çerçeve başına çıkarım: 11 ms
- Eğitim süresi (koşu başına): 11.0 dk
- En iyi doğrulama makro-F1: M-lin 0.815, M-nl4 0.817, M-nl5 0.839
