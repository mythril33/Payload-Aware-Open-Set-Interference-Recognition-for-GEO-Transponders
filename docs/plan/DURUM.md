# Proje durumu ve eksik kaydı

Son güncelleme: 2026-10-21 (B2 yalnız-test aileleri, K17b artırımı ve ilk açık-küme koşusu; temel deney durumu 2026-10-10) · Bu dosya "şu an neredeyiz, ne eksik" sorusunun tek yanıtıdır; her oturum sonunda güncellenir.

## Uygulama eki — 2026-10-21 (üçüncü dilim: yalnız-test aileleri, K17b, açık-küme değerlendirmesi)

- **Kritik yol bağımlılığı kapatıldı — `B2-test/1` aşaması kodlandı:** [P21](P21_b2_test_families.md), `geosim.b2_test_dataset`. Beş yalnız-test aile (`pulsed`, `intermittent_bursts`, `adjacent_satellite_downlink`, `wideband_noise`, `cid_overlay`) yalnız dondurulmuş test gruplarında, bilinen varyantlarla aynı plan/link/akış/faz/eksik-taşıyıcı durumuyla ve bağlandığı bilinen artefaktın (B2-base/1 veya B2-feat/1) **aynı alıcı kalibrasyonuyla** üretilir; ayrı RNG ad alanı `[grup, 1830, aile]`. Eğitim/val rolleri için üretici reddeder; okuyucu yabancı rol dizinlerini reddeder. Beşinci kanal (artık) aynı iptal ayarıyla saklanır.
- **Yeni üreteçler:** `geosim.asi.adjacent_satellite_downlink` (K17d: aynı grubun bilinen uplink ASI RNG akışıyla grup başına **eşleştirilmiş** — geometri, C/I_psd, taşıyıcı, yerleşim aynı; yalnız giriş noktası farklı; alıcı feed gücüne ölçekli, yükü atlar; eksik taşıyıcılı gruplardaki etkin seviye sapması `effective_c_over_i_psd_db` olarak yazılır); `geosim.cid.cid_overlay(active=...)` susturulmuş taşıyıcının altında CID yok, kimlik çekilişleri korunur.
- **K17b eğitim-zamanı plan kaydırma artırımı kodlandı:** `TrainConfig.plan_shift_fraction=0,15`, `plan_shift_max_hz=0,5 MHz` (`configs/b2_feat.json`); yalnız eğitim yığınlarında, seçilen örneklerin maskeleri her iki feed birlikte sürekli Δf ile yeniden kurulur ve **ön işleme tamamen yinelenir** (A5 bozmasıyla aynı dönüşüm; taşıyıcı referansı da kayar). Doğrulama/test maskeleri asla kaydırılmaz (testle). Sıfır kayma saklı float16 maskeyi 0,02 dB içinde yeniden üretir.
- **Açık-küme değerlendirmesi:** `geoml.b2_experiment --unknown-data`: dondurulmuş checkpoint/skorlayıcı/eşiklerle aile ve ön kayıtlı grup başına AUROC/AP/OSCR/FPR@95TPR (bilinmeyen pozitif), eşikte ret, `cid_overlay` için temiz kabul / CuC deme / ret oranları; birleşik sayı yalnız "yakın" ailelerden; `wideband_noise` ayrı. Farklı bilinen veriye bağlı test artefaktı, farklı fizik/iptal ayarı veya bilinen test grubu dışındaki gruplar reddedilir.
- **Pilot ([rapor](../results/b2_test_pilot.md)):** 2 test grubu × 5 aile = 10 gözlem, ≈ 40 s; bağ ve tekrar kullanım doğrulandı. Fizik: dört bilinmeyen aile ham spektrumda ≤ 0,2 dB iken iptal artığında 0,9–3,5 dB görünür oluyor (CuC ile aynı mekanizma). Öğrenme koşusu 16 eğitim gözlemiyle şans düzeyinde; bütün açık-küme sayıları yalnız yürütme kanıtıdır.
- **Bağımsız hakem incelemesi** ([REVIEWER_RED_TEAM](../research/REVIEWER_RED_TEAM.md) §B2-test/1): sızıntı/rol ihlali yok; `prepare_scene` 144 durumda eski sürümle bit-özdeş. Altı düzeltme uygulandı: K17d grup eşleşmesi, rapor metni ve bilinmeyen-ret sütunu, `n_unknown` paydaları (yakın=6, tümü=8 ayrı), K17b tam ön işleme, tekrar üretilebilir `results_summary.json` kuralı, downlink seviye sapması belgesi.
- **Doğrulama:** tam paket **758 test geçti** (gerçek zincirli downlink ASI bütünleşme testi dahil).
- **Sıradaki:** seviye eşleşmiş ASI ↔ `unauthorized` kümesi (K17c, `test-matched` üreticisi); LOKO (A8) ve EDSC baseline; A5 çift-pol plan bozma; 20 gruplu maliyet ölçümü ve ardından bulutta tam üretim (bilinen ≈ 20–25 + yalnız-test ≈ 3 çekirdek-saat **[TAHMİN]**); eğitim kullanıcının GPU'sunda. K18 onayı bekliyor.

## Uygulama eki — 2026-10-21 (ikinci dilim: iptal artığı, beşinci kanal, iki çıktılı model)

