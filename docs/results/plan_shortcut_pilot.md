# Plan maskesi kısa yolu testi (A5) — pilot

Tarih 2026-10-20 · Komut: `python -m geoml.plan_shortcut --data data/pilot-a1 --runs runs/pilot-a1 --out runs/pilot-plan` ·
Ham sonuç: [plan_shortcut_pilot.json](plan_shortcut_pilot.json) · Checkpoint'ler: [R1 pilotu](r1_pilot.md) ile aynı
(tek eğitim tohumu, %6 veri). **Pilot; yön gösterir.**

## Yöntem

- **Model ve veri:** M-nl5, `test_id_nl` (149 örnek, 30 senaryo).
- **Ne değişir:** spektrumlar değişmez; yalnız plan maskesi, bozulmuş bir operatör planından `plan_mask_db` ile
  yeniden kurulur. Yeniden eğitim ve kalibrasyon yok.
- **Maske denetimi:** kaydedilmiş maskeler metadata planlarından en çok 0,015 dB farkla yeniden kuruluyor (float16).

| Bozma | Plan ne söylüyor | Gerçekte |
|---|---|---|
| `shift_plus` / `shift_minus` | her taşıyıcı 0,5 MHz kaymış (bayat plan; ≈ 2,7 izleme kutusu) | taşıyıcılar yerinde |
| `drop_one` | bir planlı taşıyıcı listede yok | taşıyıcı yayında |
| `phantom` | boş aralıkta fazladan bir taşıyıcı | o taşıyıcı yayında değil |
| `authorize_intruder` | yetkisiz taşıyıcı planda yetkili | yalnız `unauthorized` örnekleri |

## Sonuç

| Bozma | n | Doğruluk | Tahmini değişen | Temizde yanlış alarm | Unauthorized geri çağırma |
|---|---|---|---|---|---|
| yok | 149 | %85,2 (%80,5–%89,8) | — | %3,3 (n = 30) | %100 (n = 29) |
| `shift_plus` | 149 | %56,4 (%50,7–%62,2) | %48,3 | **%93,3** (%83,3–%100) | %79,3 |
| `shift_minus` | 149 | %51,7 (%45,0–%57,3) | %53,0 | **%93,3** (%83,3–%100) | %75,9 |
| `drop_one` | 139 | %35,3 | %64,7 | %100 (hepsi `unauthorized`) | %100 |
| `phantom` | 145 | %71,7 (%66,9–%76,6) | %22,8 | %37,9 (%20,7–%55,2) | %62,1 |
| `authorize_intruder` | 29 | %0 | %100 | — | %0 (27/29 `clean`) |

Karışıklık (eğitim tohumu 0, satır = gerçek etiket):

| Bozma | Temiz → | Diğer belirgin kaymalar |
|---|---|---|
| `shift_±` | `cw` 27/30 | aşırı sürme → `cw` 19/30; unauthorized → `cw` 6–7/29 |
| `drop_one` | `unauthorized` 28/28 | aşırı sürme → `unauthorized` 22/28; süpürülen CW → `unauthorized` 14/28 |
| `phantom` | `cw` 9/29 | unauthorized → `clean` 7/29 |

## Okuma

1. **Model planı istenen anlamda kullanıyor.** Operatör açısından planda olmayan yayın tanım gereği yetkisizdir:
   - `drop_one`'da temiz sahnelerin hepsine `unauthorized` demesi bu anlama uygun;
   - `authorize_intruder`'da yetkili sayılan taşıyıcıya `clean` demesi de öyle.
   Bu iki satır bir hata değil, plana koşullu karar verildiğinin kanıtıdır.
2. **Ama küçük plan hizasızlığına karşı kırılgan.**
   - 0,5 MHz'lik bayat plan (36 MHz'in %1,4'ü) temiz sahnelerin %93'ünü alarma çeviriyor; neredeyse hepsi `cw`.
   - Maske kenarının dışında kalan taşıyıcı kenarı dar bantlı girişim gibi okunuyor.
   - Aşırı sürme de `cw`'ye kayıyor (19/30). Model, IM'yi kısmen "maske kenarına göre fazla enerji" olarak tanıyor.
3. **Hayalet taşıyıcı daha ılımlı ama zararsız değil.** Temizde yanlış alarm %38. Yetkisiz taşıyıcıların
   %24'ü (7/29) `clean` sayılıyor.
4. **Sonuç ve öneri.** Plan maskesi güçlü ve gerekli bir girdi, ama hassas hizaya bağımlı. Gerçek operatör
   planlarında frekans hatası ve bayat kayıtlar olacağı için şu önerilir **[ÖNERİ; protokol değişikliği, A1'e
   değil B2/1'e]**:
   - eğitimde plan sapması artırımı (örneğin ±0,5 MHz kaydırma, eksik/fazla taşıyıcı);
   - ya da bozulmuş planlı ayrı bir değerlendirme kutusu.
   P18 §8 A5'e not edildi.

## Sınırlar

- **Eğitim ve veri:** tek eğitim tohumu, %6 veri. Aralıklar yalnız senaryo bootstrap'ı.
- **Kaydırma:** tek büyüklük (0,5 MHz) **[VARSAYIM]**; kayma büyüklüğüne göre eğri çıkarılmadı.
- **Kapsam:** yalnız tek-pol A1 checkpoint'leri. B2/1'de çift-pol maskelerle yinelenecek.
