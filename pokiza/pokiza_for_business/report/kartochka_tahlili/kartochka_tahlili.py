# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Kartochka Tahlili — Mijoz Kartochkasi bo'yicha to'liq nazorat hisoboti.

To'rt ko'rinish («Кўриниш» filtri, Akt Sverka naqshi):
  * To'lov intizomi — ASOSIY MAQSAD: mijoz kelishuv qoidalariga amal
    qilyaptimi. Oyma-oy: M oyda olingan tovar, kelishuv bo'yicha yopilishi
    kerak qism (tolov_foiz), muddat (M+1 oyning tolov_kuni sanasi), muddat
    holatiga GL qarz vs ruxsat etilgan qarz, oshgan summa va hukm
    (bajarildi / buzildi / to'lashi kerak / kelishuv yo'q), limit nazorati.
    FORMULA RAHBAR HISOBOTI (nazorat C2) BILAN AYNAN BIR XIL:
    ruxsat = M oy tovari × (100−foiz)/100 + muddatgacha olingan yangi tovar;
    muddat holatiga GL qarz shundan oshsa — buzildi (1000 so'm bardoshlik).
  * Mijozlar kesimi — har kartochka bo'yicha hamma narsa: qator statistikasi,
    marja, davr ichidagi savdo, qamrov (sotilgan-u kartochkada yo'q SKU /
    kartochkada bor-u sotilmagan SKU), GL qarz va limit, to'lov sharti,
    «oldingi tovar yopilmagan» (H5), joriy oy maqsadi vs fakt, oxirgi
    o'zgarish sanasi va «Muammolar» xulosasi;
  * Qatorlar kesimi — har SKU qatori: kartochka narxi/marjasi, JORIY davr
    tannarxi bilan farq (eskirganlik), oxirgi sotuv narxi bilan farq,
    Item Price sinxron holati, oxirgi narx o'zgarishi;
  * O'zgarishlar jurnali — Kartochka Ozgarish Jurnali davr bo'yicha.

MANBALAR: kartochka jadvallari, Sales Invoice (davr filtri, faqat sotuv
guruhlari), GL Entry (qarz — to_date holatiga), Item Price (mijoz kesimi,
pokiza.api.narx sinxronining nusxasi), Tannarx Davri (davr_map — joriy
normativ tannarx), Kartochka Ozgarish Jurnali.

ESLATMA: qatordagi `tannarx` kartochkaga yozilgan NUSXA, «Joriy tannarx»
esa bugungi Tannarx Davridan — farqi «eskirgan tannarx» belgisi. Hisobotlar
puli schyotdagi muzlatilgan nusxadan yuradi, bu yerdagi farq faqat
kartochkani yangilash kerakligini ko'rsatadi.
"""

import bisect

import frappe
from frappe import _
from frappe.utils import (add_days, add_months, flt, get_first_day,
                          get_last_day, getdate, nowdate)

from pokiza.guruhlar import sotuv_guruhlari

# Mijoz Oylik Maqsad doctype'idagi Select bilan bir xil tartib
OYLAR = ("Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
         "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr")
TANNARX_FARQ_CHEGARA = 1  # so'm — bundan katta farq «eskirgan» hisoblanadi
BARDOSHLIK = 1000  # so'm — nazorat C2 bilan bir xil: shundan kichik farq buzish emas


def execute(filters=None):
    filters = frappe._dict(filters or {})
    korinish = filters.get("korinish") or "To'lov intizomi"
    if korinish == "Mijozlar kesimi":
        return _mijozlar_kesimi(filters)
    if korinish == "Qatorlar kesimi":
        return _qatorlar_kesimi(filters)
    if korinish == "O'zgarishlar jurnali":
        return _jurnal_kesimi(filters)
    return _tolov_intizomi(filters)


# ---------------------------------------------------------------- manbalar

def _kartochkalar(filters):
    shart, qiymat = ["1=1"], {}
    if filters.get("mijoz"):
        shart.append("mijoz = %(mijoz)s")
        qiymat["mijoz"] = filters.mijoz
    if filters.get("holat"):
        shart.append("holat = %(holat)s")
        qiymat["holat"] = filters.holat
    return frappe.db.sql(
        """
        SELECT name, mijoz, holat, hudud, masul, bonus_foiz, limit_summa,
               tolov_sharti, tolov_foiz, tolov_kuni, oldingi_tovar_sharti
        FROM `tabMijoz Kartochkasi`
        WHERE %s ORDER BY mijoz
        """ % " AND ".join(shart),
        qiymat,
        as_dict=True,
    )


def _qator_map(kartochka_nomlari):
    """{kartochka: [qatorlar]} — barcha child qatorlar bitta so'rovda."""
    if not kartochka_nomlari:
        return {}
    natija = {}
    for r in frappe.db.sql(
        """
        SELECT parent, sku, sku_nomi, norma, status, amal_sana,
               sotuv_narxi, bonus_foiz, bonus_keyin_narx, tannarx,
               marja_som, marja_foiz
        FROM `tabMijoz Kartochka Qatori`
        WHERE parenttype = 'Mijoz Kartochkasi' AND parent IN %(k)s
        ORDER BY parent, idx
        """,
        {"k": tuple(kartochka_nomlari)},
        as_dict=True,
    ):
        natija.setdefault(r.parent, []).append(r)
    return natija


def _savdo_map(mijozlar, f, t):
    """{(mijoz, sku): {kg, summa, oxirgi_narx, oxirgi_sana}} — davr savdosi.

    Faqat sotuv guruhlari (xizmat/boshqa itemlar qamrov tahlilini
    bulg'amasin). ORDER BY DESC tufayli birinchi uchragan qator —
    oxirgi sotuv narxi (kartochka.py'dagi _tarix_qatorlari naqshi).
    """
    if not mijozlar:
        return {}
    rows = frappe.db.sql(
        """
        SELECT si.customer, sii.item_code, sii.stock_qty, sii.base_amount,
               sii.rate, si.posting_date
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.customer IN %(m)s
          AND si.posting_date BETWEEN %(f)s AND %(t)s
          AND it.item_group IN %(g)s
        ORDER BY si.posting_date DESC, si.creation DESC
        """,
        {"m": tuple(mijozlar), "f": f, "t": t, "g": sotuv_guruhlari()},
        as_dict=True,
    )
    natija = {}
    for r in rows:
        d = natija.setdefault(
            (r.customer, r.item_code),
            {"kg": 0.0, "summa": 0.0,
             "oxirgi_narx": flt(r.rate), "oxirgi_sana": r.posting_date},
        )
        d["kg"] += flt(r.stock_qty)
        d["summa"] += flt(r.base_amount)
    return natija


def _qarz_map(mijozlar, sana):
    """{mijoz: GL qoldiq} sana holatiga (debet − kredit = bizga qarzi).
    Nazorat C2 bilan bir xil manba: GL, SI.outstanding emas."""
    if not mijozlar:
        return {}
    return {p: flt(v) for p, v in frappe.db.sql(
        """
        SELECT party, SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = 'Customer'
          AND party IN %(m)s AND posting_date <= %(s)s
        GROUP BY party
        """,
        {"m": tuple(mijozlar), "s": sana},
    )}


def _item_price_map(mijozlar):
    """{(mijoz, sku): narx} — pokiza.api.narx sinxroni yozgan mijoz narxlari."""
    from pokiza.api.narx import PRAYS_LIST
    if not mijozlar:
        return {}
    return {(c, i): flt(n) for c, i, n in frappe.db.sql(
        """
        SELECT customer, item_code, price_list_rate FROM `tabItem Price`
        WHERE price_list = %(p)s AND customer IN %(m)s
        """,
        {"p": PRAYS_LIST, "m": tuple(mijozlar)},
    )}


def _jurnal_oxirgi(mijozlar):
    """({mijoz: oxirgi o'zgarish}, {(mijoz, sku): oxirgi narx o'zgarishi})."""
    if not mijozlar:
        return {}, {}
    umumiy = dict(frappe.db.sql(
        """
        SELECT mijoz, MAX(creation) FROM `tabKartochka Ozgarish Jurnali`
        WHERE mijoz IN %(m)s GROUP BY mijoz
        """,
        {"m": tuple(mijozlar)},
    ))
    narx = {(m, s): v for m, s, v in frappe.db.sql(
        """
        SELECT mijoz, sku, MAX(creation) FROM `tabKartochka Ozgarish Jurnali`
        WHERE mijoz IN %(m)s AND maydon = 'sotuv_narxi' GROUP BY mijoz, sku
        """,
        {"m": tuple(mijozlar)},
    )}
    return umumiy, narx


def _maqsad_map(kartochka_nomlari, sana):
    """{kartochka: (maqsad_kg, maqsad_summa)} — sana tushgan oy uchun."""
    if not kartochka_nomlari:
        return {}
    d = getdate(sana)
    return {p: (flt(kg), flt(s)) for p, kg, s in frappe.db.sql(
        """
        SELECT parent, maqsad_kg, maqsad_summa FROM `tabMijoz Oylik Maqsad`
        WHERE parenttype = 'Mijoz Kartochkasi' AND parent IN %(k)s
          AND yil = %(y)s AND oy = %(o)s
        """,
        {"k": tuple(kartochka_nomlari), "y": d.year, "o": OYLAR[d.month - 1]},
    )}


def _oy_fakt_map(mijozlar, sana):
    """{mijoz: (kg, summa)} — sana tushgan TO'LIQ oy savdosi (maqsad bilan
    solishtirish uchun; davr filtri oyga teng bo'lmasligi mumkin)."""
    if not mijozlar:
        return {}
    d = getdate(sana)
    return {c: (flt(kg), flt(s)) for c, kg, s in frappe.db.sql(
        """
        SELECT si.customer, SUM(sii.stock_qty), SUM(sii.base_amount)
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.customer IN %(m)s
          AND si.posting_date BETWEEN %(f)s AND %(t)s
          AND it.item_group IN %(g)s
        GROUP BY si.customer
        """,
        {"m": tuple(mijozlar), "f": get_first_day(d), "t": get_last_day(d),
         "g": sotuv_guruhlari()},
    )}


def _si_kunlik(mijozlar, f, t):
    """{mijoz: {sana: summa}} — SI kunlik yig'indisi (C2 kabi: docstatus=1,
    is_return filtrisiz — qaytarish manfiy summa bilan o'zi kamaytiradi)."""
    if not mijozlar:
        return {}
    natija = {}
    for c, d, v in frappe.db.sql(
        """
        SELECT customer, posting_date, SUM(base_grand_total)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND customer IN %(m)s
          AND posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY customer, posting_date
        """,
        {"m": tuple(mijozlar), "f": f, "t": t},
    ):
        natija.setdefault(c, {})[getdate(d)] = flt(v)
    return natija


def _pul_kunlik(mijozlar, f, t):
    """{mijoz: {sana: to'lov}} — GL bo'yicha haqiqiy pul tushumi
    (voucher_type != 'Sales Invoice', ya'ni savdo nachisleniyasi emas)."""
    if not mijozlar:
        return {}
    natija = {}
    for c, d, v in frappe.db.sql(
        """
        SELECT party, posting_date, SUM(credit - debit)
        FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = 'Customer'
          AND voucher_type != 'Sales Invoice'
          AND party IN %(m)s AND posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY party, posting_date
        """,
        {"m": tuple(mijozlar), "f": f, "t": t},
    ):
        natija.setdefault(c, {})[getdate(d)] = flt(v)
    return natija


def _qarz_funksiya(mijozlar, f0, t1):
    """qarz(mijoz, sana) — GL qoldiqni istalgan sanaga beradigan funksiya.

    Har (mijoz, muddat) juftiga alohida GL so'rovi yubormaslik uchun:
    bitta so'rovda f0 dan oldingi bazaviy qoldiq, ikkinchisida f0..t1
    oralig'idagi kunlik o'zgarishlar olinadi, qoldiq prefiks-yig'indi
    (bisect) bilan topiladi."""
    if not mijozlar:
        return lambda m, s: 0.0

    baza = {p: flt(v) for p, v in frappe.db.sql(
        """
        SELECT party, SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = 'Customer'
          AND party IN %(m)s AND posting_date < %(f)s
        GROUP BY party
        """,
        {"m": tuple(mijozlar), "f": f0},
    )}
    sanalar, yigindi = {}, {}
    for p, d, v in frappe.db.sql(
        """
        SELECT party, posting_date, SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = 'Customer'
          AND party IN %(m)s AND posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY party, posting_date ORDER BY party, posting_date
        """,
        {"m": tuple(mijozlar), "f": f0, "t": t1},
    ):
        sanalar.setdefault(p, []).append(getdate(d))
        oldingi = yigindi[p][-1] if yigindi.get(p) else flt(baza.get(p))
        yigindi.setdefault(p, []).append(oldingi + flt(v))

    def qarz(mijoz, sana):
        s = sanalar.get(mijoz)
        if not s:
            return flt(baza.get(mijoz))
        i = bisect.bisect_right(s, getdate(sana))
        return yigindi[mijoz][i - 1] if i else flt(baza.get(mijoz))

    return qarz


def _oxirgi_faktura(mijozlar, sana):
    """{mijoz: (sana, summa)} — sanagacha oxirgi fakturasi (H5 sharti uchun)."""
    if not mijozlar:
        return {}
    return {c: (d, flt(v)) for c, d, v in frappe.db.sql(
        """
        SELECT customer, posting_date, base_grand_total FROM (
            SELECT customer, posting_date, base_grand_total,
                   ROW_NUMBER() OVER (PARTITION BY customer
                                      ORDER BY posting_date DESC, creation DESC) rn
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND is_return = 0
              AND customer IN %(m)s AND posting_date <= %(s)s
        ) t WHERE rn = 1
        """,
        {"m": tuple(mijozlar), "s": sana},
    )}


# --------------------------------------------------- 1. To'lov intizomi

def _oraliq(kunlik, f, t):
    return sum(v for d, v in (kunlik or {}).items() if f <= d <= t)


def _tolov_intizomi(filters):
    """Oyma-oy: mijoz kelishuvga amal qildimi (formula nazorat C2 bilan bir xil)."""
    kartalar = _kartochkalar(filters)
    mijozlar = [k.mijoz for k in kartalar]
    bugun = getdate(nowdate())

    f0 = get_first_day(getdate(filters.from_date))
    oxirgi_oy = get_first_day(getdate(filters.to_date))
    # eng uzoq muddat: oxirgi oyning keyingi oyi 28-sanasi (tolov_kuni <= 28)
    t1 = min(bugun, add_days(get_first_day(add_months(oxirgi_oy, 1)), 27))

    si = _si_kunlik(mijozlar, f0, t1)
    pul = _pul_kunlik(mijozlar, f0, t1)
    qarz_at = _qarz_funksiya(mijozlar, f0, t1)

    data = []
    oy = f0
    while oy <= oxirgi_oy:
        m_f, m_t = oy, get_last_day(oy)
        keyingi_f = add_days(m_t, 1)
        for k in kartalar:
            o = _oraliq(si.get(k.mijoz), m_f, m_t)

            if flt(k.tolov_foiz) > 0:
                # --- C2 formulasi aynan
                muddat = add_days(keyingi_f, int(k.tolov_kuni) - 1) if k.tolov_kuni else m_t
                tekshir = min(muddat, bugun)
                qarz = qarz_at(k.mijoz, tekshir)
                if not o and qarz <= 0:
                    continue
                oyna_bor = tekshir >= keyingi_f
                keyingi = _oraliq(si.get(k.mijoz), keyingi_f, tekshir) if oyna_bor else 0
                # NAXT (tolov_kuni=0) da to'lov oynasi oyning o'zi
                tolangan = _oraliq(
                    pul.get(k.mijoz), keyingi_f if oyna_bor else m_f, tekshir)
                ruxsat = o * (100 - flt(k.tolov_foiz)) / 100 + keyingi
                oshgan = max(qarz - ruxsat, 0)
                kelmagan = bugun < muddat
                holat = (("to'lashi kerak" if oshgan > BARDOSHLIK else "yaxshi")
                         if kelmagan else
                         ("buzildi" if oshgan > BARDOSHLIK else "bajarildi"))
                yopishi_kerak = o * flt(k.tolov_foiz) / 100
                shart = k.tolov_sharti or "%g%% / %s-sana" % (
                    flt(k.tolov_foiz), k.tolov_kuni or 0)
            else:
                # kelishuv kiritilmagan mijoz — qarzi/savdosi bo'lsa ko'rsatamiz
                tekshir = min(m_t, bugun)
                qarz = qarz_at(k.mijoz, tekshir)
                if not o and qarz <= BARDOSHLIK:
                    continue
                muddat = yopishi_kerak = keyingi = tolangan = ruxsat = oshgan = None
                holat, shart = "kelishuv yo'q", ""

            limit_oshdi = flt(k.limit_summa) > 0 and qarz > flt(k.limit_summa)
            if filters.get("faqat_muammoli") and holat in ("bajarildi", "yaxshi") \
                    and not limit_oshdi:
                continue

            data.append({
                "mijoz": k.mijoz,
                "oy": "%s %s" % (OYLAR[oy.month - 1], oy.year),
                "shart": shart,
                "olingan": o,
                "yopishi_kerak": yopishi_kerak,
                "muddat": muddat,
                "tolangan": tolangan,
                "keyingi_tovar": keyingi,
                "ruxsat_qarz": ruxsat,
                "qarz": qarz,
                "oshgan": oshgan,
                "holat": holat,
                "limit_summa": flt(k.limit_summa) or None,
                "limit_holat": _("LIMIT OSHDI") if limit_oshdi else "",
            })
        oy = add_months(oy, 1)

    columns = [
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 200},
        {"fieldname": "oy", "label": _("Oy (tovar olingan)"), "fieldtype": "Data", "width": 110},
        {"fieldname": "shart", "label": _("Kelishuv"), "fieldtype": "Data", "width": 110},
        {"fieldname": "olingan", "label": _("Olingan tovar"), "fieldtype": "Currency", "width": 125},
        {"fieldname": "yopishi_kerak", "label": _("Yopilishi kerak"), "fieldtype": "Currency", "width": 125},
        {"fieldname": "muddat", "label": _("Muddat"), "fieldtype": "Date", "width": 95},
        {"fieldname": "tolangan", "label": _("To'langan (oynada)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "keyingi_tovar", "label": _("Yangi tovar (muddatgacha)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "ruxsat_qarz", "label": _("Ruxsat qarz"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "qarz", "label": _("Qarz (muddatda)"), "fieldtype": "Currency", "width": 125},
        {"fieldname": "oshgan", "label": _("Oshgan"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "holat", "label": _("Holat"), "fieldtype": "Data", "width": 110},
        {"fieldname": "limit_summa", "label": _("Limit"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "limit_holat", "label": _("Limit nazorati"), "fieldtype": "Data", "width": 100},
    ]

    buzgan = [r for r in data if r["holat"] == "buzildi"]
    kutilmoqda = [r for r in data if r["holat"] == "to'lashi kerak"]
    shartsiz = {r["mijoz"] for r in data if r["holat"] == "kelishuv yo'q"}
    xulosa = [
        {"value": len({r["mijoz"] for r in buzgan}), "label": _("Buzgan mijoz"),
         "datatype": "Int", "indicator": "Red" if buzgan else "Green"},
        {"value": len(buzgan), "label": _("Buzilgan oy"), "datatype": "Int",
         "indicator": "Red" if buzgan else "Green"},
        {"value": sum(r["oshgan"] for r in buzgan), "label": _("Buzilgan summa"),
         "datatype": "Currency", "indicator": "Red" if buzgan else "Green"},
        {"value": sum(r["oshgan"] for r in kutilmoqda), "label": _("To'lashi kerak (muddat kelmagan)"),
         "datatype": "Currency", "indicator": "Orange" if kutilmoqda else "Green"},
        {"value": len(shartsiz), "label": _("Kelishuvsiz qarzdor"),
         "datatype": "Int", "indicator": "Orange" if shartsiz else "Green"},
        {"value": sum(1 for r in data if r["limit_holat"]), "label": _("Limit oshgan oy"),
         "datatype": "Int",
         "indicator": "Red" if any(r["limit_holat"] for r in data) else "Green"},
    ]
    return columns, data, None, None, xulosa


# ---------------------------------------------------- 2. Mijozlar kesimi

def _mijozlar_kesimi(filters):
    from pokiza.api.tannarx import davr_map

    kartalar = _kartochkalar(filters)
    nomlar = [k.name for k in kartalar]
    mijozlar = [k.mijoz for k in kartalar]

    qatorlar = _qator_map(nomlar)
    savdo = _savdo_map(mijozlar, filters.from_date, filters.to_date)
    qarz = _qarz_map(mijozlar, filters.to_date)
    jurnal_umumiy, _narx_j = _jurnal_oxirgi(mijozlar)
    maqsad = _maqsad_map(nomlar, filters.to_date)
    oy_fakt = _oy_fakt_map(mijozlar, filters.to_date)
    davr = davr_map(filters.to_date)
    # H5: «keyingi tovardan oldin oldingisini yopadi» belgilanganlar uchun
    fakturalar = _oxirgi_faktura(
        [k.mijoz for k in kartalar if k.oldingi_tovar_sharti], filters.to_date)

    data = []
    for k in kartalar:
        qs = qatorlar.get(k.name, [])
        aktiv = [q for q in qs if q.status == "Aktiv"]
        narxli = [q for q in aktiv if flt(q.sotuv_narxi) > 0]

        zarar = sum(1 for q in narxli if flt(q.marja_som) < 0)
        narxsiz = len(aktiv) - len(narxli)
        normasiz = sum(1 for q in aktiv if not q.norma)
        eskirgan = sum(
            1 for q in aktiv
            if q.sku in davr
            and abs(flt(davr[q.sku]["tannarx"]) - flt(q.tannarx)) > TANNARX_FARQ_CHEGARA
        )

        marjalar = [flt(q.marja_foiz) for q in narxli]
        aktiv_sku = {q.sku for q in aktiv}
        sotilgan_sku = {s for (m, s) in savdo if m == k.mijoz}
        savdo_kg = sum(savdo[(k.mijoz, s)]["kg"] for s in sotilgan_sku)
        savdo_summa = sum(savdo[(k.mijoz, s)]["summa"] for s in sotilgan_sku)

        m_kg, m_summa = maqsad.get(k.name, (0, 0))
        f_kg, f_summa = oy_fakt.get(k.mijoz, (0, 0))
        q_qoldiq = flt(qarz.get(k.mijoz))
        limit_oshdi = flt(k.limit_summa) > 0 and q_qoldiq > flt(k.limit_summa)

        # H5 sharti: qarz oxirgi fakturadan katta = oldingi tovar yopilmagan
        oldingi_yopilmagan = None
        if k.oldingi_tovar_sharti:
            _sana, oxirgi_f = fakturalar.get(k.mijoz, (None, 0))
            farq = q_qoldiq - oxirgi_f
            oldingi_yopilmagan = farq if farq > BARDOSHLIK else 0

        muammolar = []
        if zarar:
            muammolar.append(_("{0} zarar qator").format(zarar))
        if narxsiz:
            muammolar.append(_("{0} narxsiz").format(narxsiz))
        if normasiz:
            muammolar.append(_("{0} normasiz").format(normasiz))
        if eskirgan:
            muammolar.append(_("{0} eskirgan tannarx").format(eskirgan))
        if sotilgan_sku - aktiv_sku:
            muammolar.append(_("{0} SKU kartochkasiz sotilgan").format(
                len(sotilgan_sku - aktiv_sku)))
        if limit_oshdi:
            muammolar.append(_("limit oshdi"))
        if oldingi_yopilmagan:
            muammolar.append(_("oldingi tovar yopilmagan"))
        if not aktiv:
            muammolar.append(_("Aktiv qator yo'q"))

        if filters.get("faqat_muammoli") and not muammolar:
            continue

        data.append({
            "mijoz": k.mijoz,
            "holat": k.holat,
            "hudud": k.hudud,
            "masul": k.masul,
            "bonus_foiz": flt(k.bonus_foiz),
            "aktiv_soni": len(aktiv),
            "disabled_soni": len(qs) - len(aktiv),
            "ortacha_marja": (sum(marjalar) / len(marjalar)) if marjalar else None,
            "min_marja": min(marjalar) if marjalar else None,
            "zarar_soni": zarar,
            "narxsiz_soni": narxsiz,
            "normasiz_soni": normasiz,
            "eskirgan_tannarx": eskirgan,
            "savdo_kg": savdo_kg,
            "savdo_summa": savdo_summa,
            "kartochkasiz_sotuv": len(sotilgan_sku - aktiv_sku),
            "sotilmagan_aktiv": len(aktiv_sku - sotilgan_sku),
            "qarz": q_qoldiq,
            "limit_summa": flt(k.limit_summa) or None,
            "shart": k.tolov_sharti or (
                "%g%% / %s-sana" % (flt(k.tolov_foiz), k.tolov_kuni or 0)
                if flt(k.tolov_foiz) else ""),
            "oldingi_tovar": _("Ha") if k.oldingi_tovar_sharti else "",
            "oldingi_yopilmagan": oldingi_yopilmagan,
            "maqsad_summa": m_summa or None,
            "oy_fakt_summa": f_summa or None,
            "maqsad_bajarilish": (f_summa / m_summa * 100) if m_summa else None,
            "oxirgi_ozgarish": jurnal_umumiy.get(k.mijoz),
            "muammolar": ", ".join(muammolar),
        })

    columns = [
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 200},
        {"fieldname": "holat", "label": _("Holat"), "fieldtype": "Data", "width": 100},
        {"fieldname": "hudud", "label": _("Hudud"), "fieldtype": "Data", "width": 90},
        {"fieldname": "masul", "label": _("Mas'ul"), "fieldtype": "Data", "width": 100},
        {"fieldname": "bonus_foiz", "label": _("Bonus %"), "fieldtype": "Percent", "precision": 1, "width": 80},
        {"fieldname": "aktiv_soni", "label": _("Aktiv qator"), "fieldtype": "Int", "width": 85},
        {"fieldname": "disabled_soni", "label": _("Disabled"), "fieldtype": "Int", "width": 80},
        {"fieldname": "ortacha_marja", "label": _("O'rt. marja %"), "fieldtype": "Percent", "precision": 1, "width": 95},
        {"fieldname": "min_marja", "label": _("Min marja %"), "fieldtype": "Percent", "precision": 1, "width": 95},
        {"fieldname": "zarar_soni", "label": _("Zarar qator"), "fieldtype": "Int", "width": 85},
        {"fieldname": "narxsiz_soni", "label": _("Narxsiz"), "fieldtype": "Int", "width": 75},
        {"fieldname": "normasiz_soni", "label": _("Normasiz"), "fieldtype": "Int", "width": 80},
        {"fieldname": "eskirgan_tannarx", "label": _("Eskirgan tannarx"), "fieldtype": "Int", "width": 110},
        {"fieldname": "savdo_kg", "label": _("Savdo kg (davr)"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "savdo_summa", "label": _("Savdo (davr)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "kartochkasiz_sotuv", "label": _("Kartochkasiz sotuv"), "fieldtype": "Int", "width": 120},
        {"fieldname": "sotilmagan_aktiv", "label": _("Sotilmagan Aktiv"), "fieldtype": "Int", "width": 110},
        {"fieldname": "qarz", "label": _("GL qarz"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "limit_summa", "label": _("Limit"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "shart", "label": _("To'lov sharti"), "fieldtype": "Data", "width": 110},
        {"fieldname": "oldingi_tovar", "label": _("Oldingisini yopadi"), "fieldtype": "Data", "width": 110},
        {"fieldname": "oldingi_yopilmagan", "label": _("Oldingi tovar yopilmagan"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "maqsad_summa", "label": _("Oy maqsadi"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "oy_fakt_summa", "label": _("Oy fakti"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "maqsad_bajarilish", "label": _("Maqsad %"), "fieldtype": "Percent", "precision": 0, "width": 85},
        {"fieldname": "oxirgi_ozgarish", "label": _("Oxirgi o'zgarish"), "fieldtype": "Datetime", "width": 140},
        {"fieldname": "muammolar", "label": _("Muammolar"), "fieldtype": "Data", "width": 280},
    ]

    xulosa = [
        {"value": len(data), "label": _("Kartochka"), "datatype": "Int"},
        {"value": sum(r["aktiv_soni"] for r in data), "label": _("Aktiv qator"), "datatype": "Int"},
        {"value": sum(r["zarar_soni"] for r in data), "label": _("Zarar qator"), "datatype": "Int",
         "indicator": "Red" if any(r["zarar_soni"] for r in data) else "Green"},
        {"value": sum(1 for r in data if r["muammolar"]), "label": _("Muammoli kartochka"), "datatype": "Int",
         "indicator": "Orange" if any(r["muammolar"] for r in data) else "Green"},
        {"value": sum(r["savdo_summa"] for r in data), "label": _("Savdo (davr)"), "datatype": "Currency"},
        {"value": sum(r["qarz"] for r in data), "label": _("GL qarz (jami)"), "datatype": "Currency"},
    ]
    return columns, data, None, None, xulosa


# ---------------------------------------------------- 2. Qatorlar kesimi

def _qatorlar_kesimi(filters):
    from pokiza.api.tannarx import davr_map

    kartalar = _kartochkalar(filters)
    nomlar = [k.name for k in kartalar]
    mijozlar = [k.mijoz for k in kartalar]
    karta_mijoz = {k.name: k.mijoz for k in kartalar}

    qatorlar = _qator_map(nomlar)
    savdo = _savdo_map(mijozlar, filters.from_date, filters.to_date)
    narxlar = _item_price_map(mijozlar)
    _umumiy_j, narx_j = _jurnal_oxirgi(mijozlar)
    davr = davr_map(filters.to_date)

    data = []
    for nom, qs in qatorlar.items():
        mijoz = karta_mijoz[nom]
        for q in qs:
            if filters.get("status") and q.status != filters.status:
                continue

            joriy = flt(davr[q.sku]["tannarx"]) if q.sku in davr else None
            t_farq = (joriy - flt(q.tannarx)) if joriy is not None else None
            s = savdo.get((mijoz, q.sku))
            n_farq = (flt(q.sotuv_narxi) - s["oxirgi_narx"]) if s else None
            ip = narxlar.get((mijoz, q.sku))

            sinxron = ""
            if q.status == "Aktiv" and flt(q.sotuv_narxi) > 0:
                if ip is None:
                    sinxron = _("yo'q")
                elif abs(ip - flt(q.sotuv_narxi)) > 0.01:
                    sinxron = _("farq!")
                else:
                    sinxron = "✓"

            muammolar = []
            if q.status == "Aktiv":
                if flt(q.sotuv_narxi) <= 0:
                    muammolar.append(_("narx yo'q"))
                elif flt(q.marja_som) < 0:
                    muammolar.append(_("zarar"))
                if not q.norma:
                    muammolar.append(_("norma yo'q"))
                if t_farq is not None and abs(t_farq) > TANNARX_FARQ_CHEGARA:
                    muammolar.append(_("tannarx eskirgan"))
                if sinxron == _("farq!") or sinxron == _("yo'q"):
                    muammolar.append(_("Item Price: {0}").format(sinxron))
                if not s:
                    muammolar.append(_("davrda sotilmagan"))

            if filters.get("faqat_muammoli") and not muammolar:
                continue

            data.append({
                "mijoz": mijoz,
                "status": q.status,
                "sku": q.sku,
                "sku_nomi": q.sku_nomi,
                "norma": q.norma,
                "amal_sana": q.amal_sana,
                "sotuv_narxi": flt(q.sotuv_narxi),
                "bonus_foiz": flt(q.bonus_foiz),
                "bonus_keyin_narx": flt(q.bonus_keyin_narx),
                "tannarx": flt(q.tannarx),
                "joriy_tannarx": joriy,
                "tannarx_farq": t_farq,
                "marja_som": flt(q.marja_som),
                "marja_foiz": flt(q.marja_foiz),
                "savdo_kg": s["kg"] if s else 0,
                "oxirgi_sotuv_narx": s["oxirgi_narx"] if s else None,
                "narx_farq": n_farq,
                "oxirgi_sotuv_sana": s["oxirgi_sana"] if s else None,
                "item_price": ip,
                "sinxron": sinxron,
                "narx_ozgargan": narx_j.get((mijoz, q.sku)),
                "muammolar": ", ".join(muammolar),
            })

    columns = [
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 75},
        {"fieldname": "sku", "label": _("SKU"), "fieldtype": "Link", "options": "Item", "width": 160},
        {"fieldname": "sku_nomi", "label": _("Nomi"), "fieldtype": "Data", "width": 180},
        {"fieldname": "norma", "label": _("Norma"), "fieldtype": "Link", "options": "Item", "width": 130},
        {"fieldname": "amal_sana", "label": _("Amal sanasi"), "fieldtype": "Date", "width": 100},
        {"fieldname": "sotuv_narxi", "label": _("Kartochka narxi"), "fieldtype": "Currency", "width": 115},
        {"fieldname": "bonus_foiz", "label": _("Bonus %"), "fieldtype": "Percent", "precision": 1, "width": 75},
        {"fieldname": "bonus_keyin_narx", "label": _("Bonusdan keyin"), "fieldtype": "Currency", "width": 115},
        {"fieldname": "tannarx", "label": _("Tannarx (kartochka)"), "fieldtype": "Currency", "width": 125},
        {"fieldname": "joriy_tannarx", "label": _("Joriy tannarx (davr)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "tannarx_farq", "label": _("Tannarx farqi"), "fieldtype": "Currency", "width": 105},
        {"fieldname": "marja_som", "label": _("Marja so'm/kg"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "marja_foiz", "label": _("Marja %"), "fieldtype": "Percent", "precision": 1, "width": 80},
        {"fieldname": "savdo_kg", "label": _("Savdo kg (davr)"), "fieldtype": "Float", "precision": 1, "width": 105},
        {"fieldname": "oxirgi_sotuv_narx", "label": _("Oxirgi sotuv narxi"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "narx_farq", "label": _("Kartochka − sotuv"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "oxirgi_sotuv_sana", "label": _("Oxirgi sotuv"), "fieldtype": "Date", "width": 100},
        {"fieldname": "item_price", "label": _("Item Price"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "sinxron", "label": _("Sinxron"), "fieldtype": "Data", "width": 75},
        {"fieldname": "narx_ozgargan", "label": _("Narx o'zgargan"), "fieldtype": "Datetime", "width": 140},
        {"fieldname": "muammolar", "label": _("Muammolar"), "fieldtype": "Data", "width": 240},
    ]
    return columns, data


# ------------------------------------------------ 3. O'zgarishlar jurnali

def _jurnal_kesimi(filters):
    shart, qiymat = ["1=1"], {}
    if filters.get("mijoz"):
        shart.append("mijoz = %(mijoz)s")
        qiymat["mijoz"] = filters.mijoz
    if filters.get("from_date"):
        shart.append("DATE(creation) >= %(f)s")
        qiymat["f"] = filters.from_date
    if filters.get("to_date"):
        shart.append("DATE(creation) <= %(t)s")
        qiymat["t"] = filters.to_date

    data = frappe.db.sql(
        """
        SELECT creation, mijoz, sku, maydon, eski_qiymat, yangi_qiymat, kim
        FROM `tabKartochka Ozgarish Jurnali`
        WHERE %s ORDER BY creation DESC LIMIT 10000
        """ % " AND ".join(shart),
        qiymat,
        as_dict=True,
    )
    columns = [
        {"fieldname": "creation", "label": _("Vaqt"), "fieldtype": "Datetime", "width": 150},
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 200},
        {"fieldname": "sku", "label": _("SKU"), "fieldtype": "Link", "options": "Item", "width": 180},
        {"fieldname": "maydon", "label": _("Maydon"), "fieldtype": "Data", "width": 110},
        {"fieldname": "eski_qiymat", "label": _("Eski"), "fieldtype": "Data", "width": 140},
        {"fieldname": "yangi_qiymat", "label": _("Yangi"), "fieldtype": "Data", "width": 140},
        {"fieldname": "kim", "label": _("Kim"), "fieldtype": "Data", "width": 180},
    ]
    return columns, data
