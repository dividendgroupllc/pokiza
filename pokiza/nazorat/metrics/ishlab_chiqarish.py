"""Ishlab chiqarish: A1/H3/K2 quvvatdan foydalanish, C4 brak va vozvrat.

Fakt = Production Entry (docstatus=1) qty_to_manufacture, faqat kg'dagi normalar.
"""
import frappe
from frappe.utils import flt

from pokiza.nazorat.metrics.base import Ctx, alias, foiz, metric, rang_chegara, rang_past


def ishlab_kg(f, t):
    return flt(frappe.db.sql(
        """SELECT SUM(p.qty_to_manufacture) FROM `tabProduction Entry` p
        JOIN `tabItem` i ON i.name = p.item_to_manufacture
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s AND i.stock_uom IN %(kg)s""",
        {"f": f, "t": t, "kg": ("кг", "Kg", "kg")})[0][0])


@metric("A1", "Quvvatdan foydalanish", "tonna", "oy", "ishlab_chiqarish")
def quvvat(ctx: Ctx):
    """Quvvat band % = ishlab chiqarilgan tonna / TO'LIQ quvvat × 100 (TZ: oy — 180 t, Nazorat Sozlamalari);
    Oylik Reja tonnasi bo'lsa — rejaga nisbatan % alohida (qism.rejaga_%).
    Hafta/kun: kunlik quvvat (6900 kg) × ish kunlari. Rang: 90%+ / 70–90% / <70%."""
    s = ctx.sozlama()
    fakt = ishlab_kg(ctx.f, ctx.t) / 1000
    rejaga = None
    if ctx.d.turi == "oy":
        reja, reja_toliq = ctx.kesim(s.oylik_quvvat_t)
        manba_reja = f"to'liq quvvat {s.oylik_quvvat_t:g} t (Nazorat Sozlamalari)"
        r = ctx.oylik_reja()
        if r and flt(r.quvvat_reja_t):
            oy_reja, _ = ctx.kesim(flt(r.quvvat_reja_t))
            rejaga = {"reja_t": flt(r.quvvat_reja_t), "rejaga_%": foiz(fakt, oy_reja)}
    else:
        reja, reja_toliq = ctx.kesim(s.kunlik_quvvat_kg * ctx.ish_kunlari(ctx.f, ctx.d.tabiiy_t) / 1000)
        manba_reja = f"kunlik quvvat {s.kunlik_quvvat_kg:g} kg × ish kunlari"
    out = {"fakt": fakt, "reja": reja, "reja_toliq": reja_toliq,
           "rang": rang_chegara(foiz(fakt, reja), s.quvvat_yashil, s.quvvat_sariq) if reja else None,
           "manba": f"Production Entry (kg). Reja: {manba_reja}"}
    if rejaga:
        out["qism"] = dict(rejaga)
    if ctx.d.turi == "kun" and not ctx.ish_kunlari():
        out.update(reja=None, rang=None, izoh=["Dam olish kuni"])
    if not ctx.full:
        return out
    kunlar = frappe.db.sql(
        """SELECT COUNT(DISTINCT posting_date) FROM `tabProduction Entry`
        WHERE docstatus = 1 AND posting_date BETWEEN %s AND %s""", (ctx.f, ctx.t))[0][0]
    out["qism"] = {"kg": round(fakt * 1000, 1), "ishlangan_kunlar": kunlar, "kalendar_ish_kunlari": ctx.ish_kunlari(),
                   "kunlik_ortacha_kg": round(fakt * 1000 / kunlar) if kunlar else None,
                   "kunlik_quvvat_kg": s.kunlik_quvvat_kg, **(rejaga or {})}
    rows = frappe.db.sql(
        """SELECT p.item_to_manufacture norma, SUM(p.qty_to_manufacture) kg, COUNT(*) pe
        FROM `tabProduction Entry` p JOIN `tabItem` i ON i.name = p.item_to_manufacture
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s AND i.stock_uom IN %(kg)s
        GROUP BY p.item_to_manufacture ORDER BY kg DESC LIMIT 25""", ctx.p, as_dict=True)
    out["tafsilot"] = [{"norma": x.norma, "kg": round(flt(x.kg), 1), "ulush_%": foiz(x.kg, fakt * 1000), "pe": x.pe}
                       for x in rows]
    return out


