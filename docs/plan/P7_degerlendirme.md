# P7-A — Değerlendirme protokolü (Kademe A)

Durum: **KAPANDI** · 2026-10-10 · Girdi: `P5_veri_protokol.md`, `P6_modeller.md` · Kod: `src/geoml/pipeline.py`

Kapanış kriteri: her iddia bir deneye, metriğe ve tabloya bağlı; istatistik yöntemi yazılı.

## 1. İddia → deney → tablo

| İddia (P5 §1) | Deney | Metrik | Sonuç tablosu |
|---|---|---|---|
| İ1 Doğrusal eğitilen model doğrusal olmayan zincirde bozulur | M-lin: `test_id_lin` ve `test_id_nl`, dört ortak sınıf | Doğruluk, makro-F1, temizde yanlış alarm | §1 |
| İ2 Doğrusal olmayan eğitim bunu kapatır | M-nl4, `test_id_nl` | aynı | §1 |
| İ3 M-lin intermodülasyonu dış girişim sanar | M-lin'in `overdrive` örneklerine verdiği sınıf dağılımı | Sınıf payları | §1 alt tablo |
| İ4 Görülmemiş koşullara genelleme | M-nl5: `test_id_nl` ve dört kayma kümesi | Doğruluk, makro-F1, sınıf başına geri çağırma | §2 |
| İ5 Model enerji dedektöründen iyi | M-nl5, CA-CFAR, planlı CA-CFAR | Sabit yanlış alarmda algılama olasılığı; C/I'ye göre | §3 |

## 2. Metrik tanımları

- **Doğruluk, makro-F1, karışıklık matrisi:** sınıflandırma. Test kümesinde bulunmayan sınıflar makro-F1'e girmez.
- **Temizde yanlış alarm:** `clean` örneklerinden `clean` dışında bir sınıfa atananların oranı.
- **Algılama skoru:** model için 1 − P(clean); CFAR için P6 §5'teki skor.
- **Eşik:** doğrulama kümesinin temiz örneklerinde hedef yanlış alarm %5. Test kümesinde eşik ayarlanmaz; gerçekleşen yanlış alarm ayrıca raporlanır.
- **Algılama olasılığı:** sınıf başına ve C/I aralığına göre (5–15, 15–25, 25–35 dB).
- **Maliyet:** parametre sayısı, CPU'da çerçeve başına süre.

%5'lik hedef tam veride 300 doğrulama tohumuna (300 temiz örnek) dayanır; %1 için 3 örnek kalırdı.

## 3. İstatistik

- **Güven aralığı:** senaryo tohumları üzerinden kümeli bootstrap, %95, 2000 yineleme. Aynı tohumun beş sınıfı planı ve gürültüyü paylaşır; örnek düzeyinde bootstrap aralığı olduğundan dar gösterirdi.
- **Eğitim tohumları:** sonuçlar eğitim tohumları üzerinden ortalanır; makro-F1 için tohumlar arası sapma verilir.
- Tam koşu 3 eğitim tohumu kullanır.

## 4. Tek komut

```
pip install -e .[dev,ml]
python -m geoml.pipeline --data data/stageA --out runs/stageA --epochs 30 --seeds 0 1 2
```

Üç modeli eğitir, baseline'ı koşar, `results.json` ve `results.md` yazar. `--reuse` eğitilmiş modelleri yeniden kullanır; `--level absolute` mutlak seviye ablasyonunu koşar; `--time-pool 1` tam zaman çözünürlüğünü kullanır.

## 5. Hakem itirazları

| İtiraz | Yanıt |
|---|---|
| "Yük farkı yalnızca iki simülatörün farkı." | Kabul edilen sınır (ana plan §1.2). Görülmemiş yükselteç kümeleri (`test_amp_*`) ve Kademe B'deki ölçülmüş yükselteç verisi bu yüzden var. |
| "CFAR kasıtlı zayıf seçilmiş." | Planlı sürüm modelle aynı yan bilgiyi alır ve eşiği aynı yoldan konur. Daha güçlü klasik baseline (uzman özellikleri) Kademe B'de. |
| "Hiperparametre araması yok; sonuçlar ayara bağlı olabilir." | Üç model aynı ayarı kullanır, karşılaştırma göreli. Mutlak sayılar ayara duyarlıdır; bu açıkça belirtilecek. |
| "Yanlış alarm %5 operasyonel olarak çok yüksek." | Doğrulama kümesinin boyutu daha düşük hedefi desteklemiyor. Tam veride daha düşük hedef için yalnızca doğrulama ve test kümeleri büyütülür. |

## 6. Açık konular

- ROC eğrileri ve şekiller (sonuçlar geldikten sonra)
- IBO 5–8 dB "belirsiz bölge" değerlendirmesi
- Plan hatasına dayanıklılık, open-set metrikleri: Kademe B
