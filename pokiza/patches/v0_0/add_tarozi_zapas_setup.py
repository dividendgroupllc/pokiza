"""Tarozi roli (egasi talabi 2026-09-25).

pre_model_sync: «tarozi» roli PE/page json'laridagi permission'lardan
OLDIN yaratilishi kerak.

Eslatma: avvalgi «ЗАПАС» texnik mijoz g'oyasi BEKOR qilindi (egasi:
zapas hech qanday mijozga bog'lanmasin) — zapas endi STANDART
Material Request (turi Manufacture) orqali, `add_zapas_mr_fields`
patchiga qarang.
"""

import frappe


def execute():
    if not frappe.db.exists("Role", "tarozi"):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": "tarozi",
            "desk_access": 1,
        }).insert(ignore_permissions=True)

    # tarozi ishlashi uchun minimal o'qish huquqlari (Custom DocPerm):
    # Item — ERPNext get_stock_balance Item read'ni talab qiladi;
    # Sales Order/Batch — navbat sahifasidagi havolalar/qoldiqlar uchun
    from frappe.permissions import add_permission
    for dt in ("Item", "Sales Order", "Batch"):
        if not frappe.db.exists(
            "Custom DocPerm", {"parent": dt, "role": "tarozi"}
        ):
            add_permission(dt, "tarozi")

    # eski yondashuvdan qolgan «ЗАПАС» texnik mijozi bo'lsa — o'chirib
    # yuboriladi (bog'liq hujjat bo'lsa nofaol qilinadi)
    if frappe.db.exists("Customer", "ЗАПАС"):
        try:
            frappe.delete_doc("Customer", "ЗАПАС", ignore_permissions=True)
        except Exception:
            frappe.db.set_value("Customer", "ЗАПАС", "disabled", 1)
