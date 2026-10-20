# P9 — Yol haritası, risk ve yayın konumlandırması

Tarih 2026-10-20 · **öneri**, proje teslim sözü veya tamamlanmış deney listesi değil. Kaynak taslağındaki 15 Aralık 2026 makale teslimi *hedef* olarak alınabilir; mevcut repo `00_ana_plan.md` dosyasında sabit ders teslimi olmadığını yazar. Takvim resmen onaylanmadan hedef kesin tarih değildir.

## 1. En kısa savunulabilir araştırma çizgisi

| Öncelik | Çıktı | Başarı ölçütü | Durum |
|---|---|---|---|
| P0 | Mevcut beş sınıflı Kademe A çalışmasını yeniden üret | `pytest`, frozen A1 full data, 3 seed, aynı çalışma noktası | Pilot var, tam koşu yok |
| P1 | C3/payload-gap'ın test edilebilir yorumunu sabitle | Bilinen yükte IM'nin false alarm ve yanlış etikete katkısı, eşik ve CI | Pilot tek başına yetersiz |
| P2 | Kaynakları belgeleyen asgari peer-review savunması | İlk 5 yakın makale ve ETSI kaynakları tam metin teyidi | Bu depo belgeleri ilk taramayı yaptı |
| P3 | Gerçek donanım çapası | En az bir **yayımlanmış ölçülmüş PA** ile OOD aktarımı | Henüz ölçüm sonucu yok |
| P4 | Open-set Kademe B | B1 protokolü, 8 known, bilinmeyen test ve OSCR | Tasarım önerisi hazır, kod yok |
| P5 | Saha güvenilirliği | Plan kayması, kalibrasyon/XPD, yanlış alarm ve tek/çoklu olay | Kod/deney yok |
| P6 | Makale ve yayımlanabilir veri | Lisans uygun kaynaklar, reproducibility, negatif sonuçlar | Karar bekliyor |

**Makale minimum kapsamı:** C3, fiziksel kaynaklı senaryo ve belirsizliğin açık tanımı; bilinen tip sınıflandırması; en az bir karşılaştırılabilir klasik baseline; tutulan çalışma koşullarında değerlendirmenin grup bazında yapılması. C2/open-set büyük bir ikinci aşama olabilir; yalnızca başlıkta yer aldığı için yapılmış sayılmaz.

## 2. Risk kaydı

| Risk | Etki | Önlem |
|---|---|---|
| Nominal IBO'da “payload gap” istatistiksel olarak anlamsız | Çok yüksek | Sonucu dürüstçe raporla; false alarm ve ayırt edilemezlik için ön kayıtlı test |
| Gerçek GEO operatör verisi bulunamaması | Yüksek | “simülasyon + standart model + ölçülmüş SSPA domain shift” kapsamını açık tut |
| GaN SSPA'yı TWTA doğrulaması sayma | Yüksek | Ayrı hardware transfer testi; teknolojileri karıştırma |
| Plan metadata'sının ground truth sızıntısı | Yüksek | Yanlış/eksik plan testi, plandan etiketi doğrudan okumayı ayırma |
| Etiketlerin ölçülebilir olmaması | Çok yüksek | Gözlenebilirlik matrisi, birleşik/hiyerarşik çıktı, belirsiz olay bayrağı |
| Unknown setine eşiği uydurma | Yüksek | Validation / unknown holdout protokolünü dondur |
| Aynı RF seed/plan parçalarının veri bölünmesi | Yüksek | Group-split & seed bootstrap; örtüşme testi |
| Üçüncü taraf veri lisans ihlali | Yüksek | Orijinal URL + haklar kaydı, raw dosyaları GitHub'a kopyalamama |
| Compute/zaman kısıtı | Orta | Önce Stage A full ve üç eğitim tohumu, sonra seçilen B deneyleri |

## 3. Yayın stratejisi

Kesin hedef dergi veya kabul olasılığı belirtilmemiştir. Tamamlanan bilimsel katkının türüne göre IEEE Transactions on Aerospace and Electronic Systems (sistem/değerlendirme), IEEE Transactions on Machine Learning in Communications and Networking (öğrenme yöntemi) ve International Journal of Satellite Communications and Networking (uydu işletimi) **uygunluk açısından araştırılabilecek** yerlerdir. Aims & scope, güncel kurallar ve ücretler başvuru anında ayrı kontrol edilmelidir; burada bir editör kararı/uygunluk garantisi verilmez.

## 4. Gerçek tamamlanma kriteri

`docs/results/pilot_A.md` yalnız pipeline/pilot kanıtıdır; **tam benchmark sonucu gibi alıntılanmaz**. Manuscript için veri sürümü+hash+seed'ler, görünmeyen işletim koşulu, güven aralığı, koşullu yanlış alarm, bire bir baseline ve deney başına en az bir başarısızlık analizi gerekli.
