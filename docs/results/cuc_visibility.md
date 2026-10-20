# Taşıyıcı altı taşıyıcının (CuC) spektrumdaki görünürlüğü

Tarih 2026-10-20 · Komut: `python scripts/cuc_visibility.py --out docs/results/cuc_visibility.json` ·
Ham sonuç: [cuc_visibility.json](cuc_visibility.json) · Amaç: P18 (K17) CuC C/I aralığına ölçülmüş dayanak.

**Yöntem**
- **Zincir:** tek polarizasyonlu A1 zinciri (DVB-S2 H.3 TWTA), 36 MHz.
- **Sabit link:** IBO 11 dB, uplink ve downlink C/N 25 dB (A1 aralıklarının ortası, **[VARSAYIM]**).
- **Senaryolar:** 24 senaryo tohumu (600000–600023; hiçbir veri protokolüyle çakışmaz).
- **Olay:** her tohumda E1 üreteciyle tek bir CuC yerleşimi. C/I düzeylerinde yalnız olayın gücü değişir.
- **Ölçü:** ΔPSD = CuC bandında, olaylı ve olaysız zaman ortalamalı PSD oranı. Taşıyıcılar ve gürültü akışları
  aynı olduğundan bu eşleşmiş fark bir **üst sınırdır**: operatörün olaysız bir ikizi yoktur.
- **Gürültü:** σ = 128 anlık görüntüden bant ortalamasının 1σ tahmin gürültüsü.
- **Bant genişliği:** CuC bandı ortanca 13, en az 6, en çok 69 izleme kutusu (187,5 kHz).

| C/I (toplam plana göre) | Kurbana göre C/I (ortanca) | ΔPSD ortanca | ΔPSD %10–%90 | 3σ | ΔPSD > 3σ | > 0,5 dB | > 1 dB |
|---|---|---|---|---|---|---|---|
| 5 dB | −2,5 dB | 5,64 dB | 1,83–8,27 dB | 0,053 dB | %100 | %100 | %100 |
| 10 dB | 2,5 dB | 2,74 dB | 0,70–4,60 dB | 0,053 dB | %100 | %96 | %83 |
| 15 dB | 7,5 dB | 1,08 dB | 0,24–2,03 dB | 0,053 dB | %100 | %71 | %54 |
| 20 dB | 12,5 dB | 0,37 dB | 0,08–0,75 dB | 0,053 dB | %100 | %25 | %4 |
| 25 dB | 17,5 dB | 0,12 dB | 0,03–0,25 dB | 0,053 dB | %88 | %0 | %0 |
| 30 dB | 22,5 dB | 0,04 dB | 0,01–0,08 dB | 0,053 dB | %17 | %0 | %0 |

## Yorum

1. **Kâhin bilgisiyle bile C/I 30 dB'de görünmez.** Olaysız ikiz bilinse bile C/I 30 dB'de olayların yalnız
   %17'si tahmin gürültüsünün üstünde kalıyor.
2. **Gerçek gözlemde eşik çok daha erken.** Gözlemci ikize değil planın beklenen seviyesine bakar. Taşıyıcı EIRP'si,
   IMUX/OMUX dalgalanması ve TWTA sıkışması yüzünden bu seviyenin belirsizliği 0,5–1 dB mertebesindedir
   **[VARSAYIM; ölçülmedi]**. Bu belirsizlikte CuC ancak C/I ≲ 15 dB'de spektrumdan seçilebilir. 20–25 dB'de
   PSD tek başına yetersizdir. Taramanın "PSD'den CuC beklenmemeli" uyarısıyla (P16 L11) uyumlu; K9'un ek
   gözlem kanalı (iptal artığı, SCF) bu bölge için gerekli.
3. **P18 için öneri.** CuC C/I aralığı 5–30 dB olsun (taslakta 5–25 dB). Böylece görünür → görünmez geçişin
   tamamı kapsanır ve ayırt edilebilirlik eğrisi uçlardan sabitlenir. C/I kutuları 5–15, 15–25, 25–30 dB.
   Karar K17'de kullanıcıda.

## Sınırlar

Tek link noktası (IBO 11 dB, C/N 25 dB); tek polarizasyon; tek TWTA; faz gürültüsü yok. Ölçü eşleşmiş farka
dayanır; plan seviyesi belirsizliği simüle edilmedi. CID metacarrier'ın −27,5 dB referansıyla doğrudan
karşılaştırma yapılmadı **[DOĞRULANACAK]**.
