# Open-set ve işletim koşulu genelleme protokolü (Kademe B önerisi)

Durum: **ÖNERİ — HENÜZ KODLANMADI** · 2026-10-20. Mevcut repo Kademe A: beş sınıf / tek pol / kapalı-küme. Bu belge gelecekteki sekiz sınıflı çalışmayı tarif eder; deney sonucu değildir.

Geliştirme güncellemesi: B1-dev/1–2 açık-küme skorları/unknown aileleri ve
[D1-dev/1 çift-pol geliştirme hattı](../plan/P14_dual_polarization.md) artık
kodlanmıştır. Buradaki **nihai sekiz sınıflı benchmark önerisi** henüz tamamlanmış
bir uygulama veya deney sonucu değildir.

## 1. Sınıflar ve gözlenebilirlik

Bilinen hedefler: `clean`, `cw`, `swept_cw`, `cross_pol`, `adjacent_satellite`, `unauthorized`, `carrier_under_carrier`, `overdrive_im`.
İlk unknown aileleri: `pulsed`, `wideband_noise`, `intermittent_bursts`. Süre/occupancy parametreleriyle pulse ve burst tanımlarını örtüşmez yap; ayrıca bilinen 7 türden her birini sıra ile tutup “bilinmeyen” yaparak leave-one-class-out raporla.

| Görev ayrımı | Co-pol PSD | Cross-pol PSD | Plan maskesi | Zamansal IQ / ekstra bilgi |
|---|---|---|---|---|
| clean vs CW | çoğu durumda evet | yararlı olabilir | taşıyıcı maskesini kullan | zayıf taşıyıcı üstü CW için yararlı |
| cross-pol leakage | çoğu kez yetersiz | **gerekli**, ancak tek başına her zaman yeterli değil | yararlı | XPD kalibrasyonu gerekir |
| unauthorized vs planned | tek başına yetersiz | tek başına yetersiz | **gerekli**, ama güncel/eksiksiz olmalı | yetkilendirme metadata'sı gerekir |
| adjacent-satellite vs başka modüleli taşıyıcı | genellikle yetersiz | yardımcı | yararlı ama kesin değil | yörünge/anten/geolokasyon veya yön bilgisi gerekebilir |
| carrier-under-carrier | toplam spektrumda gömülebilir | yardımcı | yardımcı | döngüsel istatistik/demodülasyon faydalı olabilir |
| overdrive IM vs dış girişim | yalnız PSD ile karışabilir | yardımcı | plan ve IBO yardımcı | çok taşıyıcılı doğrusal olmayan zincir modeli kritik |

**İlke:** Ölçümlerin aynı olduğu iki fiziksel sebebi sinir ağı kesin olarak ayıramaz. Gerektiğinde birleşik `unresolved_modulated_interference` etiketi veya çok-etiket/hiyerarşik karar üretilmeli; ground-truth sebep çıkarımı için yetkilendirme/yön bilgisi gerekliliği raporlanmalı.

## 2. Veri ve split

- Her `scenario_id` aynı **carrier plan + gürültü + yük + tarih/ölçüm oturumu** kümesinden türeyen örnekleri kapsar. Aynı grup train, validation, test arasında bölünmez.
- In-distribution / known: yerleşik carrier sayısı, bant, IBO, TWTA/OMUX, XPD ve plan belirsizliğini koru.
- Koşul-dışı testler: görülmeyen IBO, 36→72 MHz, carrier loading, farklı PA eğrisi, plan eksik/kayık, XPD kayması, farklı receiver NF, burst duty cycle.
- Unknown-class testleri: üç aile ayrı ayrı ve bileşik test; **leave-one-known-class-out** rotasyonu. Bilinmeyenleri eğitimde veya doğrulamada leakage yaratacak şekilde kullanma.
- Validation: yalnızca izin verilen ID ve varsa *ayrı tanımlanmış surrogate unknown*; asıl unknown test aileleri ile eşik ayarlanmaz.
- Sistematik protokol değişikliğinde `docs/plan/P5_veri_protokol.md` Kademe A donmuş A1 sürümünü **değiştirme**; B1 adıyla ayrı veri protokolü sürümü oluştur.

## 3. Skorlar ve eşikler

Model bilinen-küme logits'leri `z_k` ve feature vektörü `f(x)` için:

- MSP: `s_ID=max(softmax(z))`.
- Energy: `E(x)=-T log(sum_k exp(z_k/T))`; bilinmeyen için **yüksek enerji** genellikle düşük ID güveniyle ilişkilidir. Uygulamada skor yönünü testle doğrula.
- Mahalanobis: `d(x)=min_k (f(x)-mu_k)^T Sigma^{-1}(f(x)-mu_k)`; `mu_k` ve kovaryans yalnız eğitimden hesaplanır; küçük örnekte düzenlileştirme gerekir.
- En az bir eğitim-zamanı open-set karşılaştırması düşün: surrogate-negative exposure veya mesafe temelli kayıp. Asıl held-out türleri eğitimde göstermeden dene.

Eşikler **yalnızca validation** üzerinde sabitlenir. İstenen ID kabul oranı ve ID sınıflandırma hatasıyla birlikte bildir; test setinde eşiği optimize etme. Kontrollü ikincil baseline olarak CFAR ve plan-conditioned CFAR tut.

## 4. Raporlama

| Sonuç | Tanım |
|---|---|
| Known-class macro-F1 | Unknown'ları zorla bilinene atamadan önce ve reddetme sonrası *ayrı* |
| Unknown-vs-known AUROC / AUPR | Holdout-family başına; bilinen ve bilinmeyen olayların oranlarını açıkla |
| OSCR eğrisi / AUC | Doğru bilinen sınıflandırma oranı ile bilinmeyenin yanlış kabul oranının ortak trade-off'u |
| FPR@95% TPR | **TPR'nin bilineni kabul mü yoksa bilinmeyeni bulma mı olduğu** açık olsun |
| Sabit ID false alarmda `P_d` | C/I **ve** I/N / INR, girişimci bandwidth/duty cycle, sınıf/çalışma noktası |
| Operasyon maliyeti | Model parametreleri, FLOPs, CPU/GPU ms/frame, sensor zaman-frekans çözünürlüğü |
| İstatistik | Scenario ID düzeyinde bootstrap ve farklı eğitim tohumları; güven aralıkları |

## 5. Hata analizleri ve ablasyonlar

A0 co-pol only; A1 + doğru plan; A2 + dual-pol; A3 + payload nonlinearity; A4 + cyclic; A5 plan yanlış/eksik; A6 ölçülmüş SSPA transferi; A7 CNN/transformer; A8 unknown-family ve leave-one-known-out. Her ablasyon **tek bir değişkeni** değiştirsin; veri, eğitim bütçesi, eşik seçimi ve seed protokolü eşit olsun. Bağımsız gözlemle test edilmeyen her “payload gap” etkisini simülatör içi olarak raporla.

Temel yöntem referansları: [Hendrycks–Gimpel 2017](https://arxiv.org/abs/1610.02136), [Lee ve ark. 2018](https://proceedings.neurips.cc/paper_files/paper/2018/hash/abdeb6f575ac5c6676b747bca8d09cc2-Abstract.html), [Dhamija ve ark. 2018](https://arxiv.org/abs/1811.04110), [Liu ve ark. 2020](https://papers.neurips.cc/paper_files/paper/2020/hash/f5496252609c43eb8a3d147ab9b9c006-Abstract.html).
