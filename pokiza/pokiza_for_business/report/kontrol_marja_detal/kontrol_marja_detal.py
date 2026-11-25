# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Kontrol Marja Detal — Kontrol Marja'dagi son qayerdan yig'ilganini
ko'rsatadigan qatorma-qator hisobot: har bir qator = schyotning bitta
qatori (Sales Invoice Item), tannarxi Stock Ledger'dan.

Kontrol Marja'da son ustiga bosilganda shu hisobot ochiladi — davr va
tugun (guruh/brend/tavar) filtrlarga avtomatik to'ldirilgan holda.
Mustaqil ham ochish mumkin. Filtrlar va hisob mantig'i (shartlar, marja
formulasi) asosiy hisobot bilan BITTA manbadan (_shartlar) — sonlar
hech qachon ajralib ketmaydi.

Oxirida JAMI qatori: savdo/tannarx yig'indisi va ulardan hisoblangan
haqiqiy marja % (qatorlar foizining o'rtachasi emas).
"""

import frappe
from frappe import _
from frappe.utils import flt

from pokiza.pokiza_for_business.report.kontrol_marja.kontrol_marja import (
    _marja,
    _shartlar,
)

LIMIT = 5000


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return _columns(), _data(filters)


def _columns():
    return [
        # schyot ataylab Data: JAMI qatorida link bo'lib ketmasligi uchun,
        # linkni JS formatter chiqaradi
        {"fieldname": "schyot", "label": _("Schyot"), "fieldtype": "Data", "width": 190},
        {"fieldname": "sana", "label": _("Sana"), "fieldtype": "Date", "width": 100},
        {"fieldname": "mijoz", "label": _("Mijoz"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "guruh", "label": _("Guruh"), "fieldtype": "Link", "options": "Item Group", "width": 150},
        {"fieldname": "brend", "label": _("Brend"), "fieldtype": "Data", "width": 110},
        {"fieldname": "tavar", "label": _("Tavar"), "fieldtype": "Link", "options": "Item", "width": 230},
        {"fieldname": "kg", "label": _("Kg"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "savdo", "label": _("Savdo"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "tannarx", "label": _("Tannarx"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "foyda", "label": _("Yalpi foyda"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "marja", "label": _("Marja %"), "fieldtype": "Percent", "precision": 1, "width": 90},
    ]


def _data(filters):
    shart, qiymat = _shartlar(filters)
    if filters.get("vozvrat") == "Faqat vozvrat":
        shart.append("si.is_return = 1")
    elif filters.get("vozvrat") == "Vozvratsiz":
        shart.append("si.is_return = 0")

    rows = frappe.db.sql(f"""
        SELECT
            si.name AS schyot,
            si.posting_date AS sana,
            si.customer AS mijoz,
            si.is_return AS is_vozvrat,
            i.item_group AS guruh,
            COALESCE(NULLIF(i.custom_subkategoriya, ''), 'Boshqa') AS brend,
            sii.item_code AS tavar,
            sii.stock_qty AS kg,
            sii.base_amount AS savdo,
            -COALESCE(sle.v, 0) AS tannarx
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        LEFT JOIN (
            SELECT voucher_detail_no, SUM(stock_value_difference) AS v
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0 AND voucher_type = 'Sales Invoice'
              AND posting_date BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY voucher_detail_no
        ) sle ON sle.voucher_detail_no = sii.name
        WHERE {" AND ".join(shart)}
        ORDER BY si.posting_date DESC, si.name, ABS(sii.base_amount) DESC
        LIMIT {LIMIT + 1}
    """, qiymat, as_dict=True)

    if len(rows) > LIMIT:
        rows = rows[:LIMIT]
        frappe.msgprint(_("Faqat birinchi {0} qator ko'rsatildi — filtrlar bilan toraytiring "
                          "(JAMI ham faqat shu qatorlar bo'yicha).").format(LIMIT))

    for r in rows:
        r.foyda = flt(r.savdo) - flt(r.tannarx)
        r.marja = _marja(flt(r.savdo), flt(r.tannarx))

    if rows:
        t_savdo = sum(flt(r.savdo) for r in rows)
        t_tannarx = sum(flt(r.tannarx) for r in rows)
        rows.append(frappe._dict({
            "schyot": _("JAMI ({0} qator)").format(len(rows)),
            "is_jami": 1,
            "kg": sum(flt(r.kg) for r in rows),
            "savdo": t_savdo,
            "tannarx": t_tannarx,
            "foyda": t_savdo - t_tannarx,
            "marja": _marja(t_savdo, t_tannarx),
        }))
    return rows
