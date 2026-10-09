# Kaynak taraması — DVB-S2 referans transponder modeli (Ek H.7)

2026-10-09 · Soru: IMUX/OMUX ve TWTA referans eğrilerinin sayısal değerleri nereden alınabilir?

Okunan belgeler: EN 302 307-1 V1.4.1'in tam metni (H.7, H.8, 5.5.4, 5.6 ve takımyıldız şekil etiketleri okundu); TR 102 376-2 V1.2.1'in 4.4.1.1–4.4.1.4 maddeleri ve Ek E; Dimitrov 2016 makalesinin tamamı. TR 102 376-1 ve diğer sonuçlar yalnızca özet düzeyinde tarandı.

## Sonuç

| Bileşen | Sayısal veri var mı? | Nerede | Durum |
|---|---|---|---|
| IMUX/OMUX genlik ve grup gecikmesi | **Evet** | ETSI TR 102 376-2 V1.2.1, Ek E: belgeye ekli `tr_10237602v010201p0.zip` içinde 26, 33 ve 36 MHz için metin dosyaları | Dosyayı indiremedim (bu ortamdan ETSI'ye doğrudan erişim kapalı, okuyucu araçlar zip'i reddediyor). Elle indirilip depoya eklenmeli. |
| IMUX/OMUX için yayımlanmış parametrik yaklaşım | **Evet** | Dimitrov, "Non-linear Distortion Noise Cancellation for Satellite Forward Links", 2016 (DLR): IMUX = 7. derece Chebyshev II, 34 dB, 23 MHz kenar; OMUX = 5. derece Chebyshev II, 38 dB, 28,6 MHz kenar; 36 MHz transponder. Yazar, TR 102 376-2'deki ölçülmüş yanıtlarla "iyi eşleştiğini" belirtiyor. | **Uygulandı**, varsayılan süzgeç modeli oldu. |
| TWTA AM/AM ve AM/PM (doğrusallaştırılmamış ve doğrusallaştırılmış) | **Hayır** | EN 302 307-1 Şekil H.2 ve H.3; TR 102 376-2 Şekil 10 ve 11; TR 102 376-1 Şekil 7 ve 8 | Hepsi yalnızca şekil. Sayısal tablo veya bu eğriye uydurulmuş katsayı veren açık bir kaynak bulamadım. |
| Faz gürültüsü maskesi | **Evet** | EN 302 307-1 Tablo H.1 | Aşağıda; Kademe B'de kullanılacak. |

## Standarttan doğrulanan ayrıntılar

- **Ek H.7 yapısı:** IMUX → güç yükselteci → OMUX → downlink gürültüsü. İki yükselteç modeli: doğrusallaştırılmış Ku-bant TWTA (ölçüm frekansı 10 992,5 MHz) ve doğrusallaştırılmamış Ka-bant TWTA. Belirtilen süzgeç genişliği için referans sembol hızı 27,5 Mbaud.
- **Süzgeç referansı:** 36 MHz transponder, 40 MHz kanal aralığı (TR 102 376-2, Şekil 6 ve 7, "Courtesy of SES"). TR ayrıca bu süzgeçlerin gerçek bir transponderden alındığını ama tüm yükleri temsil etmediğini belirtiyor.
- **Ölçekleme kuralı:** G(f) = (36/BW) × grup gecikmesi(f × 36/BW), R(f) = bastırma(f × 36/BW). EN 302 307-1 metninde frekans çarpanı "BW/36" olarak yazılmış, TR 102 376-2'de "36/BW". Fiziksel olarak tutarlı olan TR'deki biçim; projede o kullanılıyor.
- **Şekil H.3 eksen aralıkları:** giriş gücü −20…+6 dB, çıkış gücü −16…0 dB, faz −10…70°. Eğrinin kendisi metinden okunamıyor.
- **Tablo H.1, toplam faz gürültüsü maskesi (dBc/Hz):**

