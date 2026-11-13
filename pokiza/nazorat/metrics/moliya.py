"""Moliya: A3 sof rentabellik, A5 sof daromad ($), C3 xarajatlar, C5/K4 dividend, K3 kassa kirimi.

Sof foyda = GL Income − GL Expense (tannarx Sales Invoice update_stock bilan COGS'ga yoziladi).
"""
import frappe
from frappe.utils import flt, get_first_day

from pokiza.nazorat.metrics.base import (QIZIL, SARIQ, YASHIL, Ctx, alias, foiz, metric, rang_chegara, rang_past,
                                          rang_trend)
from pokiza.nazorat.metrics.savdo import savdo_summa

MAXSUS = {"Cost of Goods Sold": "tannarx", "Stock Adjustment": "ombor_tuzatish", "Round Off": "boshqa"}


def pl(f, t):
    """{income, expense, sof_foyda, hisoblar:[...]} — GL bo'yicha."""
    rows = frappe.db.sql(
        """SELECT a.name, a.account_name, a.root_type, a.account_type, SUM(g.debit - g.credit) v
        FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name = g.account
        WHERE g.is_cancelled = 0 AND g.posting_date BETWEEN %s AND %s AND a.root_type IN ('Income', 'Expense')
        GROUP BY a.name""", (f, t), as_dict=True)
    income = -sum(flt(r.v) for r in rows if r.root_type == "Income")
    expense = sum(flt(r.v) for r in rows if r.root_type == "Expense")
    return frappe._dict(income=income, expense=expense, sof_foyda=income - expense,
                        hisoblar=[r for r in rows if r.root_type == "Expense"])


def _pl_qism(p):
    by = {"tannarx": 0, "ombor_tuzatish": 0, "boshqa": 0, "xarajat": 0}
    for r in p.hisoblar:
        k = MAXSUS.get(r.account_type) or ("boshqa" if "Exchange" in r.name else "xarajat")
        by[k] += flt(r.v)
    return by


@metric("A3", "Sof rentabellik", "%", "oy", "rahbar", additive=False)
def sof_rentabellik(ctx: Ctx):
    """Sof rentabellik % = sof foyda / savdo × 100. Rang: rejada yoki yuqori (0.5 pp gacha past) / 0.5–1 pp past /
    1 pp+ past. Reja bo'lmasa — oldingi davrga nisbatan o'sdi/tushdi."""
    s = ctx.sozlama()
    p = pl(ctx.f, ctx.t)
    savdo = savdo_summa(ctx.f, ctx.t)
    fakt = foiz(p.sof_foyda, savdo)
    out = {"fakt": fakt, "manba": "GL: Income − Expense; savdo — Sales Invoice"}
    r = ctx.oylik_reja()
    if r and flt(r.sof_marja_reja) and fakt is not None:
        reja = flt(r.sof_marja_reja)
        farq = round(fakt - reja, 2)
        # TZ: rejada va undan yuqori — yashil; rejadan qizil chegarasigacha past — sariq; undan past — qizil
        out.update(reja=reja, rang=YASHIL if farq >= 0 else SARIQ if farq > -s.marja_qizil_pp else QIZIL)
        out["qism"] = {"rejadan_farq_pp": farq}
    if not ctx.full:
        return out
    by = _pl_qism(p)
    out.setdefault("qism", {}).update({
        "savdo": round(savdo), "daromad_gl": round(p.income), "tannarx": round(by["tannarx"]),
        "xarajatlar": round(by["xarajat"]), "ombor_tuzatish": round(by["ombor_tuzatish"]),
        "boshqa": round(by["boshqa"]), "sof_foyda": round(p.sof_foyda)})
    izoh = []
    if abs(by["ombor_tuzatish"]) > 0.01 * max(savdo, 1):
        izoh.append(f"Stock Adjustment {round(by['ombor_tuzatish']):,} so'm sof foydaga ta'sir qilgan "
                    "(inventarizatsiya/qayta baholash) — operatsion foyda emas.")
    if not r or not flt(r.sof_marja_reja):
        izoh.append("Sof rentabellik rejasi kiritilmagan — rang oldingi davr bilan solishtirildi.")
    out["izoh"] = izoh
    return out


