# V4.1 Akademik Literatür Revizyonu — Teslim ve Kalan Kontroller

**Tarih:** 25 Ekim 2026  
**Kapsam:** Yalnızca editoryal/statik revizyon. Deney, üretim, held-out testi, GPU/CPU-heavy compute, GitHub değişikliği yapılmadı.  
**Ana belge:** `Literature_Review_GEO_Transponders_v4_1_Editorial.docx` (22 sayfa; akademik İngilizce).

## V4'e göre somut değişiklikler

1. Abstract ve Keywords eklendi; “kanıtlanmış deney başarısı” ile araştırma hipotezi ayrıldı.
2. IMUX–TWTA–OMUX için co/cross polarizasyonları, uplink/downlink giriş noktalarını ve koşullu plan bilgisini gösteren **Figure 1** özgün editoryal blok diyagram olarak eklendi. Bilinmeyen sayısal verilerle eski Figure 2–3 grafikleri yeniden yaratılmadı.
3. **17 OMML matematik nesnesi** aynen korundu; denklemler Word içinde matematik formatını kaybetmedi.
4. 106 kaynak yayın kopyasında IEEE ilk-atıf sırasına göre numaralandırıldı; tarihsel numaralar (`R001`–`R106`) `reference_reconciliation_v4_1.json` içinde bire bir korunuyor.
5. Tarihsel **[54]** 2020 DVB BlueBook draft yerine **2021 ETSI TR 102 376-2 V1.2.1** resmî yayınına bağlandı; EN 302 307-1 Annex H.7 **informative** niteliği açık yazıldı.
6. Tarihsel **[93]** SmartSpace kaynak sayfasındaki tam veri kümesi başlığıyla düzeltildi. Tarihsel **[94]** IEEE DataPort kaydına göre dört yazar ve **CC BY-NC-SA 4.0** lisansıyla düzeltildi.
7. Tarihsel **[106]** yayın yılının Mart 2021, DOI yılının 2020 olduğu ayrımı ile `10.1109/MVT.2020.3002525` eklendi; bu DOI'nin tam yayıncı metni incelenmedi.
8. Stage A dört-sınıf eşleştirilmiş nonlinear test ile `M-nl5` overdrive ayrımı; Stage B input availability, SCF contiguous IQ, host cancellation ve frozen plan koşulları güçlendirildi.
9. 367 örneklik Stage A pilot, raporlanmış fakat **yeniden üretilmemiş** olarak; D-1 test geçmişi 500/150 ana ile 498/148 çıkarma-duyarlılık kontrolü olarak belirtildi.
10. Bilimsel karar ve üretim yürütme yetkisi ayrıldı: E9/E12 bilimsel karar kayıtlarına karşın **EXECUTION NO-GO** yürürlükte; hiçbir yeni test açılmadı.

## Doğrudan bakılan kaynaklar

- [ETSI TR 102 376-2 V1.2.1 (2021)](https://www.etsi.org/deliver/etsi_tr/102300_102399/10237602/01.02.01_60/tr_10237602v010201p.pdf), §4.4.1.3–§4.4.1.4; PDF sayfaları 31 ve 33 görsel olarak kontrol edildi.
- [ETSI EN 302 307-1 V1.4.1 (2014)](https://www.etsi.org/deliver/etsi_en/302300_302399/30230701/01.04.01_60/en_30230701v010401p.pdf), Annex H (informative), Figure H.3–H.4 sayfası görsel kontrol edildi.
- [IEEE DataPort Highway Dataset 1](https://ieee-dataport.org/documents/gnss-interference-spectrum-highway-dataset-1), dört yazarlı “Dataset Citation” alanı ve lisans açıklaması incelendi.
- [SmartSpace NGSO to GSO’s Users Interference](https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/), kaynağın kendi sayfa başlığı kontrol edildi.
- ArXiv kayıtları ve resmi yazılım kayıtları `[96]–[106]` aralığında seçili metadata için tarandı; bütün makalelerin içeriği teker teker kanıtlanmış değildir.

## Statik kabul ve sınırlamalar

- DOCX: 22 sayfa; görsel render kontrolü yapıldı. **106/106 kaynak atıflı**, kaynakların ilk kullanım dizisi 1–106, 17/17 Word matematik nesnesi korunmuş, 7 tablo ve 1 blok şema var.
- Tabloların yazarlarca bildirilen sonuçları burada bağımsız yeniden üretim sayılmaz.
- Eksik yayın öncesi kontroller: kalan tam-metin/DOI/lisans doğrulamaları; sayısal şekiller için hash'li kaynak kayıtları; bilimsellik onayı; statik linter'in yeni kaynak statüleri için güncellenmesi. Bunların tamamlandığı iddia edilmez.
- Kullanıcının orijinal V4 DOCX'i, `refs.json`, repo working tree ve GitHub PR'ları **değiştirilmedi**.

## Dosya kimlikleri

| Dosya | SHA-256 |
|---|---|
| V4 orijinal (okunan) | `a7c6a3cb810655ed0a93b8169de1405fc8e0acb37efd82be43a9589d45d1e721` |
| V4.1 DOCX | `ee437ca80bdc55bacc51c66909c30fb8f7cbf7c71dc1b92ace2ffcf787f88afd` |
