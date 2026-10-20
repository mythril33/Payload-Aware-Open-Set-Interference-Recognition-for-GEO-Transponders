# P1 — Literatür, en yakın çalışmalar ve yenilik denetimi

Durum: **ARAŞTIRMA TARAMASI TAMAMLANDI; EN YAKIN 7 ÇALIŞMANIN TAM METNİ OKUNDU (§8); SİSTEMATİK DERLEME DEĞİL** · 2026-10-20. Bazı bulgular makale özetine, veri kaynağının açıklamasına veya mevcut depo testlerine dayanmaktadır. Bu farklı kanıt seviyeleri eşdeğer değildir.

## 1. Araştırma sorusu

Operatörün GEO bent-pipe transponder downlink izlemesinde **(i)** transponderin çok taşıyıcılı IMUX–TWTA–OMUX davranışını, **(ii)** plan ve mümkünse iki polarizasyondan sağlanan yan bilgiyi, **(iii)** gerçekçi işletim koşulu kaymalarını ve **(iv)** görülmemiş girişimlerin reddini birlikte değerlendiren bir karşılaştırma ne kazandırır?

**Yenilik hükmü:** “GEO'da ilk derin öğrenme” iddiası savunulamaz. Henarejos ve ark. (2019) deneysel uydu/yer sinyallerinde girişim tespit ve sınıflandırmasını, Daoud ve ark. (2023) uydu girişim veri temsillerini, Saifaldawla ve ark. (2024) NGSO→GSO girişim tespitini çalışmıştır. Buradaki **aday yenilik**, bu eksenlerin *operatör gözlem düzeni ve yük etkisiyle birlikte, önceden kaydedilmiş benchmark koşullarında* sistematik birleşimidir; araştırma öncesinde kanıtlanmış bir “ilk” değildir.

## 2. En yakın çalışmaların karşılaştırması

