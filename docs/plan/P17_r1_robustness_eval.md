# P17 — R1-eval/1: yük farkının geri çekilme eğrisi ve yükselteç uyumsuzluğu

Durum: **KODLANDI, KÜÇÜK FİZİKSEL KOŞUYLA DOĞRULANDI; TAM VERİ SONUCU YOK** · 2026-10-20 ·
Girdi: [P16](P16_literatur_duzeltme_programi.md) İP-1 ve İP-2, K11 kararı, [OpenDPD sondası](../results/opendpd_probe.md).

Kapanış kriteri: (1) A1 değişmeden, ayrı tohum aralıklı ve yalnız testten oluşan bir
protokol sürümü; (2) yeni yükselteç aileleri test edilmiş; (3) eğitilmiş Kademe A
modellerini bu kümelerde **yeniden eğitmeden** değerlendiren, IBO kutularına göre
yük farkı, ECE ve FPR@95TPR raporlayan bir değerlendirici; (4) uçtan uca küçük fiziksel koşu.

## 1. Neden

- Tarama ve P16: C3 tek sayı değil, **eğitim aralığından geri çekilme uzaklığının fonksiyonu** olarak raporlanmalı.
- "İki simülatör arasındaki fark" eleştirisine karşı, eğitimde görülmemiş yükselteç **aileleri**
  (yalnız Saleh ve doğrusallaştırılmış TWTA değil) ve ölçülmüş PA'dan türetilmiş bellekli modeller.

## 2. Bölünmeler (`geosim.dataset`, protokol `R1-eval/1`)

A1'in `SPLITS` sözlüğü, `PROTOCOL` adı ve istek biçimi değişmedi. R1 bölünmeleri
`R1_SPLITS` içinde, `PROTOCOLS` kaydıyla ayrı protokol adı taşır; bir R1 kaydını A1 diye
okumak hata verir (test). Her bölünme `test_id_nl`'e göre yalnız belirtilen koşulu değiştirir (test).

| Bölünme | Tohumlar | Değişen koşul | Sınıflar |
|---|---|---|---|
| `r1_ibo_sweep` | 400000– (300) | Nominal IBO 5–14 dB, aşırı sürme IBO 0–5 dB (eğitim: 9–13 ve 1–4) | 5 |
| `r1_amp_rapp` | 410000– (300) | Yükselteç `rapp_p2` | 5 |
| `r1_amp_opendpd_apa` | 420000– (300) | Yükselteç `opendpd_apa` | 4 (aşırı sürme yok, K11) |
| `r1_amp_opendpd_dpa` | 430000– (300) | Yükselteç `opendpd_dpa` | 4 (aşırı sürme yok, K11) |

Tohum aralıkları A1 (100000–340299), unknown (900000–), çift-pol (1000000–) ve olay
(2000000–) aralıklarıyla çakışmaz (test). R1 verisi A1 verisiyle **aynı dizine konmaz**:
Kademe A hattı tek protokol bekler; değerlendirici de yalnız R1 bölünmesi kabul eder.

**Belirsiz bölge.** `r1_ibo_sweep`'te 5–8 dB nominal IBO'daki örnekler A1'de hiç
üretilmemişti (P3 karar A); etiket kural gereği nedendir (`clean` vb.) ama sınır
tanımsızdır. Bu örnekler `gap` bölgesi olarak ayrı kutularda raporlanır; tek bir
birleşik sayıya katılmamalıdır.

## 3. Yükselteç aileleri (`geosim.payload`)