| Kayma | 100 Hz | 1 kHz | 10 kHz | 100 kHz | 1 MHz | > 10 MHz |
|---|---|---|---|---|---|---|
| Tipik | −25 | −50 | −73 | −93 | −103 | −114 |
| Kritik | −25 | −50 | −73 | −85 | −103 | −114 |

- **PL karıştırma (5.5.4):** PL başlığı karıştırılmaz; dizi her başlığın sonunda yeniden başlatılır.
- **APSK açıları:** şekil etiketleri 16APSK için φ = π/4 ve π/12, 32APSK için π/4, π/12 ve π/8. Koddaki nokta kümeleriyle uyumlu.

## TWTA için kalan yollar

1. **Şekli sayısallaştırmak.** Standardın PDF'ini bu sohbete eklerseniz Şekil H.3 ve H.2'yi okuyup tabloya çevirebilirim. Okuma hatası birkaç onda bir dB ve birkaç derece düzeyinde olur; makalede "şekilden sayısallaştırıldı" diye belirtilmesi gerekir.
2. **Saleh katsayılarını o tabloya uydurmak.** Sayısallaştırmadan sonra yapılabilir; analitik model korunur.
3. **Mevcut durumda kalmak.** Saleh'in klasik katsayıları; DVB-S2 eğrisiyle ilişkisi yok.

## Kaynaklar

- ETSI EN 302 307-1 V1.4.1: https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf
- ETSI TR 102 376-2 V1.2.1: https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf
- Ek E veri dosyası: https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p0.zip
- ETSI TR 102 376 V1.1.1: https://www.etsi.org/deliver/etsi_tr/102300_102399/102376/01.01.01_60/tr_102376v010101p.pdf
- Dimitrov 2016: https://elib.dlr.de/108553/1/07601465.pdf

---

## Güncelleme (2026-10-09): veri dosyaları ve standart PDF'i alındı

Kullanıcı TR 102 376-2 Ek E dosyalarını (26, 33, 36 MHz IMUX/OMUX), EN 302 307-1 PDF'ini ve Ek F'ye ait `User_terminal_patterns.xlsx` dosyasını sağladı. Yukarıdaki "TWTA için kalan yollar" bölümü artık geçersiz; durum şöyle:

| Bileşen | Yeni durum | Nasıl |
|---|---|---|
| IMUX/OMUX | **Resmi tablodan kuruluyor**, varsayılan model (`filter_model="etsi"`) | 36 MHz tablosundan 1024 katsayılı karmaşık FIR, 288 MHz; 72 MHz için H.7 ölçekleme kuralı. `scripts/build_mux_filters.py` |
| TWTA, doğrusallaştırılmamış (Şekil H.3) | **Sayısallaştırıldı**, varsayılan model (`amplifier="dvbs2_nl"`) | PDF'teki eğriler vektör çizgi; köşe noktaları okunup ızgara çizgilerine göre kalibre edildi. Piksel izleme yok. `scripts/digitize_twta_figures.py` |
| TWTA, doğrusallaştırılmış (Şekil H.2) | **Sayısallaştırıldı** (`amplifier="dvbs2_lin"`) | Aynı yöntem; şekil dB başına bir işaretçi veriyor (36 nokta) |
| Saleh | Seçenek olarak duruyor (`amplifier="saleh"`) | "Görülmemiş yükselteç" testi için |

### FIR'ın tabloya uygunluğu

| Süzgeç | ±20 MHz içinde en büyük kazanç hatası | En büyük grup gecikmesi hatası |
|---|---|---|
| IMUX 36 MHz | 0,009 dB | 1,4 ns |
| OMUX 36 MHz | 0,004 dB | 0,4 ns |
| IMUX 72 MHz (ölçekli) | 0,009 dB | 0,3 ns |
| OMUX 72 MHz (ölçekli) | 0,004 dB | 0,1 ns |

