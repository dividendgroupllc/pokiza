"""«kassa» roliga Sales Invoice bo'yicha TO'LIQ ruxsat (egasi talabi 2026-10-14).

Zakazga ruxsat ochilgach (add_kassa_sales_order_perm) kassa zakaz submit
qilganda tizim avtomatik QORALAMA schyot yaratadi — lekin kassa rolida
Sales Invoice'ga hech qanday ruxsat yo'q edi, ya'ni o'sha schyotni ocholmasdi.
Endi «Sotuv» roli bilan bir xil to'liq huquq beriladi.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Sales Invoice"
ROL = "kassa"
HUQUQLAR = {
    0: ("read", "write", "create", "submit", "cancel", "amend", "delete",
        "report", "export", "print", "email", "share"),
    1: ("read", "write"),
}


def execute():
    if not frappe.db.exists("Role", ROL):
        return

    for permlevel, huquqlar in HUQUQLAR.items():
        if not frappe.db.exists(
            "Custom DocPerm",
            {"parent": DOCTYPE, "role": ROL, "permlevel": permlevel},
        ):
            add_permission(DOCTYPE, ROL, permlevel)
        for huquq in huquqlar:
            update_permission_property(DOCTYPE, ROL, permlevel, huquq, 1,
                                       validate=False)
        update_permission_property(DOCTYPE, ROL, permlevel, "if_owner", 0,
                                   validate=False)

    frappe.clear_cache()
