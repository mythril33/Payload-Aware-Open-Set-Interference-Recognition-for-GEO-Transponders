# Tam B2 değerlendirmesi ve rapor üretimi

17 Kasım 2026: birincil skor **Mahalanobis**. Kullanıcı, tam GEO testine
bakılmadan sorulan seçim sorusuna “Mahalanobis — mevcut öneri” yanıtını verdi.
MSP ve Energy de raporlanır; birincil skor sonuçlara göre değiştirilmez.
[Karar kaydı](../plan/b2_primary_scorer_2026-11-17.json), mevcut
`geoml.b2_campaign.freeze_campaign` arayüzünün dört alanını kullanır.
`approved_at`, alınmış kararın kayda geçirildiği **10:53:10 +03:00** zamanıdır;
kullanıcı mesajının kesin gönderim saati iddia edilmez. Eski belgelerdeki
“öneri / NOT DESIGNATED” ifadeleri kendi tarihlerine aittir.

Tam B2 veri üretimi ve 15 modelin eğitimi henüz tamamlanmadı. Buradaki yazılım
ve sentetik doğrulamalar tanıma başarısı kanıtı değildir. Ölçülmüş mevcut CPU
sonuçları [ayrı B1-dev/2 raporundadır](../results/CPU_DELIVERY_2026-11-04.md).

## Sabit kapsam

| Profil | Görünümler | Tohumlar | Fit |
|---|---|---|---:|
| `proposed-full` | `co`, `dual`, `dual_residual` | 0, 1, 2 | 9 |
| `c2-h3-dual` | `dual_planmask`, `dual_noplan` | 0, 1, 2 | 6 |

Birincil uç nokta `dual_residual` görünümünün yakın bilinmeyen aileler için
FPR@95TPR değeridir. Bilinmeyen pozitif sınıftır; büyük skor daha bilinmeyen
anlamına gelir. Payda 4.000 bilinen test gözlemi, %95 TPR hedefinin popülasyonu
1.500 yakın-aile gözlemidir. `wideband_noise` ayrı değerlendirilir;
meşru `cid_overlay` birleşik bilinmeyen metriğine girmez.

H1/H2/H3 karşılaştırmaları sırasıyla `dual − co`, `dual_residual − dual` ve
`dual_planmask − dual_noplan` farklarıdır. FPR farkının negatif olması zengin
girdili modeli destekler. Üç eğitim tohumunun sonuçları ve betimsel özeti
verilir. Senaryo grubu bootstrap aralıkları donmuş model ve eşiklere koşulludur;
eğitim tohumu belirsizliği veya doğrulayıcı üstünlük iddiası içermez.
İsteğe bağlı `co` kontrolleri, LOKO ve C3 bu 15-fit teslimine dahil değildir.

## Kararı kampanyaya bağlama

Eğitim ve yalnız bilinen `val-calib` gruplarıyla kalibrasyon tamamlandıktan
sonra iki tam envanter birlikte dondurulur. Aşağıdaki yollar örnektir;
veri, model ve gözlem düzeyindeki çıktılar Git deposunun dışında tutulur.

```python
import json
from pathlib import Path
from geoml.b2_campaign import freeze_campaign

decision = json.loads(Path(
    "docs/plan/b2_primary_scorer_2026-11-17.json"
).read_text(encoding="utf-8"))

freeze_campaign(
    {"proposed-full": "/srv/geo/inventory-canonical.json",
     "c2-h3-dual": "/srv/geo/inventory-matched.json"},
    "/srv/geo/campaign.json",
    primary_scorer=decision["primary_scorer"],
    designation=decision,
)
```

Bu işlem 9 + 6 fit'in kaynak, veri, çalışma ortamı ve eğitim bütçesini
doğrular; mevcut kampanya dosyasının üzerine yazmaz. Karar kaydı bir bilimsel
seçimdir. Üretim yetkilendirmesi veya harici günlük erişimi sağlamaz.

## Donmuş modelleri değerlendirme

`geoml.b2_production_evaluation.evaluate_campaign_profile` veri üretmez,
eğitim yapmaz ve eşikleri yeniden ayarlamaz. Üç veri aşaması da zorunludur:
bilinen, yalnız-test aileleri ve seviye eşleşmiş küme. Gerçek çalışma ortamında
sağlanan `authorization` ve `journal` nesneleriyle kullanım:

