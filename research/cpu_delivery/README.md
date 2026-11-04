# GPU gerektirmeyen GEO geliştirme deneyi

Bu kampanya mevcut **A1 fizik + B1-dev/2 açık-küme** kodunu kullanır. Tek
kutupludur: dört bilinen sınıf ve dört bilinmeyen aileyi üç sabit eğitim
tohumuyla değerlendirir. Sekiz sınıflı çift-pol B2 projesinin tamamlandığı veya
plan/çapraz-kutup/iptal kanalının üstünlüğünün gösterildiği anlamına gelmez.

[Ön kayıt](PREREGISTRATION.md) ve [sabit ayarlar](../../configs/cpu_delivery.json)
sonuçlardan önce yazıldı. Ağ ve veri bütçesi CPU için küçültüldü; fiziksel
örnekleme değiştirilmedi. Bilinmeyen örnekler model veya eşik seçiminde kullanılmaz.

## Kurulum ve çalıştırma

Depo kökünde Python 3.12 ile, sanal ortam etkinleştirildikten sonra:

```sh
python -m pip install 'torch==2.15.0+cpu' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[dev,ml]'
python research/cpu_delivery/run.py --out /workspace/geo-cpu-campaign
```

Windows'ta çıktı yolu örneğin `C:/geo-cpu-campaign` olabilir. Bu kampanya CUDA
istemez; Windows'ta uçtan uca çalıştırma bu oturumda doğrulanmadı. Başlangıçta en
az 1 GiB boş disk kontrol edilir. Üç model aynı anda değil sırayla eğitilir;
sayısal iş parçacığı sayısı ikiyle sınırlanır.

Çıktı klasörü yeni ve depo dışında olmalı. Kesinti sonrası **aynı komuta**
`--resume` eklenebilir. Ayar/kod kimliği değişmişse yeni klasör gerekir. Başarısız
üretim/eğitim sessizce atlanmaz; son özet ancak üç eğitim tamamlandığında çıkar.

## Çıktılar

- `campaign.json`, `config-0.json` … `config-2.json`: çalıştırma öncesi sabitlenmiş
  ayarlar ve kaynak kimlikleri.
- `known/`, `unknown/`: doğrulanan fiziksel veri; `seed-*/`: modeller, eşikler,
  ayrıntılı sonuçlar ve tahminler. Bunlar Git dışında kalır.
- `execution.jsonl` ve `*.log`: adım komutları, gerçek süreler, hata ve zaman aşımı.
- `summary.json`, `summary.md`: bütün tohum/skor/aile sonuçları ve sayımlar.
- `figures/cpu_unknown_roc.{png,pdf}`: üç tohumun ROC eğrileri.
- `figures/cpu_family_auroc.{png,pdf}`: her bilinmeyen aile ve skor için AUROC.

AUROC'da bilinmeyen pozitiftir; yüksek skor daha bilinmeyen demektir. Üç tohum
aynı veriyi paylaşır: ortalama/aralık optimizasyon değişkenliğidir, güven aralığı
değildir. Önceden kullanılan geliştirme test grupları bu prefix'te bulunabilir;
bu çalışma yeni ve hiç görülmemiş bir nihai B2 test değerlendirmesi sayılmaz.
Başarı düzeyi ne olursa olsun bütün sonuçlar raporlanır.
