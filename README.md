# GEO uydu girişimini derin öğrenmeyle tanıma

Bir GEO uydusunun alıcıda gözlenen spektrumundan girişim türü tanınabilir mi?
Bu projede PyTorch ile eğitilen küçük bir **ResNet**, simüle edilmiş tek
kutuplu downlink spektrogramını ve planlanan taşıyıcıların frekans maskesini
işler. Model temiz sinyali, sürekli dalgayı (CW), yetkisiz taşıyıcıyı ve
yükseltecin aşırı sürülmesini sınıflandırır. Deney ayrıca üç açık küme
skorunun eğitimde bulunmayan sinyal türlerini ayırt etme başarısını ölçer.

[Makale (Word)](paper/geo_cnn_paper.docx) ·
[Makale (PDF)](paper/geo_cnn_paper.pdf) · [Markdown kaynak](paper/geo_cnn_paper.md)

Fraunhofer FIOT ölçümleriyle ikinci bir deney tamamlandı. CNN, hazır RGB
spektrogramları üzerinde yeniden eğitildi ve 227 bilinen GNSS test kaydında
**%91,63 doğruluk** elde etti. Energy skoru, eğitim dışında bırakılan 16 Chirp
kaydının her eğitimde 5–8'ini reddetti. Bu deneyin eğitim ve test etiketleri
Fraunhofer'a ait. [FIOT sonuçları ve grafik](docs/results/FIOT_CNN_2026-11-24.md)

## Deney ne gösterdi?

4 Kasım 2026'da tamamlanan CPU deneyinde **716 simülasyon gözlemi** üretildi.
Aynı eğitim ve test verileriyle üç farklı başlangıçtan, her biri 10 epoch
olacak şekilde model eğitildi. CNN'in 158 bilinen test örneğindeki ortalama
doğruluğu **%70,25** oldu (üç eğitimde %69,62–%70,89). Testte ayrıca 160
bilinmeyen örnek kullanıldı. Bilinmeyen örnekler eşik ve model seçiminden
ayrı tutuldu.

| Açık küme skoru | Bilinmeyen AUROC | Sabit eşikte bilinmeyen reddi |
| --- | ---: | ---: |
| Maksimum softmax olasılığı (MSP) | 0,6191 | %2,29 |
| Energy | 0,5647 | %1,25 |
| Mahalanobis | 0,3314 | %1,67 |

Tablo üç eğitim tohumunun ortalamasıdır. AUROC'da bilinmeyen örnekler
pozitiftir ve skor büyüdükçe örnek daha bilinmeyen sayılır. Eşikler yalnız
bilinen kalibrasyon örneklerinde belirlendi. CNN bilinen sınıfları ayırt
edebildi, ancak bu eşiklerde bilinmeyenlerin büyük çoğunluğunu kabul etti.
Bulgular tek kutuplu simülasyon ve bu test örnekleriyle sınırlıdır.
[Deney raporu ve grafikler](docs/results/CPU_DELIVERY_2026-11-04.md) ·
[Sayısal sonuçlar](docs/results/cpu_delivery_2026-11-04.json)

## Windows 11'de çalıştırma

Bu CPU deneyi için Git ve Python 3.12 yeterli. WSL2 veya CUDA gerekmez.
PowerShell'de şu komutları çalıştır:

```powershell
git clone https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders.git geo-cnn
Set-Location geo-cnn
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "torch==2.15.0+cpu" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ml]"
.\.venv\Scripts\python.exe research/cpu_delivery/run.py --out "$env:USERPROFILE\geo-cnn-results"
```

Çıktı için depo dışında yeni bir klasör seç. Deney veri üretimini, üç
eğitimi, değerlendirmeyi ve grafik üretimini sırayla yapar. Sonuçları çıktı
klasöründeki `summary.md`, `summary.json` ve `figures/` altında bulabilirsin.
Arşivlenen Linux çalıştırmasında veri üretimi ve eğitim alt süreçleri yaklaşık
6 dakika sürdü. Windows'ta uçtan uca çalıştırma henüz doğrulanmadı.
[Linux komutları ve deney kılavuzu](research/cpu_delivery/README.md)

## Kod

- [Simülatör](src/geosim/dataset.py) ve [bilinmeyen sinyal üretimi](src/geosim/unknowns.py)
- [ResNet modeli](src/geoml/model.py), [eğitim](src/geoml/train.py) ve [açık küme değerlendirmesi](src/geoml/experiment.py)
- [Tek komutla çalıştırıcı](research/cpu_delivery/run.py) ve [deney ayarları](configs/cpu_delivery.json)

Çift kutuplu B2 deneylerinin tasarımı ve Windows/WSL çalışma ortamı
[ayrıntılı araştırma kılavuzunda](RESEARCH_GUIDE.md) yer alıyor.
