# Proje durumu ve eksik kaydı

Son güncelleme: 2026-10-10 · Bu dosya "şu an neredeyiz, ne eksik" sorusunun tek yanıtıdır; her oturum sonunda güncellenir.

## 1. Tek cümleyle

Kademe A'nın (ders projesi) bütün zinciri kodlandı ve uçtan uca çalışıyor: simülatör → etiketli veri → üç model + baseline → sonuç tabloları. Eksik olan, **tam boyutlu veriyle alınmış sonuç**; bu koşu sizin makinenizde yapılacak.

## 2. Fazlar

| Faz | Konu | Durum | Dosya |
|---|---|---|---|
| P0 | Kapsam | Kapandı | `P0_kapsam.md` |
| P2-A | Sistem modeli | Kapandı | `P2_sistem_modeli.md` |
| P4-A | Simülatör | Kapandı, 55+ test | `P4_simulator_tasarim.md` |
| P3-A | Sınıflar ve girişimciler | Kapandı | `P3_taksonomi.md` |
| P5-A | Veri protokolü | Donduruldu (A1) | `P5_veri_protokol.md` |
| P6-A | Model ve baseline | Kapandı | `P6_modeller.md` |
| P7-A | Değerlendirme | Kapandı; yalnızca pilot sonuç var | `P7_degerlendirme.md`, `../results/pilot_A.md` |
| P1 | Literatür ve yenilik | **Başlanmadı** | — |
| P8 | Dış veri denetimi | Kısmen (ana plan §0) | — |
| P9 | Yol haritası, hedef yayın | **Başlanmadı** | — |
| Kademe B | Çift pol, 8 sınıf, open-set | Başlanmadı | — |

## 3. Elde ne var

- **Simülatör (`src/geosim/`):** DVB-S2 referans transponderi. IMUX/OMUX resmi ETSI tablolarından, TWTA standardın şekillerinden sayısallaştırıldı. 36 ve 72 MHz, üç yükselteç modeli, doğrusal karşılaştırma zinciri.
- **Beş sınıf:** clean, cw, swept_cw, unauthorized, overdrive; aynı tohumda eşleştirilmiş örnekler.
- **Veri üreticisi:** 10 bölünme, parçalı ve kaldığı yerden süren üretim; senaryo başına yaklaşık 1 s.
- **Öğrenme hattı (`src/geoml/`):** küçük ResNet (≈ 310 000 parametre), CA-CFAR baseline (planlı ve plansız), tek komutla eğitim + değerlendirme + rapor.
- **Belgeler:** her faz için karar, gerekçe, reddedilen alternatif ve hakem itirazları.

## 4. Şimdiye kadarki bulgular

| Bulgu | Kaynak |
|---|---|
| TWTA, hiçbir dış girişim yokken taşıyıcı aralarını dolduruyor: IBO 3 dB'de −39,9 dB'den −16,9 dB'ye | P4 §4 |
| Saleh'in klasik katsayıları DVB-S2 referans tüpünden belirgin farklı (doyumda faz 22° ve 42°) | Kaynak notu |
| "Geri çekilme başına 2 dB" kuralı çalışma aralığında geçerli değil (ölçülen 1,25 dB/dB) | P2 §10 |
| Aşırı sürme ile gürültülü temiz transponder aynı aralık seviyesini verebiliyor | P3 §4 |
| Mutlak güç aşırı sürmeyi tek başına ele veriyor; iki zincirin seviyesi de farklı → seviye denetimi zorunlu | P5 §5 |
| C/I 25 dB üstündeki taşıyıcı üstü CW spektrumda neredeyse görünmez (0,2 dB tepe) | P6 §6 |

Bunların hiçbiri henüz tam veriyle alınmış bir model sonucu değil.

