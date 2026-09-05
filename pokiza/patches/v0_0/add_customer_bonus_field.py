# Mijoz bonusi (2026-09-05, egasi talabi): har mijozga doimiy bonus foizi.
# Schyot (Sales Invoice) yaratilganda shu foiz umumiy summadan avtomatik
# chegirma (Additional Discount %) bo'lib tushadi — qarzdorlik sof yoziladi.
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
                        "Schyot yaratilganda umumiy summadan avtomatik "
                        "ayiriladigan doimiy bonus. Manfiy qiymat = ustama."
                    ),
                },
            ],
        },
        update=True,
    )
    frappe.clear_cache(doctype="Customer")
