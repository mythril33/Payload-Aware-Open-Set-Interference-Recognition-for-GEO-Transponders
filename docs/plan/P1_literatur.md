# P1 — Literatür, en yakın çalışmalar ve yenilik denetimi

Durum: **ARAŞTIRMA TARAMASI TAMAMLANDI; TAM METİN / KAPSAMLI SİSTEMATİK DERLEME DEĞİL** · 2026-10-20. Bazı bulgular makale özetine, veri kaynağının açıklamasına veya mevcut depo testlerine dayanmaktadır. Bu farklı kanıt seviyeleri eşdeğer değildir.

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