- **Gözlemden iptal artığı kodlandı:** `geosim.cancellation` ([P20](P20_b2_cancellation_residual.md)). Girdi yalnız kalibre co-pol monitör IQ'su ve co-pol operatör planı; aktiflik maskesi, gerçek IBO/XPD, etiket, olay parametresi ve sembol **girmez** (imza testle sabitlenir). Karar yönlü yeniden modülasyon: ×3 yeniden örnekleme (tam örnek/sembol), SRRC eşleşmiş süzgeç, Oerder–Meyr zamanlama, simetri sektöründe faz ızgarası + LS karmaşık kazanç, yeniden modülasyon ve çıkarma; kenar koruması 512 örnek. Ayarlar `obs-cancel/1` olarak dondurulur ve isteğe bağlanır. **[VARSAYIM]** operatör planı MODCOD içerir.
- **Yeni artefakt aşaması `B2-feat/1`:** `b2_dataset --cancellation configs/cancellation.json`. `residual[N,128,512]` float16 eklenir; ham IQ saklanmaz. B2-base/1 istek düzeni ve parmak izleri değişmedi; eski kayıtlar okunur (testle). Çapraz aşama okuma ve bozulma reddedilir.
- **Beş kanallı model ve bağımsız `plan_consistency` çıktısı:** `preprocess_dual(view="dual_residual")` beşinci kanalı aynı co-pol taşıyıcı referansıyla ekler; `SmallResNet(aux_outputs=1)`; `TrainConfig` `plan_consistency`, `plan_loss_weight`, `center_loss_weight`. Eski checkpoint'ler okunur. Checkpoint seçimi yalnız bilinen sınıf makro-F1 ile.
- **Dondurulmuş roller üzerinde deney koşucusu:** `geoml.b2_experiment` + `configs/b2_feat.json`: train (ağırlık + Mahalanobis), val-select (checkpoint), val-calib (MSP/energy/Mahalanobis %95 kabul eşiği ve Pfa %5 temiz alarm, yalnız bilinen), test (bir kez). Eşleşmiş `co`/`dual`/`dual_residual`. Bilinmeyen metrikleri `null` + `n_unknown=0`.
- **K18 adayı (araştırmacı onayı bekler):** merkez kaybı ağırlığı **0,005** ve plan BCE ağırlığı 1,0 eğitimden önce donduruldu (P18 §10'a yazıldı); arama yok. Onaylanmazsa değer P18 günlüğüyle değiştirilir; test sonuçlarına bakılarak seçilmez.
- **Fizik kanıtı ([pilot](../results/b2_feat_pilot.md), 64 gözlem):** bant içi iptal derinliği ortalama 12,8–16,5 dB. Sınır iki yönlü: düşük C/N'de alıcı gürültü tabanı; yüksek C/N'de pencere içi izlenmeyen LO faz yürüyüşü (150 Hz etkin linewidth'te ≈ 21–25 dB tavan, C/N'den bağımsız; hakem bulgusu, yeniden üretildi). Faz gürültüsüz sentetikte 35–48 dB; plan dışı boşluk tabanı değişmedi (−0,02…−0,09 dB); `overdrive`/`cross_pol`'da derinlik fiziksel olarak düşük. **Eşleşmiş clean/CuC:** kurban bandında ΔPSD ortancası iptal öncesi 0,99 dB → sonrası 6,46 dB; 8/8 grupta artış. K9 ön kaydını fizik düzeyinde destekler.
- **Öğrenme dilimi pilotu:** 16 eğitim gözlemi, 3 epok; üç görünüm de şans düzeyinde (%12,5), plan-tutarlılık pozitif örneği yok. Yalnız yürütme ve veri akışı kanıtıdır. Checkpoint/skorlayıcı/kalibratör tekrar kullanımı doğrulandı.
- **Maliyet:** pilot üretim 243,8 s duvar / 285,1 s CPU, tepe RSS 585 MiB, 24,75 MiB kayıt (iptal ≈ 1,3–1,8 s/gözlem). Tam üretim tahmini ≈ 20–25 çekirdek-saat **[TAHMİN]**.
- **Doğrulama:** HEAD'de 707 test; bu dilimle **743 test geçti** (iptal 16, artefakt 5, ML 10, deney 5; mevcut CLI testi güncellendi; hakem düzeltmeleri dahil). Bağımsız hakem incelemesi: [REVIEWER_RED_TEAM](../research/REVIEWER_RED_TEAM.md).
- **Harness:** `CLAUDE.md`, `.claude/rules/` (bilimsel değişmezler, artefakt/yeniden kullanım), `.claude/skills/` (physics-check, reproducibility-audit, scientific-review), [depo denetimi](../research/PROJECT_AUDIT.md). `scripts/setup_cloud.sh` PyTorch indeksi engelliyse PyPI'a düşer.
- **Eksik (hakem):** K17b eğitim-zamanı plan kaydırma artırımı (%15, ±0,5 MHz sürekli) henüz yok; şu anki `b2_experiment` modelleri P18 ana modeli değildir. Faz izlemeli `obs-cancel/2` ayrı sürüm olarak önerildi.
- **Sıradaki:** K17b plan kaydırma artırımı; yalnız-test aileleri (`pulsed`, `intermittent_bursts`, `adjacent_satellite_downlink`, `cid_overlay`, `wideband_noise`) ve seviye eşleşmiş ASI kümesi için çift-pol B2 adaptörleri; EDSC baseline (aynı iptal kodu); A5 plan bozma çift-pol maskelerle; sonra bulutta tam üretim ve kullanıcı GPU'sunda eğitim.

## Uygulama eki — 2026-10-21 (birinci dilim: fiziksel gözlemler)

- **B2'nin bilinen fiziksel gözlem aşaması kodlandı:** [P19](P19_b2_base_observations.md), `B2-base/1`. Sekiz bilinen sınıf tek çift-pol zincirde ve ayrı train / val-select / val-calib / test rollerinde üretilir. Dondurulmuş B2/1, üst protokoldür; kayıtlar `benchmark_complete: false` taşır.
- Operatör planı ve gerçek yayınlar ayrıldı. Taşıyıcı düşerken plan maskesi, nominal kazanç ve kalan taşıyıcıların RNG akışı korunur. `plan_consistency` ayrı hedeftir. Kaynaklı ASI uplink'tedir; tarihsel E1 kayıtları değiştirilmedi.
- Bağımsız pilot kalibrasyonu, atomik shard/metadata kayıtları, checksum, doğrulanmış tekrar kullanım ve sınırlı bellekli shard okuma bağlandı. Gerçek iptal artığı, beşinci kanal, iki çıktılı/merkez kayıplı model, nihai unknown/CID ve seviye eşleşmiş test üretimi sıradaki paketlerdir.
- **Doğrulama: 707 test geçti.** 64 fiziksel gözlem (dört rol × iki grup × sekiz sınıf), doğrulanmış üretim tekrarı ve ana veriye katılmayan sekiz kontrollü taşıyıcı-düşmesi ikizi tamamlandı. Önceki motorla varsayılan IQ/PSD/maske ve metadata birebir eşleşti. [Pilot sonucu](../results/b2_base_pilot.md) ve [makinece okunur kayıt](../results/b2_base_pilot.json).
- Pilot üretim 109,55 saniye sürdü; üreticinin tepe belleği 545,52 MiB, kayıtlar 16,49 MiB. Model eğitilmedi; bu paket fiziksel/veri bağlantısını doğrular. Tam B2 benchmark ve bilimsel tanıma sonucu değildir.

## Literatür taraması eki — 2026-10-20 (P16)

- **Numara notu:** bu ek önce P15 olarak yayımlandı; aynı gün main'e ayrı bir P15 (faz gürültüsü ve olaylar, E1-dev/1) girdi. Literatür programı artık [P16](P16_literatur_duzeltme_programi.md); R1-eval/1 [P17](P17_r1_robustness_eval.md); B2/1 protokolü P18.
- **Çelişki (L16) çözüldü — K16:** E1-dev/1'in alıcı tarafındaki (TWTA'yı atlayan) olayı `adjacent_satellite_downlink` adıyla ayrı tutulacak; B2/1'deki `adjacent_satellite` sınıfı K5 gereği uplink-ASI olarak yeni kodlanacak. Kodda yeniden adlandırma henüz yapılmadı (P16 İP-3, tam test paketiyle).

