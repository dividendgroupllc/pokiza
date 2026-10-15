"""«Zakaz kelgan vaqt» (custom_kelgan_vaqt) bekor qilindi (egasi 2026-10-15).

Reja endi faqat zakaz SANASI (transaction_date) bilan ishlaydi — soat/
soniya umuman ishlatilmaydi, kesim (13:00) qoidasi ham bekor. Maydon
tarixiy ma'lumot saqlanishi uchun o'chirilmaydi, faqat yashiriladi."""

import frappe


def execute():
    cf = frappe.db.get_value(
        "Custom Field", {"dt": "Sales Order", "fieldname": "custom_kelgan_vaqt"}
    )
    if cf:
        # hidden + default «Now» ham olib tashlanadi — yangi zakazlarga
        # endi vaqt yozilmasin
        frappe.db.set_value("Custom Field", cf,
                            {"hidden": 1, "default": None},
                            update_modified=False)
    frappe.clear_cache(doctype="Sales Order")
