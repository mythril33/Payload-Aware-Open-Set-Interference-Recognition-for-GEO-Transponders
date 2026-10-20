# OpenDPD ölçülmüş PA verisi — ön inceleme (sonda)

Tarih 2026-10-20 · Amaç: P15 K11 ("ölçüm aralığında kullan") kararından önce
OpenDPD verisinin projeye ne verebileceğini görmek. **Keşif amaçlı bir sondadır;
bir yükselteç modeli veya deney sonucu değildir.**

## Kaynak (bu oturumda doğrulandı)

- Depo: <https://github.com/lab-emi/OpenDPD>, commit `cb4c5ea40632a977f2725575534d3f062fcbb652` (2026-10-16). Lisans: depo **Apache-2.0**; veri setlerinin ayrı lisansı belirtilmemiş, atıf OpenDPD makaleleri üzerinden isteniyor (`docs/community/citation.md`).
- Ham CSV'ler depomuza **kopyalanmadı**; bulut kabında geçici klonlandı.

| Veri | Cihaz (OpenDPD belgelerine göre) | Sinyal | fs | Örnek (train/test) | Giriş PAPR |
|---|---|---|---|---|---|
| APA_200MHz | Ampleon **GaN Doherty** PA, 3,5 GHz, 41,5 dBm ort. çıkış | 5 × 20 MHz LTE TM3.1a, 256QAM, 200 MHz | 983,04 MHz | 58 980 / 19 662 | 10,0 dB |
| APA_200MHz_b | Aynı cihaz, ikinci ölçüm | aynı | aynı | aynı | 10,0 dB |
| DPA_200MHz | 40 nm CMOS dijital **Doherty** verici, 2,4 GHz | 10 × 20 MHz, 64QAM | 800 MHz | 23 040 / 7 680 | 9,2 dB |
| DPA_160MHz | aynı aile | 4 × 40 MHz, 1024QAM | 640 MHz | 294 912 / 98 304 | 10,3 dB |

Belgelerde adı geçen DPA_100MHz bu commit'te yok. Train-input SHA-256 değerleri
`scripts/opendpd_probe.py` çıktısındadır (APA ve APA_b aynı giriş dosyasını
kullanıyor: `2ca703c9e7eb…`).

## Ölçüm

Komut (OpenDPD, Git dışında `data/external/opendpd` altına klonlanmış olmalı):

```bash
python scripts/opendpd_probe.py data/external/opendpd/datasets/{APA_200MHz,APA_200MHz_b,DPA_200MHz,DPA_160MHz}
```

En küçük kareler uydurması train bölümünde, NMSE test bölümünde (dB, düşük daha iyi).
ΔG ve AM/PM, belleksiz K=5 uydurmasında 99. yüzdelik giriş genliğinin ortancaya göre değeridir.

| Veri | Doğrusal kazanç | Doğrusal FIR (M=8) | Belleksiz K=5 | Bellek polinomu K=5, M=4 | K=5, M=8 | ΔG (p99/ortanca) | AM/PM |
|---|---|---|---|---|---|---|---|
| APA_200MHz | −19,7 | −21,5 | −22,2 | **−29,8** | −26,5 | −0,35 dB | −11,5° |
| APA_200MHz_b | −18,8 | −17,1 | −21,0 | **−26,7** | −18,8 | −0,22 dB | −12,1° |
| DPA_200MHz | −19,8 | −25,6 | −20,8 | −30,0 | **−31,2** | −0,78 dB | +3,0° |
| DPA_160MHz | −19,3 | −29,0 | −19,7 | −37,3 | **−38,1** | −0,56 dB | +2,5° |

## Yorum ve sınırlar

1. **Sıkışma zayıf.** Ölçümler DPD çalışma noktalarında alınmış; 99. yüzdelikte kazanç kaybı yalnız 0,2–0,8 dB. Bizim aşırı sürme bölgemiz (TWTA, IBO 0–5 dB) bu ölçümlerin çok dışında. K11 kararı bu yüzden doğru: OpenDPD yalnız **nominal IBO** testinde kullanılır, aşırı sürmede kullanılmaz.
2. **Bellek etkisi belirgin.** Belleksiz modele göre bellek polinomu 5,7–18,4 dB daha iyi. DPA'da bu kazancın büyük kısmı **doğrusal** frekans tepkisinden geliyor (DPA_160: doğrusal FIR −29,0 dB); doğrusal olmayan bellek bunun üstüne 5,6–9,1 dB daha ekliyor. APA'da belleksiz doğrusalsızlık 2,5 dB, bellekli doğrusalsızlık 7,6 dB daha ekliyor.
3. **Model derecesi doğrulama bölümünde seçilmeli.** APA'da M=8, M=4'ten kötü (APA_b'de doğrusal kazanç düzeyine iniyor): aşırı uyum veya bölümler arası koşul farkı. Bu sonda test bölümüne baktı; türetilecek modelin derecesi **yalnız val bölümünde** seçilecek ve bu tablo seçim için kullanılmayacak.
4. **AM/PM işareti cihaza göre değişiyor** (GaN Doherty −12°, CMOS Doherty +3°). DVB-S2 referans TWTA'sının AM/PM'i ise doyumda onlarca derece (`DURUM` §4). Ölçülmüş PA'lar TWTA'dan **nitelik olarak farklı** bir yükselteç ailesi sağlıyor; "TWTA doğrulaması" diye sunulamaz.
5. **Bant ve frekans uyumsuzluğu.** Ölçümler 160–200 MHz sinyal, 2,4/3,5 GHz; bizim transponder 36/72 MHz, Ku. Belleği bant genişliğine ölçeklemek **[VARSAYIM]**dır ve türetme belgesinde ayrıca test edilecek.

## Sonraki adım (P15 İP-2)

`geosim.payload`'a ek seçenek olarak val bölümünde derecesi seçilmiş bellek
polinomu; katsayılar + kaynak commit + SHA-256 + Apache-2.0 atıf notu ile; A1
çıktısının değişmediğini gösteren regresyon testi; R1-eval/1'de `test_amp_opendpd_apa`
ve `test_amp_opendpd_dpa`.