**Pilot koşu** (verinin %6'sı, `docs/results/pilot_A.md`): boru hattı uçtan uca çalışıyor. Beş sınıflı model dağılım içinde %83,4. Yük farkı nominal geri çekilmede küçük çıktı (doğruluk %78,7 → %76,8, aralıklar içinde); en belirgin etki, doğrusal eğitilen modelin aşırı sürme örneklerinin %84'üne dış girişim demesi. Model CW'de planlı CFAR'ı geçemiyor.

## 5. Eksik kaydı

### 5.1 Bu oturumda kapananlar

| Eksik | Nasıl kapandı |
|---|---|
| Model, baseline ve değerlendirme kodu yoktu | `src/geoml/` yazıldı; P6-A ve P7-A belgelendi |
| Seviye kısa yolu denetlenmiyordu | Taşıyıcıya göre normalizasyon; 7,5 dB kaymaya duyarsızlık testle doğrulandı |
| Şekil H.3'ün çizilen aralığın üstündeki uzatması varsayımdı | Ölçüldü: IBO 0 dB'de örneklerin %1,6'sı aralığın üstünde; iki farklı uzatma kuralı arasında aralık seviyesi farkı en çok 0,08 dB, IBO ≥ 2,5 dB'de sıfır. Varsayım sonuçları etkilemiyor. |
| Saleh katsayıları kaynaktan teyitsizdi | MathWorks belgesi aynı dört değeri Saleh 1981'e atıfla varsayılan olarak veriyor (ikincil kaynak; makalenin kendisine bakılmadı) |
| İlk model taşıyıcı üstündeki CW'leri kaçırıyordu | Gövde tam frekans çözünürlüğüne alındı, zaman havuzlama güç ortalamasına çevrildi, artırma eklendi |

### 5.2 Açık — sizde

| # | Eksik | Ne gerekiyor |
|---|---|---|
| S1 | Tam veri kümesi üretilmedi | `python -m geosim.dataset --out data/stageA --workers 4` (≈ 9 çekirdek-saat, 4,1 GB) |
| S2 | Tam sonuç yok | `python -m geoml.pipeline --data data/stageA --out runs/stageA --epochs 30 --seeds 0 1 2`, sonra `runs/stageA/results.md` dosyasını bana gönderin |
| S3 | Dizüstünde süre ölçülmedi | S1'i önce `--limit-seeds 10` ile deneyip süreyi yazın |
| S4 | Üç varsayılan karar onaysız | Aşırı sürme sınırı (P3 §0-A), tek etiket kuralı (P3 §0-B), doğrusal zincirde aşırı sürme (P5 §0) |

### 5.3 Açık — bende, sıradaki işler

| # | Eksik | Önem | Not |
|---|---|---|---|
| B0 | **Ana iddianın biçimi.** Pilotta yük farkı doğrulukta görünmedi | Yüksek | Tam veriyle teyit; gerekirse iddia yanlış alarm ve yanlış etiketleme üzerinden kurulur veya daha düşük geri çekilme eklenir (protokol değişikliği, günlüğe yazılır) |
| B1 | **Literatür ve yenilik denetimi (P1)** başlandı, bitmedi | Yüksek | Aday çalışmalar listelendi (SnT ICASSP 2023, Henarejos ve ark. 2019, GNSS ve radar open-set çalışmaları); hiçbiri okunup karşılaştırılmadı |
| B1b | Model dar bantlı girişimde (CW) zayıf | Orta | Tam veriyle yeniden bakılacak; gerekirse zaman ortalamalı spektrum ek kanal olarak verilir |
| B2 | Sonuç şekilleri (ROC, C/I eğrileri, karışıklık matrisi) | Orta | Tam sonuç gelince |
| B3 | Mutlak seviye ablasyonu | Orta | `--level absolute`; tam veriyle |
| B4 | Parametre aralıklarının hiçbiri kaynaklı değil (C/N, C/I, taşıyıcı sayısı) | Orta | B1 ile birlikte literatürden dayanak aranacak |
| B5 | Dış veri denetiminin kalanı: RF WebLab, OpenDPD'nin yükselteç teknolojisi, DARCY dosya biçimi | Düşük (Kademe B) | |
| B6 | Proje talimat belgesi hâlâ ilk hâlinde (zincir tarifi, veri kaynağı rolleri hatalı; "Roadmap, risks and venues" boş) | Orta | P9 ile birlikte düzeltilmiş metin önerilecek |
| B7 | Gerçek sinyalle akıl sağlığı denetimi (Zenodo'daki Intelsat 37e kaydı) | Düşük | |
| B8 | Proje skill'leri eski (faz sırası, Saleh'in birincil model olduğu varsayımı) | Düşük | Güncelleme önerisi sunuldu |

### 5.4 Bilinçli olarak ertelenenler (Kademe B)

- DVB-S2 PL çerçevesi anahtarı (P0'da "ikinci adım" olarak sözü verilmişti; Kademe A iddialarının hiçbiri gerektirmiyor, cyclic dalıyla birlikte yapılacak)
- Çift polarizasyon, cross-pol, komşu uydu, carrier-under-carrier sınıfları
- Open-set reddi ve bilinmeyen sınıflar
- Faz gürültüsü, ALC, komşu transponderler
- Uzman özellikli baseline, transformer, hiperparametre araması
- Görülmemiş süzgeç kümesi (26/33 MHz tabloları), IBO 5–8 dB bölgesi

### 5.5 Çözülemeyecek sınırlar

- **Gerçek veri yok.** Çalışma bir simülasyon çalışmasıdır; yük farkı iki simülatör arasındaki farktır. Ölçüm imkânı olmadığı için bu, makalede açıkça yazılacak bir sınırdır.
- **Doğrusallaştırılmış TWTA eğrisi seyrek** (dB başına bir nokta, basamaklı faz); bu modeldeki ayrıntılara güvenilmemeli.
- **ETSI ham dosyaları depoda değil**; yeniden üretmek isteyen kendisi indirmeli.

## 6. Önerilen sıra

1. Siz: S3 → S1 → S2 (veri ve tam koşu).
2. Ben, aynı anda: B1 (literatür) ve B4.
3. Sonuç gelince: B2, B3 ve ders raporu taslağı.
4. Ardından P9 ve B6; Kademe B planı.
