"""Savdo va mijozlar: A2/H1/K1 savdo, A4/H2 o'rtacha chek, B1 mijoz rentabelligi, B2 dinamika, B3 MML, H4 jim mijozlar.

Savdo = Sales Invoice base_net_total, docstatus=1 (qaytarishlar manfiy bo'lib ayiriladi).
"""
import frappe
from frappe.utils import add_days, flt, get_first_day

from pokiza.nazorat.metrics.base import (QIZIL, SARIQ, YASHIL, Ctx, alias, foiz, metric, ozgarish,
                                          rang_chegara, rang_past, rang_trend)
from pokiza.nazorat.metrics.davr import Davr


def savdo_summa(f, t):
    return flt(frappe.db.sql(
        """SELECT SUM(base_net_total) FROM `tabSales Invoice`
        WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s""", (f, t))[0][0])


def mijoz_savdo(f, t):
    return frappe.db.sql(
        """SELECT customer, MAX(customer_name) AS nom, SUM(base_net_total) AS summa,
            SUM(CASE WHEN is_return = 0 THEN 1 ELSE 0 END) AS faktura
        FROM `tabSales Invoice` WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s
        GROUP BY customer ORDER BY summa DESC""", (f, t), as_dict=True)


def _tasdiqlanmagan(f, t):
    r = frappe.db.sql(
        """SELECT COUNT(*), SUM(base_net_total) FROM `tabSales Invoice`
        WHERE docstatus = 0 AND posting_date BETWEEN %s AND %s""", (f, t))[0]
    return int(r[0] or 0), flt(r[1])


@metric("A2", "Savdo", "so'm", "oy", "sotuv")
def savdo(ctx: Ctx):
    """Savdo (so'm) reja vs fakt. Bajarilish % = fakt / reja × 100. Rang: 95%+ / 85–95% / <85%.
    Haftalik reja = oylik reja / 4 (TZ H1); kunlik reja yo'q."""
    s = ctx.sozlama()
    fakt = savdo_summa(ctx.f, ctx.t)
    out = {"fakt": fakt, "manba": "Sales Invoice (tasdiqlangan), base_net_total"}
    r = ctx.oylik_reja()
    if r and ctx.d.turi in ("oy", "hafta"):
        reja, toliq = ctx.kesim(ctx.davr_rejasi(flt(r.savdo_reja)))
        out.update(reja=reja, reja_toliq=toliq, rang=rang_chegara(foiz(fakt, reja), s.savdo_yashil, s.savdo_sariq))
    elif ctx.d.turi in ("oy", "hafta"):
        out["izoh"] = [f"{ctx.reja_oyi():%Y-%m} uchun Oylik Reja kiritilmagan — reja bilan solishtirib bo'lmaydi."]
    if not ctx.full:
        return out
    izoh = out.setdefault("izoh", [])
    rows = mijoz_savdo(ctx.f, ctx.t)
    out["tafsilot"] = [{"mijoz": x.nom or x.customer, "summa": round(flt(x.summa)), "faktura": x.faktura,
                        "ulush_%": foiz(x.summa, fakt)} for x in rows[:30]]
    out["qism"] = {"mijozlar_soni": len(rows), "faktura_soni": sum(int(x.faktura or 0) for x in rows)}
    katta = [x for x in rows if fakt > 0 and flt(x.summa) / fakt * 100 >= s.konsentratsiya]
    if katta and ctx.d.turi != "kun":
        izoh.append("Konsentratsiya: " + ", ".join(f"{x.nom or x.customer} {foiz(x.summa, fakt)}%" for x in katta)
                    + f" (chegara {s.konsentratsiya:g}%)")
    if ctx.d.turi == "kun":
        oy_f = get_first_day(ctx.t)
        out["qism"]["oy_boshidan"] = round(savdo_summa(oy_f, ctx.t))
        if r:
            out["qism"]["oylik_reja"] = round(flt(r.savdo_reja))
            out["qism"]["oylik_bajarilish_%"] = foiz(out["qism"]["oy_boshidan"], r.savdo_reja)
    n, summa = _tasdiqlanmagan(ctx.f, ctx.t)
    if n:
        izoh.append(f"Tasdiqlanmagan (qoralama) fakturalar: {n} ta, {round(summa):,} so'm — faktga kirmagan.")
    if ctx.d.qisman and ctx.d.turi == "oy" and fakt:
        ish, jami = ctx.ish_kunlari(), ctx.ish_kunlari(ctx.f, ctx.d.tabiiy_t)
        if ish:
            out["prognoz"] = {"oy_oxiriga_taxmin": round(fakt / ish * jami),
                              "usul": f"o'tgan {ish} ish kuni o'rtachasi × {jami} ish kuni"}
    return out