alias("H3", "A1", "Haftalik quvvat", "hafta")
alias("K2", "A1", "Kunlik ishlab chiqarish", "kun")


@metric("C4", "Brak va vozvrat", "%", "oy", "ishlab_chiqarish", additive=False)
def brak(ctx: Ctx):
    """Brak % = brak kg / ishlab chiqarilgan kg × 100.
    Brak — kun oxirida «Brak» oynasidan yoziladi: ГП skladdan Material Issue, qiymati «Брак» rasxod hisobiga
    (pokiza.api.navbat.brak_vozvrat). Bekor qilingan (docstatus=2) hujjatlar kirmaydi.
    Vozvrat = qaytarilgan tovar (Sales Invoice is_return) kg va summada."""
    kg = ishlab_kg(ctx.f, ctx.t)
    hisob = brak_hisobi()
    b = _brak_qatorlar(ctx, hisob)
    brak_kg = sum(flt(x.kg) for x in b)
    out = {"fakt": round(brak_kg / kg * 100, 2) if brak_kg and kg else (0 if hisob and kg else None),
           "manba": "Brak: Stock Entry (Material Issue → «Брак» hisobi); vozvrat — Sales Invoice (is_return=1)"}
    if not hisob:
        out["izoh"] = ["«Брак» rasxod hisobi topilmadi — brak hisoblanmadi."]
    elif not brak_kg:
        out["izoh"] = ["Bu davrda brak yozilmagan (Material Issue → «Брак» yo'q)."]
    else:  # brak yozilmagan bo'lsa rang qo'yilmaydi ("0%" yashil bo'lib aldamasin)
        s = ctx.sozlama()
        out["rang"] = rang_past(out["fakt"], s.c4_yashil, s.c4_sariq)
    if not ctx.full:
        return out
    v = frappe.db.sql(
        """SELECT si.customer_name mijoz, -SUM(sii.base_net_amount) summa,
            -SUM(CASE WHEN i.stock_uom IN %(kg)s THEN sii.stock_qty ELSE 0 END) kg
        FROM `tabSales Invoice Item` sii JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 1 AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY si.customer_name ORDER BY summa DESC""", ctx.p, as_dict=True)
    brak_summa = flt(frappe.db.sql(
        """SELECT SUM(debit - credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND account = %s AND posting_date BETWEEN %s AND %s""", (hisob, ctx.f, ctx.t))[0][0]) if hisob else 0
    out["qism"] = {"ishlab_chiqarilgan_kg": round(kg, 1), "brak_kg": round(brak_kg, 1), "brak_summa": round(brak_summa),
                   "vozvrat_kg": round(sum(flt(x.kg) for x in v), 1),
                   "vozvrat_summa": round(sum(flt(x.summa) for x in v)),
                   "vozvrat_kg_%": foiz(sum(flt(x.kg) for x in v), kg)}
    out["tafsilot"] = (
        [{"turi": "brak", "nomi": x.nom, "kg": round(flt(x.kg), 1), "summa": round(flt(x.summa))} for x in b[:30]]
        + [{"turi": "vozvrat", "nomi": x.mijoz, "kg": round(flt(x.kg), 1), "summa": round(flt(x.summa))} for x in v[:30]])
    return out


def brak_hisobi():
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    return frappe.db.get_value("Account", {"account_name": "Брак", "company": company, "is_group": 0})


def _brak_qatorlar(ctx, hisob):
    """Brak Material Issue'lari mahsulot kesimida (kg, tannarx summasi)."""
    if not hisob:
        return []
    return frappe.db.sql(
        """SELECT d.item_code, MAX(d.item_name) nom, SUM(d.transfer_qty) kg, SUM(d.amount) summa
        FROM `tabStock Entry Detail` d JOIN `tabStock Entry` se ON se.name = d.parent
        WHERE se.docstatus = 1 AND se.purpose = 'Material Issue' AND d.expense_account = %(h)s
          AND se.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY d.item_code ORDER BY kg DESC""", {**ctx.p, "h": hisob}, as_dict=True)
