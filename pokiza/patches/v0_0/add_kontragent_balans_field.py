"""Customer/Supplier Details ko'rinishiga «Balans» HTML maydoni.
Qiymat saqlanmaydi — public/js/kontragent_balans.js har ochilganda
GL Entry'dan jonli hisoblab chiqarib ko'rsatadi (pokiza/api/kontragent.py).
"""
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
    "Customer": [{
        "fieldname": "custom_balans_korinish", "fieldtype": "HTML", "label": "Balans",
        "insert_after": "customer_group", "read_only": 1,
    }],
    "Supplier": [{
        "fieldname": "custom_balans_korinish", "fieldtype": "HTML", "label": "Balans",
        "insert_after": "supplier_group", "read_only": 1,
    }],
}


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