Durdurma bandındaki derin çentiklerde hata 2 dB'ye kadar çıkıyor (−60 dB düzeyinde).

### Chebyshev II yaklaşımı (Dimitrov 2016) tabloya ne kadar uyuyor?

| Süzgeç | Aralık | En büyük kazanç sapması | En büyük grup gecikmesi sapması |
|---|---|---|---|
| IMUX | ±14 MHz | 0,22 dB | 12 ns |
| IMUX | ±18 MHz | 0,49 dB | 28 ns |
| OMUX | ±14 MHz | 0,20 dB | 3 ns |
| OMUX | ±18 MHz | 1,04 dB | 9 ns |

Bant kenarında (±18 MHz): IMUX tablosu −1,18 / −1,34 dB ve 37–40 ns verirken yaklaşım −1,16 dB ve 65 ns veriyor; OMUX tablosu −1,0 dB ve 35–40 ns, yaklaşım −2,05 dB ve 31 ns. Genlik için iyi, grup gecikmesi için kaba bir yaklaşım. Tablo ayrıca hafifçe asimetrik; Chebyshev simetrik.

### Sayısallaştırılan TWTA değerleri

Giriş gücü doyuma göre (dB) → çıkış gücü (dB) / faz (°):

| Giriş | H.3 doğrusallaştırılmamış | H.2 doğrusallaştırılmış |
|---|---|---|
| −20 | −13,19 / 0,0 | −16,91 / 1,3 |
| −10 | −3,92 / 10,5 | −4,47 / 8,7 |
| −6 | −1,43 / 21,3 | −1,24 / 10,4 |
| −3 | −0,39 / 31,3 | −0,27 / 10,4 |
| 0 | 0,00 / 42,0 | 0,00 / 12,3 |
| +4 | −0,48 / 57,3 | −1,01 / 20,3 |

Saleh'in klasik katsayılarıyla fark: doyumda AM/PM 22,4° (Saleh) ve 42,0° (H.3); doyumdaki kazanç sıkışması 6,0 dB ve 6,8 dB.

Sınırlar:
- H.3 eğrisi −20,1…+5,8 dB aralığında çizilmiş. Altında sabit kazanç ve sıfır faz, üstünde son 2 dB'lik eğilimin devamı varsayıldı **[VARSAYIM]**. Düşük IBO'da çok taşıyıcılı sinyalin tepeleri üst sınırı aşar.
- H.2'de dB başına tek nokta var ve faz basamaklı; aradaki değerler doğrusal ara değerlemeyle bulunuyor. Bu modelde C/IM geri çekilmeyle tekdüze artmıyor (IBO 9 → 12 → 15 dB'de 32,5 → 31,1 → 30,6 dB). Bunun ne kadarının gerçek tüp davranışı, ne kadarının seyrek veri olduğunu ayıramıyorum.
- Standart, taban bant merkezindeki araya girme kaybını vermiyor; kazançlar görelidir.

### Depoda ne var, ne yok

- **Depoda:** türetilmiş FIR katsayıları (`src/geosim/data/mux_fir.npz`), sayısallaştırılmış TWTA tablosu (`src/geosim/data/dvbs2_twta.json`) ve bunları üreten iki betik.
- **Depoda değil:** ETSI'nin ham tablo dosyaları ve PDF. Yerelde `data/` altında duruyor ve git tarafından yok sayılıyor; ETSI belgeleri telif korumalı olduğu için yeniden dağıtmadım. Hukuki bir değerlendirme değil, ihtiyatlı bir varsayılan; karar sizin.
- **Kullanılmayanlar:** 26 ve 33 MHz tabloları (ileride "görülmemiş süzgeç" testi olabilir) ve `User_terminal_patterns.xlsx` (11,7 GHz'te 45–75 cm kullanıcı anteni azimut örüntüleri ve toplam C/(N+I) sayfası; komşu uydu girişimi sınıfı için Kademe B'de işe yarar).
