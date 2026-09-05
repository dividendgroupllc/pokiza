# Mijoz bonusi (2026-09-05, egasi talabi): har mijozga doimiy bonus foizi.
# Schyot (Sales Invoice) submit bo'lganda shu foiz umumiy summadan hisoblanib,
# avto Journal Entry yoziladi: Dt «Бонус» (rasxod) / Kt Debtors (mijoz) —
# mijoz qarzi bonus summasiga kamayadi.
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Customer": [
                {
                    "fieldname": "custom_bonus_foiz",
                    "label": "Bonus foizi (%)",
                    "fieldtype": "Percent",
                    "insert_after": "customer_group",
                    "description": (
                        "Schyot tasdiqlanganda shu foizda avto Journal Entry "
                        "yoziladi (Бонус rasxodi, mijoz qarzi kamayadi). "
                        "Manfiy qiymat = ustama."
                    ),
                },
            ],
        },
        update=True,
    )
    frappe.clear_cache(doctype="Customer")