alias("H1", "A2", "Haftalik savdo", "hafta")
alias("K1", "A2", "Kunlik savdo", "kun")


# donali mahsulot vazni (Item.weight_per_unit) kg'ga: gramm bo'lsa / 1000
_VAZN_KG = """IFNULL(i.weight_per_unit, 0) * CASE WHEN LOWER(IFNULL(i.weight_uom, '')) IN ('gram', 'g', 'г', 'гр', 'грамм')
    THEN 0.001 ELSE 1 END"""


def chek_qism(f, t):
    """(kg_summa, kg, dona_summa): kg'da sotilganlar + vazni kiritilgan donali mahsulotlar (vazn × dona);
    dona_summa — vazni yo'q donalilar (o'rtacha chekka kirmaydi)."""
    r = frappe.db.sql(
        f"""SELECT SUM(CASE WHEN i.stock_uom IN %(kg)s OR ({_VAZN_KG}) > 0 THEN sii.base_net_amount END) AS kg_summa,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN sii.stock_qty ELSE sii.stock_qty * ({_VAZN_KG}) END) AS kg,
            SUM(CASE WHEN i.stock_uom NOT IN %(kg)s AND ({_VAZN_KG}) = 0 THEN sii.base_net_amount END) AS dona_summa
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s""",
        {"f": f, "t": t, "kg": ("кг", "Kg", "kg")}, as_dict=True)[0]
    return flt(r.kg_summa), flt(r.kg), flt(r.dona_summa)


@metric("A4", "O'rtacha chek", "so'm/kg", "oy", "sotuv", additive=False, rang_trend=True)
def ortacha_chek(ctx: Ctx):
    """O'rtacha chek = kg'da sotilgan mahsulot savdosi / sotilgan kg. Rang oldingi davrga nisbatan:
    o'sdi / o'zgarmadi (±0.5%) / tushdi. Donali (шт) mahsulotlar Item'dagi vazni (weight_per_unit) bilan kiradi;
    vazni kiritilmaganlari kirmaydi (izohda ko'rsatiladi)."""
    summa, kg, dona = chek_qism(ctx.f, ctx.t)
    out = {"fakt": summa / kg if kg else None,
           "manba": "Sales Invoice Item: kg + donali × Item vazni (qaytarishlar ayirilgan)"}
    if not ctx.full:
        return out
    out["qism"] = {"kg": round(kg, 1), "kg_savdo": round(summa), "donali_savdo_kirmagan": round(dona)}
    rows = frappe.db.sql(
        """SELECT sii.item_code, MAX(sii.item_name) nom, SUM(sii.stock_qty) kg, SUM(sii.base_net_amount) summa
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s AND i.stock_uom IN %(kg)s
        GROUP BY sii.item_code ORDER BY kg DESC LIMIT 20""", ctx.p, as_dict=True)  # ro'yxat: kg mahsulotlar
    out["tafsilot"] = [{"mahsulot": x.nom, "kg": round(flt(x.kg), 1), "narx_kg": round(flt(x.summa) / flt(x.kg)) if flt(x.kg) else None,
                        "kg_ulush_%": foiz(x.kg, kg)} for x in rows]
    if dona:
        out["izoh"] = [f"Vazni kiritilmagan donali mahsulotlar savdosi {round(dona):,} so'm o'rtacha chekka kirmadi "
                       "(Item → Weight Per Unit to'ldirilsa kiradi)."]
    return out


