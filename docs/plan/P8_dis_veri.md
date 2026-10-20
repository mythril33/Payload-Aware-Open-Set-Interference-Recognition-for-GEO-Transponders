# P8 — Dış veri ve ölçüm kaynağı denetimi

Durum: **BELGELENEN KAYNAK SAYFALARI DENETLENDİ / VERİ DOSYALARI İNDİRİLİP ÇALIŞTIRILMADI** · 2026-10-20.

**Karar ilkesi:** “Kamusal olarak görüntülenebilir”, “ücretsiz araştırma amaçlı kullanım” ve “GitHub'da yeniden dağıtılabilir” birbirinden farklıdır. Depo kamuya açıktır; lisansı netleştirilmemiş büyük üçüncü taraf veri/PDF dosyalarını buraya kopyalamıyoruz. Ham veriler `data/external/` altında yerel saklanmalı (gitignore sayesinde takip edilmez).

| Kaynak | Birincil adres ve teknik içerik | Doğrulanan kısıt | Bu projede karar |
|---|---|---|---|
| **ETSI EN 302 307-1**, TR 102 376-2 | [EN PDF](https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf), [TR PDF](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf), [Annex E ZIP](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p0.zip) | Telif/yeniden dağıtma izni araştırmacı indirme hakkından ayrı | **KULLAN**: özgün kaynağı linkle, kullanıcının yerelde indirmesini sağla. Depoda türetilmiş veri zaten var |
| **SmartSpace on-board** | [Orijinal sayfa](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/): tam/azaltılmış FFT, genlik veya kompleks, 12.000 train + 3.000 validation, temiz + 5 alt bant olayı | [Toplu lisans notu](https://fnr-smartspace-project.uni.lu/datasets/): yalnızca araştırma, **ticari kullanım yasak** (kâr amacı olmayan kuruluşlar dahil) | **KULLAN**, konum/tetik algılama veya spektrum-formatı baseline; tip etiketli 8 sınıflı GEO veri gibi sunma |
| **SmartSpace NGSO→GSO** | [Orijinal sayfa](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/); [2024 yayın](https://doi.org/10.1109/TMLCN.2024.3418933); 800 uzunluklu genlik temsilleri, binary tespit bölümü | Aynı SmartSpace research-only açıklaması | **KULLAN**, ikili tespit görevinde; original IQ varsayma |
| **OpenDPD** | [Resmi repo](https://github.com/lab-emi/OpenDPD), [veri belgesi](https://lab-emi.github.io/OpenDPD/datasets/); gerçek PA input/output IQ çifti | Kod lisansı ile farklı verilerin lisansını **ayrı ayrı** doğrula; model/ölçümün PA türünü kayıt bazında kontrol et | **KOŞULLU KULLAN**: gerçek ölçülmüş PA aktarım eğrisi ve domain shift; **TWTA kalibrasyonu** diye adlandırma |
| **Chalmers RF WebLab** | [Erişim](https://dpdcompetition.com/rfweblab/access-details/) ve [düzenek](https://dpdcompetition.com/rfweblab/about/): uzaktan nonlinear **GaN PA** ölçümü, en fazla 1.000.000 IQ örneği, 200 MHz örnekleme, yaklaşık 160 MHz yararlı bant | Kayıt şart koşulmuyor; ölçüm çalışma durumu, kabul edilen güç/PAPR kısıtları ve çıktı hakları ayrıca kontrol edilmeli | **KOŞULLU KULLAN**: kontrollü PA ölçüm demonstrasyonu; GEO uzay TWTA'sının sahici ölçümü olarak sunma |
| **DARCY / Spectrum Highway 2** | [Zenodo veri kartı](https://doi.org/10.5281/zenodo.21336653), [resmi GitLab](https://gitlab.cc-asp.fraunhofer.de/darcy_gnss/fiot_highway2): GNSS E1/E6, 20 ms IQ snapshot, 62.5 MS/s, 50 MHz analog bant, etiketler | **CC BY-NC-SA 4.0**; yaklaşık **15.4 GB** arşiv; NC ve share-alike önemli | **KOŞULLU KULLAN**: GNSS'ye özgü girişim dalga biçimleri / domain shift; **GEO gerçek vakası değil**; depoya komple kopyalama |
| **DARCY controlled low frequency** | [GitLab](https://gitlab.cc-asp.fraunhofer.de/darcy_gnss/controlled_low_frequency); [yöntem makalesi](https://arxiv.org/abs/2409.15114) | Her veri sürümü/etiketin lisansı ayrıca doğrulanmalı | **OPSİYONEL**: dalga biçimi çeşitlemesi / ölçümsel domain shift |
| **Jammertest 2025** | [Veri deposu](https://github.com/FelixOtt94/FraunhoferIIS_Jammertest2025), LFS/HDF5, gerçek GNSS girişimleri | Alt veri dosyaları / LFS erişimi, kullanım koşulları ayrı denetlenmeli | **OPSİYONEL**: dış dağılımdaki gerçek girişim kalıpları |
| **TorchSig** | [Resmi repo](https://github.com/TorchDSP/torchsig) (MIT kod); [2025-26 migration notu](https://github.com/TorchDSP/torchsig/discussions/428) | “WidebandSig53” eski isim/üretim yolu; hazır ve indirilebilir GEO benchmark olduğu varsayılmamalı | **KULLAN**, sentetik RF ön eğitim generator'ı; sürümü, senaryoyu ve seed'leri kaydet |
| **Intelsat 37e SigMF** | Depo planındaki [Zenodo 13371136](https://zenodo.org/records/13371136) girdisi | **BU TARAMADA DOSYA İÇERİĞİ/İZİN AYRINTILARI YENİDEN DOĞRULANMADI** | **BEKLEMEDE**: gerçekten uygun, temiz downlink referans örneği mi denetle |

## Yanlış eşleştirmeleri önleme

- NGSO→GSO downlink paraziti **transponder TWTA'dan geçmeyebilir**; uplink girişimi ile fiziksel yol aynı değildir.
- GNSS L-band jamming kaydı = gerçek RF bozulması, fakat GEO Ku/Ka transponderin doğal girişimi **değil**. Yeniden frekans çevirimi/ölçekleme yapılırsa *türetilmiş sentetik senaryo* olarak etiketle.
- GaN katı-hal PA ≠ uyduda kullanılan TWTA. OpenDPD veya WebLab ile elde edilen fark **bilinmeyen PA/hardware transferine genelleme** deneyidir.
- SmartSpace ikili/alt-bant etiketlerini “sekiz interferer türü”ne çevirmek sahte etiket üretir.
- TorchSig'in MIT kod lisansı, üçüncü taraf ölçüm verisine otomatik MIT lisansı vermez.

## Hangi dosyalar depoya giriyor?

1. Bu denetim, birincil URL'ler, BibTeX ve **izin kapsamında bizim yazdığımız** bağımsız Markdown belgeleri.
2. Kullanıcı tarafından sağlanan orijinal araştırma taslağı: `sources/original_proposal.md` içerik transkripsiyonu; DOCX orijinalinin ikili kopyası bu araştırma kaydında otomatik yüklenmiş kabul edilmemeli.
3. Üçüncü taraf PDF/ZIP/raw IQ: yalnızca hak sahiplerinin dağıtım koşulu açıkça karşılanıyorsa ve dosya boyutu uygun ise repo kopyası. Aksi halde **kaynağın resmi URL'si orijinal dosyaya erişim yoludur**.

## Elde edilmesi gereken doğrulama kayıtları

Her ölçüm kümesinde şu alanları içeren yerel `metadata.json` tutulmalı: `source_url`, `downloaded_at_utc`, `version_or_commit`, `licence`, `sha256`, `sample_rate_hz`, `centre_frequency_hz`, `bandwidth_hz`, `representation`, `classes`, `processing`, `permissions_verified`. İndirilmiş dosya üzerinde hash hesaplamadan kayıtlara hash uydurulmamalı.
