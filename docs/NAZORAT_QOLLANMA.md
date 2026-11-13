# Pokiza Nazorat tizimi — qo'llanma va sinov

Har bo'limda avval **tizim nima qilishi** tushuntiriladi, keyin **sinov jadvali** keladi: qadam va
kutilgan natija. Natija mos kelsa ✅ qo'ying. Mos kelmasa, sinov raqamini (masalan **5.3**) va
skrinshot yoki xato matnini yuboring.

**Mundarija**
1. Tizim haqida
2. Ishga tushirish
3. Sozlamalar
4. Ko'rsatkichlar
5. AI chat (web)
6. Nazorat boti va ulanish
7. Rahbar: hisobotlar, tugmalar, grafik, dividend
8. Rollar: kim nimani ko'radi
9. Bot faqat shaxsiy chatda
10. Vazifalar
11. AI Telegram'da
12. Rahbar paneli
13. Avtomatik ishlar
14. Xavfsizlik
15. Ma'lumot sifati
16. Oylik mijoz hisoboti (PDF)
17. Prod'ga chiqarish

---

## 1. Tizim haqida

Rahbar zavodni ERP'ga kirmasdan, Telegram orqali nazorat qiladi. Barcha raqamlar ERP'dan avtomatik
olinadi. Har bir ko'rsatkich **bitta joyda** hisoblanadi, shuning uchun Telegram hisobotida, rahbar
panelida va AI javobida bir xil raqam chiqadi.

Har ko'rsatkichda:
- **fakt**: nima bo'ldi;
- **reja** va bajarilish %;
- **oldingi davr** bilan solishtirish (↑ / ↓ %);
- **rang**: 🟢 yaxshi · 🟡 diqqat · 🔴 yomon · ▫️ rangsiz (reja kiritilmagan yoki rang kerak emas).

Foydalanuvchi hamma joyda ko'rsatkichni **nomi bilan** ko'radi: "Savdo", "Quvvat", "Debitorlik"…
Telegram'da, rahbar panelida va AI javobida hech qanday ichki kod (harf-raqam) chiqmaydi.

| Qism | Qayerda | Kim ishlatadi |
|---|---|---|
| Nazorat boti | Telegram (alohida ichki bot), shaxsiy chat | Rahbar, xodimlar |
| Rahbar paneli | ERP → `/app/rahbar-paneli` | Rahbar, bo'lim boshliqlari |
| Pokiza AI | ERP → `/app/pokiza-ai` va Telegram | Rahbar, ruxsat berilgan xodimlar |
| Sozlamalar | ERP: Nazorat Sozlamalari, Oylik Reja, Nazorat Bot Sozlamalari, TG Azo, TG Chat | Administrator |

Mijozlarga akt sverka yuboradigan eski bot o'zgarmagan. Nazorat boti undan butunlay alohida.

---

## 2. Ishga tushirish

- **Terminal 1:** `cd ~/frappe-bench-15 && bench start`. Bu buyruq web'ni, worker'larni va
  scheduler'ni ishga tushiradi. AI javoblari va vazifa xabarlari worker orqali ketadi.
- **Kod o'zgargandan keyin** worker'lar yangilanishi uchun Ctrl+C bosing va yana `bench start` qiling.
- **ERP'ga kirish:** brauzerda `http://localhost:8001`. **Administrator emas, oddiy foydalanuvchi**
  bilan ham kira oladigan bo'ling: Administrator Telegram'ga ulana olmaydi, bu xavfsizlik uchun
  shunday qilingan.

---

## 3. Sozlamalar

**Nima uchun kerak:** reja va chegaralarsiz tizim faqat faktni ko'rsatadi, rang va bajarilish foizi
chiqmaydi.

| Sahifa | Nima saqlanadi |
|---|---|
| **Nazorat Sozlamalari** | Rang chegaralari (quvvat 90/70%, savdo 95/85%, rentabellik 1 pp, $50K/$40K), to'liq quvvat 180 t, jimlik 7 kun, bitta mijoz ulushi 25%, postavshik to'lov kuni 10, Дивиденд 1/2/3 kimga tegishli. **"Qo'shimcha ko'rsatkichlar ranglari"** bo'limida: mijoz rentabelligi, mijoz dinamikasi, top mahsulotlar, kategoriyalar, xarajatlar, brak, dividend va foyda taqsimoti chegaralari |
| **Oylik Reja** | Har oy boshida rahbar kiritadi: savdo, sof rentabellik %, tonna, $ maqsad. Oy yakunida **"Foyda ishlatilishi"** jadvali: sof foyda dividenddan tashqari nimalarga ketgani (uskuna, qarz, zaxira…). Sahifani faqat administrator va Accounts Manager ko'radi |
| **Currency Exchange** (ERPNext) | USD→UZS kursi. Sof daromad ($) shu yerdagi eng so'nggi kurs bilan hisoblanadi. Kurs boshqa joyda kiritilmaydi |
| **Mijoz Kartochkasi** | To'lov sharti: yopiladigan % (70/30 dagi 70), to'lov kuni (20), "keyingi tovardan oldin oldingisini yopadi" belgisi. Eski "70/30 20-SANA" matni avtomatik ko'chirilgan |
| **Item** | "Kategoriya (nazorat)": sosiska, kopchyonniy, varyonniy, delikates, boshqa |
| **Account** | "Xarajat turi (nazorat)": doimiy yoki o'zgaruvchi |

**Kategoriya va xarajat turini to'ldirish.** Tizim mahsulot va hisob nomlaridan taklif tuzib qo'ygan:
`~/Downloads/nazorat_taklif.xlsx`. Siz tekshirib, kerak bo'lsa tuzatasiz, keyin bitta buyruq bilan
yozasiz. Bunda faqat bo'sh maydonlar to'ldiriladi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 3.1 | **Nazorat Sozlamalari**ni oching | Chegaralar to'ldirilgan, kurs maydoni yo'q |
| 3.2 | **Currency Exchange** → bugungi USD→UZS kursi | Saqlanadi (oxirgi kurs 02.09.2026 da kiritilgan) |
| 3.3 | **Oylik Reja** → New: 2026 / 10 — savdo 5 000 000 000, rentabellik 20, tonna 180, $ 50 000. Xuddi shunday 2026 / 11 | `REJA-2026-10`, `REJA-2026-11` |
| 3.4 | Oylik Reja: savdoni 0 qilib saqlashga urining | Xato: "0 dan katta bo'lishi kerak" |
| 3.5 | **Mijoz Kartochkasi** → ЧП Жамилов Жонибек | 70% / 20-sana to'lgan |
| 3.6 | Kartochkada to'lov kunini 40 qilib saqlang | Xato: 0..28 |
| 3.7 | Excel'ni tekshirib saqlang, keyin: `bench --site pokiza.local execute pokiza.nazorat.setup.qollash --kwargs "{'fayl': '/home/sardorbek/Downloads/nazorat_taklif.xlsx'}"` | "Yozildi: N mahsulot kategoriyasi, M xarajat turi" |
| 3.8 | Item va Account'ni oching | Kategoriya va xarajat turi ko'rinadi |

