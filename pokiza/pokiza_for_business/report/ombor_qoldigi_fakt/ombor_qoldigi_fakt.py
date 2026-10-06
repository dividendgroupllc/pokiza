# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Ombor qoldig'i (fakt) — omborchi uchun SODDA 3 darajali daraxt
(egasi talabi 2026-10-06, 1C «Остатки товаров» / SAP MB52 uslubi):

    Ombor (yig'ma)  →  Item Group (yig'ma)  →  itemlar (fakt qoldiq)

Faqat miqdor: Nomi | Qoldiq (fakt) | Birlik. Pul, opening/in-out YO'Q —
buning uchun standart Stock Balance bor. Manba: Bin.actual_qty (hozirgi
real qoldiq — tez, tarix hisoblanmaydi).

Yig'ma qatorlar ARALASH birlik gotchasi: ombor/guruh jami'si o'sha to'plamda
eng ko'p uchraydigan birlik (odatda кг) bo'yicha yig'iladi va birligi
ko'rsatiladi — кг bilan шт qo'shilib yolg'on raqam chiqmasligi uchun.

Guruhlar dinamik — Item Group daraxti/biriktirish o'zgarsa report o'zi
moslashadi (ГП 5 turga bo'linsa shu yerda avtomatik chiqadi).
"""

import frappe
from frappe import _
from frappe.utils import flt

EPS = 0.001


def _dominant_jami(rows):
    """Eng ko'p uchraydigan birlik va o'sha birlikdagi yig'indi."""
    uom_soni = {}
    for r in rows:
        uom_soni[r.stock_uom] = uom_soni.get(r.stock_uom, 0) + 1
    if not uom_soni:
        return 0.0, ""
    uom = max(uom_soni, key=uom_soni.get)
    return flt(sum(flt(r.qty) for r in rows if r.stock_uom == uom)), uom


def execute(filters=None):
    filters = frappe._dict(filters or {})

    shart = ["1=1"]
    params = {}
    if filters.get("warehouse"):
        shart.append("b.warehouse = %(warehouse)s")
        params["warehouse"] = filters.warehouse
    if filters.get("item_group"):
        shart.append("i.item_group = %(item_group)s")
        params["item_group"] = filters.item_group

    rows = frappe.db.sql(
        f"""
        SELECT b.warehouse, i.item_group, b.item_code,
               COALESCE(NULLIF(i.item_name, ''), i.name) AS item_name,
               i.stock_uom, b.actual_qty AS qty
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE {' AND '.join(shart)}
        """,
        params,
        as_dict=True,
    )

    if not filters.get("nol_korsat"):
        rows = [r for r in rows if abs(flt(r.qty)) > EPS]

    # guruhlar Item Group daraxti tartibida
    guruh_tartib = {
        g.name: g.lft
        for g in frappe.get_all("Item Group", fields=["name", "lft"])
    }

    # ombor -> guruh -> itemlar
    daraxt = {}
    for r in rows:
        daraxt.setdefault(r.warehouse, {}).setdefault(r.item_group, []).append(r)

    data = []
    jami_kg = 0.0
    jami_item = 0
    for wh in sorted(daraxt):
        wh_rows = [r for g in daraxt[wh].values() for r in g]
        wh_jami, wh_uom = _dominant_jami(wh_rows)
        data.append({
            "nomi": wh,
            "qoldiq": wh_jami,
            "birlik": wh_uom,
            "itemlar_soni": len(wh_rows),
            "ota": None,
            "indent": 0,
            "is_group": 1,
        })

        for guruh in sorted(daraxt[wh], key=lambda g: guruh_tartib.get(g, 0)):
            itemlar = sorted(
                daraxt[wh][guruh], key=lambda r: (r.item_name or "").lower()
            )
            g_jami, g_uom = _dominant_jami(itemlar)
            if g_uom == "кг":
                jami_kg += g_jami
            jami_item += len(itemlar)

            data.append({
                "nomi": guruh,
                "qoldiq": g_jami,
                "birlik": g_uom,
                "itemlar_soni": len(itemlar),
                "ota": wh,
                "indent": 1,
                "is_group": 1,
            })
            for r in itemlar:
                data.append({
                    "nomi": r.item_name,
                    "qoldiq": flt(r.qty),
                    "birlik": r.stock_uom,
                    "itemlar_soni": None,
                    "ota": guruh,
                    "indent": 2,
                    "item_code": r.item_code,
                })

    columns = [
        {
            "fieldname": "nomi",
            "label": _("Nomi"),
            "fieldtype": "Data",
            "width": 440,
        },
        {
            "fieldname": "qoldiq",
            "label": _("Qoldiq (fakt)"),
            "fieldtype": "Float",
            "precision": "1",
            "width": 150,
        },
        {
            "fieldname": "birlik",
            "label": _("Birlik"),
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "fieldname": "itemlar_soni",
            "label": _("Itemlar"),
            "fieldtype": "Int",
            "width": 90,
        },
    ]

    report_summary = [
        {
            "value": flt(jami_kg, 1),
            "label": _("Jami qoldiq (faqat кг)"),
            "datatype": "Float",
            "indicator": "Green",
        },
        {
            "value": jami_item,
            "label": _("Qoldiqli itemlar"),
            "datatype": "Int",
        },
        {
            "value": len(daraxt),
            "label": _("Omborlar"),
            "datatype": "Int",
        },
    ]

    return columns, data, None, None, report_summary
