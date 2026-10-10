# P6-A — Model, girdi ve baseline (Kademe A)

Durum: **KAPANDI** · 2026-10-10 · Girdi: `P5_veri_protokol.md` · Kod: `src/geoml/`

Kapanış kriteri: girdi tensörü, mimari, parametre bütçesi, baseline tanımı ve eğitim ayarları yazılı.

## 1. Üç model

| Ad | Eğitim verisi | Sınıf | Amaç |
|---|---|---|---|
| M-lin | `train_lin` | 4 | Yük zinciri olmadan eğitilmiş model |
| M-nl4 | `train_nl` (overdrive hariç) | 4 | Aynı görev, yük zinciriyle eğitilmiş |
| M-nl5 | `train_nl` | 5 | Tam Kademe A tanıyıcısı |

Üçü de aynı mimari, aynı ayarlar ve aynı eğitim tohumlarıyla eğitilir; tek fark veridir.

## 2. Girdi

2 kanal × (128 / zaman havuzlama) × 512:

1. **Spektrogram**, dB. Örnek kendi planlı taşıyıcı seviyesine göre ifade edilir: zaman ortalamalı güç yoğunluğunun, maskenin −3 dB üstündeki kutularda ortalaması çıkarılır. [−60, +20] dB'ye kırpılır, 20'ye bölünür.
2. **Plan maskesi**, dB/20, zaman boyunca yinelenir.

- **Seviye denetimi (P5 §5'in zorunlu kıldığı):** taşıyıcıya göre normalizasyon mutlak gücü modelden gizler. Testle doğrulandı: girdiye 7,5 dB sabit kayma eklemek model girdisini değiştirmiyor. Böylece ne aşırı sürmenin 3,3 dB'lik güç farkı ne de iki zincir arasındaki 0,6–1,65 dB'lik seviye farkı kısa yol olabilir.
- `--level absolute` kipi mutlak seviyeyi korur (referans yalnızca eğitim verisinden); yalnızca ablasyon içindir.
- Zaman havuzlama satırları **güç** olarak ortalar (dB ortalaması süpürülen tonu zayıflatır). Varsayılan 2; GPU'da 1 kullanılabilir.

## 3. Mimari

Küçük ResNet: 5×5 gövde (tam frekans çözünürlüğünde), dört artık blok (16, 32, 64, 128 kanal), küresel ortalama ve küresel en büyük havuzlamanın birleşimi, doğrusal sınıflandırıcı. Yaklaşık 310 000 parametre.

- Gövde frekansta seyreltme yapmaz: tek kutuluk bir çizgi (CW) ilk doğrusal olmayan katmana tam çözünürlükte ulaşır. İlk sürümde gövde frekansta 2'ye seyreltiyordu ve taşıyıcı üstündeki CW'leri kaçırıyordu (§6).
- En büyük havuzlama dar bir çizginin ortalamada kaybolmasını önler.

## 4. Eğitim

| Ayar | Değer |
|---|---|
| Optimizasyon | AdamW, lr 1e-3 (tek döngü), ağırlık azaltma 1e-4 |
| Epok, yığın | 30, 32 |
| Artırma | Frekans ekseninde ayna (olasılık 0,5), zamanda dairesel kaydırma |
| Model seçimi | En iyi doğrulama makro-F1 |
| Eğitim tohumu | 3 (tam koşu); sonuçlar tohumlar üzerinden ortalanır |

Hiperparametre araması yapılmadı; üç model aynı ayarı kullandığı için karşılaştırma adil, ama ayarlar en iyi değil. Tümü **[VARSAYIM]**.

Frekans aynası IMUX/OMUX'un hafif asimetrisini yok sayar; kabul edilen yaklaşıklık.

## 5. Baseline: CA-CFAR

Frekans ekseninde hücre ortalamalı CFAR; her yanda 1 koruma, 4 eğitim hücresi (hücre = 187,5 kHz).

- İki özellik: zaman ortalamalı spektrumdaki en güçlü hücre (sabit girişimciler) ve tek satırdaki en güçlü hücre (hareketli girişimciler). Her biri doğrulama kümesindeki temiz örneklerin ortalama ve sapmasıyla ölçeklenir; skor ikisinin büyüğüdür.
- **Plansız sürüm:** transponder bandı içindeki tüm hücreler.
- **Planlı sürüm:** pencere içinde planlanan seviyenin 1 dB'den fazla değiştiği hücreler atlanır (taşıyıcı kenarları). Modelle aynı yan bilgiyi kullanır.
- Eşik, modelinkiyle aynı yoldan konur: doğrulama kümesinin temiz örneklerinde hedef yanlış alarm oranı.
- Yalnızca algılama yapar (girişim var/yok); sınıflandırmaz. Yerel bir tepe üretmeyen aşırı sürmeyi görmesi beklenmez.

Uzman özellikleri + gradyan artırma baseline'ı Kademe B'ye bırakıldı.

## 6. İlk denemeden öğrenilenler

Küçültülmüş veriyle ilk koşuda (gövde seyreltmeli, zaman havuzlama 4, dB ortalaması) beş sınıflı model:

- `overdrive` 77/80, `unauthorized` 73/75 doğru,
- boşluktaki CW'leri buluyor (C/I 5–25 dB'de %90–100), taşıyıcı üstündekileri kaçırıyor (C/I 15–25 dB'de 0/8),
- süpürülen CW'de %30 civarında kalıyordu.

Aynı verilerde ölçülen tepe yükseklikleri sorunun veride değil modelde olduğunu gösterdi:

| Taşıyıcı üstü CW, C/I | Ölçülen tepe (ortanca) | Güç hesabından beklenen |
|---|---|---|
| 5–15 dB | 7,6 dB | 7,9 dB |
| 15–25 dB | 2,4 dB | 2,8 dB |
| 25–35 dB | 0,18 dB | 0,22 dB |

Bu yüzden gövde tam çözünürlüğe alındı, havuzlama güç ortalamasına çevrildi ve artırma eklendi. Tablo ayrıca bir üst sınır veriyor: C/I 25 dB'nin üstündeki taşıyıcı üstü CW spektrumda neredeyse görünmez (0,2 dB; kutu başına ölçüm sapması 128 satır ortalamasında yaklaşık 0,1 dB).

## 7. Açık konular

- Hiperparametre araması ve eşit arama bütçesi (Kademe B)
- Mutlak seviye ablasyonu (`--level absolute`) tam veriyle koşulacak
- Çapraz polarizasyon kanalı, open-set skorları, transformer: Kademe B