alias("H2", "A4", "Haftalik o'rtacha chek", "hafta")


@metric("B1", "Mijoz rentabelligi", "%", "oy", "rahbar", additive=False)
def mijoz_rentabelligi(ctx: Ctx):
    """Mijoz rentabelligi = (savdo − tannarx − bonus) / savdo × 100, mijoz bo'yicha, past rentabellik birinchi.
    Tannarx = faktura bo'yicha GL COGS; bonus = 'Бонус' hisobidagi GL (against = mijoz).
    Umumiy (doimiy) xarajatlar mijozlarga taqsimlanmagan — bu yalpi marja."""
    # Tannarx GL'dan (faktura bo'yicha COGS): 2026-10 gacha SI qatorlarida incoming_rate 0 bo'lgan
    rows = frappe.db.sql(
        """SELECT si.customer, MAX(si.customer_name) nom, SUM(si.base_net_total) savdo, SUM(COALESCE(c.v, 0)) tannarx
        FROM `tabSales Invoice` si
        LEFT JOIN (
            SELECT g.voucher_no, SUM(g.debit - g.credit) v FROM `tabGL Entry` g
            JOIN `tabAccount` a ON a.name = g.account
            WHERE g.is_cancelled = 0 AND g.voucher_type = 'Sales Invoice' AND a.account_type = 'Cost of Goods Sold'
                AND g.posting_date BETWEEN %(f)s AND %(t)s
            GROUP BY g.voucher_no
        ) c ON c.voucher_no = si.name
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY si.customer""", ctx.p, as_dict=True)
    bonus = dict(frappe.db.sql(
        """SELECT g.against, SUM(g.debit - g.credit) FROM `tabGL Entry` g
        JOIN `tabAccount` a ON a.name = g.account
        WHERE g.is_cancelled = 0 AND a.account_name = 'Бонус' AND g.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY g.against""", ctx.p))
    jami_savdo = sum(flt(x.savdo) for x in rows)
    jami_foyda = 0
    tafsilot = []
    for x in rows:
        b = flt(bonus.pop(x.customer, 0)) + (flt(bonus.pop(x.nom, 0)) if x.nom != x.customer else 0)
        foyda = flt(x.savdo) - flt(x.tannarx) - b
        jami_foyda += foyda
        tafsilot.append({"mijoz": x.nom or x.customer, "savdo": round(flt(x.savdo)), "tannarx": round(flt(x.tannarx)),
                         "bonus": round(b), "foyda": round(foyda), "rentabellik_%": foiz(foyda, x.savdo)})
    qolgan_bonus = sum(flt(v) for v in bonus.values())
    jami_foyda -= qolgan_bonus
    s = ctx.sozlama()
    fakt = foiz(jami_foyda, jami_savdo)
    out = {"fakt": fakt, "rang": rang_chegara(fakt, s.b1_yashil, s.b1_sariq),
           "manba": "Sales Invoice + GL COGS (faktura bo'yicha) + GL 'Бонус'"}
    if ctx.full:
        tafsilot.sort(key=lambda r: (r["rentabellik_%"] is None, r["rentabellik_%"] or 0))
        out["tafsilot"] = tafsilot[:40]
        out["qism"] = {"savdo": round(jami_savdo), "yalpi_foyda": round(jami_foyda), "mijozlar": len(rows)}
        out["izoh"] = ["Yalpi marja: doimiy xarajatlar (ish haqi, svet, ijara) mijozlarga taqsimlanmagan."]
        if qolgan_bonus:
            out["izoh"].append(f"Mijozga bog'lanmagan bonus {round(qolgan_bonus):,} so'm umumiy natijadan ayirildi.")
    return out


