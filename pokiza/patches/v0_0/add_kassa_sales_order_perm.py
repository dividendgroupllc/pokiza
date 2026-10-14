"""«kassa» roliga Sales Order bo'yicha TO'LIQ ruxsat (egasi talabi 2026-10-14).

Kassa xodimi zakaz bilan to'liq ishlashi kerak: yaratish, o'zgartirish,
tasdiqlash (submit), bekor qilish (cancel), tuzatish (amend), o'chirish,
hisobot/eksport/chop etish. Shu paytgacha «kassa» rolida Sales Order'ga
umuman ruxsat yo'q edi (Custom DocPerm'da qatori ham yo'q).

Sales Order'da permlevel 1 ham bor (faqat `ignore_pricing_rule` maydoni) —
hech narsa bloklanmasligi uchun unga ham o'qish/yozish beriladi
(Sales Manager rolida ham xuddi shunday).
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

DOCTYPE = "Sales Order"
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
        # faqat o'zi yaratgani emas — hamma zakaz ko'rinsin
        update_permission_property(DOCTYPE, ROL, permlevel, "if_owner", 0,
                                   validate=False)

    frappe.clear_cache()
