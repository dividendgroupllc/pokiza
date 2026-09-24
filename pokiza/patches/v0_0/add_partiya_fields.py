"""Faza 3 (partiya rejimi) custom maydonlari.

Batch.custom_norma — partiya qaysi normadan chiqqani (SKU+norma juftligiga
BITTA doimiy partiya ochiladi, kunlik lot emas).

Sales Invoice Item snapshot maydonlari — sotuv paytida kartochkadagi
qiymatlar MUZLATILADI: keyin kartochka o'zgarsa ham tarixiy hisobot
buzilmaydi (egasining qat'iy talabi).
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "Batch": [
            {
                "fieldname": "custom_norma",
                "label": "Norma",
                "fieldtype": "Link",
                "options": "Item",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
        ],
        "Sales Invoice Item": [
            {
                "fieldname": "custom_norma",
                "label": "Norma (muzlatilgan)",
                "fieldtype": "Link",
                "options": "Item",
                "read_only": 1,
                "insert_after": "item_name",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_tannarx_kg",
                "label": "Tannarx so'm/kg (muzlatilgan)",
                "fieldtype": "Currency",
                "read_only": 1,
                "insert_after": "custom_norma",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_bonus_foiz_qator",
                "label": "Bonus % (muzlatilgan)",
                "fieldtype": "Percent",
                "read_only": 1,
                "insert_after": "custom_tannarx_kg",
                "no_copy": 1,
            },
        ],
    }, ignore_validate=True, update=True)
