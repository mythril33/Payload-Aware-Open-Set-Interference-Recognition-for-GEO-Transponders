# Kod, deney ve rapor doğrulaması — 4 Kasım 2026

Taban: `3f26393`. Teslim hedefi: **8 Kasım Pazar, kod + deney sonuçları + rapor**.
Bu kayıt yeni çalıştırmaları tarihsel araştırma sonuçlarından ayırır.
`benchmark_complete=false`; tam GEO benchmark sonucu henüz yok.

## Bu oturumda gerçekten çalıştırılanlar

| Kontrol | Sonuç | Kapsam |
| --- | --- | --- |
| Gerçek-fizik geliştirme zinciri | **Geçti** | 24 gözlem; train/val-select/val-calib için birer grup; iki CPU epoch; kalibrasyon, freeze ve yerel kopya hash kontrolü |
| Adaptör ve kampanya testleri | **58 geçti**, 3,97 s; bir mevcut pytest/anyio uyarısı | `test_b2_real_generation.py`, `test_b2_production_training.py`, `test_b2_campaign.py` |
| Tam kod + kamusal veri testleri | **5.073 geçti, 2 başarısız, 10 atlandı**, 1.312,57 s | İki hata eksik dashboard kanıt envanteri kayıtlarıydı; düzeltme aşağıda. Track B dahil değil |
| Envanter düzeltmesi ve CPU çalıştırıcısı | **28 geçti**, 1,41 s | İki hatanın bulunduğu dashboard modülleri + altı yeni CPU kampanya sınır/resume/süreç-durdurma testi |
| CPU B1-dev/2 kampanyası | **Üç fit tamamlandı**, 355,07 s alt-süreç duvar toplamı | 716 fiziksel gözlem; 159 train, 80 select, 79 calib, 158 bilinen test ve 160 bilinmeyen test örneği |
| CPU sonuç aritmetiği ve şekiller | **Geçti** | On arşiv/şekil hash'i, 45 ROC/AP/OSCR popülasyonu, rol ayrımı ve kalibrasyon sayımı |
| Karşılaştırmalı makale kanıt denetimi | **Geçti** | 21 kaynak hash'i, 206 JSON değeri, 30 iddia grubu, altı skor satırının sayısal kontrolü |
| GEO makale kanıt denetimi | **Geçti** | 66 kaynak/şekil hash'i, 18 iddia grubu, 15 atıf; sekiz NOT RUN satırı korundu |
| PDF üretimi | **İki belge geçti** | 13 ve 16 sayfa; taşma ve eksik atıf kontrolü; yeni araştırma deneyi yok |
| Word aktarımı | **İki belge üretildi ve içerikleri denetlendi** | Karşılaştırmalı/GEO: 4/2 kaynakla aynı grafik, 31/57 yerel Word denklemi, 14/15 kaynak; son Word sayfalaması ayrıca kontrol edilmeli |
| Üretim hazırlık kontrolü | **BLOCKED**, beklenen çıkış kodu 4 | PASS 39 / FAIL 0 / BLOCKED 16 / NOT_RUN 1; çalıştırma izni vermez |

Tam testteki iki hata, önceki değişiklikten gelen iki ve bu oturumda eklenen üç
sonuç belgesinin `dashboard/data/evidence_map.json` içinde sınıflandırılmamasından
kaynaklandı. Belgeler uygun **türetilmiş belge/geliştirme pilotu** sınıfına
eklendi; otomatik olarak doğrulanmış üretim sonucu sayılmadı. İlgili iki modül
yeniden geçti; 22 dakikalık tam paket tekrar çalıştırılmış gibi sunulmaz.
Atlamalar: bir RSS sayacı izni, yedi bu Torch/makinede eşleşmeyen tarihsel
bit düzeyi kayıt, iki yalnız-Windows davranışı. Bir mevcut anyio/pytest uyarısı.
Tam testin 5,8 GB geçici fixture'ı test bittikten sonra temizlendi; günlük korundu.

