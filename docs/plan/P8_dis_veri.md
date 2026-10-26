# P8 — Dış veri ve ölçüm kaynağı denetimi

## Güncel araştırma önceliği ve gerçek erişim — 2026-10-25

**Öncelik: mevcut kamusal araştırma verisini edinmek ve değerlendirmek; tam B2
üretimi bundan önce gelmiyor.** Yeni E-numaralı iş paketi yok. B2/1, bilimsel
onaylar ve compute yetkileri değiştirilmedi; korumalı B2 test gözlemi açılmadı.
Özgün önerinin dış veri stratejisi yeniden uygulamaya alındı.

| Kaynak | Resmî kaynak / lisans | Gerçekte erişilen dosya ve temsil | Ayrım / görev / engel |
|---|---|---|---|
| SmartSpace on-board | [Veri sayfası](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/), [research-only koşulu](https://fnr-smartspace-project.uni.lu/datasets/); ticari kullanım yasak | Açıklama HTTP200; SharePoint indirmesi giriş HTML'i, anonim API401, sonraki doğrudan istek403. **0 ham dosya**; ham dosya hash'i yok | 12.000 train/3.000 validation; ayrı test tarif edilmemiş. Beş sıfır temiz, beş one-hot vektör alt bant1–5. Altı **konum** sınıfı; sekiz girişim türü değil. 1000/100-bin FFT genlik/kompleks. MAT anahtarları ve kaynak-kayıt kimlikleri doğrulanamadı |
| SmartSpace NGSO→GSO | [Veri sayfası](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/); aynı research-only koşulu | Açıklama HTTP200; indirme aynı Microsoft kimlik doğrulama engeli. **0 ham dosya**, performans sonucu null | 11.500 temiz train/1.302 temiz validation; 4.470 karışık test, 800 genlik değeri. Test etiketinin sayısal pozitif yönü açıklanmamış. 801/802 sütunlu karşılaştırma tablolarındaki etiket/INR/açı özellik olamaz |
| Fraunhofer LC laboratory | [Zenodo21333335](https://zenodo.org/records/21333335), [sabit yazar deposu](https://github.com/FelixOtt94/FIOT_LC_laboratory/tree/2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26) | Gerçek LFS arşivi **2.216.728 B**, 744 NPY; 736 etiketli, sekiz etiketsize etiket atanmadı. 9/10×308 alıcı özelliği; IQ değil | Yayımlanan577/159 train/test; 145/39 boş dizi. Kullanılabilir432/120. Yer/PRN/azimut/açı, jammer-ID ve güç girdiden çıkarıldı. Kayıt-ID ve boş olmayan dosya-hash kesişimi0. Sınıf7(CW) yok |
| Fraunhofer FIOT laboratory | Aynı sabit depo ve Zenodo kaydı | Gerçek LFS arşivi **364.187.305 B**. Yalnız tüm1.121 ana kaydın crop0'ı çıkarıldı: **1.673.787.520 B**, 512×243×3 int32 RGB spektrogram görüntüsü. IQ/kalibre PSD değil; üç kanal renk, polarizasyon değil | Yerel train878/test243; bütün altı crop aynı ana kayıtta. Test81 temiz/162 girişimli. Kayıt-ID/hash kesişimi0; edinim günü/oturum bağımsızlığı bilinmiyor. Tam10,04-GB açılım yapılmadı |
| Fraunhofer Highway2 | [Zenodo21336653](https://zenodo.org/records/21336653) | Metadata HTTP200; **15.352.279.851 B arşiv indirilmedi**. GitLab bu denetimde503 | Yönetilebilir laboratuvar verisi seçildi. Bu kaynağın ham dosyası edinilmiş gibi sunulmuyor |
| OpenDPD | [Resmî depo](https://github.com/lab-emi/OpenDPD), Apache-2.0 kod; ayrı veri lisansı incelenen kartlarda belirtilmemiş | APA/DPA200MHz iki train-input CSV gerçekten indirildi: toplam2.780.743 B; I,Q sütunları. Hash'ler mevcut modele eşit; ilgili12 train/val/test input/output Git blob'u değişmemiş | **Mevcut val-seçilmiş model tekrar kullanılır**, yeni PA deneyi/fit yok. GaN/CMOS Doherty, uzay TWTA ölçümü değil |
| Chalmers RF WebLab | [Erişim](https://dpdcompetition.com/rfweblab/access-details/), [düzenek](https://dpdcompetition.com/rfweblab/about/), HTTP200 | Sayfa kayıt gerektirmeyen çalışan **canlı ölçüm hizmeti** diyor; hazır indirilebilir veri kümesi değil. Ölçüm endpoint'i çağrılmadı | Çıktı hakları ayrıca açıklanmamış; mevcut OpenDPD kanıtı varken yeni donanım ölçümü acil bağımlılık değil |

**Lisans tutarsızlığı:** LC/FIOT ve Highway2 Zenodo API alanı `CC BY-SA 4.0`,
kaynak README/açıklaması `CC BY-NC-SA 4.0` diyor. Bu çelişki çözülmüş sayılmadı.
Yerel ticari olmayan araştırma daha kısıtlı koşula uygundur; ham arşiv/NPY/liste
dosyaları Git'e konmadı. Küçük Zenodo LC ZIP'i (221.844 B) yalnız repository/LFS
pointer içeriyor; onu indirmek gerçek örnekleri edinmek değildir.

SmartSpace'in iki kümesi de mevcut P1 birincil-makale denetiminde **simülasyon**
verisi olarak tanımlanır: on-board uplink ve NGSO downlink karşılaştırmasıdır.
Kamusal olmaları ölçülmüş GEO RF, payload doğrusal olmayanlığı, operatör planı veya
çift polarizasyon sağladıkları anlamına gelmez. NGSO downlink girişimi transponder
TWTA'sından geçmek zorunda değildir.

Gerçek sayısal sonuçlar, kaynak/arşiv hash'leri, komutlar ve kısıtlar
[sonuç raporunda](../results/public_data_baselines.md); bağımsız yükleyiciler ve
sabit deney tarifi [research/public_data](../../research/public_data/README.md)
altında. SmartSpace yükleyicileri beyan edilen şemaya ait fixture testleridir;
ham MATLAB konteyneri görülmeden gerçek-veri uyumluluğu iddia edilmez.

SmartSpace için somut kalan adım: veri sahibinden çalışan anonim araştırma
paylaşımı veya kullanıcının yetkili yerel kopyası; ayrıca gerçek değişken adları,
NGSO pozitif etiket yönü ve varsa ana kayıt/senaryo kimlikleri. Validation'ı hem
eşik seçimi hem bağımsız test olarak kullanmayacağız.

## 2026-10-20 tarihsel kaynak envanteri

Aşağıdaki eski erişim/lisans durumlarının güncel karşılığı üst tablodadır.
Özellikle eski "SmartSpace host engelli" ve "veri indirilmedi" ifadeleri artık
tüm kaynaklar için geçerli değildir.

Tarihsel durum: **KAYNAK SAYFALARI DENETLENDİ / VERİ DOSYALARI İNDİRİLİP ÇALIŞTIRILMADI** · 2026-10-20.

**Karar ilkesi:** “Kamusal olarak görüntülenebilir”, “ücretsiz araştırma amaçlı kullanım” ve “GitHub'da yeniden dağıtılabilir” birbirinden farklıdır. Depo kamuya açıktır; lisansı netleştirilmemiş büyük üçüncü taraf veri/PDF dosyalarını buraya kopyalamıyoruz. Ham veriler `data/external/` altında yerel saklanmalı (gitignore sayesinde takip edilmez).

| Kaynak | Birincil adres ve teknik içerik | Doğrulanan kısıt | Bu projede karar |
|---|---|---|---|
| **ETSI EN 302 307-1**, TR 102 376-2 | [EN PDF](https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf), [TR PDF](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf), [Annex E ZIP](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p0.zip) | Telif/yeniden dağıtma izni araştırmacı indirme hakkından ayrı | **KULLAN**: özgün kaynağı linkle, kullanıcının yerelde indirmesini sağla. Depoda türetilmiş veri zaten var |
| **SmartSpace on-board** | [Orijinal sayfa](https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/): tam/azaltılmış FFT, genlik veya kompleks, 12.000 train + 3.000 validation, temiz + 5 alt bant olayı | [Toplu lisans notu](https://fnr-smartspace-project.uni.lu/datasets/): yalnızca araştırma, **ticari kullanım yasak** (kâr amacı olmayan kuruluşlar dahil) | **KULLAN**, konum/tetik algılama veya spektrum-formatı baseline; tip etiketli 8 sınıflı GEO veri gibi sunma. **Karar 2026-10-20:** bulutta işlenecek; host bulut ortamının ağ politikasında engelli, kullanıcı izinli alanlara ekleyecek ve kullanım koşulunu teyit edecek (P16 §5) |
| **SmartSpace NGSO→GSO** | [Orijinal sayfa](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/); [2024 yayın](https://doi.org/10.1109/TMLCN.2024.3418933); 800 uzunluklu genlik temsilleri, binary tespit bölümü | Aynı SmartSpace research-only açıklaması | **KULLAN**, ikili tespit görevinde; original IQ varsayma |
| **OpenDPD** | [Resmi repo](https://github.com/lab-emi/OpenDPD), [veri belgesi](https://lab-emi.github.io/OpenDPD/datasets/); gerçek PA input/output IQ çifti. **2026-10-20, commit `cb4c5ea` klonlanıp incelendi:** APA_200MHz(_b) = Ampleon GaN Doherty, 3,5 GHz; DPA_160/200MHz = 40 nm CMOS dijital Doherty verici, 2,4 GHz; 160–200 MHz çok taşıyıcılı OFDM | Depo Apache-2.0; veri için ayrı lisans belirtilmemiş, atıf makaleler üzerinden. Sıkışma zayıf (p99'da 0,2–0,8 dB) — [sonda](../results/opendpd_probe.md) | **KULLAN (K11)**: yalnız ölçülen genlik aralığında, nominal IBO testinde; bellek polinomu türetilir; **TWTA kalibrasyonu** diye adlandırma |
| **Chalmers RF WebLab** | [Erişim](https://dpdcompetition.com/rfweblab/access-details/) ve [düzenek](https://dpdcompetition.com/rfweblab/about/): uzaktan nonlinear **GaN PA** ölçümü, en fazla 1.000.000 IQ örneği, 200 MHz örnekleme, yaklaşık 160 MHz yararlı bant | Kayıt şart koşulmuyor; ölçüm çalışma durumu, kabul edilen güç/PAPR kısıtları ve çıktı hakları ayrıca kontrol edilmeli | **KOŞULLU KULLAN**: kontrollü PA ölçüm demonstrasyonu; GEO uzay TWTA'sının sahici ölçümü olarak sunma |
| **DARCY / Spectrum Highway 2** | [Zenodo veri kartı](https://doi.org/10.5281/zenodo.21336653), [resmi GitLab](https://gitlab.cc-asp.fraunhofer.de/darcy_gnss/fiot_highway2): GNSS E1/E6, 20 ms IQ snapshot, 62.5 MS/s, 50 MHz analog bant, etiketler | **CC BY-NC-SA 4.0** (2026-10-20'de Zenodo kaydından yeniden okundu; literatür taramasının CC BY-SA ifadesi yanlış; LC Laboratory kaydı zenodo 21333335 ise CC BY-SA 4.0); yaklaşık **15.4 GB** arşiv; NC ve share-alike önemli | **KOŞULLU KULLAN**: GNSS'ye özgü girişim dalga biçimleri / domain shift; **GEO gerçek vakası değil**; depoya komple kopyalama |
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
