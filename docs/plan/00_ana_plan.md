# Ana Plan — Payload-Aware Open-Set Interference Recognition for GEO Transponders

Sürüm 0.4 · 2026-10-09 · Durum: P0 kapandı; sıradaki P2-A

Bu dosya projenin "harita" belgesidir. Her faz ayrı bir oturumda, tek bir alana odaklanarak detaylandırılır; bu dosya yalnızca fazları, sıralarını, çıktılarını ve açık kararları tutar.

---

## 0. Çalışma varsayımları (yanlışsa düzeltin, plan buna göre değişir)

| # | Varsayım | Etkilediği yer |
|---|---|---|
| V1 | **[ONAYLANDI 2026-10-09]** Ders projesi; sonra makaleye dönüştürülecek. İki kademe: Kademe A = ders teslimi (küçük kapsam), Kademe B = makale genişletmesi | Kapsam, süre, C1/C2/C3 seçimi |
| V2 | **[ONAYLANDI 2026-10-09]** Sabit teslim tarihi yok; öncelik erken üretim. Hızlı yol sırası için bkz. `P0_kapsam.md` §5 | Faz sırası |
| V3 | Tek GPU'lu iş istasyonu sınıfı donanım | Veri seti boyutu, transformer boyutu |
| V4 | Operatör verisi YOK kabul edilir; gelirse bonus | Risk R1, doğrulama stratejisi |
| V5 | **[ONAYLANDI 2026-10-09]** Ana depo: `mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders` (ESM-DL değil). Planlama dosyaları `docs/plan/` altında; kod yapısı P4'te belirlenir | Depo yapısı (P4) |
| V6 | **[KARAR 2026-10-09]** Simülatör IQ üretir; model girdisi IQ'dan türetilen spektrogramdır. Ayrıca SnT veri formatıyla uyumlu "tek FFT çerçevesi, yalnızca genlik" kipi tutulur (önceki çalışmalarla karşılaştırma için) | Cyclic dalı, spektrogram çözünürlüğü |
| V7 | **[ONAYLANDI 2026-10-09]** Masaüstü ölçüm imkânı yok → gerçeklik çapası yalnızca (c) ölçülmüş PA verisi; makale açıkça "simülasyon çalışması" olarak konumlanır | Risk R1, hedef yayın |

### Kademe A / Kademe B kapsamı
| | Kademe A (ders projesi) | Kademe B (makale) |
|---|---|---|
| Simülatör | Tek pol, tek transponder; doğrusal + IMUX/OMUX + TWTA; çok taşıyıcı | + çift pol, faz gürültüsü, ölçülmüş PA modeli |
| Sınıflar | clean, CW, swept CW, unauthorized carrier, overdrive IM | 8 bilinen + open-set rotasyonu |
| Model | Tek ResNet + plan maskesi + CA-CFAR baseline | + çapraz pol kanalı, open-set skorları, transformer (opsiyonel) |
| Ana sonuç | Payload gap'in ilk ölçümü (doğrusal eğitim → doğrusal olmayan test) | Tam C3 + ablasyonlar + SnT formatında karşılaştırma |

### Dış veri — doğrulanan durum (2026-10-09, kaynak sayfalarından)
| Kaynak | Gerçekte ne veriyor | Projedeki gerçekçi rol |
|---|---|---|
| SnT on-board interference | Tek FFT çerçevesi: 1000 veya 100 bin, genlik ya da karmaşık; 12000 eğitim + 3000 doğrulama; 6 sınıf (girişim yok / 5 alt banttan biri) | Algılama alt görevinde önceki çalışmayla karşılaştırma; zaman ekseni ve girişimci türü etiketi yok |
| SnT NGSO→GSO | Yalnızca genlik, 800 nokta (zaman veya FFT); ikili etiket; simülasyon | Anomali algılama karşılaştırması; IQ yok |
| DARCY Highway 2 | L-bant (E1/E6); 20 ms IQ olarak kaydedilmiş, numpy float64 olarak dağıtılıyor; CC BY-NC-SA; DataPort aboneliği veya GitLab | Zayıf; Kademe B'de opsiyonel. Dağıtılan dosyanın IQ mu spektrogram mı olduğu [DOĞRULANACAK] |
| OpenDPD | Ölçülmüş PA giriş/çıkış IQ çiftleri (ör. APA_200MHz); Apache-2.0 | "Görülmemiş, ölçülmüş yükselteç" testi. PA teknolojisi [DOĞRULANACAK] |
| TorchSig | Artık sentetik IQ **üretici**; güncel README'de "WidebandSig53" adıyla hazır set yok | Ön eğitim baseline'ı için veri üretilecek; dokümandaki ad güncellenecek |
| Zenodo 13371136 (yeni) | Intelsat 37e C-bant transponderi üzerinden gerçek downlink IQ kaydı, SigMF, 4.8 MB | Gerçek "clean" transponder sinyaliyle simülatör akıl sağlığı kontrolü |
| RF WebLab | Henüz denetlenmedi | [DOĞRULANACAK] |

