"""To'lov intizomi: C1 postavshiklarga to'lov, C2 mijozlardan to'lov (debitorlik), H5 nazoratdagi mijozlar.

Qarz qoldig'i faqat GL bo'yicha (party_type + party). Sales Invoice.outstanding_amount ishlatilmaydi:
to'lovlar fakturalarga bog'lanmagan, u yerdagi qiymat noto'g'ri (jami 24 mlrd vs GL 3,4 mlrd).
"""
from datetime import timedelta

import frappe
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate, nowdate

from pokiza.nazorat.metrics.base import QIZIL, SARIQ, YASHIL, Ctx, foiz, metric


def _qoldiq(party_type, sana, belgi=1):
    """{party: qoldiq} sana holatiga. Customer: debet−kredit (bizga qarz); Supplier: belgi=-1 (biz qarzmiz)."""
    return {p: belgi * flt(v) for p, v in frappe.db.sql(
        """SELECT party, SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = %s AND posting_date <= %s GROUP BY party""", (party_type, sana))}


def _rang_oraliq(qiymat, yashil=(98, 102), sariq=(90, 110)):
    if qiymat is None:
        return None
    if yashil[0] <= qiymat <= yashil[1]:
        return YASHIL
    return SARIQ if sariq[0] <= qiymat <= sariq[1] else QIZIL


@metric("C1", "Postavshiklarga to'lov", "%", "oy", "buxgalteriya", additive=False, davrlar=("oy",))
def postavshik(ctx: Ctx):
    """Qoida: M oyda olingan tovar M+1 oyning 10-sanasigacha (sozlanadi) yopiladi — ortiqcha ham, kam ham emas.
    Yopilgan = M oy 11-sanadan M+1 oy 10-sanagacha postavshikka to'lovlar (Purchase Invoice'dan boshqa GL).
    Fakt = yopilgan / olingan × 100. Rang: 98–102% / 90–110% / boshqa. Ostatka — oyna oxiridagi qoldiq."""
    k = ctx.sozlama().tolov_kuni
    oyna_f = add_days(ctx.f, k)
    oyna_t = add_days(get_first_day(add_days(get_last_day(ctx.f), 1)), k - 1)
    bugun = getdate(nowdate())
    p = {"f": ctx.f, "t": get_last_day(ctx.f), "of": oyna_f, "ot": min(oyna_t, bugun)}
    olingan = dict(frappe.db.sql(
        """SELECT supplier, SUM(base_grand_total) FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND posting_date BETWEEN %(f)s AND %(t)s GROUP BY supplier""", p))
    tolangan = dict(frappe.db.sql(
        """SELECT party, SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = 'Supplier' AND voucher_type != 'Purchase Invoice'
            AND posting_date BETWEEN %(of)s AND %(ot)s GROUP BY party""", p))
    jami_o, jami_t = sum(map(flt, olingan.values())), sum(flt(tolangan.get(s)) for s in olingan)
    fakt = foiz(jami_t, jami_o)
    davom = bugun < oyna_t
    out = {"fakt": fakt, "rang": None if davom else _rang_oraliq(fakt),
           "manba": f"Purchase Invoice ({ctx.f:%m.%Y}) vs to'lovlar {oyna_f:%d.%m}–{oyna_t:%d.%m.%Y} (GL Supplier)"}
    if davom:
        out["izoh"] = [f"To'lov oynasi {oyna_t:%d.%m.%Y} da yopiladi — hozircha oraliq natija."]
    if not ctx.full:
        return out
    qoldiq = _qoldiq("Supplier", min(oyna_t, bugun), belgi=-1)
    rows = []
    for s, o in olingan.items():
        t = flt(tolangan.get(s))
        r = foiz(t, o)
        rows.append({"postavshik": s, "olingan": round(flt(o)), "yopilgan": round(t), "farq": round(t - flt(o)),
                     "yopish_%": r, "ostatka": round(qoldiq.get(s, 0)),
                     "holat": "ortiqcha" if t > flt(o) * 1.02 else "kam" if t < flt(o) * 0.98 else "to'g'ri",
                     "rang": None if davom else _rang_oraliq(r)})
    boshqa = {s: v for s, v in tolangan.items() if s not in olingan and flt(v) > 0}
    rows.sort(key=lambda r: -abs(r["farq"]))
    out["tafsilot"] = rows[:40]
    out["qism"] = {"olingan": round(jami_o), "yopilgan": round(jami_t), "farq": round(jami_t - jami_o),
                   "ortiqcha_yopganlar": sum(1 for r in rows if r["holat"] == "ortiqcha"),
                   "kam_yopganlar": sum(1 for r in rows if r["holat"] == "kam"),
                   "jami_ostatka": round(sum(v for v in qoldiq.values() if v > 0)),
                   "oyna": f"{oyna_f} .. {oyna_t}"}
    if boshqa:
        out.setdefault("izoh", []).append(
            f"Bu oyda xaridi bo'lmagan {len(boshqa)} postavshikka {round(sum(boshqa.values())):,} so'm to'langan "
            "(eski ostatka yoki avans).")
    return out