---

## 4. Ko'rsatkichlar

TZ bo'yicha 26 ta ko'rsatkich bor. Ularning hammasi bitta "KPI dvigateli"da hisoblanadi.

### Oylik (oyning 1-sanasida, o'tgan oy uchun)

**Strategik fokus**
| Ko'rsatkich | Qanday hisoblanadi |
|---|---|
| Quvvatdan foydalanish | Ishlab chiqarilgan tonna / to'liq quvvat 180 t. Oylik Reja'da tonna bo'lsa, "rejaning X%" alohida qator |
| Savdo | Tasdiqlangan sotuv fakturalari (qaytarishlar ayirilgan) / oylik reja |
| Sof rentabellik | Sof foyda / savdo. Rejada va yuqori — yashil, rejadan 1 pp gacha past — sariq, undan past — qizil |
| O'rtacha chek | Kg'dagi savdo / sotilgan kg. Donali mahsulotlar Item'dagi vazn (Weight Per Unit) bilan kiradi. Rang: o'sdi / o'zgarmadi / tushdi |
| Sof daromad ($) | Sof foyda / Currency Exchange'dagi kurs. Maqsad $50K |

**Mijozlar va sotish**
| Ko'rsatkich | Qanday hisoblanadi |
|---|---|
| Mijoz rentabelligi | Har mijoz: savdo − tannarx − bonus. Eng pastlari birinchi |
| Mijoz dinamikasi | Kim o'sdi, kim tushdi (o'tgan oyga nisbatan) |
| Top mahsulotlar | Daromadning 50% ini beradigan mahsulotlar |
| Kategoriyalar | Sosiska / kopchyonniy / varyonniy / delikates: ulushi va marjasi |