## Ortama uyarlanmış yeni deney

Kullanıcının yerel ortamda deney yapma yönlendirmesiyle
[CPU-delivery-B1/1](../../research/cpu_delivery/PREREGISTRATION.md) kampanyası
sonuçlardan önce `4f4b74a` commit'inde kaydedildi. Mevcut A1/B1-dev/2 fizik ve
rol tanımları korunur: dört bilinen sınıf, dört bilinmeyen aile; en fazla 720
gözlem; üç eğitim tohumu; width 8 ve 10 epoch; CPU. Bu, sekiz sınıflı çift-pol
B2 benchmark'ın yerine geçmez. Donmuş B2 kaynakları ve testleri değiştirilmedi.
[Kampanya sonuçları ve grafikler](CPU_DELIVERY_2026-11-04.md) tamamlandı:
bilinen doğruluk ortalama %70,25; bilinmeyen AUROC MSP 0,6191, energy 0,5647,
Mahalanobis 0,3314. Sabit eşikte bilinmeyen reddi düşük; sonuç iyileştirmek
için test sonrası eşik/skor yönü değiştirilmedi. Kod, küçük sayısal sonuçlar,
grafikler, PDF ve Word raporu aynı teslim paketindedir.

## Sınırlı deneyin gerçek çıktısı

[Makinece okunabilir kayıt](delivery_development_2026-11-04.json), dışarıda tutulan
`exercise.json` dosyasının SHA-256 kimliğini ve gerçek eğitim/kalibrasyon çıktısını
içerir. Ham üretilmiş veri ve model depoya eklenmedi.

- Sekiz sınıf varyantı × üç bağımsız rol grubu = **24 gözlem**. Eğitim, model
  seçimi ve eşik kalibrasyonu ayrı gruplarda; test gözlemi okunmadı.
- `dual_residual`, width 2, iki epoch, CPU. Seçilen epoch 0;
  validation macro-F1 **0,02778** (epoch 1: **0**). Her validation rolünde
  yalnız sekiz bağımlı sınıf varyantı bulunduğundan bu sayı genelleme başarısı
  veya güven aralığı tahmini olarak kullanılamaz. Olumsuz sonuç saklanır.
- MSP, energy ve Mahalanobis eşikleri sekiz bilinen kalibrasyon gözleminden;
  temiz-alarm eşiği yalnız **bir** temiz gözlemden üretildi. Hedef kabul 0,95
  olması sahada veya testte %95 kabul sağlandığı anlamına gelmez.
- Üretici alt süreci: **40,366 s** duvar süresi, **47,062 s** kullanıcı CPU +
  **2,384 s** sistem CPU, **582.228 KiB** tepe RSS. Bunlar tüm hattın süresi
  veya üretim ölçeği kaynak garantisi değildir.
- Yerel veri/model kopyaları hash ile doğrulandı. Bağımsız depolama/afet
  kurtarma yeterliliği, GPU çalışması ve nihai test çıkarımı yapılmadı.

## Raporda kullanılabilecek mevcut araştırma sonuçları

Bu rakamlar **bu oturumda yeniden ölçülmedi**; mevcut kayıtların aritmetiği ve
kaynak eşleşmesi makale denetleyicisiyle doğrulandı. Ayrıntı ve güven aralıkları
[kamusal veri raporunda](public_data_baselines.md) ve makalede bulunur.

| Mevcut kanıt | Sonuç | Yorum sınırı |
| --- | --- | --- |
| Ölçülmüş GNSS LC, sinyal-seviyesi skoru | AUROC 0,9842; tespit 55/76, yanlış alarm 0/44 | 159 test kaydının yalnız 120'si boş değil; GEO tanıma sonucu değil |
| Ölçülmüş GNSS FIOT, temiz-uzaklık skoru | AUROC 0,8578; tespit 105/162, yanlış alarm 3/81 | Kayıt bazlı mevcut ayrım; GEO'ya aktarım denenmedi |
| FIOT RGB-seviye skoru | AUROC 0,2590 | Olumsuz sonuç; testten sonra skor yönü çevrilmedi |
| GEO simülasyon tanıları | NPR eğimi 1,248 dB/dB; iptal derinliği 12,78–16,47 dB | Fiziksel tanı, tanıyıcı üstünlüğü değil |