- Kullanıcının verdiği literatür taraması okundu ve depo belgeleriyle karşılaştırıldı: [P16 düzeltme ve tamamlama programı](P16_literatur_duzeltme_programi.md). Yeni deney veya kod **yok**; yalnız belge, kaynakça ve plan.
- **Hüküm:** boşluk iddiası ayakta, ama yenilik "birlikte modelleyen ilk" biçiminde daraltılır (K10). Carrier-under-carrier ve ASI↔unauthorized ayırt edilemezlik bulgusu olarak tasarıma girer; gerçekçilik çapası yükselteç ailesi uyumsuzluğu + NPR + ölçülmüş PA olarak üç ayağa çıkar.
- Bu oturumda kapanan: P1'e tarama v2 eki ve planlanan/uygulanan boşluk matrisi; `open_set_protocol.md` CuC satırı; P9 yayın yeri adayları; `references.bib`'e 19 girdi (doğrulanmamışlar `note = {verify}`); aşağıdaki faz tablosu.
- Açık kalan çelişkiler (P16 §2): L1 Highway 2 lisansı (CC BY-SA mı BY-NC-SA mı), L2 OpenDPD kayıt adı (APA/DPA), L7 Daoud başlığı ve TR 102 376-2 başlığı, L10 XPD değerlerinin kaynağı, L12 yakın/uzak OOD gruplaması.
- **Kararlar alındı (2026-10-20):** K5 uplink-ASI (downlink veto), K9 iptal artığı + cyclic, K10 aşamalı cümle, K11 OpenDPD ölçüm aralığında, K12 sabit tarih yok, K13 şimdilik lisans yok, K14 vekil unknown yok. L2 kapandı: OpenDPD'de APA (GaN Doherty, 3,5 GHz) ve DPA (CMOS Doherty, 2,4 GHz) ikisi de var; [ön sonda](../results/opendpd_probe.md) sıkışmanın zayıf (p99'da ≤ 0,8 dB), belleğin belirgin olduğunu gösterdi. SmartSpace sitesi bu bulut ortamında ağ politikasınca engelli (S6).
- Yeni iş paketleri İP-0…İP-7 ve iş sırası P16 §3–§4'te; yeni sürüm adları **R1-eval/1** (yalnız test: IBO süpürmesi, yükselteç uyumsuzluğu) ve **B2/1** (nihai sekiz sınıflı benchmark). A1 değişmedi.