def _kartochka_shartlari():
    return {r.mijoz: r for r in frappe.get_all(
        "Mijoz Kartochkasi", filters={"tolov_foiz": [">", 0]},
        fields=["mijoz", "tolov_foiz", "tolov_kuni", "tolov_sharti"])}


@metric("C2", "Mijozlardan to'lov (debitorlik)", "mijoz", "oy", "buxgalteriya", additive=False, davrlar=("oy",))
def debitorlik(ctx: Ctx):
    """Har mijoz kelishuvi (Mijoz Kartochkasi: yopiladigan %, to'lov kuni). M oy tovari uchun to'lov kunida
    (M+1 oyning X-sanasi; naqd = M oy oxiri) GL qarzi ruxsatdan oshmasligi kerak:
    ruxsat = M oy tovarining (100 − foiz)% + X sanagacha olingan yangi tovar. Ushlab qolingan qism aylanadi:
    qarz hech qachon oxirgi oy tovarining 30% (70/30 da) dan oshmasligi kerak.
    Fakt = kelishuvni buzgan mijozlar soni."""
    shart = _kartochka_shartlari()
    bugun = getdate(nowdate())
    m_f, m_t = ctx.f, get_last_day(ctx.f)
    keyingi_f = add_days(m_t, 1)
    olingan = dict(frappe.db.sql(
        """SELECT customer, SUM(base_grand_total) FROM `tabSales Invoice`
        WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s GROUP BY customer""", (m_f, m_t)))
    rows, qoldiq_cache = [], {}
    for mijoz, s in shart.items():
        muddat = add_days(keyingi_f, int(s.tolov_kuni) - 1) if s.tolov_kuni else m_t
        tekshir = min(muddat, bugun)
        if tekshir not in qoldiq_cache:
            qoldiq_cache[tekshir] = _qoldiq("Customer", tekshir)
        qarz = qoldiq_cache[tekshir].get(mijoz, 0)
        keyingi = flt(frappe.db.sql(
            """SELECT SUM(base_grand_total) FROM `tabSales Invoice` WHERE docstatus = 1 AND customer = %s
            AND posting_date BETWEEN %s AND %s""", (mijoz, keyingi_f, tekshir))[0][0]) if tekshir >= keyingi_f else 0
        o = flt(olingan.get(mijoz))
        ruxsat = o * (100 - flt(s.tolov_foiz)) / 100 + keyingi
        oshgan = qarz - ruxsat
        kelmagan = bugun < muddat
        if not o and qarz <= 0:
            continue
        rows.append({"mijoz": mijoz, "shart": s.tolov_sharti or f"{s.tolov_foiz:g}% / {s.tolov_kuni}-sana",
                     "muddat": str(muddat), "olingan_M": round(o), "qarz": round(qarz), "ruxsat_qarz": round(ruxsat),
                     "oshgan": round(max(oshgan, 0)),
                     "holat": ("to'lashi kerak" if oshgan > 1000 else "yaxshi") if kelmagan
                     else ("buzildi" if oshgan > 1000 else "bajarildi"),
                     "rang": (SARIQ if oshgan > 1000 else YASHIL) if kelmagan else (QIZIL if oshgan > 1000 else YASHIL)})
    buzgan = [r for r in rows if r["holat"] == "buzildi"]
    out = {"fakt": len(buzgan), "rang": YASHIL if not buzgan else QIZIL,
           "manba": "Mijoz Kartochkasi shartlari + GL qarz qoldig'i (to'lov kuni holatiga)"}
    if not ctx.full:
        return out
    rows.sort(key=lambda r: -r["oshgan"])
    out["tafsilot"] = rows
    jami_qarz = _qoldiq("Customer", min(get_last_day(keyingi_f), bugun))
    sharsiz = {c: v for c, v in jami_qarz.items() if c not in shart and v > 1000}
    out["qism"] = {"buzgan": len(buzgan), "buzilgan_summa": round(sum(r["oshgan"] for r in buzgan)),
                   "muddati_kelmagan_tolashi_kerak": round(sum(r["oshgan"] for r in rows if r["holat"] == "to'lashi kerak")),
                   "kelishuvli_mijozlar": len(shart), "kelishuvsiz_qarzdorlar": len(sharsiz),
                   "kelishuvsiz_qarz": round(sum(sharsiz.values()))}
    if sharsiz:
        out["izoh"] = [f"{len(sharsiz)} ta qarzdor mijozda to'lov kelishuvi kiritilmagan "
                       f"({round(sum(sharsiz.values())):,} so'm) — Mijoz Kartochkasi'da to'ldiring."]
    return out


