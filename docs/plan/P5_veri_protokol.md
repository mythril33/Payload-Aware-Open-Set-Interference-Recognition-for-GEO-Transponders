# P5-A — Veri kümesi tasarımı ve bölünme protokolü (Kademe A)

Durum: **DONDURULDU** — protokol A1, 2026-10-09 (bir karar veto edilebilir, §0) · Girdi: `P3_taksonomi.md`

Kapanış kriteri: parametre aralıkları, örnek sayıları ve eğitim/doğrulama/test koşul ayrımı eğitim kodu yazılmadan sabitlenmiş; depolama biçimi ve boyut bütçesi yazılı.

Bu tarihten sonraki her değişiklik §9'daki değişiklik günlüğüne gerekçesiyle yazılır.

## 0. Varsayılan aldığım karar: doğrusal zincirde aşırı sürme

Doğrusal zincirde intermodülasyon yok, bu yüzden `overdrive` sınıfı orada tanımsız.

| Seçenek | Ne olur | Değerlendirme |
|---|---|---|
| **A (seçilen)** | Doğrusal veriyle eğitilen model 4 sınıflıdır (overdrive yok). Doğrusal olmayan test kümesindeki `clean` ve `overdrive` örneklerinde bu modelin ne dediğine bakılır. | Proje belgesindeki iddiayı doğrudan ölçer: "yük intermodülasyonu dış girişimle karıştırılıyor". |
| B | Doğrusal zincirde overdrive örnekleri "yalnızca daha güçlü temiz sinyal" olarak üretilir. | Öğrenilemez bir sınıf yaratır; karşılaştırmayı bulandırır. |
| C | Overdrive tümüyle çıkarılır. | En ilginç sınıfı ve §P3-4'teki bulguyu kaybederiz. |

Sonuç olarak üç model eğitilecek: **M-lin** (4 sınıf, doğrusal veri), **M-nl4** (4 sınıf, doğrusal olmayan veri), **M-nl5** (5 sınıf, doğrusal olmayan veri). Yük farkı = M-lin ile M-nl4'ün aynı doğrusal olmayan test kümesindeki farkı.

## 1. İddialar ve onları sınayan veri

| # | İddia | Karşılaştırma | Test kümesi |
|---|---|---|---|
| İ1 | Doğrusal zincirle eğitilen model doğrusal olmayan zincirde bozulur | M-lin: `test_id_lin` ile `test_id_nl` (4 sınıf) | `test_id_lin`, `test_id_nl` |
| İ2 | Bu bozulma doğrusal olmayan zincirle eğitince kapanır | M-lin ile M-nl4 | `test_id_nl` |
| İ3 | M-lin, intermodülasyonu dış girişim sanar | M-lin'in `clean` ve `overdrive` örneklerindeki yanlış alarm oranı | `test_id_nl` |
| İ4 | Model görülmemiş çalışma koşullarına genellenir | M-nl5: dağılım içi ile her kayma kümesi | `test_ibo`, `test_bw72`, `test_amp_lin`, `test_amp_saleh` |
| İ5 | Model enerji dedektöründen iyidir | M-nl5 ile CA-CFAR, sabit yanlış alarmda | `test_id_nl` |

Hiçbir iddiaya bağlanmayan deney yok; metrikler ve tablolar P7-A'da.

## 2. Bölünmeler

Bölünme rastgele değil, tohum aralığına ve çalışma koşuluna göredir. Her tohum bir taşıyıcı planı, bir gürültü gerçekleşmesi ve bir bağlantı parametre takımı demektir; aynı tohumun beş sınıfı (eşleştirilmiş örnekler) her zaman aynı bölünmede kalır.