## Uygulama eki — 2026-10-20

- **P18 (B2/1) donduruldu (K17, 2026-10-20).** Son kararlar:
  - eğitim zamanı açık-küme yöntemi prototip/merkez kaybı;
  - iptal artığı ana modelin beşinci kanalı; SCF yalnız ablasyon A4b;
  - CuC'nin CID referansı birincil kaynakla doğrulandı (ETSI TS 103 129 V1.1.2 Tablo 6: −27,5…−17,5 dB, ana taşıyıcının sembol hızına bağlı);
  - gerçek DVB-CID üreteci ve yalnız-test `cid_overlay` ailesi (meşru sinyal, beklenen karar `clean`);
  - ASI dağılımları olduğu gibi; duyarlılık kümeleri ayrı yalnız-test sürümü R2-eval/1;
  - üretim bulutta, eğitim kullanıcının GPU makinesinde.
- **DVB-CID üreteci kodlandı:** `geosim.cid`.
  - Standarda göre: çerçeve (UW, CRC-8, BCH(111,69)), karıştırma, 4× tekrar, diferansiyel kodlama, 4096 çip/bit LFSR, BPSK, RRC α = 0,35, 224/112 kHz, +220 Hz, Tablo 6 seviyesi.
  - Standart test vektörleri tutuyor: CRC-8 kontrol hanesi 0x75; ilk 32 çip 0x5091E364; BCH üreteci x¹²⁷+1'i bölüyor.
  - Dalga biçimi analitik RRC toplamından %0,5 rms sapıyor. Ölçülen PSD Tablo 6'nın +0,23 dB içinde (standart ±0,5 dB).
  - Karıştırıcının test vektörü yok [DOĞRULANACAK]. Faz gürültüsü maskesi modellenmedi.
  - 7 test geçti; tam paket **601 test geçti**.

- **R1 ve A5 pilotu koşuldu.** A1'den 120/60/30, R1'den 4 × 60 senaryo tohumu; 30 epok; tek eğitim tohumu; CPU'da ≈ 52 dk. Pilottur, iddia taşımaz: [R1 pilotu](../results/r1_pilot.md), [A5 pilotu](../results/plan_shortcut_pilot.md).
  - Dağılım içi M-nl5 %85,2.
  - Rapp %66,1: aşırı sürme → `clean`. IBO'yla tanımlı etiket yükselteçten bağımsız değil; NPR bunu açıklıyor.
  - OpenDPD %77–80.
  - Dağılım içi %5 eşiği kaymada %18–27 yanlış alarm veriyor.
  - Yük farkı IBO süpürmesinde yanlış alarmda görünüyor (M-lin %23,3, M-nl4 %1,7). Bu, B0'daki "iddia yanlış alarm üzerinden kurulur" yönünü destekliyor.
  - **A5:** model planı istenen anlamda kullanıyor (eksik taşıyıcı → `unauthorized`, yetkili sayılan intruder → `clean`). Ama 0,5 MHz bayat plan temizde yanlış alarmı %3 → %93'e çıkarıyor.
  - P18'e iki açık konu eklendi: aşırı sürme etiketi ve plan sapması artırımı. Kullanıcı yanıtladı; K17a–d olarak P18 §7a'ya yazıldı.
  - A5 çıktısına karışıklık matrisleri eklendi.

- **Uplink ASI üreteci (K5, P18 `adjacent_satellite`) kaynaklı geometriyle kodlandı:** `geosim.asi`.
  - Komşu ağ yer istasyonunun eksen dışı ışıması bizim uydunun alıcısına girer ve IMUX/TWTA/OMUX'tan geçer.
  - C/I_psd = Gmax − G(φ) − ΔEIRP (ITU BR uplink C/I yöntemi).
  - Desenler: ITU-R S.1428-1 tam desen (S.580 yan lobu) ya da S.465-6 zarfı.
  - Uydu aralığı 2,06–2,36°, FCC iki derece aralığından topo-merkezli açıya çevrildi.
  - θ₃dB = 69,3 λ/D (ITU-R F.699-6).
  - Çap, işaretleme hatası ve ΔEIRP dağılımları **[VARSAYIM]**; plan örtüşmesi %20–80 sınıf tanımıdır.
  - E1 `events.py` değişmedi; doğrulama yardımcıları yeniden kullanıldı.
  - 18 yeni test geçti; tam paket **594 test geçti**.
- **[ASI ölçümü](../results/asi_visibility.md)** (120 senaryo, A1 zinciri):
  - C/I_psd ortancası 20,3 dB (%10–%90: 14,4–26,6 dB), çapla monoton.
  - Plan içi kısım kâhin ikizle bile neredeyse görünmez (ΔPSD ortancası ≤ 0,18 dB).
  - Plan dışı kısım C/I_psd < 20 dB'de her olayda 1 dB'nin üstünde.
  - Sonuç: ASI ile `unauthorized` ayrımı plan örtüşmesinden çok seviyeden gelir (yan lob ve ana lob farkı). P18 §6'ya seviye eşleşmiş alt kutu önerisi eklendi.
- **K17 alt kararları P18'e işlendi:** CuC C/I 5–30 dB; roller 1500/150/150/500; `adjacent_satellite_downlink` yakın-OOD bilinmeyen; LOKO 3 eğitim tohumu (21 ek eğitim). P18, 2026-10-20'de donduruldu (S9 kapandı).