| Çalışma | Görev / gözlem | İlgili katkı | Bu projeden önemli fark veya bilinmeyen |
|---|---|---|---|
| [Henarejos, Vázquez & Pérez-Neira (2019)](https://arxiv.org/abs/1906.03012) | Karasal ve uydu ağlarından gerçek sinyallerle girişim tespiti ve sınıflandırma | Gerçek sinyal kullanılması ve DL ile sınıflandırma, “tümü ideal simülasyon” iddiasını çürütür | GEO transponderin çok taşıyıcılı TWTA/IMUX/OMUX etkisi, dual-pol/plan koşullaması ve open-set deneyleri **bu taramada doğrulanamadı** |
| [Daoud ve ark. (ICASSP 2023)](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/) | On-board interference; FFT genlik/kompleks gösterimleri; girişimin alt-bant konumu | CNN ve spektral temsil bağıntısı, doğrudan karşılaştırma verisi | Yayımlanan küme 6 etiket (temiz + 5 alt bant), tür etiketleri veya uzun spektrogramların yerine konamaz |
| [Saifaldawla ve ark. (PIMRC 2023)](https://orbilu.uni.lu/handle/10993/55631) | NGSO→GSO otomatik kodlayıcı ile tespit | Uydu özgül anomali algılama | Farklı girişim mekanizması; operatörün transponder içi IM sınıflandırması ile özdeş değil |
| [Saifaldawla ve ark. (TMLCN 2024)](https://doi.org/10.1109/TMLCN.2024.3418933) | NGSO kaynaklı GSO yer-istasyonu **downlink** girişiminin AE/VAE/transformer ile tespiti | Güçlü AI ve energy-detector karşılaştırması, hareketli NGSO senaryosu | Temel görev girişim var/yok; 8 sınıflı tip tayini + plan + yük IM'si + holdout-open-set protokolü değil |
| [Saifaldawla ve ark. (ICC Workshops 2024)](https://doi.org/10.1109/ICCWorkshops59551.2024.10615457) | 1D/2D convolutional autoencoder ile NGSO girişimi tespiti | Temsil ve tek/çoklu model kıyaslaması | Aynı uzay/hardware mekanizmasına ilişkin sonuçlar, tüm GEO bent-pipe tiplerine genellenemez |
| [Henarejos ve ark. (2019), uydu+karasal gerçek veri](https://arxiv.org/abs/1906.03012) | **Özellikle kapsam kontrolü** | Gerçek kayıt karşılaştırması temel zorunluluk | Yakın işin tam metninde transponder koşulları ve bilinmeyen tür testi ayrıca okunmalıdır |

Son satır ayrı yayın sayılmaz; tam metin okuma için kontrol satırıdır. Sayısal sonuçlar, farklı veri dağılımı ve yanlış alarm çalışma noktası nedeniyle doğrudan sıralanmamalıdır.

## 3. Temel fiziksel kaynaklar

1. [ETSI EN 302 307-1 V1.4.1 (DVB-S2)](https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf): referans uydu kanalı, Annex H, TWTA AM/AM ve AM/PM ve grup gecikmesi bağlamı.
2. [ETSI TR 102 376-2 V1.2.1](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf): doğrulama kılavuzu; Annex E'de IMUX/OMUX ek veri dosyası [orijinal ZIP](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p0.zip).
3. [ETSI EN 302 307-2 V1.4.1 (DVB-S2X, 2024)](https://dvb.org/?standard=second-generation-framing-structure-channel-coding-and-modulation-systems-for-broadcasting-interactive-services-news-gathering-and-other-broadband-satellite-applications-part-2-dvb-s2-extensions): S2X kapsamı; mevcut kodun otomatik olarak tam S2X uygulaması olduğunu göstermez.
4. [Saleh (1981)](https://doi.org/10.1109/TCOM.1981.1094911): TWTA'nın hafızasız AM/AM–AM/PM analitik modeli. Belirli bir DVB-S2 referans tüpünün ölçümü değildir.
5. [ITU-R Space Radio Monitoring](https://www.itu.int/en/ITU-R/space/Pages/ITU-Space-RadioMonitoring.aspx) ve [Spacecraft monitoring handbook (2008)](https://www.itu.int/dms_pub/itu-r/opb/hdb/R-HDB-53-2008-OAS-PDF-E.pdf): plan/atama bilgisinin operasyonel gözlemdeki rolü; modelde yer-truth taşıyıcı planını yüzde yüz güncel kabul etmek yine de ek bir varsayımdır.

**Önemli durum:** Bu deponun `docs/plan/kaynak_transponder_modeli.md` belgesi, halihazırda resmi filtre dosyalarından türetilen FIR ve şekilden sayısallaştırılmış TWTA örneklerini anlatıyor. “Sadece Saleh kullanılıyor” demek güncel repo için yanlıştır. Sayısallaştırma ve FIR toleransı gerçek ölçüm doğrulaması ile aynı şey değildir.

## 4. Open-set ve klasik baseline kaynakları

| Metot | Birincil kaynak | Değerlendirme notu |
|---|---|---|
| Maksimum softmax olasılığı (MSP) | [Hendrycks & Gimpel, ICLR 2017](https://arxiv.org/abs/1610.02136) | Yüksek softmax, bilinmeyen için güvence değildir |
| Energy score | [Liu ve ark., NeurIPS 2020](https://papers.neurips.cc/paper_files/paper/2020/hash/f5496252609c43eb8a3d147ab9b9c006-Abstract.html) | Sınıf logits'lerinin sıcaklığa duyarlı skoru |
| Mahalanobis | [Lee ve ark., NeurIPS 2018](https://proceedings.neurips.cc/paper_files/paper/2018/hash/abdeb6f575ac5c6676b747bca8d09cc2-Abstract.html) | Yalnızca eğitimden öğrenilmiş embedding ortalamaları/kovaryans |
| Open-set performans çerçevesi / OSCR | [Dhamija, Günther & Boult, 2018](https://arxiv.org/abs/1811.04110) | Sadece AUROC değil, doğru sınıflandırma ile yanlış kabul birlikte ölçülmeli |
| CA-/OS-CFAR | [Rohling (1983)](https://doi.org/10.1109/TAES.1983.309350) | Spektrum kenarları ve çoklu girişimlerde CFAR varyantları farklı davranır |
| Plan/etiket belirsizliği | [ITU space monitoring handbook](https://www.itu.int/dms_pub/itu-r/opb/hdb/R-HDB-53-2008-OAS-PDF-E.pdf) | Her sınıf doğrudan tek spektrumdan tanımlanamayabilir |

## 5. İddia ve kanıt matrisi

| Aday iddia | Kanıt durumu | Yazılabilecek güvenli ifade |
|---|---|---|
| “GEO girişim DL çalışmaları yok” | **YANLIŞ**: [2019](https://arxiv.org/abs/1906.03012), [2023](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/), [2024](https://doi.org/10.1109/TMLCN.2024.3418933) | “Belli önemli eksenleri birlikte inceleyen karşılaştırmalar sınırlı olabilir; tarama ve deneyle doğrulanmalı” |
| “Önceki işlerin hepsi idealize” | **ÇÜRÜTÜLDÜ**: deneysel uydu sinyali ve fiziksel NGSO yörüngeleri kullanan çalışmalar var | “Transponder içi multicarrier nonlinearity'nin çeşitli veri setlerinde açıkça modellenmesi farklılık gösterebilir” |
| “TWTA IM dış girişimle karışabilir” | **Fiziksel olarak makul ve repo pilotunda gözlem var**, saha doğrulaması yok | “Sentetik modelde yanlış alarm/yanlış sınıflama etkisi sınanıyor” |
| “Dual-pol + plan türleri her zaman ayırt eder” | **DESTEK YOK**: eşdeğer gözlemler mümkün | “Ayırt edilebilirlik koşula, sensor kalibrasyonuna ve operatör metadata'sına bağlı” |
| “Open-set reddi gereklidir” | **Metodolojik gerekçe var; GEO üzerinde ölçülen fayda henüz yok** | “Holdout-class deneyleriyle nicel test edilecek” |
| “Payload gap doğrulukta büyüktür” | **Mevcut küçük pilotta desteklenmedi** | “Tam veri ve uygun çalışma koşulu gerektirir; sınıfa özgü FA/etiket etkisi öncelikli” |

## 6. Açık araştırma işleri

- En yakın beş çalışmanın tam metninden **uygulama yeri, sinyal kaynağı, nonlinearity, plan metadata, polarization ve unknown-class** kanıtlarını sayfa/tablo ile çıkart.
- Konferans/jurnal sürümlerini tek çalışmanın iki baskısı olarak say; kendini alıntılayan veri setlerini bağımsız deney olarak değerlendirme.
- Operatör verisi veya ölçüm doğrulaması gelmedikçe fiziksel gerçekçiliği **standarta dayalı simülatör varsayımı** olarak etiketle.
- Plan gerçekliği (yanlış/eksik taşıyıcı listesi), transponder/anten geometri bilgisi ve en düşük test edilebilir bilinmeyen gücü için ayrıca kontrol ekle.
- Tarama sistematik değildir; “literatürde hiç yok” türünde negatif iddiaları, arama kapsamı belgelenmeden kullanma.

Kaynak künyeleri: `references/references.bib`; erişim ve telif koşulları: `docs/plan/P8_dis_veri.md`, `sources/ORIGINALS.md`.

## 7. Tarama v2 eki (2026-10-20)

Kaynak: kullanıcının verdiği *"Payload-Aware Open-Set Interference Recognition for
GEO Transponders: Literature Review"* (2026-10-20). Düzeltme ve iş programı:
[P16](P16_literatur_duzeltme_programi.md). Aşağıdaki satırlar taramanın
özetlerine dayanır; **tam metin okuması henüz yapılmadı** (P16 İP-0).

### 7.1 En yakın çalışmalara eklenenler

| Çalışma | Görev / gözlem | Bu projeden fark (taramaya göre) | Kanıt |
|---|---|---|---|
| Agon — Yang ve ark., arXiv 2606.14147 (2026) | Yarı denetimli ikili girişim tespiti; MAE ön eğitimli çift dikkatli transformer; çapraz veri/OOD dayanıklılık | Doğrusal süperpozisyon; ikili görev; OOD = kovaryat kayması, bilinmeyen sınıf reddi değil | **Ön baskı** |
| Pellaco, Singh & Jaldén, ICSSC 2019 (arXiv 1912.04716) | LSTM ile spektrum tahmini, sapmadan alarm; gerçek alınan spektrumlar | Yük modeli, plan, polarizasyon, open-set yok | OA PDF |
| Vázquez ve ark., IEEE Commun. Mag. 2021; SSC Newsletter 2019 (arXiv 2007.10110) | Operatör iş akışında ML; otoenkoder dedektörü, sabit eşik | Sınıfları adlandırıyor (yanlış yönlenmiş anten, yanlış yapılandırılmış ekipman), modellemiyor; "gerçek veri" ayrıntısı **[DOĞRULANACAK]** | OA (Zenodo, arXiv) |
| Politis ve ark., SPAWC 2016 / ICASSP 2017 | Uyduda istenen sinyali iptal edip artıkta enerji dedektörü (EDSC) | Uydu üstü (TWTA öncesi) gözlem; sınıflandırma yok; **baseline adayı** | ICASSP 2017 OA |
| Pérez-Neira ve ark., arXiv 1802.03958 | HTS sinyal işleme derlemesi | Yer tabanlı tespitin transponder bozulmasından etkilendiğini not ediyor → C3 motivasyonu | OA |
| Açık-küme karıştırma tanıma (Appl. Sci. 12(9):4380, 2022; Remote Sens. 14(24):6220, 2022; IET RSN 2024; IET Commun. 2026) | Genel / radar karıştırma sinyallerinde OSR | Uydu transponderi yok; en yakın OSR-girişim öncülü Appl. Sci. 2022 | Özet / OA |

### 7.2 Boşluk matrisi — planlanan ve uygulanan ayrı

✔ modellendi · ◐ kısmi · ✖ yok. "Uygulanan" sütunu 2026-10-20 depo durumudur;
tarama son satırı yalnız "planlanan" olarak doldurmuştu (P16 L6).

| | TWTA NL / IBO | IMUX/OMUX | Çok taşıyıcılı IM | Çift-pol / XPD | Taşıyıcı planı | Open-set |
|---|---|---|---|---|---|---|
| En yakın GEO işleri (SnT, Agon, CTTC, KTH) | ✖ (Agon: yalnız testbed ◐) | ✖ | ✖ | ✖ | ✖ (Daoud: alt-bant ızgarası ◐) | ✖ |
| DVB-S2X kılavuzu (referans kanal) | ✔ | ✔ | ✔ | ✖ (ihmal edildiği söyleniyor, **[DOĞRULANACAK]**) | ◐ | — |
| **Bu proje — planlanan** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Bu proje — uygulanan** | ✔ (A1) | ✔ (A1) | ✔ (A1) | ◐ (D1-dev/1, iki sınıf) | ✔ (maske) | ◐ (B1-dev/1–2, geliştirme) |

### 7.3 P1 kapanış kriterine göre durum

Ana plan P1 kapanış kriteri: "her boşluk iddiası en az 2 kaynakla desteklenmiş
veya düzeltilmiş; en yakın 5 çalışma ile fark tablosu". Fark tablosu artık
§2 + §7.1'de; ancak destek kaynakları özet düzeyinde. **P1 tam metin okuması
(P16 İP-0) bitmeden kapanmış sayılmaz.**

## 8. Tam metin denetimi (2026-10-20, P16 İP-0 / B9)

Açık erişimli tam metinler bu oturumda okundu (Agon: arXiv HTML v1). Konum
bilgileri ilgili PDF'teki bölüm ve denklem numaralarıdır.

| Çalışma | Gözlem noktası | Sinyal / veri | Doğrusalsızlık / transponder | Plan bilgisi | Polarizasyon | Görev | Bilinmeyen sınıf testi | Kanıt |
|---|---|---|---|---|---|---|---|---|
| Saifaldawla ve ark., TMLCN 2024 | GSO yer istasyonu, **downlink** | Simülasyon: MATLAB uydu araç kutusu + TLE yörüngeleri ile CNR/INR; DVB-S2X ModCod sembolleri, yükseltilmiş kosinüs | **Yok.** `y = x√CNR + Σ i_k √INR_k + ζ` (denklem 14–16), "yukarı/aşağı çevrim kusurları ideal biçimde telafi edilmiş" (dipnot 2) | Yok (bant örtüşme katsayısı B_adj) | Belirtilmemiş, tek kanal | İkili tespit; AE/VAE/TrID yeniden yapılandırma hatası; ED karşılaştırması | Yok | §II.A–B, §III, Alg. 1–2 |
| Henarejos ve ark., SPAWC 2019 | Yer terminali, **downlink**, tek anten | **Gerçek** Ku bandı DVB-S2 kaydı. LTE/UMTS/GSM ayrı bantlarda kaydedilip taban bantta β ile ölçeklenerek **sayısal olarak eklendi** (denklem 2) | İstenen sinyal gerçek bir transponderden geçmiş olabilir; **girişim transponderden geçmiyor**. Model `y = √ρ (x + √γ⁻¹ i) + w` (denklem 1) | Yok | Belirtilmemiş | Tespit: seyrek AE, temiz segmentlerden eşik. Sınıflandırma: kapalı küme 3 sınıf (LTE/UMTS/GSM), LSTM, 512 örnek, 4 öznitelik | Yok | §II, §III.A, §IV.A |
| Vázquez ve ark., SSC Newsletter 2019 (arXiv 2007.10110) | Operatör iş akışı (Eutelsat ortaklı, ESA ARTES) | Konum belgesi; deney yok | — | — | Cross-pol bir **neden** olarak anılıyor | Sabit eşikli sapma alarmı ("throws an alarm if the deviation trespasses a fixed threshold") | Yok | §C "Interference Detection and Classification"; %70–80 alıntısı metinde birebir |
| Pellaco ve ark., ICSSC 2019 | Yer istasyonu alıcısı | **Gerçek** spektrum verisi (Swedish Space Corporation), 1024 kutulu PSD | Model edilmiyor (veri gerçek) | Yok | Belirtilmemiş | LSTM ile bir sonraki spektrumun tahmini, eşik aşımında anomali; zamanda ve frekansta konumlama. İkincil ağ **modülasyonu** sınıflıyor, girişimi değil | Anomali tespiti doğası gereği tür bağımsız; sınıf bazlı open-set yok | §1, §2.1–2.2 |
| Politis ve ark., ICASSP 2017 | **Uydu üstü**, uplink (kısmen rejeneratif SMU) | Analitik + simülasyon; QPSK/BPSK taban bant sembol modeli | **Yok.** `H1: y = hs + w + i`, düz sönümleme (denklem 1–2). Yer tabanlı tespitin "transponder bozulmalarından" etkilendiğini açıkça not ediyor (§1) | Yok | Tek anten | İkili; çöz-iptal et-ED, kusurlu iptal altında Pfa türetimi | Yok | §1, §2.1–2.2, Teorem 1 |
| Daoud ve ark., ICASSPW 2023 | **Uydu üstü**, GSO uplink dönüş bağlantısı | Simülasyon: BPSK, f_d = 29,55 GHz, W = 50 MHz, f_s = 5 GHz, SNR_d = 12 dB, SNR_i = 6 dB sabit; sınıf başına 2500 örnek | **Yok** | 5 alt bant ızgarası | Belirtilmemiş | Kapalı küme 6 sınıf: temiz + girişimin bulunduğu alt bant | Yok | §3, §3.1–3.2 |
| Yang ve ark., Agon (arXiv 2606.14147v1; ön sürümü IEEE/CIC ICCC 2025) | Yer istasyonu; NGSO→GSO ve NGSO→NGSO | Kamusal NGSO-GSO seti (17 281 etiketli anlık görüntü) + "yüksek doğruluklu" NGSO-NGSO seti; ITU-R S.1428-1 anten deseni, Doppler | **Yok.** Bileşik sinyal açıkça "doğrusal süperpozisyon": `y = x_d√CNR + Σ x_k e^{j2πΔf t}√INR_k + ζ` (§III-B, denklem 4); girdi PWVD zaman-frekans gösterimi (denklem 5) | Yok | Belirtilmemiş | İkili tespit (eşiksiz doğrudan sınıflandırıcı) + çok görevli modülasyon sınıflandırma | OOD = kovaryat kayması (eksen dışı açı, INR, çapraz bant); bilinmeyen sınıf reddi yok | HTML tam metin §I–III; ön baskı |

| Chen ve ark., Appl. Sci. 12(9):4380, 2022 (açık-küme karşılaştırma) | Genel anti-jamming iletişim | Simülasyon: 9 karıştırma türü (tek/çok ton, darbeli Gauss, frekans atlamalı, doğrusal/ikinci derece süpürme, BPSK, gürültü-FM, QPSK); JNR ekseni | Yok (uydu yok) | Yok | Yok | Açık-küme tanıma: konvolüsyonel prototip öğrenme (HCPL), farklı "openness" düzeyleri | **Var:** bilinen sınıf doğruluğu + bilinmeyen reddi; JNR −10 dB'de bilinen sınıf doğruluğu diğerlerinden %2–7 yüksek | §1–2, özet |

**Sonuç:** Okunan yedi GEO/uydu tam metninin hiçbiri (a) bir uydu transponderinin çok taşıyıcılı TWTA/IMUX/OMUX
zincirini girişim tanıma verisine katmıyor, (b) taşıyıcı planını model girdisi yapmıyor, (c) çift
polarizasyon gözlemi kullanmıyor, (d) bilinmeyen girişim sınıfı reddini ölçmüyor. Bu bulgu tarama
iddiasını tam metin düzeyinde destekliyor. Açık-küme girişim tanıma ise uydu dışında vardır (Appl. Sci. 2022 tam metin; Remote Sens. 2022, IET RSN 2024 ve
IET Commun. 2026 özet düzeyinde); bu eksende yenilik "ilk açık-küme girişim tanıma" değil, "GEO transponder
gözleminde ilk" biçiminde kurulmalıdır. Kapsam sınırı: tarama sistematik değil (CNKI ve IEEE tam metinleri kısmen).

İki ince ayrım makale metnine taşınmalı:
- Henarejos 2019 ve Pellaco 2019 **gerçek** kayıt kullanıyor. "Bütün önceki işler simülasyondur" denemez.
  Doğru ifade: "girişim transpondere hiç girmiyor (sayısal ekleme) ya da transponder ayrıca modellenmiyor".
- Politis 2017, yer tabanlı gözlemin transponder bozulmasıyla kirlendiğini **kendisi** söylüyor. C3 motivasyonu
  için doğrudan alıntılanabilir.