@metric("H5", "Nazoratdagi mijozlar (oldingi tovarni yopish)", "mijoz", "hafta", "sotuv", additive=False)
def nazoratdagi_mijozlar(ctx: Ctx):
    """'Keyingi tovardan oldin oldingisini yopish' sharti belgilangan mijozlar: qarz oxirgi fakturadan katta
    bo'lsa — oldingi tovar puli yopilmagan; yangi tovar berishdan oldin farqni undirish kerak."""
    mijozlar = frappe.get_all("Mijoz Kartochkasi", filters={"oldingi_tovar_sharti": 1}, pluck="mijoz")
    if not mijozlar:
        return {"fakt": None, "izoh": ["Hech bir mijoz kartochkasida 'keyingi tovardan oldin oldingisini yopadi' "
                                       "belgilanmagan."], "manba": "Mijoz Kartochkasi"}
    qoldiq = _qoldiq("Customer", ctx.t)
    rows = []
    for m in mijozlar:
        last = frappe.db.sql(
            """SELECT posting_date, base_grand_total FROM `tabSales Invoice` WHERE docstatus = 1 AND is_return = 0
            AND customer = %s AND posting_date <= %s ORDER BY posting_date DESC, creation DESC LIMIT 1""",
            (m, ctx.t), as_dict=True)
        oxirgi = flt(last[0].base_grand_total) if last else 0
        qarz = qoldiq.get(m, 0)
        if qarz - oxirgi > 1000:
            rows.append({"mijoz": m, "qarz": round(qarz), "oxirgi_faktura": round(oxirgi),
                         "oxirgi_sana": str(last[0].posting_date) if last else None,
                         "yopishi_kerak": round(qarz - oxirgi)})
    rows.sort(key=lambda r: -r["yopishi_kerak"])
    out = {"fakt": len(rows), "rang": YASHIL if not rows else QIZIL,
           "manba": f"Mijoz Kartochkasi (shart) + GL qarz {ctx.t} holatiga"}
    if ctx.full:
        out["tafsilot"] = rows
        out["qism"] = {"nazoratdagi": len(mijozlar), "yopmaganlar": len(rows)}
    return out
