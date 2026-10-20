# P16 — Literatür taraması sonrası düzeltme ve tamamlama programı

Durum: **PLAN — UYGULANMADI** · 2026-10-20 · Girdi: kullanıcının verdiği ([depo kopyası](../research/literature_review_2026-10-20.md))
*"Payload-Aware Open-Set Interference Recognition for GEO Transponders: Literature
Review"* (PDF 20 sayfa + aynı içerikte Markdown, 2026-10-20; bundan sonra
**"tarama"**), `DURUM.md`, `00_ana_plan.md`, `P1`, `P3`, `P5`–`P9`, `P11`–`P14`,
`docs/research/open_set_protocol.md`, `references/references.bib`, `src/`.

Bu belge üç soruya yanıt verir: (1) tarama projede neyi değiştiriyor, (2) tarama
ile depo arasında hangi çelişkiler var ve nasıl düzeltilecek, (3) çalışmayı
tamamlamak için hangi işler hangi sırayla yapılacak. Burada yeni deney sonucu
**yoktur**; bütün sayılar taramadan, depodaki ölçümlerden alınmıştır ya da
**[VARSAYIM]** / **[DOĞRULANACAK]** olarak etiketlidir.

**Kapanış kriteri:** §2'deki her düzeltme ya kapatılmış ya da sahibi ve
doğrulama yolu yazılı; §3'teki her iş paketinin kapanış ölçütü, sahibi ve
bağımlılığı belli; §5'teki kararlar kullanıcıya sunulmuş.

---

## 0. Hüküm: tarama ne söylüyor, bize ne yapmamızı söylüyor