@metric("B2", "Mijoz savdosi dinamikasi", "mijoz", "oy", "sotuv", additive=False)
def mijoz_dinamikasi(ctx: Ctx):
    """Har mijoz savdosi o'tgan davrga nisbatan. Fakt = savdosi tushgan mijozlar soni.
    Ro'yxat: eng ko'p tushganlar birinchi (qizil), o'sganlar (yashil)."""
    hozir = {x.customer: x for x in mijoz_savdo(ctx.f, ctx.t)}
    od = ctx.d.oldingi()
    oldin = {x.customer: x for x in mijoz_savdo(od.f, od.t)}
    rows = []
    for c in set(hozir) | set(oldin):
        a, b = flt(hozir[c].summa) if c in hozir else 0, flt(oldin[c].summa) if c in oldin else 0
        nom = (hozir.get(c) or oldin.get(c)).nom or c
        rows.append({"mijoz": nom, "hozir": round(a), "oldin": round(b), "farq": round(a - b),
                     "ozgarish_%": ozgarish(a, b), "rang": YASHIL if a > b else QIZIL if a < b else SARIQ})
    tushgan = [r for r in rows if r["farq"] < 0]
    s = ctx.sozlama()
    out = {"fakt": len(tushgan), "rang": rang_past(foiz(len(tushgan), len(rows)) if rows else None, s.b2_yashil, s.b2_sariq),
           "manba": "Sales Invoice, mijoz bo'yicha, oldingi teng davr bilan"}
    if ctx.full:
        rows.sort(key=lambda r: r["farq"])
        out["tafsilot"] = rows[:40]
        out["qism"] = {"tushgan": len(tushgan), "osgan": sum(1 for r in rows if r["farq"] > 0),
                       "yangi": sum(1 for r in rows if not r["oldin"] and r["hozir"]),
                       "yoqolgan": sum(1 for r in rows if r["oldin"] and not r["hozir"]),
                       "solishtirildi": od.nom}
    return out


@metric("B3", "Top mahsulotlar (daromadning 50%i)", "mahsulot", "oy", "sotuv", additive=False)
def mml(ctx: Ctx):
    """Mahsulotlar savdo bo'yicha saralanadi; kumulativ 50% gacha bo'lganlari — asosiy daromad manbai.
    Fakt = 50% savdoni beradigan mahsulotlar soni."""
    rows = frappe.db.sql(
        """SELECT sii.item_code, MAX(sii.item_name) nom, SUM(sii.base_net_amount) summa, SUM(sii.stock_qty) miqdor,
            MAX(sii.stock_uom) birlik
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY sii.item_code HAVING summa > 0 ORDER BY summa DESC""", ctx.p, as_dict=True)
    jami = sum(flt(x.summa) for x in rows)
    kum, top = 0, []
    for x in rows:
        if jami and kum / jami >= 0.5:
            break
        kum += flt(x.summa)
        top.append({"mahsulot": x.nom, "summa": round(flt(x.summa)), "miqdor": round(flt(x.miqdor), 1),
                    "birlik": x.birlik, "ulush_%": foiz(x.summa, jami), "kumulativ_%": foiz(kum, jami)})
    s = ctx.sozlama()
    out = {"fakt": len(top), "rang": rang_chegara(len(top), s.b3_yashil, s.b3_sariq) if top else None,
           "manba": "Sales Invoice Item, mahsulot bo'yicha"}
    if ctx.full:
        out["tafsilot"] = top
        out["qism"] = {"jami_mahsulot": len(rows), "jami_savdo": round(jami)}
    return out