- **Plan maskesi kısa yolu testi (A5, P16 İP-4.4) kodlandı:** `geoml.plan_shortcut`.
  - Kademe A checkpoint'lerini kimlik denetimiyle yükler ve yalnız plan maskesini bozulmuş bir operatör planından yeniden kurar.
  - Bozmalar: plan 0,5 MHz kaymış; bir taşıyıcı plandan düşmüş; yayınlanmayan hayalet taşıyıcı; yetkisiz taşıyıcı plana "yetkili" eklenmiş.
  - Spektrumlar değişmez; yeniden eğitim ve kalibrasyon yok.
  - Gerçek veride kaydedilmiş maskeler metadata planından en çok 0,0135 dB farkla yeniden kuruluyor (float16).
  - 3 test geçti.

- **R1-eval/1 kodlandı ([P17](P17_r1_robustness_eval.md)):** A1'i değiştirmeyen, ayrı protokol adlı ve ayrı tohumlu (400000–430299) **yalnız-test** bölünmeler:
  - `r1_ibo_sweep`: nominal IBO 5–14 dB, aşırı sürme 0–5 dB;
  - `r1_amp_rapp`: Rapp SSPA, p = 2 [VARSAYIM];
  - `r1_amp_opendpd_apa` ve `r1_amp_opendpd_dpa`: OpenDPD ölçümlerinden türetilmiş bellek polinomları; yalnız ölçüm aralığında, aşırı sürme yok (K11).
- Değerlendirici `geoml.robustness` Kademe A checkpoint'lerini yeniden eğitmeden yükler. Raporladıkları:
  - IBO kutularına göre yük farkı (M-nl4 − M-lin, eşleşmiş);
  - ECE ve FPR@95TPR;
  - eşikli algılama;
  - ölçüm aralığı dışındaki giriş oranı.
- `ranking_metrics` artık `unknown_fpr_at_95_tpr` da veriyor.
- **Doğrulama:** baseline HEAD'de 544, bu dilimden sonra **569 test geçti**. A1 regresyonu: 17 A1 örneğinin spektrum, maske ve metadata anahtarları önceki kodla birebir aynı.
- **Küçük fiziksel koşu:**
  - A1 6 tohum, R1 4 × 6 tohum;
  - 3 epok eğitim ve uçtan uca değerlendirme; veri tekrar kullanımı doğrulandı.
  - Modeller 30 örnekle dejenere; yalnız çalışma kanıtıdır: [sonuçlar](../results/r1_smoke.md).
- **NPR kontrolü** ([sonuç](../results/npr_check.md)):
  - `dvbs2_nl` NPR eğimi IBO 10–14 dB'de 1,25 dB/dB; P2 §10'daki çok taşıyıcılı C/IM eğimiyle aynı.
  - Rapp p = 2'nin eğimi beşinci derece asimptotuna (4 dB/dB) doğru artıyor.
  - `dvbs2_lin` bir bozulma tabanı gösteriyor.
  - OpenDPD modelleri IBO ≤ 6 dB'de ölçüm aralığı dışına taşıyor; bu, K11'i doğruluyor.
- OpenDPD katsayıları yalnız val bölümünde seçildi:
  - APA: K = 5, M = 3; test NMSE −30,6 dB.
  - DPA: K = 5, M = 16; test NMSE −33,9 dB. Seçim ızgara kenarında, daha uzun bellek denenmedi.
- **Uyarı:** bu dilim `geosim/` kaynaklarını değiştirdi. Eski kodla başlamış yarım bir üretim yeni kodla sürdürülemez; tamamlanmış veri okunur.