| Tarama bulgusu | Projeye etkisi | Kanıt seviyesi |
|---|---|---|
| 2018–2026 arasında transponder zincirini (TWTA/IMUX/OMUX/çok taşıyıcılı IM), çift polarizasyonu, taşıyıcı planını veya open-set reddini modelleyen GEO girişim tanıma makalesi bulunamadı | Boşluk iddiası **ayakta**, ama "ilk" yerine "**birlikte modelleyen ilk**" ifadesi kullanılmalı | Sistematik olmayan tarama; CNKI ve IEEE tam metinleri kısmen bakıldı (taramanın kendi uyarısı) |
| En yakın işler: SnT (Daoud 2023; Saifaldawla 2023/2024), Fudan Agon (arXiv 2026), CTTC/Eutelsat (Henarejos 2019, Vázquez 2019/2021), KTH (Pellaco 2019), Politis 2016/2017 | P1 yakın-çalışma tablosu bu listeye genişletilmeli; Agon "en güçlü yeni rakip" | Özet/OA PDF; Agon hakemsiz ön baskı |
| Open-set yalnızca genel karıştırma (jamming), radar ve GNSS'de yayımlanmış | C2'nin open-set ekseni en net boş eksen | Özet düzeyi |
| Carrier-under-carrier PSD'de görünmez; ticari araçlar taşıyıcı **iptali** ile bulur | Spektrogram-tek model için CuC'de şans düzeyi beklenmeli → bu bir **ayırt edilebilirlik sonucudur**, hata değil | Satıcı sayfaları + ticari basın; bağımsız ölçüm değil |
| Plan maskesi "unauthorized" sınıfını kısa yoldan ele verebilir | Plan bozma (bayat/kaydırılmış plan) testi zorunlu | Metodolojik uyarı |
| Değerlendirme: OSCR, FPR@95TPR, unknown başına AUROC, ECE, sabit Pfa'da Pd (C/I ve IBO'ya göre), gecikme | Mevcut metrik setine FPR@95TPR, ECE, gecikme ve "yakın/uzak OOD" ayrımı eklenmeli | Standart yöntem kaynakları |
| Gerçeklik: yükselteç uyumsuzluğu testi (eğitim tablo-TWTA, test Rapp / bellek polinomu / OpenDPD'den öğrenilmiş model), NPR literatürü | C3'ün "sim-to-sim" eleştirisine karşı ana savunma | Yöntem önerisi; OpenDPD GaN PA'dır, TWTA değildir |
| C3 tek sayı değil, **eğitimden IBO uzaklığının fonksiyonu** olarak raporlanmalı | P7 İ1–İ4 raporlarına IBO-eğrisi eklenir | Öneri |

**Özet karar:** Projenin yönü değişmiyor. Değişen üç şey var: (a) yenilik
ifadesi daraltılır, (b) CuC ve ASI/unauthorized çiftleri "ayırt edilemezlik"
bulgusu olarak tasarıma girer, (c) gerçekçilik çapası "ölçülmüş PA" tek
ayağından "yükselteç ailesi uyumsuzluğu + NPR kontrolü + ölçülmüş PA" üç
ayağına çıkar.

---

## 1. Taramadaki iddiaların kullanım durumu

Taramadaki her iddia makaleye aynı güvenle girmez.

| Sınıf | Örnekler | Kural |
|---|---|---|
| **Doğrudan kullanılabilir (birincil kaynak açık erişimli, künye tutarlı)** | Saifaldawla TMLCN 2024 (DOI 10.1109/TMLCN.2024.3418933); Henarejos 2019 (arXiv 1906.03012); OSR temel makaleleri (MSP, ODIN, energy, Mahalanobis, OSCR, Vaze 2022, ARPL); OpenDPD ISCAS 2024 | Tam metin okunduktan sonra sayfa/tablo numarasıyla alıntılanır (P1 §6) |
| **Ön baskı** | Agon arXiv 2606.14147; 2026 tarihli arXiv GNSS işleri (2607.03411, 2607.28404) | "preprint" diye etiketlenir; sürüm numarası kaydedilir |
| **Taramada "(verify)" işaretli künyeler** | Saleh 1981 DOI, Morello & Mignone DOI, Gardner 1991 DOI, Mehr & Dovis DOI, van der Merwe DOI, Ott ICL-GNSS 2024 erişimi | **[DOĞRULANACAK]**: yayıncı sayfasından BibTeX alınmadan `references.bib`'e kesin künye olarak girmez |
| **Ticari basın / satıcı iddiası** | SUIRG %34 "unknown", Intelsat %33 cross-pol ve %47 unauthorized, IRG VSAT %40, SIRG %93 anketi, Integrasys "200 taşıyıcı/s", Kratos İran kaynaklı karıştırma (2026) | Yalnızca **motivasyon** cümlesinde, "sektör kaynaklarına göre" kalıbıyla; hiçbir deney tasarım parametresi bunlardan türetilmez |
| **Standart içeriğine dair iddia** | TR 102 376-2'nin altı taşıyıcılı/tek TWTA senaryosu içerdiği ve çapraz-pol/eş-kanal katkısını ihmal ettiği; CID metacarrier'ın taşıyıcı spektral yoğunluğuna göre −27,5 dB olduğu | **[DOĞRULANACAK]**: madde/şekil numarasıyla birincil kaynaktan (ETSI PDF, ITU-R S.2062, ETSI CID standardı) teyit; Via Satellite ikincil kaynaktır |

---

## 2. Tarama ↔ depo çelişkileri ve düzeltmeler

| # | Yer | Sorun | Düzeltme | Sahip | Durum |
|---|---|---|---|---|---|
| L1 | `P8` DARCY/Highway 2 | Tarama Highway 2, LC-lab ve Jammertest 2025'i **CC BY-SA 4.0** diyor; P8 Highway 2'yi **CC BY-NC-SA 4.0** olarak kaydetmiş | **2026-10-20 Zenodo kayıtlarından okundu:** Highway 2 (10.5281/zenodo.21336653) = **CC BY-NC-SA 4.0** (tarama yanlış); LC Laboratory (zenodo 21333335) = **CC BY-SA 4.0**; Jammertest 2025 (zenodo 21332689) lisansı okunan sayfa metninde görünmedi **[DOĞRULANACAK]** | ben | Highway 2 ve LC kapandı; Jammertest açık |
| L2 | `00_ana_plan` §0, `P8` OpenDPD | Tarama `DPA_200MHz`, ana plan `APA_200MHz` diyor | **İkisi de var** (OpenDPD commit `cb4c5ea`): DPA_160/200MHz = 40 nm CMOS dijital Doherty verici, 2,4 GHz; APA_200MHz(_b) = Ampleon GaN Doherty PA, 3,5 GHz, 41,5 dBm. [Sonda](../results/opendpd_probe.md) | ben | **kapatıldı** |
| L3 | Tarama "WBSig53 pre-trained detector" baseline | P8: güncel TorchSig'de hazır WidebandSig53 seti yok; artık üretici | WBSig53 baseline'ı **koşullu**: TorchSig sürümüyle üretilip ön eğitilirse yapılır; aksi halde düşer. Önceliği en alt (§3 İP-6) | ben | düzeltme bu belgede |
| L4 | Tarama "Validate realism against OpenDPD and the SnT data" | SnT verisinde yük etkisi yok; yük gerçekçiliğini doğrulayamaz. OpenDPD TWTA değildir | Doğru ifade: SnT = **görev/format karşılaştırılabilirliği** (V6 kipi); OpenDPD = **ölçülmüş, bellekli PA'ya aktarım**. "Gerçekçilik doğrulaması" ifadesi kullanılmaz | ben | düzeltme bu belgede |
| L5 | Tarama §9 ipucu 1: IM3 "yaklaşık 3:1 dB eğim" | 3:1 küçük-sinyal kuralıdır (C/IM'de 2 dB/dB). Bizim çalışma aralığında ölçülen C/IM eğimi **1,25 dB/dB** (`DURUM` §4, `P2` §10) | Ayırt edilebilirlik ipucu kendi ölçtüğümüz eğriyle yazılır; 3:1 kuralı yalnız küçük-sinyal sınırı olarak anılır | ben | düzeltme bu belgede |
| L6 | Tarama "Gap Matrix" son satırı (bütün sütunlar ✔) | Depo gerçeği: TWTA/IMUX/OMUX/çok taşıyıcılı IM ✔; plan maskesi ✔; çift-pol yalnız iki sınıflı geliştirme (D1-dev/1); open-set yalnız geliştirme (B1-dev/1–2); 8 sınıf, faz gürültüsü, PL çerçeve **yok** | Makalede ve P1'de **planlanan** ve **uygulanan** ayrı sütun olarak gösterilir (P1 §7) | ben | P1'de kapatıldı |
| L7 | `references.bib` | (a) Daoud 2023 başlığı farklı; (b) `etsi2021dvbs2guide` başlığı yanlış; (c) Heublein iki ayrı iş; (d) en yakın işler eksik | (a) **kapandı:** yayımlanmış başlık "CNN-Based on-Board Interference Detection in Satellite Systems: An Analysis of Dataset Impact on Performance", **ICASSP Workshops** 2023, doi:10.1109/ICASSPW59220.2023.10193395; SmartSpace sayfası eski başlığı veriyor. (b) **kapandı:** ETSI PDF başlığı "… Part 2: S2 Extensions (DVB-S2X)", V1.2.1 (2021-01). (c) **kapandı:** iki girdi; 2503.23775 = ION GNSS+ 2024, pp. 1260–1293, doi:10.33012/2024.19887 (Zenodo kaydındaki atıf). (d) eklendi, `verify` notlu olanlar açık | ben | (a)–(c) kapandı |
| L8 | `P1` §2 | Agon, Pellaco, Vázquez, Politis ve open-set karıştırma işleri yok (ikinci Henarejos satırı bilerek bırakılmış tam metin kontrol satırıdır); ana plan P1 kapanış kriteri "her boşluk iddiası ≥ 2 kaynak" karşılanmamış | P1'e §7 (tarama v2) eklendi; tam metin okuması İP-0'da | ben | kısmen kapatıldı |
| L9 | `DURUM` §2 faz tablosu | P1/P9/Kademe B "Başlanmadı" yazıyor; araştırma ve uygulama ekleriyle çelişiyor | Tablo güncellendi | ben | kapatıldı |
| L10 | `P14` XPD değerleri (uplink 30/10 dB, downlink 35 dB, enstrüman 25 dB) | Kaynaksız geliştirme seçimi | **Kısmen kapandı (yer istasyonu standartları):** Eutelsat EESS 502 doğrusal polarizasyonda referans çapraz-pol ayrımı **35 dB**, koşullu en düşük **25 dB**; Intelsat IESS-207 (Rev. 4) doğrusal Standard A/B/F-3 için **≥ 30,0 dB**, yağmurda izolasyon yılın %0,01'inde **12 dB**'nin altına iniyorsa kompanzasyon öneriyor. Nominal 30 / 35 dB bu aralıkta; `cross_pol` sınıfının 10 dB'si izinli en düşük değerin ve yağmur eşiğinin altında bir **arıza** senaryosudur. Açık: uydu anteni XPD'si ve sınıf içi dağılım **[VARSAYIM]** | ben | kısmen kapandı |
| L11 | `open_set_protocol.md` §1 CuC satırı | "döngüsel istatistik faydalı olabilir" — tarama "PSD ile beklenemez, iptal artığı veya cyclic gerekli" diyor | Satır "PSD-tek gözlemde düşük C/I'de **tanımlanamaz beklenir**; iptal artığı veya cyclic özellik gerekli" olarak güncellenir; karar K9 | ben | kapatıldı |
| L12 | `P12` unknown aileleri | Tarama: `wideband_noise` ≈ overdrive spektral yeniden büyümesi, `pulsed` ≈ `intermittent_bursts` → yakın-OOD | U1-dev/1 üreteci değişmez; raporlarda aileler **yakın/uzak OOD** diye önceden gruplanır (gruplama test sonucundan önce dondurulur) | ben | **açık** (İP-5) |
| L13 | `P9` §3 yayın yerleri | Üç dergi var; tarama TCCN, OJ-COMS, ICASSP/SPAWC, ICC/GLOBECOM çalıştayları, ASMS/SPSC, ICSSC, IEEE Aerospace/MILCOM ekliyor | P9'a eklendi; uygunluk yine başvuru anında kontrol edilir | ben | kapatıldı |
| L14 | `src/geosim/payload.py` Saleh katsayıları | Kod yorumu "makaleye karşı kontrol edilmedi"; tarama da DOI'yi "(verify)" diyor | Açık kalır (B-kaynak); Saleh zaten birincil değil, alternatif model | ben | açık, düşük |
| L15 | Motivasyon istatistikleri | Taramadaki yüzdeler basın/satıcı kaynaklı | §1 kuralı; makale girişinde tek paragraf, açık niteleme | ben | kural yazıldı |
| L16 | `P15_phase_noise_and_events.md` (E1-dev/1, main'e 2026-10-20'de eklendi) | E1-dev/1 `adjacent_satellite`'ı **alıcı tarafında (downlink) olay** olarak kodluyor; hedef yükün TWTA'sını atlıyor. K5 kararı ise **uplink-ASI** (downlink kullanıcı tarafından veto edildi) | E1-dev/1 kodu ve sonuçları **değiştirilmedi**. B2/1'de `adjacent_satellite` = uplink-ASI; E1'deki downlink olayı ya `adjacent_satellite_downlink` diye ayrı bir geliştirme olayı olarak kalır ya da kaldırılır — **K16 kararı: ayrı adla tutulur** | ben | karar alındı; kod yeniden adlandırması İP-3'te |
| L17 | Belge numarası | Bu belge önce P15 olarak yayımlandı; aynı gün main'e ayrı bir P15 (faz gürültüsü ve olaylar) girdi | Bu belge **P16** oldu; R1-eval/1 **P17** ([belge](P17_r1_robustness_eval.md)); B2/1 protokol belgesi **P18** | ben | kapatıldı |

---

## 3. Tamamlama programı — iş paketleri

Her iş paketi (İP) bir katkıya bağlıdır. **A1 donmuş protokolü değişmez**; yeni
test kümeleri ayrı sürüm adlarıyla ve ayrı tohum aralıklarıyla üretilir
(AGENTS.md kuralı). Önerilen yeni sürümler:

- **R1-eval/1** — yalnızca test: IBO süpürmesi ve yükselteç uyumsuzluğu kümeleri, tohumlar 400000– **[VARSAYIM]** (A1: 100000–340000+, unknown: 900000–, çift-pol: 1000000– ile çakışmaz; kodda çakışma testi zorunlu).
- **B2/1** — nihai sekiz bilinen sınıflı çift-pol open-set benchmark protokolü; ayrı belge (`P18`), kod yazılmadan önce dondurulur.

### İP-0 — Belge ve kaynak düzeltmeleri (C1–C3 savunması) · öncelik: hemen

| İş | Kapanış ölçütü |
|---|---|
| §2'deki açık L-maddeleri (L1, L2, L7a/b, L10) | Her biri birincil kaynakla kapatılmış veya **[DOĞRULANACAK]** olarak sahibiyle kayıtlı |
| En yakın 6 çalışmanın tam metin okuması: Saifaldawla TMLCN 2024, Agon 2026, Daoud 2023, Henarejos 2019, Vázquez 2021, Politis 2017 | Her biri için: gözlem noktası, sinyal kaynağı, doğrusalsızlık, plan bilgisi, polarizasyon, unknown testi, metrik, veri — sayfa/tablo numarasıyla P1 §7 tablosunda |
| Yenilik cümlesinin dondurulması (K10) | README, P0, P1 ve makale özetinde aynı cümle |

### İP-1 — Kademe A'yı bitir (C3 ana bulgu) · öncelik: kritik yol

Mevcut S1–S4 ve B0–B3 işleri **aynen geçerli**; tarama bunları değiştirmiyor, yalnızca raporu genişletiyor.

| İş | Sahip | Kapanış ölçütü |
|---|---|---|
| S3 → S1 → S2 tam veri ve tam koşu (`DURUM` §5.2'deki komutlar) | **siz** | `runs/stageA/results.md` + `results.json` gönderildi |
| Metrik eklemeleri: FPR@95TPR (pozitif sınıf ve payda açıkça), ECE (kapalı küme, 15 kutu **[VARSAYIM]**), CPU ms/çerçeve, parametre sayısı | ben | Birim testleri; `null` + sayım kuralı (katı JSON); mevcut 355 test bozulmadan |
| C3'ü IBO uzaklığına göre raporla: `test_id_nl`, `test_ibo` + R1-eval/1 IBO süpürmesi (0–14 dB, 1 dB adım; 5–8 dB "belirsiz bölge" ayrı) | ben (kod) / siz (tam üretim) | Doğruluk, makro-F1, temizde yanlış alarm ve İ3 payları IBO'ya karşı, senaryo-bootstrap %95 aralıklı |
| B0: ana iddianın biçimi — tam veriyle, nominal IBO'da fark yoksa iddia yanlış alarm/yanlış etiket ve IBO eğrisi üzerinden kurulur | ben | Karar `P7` değişiklik notunda, sonuçlar görülmeden önce yazılmış ölçütle |
| B2 şekiller, B3 mutlak seviye ablasyonu | ben | Şekiller `docs/figures/`, özet `docs/results/` |

### İP-2 — Gerçekçilik çapası (C1, C3) · öncelik: yüksek

| İş | Kapanış ölçütü |
|---|---|
| Yükselteç ailesi uyumsuzluğu: `rapp` (SSPA, p parametreli) ve `memory_poly` (bellekli) amplifikatörleri `geosim.payload`'a **ek seçenek** olarak; R1-eval/1'de `test_amp_rapp`, `test_amp_mp` | Her model için AM/AM–AM/PM birim testleri; doyum/IBO tanımı mevcut `drive_gain` ile tutarlı; A1 çıktısı bit-düzeyinde değişmemiş (regresyon testi) |
| OpenDPD'den öğrenilmiş PA modeli → `test_amp_opendpd` (L2 sonrası). Ham veri depoya girmez, yalnız türetilmiş katsayılar + betik + `metadata.json` (P8 §Doğrulama alanları) | Kaynak hash'i yerelde hesaplanmış; model hatası (NMSE) raporlanmış; "TWTA doğrulaması" ifadesi yok |
| NPR kontrolü: DVB-S2 tablo-TWTA'da gürültü yüklemeli NPR – IBO eğrisi; literatürdeki TWTA NPR aralığıyla nitel karşılaştırma (tarama kaynak 49) | Eğri + karşılaştırma tablosu; kaynak değerleri **[DOĞRULANACAK]** okunmadan sayı yazılmaz |
| Alan rastgeleleştirme (domain randomization) eğitimi: TWTA ailesi, IMUX/OMUX derecesi, (çift-pol'de) XPD dağılımı — **yalnız B2/1 sürümünde**, ayrı model | A1 modelleriyle aynı test kümelerinde karşılaştırma; ayrı eğitim bütçesi eşit |
| B7: Intelsat 37e SigMF kaydıyla "clean" akıl sağlığı kontrolü (P8 beklemede) | İçerik/izin doğrulandıktan sonra PSD şekli karşılaştırması; nicel iddia yok |

**Uygulama durumu (2026-10-20):** İP-1'in metrik ve IBO eğrisi kısmı ile İP-2'nin Rapp ve OpenDPD bellek polinomu kısmı [P17](P17_r1_robustness_eval.md) (R1-eval/1) olarak kodlandı ve test edildi; tam koşu kullanıcıda. [NPR kontrolü](../results/npr_check.md) yapıldı; literatürle sayısal karşılaştırması, sentetik bellek polinomu ve OpenDPD eşleme duyarlılığı açık.

### İP-3 — Bilinen sınıfları sekize tamamla (C1, C2) · öncelik: yüksek

| Sınıf / blok | Giriş noktası | Tasarım notu | Kapanış ölçütü |
|---|---|---|---|
| `cross_pol` | uplink XPD bozulması | D1-dev/1'de var; XPD dağılımı kaynaklandırılacak (L10) | İzole kaynak XPD testi (mevcut) + kaynaklı dağılım |
| `adjacent_satellite` | **uplink** (K5 kararı) | Komşu sistemin yer istasyonu yan lobu; planlı taşıyıcıyla kısmen örtüşen, farklı sembol hızı/ofsetli modüleli taşıyıcı. Yetkisiz taşıyıcıyla "tasarım gereği karışabilir çift". E1-dev/1'deki mevcut uygulama downlink'tir (L16) | Giriş noktası testi: IMUX/TWTA/OMUX'tan geçtiği; örtüşme oranı üst veride. **Kodlandı:** `geosim.asi` (ITU-R S.1428-1/S.465-6 desenleri, FCC iki derece aralığı; [ölçüm](../results/asi_visibility.md)) |
| `carrier_under_carrier` | uplink, planlı taşıyıcının üstüne | **E1-dev/1'de üreteç var** (kurban taşıyıcının bandı içinde, C/I 5–15 dB keşif aralığı). B2/1 için C/I süpürmesi genişletilir; CID metacarrier seviyesi (−27,5 dB, **[DOĞRULANACAK]**) bir referans nokta | Spektrumda görünürlük ölçümü (P6 §6'daki CW tepe tablosu gibi) C/I'ye karşı |
| `overdrive_im` | yük içi | A1 `overdrive` ile aynı tanım | — |
| Faz gürültüsü | LO | **E1-dev/1'de var:** ortak uydu/alıcı Wiener süreci, Lorentz linewidth (100/50 Hz keşif değerleri). Kalan: DVB-S2 faz gürültüsü maskesiyle (EN 302 307-1 Annex H) karşılaştırma veya maske-tabanlı üreteç | Ölçülen PSD maskeye tolerans içinde |
| PL çerçeve anahtarı | taşıyıcı üretici | P0'da söz verilen SOF+PLS+pilot+karıştırma; cyclic/iptal için ön koşul | Sembol sayıları EN 302 307-1'e karşı test; "tam DVB-S2 çerçeveleme" iddiası yalnız bu testlerden sonra |

### İP-4 — Ayırt edilebilirlik analizi (C2'nin özgün kısmı) · öncelik: yüksek

1. **Sınıf × gözlemlenebilir tablosu** (co-pol PSD, cross-pol PSD, plan, IBO tepkisi, cyclic/iptal artığı) — `open_set_protocol.md` §1 tablosu genişletilir; her hücre bir ablasyonla desteklenir (A0–A8).
2. **Dört fiziksel ipucu** (taramanın §9'u, L5 düzeltmesiyle): (i) IM ↔ dış taşıyıcı: plan + IBO süpürmesi; (ii) cross-pol ↔ eş-pol plansız taşıyıcı: karşı polarizasyon kanalı; (iii) CuC: cyclic veya iptal artığı; (iv) ASI ↔ unauthorized: gözlenebilirlerin dışında (plan/geolokasyon/CID) → **karışabilir çift olarak raporla**.
3. **CuC için gözlem kanalı (K9):** iptal artığı **yalnız gözlemden** hesaplanmalı (planın sembol hızı + karar-yönlü yeniden modülasyon). Simülatörün bildiği taşıyıcı dalga biçimiyle "kâhin iptal" (oracle) yalnız **üst sınır** olarak, açıkça etiketli raporlanır; model girdisi olamaz (AGENTS.md: model girdisi simülatör gerçeğinden ayrı).
4. **Plan kısa yolu testi:** bayat plan, ±kaydırılmış taşıyıcı, eksik/fazla taşıyıcı; maske var ama taşıyıcılar taşınmış ablasyonu. Unauthorized başarımı maskeden okunuyorsa bu görünür olmalı.
5. **FiLM koşullaması** (Perez ve ark. 2018) maske kanalına alternatif; eşit parametre/eğitim bütçesiyle tek ablasyon.

Kapanış ölçütü: her ayırt edilemeyen çift için "hangi gözlem eklenince ayrılıyor" sorusuna ölçülmüş yanıt veya açık sınır cümlesi.

### İP-5 — Kademe B open-set benchmark (C2) · öncelik: orta-yüksek

| İş | Kapanış ölçütü |
|---|---|
| [`P18`](P18_b2_protocol.md) B2/1 protokolü (**taslak yazıldı, onay bekliyor**): 8 bilinen sınıf, 3 unknown ailesi + leave-one-known-out rotasyonu, yakın/uzak OOD gruplaması (L12), kalibrasyon grupları ağırlık seçiminden ayrı | Kod yazılmadan dondurulmuş; P5 kuralı gibi değişiklik günlüğü |
| Eğitim-zamanı open-set yöntemi (ana plan D13): ARPL veya prototip/merkez kaybı; OpenMax ikincil; ODIN opsiyonel (sıcaklık **yalnız bilinen** doğrulamada) | Asıl unknown aileleri eğitim/seçim/kalibrasyona girmez — mevcut sızıntı testleri yeni yöntemlere de uygulanır |
| Rapor: unknown-pozitif AUROC/AP aile başına ve birleşik, OSCR, FPR@95TPR (TPR'nin hangi popülasyon olduğu yazılı), ECE, sabit Pfa'da Pd (C/I, I/N, IBO'ya göre), kapalı-küme doğruluğu OSCR ile birlikte (Vaze 2022) | Katı JSON, `null`+sayım; senaryo-bootstrap ve eğitim tohumu belirsizliği ayrı |

### İP-6 — Baseline genişletmesi (C2, C3) · öncelik: orta

Öncelik sırasıyla:

1. **EDSC** (Politis 2016/2017 tarzı iptal sonrası enerji dedektörü) — CuC için operatör araçlarına en yakın klasik baseline; İP-4.3 ile aynı iptal kodunu kullanır.
2. **Uzman özellik + gradyan artırma** (XGBoost) — P6 §5'te Kademe B'ye bırakılmıştı; taramanın hibrit DL+uzman önerisi (arXiv 2302.03749) ile birleştirilir.
3. **Yeniden yapılandırma dedektörü** (Saifaldawla tarzı CAE) — yalnız temiz eğitim, ikili algılama karşılaştırması.
4. **SnT formatında karşılaştırma** (V6 kipi: tek FFT, genlik) — araştırma-amaçlı lisans (P8); yük gerçekçiliği iddiası yok (L4).
5. **TorchSig ön eğitimli dedektör** — koşullu (L3).

### İP-7 — Yayın paketi (C1) · öncelik: son

| İş | Kapanış ölçütü |
|---|---|
| Veri kartı (dataset card) + sabit benchmark bölünmesi + üretici sürüm/hash | S-ICDF ve Fraunhofer sürümleri örnek alınır; üretilen veri Git'e girmez, komut + hash girer |
| Depo lisansı (README: üst düzey lisans yok) — **K13** | Kullanıcı kararı; üçüncü taraf türetilmiş veriler (ETSI tabloları) için ayrı not |
| Makale taslağı: ilgili çalışmalar = P1 §7 boşluk matrisi (uygulanan sütunuyla), sınırlar bölümü = DURUM §5.5 + bu belgenin §6'sı | Her sayı bir `results.json` alanına bağlı |

---

## 4. İş sırası

**K12 kararı: sabit tarih yok.** Aşağıdaki tarih sütunu yalnız ilk taslaktaki
tahmindir, bağlayıcı değildir; geçerli olan **sıradır**.

| Hafta | Tarih | Ben | Siz | Kilometre taşı |
|---|---|---|---|---|
| 1 | 20–26 Eki | İP-0 açık L-maddeleri; İP-1 metrik eklemeleri | S3 → S1 başlat | Belgeler tutarlı; metrikler testli |
| 2 | 27 Eki–2 Kas | R1-eval/1 kodu (IBO süpürmesi, Rapp, bellek polinomu); tam metin okumaları | S2 tam koşu → sonuç gönder | **Kademe A tam sonuç** |
| 3 | 3–9 Kas | B0 kararı, B2/B3; NPR kontrolü; OpenDPD türetme betiği | R1-eval/1 tam üretim | C3 IBO-eğrisi + yükselteç uyumsuzluğu |
| 4–5 | 10–23 Kas | İP-3: ASI, CuC, faz gürültüsü, PL çerçeve; `P18` B2/1 protokolü dondurulur | — | 8 sınıf üreteci testli |
| 6 | 24–30 Kas | İP-4: iptal artığı, plan kısa yolu, ablasyon altyapısı; İP-5 eğitim-zamanı OSR | B2/1 tam üretim | Ayırt edilebilirlik tablosu taslağı |
| 7 | 1–7 Ara | İP-6 EDSC + XGBoost; analiz | B2/1 tam koşu (3 tohum) | Nihai tablolar |
| 8 | 8–15 Ara | İP-7 taslak, sınırlar, veri kartı | Okuma/onay | Makale taslağı |

**Kesme sırası** (kapsam sıkışırsa, proje kuralı korunarak): cyclic dalı →
transformer karşılaştırması → ek unknown aileleri. K9 iki kanalı da istiyor;
cyclic dalı kesilmek zorunda kalırsa **iptal artığı + EDSC** kalır ve CuC sonucu
"PSD-tek gözlemde tanımlanamaz, C/I eşiği şu" biçiminde raporlanır.

---

## 5. Kararlar (kullanıcı yanıtları, 2026-10-20)

| # | Karar | Sonuç | Uygulamaya etkisi |
|---|---|---|---|
| K5 | ASI giriş noktası | **Uplink-ASI.** Downlink önerisi kullanıcı tarafından veto edildi | Komşu sistem yer istasyonunun yan lobu bizim uydunun alıcısına girer; IMUX/TWTA/OMUX'tan geçer, planlı taşıyıcıyla kısmen örtüşür, farklı sembol hızı/ofset. Yetkisiz taşıyıcıyla **tasarım gereği karışabilir çift** olarak raporlanır. Downlink-ASI park listesinde. E1-dev/1 ile çelişki: L16, K16 |
| K9 | CuC gözlem kanalı | **İkisi birden:** gözlemden iptal artığı **ve** tam cyclic (SCF) dalı | Sıra: önce iptal artığı (EDSC baseline'ı ile ortak kod), sonra PL çerçeve anahtarı + SCF dalı. Kâhin iptal yalnız etiketli üst sınır |
| K10 | Yenilik cümlesi | **Aşamalı.** Şimdilik: "Bildiğimiz kadarıyla, çok taşıyıcılı TWTA/IMUX/OMUX zincirini ve taşıyıcı planını birlikte modelleyen ilk açık GEO girişim tanıma benchmark'ı ve nicel yük farkı ölçümü." Çift-pol ve open-set B2/1 tamamlanınca eklenir | README, P0, P1 ve makale özeti bu cümleyi kullanır |
| K11 | Ölçülmüş PA kullanımı | **Ölçüm aralığında:** OpenDPD APA/DPA ölçümlerine bellek polinomu uydurulur; Rapp ve sentetik bellek polinomu eklenir; yalnız ölçülen genlik aralığındaki nominal IBO'da test; aşırı sürme bölgesinde kullanılmaz | Ön inceleme: [OpenDPD sondası](../results/opendpd_probe.md). Belleğin bant genişliğine ölçeklenmesi **[VARSAYIM]** |
| K12 | Takvim | **Sabit tarih yok** (ana plan V2 sürer) | §4 tarih sütunu bağlayıcı değil; yalnız **sıra** geçerli. 15 Aralık hedefi düştü |
| K13 | Lisans | **Şimdilik lisans yok** | Depo herkese açık ama lisanssız: başkaları kodu yasal olarak yeniden kullanamaz. OpenDPD'den türetilen katsayılar Apache-2.0 atıf koşuluyla (kaynak, commit, lisans notu) eklenir. Yayın öncesi yeniden sorulacak |
| K14 | Vekil unknown | **Yok:** eşikler ve sıcaklıklar yalnız bilinen doğrulamadan | Outlier exposure kapsam dışı; eğitim-zamanı OSR için ARPL/prototip kaybı (vekil gerektirmez) |
| K16 | E1-dev/1'deki downlink `adjacent_satellite` olayı | **Ayrı adla tutulur:** `adjacent_satellite_downlink` (geliştirme olayı ve ileride unknown adayı); B2/1'deki `adjacent_satellite` = uplink-ASI, yeni üreteçle | Yeniden adlandırma İP-3'te, tam test paketiyle; E1-dev/1 sürüm adı ve geçmiş sonuç dosyaları eski etiketi korur (tarihsel okuma testi) |

**SmartSpace on-board verisi (karar: bulutta işle).** Kullanıcı
`fnr-smartspace-project.uni.lu` adresini ortamın izinli alanlarına ekleyip
araştırma-amaçlı/ticari olmayan kullanım koşulunu kabul ettiğini teyit edince:
indir → yerelde SHA-256 → `data/external/smartspace_onboard/metadata.json` (P8
alanları) → Daoud ve ark. görevinin (6 sınıf: temiz + 5 alt bant) yeniden
üretimi ve bizim ResNet'in aynı görevde karşılaştırılması (V6 kipi). Depoya
yalnız betik, hash ve özet metrik girer; ham veri girmez. Bu karşılaştırma
**görev/format karşılaştırılabilirliğidir**, yük gerçekçiliği doğrulaması değildir
(L4). İndirme yolu ve kayıt formu gerekip gerekmediği **[DOĞRULANACAK]** (site bu
oturumda erişilemedi).

---

## 6. Hakem itirazları (bu programın en zayıf üç noktası)

| İtiraz | Yanıt / sınır |
|---|---|
| "Bütün sonuçlar iki simülatör arasındaki fark; gerçek veri yok." | Kabul edilen sınır (ana plan §1.2, DURUM §5.5). Program bunu üç ayakla daraltır: yükselteç ailesi uyumsuzluğu, NPR karşılaştırması, ölçülmüş PA aktarımı. Hiçbiri "operasyonel başarım" iddiası taşımaz. |
| "Plan maskesi unauthorized sınıfını bedavaya veriyor; model plan okuyucu." | İP-4.4 plan bozma testleri ve "maske var, taşıyıcı taşınmış" ablasyonu. Başarım maskeye bağlıysa sonuç böyle yazılır. |
| "CuC ve ASI'de kötü sonuç yöntemin başarısızlığıdır." | Önceden kayıtlı ayırt edilebilirlik analizi: hangi gözlem olmadan hangi çiftin ayrılamayacağı **sonuçtan önce** yazılır (İP-4, P18); kâhin üst sınırı ile gözlem-tabanlı yöntem arasındaki fark ayrıca raporlanır. |

---

## 7. Park listesi

- Downlink-ASI alt mekanizması (K5'te veto edildi)
- Çok etiketli / frekans konumlu çıktı (K4: Kademe B sonrası)
- Chalmers RF WebLab ölçümü (P8 koşullu)
- LLM tabanlı karakterizasyon, VAE ayrıştırma (GNSS literatüründen; kapsam dışı)
- ALC (otomatik seviye kontrolü), komşu transponderler
- Düşük bit derinliği/nicemleme etkisi (Electronics 2025)

## 8. Bu belgenin bıraktığı açık durum

İP-0'ın kalan L-maddeleri ve İP-1 metrik kodu sırada bende; S1–S2 tam koşusu ve
§5'teki kararlar sizde. Uygulama başlayınca her İP kendi P-belgesini veya
mevcut belgedeki değişiklik notunu alır; bu plan yalnızca sırayı ve kapanış
ölçütlerini tutar.
