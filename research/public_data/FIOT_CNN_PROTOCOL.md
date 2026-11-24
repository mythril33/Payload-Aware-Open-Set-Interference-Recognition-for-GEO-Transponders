# FIOT-CNN/1 deney planı ve çalıştırma kılavuzu

24 Kasım 2026. Plan CNN test sonuçları hesaplanmadan önce kaydedildi. Amaç, GEO
simülasyonunda kullanılan küçük ResNet mimarisinin Fraunhofer FIOT laboratuvar
kayıtlarında da bilinen girişim türlerini sınıflandırıp yeni bir türü ayırıp
ayıramadığını ölçmek. CNN, FIOT verisi ve etiketleriyle baştan eğitilir.

## Veri ve görev

FIOT, ölçülmüş **GNSS** girişiminin `512 × 243 × 3` RGB spektrogram görsellerini
yayımlar. Piksel değerleri, renk kanalları ve görüntü eksenleri bu gösterime
aittir. Ham IQ, kalibre güç, çift polarizasyon veya GEO taşıyıcı planı sağlanmaz.
Sonuçlar GNSS laboratuvar verisindeki bu görevi kapsar. Kaynak kimlikleri kayıt
sızıntısını denetlemeye yeterlidir. Bağımsız ölçüm oturumu veya düzenek bilgisi
sağlanmadığı için bu daha geniş genelleme sınanmaz.

- Sabit kaynak, `FelixOtt94/FIOT_LC_laboratory` deposunun
  `2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26` revizyonudur. Bu revizyondan
  `GNSS_dataset/train_FIOT.txt`, `GNSS_dataset/test_FIOT.txt` ve
  `GNSS_dataset/data_FIOT/data.7z` kullanılır. Arşivin boyutu **364.187.305**
  bayt, SHA-256 değeri `f1a062ccfffdd4e0da31ed92af2f8c1c4386090170c3fa6644fee5caa3ffa2d8`.
  [Veri kaydı](https://zenodo.org/records/21333335) · [Arşiv](https://media.githubusercontent.com/media/FelixOtt94/FIOT_LC_laboratory/2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26/GNSS_dataset/data_FIOT/data.7z)
- Beklenen ayrım dosyası SHA-256 değerleri:

  | Dosya | SHA-256 |
  |---|---|
  | `train_FIOT.txt` | `d295bababaa6938626be0fd43bc190479b6aec6d730ea4bb7cf3ec94cbb663b5` |
  | `test_FIOT.txt` | `7fa00209df88ec5bcf42c08f22e5f26dfe02f727be75375f7121360a65a51155` |

- Yayımlanan eğitim/test ayrımındaki **878/243 ana kaydın** her birinden yalnızca
  `crop 0` alınır. Veri azaltımı kayıt ve kırpım kimliğine göre yapılır. Kaynak
  metadata'sındaki beş basamaklı ana kayıt kimliği ayırma birimidir. Eğitim
  ve test arasında aynı kayıt, kullanılan roller arasında eş dosya içeriği
  denetlenir.
- Kaynak etiketleri `0 None` (temiz), `1 Noise`, `2 Chirp`, `3 FreqHopper`,
  `4 Modulated`, `5 Multitone`, `6 Pulsed`, `7 Cw` ve `8 Tone`. Simülasyondaki
  frekansı taranan tona benzerliği nedeniyle **`2 Chirp`** bilinmeyen olarak
  sabitlenir. Chirp kayıtları eğitime, model seçimine veya kalibrasyona girmez.
  Yayımlanan eğitim listesindeki 48 Chirp kullanılmaz. Testte **227 bilinen** ve
  **16 Chirp** kaydı vardır. Eğitim listesinde bulunan diğer sınıflar bilinen
  sınıflardır. Gerçek sınıf desteği her veri bölümü için sayılır.
- Yayımlanan eğitim bölümü, her bilinen sınıf içinde
  `sha256('fiot-cnn-split-v1:' + recording_id)` değerine göre sıralanır.
  Sınıfın `n ≥ 3` kaydından ilk `max(1, n // 5)` kayıt doğrulamaya, sonraki
  aynı sayıda kayıt kalibrasyona, kalan kayıtlar eğitime ayrılır. CNN yalnızca
  RGB görüntülerini alır. Kayıt kimliği, kaynak gücü ve girişimci alt türü
  metadata olarak kalır.

## Model ve ölçüm

`geoml.model.SmallResNet` üç RGB giriş kanalı ve 8 başlangıç genişliğiyle
kullanılır. Görüntüler alan ortalamasıyla `128 × 64` boyutuna indirilir, piksel
değerleri 255'e bölünür. Veri artırma uygulanmaz. Sabit eğitim ayarları CPU,
iki iş parçacığı, 10 epoch, batch 16, ağırlıksız çapraz entropi kaybı, AdamW,
0,001 tepe öğrenme hızına sahip OneCycleLR, 0,0001 ağırlık sönümü ve başlangıç
tohumları 0, 1, 2'dir. Doğrulamada en yüksek bilinen-sınıf makro F1 veren
ağırlıklar seçilir. Eşitlikte ilk epoch kullanılır.

Üç skor değerlendirilir. MSP, bir eksi en büyük softmax olasılığıdır. Energy
skorunda sıcaklık 1'dir. Mahalanobis sınıf merkezleri ve ortak kovaryansı yalnız
eğitim temsillerinden, 0,1 düzenlileştirmeyle hesaplanır. Yüksek skor daha
bilinmeyen örnek anlamına gelir. Her skorun eşiği yalnızca bilinen kalibrasyon
skorlarının ampirik %95 persentilinden, `higher` yöntemiyle hesaplanır.
Eşiği aşan örnek bilinmeyen sayılır.

Bilinen test örneklerinde doğruluk ve makro F1, bilinen ve Chirp örneklerinin
birleşiminde bilinmeyen-pozitif AUROC raporlanır. Sabit eşikte bilinen kabulünün
paydası bilinen test örnekleri, bilinmeyen reddinin paydası Chirp test
örnekleridir. Tohumlar aynı kayıtları paylaştığından tohum ortalamaları model
başlangıcının değişimini özetler. Önceki FIOT raporu aynı yayımlanan kayıtları
farklı bir ikili girişim tespiti görevinde kullanmıştır.

## Tekrarlama

Depo kökünde, Python 3.12 ve CPU PyTorch kuruluyken çalıştırın. Tam açılım yerine
iki özgün ayrım listesindeki `_0.npy` dosyalarını arşivden seçerek çıkarın.
Dizin, doğrudan bu `.npy` dosyalarını içermelidir. Çıktıya depo dışında yeni
bir klasör verin. [Arşiv hazırlama kılavuzu](README.md#reproduce-the-bounded-fraunhofer-runs)

```bash
python -m pip install -e '.[dev,ml]'
python -m research.public_data.fiot_cnn --data /path/to/crop0/data \
  --train /path/to/train_FIOT.txt --test /path/to/test_FIOT.txt \
  --out /path/to/new-fiot-cnn-run
```

Zenodo API alanı CC BY-SA 4.0, yazarın veri açıklaması CC BY-NC-SA 4.0 belirtiyor.
Deney yerel ve ticari olmayan araştırma kapsamında yürütülür. Ham dosyalar
ve ağırlıklar depo dışında tutulur. [Lisans ve kaynak denetimi](../../docs/plan/P8_dis_veri.md)