**Moliya va to'lovlar**
| Ko'rsatkich | Qanday hisoblanadi |
|---|---|
| Postavshiklarga to'lov | O'tgan oy xaridi keyingi oyning 10-sanasigacha yopildimi (ortiqcha ham, kam ham emas). Yakuniy holat **11-sanada** alohida xabar bilan keladi |
| Debitorlik (mijozlardan to'lov) | Kelishuv (70/30, sana) bo'yicha: kim buzdi, kim qancha to'lashi kerak |
| Xarajatlar | Xarajat / savdo, doimiy va o'zgaruvchi alohida |
| Brak va vozvrat | Brak kg («Brak» oynasidan yozilgan Material Issue, «Брак» hisobi) / ishlab chiqarilgan kg; qaytgan tovar |
| Dividend | Rahbar olgan pul: kim, qancha, qachon |
| Sof foyda taqsimoti | Foyda: dividend + Oylik Reja'dagi "Foyda ishlatilishi" + oborotda qolgani |

**Vazifalar**
| Ko'rsatkich | Qanday hisoblanadi |
|---|---|
| Vazifalar bajarilishi | Har xodim: jami — bajarilgan — bajarilmagan |

### Haftalik (dushanba, o'tgan hafta uchun)
| Ko'rsatkich | Nima |
|---|---|
| Savdo | Reja = oylik rejaning 1/4 qismi |
| O'rtacha chek | O'tgan haftaga nisbatan |
| Quvvat | 6 900 kg × ish kunlari |
| Jim mijozlar | 7 kundan beri buyurtma bermagan mijozlar |
| Nazoratdagi mijozlar | "Keyingi tovardan oldin yopadi" sharti bor mijozlar: kim yopmagan |
| Kechikkan vazifalar | Berilgan, rad etilgan, muddati o'tgan |

### Kunlik (oxirgi ish kuni uchun; dushanba kuni shanba ko'rsatiladi)
| Ko'rsatkich | Nima |
|---|---|
| Savdo | Kim qancha oldi, oy boshidan jami |
| Ishlab chiqarish | Tonna va quvvat % |
| Kassa kirimi | Kimdan qancha kirdi |
| Dividend | Kunlik va oy boshidan |

**Davr qanday tanlanadi:** Telegram'da `◀` / `▶` tugmalari bilan, rahbar panelida sana tanlagich
bilan. Hech narsa qo'lda yozilmaydi.

Oy hali tugamagan bo'lsa, reja o'tgan ish kunlariga proporsional olinadi, savdo uchun esa oy
oxiriga prognoz chiqadi.

**Avtomatik tekshiruv (4.1):** bu buyruq ko'rsatkichlar dvigatelini **mustaqil** tekshiradi. Savdo,
quvvat, o'rtacha chek, rentabellik, dividend va kassa bazadan to'g'ridan-to'g'ri, oddiy SQL bilan
qayta hisoblanadi va dvigatel natijasi bilan solishtiriladi. Qolgan ko'rsatkichlar xatosiz hisoblanishi
tekshiriladi. "hammasi mos" chiqsa, Telegram'dagi, paneldagi va AI'dagi raqamlarga ishonsa bo'ladi.
Kod o'zgargandan keyin va prod'ga chiqarilgandan keyin bir marta ishga tushiriladi. Hech narsani
o'zgartirmaydi, faqat o'qiydi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 4.1 | `bench --site pokiza.local execute pokiza.nazorat.metrics.tekshir.run --kwargs "{'davr': '2026-10'}"` | Oxirida `NATIJA: hammasi mos` |
| 4.2 | Xuddi shu, `'2026-09'` | `hammasi mos` |

---

## 5. AI chat (web)

Pokiza AI'ga savol berilganda, u avval rasmiy ko'rsatkichlarni oladi (`get_kpi`). Shuning uchun
javobdagi raqam Telegram hisoboti bilan bir xil bo'ladi. Qurilmagan yoki ma'lumoti yo'q narsani
o'ylab topmaydi.

**Loyihalar** (ChatGPT / Claude'dagi "Project" kabi). Chap panelda **Loyihalar** yonidagi **+** → nomi va
**AI uchun ko'rsatma** (masalan: "Bu loyiha Jizzax filiali sotuvi haqida. Javobni qisqa, jadval bilan ber").
Loyihaga 10 tagacha fayl qo'shiladi: PDF, Excel/CSV yoki rasm. Loyiha ichida yozilgan har bir yangi suhbatda AI
ko'rsatmani, fayllarni va shu loyihadagi boshqa suhbatlar mavzusini biladi. Mavjud suhbatni loyihaga ko'chirish
uchun suhbat ustidagi papka tugmasi. Loyiha o'chirilsa, suhbatlari saqlanib, umumiy ro'yxatga o'tadi.
Har kim faqat o'z loyihalarini ko'radi. Ko'rsatma rol cheklovlarini va "faqat o'qish" qoidasini bekor qilmaydi.
Loyihalar faqat web chatda, Telegram'da yo'q.

### Sinov
| # | Savol (`/app/pokiza-ai`) | Kutiladi |
|---|---|---|
| 5.1 | "Oktabr savdosi rejaga nisbatan qanday?" | 4,67 mlrd, reja 5 mlrd, 93,4%, 🟡 |
| 5.2 | "Oktabrda quvvat qancha ishladi?" | 151,5 t |
| 5.3 | "Qaysi mijozlar to'lov kelishuvini buzdi?" | Debitorlik ro'yxati (Jizzakh Local, Мухаммад Зубайр …) |
| 5.4 | "Oktabrda sof daromad dollarda qancha?" | Kurs Currency Exchange'dan olinganini aytadi |
| 5.5 | Dashboard so'rang (masalan "oylik savdo grafigi") | Avvalgidek ishlaydi |
| 5.6 | Istalgan javobni o'qing | Javobda A2, C1 kabi kodlar **yo'q**, faqat nomlar |
| 5.7 | Loyihalar **+** → nomi "Jizzax filiali", ko'rsatma "Javobni faqat jadval bilan ber" → Yaratish | Loyiha oynasi: ko'rsatma, Fayllar 0 / 10, Suhbatlar bo'sh |
| 5.8 | Loyihada pastdan savol yozing | Javob jadval ko'rinishida; suhbat loyiha ichida, sarlavhada "Jizzax filiali / …" |
| 5.9 | Loyihaga CSV yoki Excel qo'shing, keyin yangi suhbatda shu fayl haqida so'rang | AI fayl ichidagini biladi |
| 5.10 | Umumiy ro'yxatdagi suhbat ustida papka tugmasi → loyihani tanlang | Suhbat loyihaga o'tadi |
| 5.11 | Loyihani o'chiring | Loyiha yo'qoladi, suhbatlari umumiy ro'yxatda qoladi |

---

## 6. Nazorat boti va ulanish

**Ulanish qanday ishlaydi (ikki yo'l):**
- **Admin ulaydi (odatiy):** administrator yoki rahbar xodimning User sahifasini ochadi
  (User → `ishlabchiqarish@gmail.com`) → **Telegram'ga ulash** → bo'limni tanlaydi (rolga qarab
  oldindan tanlangan bo'ladi) → **Kod yaratish** → havolani nusxalab xodimga yuboradi. Xodim
  havolani o'z telefonida ochib Start bosadi.
- **Xodim o'zi:** ERP'ga kirib **My Settings** → **Telegram'ga ulash** → **Telegram'da ochish** → Start.
  Bunda bo'limni keyin admin TG Azo'da belgilaydi.

User sahifasi tepasida holat ko'rinadi: "Telegram ulangan: Ism @username · bo'lim: …" yoki
"Telegram ulanmagan". Bot yoqilmagan bo'lsa, tugma shuni aytadi.

Kod 10 daqiqa amal qiladi va faqat bir marta ishlaydi. Telefon raqam so'ralmaydi. 5 marta noto'g'ri
kod kiritilsa, 1 soatga bloklanadi. "Nazorat Bot Sozlamalari → Rahbar" maydonida ko'rsatilgan
foydalanuvchi ulanganda avtomatik **Rahbar** roli oladi.

**Lokal va prod farqi:** lokalda bot faqat polling ishlab turganda javob beradi (2-terminal). Prod'da
polling kerak emas, u yerda webhook ishlaydi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 6.1 | @BotFather → /newbot → nomi "Pokiza Nazorat", username `pokiza_nazorat_bot` | Token beriladi |
| 6.2 | ERP → **Nazorat Bot Sozlamalari**: token, Rahbar = o'z foydalanuvchingiz, "Bot faol" → Save | Saqlanadi, token yulduzcha bilan ko'rinadi |
| 6.3 | "Tekshirish va webhook o'rnatish" tugmasi | "Token to'g'ri: @… Sayt HTTPS emas — lokalda polling" |
| 6.4 | **Terminal 2:** `bench --site pokiza.local execute pokiza.nazorat.tg.polling.run` | "🤖 @pokiza_nazorat_bot polling rejimida" |
| 6.5 | Ulanmasdan botga istalgan xabar yozing | "🔒 Siz Nazorat botiga hali ulanmagansiz" |
| 6.6 | My Settings → **Telegram'ga ulash** → Telegram'da ochish → Start | "✅ Ulandingiz! Salom, …" va pastda tugmali menyu |
| 6.7 | Shu havolani ikkinchi marta bosing | "Kod noto'g'ri yoki muddati o'tgan" |
| 6.7a | Admin: User → `ishlabchiqarish@gmail.com` → **Telegram'ga ulash** | Dialog, bo'lim "Ishlab chiqarish" tanlangan |
| 6.7b | Kod yaratish → havolani boshqa Telegram akkauntdan oching → Start | Ulandi; User sahifasida "Telegram ulangan … bo'lim: Ishlab chiqarish" |
| 6.7c | Xodim akkauntida boshqa xodimning User sahifasi | Tugma chiqmaydi |
| 6.8 | Ishlab chiqarish xodimining menyusi | Faqat Kunlik / Haftalik / Oylik, Ko'rsatkichlar, Vazifalarim; "Vazifa berish" yo'q |
| 6.9 | Buxgalteriya xodimining menyusi | "Haftalik" yo'q (bu bo'limda haftalik ko'rsatkich yo'q) |
| 6.10 | Nazorat Bot Sozlamalari → "Tekshirish va webhook o'rnatish" ni qayta bosing | Telegram'dagi "/" ro'yxatida faqat `/start` qoladi |

---

## 7. Rahbar: hisobotlar, tugmalar, grafik, dividend

Rahbar **hamma** ko'rsatkichni ko'radi.

**Avtomatik keladi (shaxsiy chatga):**
- 08:00 — kunlik hisobot;
- dushanba 08:00 — haftalik;
- oyning 1-sanasi — oylik;
- **darhol** — kassadan dividend olinganda yoki bekor qilinganda ("💸 Rahbar pul oldi").

Xodimlarga ham shu vaqtda o'z bo'limi bo'yicha hisobot keladi (TG Azo → "08:00 hisobotlari shaxsiy
chatga keladi" belgisi bilan o'chirsa bo'ladi).

Kunlik hisobotda qoralama (tasdiqlanmagan) hujjatlar haqida ham ogohlantirish chiqadi.

**Menyu (buyruq yozish shart emas):** botning pastida doimiy tugmalar turadi:
`📅 Kunlik` `🗓 Haftalik` `📊 Oylik` · `📈 Ko'rsatkichlar` `📌 Vazifalarim` · `➕ Vazifa berish`.
Har kim faqat o'ziga tegishli tugmalarni ko'radi. Masalan, "Vazifa berish" faqat rahbarda bo'ladi.
Bo'lim xodimiga esa o'z ko'rsatkichi bo'lmagan hisobot turi chiqmaydi.

**Hisobot ko'rinishi:**
- Har ko'rsatkich 1–2 qatordan iborat: rang, qisqa nom, qiymat. Rejasi borida progress-chiziq `▰▰▰▰▰▰▰▰▰▱ 93%` chiqadi.
- O'tgan davrga nisbatan o'zgarish ham ko'rsatiladi. Foizli ko'rsatkichlarda u **pp** bilan beriladi.
- Oylik hisobot rahbarda 4 bo'limga guruhlanadi.
- Ogohlantirishlar oxirida **yig'iladigan blokda** turadi ("⚠️ N ta eslatma" — bosilsa ochiladi).
- Kunlikdagi "tasdiqlanmagan hujjat" eslatmasi faqat tegishli bo'limga boradi: sotuv fakturasi Sotuvga, xarid va kassa Buxgalteriyaga, hammasi rahbarga.

**Tugmalar:** hisobot ostida ko'rsatkich nomlari rangi bilan turadi (masalan, `🟡 Savdo`). Bosilsa batafsil kartochka chiqadi:
- katta raqam;
- reja;
- o'tgan davr;
- asosiy tarkib;
- top-8 ro'yxat.

Kartochka ostida 📈 grafik tugmalari bo'ladi. Eng pastdagi `◀ sentabr 2026` / `noyabr 2026 ▶` tugmalari
**shu xabarning o'zida** oldingi yoki keyingi davrni ochadi.

Eski `/kunlik`, `/haftalik`, `/oylik`, `/vazifalar` buyruqlari ham ishlaydi, lekin menyuda ko'rinmaydi —
hammasi tugmalar orqali.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 7.1 | Menyu → `📊 Oylik` | Oktabr hisoboti: 4 guruh, progress-chiziqlar, "⚠️ N ta eslatma" bloki, nomli tugmalar |
| 7.1a | `◀ sentabr 2026` tugmasi | Shu xabar sentabr hisobotiga almashadi; `oktabr 2026 ▶` bilan qaytadi |
| 7.2 | `🟡 Savdo` tugmasi | Kartochka: 4,67 mlrd, ▰ 93%, sentabrga nisbatan ↑15%, top-8 mijoz |
| 7.3 | "📈 12 oylik" | Ustunli grafik rasm (oxirgi qiymat yozilgan, reja punktir) |
| 7.4 | `📅 Kunlik`, `🗓 Haftalik` | Oxirgi ish kuni / o'tgan hafta; kunlikda "Tasdiqlanmagan sotuv fakturasi" |
| 7.5 | `📈 Ko'rsatkichlar` → `Debitorlik · oy` | Tugmali ro'yxat; qarzdorlar kartochkasi |
| 7.5a | Kartochkadagi "📈 12 oylik" grafik | Rasm sarlavhasida faqat nom (kod yo'q) |
| 7.6 | 08:00 ni kutmasdan: `bench --site pokiza.local execute pokiza.nazorat.jadval.kunlik` | Rahbarga keladi |
| 7.7 | 7.6 ni yana bir marta ishga tushiring | Ikkinchi marta **kelmaydi** (Nazorat Yuborish jurnali) |
| 7.8 | `...jadval.haftalik` va `...jadval.oylik` | Haftalik va oylik hisobotlar |
| 7.9 | Kassa: Расход, Дивиденд 1, kichik summa → Submit | Rahbarga darhol "💸 Rahbar pul oldi" |
| 7.10 | Shu Kassa'ni Cancel | "↩️ Dividend hujjati BEKOR qilindi" |
| 7.11 | Nazorat Sozlamalari → "Дивиденд 1 — kim" ga ism yozing, 7.9 ni takrorlang | Xabarda ism chiqadi |

---

## 8. Rollar: kim nimani ko'radi

Kim nimani ko'rishi **ERP'da sozlanadi**: **Nazorat Roli** sahifasi. Kod o'zgartirish kerak emas.

- **Rol sahifasida:**
  - rol nomi;
  - "To'liq ruxsat" — rahbar darajasi, hamma narsa ochiq;
  - "Vazifa bera oladi" — vazifa beradi va xodimlarga botdan xabar yuboradi;
  - ko'rsatkichlar ro'yxati — **nomi bilan** belgi qo'yiladi (Savdo, Quvvat, Debitorlik…);
  - AI nimalarni ko'ra oladi — mijoz qarzi, postavshik qarzi, kassa, ishlab chiqarish, savdo tarixi,
    Excel va "butun baza bo'yicha erkin so'rov" (bu oxirgisi xavfli);
  - ERP rollari — xodimni ulashda shu ERP roli bo'lsa, bu rol avtomatik taklif qilinadi.
- **Xodimga rol berish:** **TG Azo** → "Nazorat roli" maydoni. Shu zahoti menyusi, hisobotlari va AI
  doirasi o'zgaradi.
- **Botdan rol berish (faqat administrator):** botda `👥 Xodimlar` → xodim → kartochka. Tugmalar:
  - 🎭 Rolni o'zgartirish — Nazorat Roli tanlanadi; 🔑 belgili (to'liq ruxsatli) rol alohida tasdiq bilan beriladi;
  - 🤖 AI bilan savol-javob — yoqish / o'chirish;
  - 📅 08:00 hisobotlari — yoqish / o'chirish;
  - ⛔ Botdan uzish / ✅ Qayta yoqish.

  Har o'zgarish TG Azo tarixiga va izohiga yoziladi (kim, qachon, nima). Xodimga botda xabar boradi, menyusi
  yangi roliga moslanadi. Administrator o'z rolini o'zgartira va o'zini uza olmaydi. Menyu faqat System Manager
  rolidagi foydalanuvchida ko'rinadi, boshqalar tugmani bosa olmaydi.
- **Tayyor rollar** (avvalgi bo'limlar ko'chirilgan): Rahbar, Sotuv, Ishlab chiqarish, Buxgalteriya, Ombor.
- Rahbar rolini o'chirib bo'lmaydi.

| Rol | Ko'radi (standart) |
|---|---|
| Sotuv | Savdo, o'rtacha chek, mijoz dinamikasi, top mahsulotlar, jim mijozlar, nazoratdagi mijozlar |
| Ishlab chiqarish | Quvvat, kunlik ishlab chiqarish, brak |
| Buxgalteriya | Postavshik, debitorlik, xarajatlar, kassa |
| Rahbar | Hammasi |

Rol berilmagan xodim hech qanday ko'rsatkich ko'rmaydi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 8.0 | **Nazorat Roli** → New: "Logistika", faqat "Jim mijozlar" va "Excel" belgilansin → Save; TG Azo'da xodimga shu rolni bering; botga `/start` | Menyuda faqat Haftalik va Ko'rsatkichlar; ichida faqat "Jim mijozlar" |
| 8.1 | Ikkinchi foydalanuvchi (xodim) 6.6 kabi ulansin, bo'lim tanlanmasin | "✅ Ulandingiz!", "Bo'lim hali biriktirilmagan" |
| 8.2 | Xodimning pastki menyusi | Faqat `📌 Vazifalarim` (hisobot va ko'rsatkich tugmalari yo'q) |
| 8.3 | **TG Azo** → xodim → Nazorat roli = Sotuv; botga `/start` | Menyuda Kunlik / Haftalik / Oylik va Ko'rsatkichlar paydo bo'ladi |
| 8.4 | `📈 Ko'rsatkichlar` | Faqat Savdo, O'rtacha chek, Mijoz dinamikasi, Top mahsulotlar, Jim mijozlar, Nazoratdagi mijozlar |
| 8.5 | `📊 Oylik` | Faqat savdo ko'rsatkichlari; foyda, rentabellik, dividend yo'q |
| 8.6 | Administrator botda `👥 Xodimlar` → xodim → 🎭 Rolni o'zgartirish → Ishlab chiqarish | Xodimga "Rolingiz o'zgardi" xabari, menyusi yangilanadi; TG Azo izohida yozuv |
| 8.7 | Xuddi shu yerda "Rahbar 🔑" ni tanlang | Avval "to'liq ruxsatli rol — tasdiqlaysizmi?" chiqadi |
| 8.8 | Xodim kartochkasida ⛔ Botdan uzish → xodim botga `/start` | Xodimga "ulanmagansiz" chiqadi |
| 8.9 | Oddiy xodim botga `👥 Xodimlar` deb yozadi | "Bu bo'lim faqat administrator uchun" |

---

## 9. Bot faqat shaxsiy chatda

Nazorat boti faqat xodimlar uchun va faqat **shaxsiy chatda** ishlaydi. Telegram guruhi yo'q.
- Botni guruhga qo'shsa, u **jim chiqib ketadi**: guruhga hech narsa yozmaydi, guruhdagi xabarlarga javob bermaydi.
- Vazifalar, eslatmalar, kunlik ro'yxat, ish signallari, hisobotlar va AI javoblari — hammasi har kimning
  shaxsiy chatiga, o'z roli doirasida keladi.
- **Ish signallari (har kuni 09:00)** — oxirgi ish kuni bo'yicha nima kiritilmagan, raqamsiz:
  - tasdiqlanmagan sotuv fakturasi → Sotuv xodimlariga;
  - tasdiqlanmagan xarid fakturasi, kassa hujjati, kassa yozuvi yo'q → Buxgalteriyaga;
  - ishlab chiqarish kiritilmagan → Ishlab chiqarishga;
  - **rahbarga hammasi**, har signal yonida mas'ul xodimlar nomi bilan.

  Kim mas'ulligi xodimning Nazorat Roli'dan olinadi (TG Azo → rol).
- **Sozlamalar** (Nazorat Bot Sozlamalari → Vazifalar va signallar): bajarilgan vazifani beruvchi tasdiqlaydimi;
  ish signallari yoqilganmi.
- Botni guruhga umuman qo'shib bo'lmasligi uchun **@BotFather → /setjoingroups → Disable** qiling (bir martalik).

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 9.1 | Botni istalgan Telegram guruhiga qo'shing | Bot hech narsa yozmasdan guruhdan chiqib ketadi |
| 9.2 | Nazorat Bot Sozlamalari → **Tekshirish va webhook o'rnatish** tugmasi | Guruh buyruqlari menyusi o'chadi |
| 9.3 | `bench --site pokiza.local execute pokiza.nazorat.signallar.ish_signallari` | Mas'ul xodimga — o'z signallari, rahbarga — hammasi, mas'ullar nomi bilan (shaxsiy chatda) |
| 9.4 | Sozlamada "ish signallari"ni o'chiring, 9.3 ni takrorlang | Hech narsa kelmaydi |

---

## 10. Vazifalar

- **Rahbar vazifa beradi** uch yo'l bilan: botda `➕ Vazifa berish`, ERP'da **Vazifa** → New, yoki AI orqali (11-bo'lim).
- **Hammasi shaxsiy chatda:**
  - mas'ulga tugmali xabar keladi: ✅ Qabul qilaman / ❌ Rad etaman → ✔️ Bajarildi;
  - qabul qilinsa, beruvchiga qisqa xabar boradi;
  - rad etilsa, sabab so'raladi va beruvchiga sababi bilan boradi;
  - **beruvchi tekshiruvi:** "Bajarildi"dan keyin beruvchiga 👍 Qabul qilaman / ↩️ Qaytarish keladi;
    qaytarishda sabab so'raladi, mas'ulga sababi bilan qaytadi;
  - ertangi muddat eslatmasi va "muddati o'tdi" xabari mas'ulga, "muddati o'tdi" beruvchiga ham.
  - vazifa ERP'da o'zgarsa ham mas'uldagi vazifa xabari yangilanadi.
- **09:00 da har kimga o'z ro'yxati** (bo'sh bo'lsa xabar kelmaydi):
  - o'zidagi vazifalar: bugun muddati tugaydiganlar, muddati o'tganlar, hali qabul qilmaganlari (tugmalar bilan);
  - o'zi bergan vazifalardan: tekshiruv kutayotganlar va muddati o'tganlar.
- **Dushanba 09:05:** rahbarga o'tgan hafta natijasi — har xodimning bajargani, kechikkani va reyting (summalarsiz).
- **ERP'dagi cheklov:** xodim faqat o'ziga tegishli vazifani ko'radi va faqat holat, rad sababi va
  izohni o'zgartira oladi. Tasdiq va tarix faqat ko'rish uchun.
- **Statistika:** oylik hisobotda "Vazifalar bajarilishi", haftalikda "Kechikkan vazifalar".

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 10.1 | Rahbar botda `➕ Vazifa berish` → xodim → matn → "3 kun" → ✅ Yaratish | Xodimning shaxsiy chatida vazifa va ✅ / ❌ |
| 10.3 | Mas'ul "✅ Qabul qilaman" | Rahbarga "qabul qildi" xabari; mas'ulda tugma ✔️ Bajarildi |
| 10.4 | Mas'ul "✔️ Bajarildi" | Rahbarga "tekshirib qabul qiling" va 👍 / ↩️ |
| 10.6 | Rahbar "↩️ Qaytarish" → sabab yozadi | Mas'ulga "↩️ qaytarildi" + sabab + ✔️ Bajarildi |
| 10.7 | Mas'ul yana bajaradi → rahbar 👍 | ERP'da "Beruvchi tasdiqladi" ✔ |
| 10.8 | Yangi vazifa → mas'ul "❌ Rad etaman" → sabab | Rahbarga "rad etdi" + sabab |
| 10.9 | ERP'da **Vazifa** → New | Mas'ulga tugmali xabar |
| 10.10 | Xodim ERP'da muddatni o'zgartirishga urinadi | Xato: faqat holat/izoh |
| 10.11 | (System Manager) bir vazifa muddatini kechaga qo'ying → `bench --site pokiza.local execute pokiza.nazorat.vazifa.kunlik_tekshir` | Mas'ul va beruvchiga "⏰ Muddati o'tdi"; ikkalasiga ham o'z kunlik ro'yxati |
| 10.12 | `bench --site pokiza.local execute pokiza.nazorat.vazifa.haftalik_natija` | Rahbarga o'tgan hafta natijasi (o'tgan hafta muddatli vazifa bo'lsa) |
| 10.13 | Botda `📌 Vazifalarim` | Ro'yxat muddatlar bilan ("2 kun qoldi", "kechikdi") |

---

## 11. AI Telegram'da

Telegram'da ham web'dagi Pokiza AI'ning o'zi javob beradi.

- **Shaxsiy chat:** rahbar istalgan savolni matn yoki **ovozli xabar** bilan beradi. Excel so'ralsa,
  fayl keladi. Xodim savol bera oladi, agar TG Azo'da "AI bilan savol-javob" belgisi bo'lsa; javob
  faqat o'z bo'limi doirasida bo'ladi.
- **Vazifa berish:** rahbar "Alisherga ... vazifasini ber" desa, AI vazifani faqat **taklif** qiladi.
  Vazifa **✅ Yaratish** bosilgandagina yaratiladi va mas'ulga ketadi.
- **Xodimga xabar:** rahbar shaxsiy chatda "Odilga yoz, ..." desa, AI xabar matnini ko'rsatadi.
  Xabar **✅ Yuborish** bosilgandagina ketadi.
- **Navbat:** javob tayyorlanayotganda yana savol yozilsa, savol yo'qolmaydi: navbatga qo'yiladi va
  oldingi javobdan keyin ishlanadi.
- **Ruxsat:** bot faqat AI ruxsati bor odamga javob beradi. Web AI chat ham TG Azo'dagi rol
  bo'yicha cheklangan (administrator — cheklovsiz).
- **Limitlar:** bir foydalanuvchiga kuniga 40 ta savol (Nazorat Bot Sozlamalari). Bundan tashqari AI'ning
  oylik $ limiti ham amal qiladi.
- **Tarix:** Telegram suhbatlari ERP'dagi Pokiza AI sahifasida ham ko'rinadi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 11.1 | Rahbar shaxsiy chatda: "Oktabr savdosi rejaga nisbatan?" | "yozmoqda…" → qisqa javob |
| 11.2 | Ovozli xabar bilan savol | Javob |
| 11.3 | "Oktabr mijozlar savdosini Excel qilib ber" | Excel fayl keladi |
| 11.4 | "<xodim ismi>ga ertagacha ... vazifasini ber" | Javob + "✅ Yaratish"; bosilgach vazifa mas'ulga ketadi |
| 11.5 | Xodim (AI belgisi yo'q) shaxsiy chatda matn yozadi | "Pastdagi menyudan tanlang 👇" |
| 11.6 | Xodimga AI belgisini qo'ying (bo'lim Sotuv): "Oktabrda sof foyda qancha?" | "Sotuv bo'limi uchun yopiq" |
| 11.11 | ERP → Pokiza AI sahifasi | Telegram suhbatlari ham ro'yxatda |

---

## 12. Rahbar paneli

`/app/rahbar-paneli` — ERP ichidagi ko'rsatkichlar sahifasi.
- **Davr:** Oylik / Haftalik / Kunlik tugmalari, sana tanlagich (maydonda davr oralig'i ko'rinadi),
  `‹ ›` va "Joriy / O'tgan" tugmalari. Kelajakdagi davrga o'tib bo'lmaydi.
- **Oylik ko'rinish** 4 bo'limga guruhlangan: Strategik fokus (katta kartochkalar, reja chizig'i bilan),
  Mijozlar va sotish, Moliya va to'lovlar, Vazifalar va jamoa.
- **Har kartochkada** ko'rsatkich nomi, holat (belgi va so'z bilan), qiymat, reja va o'zgarish. Kod yozilmaydi.
- **Kartochka bosilsa:** trend grafigi, "Jadval ko'rinishi", asosiy raqamlar va tafsilot jadvali.
- **Raqamlar va cheklov:** raqamlar Telegram bilan bir xil. Xodim faqat o'z bo'limini ko'radi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 12.1 | `http://localhost:8001/app/rahbar-paneli` (System Manager) | Oktabr, 4 bo'lim, kartochkalarda faqat nomlar |
| 12.2 | Haftalik / Kunlik tugmalari; sana tanlagichdan sentabrni tanlang; `‹ ›` | Ko'rsatkichlar shu davrga; joriy davrda `›` o'chiq |
| 12.3 | Kartochkani bosing | Oyna sarlavhasida nom; grafik, jadval, tafsilot |
| 12.4 | Sotuv bo'limli xodim bilan kiring (Sales Manager roli) | Faqat savdo, foyda/dividend yo'q |
| 12.5 | Telegram `📊 Oylik` bilan solishtiring | Raqamlar bir xil |

---

## 13. Avtomatik ishlar (scheduler)

| Vaqt | Nima |
|---|---|
| Har kuni 08:00 | Kunlik hisobot |
| Dushanba 08:00 | Haftalik hisobot |
| Oyning 1-sanasi 08:00 | Oylik hisobot |
|  | (08:00 hisobotlari — rahbarga va xodimlarga, shaxsiy chatda) |
| Har kuni 09:00 | Vazifalar: muddati o'tganlarni belgilash, eslatmalar, har kimga o'z ro'yxati; ish signallari (mas'ulga va rahbarga); Sotuvga bugun jim bo'lgan mijozlar (shaxsiy chatda) |
| Dushanba 09:05 | Rahbarga o'tgan hafta vazifa natijasi |
| Oyning 11-sanasi 09:00 | To'lov intizomi: postavshiklar va debitorlik bo'yicha yakuniy holat (to'lov muddati 10-sana) |
| Darhol | Dividend: Kassa yoki to'g'ridan-to'g'ri Journal Entry (dividend hisobi) submit/cancel qilinganda |

Har bir xabar bir marta ketadi: hisobotlar **Nazorat Yuborish** jurnaliga yoziladi, qolgan xabarlar
kunlik belgi bilan. Bot o'chirilsa (Nazorat Bot Sozlamalari → Faol), hech qanday xabar ketmaydi.

Lokalda scheduler o'chiq. Sinovda hisobotlarni buyruq bilan qo'lda yuborasiz (7.6). Avtomatik
ishlashini ko'rmoqchi bo'lsangiz, `bench --site pokiza.local enable-scheduler` qiling. Bunda boshqa
app'larning rejali vazifalari ham ishga tushadi.

---

## 14. Xavfsizlik

- **AI faqat o'qiydi.** Bazaga hech narsa yoza olmaydi. Vazifa va xodimga xabar faqat taklif
  ko'rinishida, rahbar tugma bosib tasdiqlaydi.
- **Excel fayl** faqat rolda ochiq ma'lumotdan tuziladi. Erkin SQL va report faqat "butun baza" belgisi bor rolda.
- **Bot faqat shaxsiy chatda.** Guruhga qo'shilsa chiqib ketadi, guruhga hech narsa yozmaydi.
- **Telegram ulash:** boshqa xodim uchun kodni administrator yoki rahbar yaratadi. Rahbar administrator
  akkaunti uchun va allaqachon ulangan akkaunt uchun kod yarata olmaydi.
- **Bo'lim cheklovi** kod darajasida qo'yilgan. Masalan, Sotuv xodimining AI'siga foydani yoki ish
  haqini hisoblaydigan vosita umuman berilmaydi.
- **Vazifa tugmalari**: mas'ulda (qabul, rad, bajarildi) va beruvchida (tasdiq, qaytarish).
- **Ulanmagan** Telegram foydalanuvchiga bot ma'lumot bermaydi.
- **Webhook maxfiy kalit bilan himoyalangan.** Bot tokeni ERP'da shifrlangan holda saqlanadi.

**Ma'lumot himoyasi** (Nazorat Bot Sozlamalari → "Ma'lumot himoyasi"): xodim AI orqali ma'lumotni yig'ib
olib chiqib ketmasligi uchun. Rahbar va administratorga cheklov qo'yilmaydi.

| Sozlama | Standart | Nima qiladi |
|---|---|---|
| Xodimlar AI'dan Excel/PDF fayl ola oladi | o'chiq | O'chiq bo'lsa fayl faqat rahbarga. Yoqilsa — Nazorat Roli'da "Excel" belgisi bor rollarga ham |
| Forward va saqlash taqiqlansin | yoqiq | Xodimga bot yuborgan xabar va faylni boshqa chatga uzatib, yuklab olib bo'lmaydi |
| Rahbarga ham taqiq | o'chiq | Yoqilsa rahbarning xabarlari ham himoyalanadi |
| ERP'dagi AI chat ham "AI bilan savol-javob" belgisini talab qilsin | yoqiq | Belgisi yo'q xodim web AI'dan ham foydalana olmaydi |
| Bir kunda shuncha fayl — rahbarga xabar | 3 | Xodim chegaraga yetganda rahbarga "Diqqat" xabari (0 — o'chiq) |
| Bir kunda shuncha savol — rahbarga xabar | 25 | Xuddi shunday, savollar soni bo'yicha |

Barcha AI suhbatlari ERP'da (**AI Suhbat**) saqlanadi — kim nima so'ragani ko'rinadi. ERP'ning o'z
hisobotlaridan Excel yuklash ERP rollari bilan alohida cheklanadi.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 14.1 | Sotuv xodimi (AI belgisi bor) botda: "mijozlar qarzini Excel qilib ber" | Fayl berilmaydi |
| 14.2 | Sozlamada "Xodimlar AI'dan Excel…" ni yoqing, 14.1 ni takrorlang | Fayl keladi; uni forward qilib bo'lmaydi |
| 14.3 | Xodimga kelgan bot xabarini boshqa chatga forward qilishga urining | Telegram ruxsat bermaydi |
| 14.4 | AI belgisi yo'q xodim ERP → Pokiza AI sahifasida savol beradi | "AI bilan savol-javob ruxsati berilmagan" |
| 14.5 | "Bir kunda shuncha savol" ni 2 qiling; xodim 2 ta savol beradi | Rahbarga "⚠️ Diqqat: … bugun AI'ga 2 ta savol berdi" |

---

## 15. Ma'lumot sifati (bilib qo'ying)

- **Brak:** "Brak va vozvrat" ko'rsatkichi brakni «Brak» oynasidan yozilgan Material Issue'lardan oladi (tannarxi «Брак» hisobida). Davrda brak yozilmagan bo'lsa, 0% va "brak yozilmagan" izohi chiqadi.
- **Kategoriya va xarajat turi:** belgilanmaguncha "Kategoriyalar" va "Xarajatlar" to'liq chiqmaydi (3.7).
- **Mijoz kelishuvi:** kiritilmagan qarzdorlar "Debitorlik"da alohida eslatma bo'lib chiqadi.
- **Qoralama hujjatlar:** hisobotga kirmaydi; kunlik hisobot tegishli bo'limga ular haqida eslatadi.
- **Mijoz qarzi** GL qoldig'idan olinadi. Fakturalardagi "qolgan summa" ishlatilmaydi, chunki
  to'lovlar fakturalarga bog'lanmagan.
- **Kurs:** Currency Exchange'dagi kurs 45 kundan eski bo'lsa, "Sof daromad"da ogohlantirish chiqadi.

---

## 16. Oylik mijoz hisoboti (PDF)

Mijozga beriladigan bir sahifalik "savdo tahlili". Avval bu hisobot AI orqali qo'lda tayyorlanardi,
endi ERP o'zi yasaydi. Tanlangan oy o'tgan oyga solishtiriladi.

**Hisobotda nima bor:**
- savdo hajmi (kg) va savdo summasi: ikki oy va o'zgarish (% va farq);
- savdosi eng ko'p kamaygan va eng ko'p oshgan 5 ta mahsulot;
- asosiy mahsulot tahlili: mijoz eng ko'p oladigan mahsulot, uning o'zgarishi va umumiy o'zgarishdagi hissasi;
- hajm ulushi: asosiy mahsulot va qolgan mahsulotlar;
- keyingi oy maqsadi.

**Raqamlar qayerdan olinadi:**
- faqat tasdiqlangan sotuv fakturalari, qaytarishlar ayirilgan;
- summa QQS'siz;
- hajm: kg'dagi mahsulotlar + donali mahsulotlar × Item'dagi vazn. Vazni kiritilmagan donali
  mahsulotlar kg'ga qo'shilmaydi, pastda alohida "N dona" deb yoziladi.

**Maqsad qayerdan olinadi:** **Mijoz Kartochkasi → Oylik maqsadlar** jadvali. Har qatorda yil, oy,
maqsad kg, maqsad summa va ixtiyoriy izoh bo'ladi. Bir oy bir marta kiritiladi. Maqsad kiritilmagan
bo'lsa, hisobotda "maqsad kiritilmagan" deb yoziladi. Izoh yozilsa, banner'da shu izoh chiqadi.
Izoh bo'lmasa, avtomatik "savdoni kamida N% oshirish" yoziladi.

**Qanday olinadi:** **Customer** sahifasi → **Hisobotlar → Oylik savdo tahlili (PDF)**. Yoki
**Mijoz Kartochkasi** → **Oylik savdo tahlili (PDF)**. Oy tanlanadi, PDF yangi oynada ochiladi.
PDF'ni yuklab olib, mijozga yuborasiz.

### Sinov
| # | Qadam | Kutiladi |
|---|---|---|
| 16.1 | Mijoz Kartochkasi → ЧП Жамилов Жонибек → "Oylik maqsadlar" | 2026 Oktabr 40 000 kg / 1 mlrd, Noyabr 42 000 kg |
| 16.2 | **Oylik savdo tahlili (PDF)** → Sentabr 2026 | Bir sahifali PDF: 38 628 → 31 660 kg (−18,0%), 913,1 → 807,2 mln (−11,6%) |
| 16.3 | PDF'dagi asosiy mahsulot | Сосиски НЕЖНАЯ: 26 212 → 19 695 kg, −24,9%, umumiy pasayishning 94%i |
| 16.4 | PDF'dagi maqsad | Oktabr: 40 000 kg, 1,00 mlrd; "kamida 26% oshirish" |
| 16.5 | Customer → Мухиддин → Hisobotlar → Oylik savdo tahlili → Oktabr 2026 | PDF; maqsad bo'limida "Noyabr 2026 uchun maqsad kiritilmagan" |
| 16.6 | Kartochkada bir oyni ikki marta kiriting → Save | Xato: "ikki marta kiritilgan" |
| 16.7 | Maqsad qatoriga izoh yozing (masalan "Sosiska savdosini qayta tiklash"), PDF'ni qayta oling | Banner'da shu izoh |
| 16.8 | Sotuvi bo'lmagan mijoz uchun PDF | "tasdiqlangan sotuv yo'q" |
| 16.9 | Hisobotdagi raqamlarni ERP'da tekshiring: Sales Analytics yoki Sales Invoice ro'yxati (mijoz + oy, tasdiqlangan) | Summa bir xil |

---

## 17. Prod'ga chiqarish (siz qilasiz)

1. `git pull`
2. `bench pip install matplotlib` (yoki `bench setup requirements`)
3. `bench --site pokiza.local migrate`
4. `bench build --app pokiza`
5. `bench restart`
6. `bench --site pokiza.local execute pokiza.nazorat.metrics.tekshir.run --kwargs "{'davr': '2026-10'}"` → "hammasi mos"
7. Nazorat Bot Sozlamalari: token, Rahbar, **Sayt manzili (https://…)** → "Tekshirish va webhook
   o'rnatish". Prod'da polling **kerak emas**.
8. Scheduler yoqilganini tekshiring: `bench --site pokiza.local scheduler status`
9. **Worker'lar:** AI javob yozayotganda bot tugmalari qotib qolmasligi uchun tezkor navbat (short, default)
   va AI navbati (long) alohida worker'da bo'lishi kerak. `bench setup supervisor` buni o'zi qiladi
   (default-, short- va long-worker). Tekshirish: `sudo supervisorctl status | grep worker` — kamida
   short va long worker'lar RUNNING bo'lsin. Bitta umumiy worker bo'lsa: `config/common_site_config.json`
   da `"background_workers": 2` qo'yib, `bench setup supervisor && sudo supervisorctl reread && sudo supervisorctl update`.
