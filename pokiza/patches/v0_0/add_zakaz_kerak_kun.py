# Oldindan zakaz (2026-08-23, egasi talabi): zakazni bir necha kun keyinga
# olib qo'yish mumkin — reja tanlangan kundan boshlab to'ldiriladi.
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": "custom_kerak_kun",
                    "label": "So'ralgan kun (reja shu kundan boshlanadi)",
                    "fieldtype": "Date",
                    "insert_after": "custom_kelgan_vaqt",
                    "no_copy": 1,
                    "print_hide": 1,
                },
            ],
        },
        update=True,
    )
    frappe.clear_cache(doctype="Sales Order")