@metric("A5", "Sof daromad", "$", "oy", "rahbar")
def sof_daromad(ctx: Ctx):
    """Sof daromad ($) = sof foyda (so'm) / kurs. Maqsad $50K/oy. Rang: $50K+ / $40–50K / <$40K
    (qisman davrda chegaralar o'tgan ish kunlariga proporsional)."""
    s = ctx.sozlama()
    ki = ctx.kurs_info()
    kurs = ki["kurs"]
    p = pl(ctx.f, ctx.t)
    if not kurs:
        return {"fakt": None, "manba": "Currency Exchange (USD→UZS)",
                "izoh": ["Currency Exchange'da USD→UZS kursi yo'q — sof daromadni dollarda hisoblab bo'lmaydi. "
                         "Kursni kiriting."]}
    fakt = p.sof_foyda / kurs
    r = ctx.oylik_reja()
    maqsad = flt(r.sof_daromad_usd_reja) if r and flt(r.sof_daromad_usd_reja) else s.daromad_yashil
    reja, toliq = ctx.kesim(ctx.davr_rejasi(maqsad))
    ulush = (reja / maqsad) if maqsad else 1
    out = {"fakt": fakt, "reja": reja, "reja_toliq": toliq,
           "rang": rang_chegara(fakt, s.daromad_yashil * ulush, s.daromad_sariq * ulush) if ctx.d.turi == "oy" else None,
           "manba": f"GL sof foyda / kurs {kurs:,.0f} (Currency Exchange, {ki['sana']:%d.%m.%Y})"}
    if ctx.full:
        out["qism"] = {"sof_foyda_som": round(p.sof_foyda), "kurs": kurs, "kurs_sanasi": str(ki["sana"])}
        izoh = []
        if (ctx.t - ki["sana"]).days > 45:
            izoh.append(f"Kurs eskirgan: Currency Exchange'da oxirgi USD→UZS {ki['sana']:%d.%m.%Y} ({kurs:,.0f}). "
                        "Yangi kursni kiriting.")
        if ctx.d.turi != "oy":
            izoh.append("$50K maqsad oylik; haftalik/kunlik reja oylikdan ulush sifatida olingan.")
        out["izoh"] = izoh
    return out


@metric("C3", "Xarajatlar", "%", "oy", "buxgalteriya", additive=False)
def xarajatlar(ctx: Ctx):
    """Xarajat % = xarajat summasi / savdo × 100 (tannarx — xomashyo — alohida). Doimiy va o'zgaruvchi
    xarajatlar Account.custom_xarajat_turi bo'yicha ajratiladi (belgilanmaganlar alohida)."""
    p = pl(ctx.f, ctx.t)
    savdo = savdo_summa(ctx.f, ctx.t)
    tur_bor = frappe.db.has_column("Account", "custom_xarajat_turi")
    turlar = dict(frappe.db.sql("SELECT name, custom_xarajat_turi FROM `tabAccount` WHERE root_type = 'Expense'")) if tur_bor else {}
    guruh, tafsilot, tannarx = {}, [], 0
    for r in p.hisoblar:
        if r.account_type in MAXSUS or "Exchange" in r.name:
            if r.account_type == "Cost of Goods Sold":
                tannarx += flt(r.v)
            continue
        tur = turlar.get(r.name) or "belgilanmagan"
        guruh[tur] = guruh.get(tur, 0) + flt(r.v)
        tafsilot.append({"hisob": r.account_name, "turi": tur, "summa": round(flt(r.v)), "savdoga_%": foiz(r.v, savdo)})
    jami = sum(guruh.values())
    s = ctx.sozlama()
    fakt = foiz(jami, savdo)
    out = {"fakt": fakt, "rang": rang_past(fakt, s.c3_yashil, s.c3_sariq),
           "manba": "GL Expense hisoblari (COGS, Stock Adjustment, kurs farqi chiqarilgan)"}
    if ctx.full:
        tafsilot.sort(key=lambda r: -r["summa"])
        out["tafsilot"] = tafsilot
        out["qism"] = {"jami_xarajat": round(jami), "savdo": round(savdo), "tannarx_xomashyo": round(tannarx),
                       "tannarx_savdoga_%": foiz(tannarx, savdo),
                       **{f"{k}": {"summa": round(v), "savdoga_%": foiz(v, savdo)} for k, v in guruh.items()}}
        if "belgilanmagan" in guruh:
            out["izoh"] = ["Ba'zi xarajat hisoblari doimiy/o'zgaruvchi deb belgilanmagan (Account → Xarajat turi)."]
    return out