AUROC'da pozitif sınıf anormal/bilinmeyen örnektir; büyük skor daha anormal
demektir. Tespit ve yanlış alarm paydaları tablodaki kendi sınıf sayılarıdır.
Kayıt bootstrap aralıkları ile eğitim tohumu değişkenliği aynı belirsizlik
değildir. Ana B2 performans tabloları **NOT RUN** kalır.

## Yeniden çalıştırma

Python 3.12 kullanın. Bu oturumdaki sayısal paketler: NumPy 2.3.5, SciPy 1.17.0,
Torch 2.15.0+cpu; testlerde pytest 9.2.0, Streamlit 1.65.0, XGBoost CPU 3.4.1.
Kullanılan ortam `/workspace/.venvs/geosim`; kurulum yerel ve Git dışındadır.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install 'torch==2.15.0+cpu' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[dev,ml,xgb]' -r dashboard/requirements.txt
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES='' MPLBACKEND=Agg
python -m pytest -q -rs tests research/public_data/tests
PYTHONPATH=src python scripts/b2_real_execution.py --out /tmp/geo-development-new-run --groups 1
python paper/audit_evidence.py
python paper/validate_geo_b2.py
sh paper/build.sh
sh paper/build_geo_b2.sh
sh paper/export_docx.sh
```

Deney çıktı dizini yeni ve depo dışında olmalıdır; mevcut kayıtların üzerine
yazılmaz. Paket aralıkları tüm transitif bağımlılıkları sabitlemez; tam
üretim için ayrı ortam/host kaydı gerekir. PDF araçları ve Word sayfa düzeni
notları [teslim planında](../plan/DELIVERY_2026-11-08.md).

Kod ve raporların aynı sürümünü paketlemek için test edilmiş commit üzerinde:

```sh
git archive --format=zip --prefix=geo-delivery/ --output=../geo-delivery.zip HEAD
```

Bu arşiv yalnız Git'e alınmış kaynakları, küçük sonuç özetlerini ve belgeleri
içerir; ham veri, checkpoint, sanal ortam veya kimlik bilgisi içermez. Deneyin
yeniden çalıştırılması yukarıdaki komutla ayrı çıktı üretir. Şekiller
`paper/figures/` ve `docs/figures/b2/` içinde korunur.

## Tamamlanmamış işler

Bu çalışma ortamının okunan cgroup sınırları **2 CPU, 8 GiB RAM**;
`/workspace` overlay dosya sisteminin toplam kapasitesi **8.417.406.976 B**
(yaklaşık 7,84 GiB). Testler sürerken boş alan **5.516.906.496 B** idi; boş
alan anlık ölçümdür. Dosya sisteminin toplamı bile tahmini 8,6681 GB veri
artefaktından küçük ve 33,88 GiB başlangıç boş-alan kuralını karşılamıyor.
Bu nedenle mevcut ortam tam veri üretim host'u olarak yeterli değildir;
GPU donanımı sorgulanmadı. Bağımsız kalıcılık/yedekleme doğrulanmadı.

Tam veri üretimi, 15 üretim fit'i, GPU yeterlilik çalışması ve nihai held-out
değerlendirme bu oturumda yapılmadı. Gerçek host/depolama/yetki entegrasyonu ve
üretim ölçeğinde held-out yürütücüsü gerekiyor. Yazar/kurum/şablon ve belgelenmiş
yayın izinleri de son teslimden önce netleştirilmeli. Mevcut sonuçları bu
eksikleri kapatmış gibi sunmak projenin bilimsel kapsamını yanlış gösterir.
