# Ombordan foydalanish (2026-08-23, egasi talabi):
# zakaz kunlik limitga sig'masa, yetmagan qismini ombordagi tayyor
# mahsulotdan band qilish mumkin. Band qilingan kg ishlab chiqarish
# rejasiga TUSHMAYDI (faqat qolgan qismi taqsimlanadi).
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": "custom_ombordan_jami",
                    "label": "Ombordan jami (kg)",
                    "fieldtype": "Float",
                    "insert_after": "custom_jami_kg",
                    "read_only": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
            ],
            "Sales Order Item": [
                {
                    "fieldname": "custom_ombordan_kg",
                    "label": "Ombordan (kg)",
                    "fieldtype": "Float",
                    "insert_after": "custom_fakt_kg",
                    "read_only": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
            ],
        },
        update=True,
    )
    frappe.clear_cache(doctype="Sales Order")
    frappe.clear_cache(doctype="Sales Order Item")