| Ad | Model | Kaynak / varsayım |
|---|---|---|
| `rapp_p2` | Rapp SSPA, AM/AM `r / (1 + r^{2p})^{1/(2p)}`, AM/PM yok, p = 2 | p **[VARSAYIM]** (SSPA'lar için yaygın 2–3); 0,02 dB tablolu; ızgara üstünde çıkış doyumda kalır |
| `opendpd_apa` | Bellek polinomu, K = 5, M = 3 | OpenDPD `APA_200MHz`, Ampleon GaN Doherty, 3,5 GHz |
| `opendpd_dpa` | Bellek polinomu, K = 5, M = 16 | OpenDPD `DPA_200MHz`, 40 nm CMOS dijital Doherty, 2,4 GHz |

Bellek polinomu: `y[n] = Σ_m Σ_k c[m,k] x[n−d_m] min(|x[n−d_m]|, clip)^k`. Katsayılar
`scripts/derive_opendpd_mp.py` ile OpenDPD commit `cb4c5ea` train bölümünden uyduruldu;
**derece yalnız val bölümünde** seçildi (en iyi val NMSE'nin 0,1 dB içindeki en küçük model);
test NMSE seçimden sonra bir kez hesaplandı: APA val −31,04 / test −30,64 dB, DPA val −33,78 /
test −33,89 dB. Ham veri depoda yok; dosya SHA-256'ları, commit ve Apache-2.0 atfı
`src/geosim/data/opendpd_mp.json` içinde.

Varsayımlar ve sınırlar:

1. **Ölçek:** ölçülen giriş RMS'i IBO 11 dB'ye (A1 nominal aralığının merkezi) yerleştirildi
   (`OPENDPD_IBO_REF_DB`) **[VARSAYIM]**. Ölçülen PA'ların doyumu ölçülmedi; IBO ve OBO bu cihazlar için
   nominal bir referansa göredir, fiziksel doyuma göre değil.
2. **Ölçüm aralığı (K11):** polinom terimlerindeki genlik ölçülen en büyük girişte (`clip`, APA 3,16 ×
   RMS, DPA 2,89 × RMS) kırpılır; üstündeki örnekler kenar kazancını korur. Bu örneklerin oranı her
   senaryonun metadata'sına `amplifier_input_beyond_measured` olarak yazılır ve raporlanır. Bu alan
   yalnız bellek polinomu yükselteçlerinde vardır; A1 metadata'sı değişmedi (test).
3. **Bellek gecikmeleri:** ölçümdeki tap aralığı, işgal edilen bant genişliğine göre korunarak 36 MHz
   transponder ve 288 MHz simülasyon hızına eşlendi (`REFERENCE_BANDWIDTH`) **[VARSAYIM]**: APA
   gecikmeleri (0, 2, 3, 5), DPA (0, 2, …, 32) örnek. Mutlak zaman eşlemesi belleği çok daha zayıf
   gösterirdi; bu seçim bilinçli bir zorlama testidir.
4. **DPA derecesi ızgara kenarında:** M = 16 ızgaranın en büyük değeri ve val NMSE M arttıkça iyileşmeye
   devam ediyor (M = 12 → 16: −32,1 → −33,8 dB). Izgara 16'da sınırlandı; daha uzun bellek denenmedi.
5. **TWTA değil:** ölçülen cihazlar katı-hal Doherty PA'dır; sıkışmaları ölçüm noktalarında zayıftır
   (sonda: p99'da ≤ 0,8 dB). Bu kümeler "TWTA doğrulaması" değil, **görülmemiş yükselteç ailesine
   aktarım** testidir.

## 4. Değerlendirici (`geoml.robustness`)

- Kademe A koşusunun `results.json`'undaki eğitim tohumları, seviye kipi, epok ve zaman havuzlamasıyla
  checkpoint'leri **yapılandırma ve kaynak kimliği denetimiyle** yükler; eğitim/val bölünmelerinin
  parmak izi o koşudakinden farklıysa durur (test). R1 verisiyle hiçbir şey eğitilmez, seçilmez,
  kalibre edilmez.
- Algılama eşiği: her eğitim tohumu için `val_nl` temiz örneklerinde hedef yanlış alarm %5 (P7 ile aynı).
- Metrikler, bölünme başına:
  - M-nl5 doğruluk, makro-F1 (yalnız mevcut sınıflar), sınıf başına geri çağırma, karışıklık matrisi;
  - **ECE**: en yüksek olasılık, 15 eşit genişlikli kutu (Guo ve ark., 2017);
  - eşikli algılama: gerçekleşen yanlış alarm ve sınıf başına Pd;
  - sıralama: AUROC ve **FPR@95TPR**. Pozitif = herhangi bir temiz-dışı etiket, negatif = `clean`.
    FPR, girişimlerin en az %95'ini bulan ilk eşikte (eşit skorlar gruplanmış) temiz örneklerin
    girişim sayılma oranıdır. Bu test sıralamasını özetler, işletim eşiği değildir;
  - dört ortak sınıfta M-lin ve M-nl4: doğruluk ve temizde yanlış alarm; aşırı sürme örneklerinin dış
    girişim sayılma payı.
- `r1_ibo_sweep` için 1 dB'lik IBO kutuları. Her kutu bölge etiketi taşır (`train`, `near` ≤ 1 dB,
  `gap` 5–8 dB nominal, `far`). Kutu metrikleri:
  - M-nl5 doğruluk ve temizde alarm;
  - **yük farkı** = aynı örneklerde M-nl4 − M-lin doğruluğu; eşleşmiş fark olduğu için aralık senaryo
    tohumları üzerinden alınır;
  - iki dört-sınıflı modelin aşırı sürmeye "dış girişim" deme payı.
- `ranking_metrics` (open-set) artık `unknown_fpr_at_95_tpr` da döndürür. Pozitif unknown, payda bilinen
  test olaylarıdır.
- Aralıklar: eğitilmiş ağırlık ve eşik sabitken senaryo tohumları üzerinden bootstrap. Eğitim tohumu
  belirsizliği ayrıca `per_training_seed` alanlarında. Boş seçimler `null` ve sayımla yazılır (katı JSON).

## 5. Çalıştırma

Tam ölçek (sizin makinenizde; Kademe A tam koşusundan sonra):

```bash
python -m geosim.dataset --protocol R1-eval/1 --out data/r1 --workers 4     # 4 × 300 tohum, ≈ 5 600 örnek
python -m geoml.robustness --data data/stageA --runs runs/stageA --r1 data/r1 --out runs/r1
```

Üretim süresi, bu oturumda tek iş parçacığında ölçülen örnek başına sürelerle (A1 doğrusal olmayan ≈ 1,3 s,
Rapp ≈ 1,5 s, OpenDPD-APA ≈ 1,6 s, OpenDPD-DPA ≈ 2,8 s): 1500 + 1500 + 1200 + 1200 örnek için
≈ 2,6 çekirdek-saat. Sizin makinenizde farklı olabilir. Üretilen veri ve çıktılar Git'e girmez.

OpenDPD katsayılarını yeniden türetmek:

```bash
git clone https://github.com/lab-emi/OpenDPD data/external/opendpd
python scripts/derive_opendpd_mp.py data/external/opendpd
```

**Dikkat (yarım kalan üretimler):** veri üreticisi `geosim/*.py` ve `geosim/data/*` dosyalarının
hash'ini isteğe yazar. Bu dilim `payload.py`, `scenario.py`, `dataset.py` ve yeni bir veri dosyası
eklediği için, eski kodla başlamış yarım bir A1 üretimi yeni kodla **sürdürülemez** (taze dizin gerekir).
Tamamlanmış ve doğrulanmış veri kümeleri okunmaya devam eder.

## 6. Doğrulama

- Değiştirilmemiş HEAD üzerinde tam test paketi: **544 test geçti** (baseline). Bu dilimden sonra:
  **569 test geçti** (25 yeni: yükselteç aileleri 9, R1 protokolü 5, metrikler ve değerlendirici 11).
- **A1 regresyonu:** 17 A1 örneğinin (5 sınıf × 3 A1 yükselteci, 72 MHz CW, ek bir temiz senaryo) spektrum
  ve maske SHA-256'ları ve metadata anahtarları değişiklikten önceki kodla **birebir aynı**.
- Testlerin yakaladığı hata: Rapp tablosu +30 dB üstünde kazancı sabit tutuyordu, yani çıkış doyuma gitmeden
  büyüyordu. Tabloya doyum ucu eklendi.
- Küçük fiziksel koşu: A1'den 6, R1'den 6'şar senaryo tohumu; 3 epok eğitim; uçtan uca değerlendirme;
  veri tekrar kullanımı doğrulandı. Modeller dejenere (30 eğitim örneği). Bu yalnız çalışma kanıtıdır:
  [sonuçlar](../results/r1_smoke.md).

## 7. Hakem itirazları

| İtiraz | Yanıt / sınır |
|---|---|
| "OpenDPD ölçeği keyfi; IBO 11 dB eşlemesi sonucu belirler." | Kabul edilen varsayım; `OPENDPD_IBO_REF_DB` tek yerde ve sonuçlara yazılır. Duyarlılık için farklı eşlemeyle ikinci bir sürüm (R1-eval/2) gerekir; bu dilimde yapılmadı. |
| "Ölçüm aralığı dışında kırpma sonucu iyimser yapar." | Oran her örnekte ölçülüp raporlanır; nominal IBO'da küçüktür (bu oturumda tek örneklerde ≤ 1,3·10⁻³). Aşırı sürme bölgesi bu cihazlarla hiç üretilmez (K11). |
| "IBO kutuları küçük örnekle gürültülü." | Kutu başına n ve senaryo-bootstrap aralığı yazılır; tam veri (300 tohum × 5 sınıf) kutu başına ≈ 100+ örnek verir **[TAHMİN]**. Küçük koşu yalnız çalışma kanıtıdır. |