- **M3 faz gürültüsü ve olay blokları kodlandı:** [P15](P15_phase_noise_and_events.md); ortak uydu/alıcı Wiener faz gürültüsü, uplink taşıyıcı-altı girişim ve alıcı tarafında komşu uydu girişimi eklendi. Uydu girişimi hedef yükün TWTA'sından geçmez. Sıfır linewidth eski sayısal çıktıları korur; A1 değiştirilmedi.
- Son birleşik doğrulama: **542 test geçti**. `E1-dev/1`, aynı planları, link ayarlarını ve faz süreçlerini paylaşan `clean` / `carrier_under_carrier` / `adjacent_satellite` geliştirme deneyidir. Veri, bağımsız pilot kalibrasyonu, kayıt kimlikleri ve ayrı model-seçimi/eşik-kalibrasyonu grupları denetlenir.
- E1 fiziksel pilotu: **54 gözlem**, iki giriş görünümü için üçer epok; doğrulanmış veri/model/eşik tekrar kullanımı tamamlandı. İki model de %33,3 doğruluk ve 0,167 macro-F1 verdi. Üç temiz örnekle eşik kurulması ve yüksek test yanlış alarmları nedeniyle sonuçlar çalışma doğrulamasıdır; tanıma avantajı göstermez. [Sonuçlar](../results/events_development.md) ve [18 eşleşmiş senaryonun fiziksel kontrolleri](../results/events_physics_check.json) kaydedildi.
- Fiziksel olay üreteçleri artık vardır; sekiz bilinen sınıfı tek çift-pol protokolünde birleştirme, çift-pol unknown reddi, tam veri/çok eğitim tohumu ve fiziksel kaynakların gözlemlerle ayırt edilebilirliği üzerindeki çalışma sürmektedir. PSD, komşu uydu kaynağını veya yetkilendirmeyi tek başına benzersiz belirlemez.
- **M3 çift-pol geliştirme dilimi kodlandı:** [P14](P14_dual_polarization.md); uplink kuplajı → iki ayrı IMUX/TWTA/OMUX yolu → downlink kuplajı → alıcı enstrüman yanıtı ve gürültüsü → bağımsız pilotlarla kalibrasyon. Fiziksel sızıntı kalibrasyonla kaldırılmaz. Ayrı planlar için dört model kanalı ve eşleşmiş co-only karşılaştırması vardır.
- M3 doğrulaması: **355 test geçti**. 36 çift-pol gözlem üretildi; iki giriş görünümü üçer epok eğitildi ve kayıt/üretim tekrar kullanımı doğrulandı. Her görünümde sınıflandırma doğruluğu %50; küçük koşu yalnız çalışma kanıtıdır. [Sonuçlar ve kalibrasyon kontrolü](../results/dual_development.md) kaydedildi.
- `D1-dev/1`, `clean`/`cross_pol` için kontrollü iki sınıflı geliştirme protokolüdür; sekiz sınıflı nihai open-set benchmark değildir. Birlikte yüklenmiş iki yolun toplam güç oranı XPD değildir; XPD doğrulaması izole kaynak testleriyle yapılır.
- **M2 geliştirme dilimi kodlandı:** [P12 unknown üreteçleri](P12_unknown_events.md), [P13 genişletilmiş deney](P13_extended_openset.md); periyodik darbeli CW, geniş bant gürültü ve aralıklı uzun burst aileleri test için üretilebilir. Mahalanobis yalnız eğitim embedding'leriyle uydurulur. AUROC/AP ve OSCR aile bazında ve birleşik raporlanır; eşikler yine ayrı bilinen kalibrasyon verisinden alınır.
- M2 doğrulaması: **226 test geçti**. Toplam 108 fiziksel simülasyon gözlemi üretildi; üç epok eğitim, yalnız 24 eğitim örneğinden Mahalanobis ve ayrı 12 bilinen örnekten eşik kalibrasyonu tamamlandı. Kayıtlı sonuç, eğitilmiş model ve üretim tekrar kullanımı doğrulandı. [Küçük koşu sonuçları](../results/openset_extended.md) zayıftır; bilimsel veya operasyonel başarı kanıtı değildir.
- Ajan görev tanımları `.agents/` ve depo geliştirme kuralları `AGENTS.md` altında sürümlendi. M0/M1 kaynak, test, kurulum ve ajan belgeleri GitHub'a `dcdc023` ile gönderildi.
- [P10 uygulama yapısı](P10_implementation_structure.md) ve [P11 geliştirme protokolü](P11_openset_development.md) eklendi.
- **M0 + ilk M1 dilimi kodlandı:** veri/çekirdek kayıtlarının kimlik ve bütünlük kontrolü, senaryo bazlı ayrım, bilinen doğrulama verisiyle MSP/energy eşikleri ve `known/unknown` tahmin/rapor hattı.
- `B1-dev/1`, mevcut beş sınıftan bir girişim ailesini dışarıda tutar; `clean` bilinen olarak kalır. Eğitim için doğrulama ve ret eşiği kalibrasyonu ayrı senaryo gruplarıdır. A1 protokolünün fiziksel örnekleme/sınıf/split tanımları değiştirilmedi.
- Altı tohum × üç kaynak split ile fiziksel üretim ve üç epok eğitim denemesi yapıldı. Küçük koşu yalnız çalışma kanıtıdır; model kalitesi zayıftır ve bilimsel sonuç değildir.
- Doğrulama: tam test paketi **141 test geçti**; son kaynak-rolü kontrolü sonrası yedi deney testi tekrar geçti. Veri ve checkpoint tekrar kullanımı da gerçek koşuda doğrulandı.
- Sekiz sınıflı nihai B benchmark'ı henüz uygulanmadı. Unknown üreteçleri, Mahalanobis, AUROC/OSCR, çift-pol geliştirme hattı, faz gürültüsü ve modüle girişim blokları vardır; tam bilimsel değerlendirme yapılmadı. Aşağıdaki eski faz/eksik tabloları temel Kademe A durumunu tarif eder; güncel uygulama durumu bu ektedir.

## Araştırma eki — 2026-10-20

