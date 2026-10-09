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