@metric("H4", "7 kun buyurtma bermagan mijozlar", "mijoz", "hafta", "sotuv", additive=False)
def jim_mijozlar(ctx: Ctx):
    """Davr oxiriga kelib oxirgi xaridi 7 kundan (sozlanadi) oldin bo'lgan faol mijozlar
    (oxirgi 90 kunda kamida bitta xarid). Rang: 0 — yashil, bor — qizil."""
    s = ctx.sozlama()
    rows = frappe.db.sql(
        """SELECT customer, MAX(customer_name) nom, MAX(posting_date) oxirgi, COUNT(*) soni,
            MIN(posting_date) birinchi
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0 AND posting_date BETWEEN %s AND %s
        GROUP BY customer""", (add_days(ctx.t, -90), ctx.t), as_dict=True)
    jim = []
    for x in rows:
        kun = (ctx.t - x.oxirgi).days
        if kun >= s.jimlik_kun:
            orta = round((x.oxirgi - x.birinchi).days / (x.soni - 1), 1) if x.soni > 1 else None
            jim.append({"mijoz": x.nom or x.customer, "oxirgi_xarid": str(x.oxirgi), "jim_kun": kun,
                        "ortacha_oraliq_kun": orta})
    jim.sort(key=lambda r: r["jim_kun"])
    out = {"fakt": len(jim), "rang": YASHIL if not jim else QIZIL,
           "manba": f"Sales Invoice: oxirgi xarid {ctx.t} holatiga"}
    if ctx.full:
        out["tafsilot"] = jim
        out["qism"] = {"faol_mijozlar_90_kun": len(rows), "chegara_kun": s.jimlik_kun}
    return out


@metric("B4", "Mahsulot mix va kategoriya rentabelligi", "%", "oy", "rahbar", additive=False)
def kategoriya_mix(ctx: Ctx):
    """Kategoriya ulushi = kategoriya hajmi (kg) / umumiy hajm × 100; rentabellik = (savdo − tannarx) / savdo.
    Kategoriya: Item.custom_kategoriya (sosiska / kopchyonniy / varyonniy / delikates / boshqa).
    Tannarx — Stock Ledger (faktura qatori bo'yicha). Fakt = kategoriyalangan mahsulotlarning yalpi marjasi %."""
    if not frappe.db.has_column("Item", "custom_kategoriya"):
        return {"fakt": None, "izoh": ["Kategoriya maydoni hali yaratilmagan (migrate)."]}
    rows = frappe.db.sql(
        """SELECT COALESCE(NULLIF(i.custom_kategoriya, ''), 'belgilanmagan') kat,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN sii.stock_qty ELSE 0 END) kg,
            SUM(sii.base_net_amount) savdo, SUM(-COALESCE(sle.v, 0)) tannarx
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        LEFT JOIN (
            SELECT voucher_detail_no, SUM(stock_value_difference) v FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0 AND voucher_type = 'Sales Invoice' AND posting_date BETWEEN %(f)s AND %(t)s
            GROUP BY voucher_detail_no
        ) sle ON sle.voucher_detail_no = sii.name
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY kat ORDER BY savdo DESC""", ctx.p, as_dict=True)
    jami_kg = sum(flt(r.kg) for r in rows)
    jami_savdo = sum(flt(r.savdo) for r in rows)
    bel = [r for r in rows if r.kat != "belgilanmagan"]
    b_savdo = sum(flt(r.savdo) for r in bel)
    s = ctx.sozlama()
    fakt = foiz(b_savdo - sum(flt(r.tannarx) for r in bel), b_savdo) if bel else None
    out = {"fakt": fakt, "rang": rang_chegara(fakt, s.b4_yashil, s.b4_sariq),
           "manba": "Sales Invoice Item + Item.custom_kategoriya + Stock Ledger tannarx"}
    nob = next((r for r in rows if r.kat == "belgilanmagan"), None)
    if nob and flt(nob.savdo) > 0.02 * max(jami_savdo, 1):
        out["izoh"] = [f"Savdoning {foiz(nob.savdo, jami_savdo)}% i kategoriyasiz mahsulotlarda — "
                       "pokiza.nazorat.setup.taklif / qollash bilan to'ldiring."]
    if ctx.full:
        out["tafsilot"] = [{"kategoriya": r.kat, "kg": round(flt(r.kg), 1), "kg_ulush_%": foiz(r.kg, jami_kg),
                            "savdo": round(flt(r.savdo)), "savdo_ulush_%": foiz(r.savdo, jami_savdo),
                            "yalpi_marja_%": foiz(flt(r.savdo) - flt(r.tannarx), r.savdo)} for r in rows]
    return out
