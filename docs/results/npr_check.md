# NPR kontrolü — yükselteç aileleri (P16 İP-2, B11)

Tarih 2026-10-20 · Komut: `python scripts/npr_check.py --out docs/results/npr_check.json` · Ham sonuç: [npr_check.json](npr_check.json).

**Yöntem:**
- Yükselteç tek başına sürülür (IMUX/OMUX yok).
- Sürücü sinyal: karmaşık Gauss gürültüsü, 32 MHz banda sınırlı, 2–3 MHz arasında çentikli.
- Bant genişliği, çentik konumu ve koruma payı **[VARSAYIM]**dır.
- IBO tanımı zincirle aynıdır: sabit kazanç, tek taşıyıcı doyumuna göre.
- NPR = çentik dışındaki bant içi PSD ortalaması / çentik merkezindeki PSD ortalaması.
- 2¹⁹ örnek, Welch 4096, tohum 0.
- Ölçüm tabanı: girişin çentik derinliği 53,6 dB; doğrusal zincirde de 53,6 dB.

## NPR (dB), IBO'ya göre

| IBO (dB) | 0 | 2 | 4 | 6 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | Eğim 10–14 dB (dB/dB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dvbs2_nl` (H.3 TWTA) | 8,5 | 9,5 | 10,7 | 12,1 | 13,8 | 14,7 | 15,7 | 16,8 | 18,0 | 19,3 | 20,7 | 1,25 |
| `dvbs2_lin` (H.2 doğrusallaştırılmış) | 8,8 | 10,5 | 12,4 | 14,8 | 18,1 | 20,1 | 22,2 | 23,7 | 23,8 | 22,8 | 21,8 | −0,17 |
| `saleh` | 9,4 | 11,0 | 12,9 | 14,9 | 17,1 | 18,1 | 19,1 | 20,1 | 21,1 | 22,1 | 23,1 | 0,98 |
| `rapp_p2` | 14,5 | 17,0 | 20,3 | 24,5 | 29,7 | 32,7 | 35,9 | 39,1 | 42,5 | 45,7 | 48,6 | 3,21 |
| `opendpd_apa`* | 24,5 | 21,3 | 19,2 | 18,8 | 20,0 | 21,0 | 22,1 | 23,4 | 24,6 | 26,0 | 27,6 | 1,35 |
| `opendpd_dpa`* | 26,7 | 23,3 | 21,3 | 21,0 | 22,9 | 24,6 | 26,9 | 29,5 | 32,4 | 35,1 | 37,8 | 2,74 |

\* Ölçüm aralığı dışındaki sürücü örneklerinin oranı:

| IBO (dB) | 0 | 4 | 6 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|
| APA | 0,45 | 0,14 | 0,043 | 6,8·10⁻³ | 1,9·10⁻³ | 3,7·10⁻⁴ | 6,5·10⁻⁵ | 1,3·10⁻⁵ | 0 |
| DPA | 0,52 | 0,19 | 0,072 | 0,015 | 5,2·10⁻³ | 1,4·10⁻³ | 2,3·10⁻⁴ | 4,8·10⁻⁵ | 7,6·10⁻⁶ |

Gauss gürültüsünün tepe/ortalama oranı, çok taşıyıcılı yükünkinden yüksektir. Bu yüzden oranlar R1 senaryolarında ölçülenlerden büyük.

## Yorum

1. **TWTA eğimi bağımsız ölçümle tutarlı.** `dvbs2_nl` için NPR eğimi IBO 10–14 dB'de 1,25 dB/dB. Bu değer, P2 §10'da çok taşıyıcılı yükle ölçülen C/IM eğimiyle (1,25 dB/dB) aynı. Küçük sinyalde üçüncü derece ürünler için beklenen asimptot 2 dB/dB'dir; tüp bu aralıkta henüz küçük sinyal bölgesinde değildir.
2. **Rapp beklenen dereceyi gösteriyor.** p = 2'de kazanç ≈ 1 − r⁴/4; ilk bozulma terimi beşinci derecedir. Eğim 3,2 dB/dB ve 4 dB/dB asimptotuna doğru artıyor. Nominal IBO'da Rapp, TWTA'dan çok daha doğrusaldır (IBO 11'de 39 dB'ye karşı 17 dB).
3. **`dvbs2_lin` için bozulma tabanı.** Doğrusallaştırılmış TWTA'nın NPR'si IBO 12 dB'de ≈ 23,8 dB ile en yükseğe çıkıyor, sonra geri çekilme arttıkça **düşüyor**. Sayısallaştırılmış H.2 eğrisi seyrek, fazı basamaklı (DURUM §5.5); bu, düşük sürüşte yapay bir bozulma tabanı yaratır. `test_amp_lin` sonuçlarında IBO ≥ 12 dB bölgesinin bozulması model artefaktı olabilir. Bu ayrıca not edilmeli.
4. **OpenDPD ölçüm aralığı dışında güvenilmez (K11 doğrulandı).** IBO ≤ 6 dB'de sürücünün %4–52'si ölçülen en büyük genliğin üstündedir. Kırpma, kenar kazancını sabit tuttuğu için bozulma eksik gösterilir ve NPR yapay olarak *yükselir*. Bu yüzden OpenDPD'li R1 bölünmeleri aşırı sürme içermez.
5. **Nominal IBO'da ölçülmüş PA'lar TWTA'dan daha doğrusal.** IBO 9–13 dB'de APA 21–26 dB, DPA 25–35 dB, `dvbs2_nl` ise 15–19 dB. Bu karşılaştırma `OPENDPD_IBO_REF_DB = 11` eşlemesine bağlıdır **[VARSAYIM]**. R1'de bu cihazlarla görülen bir yük farkı, daha *az* IM'ye karşı sağlamlık olarak okunmalıdır.

## Sınırlar

- Literatürdeki TWTA NPR değerleriyle **sayısal karşılaştırma yapılmadı**; tarama kaynağı (ResearchGate 349494998) birincil kaynaktan okunmadı **[DOĞRULANACAK]**.
- Tek tohum ve tek çentik konumu kullanıldı. Çentiğin bant kenarına yakınlığı ve IMUX/OMUX etkisi ölçülmedi.