```python
from geoml.b2_production_evaluation import evaluate_campaign_profile

# authorization ve journal, yürütme ortamının doğrulanmış portlarıdır.
# Bu örnek bunların yerine geçen bir onay veya bellek içi günlük oluşturmaz.
for profile, output in (
    ("proposed-full", "/srv/geo/eval-canonical"),
    ("c2-h3-dual", "/srv/geo/eval-matched"),
):
    evaluate_campaign_profile(
        "/srv/geo/data-known", "/srv/geo/campaign.json", output,
        unknown_data="/srv/geo/data-test-only",
        matched_data="/srv/geo/data-matched",
        profile=profile, device="cpu",
        authorization=authorization, journal=journal,
    )
```

Kanonik profil önce, eşleşmiş profil sonra okunur; eksik envanter ve sırasız
veya tekrarlanan okuma reddedilir. Başarısız/kısmi test okuması tüketilmiş
sayılır; aynı okuma yeni çıktı klasörüyle sessizce tekrarlanamaz. CPU çalışma
ortamı donmuş eğitim ortamıyla eşleşmelidir; tüm girdiler işlem boyunca
değişmeden kalmalıdır.

Gözlemler açılmadan önce gerçek üretim metadata'sı K17d kimlik kaydıyla
çapraz doğrulanır. Ana 500 test / 150 eşleşmiş gruba ek olarak önceden
belirlenen D-1 498 / 148 grupları ve K17d 35 / 465 grupları ayrı raporlanır.
Alt gruplar için yeniden eğitim veya kalibrasyon yapılmaz.

Her profil `results.json` ve `predictions.json` üretir. `completion.json`
ancak harici günlüğe tamamlanma kaydı başarıyla yazıldıktan sonra oluşturulur.
Bu işaret tek profilin tamamlandığını bildirir; `benchmark_complete=false`
korunur. Ham gözlem, model veya korunan test verisi bu belgede yer almaz.

## Kaydedilmiş çıktılardan rapor ve grafik

İki profil de başarıyla tamamlandığında, veri veya model tekrar açılmadan:

```bash
python -m geoml.b2_production_reporting \
  --evaluation /srv/geo/eval-canonical /srv/geo/eval-matched \
  --out /srv/geo/report
```

Varsayılan bootstrap tekrar sayısı 2.000'dir (`--n-boot`). Çıktılar
`report.json`, `comparison.md`, `near_fpr95.png` ve `near_fpr95.pdf` olur.
Çıktı klasörü yeni ve depo dışında olmalıdır. Okuyucu tamamlanma işaretlerini,
hash'leri, tam 15-fit listesini, popülasyonları ve iki profilin ortak
kökenini doğrular. Birincil skoru donmuş kampanyadan alır; komut satırında
sonuçlara göre birincil skor değiştirme seçeneği yoktur.

## Windows 11 bilgisayarında sıradaki adım

Kullanıcının bildirdiği makine 16 GB RAM, dahili ekran kartı ve en az 60 GB
boş alana sahip; WSL2 henüz kurulu değil. Çalışma yolu CPU'dur. Dahili ekran
kartına CUDA desteği varsayılmaz; bu makinede tam eğitimin süresi henüz ölçülmedi.

1. Windows CI'ın ürettiği `Payload-Aware-GEO-Workbench-Windows` ZIP'ini açıp
   `windows/KURULUM.bat` dosyasını çalıştırın.
2. **GEO WSL Kurulumu** kısayolunu açın. WSL2/Ubuntu kurulumu yönetici onayı
   veya yeniden başlatma isteyebilir. Ubuntu kullanıcı hesabını oluşturduktan
   sonra aynı kısayolu yeniden çalıştırın.
3. **GEO Pilot Başlat** ile sınırlı geliştirme pilotunu doğrulayın. Bu pilot
   yalnız train/val-select/val-calib rollerini kullanır; 15-fit kampanyayı
   başlatmaz. Ayrıntılar: [Windows kılavuzu](../../windows/BENIOKU.md).

Fiziksel Windows/WSL kurulumu, kalıcı veri/çıktı alanı, gerçek üretim çalışma
portları ve tam veri/eğitim kampanyası henüz doğrulanmadı. CI'daki Windows
paket testlerinin geçmesi fiziksel bilgisayarda WSL2 deneyinin çalıştığı
anlamına gelmez. Birincil skor kararı bu eksiklerden yalnız bilimsel seçim
adımını tamamlar.
