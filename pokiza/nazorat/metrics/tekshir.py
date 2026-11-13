"""KPI dvigatelini mustaqil SQL bilan solishtirish (lokal va prod'da).

    bench --site pokiza.local execute pokiza.nazorat.metrics.tekshir.run --kwargs "{'davr': '2026-10'}"
"""
import frappe
from frappe.utils import flt

from pokiza.nazorat.metrics import Davr, compute


def _one(sql, p):
    return flt(frappe.db.sql(sql, p)[0][0])


def run(davr="otgan_oy"):
    d = Davr.parse(davr, "oy")
    p = {"f": d.f, "t": d.t}
    kutilgan = {
        "A2": _one("SELECT SUM(base_net_total) FROM `tabSales Invoice` WHERE docstatus=1 AND posting_date BETWEEN %(f)s AND %(t)s", p),
        "A1": _one("""SELECT SUM(p.qty_to_manufacture)/1000 FROM `tabProduction Entry` p JOIN `tabItem` i ON i.name=p.item_to_manufacture
                   WHERE p.docstatus=1 AND i.stock_uom='кг' AND p.posting_date BETWEEN %(f)s AND %(t)s""", p),
        "A4": _one("""SELECT SUM(sii.base_net_amount)/SUM(sii.stock_qty) FROM `tabSales Invoice Item` sii
                   JOIN `tabSales Invoice` si ON si.name=sii.parent JOIN `tabItem` i ON i.name=sii.item_code
                   WHERE si.docstatus=1 AND i.stock_uom='кг' AND si.posting_date BETWEEN %(f)s AND %(t)s""", p),
        "C5": _one("""SELECT SUM(g.debit-g.credit) FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name=g.account
                   WHERE g.is_cancelled=0 AND a.account_number IN ('3200','3201','3202') AND g.posting_date BETWEEN %(f)s AND %(t)s""", p),
        "K3": _one("""SELECT SUM(amount) FROM `tabKassa` WHERE docstatus=1 AND transaction_type='Приход'
                   AND cash_account_currency='UZS' AND date BETWEEN %(f)s AND %(t)s""", p),
    }
    inc = _one("""SELECT SUM(g.credit-g.debit) FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name=g.account
               WHERE g.is_cancelled=0 AND a.root_type='Income' AND g.posting_date BETWEEN %(f)s AND %(t)s""", p)
    exp = _one("""SELECT SUM(g.debit-g.credit) FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name=g.account
               WHERE g.is_cancelled=0 AND a.root_type='Expense' AND g.posting_date BETWEEN %(f)s AND %(t)s""", p)
    kutilgan["A3"] = round((inc - exp) / kutilgan["A2"] * 100, 1) if kutilgan["A2"] else None

    xato = 0
    print(f"Davr: {d.nom}")
    for code, exp_v in kutilgan.items():
        got = compute(code, d, full=False)["fakt"]
        ok = (got is None and not exp_v) or (exp_v is not None and abs(flt(got) - exp_v) <= max(1, abs(exp_v) * 0.001))
        xato += not ok
        print(f"  {'OK ' if ok else 'XATO'} {code}: dvigatel={got}  mustaqil_sql={round(exp_v, 2) if exp_v else exp_v}")
    for code in ("B1", "B2", "B3", "C3", "C4", "H4"):
        r = compute(code, d)
        print(f"  ..  {code}: {r['fakt']}  (tafsilot {len(r.get('tafsilot') or [])} qator)")
    print("NATIJA:", "hammasi mos" if not xato else f"{xato} ta farq bor")
    return xato