---

## 1. Mevcut dokümanda düzeltilmesi gerekenler

### 1.1 Teknik hatalar / belirsizlikler

| # | Dokümandaki ifade | Sorun | Önerilen düzeltme |
|---|---|---|---|
| D1 | "…injection of receiver phase noise, signal passes through the IMUX and TWTA…, gets into the OMUX that is eventually turned into downlink noise" | Zincir sırası ve gürültü tanımı karışık. OMUX gürültüye "dönüşmez"; faz gürültüsü alıcıdan değil frekans dönüştürücü LO'sundan gelir. | Zincir: **uplink taşıyıcılar + uplink girişimciler + uplink termal gürültü → uydu Rx anteni (XPD) → LNA → frekans dönüştürme (LO faz gürültüsü) → IMUX → kanal yükselteci (FGM/ALC) → TWTA → OMUX → Tx anteni (XPD) → downlink yolu → izleme istasyonu anteni (downlink girişimi burada girer) → izleme alıcısı gürültüsü → IQ/PSD** |
| D2 | Tüm girişimciler "uplink'te giriyor" gibi anlatılmış | Girişimin **nereden girdiği** sınıfın imzasını belirler. Uplink'ten giren girişim TWTA'dan geçer (bastırma, IM üretir); downlink komşu uydu girişimi transponder'dan hiç geçmez. | Her sınıf için "giriş noktası" (uplink / payload içi / downlink) açıkça tanımlanmalı. Adjacent-satellite sınıfı uplink-ASI ve downlink-ASI olarak iki alt mekanizmaya ayrılmalı ya da biri seçilmeli. |
| D3 | "TWTA (Saleh model at a set input back-off)" + "traceable to the DVB-S2 reference satellite channel" | İkisi aynı şey değil. Saleh'in klasik katsayıları belirli bir tüpe uydurulmuştur; DVB-S2 standardı kendi AM/AM–AM/PM eğrilerini ve IMUX/OMUX genlik/grup gecikmesi maskelerini verir. | Birincil model: DVB-S2 referans transponder eğrileri (tablo/interpolasyon). Saleh: bu eğrilere uydurulmuş ikincil/analitik model + "görülmemiş yükselteç" genelleme testi. Standart madde numaraları P2'de doğrulanacak. |
| D4 | "multicarrier DVB-S2 loading" + DVB-S2 referans kanalı | DVB-S2 referans kanalı tek taşıyıcı / doyuma yakın çalışma içindir. Çok taşıyıcılı çalışma birkaç dB geri çekilme gerektirir ve farklı bir çalışma rejimidir. | İki çalışma modu açıkça tanımlanmalı: (a) tek taşıyıcı/transponder, (b) çok taşıyıcı FDM. "Overdrive IM" yalnızca (b)'de anlamlıdır. |
| D5 | "overdrive IM" sınıfı vs "clean" | Çok taşıyıcıda IM **her zaman** vardır. Sınıf sınırı tanımlı değil → etiket gürültüsü. | Nicel eşik: ör. nominal IBO'dan ≥X dB sapma veya C/IM < Y dB. Eşik P3'te sabitlenir. |
| D6 | unauthorized carrier / adjacent-satellite / carrier-under-carrier / cross-pol | Dördü de "modüleli taşıyıcı"dır; tek pol spektrogramda ayırt edilemeyebilir. Ayrım yalnızca plan maskesi + çapraz pol + güç/konum ilişkisi ile mümkün. | Identifiability analizi (C2'nin parçası) modelden **önce** yapılmalı (P3). Ayırt edilemeyen çiftler birleştirilir veya "gerekli gözlemlenebilir" koşuluna bağlanır. |
| D7 | Tek etiketli 8 sınıf | Gerçekte eşzamanlı birden çok olay olur; ayrıca operatör "hangi frekansta" bilgisini ister. | Karar gerekli: tek-etiket sınıflandırma / çok-etiket / frekans ekseninde segmentasyon. Öneri: çerçeve başına çok-etiket + kaba frekans lokalizasyonu; ilk sürümde tek girişimci. |
| D8 | 3 sabit "unknown" sınıf | Yalnızca 3 sabit bilinmeyenle open-set sonucu o 3 sınıfa özgü kalır. Ayrıca "pulsed" ile "intermittent bursts" tanımı örtüşüyor. | Sabit 3 bilinmeyene ek olarak **leave-one-class-out rotasyonu** (bilinen sınıflar sırayla dışarıda bırakılır). Bilinmeyen tanımları parametrik olarak ayrıştırılır. |
| D9 | "Fraunhofer DARCY GNSS datasets → real interferer recordings" | L-bant GNSS jammer kayıtları; bant, bant genişliği ve kanal farklı. Doğrudan "gerçek GEO girişimi" iddiası taşımaz. | Rolü daralt: yalnızca "gerçek donanım kusurları taşıyan girişimci dalga biçimi kaynağı" (yeniden örneklenip uplink'e enjekte edilir). Format/lisans P8'de doğrulanacak. |
| D10 | "OpenDPD; RF WebLab → measured amplifier nonlinearity" | Bildiğim kadarıyla ikisi de katı-hal (GaN) PA ölçümleri; TWTA değil. | İddia: "TWTA doğrulaması" değil, "ölçülmüş, hafızalı gerçek PA'ya genelleme". P8'de doğrulanacak. |
| D11 | Plan maskesi her zaman doğru varsayılıyor | Operasyonda plan bayat/hatalı olabilir. | Ablasyon ekle: plan hatası (kayık frekans, eksik/fazla taşıyıcı) altında dayanıklılık. |
| D12 | "detection probability at fixed false-alarm rate versus C/I" | C/I tek başına yetersiz; girişimci bant genişliği ve gürültü tabanı da belirleyici. | Eksenler: C/I **ve** I/N (veya INR); sınıf bazında eğriler. |
| D13 | Open-set yöntemleri: MSP, energy, Mahalanobis | Üçü de sonradan-skorlama; hakem "eğitim-zamanı open-set" yöntemi sorabilir. | En az bir eğitim-zamanı yöntem (ör. outlier exposure veya prototip/merkez kayıplı) karşılaştırmaya eklenir. P6'da seçilir. |
| D14 | "Roadmap, risks and venues" boş | — | P9'da doldurulacak; ön risk listesi aşağıda (§6). |

### 1.2 En büyük yapısal risk

**C3 ("payload gap") tamamen simülasyon-içi bir karşılaştırma.** "Doğrusal simülatörle eğitilen model, doğrusal olmayan simülatörde kötü" bulgusu, gerçek veri olmadan "iki simülatör arasındaki fark" olarak eleştirilir. Makalenin ikna gücü için en az bir gerçeklik çapası gerekir:
- (a) operatör verisi (en güçlü, en belirsiz),
- (b) SDR + gerçek yükselteç ile masaüstü döngü (orta maliyet, güçlü),
- (c) ölçülmüş PA modelleri (OpenDPD/WebLab) üzerinden "görülmemiş donanım" testi (ucuz, zayıf ama savunulabilir).

Plan (c)'yi garanti, (b)'yi hedef, (a)'yı fırsat olarak alır.

---

## 2. Katkı konumlandırması (öneri)

- **C1 = altyapı** (makalenin yöntem bölümü + açık kaynak yayın).
- **C3 = ana bulgu** (makalenin başlığını taşıyan nicel sonuç).
- **C2 = bulguyu taşıyan yöntem**; identifiability analizi C2'nin en özgün kısmı ve ucuz — öne alınır.
- Transformer vs CNN karşılaştırması ve cyclic dalı **ikincil**; süre sıkışırsa ilk kesilecekler.

---

## 3. Faz haritası

Her faz = bir (veya birkaç) odaklı planlama oturumu. Çıktısı ayrı bir dosyadır. Bir faz "kapanış kriteri" sağlanmadan kapanmaz.

| Faz | Odak | Çıktı dosyası | Kapanış kriteri | Skill / agent |
|---|---|---|---|---|
| **P0** | Kapsam ve çerçeve | `P0_kapsam.md` | V1–V6 onaylı; ana katkı seçili; "yapılmayacaklar" listesi yazılı | proje skill'i |
| **P1** | Literatür ve yenilik kontrolü | `P1_literatur.md` + kaynak tablosu | "Gap" paragrafındaki her iddia en az 2 kaynakla desteklenmiş veya düzeltilmiş; en yakın 5 çalışma ile fark tablosu | research-assistant + literatür tarayıcı agent |
| **P2** | Sinyal ve sistem modeli şartnamesi | `P2_sistem_modeli.md` | Zincirin her bloğu için: denklem, parametre aralığı, kaynak, birim; sensör modeli (fs, BW, süre, IQ/PSD) sabit | satcom-payload-modeling |
| **P3** | Sınıf taksonomisi ve identifiability | `P3_taksonomi.md` | Her sınıf: giriş noktası, parametre dağılımı, etiket kuralı; sınıf×gözlemlenebilir matrisi; ayırt edilemeyen çiftler çözülmüş | satcom-payload-modeling |
| **P4** | Simülatör mimarisi ve doğrulama planı | `P4_simulator_tasarim.md` | Modül arayüzleri, konfig şeması, depo yapısı; her blok için sayısal doğrulama testi ve kabul toleransı | code-architect + ew-python-simulation |
| **P5** | Veri seti tasarımı ve split protokolü | `P5_veri_protokol.md` | Parametre ızgarası, örnek sayıları, train/val/test koşul ayrımı **kod yazılmadan** dondurulmuş; depolama formatı ve boyut bütçesi | openset-rf-eval-protocol |
| **P6** | Modeller, open-set yöntemleri, baseline'lar | `P6_modeller.md` | Her model: girdi tensörü, mimari, parametre bütçesi; baseline'ların tam tanımı; hiperparametre arama bütçesi | openset-rf-eval-protocol |
| **P7** | Değerlendirme ve ablasyon protokolü | `P7_degerlendirme.md` | Her iddia ↔ deney ↔ metrik ↔ tablo/şekil eşlemesi; istatistik (tohum sayısı, güven aralığı) | openset-rf-eval-protocol |
| **P8** | Dış veri denetimi | `P8_dis_veri.md` | Her kaynak: erişilebilirlik, lisans, format, bant/fs, projedeki kesin rolü, "kullan / kullanma" kararı | veri denetçisi agent |
| **P9** | Yol haritası, riskler, hedef yayın | `P9_yol_haritasi.md` | Haftalık kilometre taşları, risk kaydı (olasılık/etki/önlem), 2–3 hedef dergi + yedek | proje skill'i + kırmızı takım agent |

**Sıra (v0.4, hızlı yol):** P0 ✔ → P2-A → P4-A + kod → P3-A + kod → P5-A → P6-A/P7-A → [Kademe B: P1 ∥ P8 → P2–P7 B dilimleri → P9]. Ayrıntı `P0_kapsam.md` §5. Eski sıra: P0 → P1 ∥ P8 → P2 → P3 → P4 → P5 → P6 → P7 → P9. (P1 ve P8 web araştırması gerektirir, paralel yürür; P3'ün sonucu P5–P7'yi değiştirebilir, bu yüzden önce gelir.)

**Uygulamaya geçiş (planlama bittikten sonra)** — önceki önerideki sıra geçerli, P4'te detaylanacak:
1. Tek taşıyıcı, doğrusal kanal (referans) → 2. IMUX/OMUX → 3. TWTA + IBO süpürme → 4. çok taşıyıcı → 5. faz gürültüsü, çift pol → 6. clean+CW ile uçtan uca pipeline + CA-CFAR baseline → 7. 8 sınıf.

---

## 4. Skill ve agent seti

### 4.1 Mevcut skill'lerin eşlemesi
| Skill | Kullanım |
|---|---|
| research-assistant | P1 (makale okuma, fark tablosu) |
| code-architect | P4 (simülatör mimarisi, depo yapısı) |
| ew-python-simulation | P4 ve uygulama (sinyal işleme kodu, doğrulama) |
| ew-radar-system-analysis | P2 (bütçe/SNR türetmeleri — radar ağırlıklı, satcom için eksik) |
| visualization | Şekil ve spektrogram planı |

### 4.2 Oluşturulacak yeni skill'ler (bu oturumda öneri kartı olarak sunuldu)
1. **geo-interference-project** — proje hafızası ve oturum protokolü: düzeltilmiş zincir, faz listesi, karar günlüğü formatı, "tek oturum = tek faz" kuralı.
2. **satcom-payload-modeling** — bent-pipe zincirinin modellenmesi ve sayısal doğrulama kontrol listeleri (mevcut EW skill'lerinin kapsamadığı alan).
3. **openset-rf-eval-protocol** — koşula göre split, sızıntı kontrolü, open-set metrikleri, ablasyon ve istatistik kuralları.

### 4.3 Agent rolleri (istendiğinde çalıştırılacak görev tanımları)
| Agent | Görev | Çıktı |
|---|---|---|
| Literatür tarayıcı | P1: GEO/satcom girişim tanıma, open-set RF, transponder doğrusalsızlığı altında ML konularında kaynak tarar; her iddiayı kaynağa bağlar | Kaynak tablosu + en yakın çalışmalar |
| Veri denetçisi | P8: tablodaki her veri kaynağını açıp lisans/format/bant bilgilerini doğrular | Kaynak başına denetim kartı |
| Kırmızı takım hakem | Her faz çıktısını **üretim sürecini görmeden** hakem gözüyle eleştirir | Öncelikli itiraz listesi |

---

## 5. Oturum protokolü

1. Oturum başında: hangi faz, girdi dosyaları, önceki açık kararlar.
2. Tek faz, tek çıktı dosyası. Faz dışı konular "park listesi"ne yazılır.
3. Her sayısal değer: kaynaklı, ya da açıkça **[VARSAYIM]** / **[DOĞRULANACAK]** etiketli.
4. Oturum sonunda: karar günlüğüne ek (karar, gerekçe, alternatif, tarih) ve bu ana planın güncellenmesi.
5. Faz kapanmadan kırmızı takım geçişi (P2, P3, P5, P7 için zorunlu).

---

## 6. Ön risk kaydı (P9'da tamamlanacak)

| # | Risk | Etki | Önlem |
|---|---|---|---|
| R1 | Gerçek veri yok → "sim-to-sim" eleştirisi | Yüksek | §1.2'deki (c) garanti, (b) hedef |
| R2 | Sınıflar tek gözlemle ayırt edilemiyor | Yüksek | P3 identifiability önce; sınıf birleştirme serbest |
| R3 | Benzer bir çalışma yayımlanmış/yayımlanıyor | Yüksek | P1'i en başta yap |
| R4 | Geniş bant IQ + çift pol → veri hacmi/hesap patlaması | Orta | P5'te boyut bütçesi; anında üretim (on-the-fly) |
| R5 | Kapsam şişmesi (3 katkı + 2 mimari + cyclic dalı) | Orta | §2'deki kesme sırası |
| R6 | Koşula göre split'te dağılım kayması o kadar büyük ki her model çöker | Orta | Kademeli split (yakın/uzak görülmemiş koşul) |

---

## 7. Açık kararlar (karar günlüğü tohumları)

| # | Karar | Hangi fazda |
|---|---|---|
| K1 | ~~Hedef çıktı türü ve süre~~ — kapandı: ders projesi → makale, sabit tarih yok | P0 ✔ |
| K2 | Sensör: IQ (kapandı); fs ve gözlem süresi açık | P2-A |
| K3 | Tek transponder mı, çok transponderli görünüm mü | P2 |
| K4 | Tek-etiket / çok-etiket / segmentasyon | P3 |
| K5 | Adjacent-satellite: uplink, downlink ya da ikisi | P3 |
| K6 | Overdrive eşiği | P3 |
| K7 | DVB-S2 dalga biçimi: kendi üretici mi, hazır kütüphane mi | P4 |
| K8 | ~~Gerçeklik çapası~~ — kapandı: yalnızca (c) ölçülmüş PA verisi, Kademe B | P0 ✔ |