| Bölünme | Tohumlar | Sayı | Bant | Yükselteç | Zincir | Sınıf | Nominal IBO | Aşırı sürme IBO |
|---|---|---|---|---|---|---|---|---|
| `train_nl` | 100000– | 2000 | 36 MHz | H.3 | doğrusal olmayan | 5 | 9–13 | 1–4 |
| `train_lin` | 100000– | 2000 | 36 MHz | H.3 | doğrusal | 4 | 9–13 | — |
| `val_nl` | 200000– | 300 | 36 MHz | H.3 | doğrusal olmayan | 5 | 9–13 | 1–4 |
| `val_lin` | 200000– | 300 | 36 MHz | H.3 | doğrusal | 4 | 9–13 | — |
| `test_id_nl` | 300000– | 500 | 36 MHz | H.3 | doğrusal olmayan | 5 | 9–13 | 1–4 |
| `test_id_lin` | 300000– | 500 | 36 MHz | H.3 | doğrusal | 4 | 9–13 | — |
| `test_ibo` | 310000– | 300 | 36 MHz | H.3 | doğrusal olmayan | 5 | 8–9 ve 13–14 | 0–1 ve 4–5 |
| `test_bw72` | 320000– | 300 | **72 MHz** | H.3 | doğrusal olmayan | 5 | 9–13 | 1–4 |
| `test_amp_lin` | 330000– | 300 | 36 MHz | **H.2** | doğrusal olmayan | 5 | 9–13 | 1–4 |
| `test_amp_saleh` | 340000– | 300 | 36 MHz | **Saleh** | doğrusal olmayan | 5 | 9–13 | 1–4 |

- Her kayma kümesi dağılım içi teste göre **tek bir koşulu** değiştirir (testle denetleniyor).
- Kademeli kayma: `test_ibo` yakın (aralığın 1 dB dışı), `test_amp_*` orta, `test_bw72` uzak.
- Doğrusal ve doğrusal olmayan çiftler aynı tohumları kullanır: aynı senaryo iki zincirden geçer.
- Diğer bütün parametreler `P3_taksonomi.md` §2'deki aralıklardan çekilir.
- P3'teki IBO aralıklarının uçları (nominal 8–9 ve 13–14, aşırı sürme 0–1 ve 4–5) eğitimden çıkarılıp `test_ibo`'ya ayrıldı.

## 3. Boyut ve süre

| | Tohum | Örnek (yaklaşık) |
|---|---|---|
| Eğitim (nl + lin) | 2000 | 10 000 + 8 000 |
| Doğrulama (nl + lin) | 300 | 1 500 + 1 200 |
| Dağılım içi test (nl + lin) | 500 | 2 500 + 2 000 |
| Dört kayma testi | 4 × 300 | 6 000 |
| **Toplam** | | **≈ 31 200** |

- Plansız taşıyıcı sığmayan tohumlarda o sınıf atlanır (pilotta 367 örnekte 1 kez); sayılar bu yüzden yaklaşık.
- **Depolama:** örnek başına 128 × 512 float16 = 131 KB; toplam ≈ 4,1 GB.
- **Süre:** senaryo başına 1,05 s ölçüldü (bulut makinesi, iki süreç yan yana). Toplam ≈ 9 çekirdek-saat; 4 çekirdekli dizüstünde yaklaşık 2,5 saat beklenir, dizüstünde ölçülmedi.
- Hız kazancı taşıyıcı üretecinin frekans düzlemine taşınmasından geldi (3,3 s → 1,05 s). Yan etkisi: darbe biçimlendirme artık kesilmemiş ideal SRRC.

## 4. Üretim

```
pip install -e .[dev]
python -m geosim.dataset --out data/stageA --workers 4
```

- Bölünme başına bir klasör; 100 tohumluk parçalar (`part-*.npz`: `spec`, `mask`, `label`, `seed`; `meta-*.jsonl`: örnek başına tüm parametreler) ve `manifest.json` (protokol sürümü, kod sürümü, sınıf sayıları).
- Yarıda kesilirse aynı komut kaldığı yerden sürer; bitmiş parçalar yeniden üretilmez.
- `--limit-seeds 10` ile birkaç dakikalık deneme yapılabilir; `--splits` ile tek bölünme seçilir.
- Okuma: `geosim.dataset.load_split(klasör)`.

## 5. Pilot (bölünme başına 8 tohum, 367 örnek)

Boru hattı uçtan uca çalıştı; sınıf sayıları, IBO aralıkları ve eşleştirme beklendiği gibi. İki önemli gözlem:

**a) Mutlak güç, aşırı sürmeyi tek başına ele veriyor.** Bant içi toplam güç (dB, ortalama ± sapma):

| Bölünme | clean | cw | swept_cw | unauthorized | overdrive |
|---|---|---|---|---|---|
| `train_nl` | −4,87 ± 0,60 | −4,85 ± 0,61 | −4,69 ± 0,56 | −4,72 ± 0,63 | **−1,58 ± 0,24** |
| `test_amp_saleh` | −6,25 ± 1,03 | −5,90 ± 1,02 | −6,19 ± 1,03 | −6,10 ± 1,05 | −1,56 ± 0,22 |

Aşırı sürme 3,3 dB daha güçlü ve dağılımlar ayrık. Spektrogram mutlak seviyesiyle verilirse model bu sınıfı tek sayıyla çözer; seviye bilgisi verilmezse `P3_taksonomi.md` §4'teki zor problem kalır. Hangisinin gerçekçi olduğu izleme istasyonunun kalibrasyonuna ve yağmur zayıflamasına bağlı.

**b) Doğrusal ve doğrusal olmayan zincirin mutlak seviyesi farklı.** Aynı tohumların `clean` örneklerinde doğrusal olmayan zincir 0,6–1,65 dB daha zayıf (sıkışma). Mutlak seviye modele verilirse yük farkının bir kısmı yalnızca bu seviye kayması olur ve İ1 şişer.

**Bu yüzden P6-A için zorunlu denetim:** modele giden spektrogramın seviyesi ya örnek başına normalize edilecek ya da eğitimde ve testte rastgele kaydırılacak. Mutlak seviyeli sürüm ancak ayrı bir ablasyon olarak raporlanabilir. Veri kümesi mutlak seviyeyi saklıyor, yani iki yol da açık.

## 6. Sızıntı denetimleri

| Denetim | Durum |
|---|---|
| Bölünmeler arasında ortak tohum yok (doğrusal/doğrusal olmayan çiftleri dışında) | Testle denetleniyor |
| Her kayma kümesi tek koşul değiştiriyor | Testle denetleniyor |
| `test_ibo` hiçbir zaman eğitim IBO aralığından çekmiyor | Testle denetleniyor |
| Doğrulama kümesi yalnızca dağılım içi koşullardan | Tanım gereği |
| Normalizasyon istatistikleri yalnızca eğitim verisinden | P6-A'da uygulanacak |
| Etiketi ele veren parametre | Mutlak güç → overdrive (§5a); denetimi P6-A'da |
| Bağlantı parametreleri (C/N) sınıftan bağımsız | Eşleştirme gereği aynı |

Toplam 55 test geçiyor (4'ü bu faza ait).

## 7. Hakem itirazları

| İtiraz | Yanıt |
|---|---|
| "Eşleştirilmiş örnekler bağımsız değil; etkin örnek sayısı 10 000 değil 2000 plan." | Doğru. Güven aralıkları tohum (plan) düzeyinde hesaplanacak; P7-A'ya not edildi. |
| "Bant genişliği kayması tek yönlü (36 → 72)." | Kademe A kapsamı. Ters yön Kademe B'de. |
| "Kayma kümeleri 300 tohum; C/I'ye göre eğrilerde kutu başına örnek az." | 30 dB'lik aralık 5 dB'lik kutulara bölünürse sınıf başına kutuda ≈ 50 örnek. Eğriler için yetersiz kalırsa yalnızca test kümeleri büyütülür (eğitim değişmez, protokol bozulmaz). |

## 8. Açık sorular ve park listesi

- §0'daki kararın onayı
- Seviye normalizasyonu / kaydırma (P6-A, zorunlu)
- Park: IBO 5–8 dB "belirsiz bölge" test kümesi; görülmemiş süzgeç (26/33 MHz tabloları, Chebyshev) kümesi; ters yönlü bant genişliği kayması

## 9. Değişiklik günlüğü

| Tarih | Değişiklik | Gerekçe |
|---|---|---|
| 2026-10-09 | A1 ilk sürüm | — |
