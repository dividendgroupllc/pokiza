# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Mijoz Marja hisoboti — egasi izlagan yakuniy hisobot:
«Alixon bu oy 240 mln savdo → 47 mln yalpi foyda → 19.6% marja».

Faqat MUZLATILGAN qiymatlardan o'qiydi (schyot qatoridagi custom_norma /
custom_tannarx_kg / custom_bonus_foiz_qator — sotuv paytida kartochkadan
ko'chirilgan): kartochka keyin o'zgarsa ham bu hisobot o'zgarmaydi.
Snapshot'i yo'q qatorlar (kartochka joriy etilishidan avvalgi sotuvlar)
«Tannarxsiz savdo» ustunida alohida ko'rinadi — chalg'itmaydi.

Mijoz filtri berilsa — o'sha mijoz SKU kesimida ochiladi.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("mijoz"):
        return _sku_kesimi(filters)
    return _mijoz_kesimi(filters)


def _shartlar(filters):
    shart = ["si.docstatus = 1", "si.is_return = 0"]
    qiymat = {}
    if filters.get("from_date"):
        shart.append("si.posting_date >= %(from_date)s")
        qiymat["from_date"] = filters.from_date
    if filters.get("to_date"):
        shart.append("si.posting_date <= %(to_date)s")
        qiymat["to_date"] = filters.to_date
    if filters.get("mijoz"):
        shart.append("si.customer = %(mijoz)s")
        qiymat["mijoz"] = filters.mijoz
    return " AND ".join(shart), qiymat


def _hisob_sql(guruh_ustun, alias, shart):
    return f"""
        SELECT
            {guruh_ustun} AS {alias},
            SUM(sii.base_amount) AS savdo,
            SUM(sii.base_amount * IFNULL(sii.custom_bonus_foiz_qator, 0) / 100) AS bonus,
            SUM(CASE WHEN IFNULL(sii.custom_tannarx_kg, 0) > 0
                     THEN sii.stock_qty * sii.custom_tannarx_kg ELSE 0 END) AS tannarx,
            SUM(CASE WHEN IFNULL(sii.custom_tannarx_kg, 0) > 0
                     THEN sii.base_amount ELSE 0 END) AS hisobli_savdo,
            SUM(CASE WHEN IFNULL(sii.custom_tannarx_kg, 0) > 0
                     THEN sii.base_amount * IFNULL(sii.custom_bonus_foiz_qator, 0) / 100
                     ELSE 0 END) AS hisobli_bonus,
            SUM(CASE WHEN IFNULL(sii.custom_tannarx_kg, 0) = 0
                     THEN sii.base_amount ELSE 0 END) AS tannarxsiz_savdo,
            SUM(sii.stock_qty) AS kg
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {shart}
        GROUP BY {guruh_ustun}
        ORDER BY savdo DESC
    """


def _qator_tayyorla(rows):
    data = []
    for r in rows:
        sof = flt(r.hisobli_savdo) - flt(r.hisobli_bonus)
        foyda = sof - flt(r.tannarx)
        data.append({
            **r,
            "sof_savdo": flt(r.savdo) - flt(r.bonus),
            "foyda": foyda,
            "marja_foiz": (foyda / sof * 100) if sof else 0,
        })
    return data


UMUMIY_USTUNLAR = [
    {"fieldname": "kg", "label": _("Kg"), "fieldtype": "Float", "precision": 1, "width": 90},
    {"fieldname": "savdo", "label": _("Savdo"), "fieldtype": "Currency", "width": 140},
    {"fieldname": "bonus", "label": _("Bonus"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "sof_savdo", "label": _("Sof savdo (bonusdan keyin)"), "fieldtype": "Currency", "width": 140},
    {"fieldname": "tannarx", "label": _("Tannarx (muzlatilgan)"), "fieldtype": "Currency", "width": 140},
    {"fieldname": "foyda", "label": _("Yalpi foyda"), "fieldtype": "Currency", "width": 140},
    {"fieldname": "marja_foiz", "label": _("Marja %"), "fieldtype": "Percent", "precision": 1, "width": 90},
    {"fieldname": "tannarxsiz_savdo", "label": _("Tannarxsiz savdo (eski)"), "fieldtype": "Currency", "width": 140},
]


def _mijoz_kesimi(filters):
    shart, qiymat = _shartlar(filters)
    rows = frappe.db.sql(
        _hisob_sql("si.customer", "mijoz", shart), qiymat, as_dict=True
    )
    columns = [
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link",
         "options": "Customer", "width": 220},
    ] + UMUMIY_USTUNLAR
    return columns, _qator_tayyorla(rows)


def _sku_kesimi(filters):
    shart, qiymat = _shartlar(filters)
    rows = frappe.db.sql(
        _hisob_sql("sii.item_code", "sku", shart), qiymat, as_dict=True
    )
    columns = [
        {"fieldname": "sku", "label": _("SKU"), "fieldtype": "Link",
         "options": "Item", "width": 260},
    ] + UMUMIY_USTUNLAR
    return columns, _qator_tayyorla(rows)