def _dividend_hisoblar():
    from pokiza.pokiza_for_business.doctype.kassa.kassa import DIVIDEND_ACCOUNT_NUMBERS
    rows = frappe.db.sql(
        "SELECT name, account_number FROM `tabAccount` WHERE account_number IN %s",
        (tuple(DIVIDEND_ACCOUNT_NUMBERS.values()),), as_dict=True)
    turi = {v: k for k, v in DIVIDEND_ACCOUNT_NUMBERS.items()}
    return {r.name: turi.get(r.account_number) for r in rows}


@metric("C5", "Rahbar olgan pul (dividend)", "so'm", "oy", "rahbar", additive=False)
def dividend(ctx: Ctx):
    """Dividend = 'Dividends Paid' hisoblari (3200/3201/3202) bo'yicha GL debet − kredit.
    Kunlik ro'yxat + davr jami; kunlik xabarda oy boshidan jami ham ko'rsatiladi."""
    hisob = _dividend_hisoblar()
    if not hisob:
        return {"fakt": None, "izoh": ["Dividend hisoblari topilmadi"]}
    rows = frappe.db.sql(
        """SELECT g.posting_date sana, g.account, g.voucher_no, SUM(g.debit - g.credit) summa,
            MAX(je.user_remark) izoh
        FROM `tabGL Entry` g LEFT JOIN `tabJournal Entry` je ON je.name = g.voucher_no AND g.voucher_type = 'Journal Entry'
        WHERE g.is_cancelled = 0 AND g.account IN %(a)s AND g.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY g.posting_date, g.account, g.voucher_no ORDER BY g.posting_date, g.voucher_no""",
        {"a": tuple(hisob), "f": ctx.f, "t": ctx.t}, as_dict=True)
    fakt = sum(flt(r.summa) for r in rows)
    out = {"fakt": fakt, "manba": "GL: Dividends Paid 3200/3201/3202"}
    if ctx.d.turi in ("oy", "oraliq"):
        # rang: sof foydaning qancha qismi yechildi (100% dan ko'p — aylanma pul kamaymoqda)
        sof = pl(ctx.f, ctx.t).sof_foyda
        ulush = foiz(fakt, sof) if sof > 0 else None
        out["rang"] = (QIZIL if fakt > 0 else None) if ulush is None else (
            YASHIL if ulush <= ctx.sozlama().c5_sariq else SARIQ if ulush <= 100 else QIZIL)
        if ctx.full:
            out["qism"] = {"sof_foydadan_%": ulush}
    if not ctx.full:
        return out
    egasi = ctx.sozlama().dividend_egasi
    kim = {}
    for r in rows:
        t = hisob.get(r.account)
        kim[t] = kim.get(t, 0) + flt(r.summa)
    out.setdefault("qism", {}).update({"kim_boyicha": {(egasi.get(t) or t): round(v) for t, v in kim.items()},
                                       "yozuvlar": len(rows)})
    out["tafsilot"] = [{"sana": str(r.sana), "kim": egasi.get(hisob.get(r.account)) or hisob.get(r.account),
                        "summa": round(flt(r.summa)), "izoh": (r.izoh or "")[:120], "hujjat": r.voucher_no} for r in rows[-60:]]
    if ctx.d.turi == "kun":
        oy = frappe.db.sql(
            """SELECT SUM(debit - credit) FROM `tabGL Entry` WHERE is_cancelled = 0 AND account IN %s
            AND posting_date BETWEEN %s AND %s""", (tuple(hisob), get_first_day(ctx.t), ctx.t))[0][0]
        out["qism"]["oy_boshidan"] = round(flt(oy))
    return out


alias("K4", "C5", "Kunlik dividend", "kun")


