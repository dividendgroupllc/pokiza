# Pokiza Nazorat Tizimi — ERP + Telegram + AI (TZ 1-bosqich)

## Context
Rahbar (egasi) zavodni ERP'ga kirmasdan Telegram orqali nazorat qilmoqchi ("ERP TZ.docx"):
oylik / haftalik / kunlik ko'rsatkichlar, har birida reja vs fakt, % farq va yashil/sariq/qizil rang;
ertalab 08:00 da avtomatik hisobotlar, "batafsil" tugmalari, vazifalar bo'limi (berish, qabul/rad,
muddat), rahbar pul olganda darhol xabar. Bundan tashqari AI'ni (allaqachon qurilgan Pokiza AI chat)
Telegram'ga olib chiqish: shaxsiy chatda va bo'lim guruhlarida savolga javob berish, guruhlarga
hisobot va signal yozib turish.

Qabul qilingan qarorlar:
- **Alohida ichki bot** (rahbar + xodimlar). Hozirgi mijozlar boti (akt sverka, kassa xabarlari) o'zgarmaydi.
- **Guruhlarda AI bo'lim doirasida:** har guruhga bo'lim biriktiriladi, AI faqat shu bo'lim
  tool'lari va ma'lumoti bilan javob beradi. To'liq moliya (foyda, dividend, P&L) faqat rahbar DM'ida.
- Kod `pokiza` app ichida; AI logikasi (`pokiza/ai/`) qayta ishlatiladi, ikkinchi "miya" yozilmaydi.
- hamroh (MIT) — kod emas, faqat Telegram patternlari olinadi (pastda).

## Arxitektura

```
                    ┌──────────────── ERP (MariaDB) — yagona manba ────────────────┐
                    │ Sales/Purchase Invoice, GL, Kassa, Production Entry, Bin ... │
                    │ + yangi: Oylik Reja, Nazorat Sozlamalari, Vazifa, TG Chat    │
                    └───────────────▲──────────────────────────────▲───────────────┘
                                    │ faqat o'qish                  │ faqat tasdiqlangan amallar
              ┌─────────────────────┴───────────┐                   │ (vazifa yaratish/holati)
              │  KPI dvigateli  pokiza/nazorat/  │                   │
              │  metrics/*.py — A1..K4 funksiyalar│◄──── bitta manba: hisobot, panel, AI
              │  {fakt, reja, %, rang, trend, tafsilot}               │
              └───┬──────────────┬──────────────┬┘                   │
                  │              │              │                    │
   ┌──────────────▼───┐ ┌────────▼────────┐ ┌───▼────────────────────┴───────┐
   │ Hisobot builder  │ │ Rahbar paneli   │ │ Pokiza AI (agent.py, tool'lar)  │
   │ kunlik/haftalik/ │ │ /app/rahbar-    │ │ + get_kpi tool                  │
   │ oylik + grafik   │ │ paneli (trend)  │ │ + kanal: Web | Telegram          │
   │ (matplotlib PNG) │ └─────────────────┘ └───▲────────────────────────────┘
   └──────┬───────────┘                         │ enqueue (per-chat lock)
          │ scheduler 08:00 (cron)              │
   ┌──────▼─────────────────────────────────────┴──────────────────────────┐
   │ Telegram qatlami  pokiza/nazorat/tg/  (ichki bot, webhook + secret)    │
   │ router: DM rahbar | DM xodim | bo'lim guruhi │ callback tugmalar       │
   │ sender: text/HTML, photo, edit, chunking, rate limit, typing           │
   └───────────────────────────────────────────────────────────────────────┘
   Hodisalar: Kassa on_submit (Дивиденд 1/2/3) → rahbarga darhol xabar
```

Asosiy tamoyil: **har bir ko'rsatkich bitta joyda hisoblanadi** (`metrics/`). Telegram hisoboti,
web panel va AI bir xil funksiyani chaqiradi; shuning uchun raqamlar hamma joyda bir xil.

## 0-bosqich: ma'lumot tayyorlash (siz bilan birga, kodsiz hisobot noto'g'ri bo'ladi)
Tahlil natijasi: ko'p ko'rsatkichni hozir hisoblasa bo'ladi, lekin quyidagilar bazada yo'q:

| Kamchilik | Yechim | Kim |
|---|---|---|
| Reja (5 mlrd savdo, marja, 180 t, $50K) hech qayerda saqlanmaydi | Yangi doctype **Oylik Reja** | rahbar har oy kiritadi |
| Chegaralar (90/70%, 1pp, 7 kun, 25%, 10-sana); kurs — Currency Exchange'dan | **Nazorat Sozlamalari** (Single) | rahbar |
| Kategoriya (sosiska/kopchyonniy/varyonniy/delikates): sotuv SKU'lari hammasi bitta guruhda | Item'ga `custom_kategoriya` + bir martalik to'ldirish (norma bo'yicha taklif qilamiz) | biz + siz tasdiqlaysiz |
| Doimiy/o'zgaruvchi xarajat ajratilmagan | Account'ga `custom_xarajat_turi` (52xx hisoblarga bir marta) | biz + buxgalter |
| Mijoz kelishuvi (70/30, 10-sana) erkin matn, kartochkalar Qoralama | Mijoz Kartochkasi: `oldindan_foiz`, `tolov_kuni`, `oldingi_tovar_puli_sharti` + mavjud matndan avtomatik ko'chirish | biz + sotuv |
| Brak umuman kiritilmaydi (C4) | Jarayon: sex Brak Vozvrat / `brak_kg` kiritadi; hisobotda "kiritilmagan" deb ko'rsatiladi | sex |
| 22 ta donali SKU'da vazn yo'q (o'rtacha chek kg) | Item `weight_per_unit` to'ldirish | ombor |
| Dividend kimniki (Дивиденд 1/2/3) | Nazorat Sozlamalari'da 1/2/3 → shaxs nomi | rahbar |
| Kiritish kechikishi (3–6-noyabr fakturalar qoralama) | Kunlik hisobotda "tasdiqlanmagan hujjatlar" signali | avtomatik |

## 1-bosqich: KPI dvigateli (`pokiza/nazorat/metrics/`)
Har ko'rsatkich: `def a1_quvvat(davr) -> Metric(fakt, reja, foiz, rang, oldingi, trend[], tafsilot[], izoh, manba)`.
Registry (`metrics/__init__.py`) kod bo'yicha: A1–A5, B1–B4, C1–C6, D1, H1–H6, K1–K4.

Qayta ishlatiladi:
- Ishlab chiqarish: `pokiza/ai/tools/production.py` (`production_report`, `_work_days`, `_settings`, KG_UOMS)
- Qarz/kassa: `pokiza/ai/tools/business.py` (`get_party_balances`, `get_cash_balances`)
- Dividend: `pokiza/pokiza_for_business/doctype/kassa/kassa.py` (`DIVIDEND_ACCOUNT_NUMBERS`, `is_dividend_party_type`)
- Formulalar uchun namuna (import qilinmaydi, logika ko'chiriladi — dashboards alohida app, ba'zi
  funksiyalari bu saytda bo'sh): `apps/dashboards/.../page/main_dashboard/main_dashboard.py`
  (`_get_average_check_data`, `_get_margin_bonus_data`), `page_dashboard/data.py` (`get_client_kpi_rows`).

Hisob qoidalari (tahlildan): savdo = SI `base_net_total` docstatus=1 (qaytarish ayirilgan);
sof foyda = Income − barcha Expense GL (COGS SI'da `update_stock=1` bilan yoziladi); Stock Adjustment
shovqini alohida ko'rsatiladi; kg = faqat `stock_uom='кг'`; quvvat = PE fakti / (6900 × ish kunlari)
yoki 180 t; postavshik qoidasi = M oy xaridi vs M+1 oy 10-sanagacha to'lov; jim mijoz = oxirgi SI > 7 kun.

AI ga yangi tool `get_kpi(code, davr)` — AI ham shu raqamlardan foydalanadi.

## 2-bosqich: Ichki Telegram bot (`pokiza/nazorat/tg/`)
- Doctypes: **Nazorat Bot Sozlamalari** (token, webhook secret), **TG Chat** (chat_id, turi DM/guruh,
  bo'lim, ruxsat, AI yoqilgan, hisobot turlari), **TG A'zo** (telegram_id ↔ ERP **User**, rol).
- Bog'lash: xodim botga /start → bir martalik kod (ERP'da User sahifasida "Telegram ulash" tugmasi
  kod beradi) — telefon raqam bilan emas (xavfsizroq).
- Webhook: `allow_guest` endpoint + `X-Telegram-Bot-Api-Secret-Token` tekshiruvi, faqat ro'yxatdagi
  chat/user; update tez qabul qilinib `frappe.enqueue` ga beriladi. Lokal uchun polling (mavjud
  `pokiza/telegram/polling.py` namunasi).
- Sender: mavjud `pokiza/telegram/sender.py` uslubida (requests), qo'shiladi: sendPhoto,
  editMessageText, chatAction "typing", 4096 belgidan uzun matnni bo'lish, Markdown→Telegram HTML,
  429 flood limitda qayta urinish.
- Grafiklar: matplotlib (yangi dependency) → PNG (30 kun / 12 hafta / 12 oy trend).

## 3-bosqich: Rejali hisobotlar va signallar
- `hooks.py` `scheduler_events.cron`: `0 8 * * *` kunlik (K1–K4), `0 8 * * 1` haftalik (H1–H6),
  `0 8 1 * *` oylik (A–D hammasi). System Settings vaqt zonasi Asia/Tashkent bo'lishi shart.
- Format: qisqa matn, har qatorda 🟢🟡🔴 + fakt/reja/%; ostida inline tugmalar "Grafik", "Ro'yxat",
  "Tafsilot" (callback → shu metrikaning tafsiloti/PNG). Yuborilganlar log qilinadi (ikki marta ketmasin:
  claim → yubor → belgilash, hamroh reminder patterni).
- Bo'lim guruhlariga o'z ko'rsatkichlari (TZ "Mas'ullik taqsimoti"): Sotuv → savdo, jim mijozlar;
  Ishlab chiqarish → quvvat, brak; Buxgalteriya → debitorlik, postavshik, kassa; Ombor → qoldiq.
- Darhol signallar: Kassa `on_submit` Дивиденд 1/2/3 → rahbarga (C5/K4); kunlik oxirida
  "tasdiqlanmagan hujjatlar" va "7 kun jim mijozlar" (H4).

## 4-bosqich: Vazifalar (D1, H6)
- Doctype **Vazifa**: sarlavha, bo'lim, mas'ul (User), muddat, holat (Yangi → Qabul qilindi / Rad
  etildi → Bajarildi / Muddati o'tdi), rad sababi, izohlar, TG message id.
- Rahbar beradi: botda /vazifa (bosqichma-bosqich) yoki AI orqali tabiiy tilda ("Aliga juma kuni
  gacha ... vazifa ber") — AI **taklif qiladi**, rahbar "✅ Yaratish" tugmasini bosgandagina yoziladi.
- Xodimga tugmalar: "Qabul qilaman" / "Rad etaman (sabab)" / "Bajarildi". Rad etilsa rahbarga xabar.
- Eslatma: muddatdan 1 kun oldin va muddat o'tganda; D1 statistikasi oylik hisobotda.

## 5-bosqich: AI Telegram'da (mavjud `pokiza/ai` qayta ishlatiladi)
- `agent.run` kanalga bog'liqmas qilinadi: `Publisher` interfeysi — Web (hozirgi realtime) va
  Telegram (typing → yakuniy javob, kerak bo'lsa bo'lib yuborish, fayl/grafik sendDocument/sendPhoto).
  `AI Suhbat` ga `kanal`, `tg_chat` maydonlari. Ovoz → mavjud `pokiza/ai/voice.py` (Gemini).
- Job ERP user nomidan ishlaydi (`frappe.set_user(tg_azo.user)`), har chat uchun bitta navbat (lock).
- **Guruhda:** faqat @mention, botga reply yoki /so'ra buyrug'ida javob beradi; kontekst — guruhning
  oxirgi N xabari XML bilan (`<msg user time reply_to>` — hamroh `engine/format.py` patterni),
  kirish matni tozalanadi (zero-width/bidi — hamroh `input_normalizer`).
- **Bo'lim doirasi (kod darajasida, prompt emas):** `tool_specs()` ga `scope` beriladi — Sotuv guruhi:
  savdo/mijoz/qarz tool'lari, SQL faqat ruxsat jadvallari; Ishlab chiqarish: production tool'lari;
  moliya (P&L, dividend, foyda) faqat rahbar DM. Javob faqat shu chatga ketadi (`chat_id` AI'dan
  olinmaydi — hamroh'dagi chatlararo sizish xatosi takrorlanmaydi).
- AI hali ham **faqat o'qiydi** (READ ONLY guard saqlanadi); yagona yozish — tasdiq tugmali vazifa.
- Rate limit: user/kun va guruh/soat; oylik $ limit mavjud.

## 6-bosqich: Rahbar paneli (web)
`/app/rahbar-paneli` — shu metrikalar, rang, 30 kun/12 hafta/12 oy trend (frappe.Chart, AI chatdagi
dashboard komponentlari qayta ishlatiladi). Telegram "Batafsil" tugmasi shu sahifaga havola beradi.

## hamroh'dan olinadiganlar (MIT, mualliflik izohi bilan)
`utils/input_normalizer.py` (matn tozalash), `utils/formatting.py` (Markdown→TG HTML, chunking),
`engine/format.py` (guruh kontekstini XML), "skip with reason" (guruhda gapirmaslik qarori),
reminder claim/commit/revert, `rate_limiter.py` g'oyasi. **Olinmaydi:** Claude Code subprocess, umumiy
sessiya, SQLite xotira, polling-only, ixtiyoriy `chat_id`li send tool.

## Fayllar (yangi, asosiylari)
```
pokiza/nazorat/metrics/{__init__,ishlab_chiqarish,savdo,moliya,mijoz,vazifa}.py
pokiza/nazorat/reports.py            # kunlik/haftalik/oylik matn + tugmalar + grafik
pokiza/nazorat/charts.py             # matplotlib PNG
pokiza/nazorat/tg/{webhook,router,sender,callbacks,linking,format}.py
pokiza/nazorat/ai_channel.py         # Telegram Publisher + guruh konteksti + scope
pokiza/nazorat/events.py             # Kassa dividend signali
pokiza/pokiza_for_business/doctype/{oylik_reja,nazorat_sozlamalari,vazifa,tg_chat,tg_azo,nazorat_bot_sozlamalari}/
pokiza/pokiza_for_business/page/rahbar_paneli/
```
O'zgaradi: `pokiza/hooks.py` (scheduler_events, Kassa doc_events), `pokiza/ai/agent.py` (Publisher
interfeysi), `pokiza/ai/tools/__init__.py` (`tool_specs(scope)` + `get_kpi`), `pyproject.toml` (matplotlib),
`patches.txt` (custom fieldlar: Item kategoriya, Account xarajat turi, Mijoz Kartochkasi shartlari).

## Tekshirish
- KPI: har metrika uchun mustaqil SQL "oltin javob" bilan avtomatik test (oktabr: savdo 4 671 mln,
  quvvat ~151,5 t, o'rtacha chek ~26 700 so'm/kg, sof foyda ~874 mln) — `bench run-tests` / skript.
- Telegram: test guruhi + test bot; secretsiz webhook → 403; ro'yxatsiz chat → e'tiborsiz; bo'lim
  guruhida moliya savoli → rad; rahbar DM → javob; tugmalar callback; 08:00 cron'ni qo'lda chaqirish.
- Vazifa: yaratish → xodim qabul/rad → eslatma → muddati o'tdi holati.
- Dividend: test Kassa (Дивиденд 1) submit → rahbarga xabar ≤ 5 s.
- Xavfsizlik: mavjud 114 test + yangi (guruh scope, chat_id sizishi, tasdiqsiz yozish yo'qligi).

## Tartib va hajm (taxminiy)
0 → 1 → 2 → 3 (birinchi foydali natija: rahbarga 08:00 hisobot) → 4 → 5 → 6.
Har bosqichdan keyin lokal test, siz prod'ga chiqarasiz.

## Bajarilish holati
| Bosqich | Holat | Izoh |
|---|---|---|
| 1 — KPI dvigateli | ✅ lokal tayyor (2026-11-09) | Oylik Reja, Nazorat Sozlamalari, 19 ko'rsatkich, AI `get_kpi`. Tekshiruv: `bench --site pokiza.local execute pokiza.nazorat.metrics.tekshir.run --kwargs "{'davr':'2026-10'}"` |
| 0 — ma'lumot tayyorlash | ✅ kod tayyor (2026-11-09) | Item `custom_kategoriya`, Account `custom_xarajat_turi`, Mijoz Kartochkasi `tolov_foiz`/`tolov_kuni`/`oldingi_tovar_sharti` (patch `add_nazorat_fields` matndan ko'chiradi). Yangi KPI: B4, C1, C2, H5. Kategoriya/xarajat turi: `pokiza.nazorat.setup.taklif` → tekshirish → `qollash` |
| 2 — ichki Telegram bot | ✅ lokal tayyor (2026-11-09) | Nazorat Bot Sozlamalari, TG Azo, TG Chat; /kunlik /haftalik /oylik /kpi; guruh /ulash; webhook secret; lokal: `bench --site pokiza.local execute pokiza.nazorat.tg.polling.run` |
| 3 — rejali hisobot/signal | ✅ lokal tayyor | cron 08:00/dushanba/1-sana, Nazorat Yuborish jurnali (claim), kod tugmalari, matplotlib grafik, Kassa dividend on_submit/on_cancel, tasdiqlanmagan hujjatlar signali |
| 4 — vazifalar | ✅ lokal tayyor | Vazifa doctype (ruxsat: mas'ul/beruvchi), /vazifa ustasi, qabul/rad(sabab)/bajarildi, 09:00 eslatma va muddat nazorati, D1/H6 |
| 5 — AI Telegram'da | ✅ lokal tayyor | agent.run(publisher, kontekst), bo'lim doirasi tool_specs+run_tool+get_kpi, vazifa_taklif (tasdiq tugmasi), ovoz, guruh @mention/reply//sora, limitlar |
| 6 — rahbar paneli | ✅ lokal tayyor | /app/rahbar-paneli, pokiza.nazorat.panel (bir xil doira) |
| C6 | ✅ | sof foyda taqsimoti = dividend / sof foyda; TZ'dagi 26 kod hammasi qurildi |
