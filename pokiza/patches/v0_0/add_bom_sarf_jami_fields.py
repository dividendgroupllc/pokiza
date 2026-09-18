# BOM sarf jami (2026-09-18, egasi talabi): har BOM'da sarflanadigan
# mahsulotlar (syryo) jadvalining umumiy soni (qty yig'indisi) va umumiy
# summasi (amount yig'indisi) ko'rinib turadigan maydonlar.
# Qiymatlar BOM validate hook'ida avto hisoblanadi (pokiza.events.bom).
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "BOM": [
                {
                    "fieldname": "custom_sarf_jami_soni",
                    "label": "Sarf mahsulotlar umumiy soni",
                    "fieldtype": "Float",
                    "insert_after": "items",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Syryo jadvalidagi barcha qatorlar miqdorining yig'indisi",
                },
                {
                    "fieldname": "custom_sarf_jami_summa",
                    "label": "Sarf mahsulotlar umumiy summasi",
                    "fieldtype": "Currency",
                    "insert_after": "custom_sarf_jami_soni",
                    "options": "currency",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Syryo jadvalidagi barcha qatorlar summasining yig'indisi",
                },
            ],
        },
        update=True,
    )

    # Mavjud BOM'larga backfill (timestamp/modified tegilmaydi)
    frappe.db.sql(
        """
        UPDATE `tabBOM` b
        LEFT JOIN (
            SELECT parent,
                   SUM(qty) AS jami_soni,
                   SUM(amount) AS jami_summa
            FROM `tabBOM Item`
            GROUP BY parent
        ) i ON i.parent = b.name
        SET b.custom_sarf_jami_soni = IFNULL(i.jami_soni, 0),
            b.custom_sarf_jami_summa = IFNULL(i.jami_summa, 0)
        """
    )

    frappe.clear_cache(doctype="BOM")