@metric("K3", "Kassa kirimi", "so'm", "kun", "buxgalteriya", additive=False)
def kassa_kirim(ctx: Ctx):
    """Kassa kirimi = tasdiqlangan Kassa 'Приход' hujjatlari, valyuta bo'yicha; kimdan kirgani ro'yxati.
    Fakt — asosiy valyuta (so'm) kirimi; boshqa valyutalar alohida."""
    asosiy = frappe.get_cached_value("Company", frappe.defaults.get_global_default("company"), "default_currency") or "UZS"
    rows = frappe.db.sql(
        """SELECT party_type, COALESCE(NULLIF(party_name, ''), party, '—') kim, cash_account_currency val,
            SUM(amount) summa, COUNT(*) n
        FROM `tabKassa` WHERE docstatus = 1 AND transaction_type = 'Приход' AND date BETWEEN %s AND %s
        GROUP BY party_type, kim, val ORDER BY summa DESC""", (ctx.f, ctx.t), as_dict=True)
    val = {}
    for r in rows:
        val[r.val] = val.get(r.val, 0) + flt(r.summa)
    out = {"fakt": val.get(asosiy, 0), "manba": "Kassa (Приход, tasdiqlangan)"}
    if ctx.full:
        out["qism"] = {"valyuta_boyicha": {k: round(v, 2) for k, v in val.items()}, "hujjatlar": sum(r.n for r in rows)}
        out["tafsilot"] = [{"kim": r.kim, "turi": r.party_type, "valyuta": r.val, "summa": round(flt(r.summa), 2),
                            "hujjat": r.n} for r in rows[:40]]
    return out


@metric("C6", "Sof foyda taqsimoti", "%", "oy", "rahbar", additive=False, davrlar=("oy", "oraliq"))
def foyda_taqsimoti(ctx: Ctx):
    """Sof foyda nimaga ishlatildi: yechilgan (dividend) / sof foyda × 100; qolgani oborotda qolgan.
    Tamoyil (TZ C6): ortiqcha pul oborotda qoldirilmaydi — yechib yig'iladi."""
    p = pl(ctx.f, ctx.t)
    div = compute_dividend(ctx)
    fakt = foiz(div["jami"], p.sof_foyda) if p.sof_foyda > 0 else None
    out = {"fakt": fakt, "rang": None if fakt is None else (
               QIZIL if fakt > 100 else YASHIL if fakt >= ctx.sozlama().c6_min else SARIQ),
           "manba": "GL sof foyda + Dividends Paid (3200–3202)"}
    if ctx.full:
        # Oylik Reja → "Foyda ishlatilishi" jadvali (dividenddan boshqa yo'nalishlar: uskuna, qarz, zaxira...)
        boshqa = []
        if ctx.d.turi == "oy":
            oy = ctx.reja_oyi()
            reja = frappe.db.get_value("Oylik Reja", {"yil": oy.year, "oy": f"{oy.month:02d}"}, "name")
            if reja:
                boshqa = frappe.get_all("Oylik Reja Foyda", filters={"parent": reja, "parenttype": "Oylik Reja"},
                                        fields=["yonalish", "summa", "izoh"], order_by="idx asc")
        boshqa_jami = sum(flt(b.summa) for b in boshqa)
        out["qism"] = {"sof_foyda": round(p.sof_foyda), "yechilgan": round(div["jami"]),
                       "boshqa_yonalishlar": round(boshqa_jami) if boshqa else None,
                       "oborotda_qolgan": round(p.sof_foyda - div["jami"] - boshqa_jami)}
        out["tafsilot"] = ([{"kim": f"Dividend: {k}", "summa": round(v), "foydadan_%": foiz(v, p.sof_foyda)}
                            for k, v in div["kim"].items()]
                           + [{"kim": b.yonalish + (f" ({b.izoh})" if b.izoh else ""), "summa": round(flt(b.summa)),
                               "foydadan_%": foiz(b.summa, p.sof_foyda)} for b in boshqa])
        if ctx.d.turi == "oy" and not boshqa:
            out.setdefault("izoh", []).append("Foyda boshqa nimalarga ishlatilgani Oylik Reja → «Foyda ishlatilishi» "
                                              "jadvalida yozilmagan.")
        if p.sof_foyda <= 0:
            out["izoh"] = ["Bu davrda sof foyda yo'q — taqsimlanadigan foyda yo'q."]
    return out


def compute_dividend(ctx):
    hisob = _dividend_hisoblar()
    if not hisob:
        return {"jami": 0, "kim": {}}
    egasi = ctx.sozlama().dividend_egasi
    kim = {}
    for acc, v in frappe.db.sql(
            """SELECT account, SUM(debit - credit) FROM `tabGL Entry` WHERE is_cancelled = 0 AND account IN %s
            AND posting_date BETWEEN %s AND %s GROUP BY account""", (tuple(hisob), ctx.f, ctx.t)):
        t = hisob.get(acc)
        k = egasi.get(t) or t
        kim[k] = kim.get(k, 0) + flt(v)
    return {"jami": sum(kim.values()), "kim": kim}