- **P1 literatür / yakın çalışmalar:** ilk kaynak-tabanlı denetim eklendi: [P1_literatur.md](P1_literatur.md). “GEO'da ilk DL” ve “önceki çalışmaların hepsi idealize” iddiaları **geçersiz**; doğrulanmış yenilik yerine test edilebilir aday katkı önerildi. Kapsamlı sistematik tarama veya bütün yakın makalelerin tam metin analizi henüz yapılmadı.
- **P8 dış kaynak:** veri temsilleri, SmartSpace araştırma amaçlı kullanım koşulu, GaN PA vs TWTA ve GNSS kayıtlarının görev farkı belgelendi: [P8_dis_veri.md](P8_dis_veri.md). Ham veri indirilip deney yapılmadı.
- **P9 ve B açık-küme protokolü:** [P9_yol_haritasi.md](P9_yol_haritasi.md) ve [open_set_protocol.md](../research/open_set_protocol.md) yayımlandı. Tam B benchmark'ı tasarım aşamasındadır; kodlanan/test edilen geliştirme dilimleri yukarıda ayrı sürümleriyle listelenir.
- **Kaynakça ve birincil kaynak yolları:** [references.bib](../../references/references.bib) ve [ORIGINALS.md](../../sources/ORIGINALS.md); özgün DOCX'in [Markdown transkripsiyonu](../../sources/original_proposal.md).
- **S1–S4, B0/B1b/B2/B3/B4/B7 ve tam benchmark** bu araştırma commit'leriyle kapanmadı. Eski pilot rakamları değişmedi.

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
| P1 | Literatür ve yenilik | Tarama v2 eklendi; **tam metin okuması yok, kapanmadı** | `P1_literatur.md` §7 |
| P8 | Dış veri denetimi | Kaynak sayfaları denetlendi; veri indirilmedi; L1/L2 açık | `P8_dis_veri.md` |
| P9 | Yol haritası, hedef yayın | Öneri; takvim P16 §4'te, onaysız (K12) | `P9_yol_haritasi.md` |
| P15 | Faz gürültüsü ve olaylar (E1-dev/1) | Geliştirme dilimi | `P15_phase_noise_and_events.md` |
| P16 | Literatür sonrası düzeltme programı | Plan; İP-0…İP-7 | `P16_literatur_duzeltme_programi.md` |
| P17 | R1-eval/1 sağlamlık değerlendirmesi | Kodlandı, küçük koşu; tam sonuç yok | `P17_r1_robustness_eval.md` |
| P18 | B2/1 sekiz sınıflı çift-pol açık-küme protokolü | **Donduruldu 2026-10-20 (K17)**; bilinen fiziksel aşama P19'da; nihai model ve yalnız-test aileleri bekliyor | `P18_b2_protocol.md` |
| P19 | B2 bilinen fiziksel gözlemleri | `B2-base/1` üretici, aktif yayın ayrımı, bağımsız kalibrasyon ve veri bütünlüğü | `P19_b2_base_observations.md` |
| P20 | B2 iptal artığı ve beş kanallı model | `B2-feat/1` üretici, `geosim.cancellation`, iki çıktılı model, `geoml.b2_experiment`; pilot fizik kanıtı var, tanıma sonucu yok | `P20_b2_cancellation_residual.md` |
| P21 | B2 yalnız-test aileleri, K17b, açık-küme değerlendirmesi | `B2-test/1` üretici, downlink ASI ve aktif-farkında CID, plan kaydırma artırımı, aile başına açık-küme metrikleri; pilot yürütme kanıtı | `P21_b2_test_families.md` |
| Kademe B | Çift pol, 8 sınıf, open-set | Geliştirme dilimleri var (B1-dev/1–2, D1-dev/1, E1-dev/1); nihai B2/1 benchmark yok | `P11`–`P14` |

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
| S5 | ~~P16 kararları~~ — **2026-10-20 yanıtlandı** (P16 §5): uplink-ASI, iptal artığı + cyclic, aşamalı yenilik cümlesi, OpenDPD ölçüm aralığında, sabit tarih yok, lisans şimdilik yok, vekil unknown yok | — |
| S9 | ~~K17: P18 dondurma~~ — **2026-10-20 donduruldu** | — |
| S8 | R1-eval/1 tam koşu (S2'den sonra) | `python -m geosim.dataset --protocol R1-eval/1 --out data/r1 --workers 4` (≈ 2,6 çekirdek-saat, ayrı dizin) ve `python -m geoml.robustness --data data/stageA --runs runs/stageA --r1 data/r1 --out runs/r1`; `runs/r1/results.md` dosyasını gönderin |
| S6 | SmartSpace verisi bulutta işlenecek | Ortam ayarlarında **Network access → Allowed domains**'e `fnr-smartspace-project.uni.lu` ekleyin (paket yöneticileri kutusu işaretli kalsın) ve araştırma-amaçlı, ticari olmayan kullanım koşulunu kabul ettiğinizi yazın |

### 5.3 Açık — bende, sıradaki işler

| # | Eksik | Önem | Not |
|---|---|---|---|
| B0 | **Ana iddianın biçimi.** Pilotta yük farkı doğrulukta görünmedi | Yüksek | Tam veriyle teyit; gerekirse iddia yanlış alarm ve yanlış etiketleme üzerinden kurulur veya daha düşük geri çekilme eklenir (protokol değişikliği, günlüğe yazılır). R1 pilotu bu yönü destekliyor: IBO süpürmesinde temizde yanlış alarm M-lin %23,3, M-nl4 %1,7 ([r1_pilot](../results/r1_pilot.md)) |
| B1 | **Literatür ve yenilik denetimi (P1)** başlandı, bitmedi | Yüksek | Aday çalışmalar listelendi (SnT ICASSP 2023, Henarejos ve ark. 2019, GNSS ve radar open-set çalışmaları); hiçbiri okunup karşılaştırılmadı |
| B1b | Model dar bantlı girişimde (CW) zayıf | Orta | Tam veriyle yeniden bakılacak; gerekirse zaman ortalamalı spektrum ek kanal olarak verilir |
| B2 | Sonuç şekilleri (ROC, C/I eğrileri, karışıklık matrisi) | Orta | Tam sonuç gelince |
| B3 | Mutlak seviye ablasyonu | Orta | `--level absolute`; tam veriyle |
| B4 | Parametre aralıklarının hiçbiri kaynaklı değil (C/N, C/I, taşıyıcı sayısı) | Orta | B1 ile birlikte literatürden dayanak aranacak |
| B5 | Dış veri denetiminin kalanı: RF WebLab, DARCY dosya biçimi, Jammertest 2025 lisansı | Düşük (Kademe B) | OpenDPD teknolojisi kapandı (APA GaN Doherty, DPA CMOS Doherty); Highway 2 = CC BY-NC-SA 4.0, LC-lab = CC BY-SA 4.0 (Zenodo) |
| B6 | Proje talimat belgesi hâlâ ilk hâlinde (zincir tarifi, veri kaynağı rolleri hatalı; "Roadmap, risks and venues" boş) | Orta | P9 ile birlikte düzeltilmiş metin önerilecek |
| B7 | Gerçek sinyalle akıl sağlığı denetimi (Zenodo'daki Intelsat 37e kaydı) | Düşük | |
| B8 | Proje skill'leri eski (faz sırası, Saleh'in birincil model olduğu varsayımı) | Düşük | Güncelleme önerisi sunuldu |
| B9 | P16 İP-0: L1 Jammertest lisansı; L10 uydu anteni XPD'si; isteğe bağlı sistematik tarama (CNKI/IEEE) | Düşük | En yakın 7 GEO/uydu çalışması ve bir açık-küme karşılaştırması tam metin okundu ([P1 §8](P1_literatur.md)): hiçbir uydu çalışması transponder zinciri, plan, çift-pol veya bilinmeyen sınıf reddi içermiyor; L2, L7 (a–c) kapandı |
| B10 | P16 İP-1: C3'ün IBO eğrisi, ECE, FPR@95TPR | Yüksek | **Kodlandı (P17)**; tam üretim ve değerlendirme sizde (S8) |
| B11 | P16 İP-2: sentetik bellek polinomu, OpenDPD eşleme duyarlılığı (R1-eval/2), NPR'nin literatürle sayısal karşılaştırması | Yüksek | Rapp ve OpenDPD bellek polinomları (P17) ve [NPR kontrolü](../results/npr_check.md) yapıldı |
| B12 | P16 İP-3/4: B2 gözlemleri, iptal artığı, PL çerçeve/SCF ve plan bozma | Yüksek | Sekiz bilinen sınıf P19'da, gözlemden iptal artığı P20'de bağlandı; kalan: PL çerçeve/SCF ve B2 plan-bozma değerlendirmesi |
| B13 | P16 İP-5/6: B2/1 nihai test üretimi, eğitim-zamanı OSR, EDSC ve XGBoost | Orta | Beş kanallı/iki çıktılı model ve merkez kaybı P20'de; unknown/CID aileleri ve açık-küme değerlendirmesi P21'de var; seviye eşleşmiş test kümesi (K17c), EDSC ve XGBoost henüz yok |
| B14 | K18: merkez kaybı 0,005 ve plan BCE 1,0 ön kaydının onayı | Orta | Araştırmacı kararı; onaylanmazsa P18 §10 ile değiştirilir |

### 5.4 Bilinçli olarak ertelenenler (Kademe B)

- DVB-S2 PL çerçevesi anahtarı (P0'da "ikinci adım" olarak sözü verilmişti; Kademe A iddialarının hiçbiri gerektirmiyor, cyclic dalıyla birlikte yapılacak)
- Çift polarizasyon, cross-pol, komşu uydu, carrier-under-carrier sınıfları
- Open-set reddi ve bilinmeyen sınıflar
- Faz gürültüsü, ALC, komşu transponderler
- Uzman özellikli baseline, transformer, hiperparametre araması
- Görülmemiş süzgeç kümesi (26/33 MHz tabloları), IBO 5–8 dB bölgesi

### 5.5 Çözülemeyecek sınırlar

- **Gerçek veri yok.** Çalışma bir simülasyon çalışmasıdır; yük farkı iki simülatör arasındaki farktır. Ölçüm imkânı olmadığı için bu, makalede açıkça yazılacak bir sınırdır.
- **Doğrusallaştırılmış TWTA eğrisi seyrek** (dB başına bir nokta, basamaklı faz); bu modeldeki ayrıntılara güvenilmemeli. NPR kontrolü bunu nicelleştirdi: `dvbs2_lin`'in NPR'si IBO 12 dB'de ≈ 23,8 dB ile tepe yapıp geri çekilme arttıkça düşüyor, yani yapay bir bozulma tabanı var ([NPR kontrolü](../results/npr_check.md)); `test_amp_lin` yorumlanırken dikkate alınmalı.
- **ETSI ham dosyaları depoda değil**; yeniden üretmek isteyen kendisi indirmeli.

## 6. Önerilen sıra

1. Siz: S3 → S1 → S2 (veri ve tam koşu); S5 kararları.
2. Ben, aynı anda: B9 (tam metin + açık L-maddeleri), B10 (metrikler, R1-eval/1 kodu), B4.
3. Sonuç gelince: B0, B2, B3, B11 ve ders raporu taslağı.
4. Ardından B12–B13 (Kademe B); haftalık sıra P16 §4.
