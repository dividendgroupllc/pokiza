"""Stock Balance hisobotini kassa va Ombor rollariga ochish.

Ikki shart kerak: (1) rol hisobot ruxsat ro'yxatida bo'lishi (Custom Role
orqali — u Report'dagi ro'yxatni TO'LIQ almashtiradi, shuning uchun mavjud
rollar ham ko'chiriladi); (2) rolda ref_doctype (Stock Ledger Entry)
ustida read+report ruxsati bo'lishi (query_report.run tekshiradi).
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

REPORT = "Stock Balance"
YANGI_ROLLAR = ("kassa", "Ombor")


def execute():
    if not frappe.db.exists("Report", REPORT):
        return

    rollar = [r for r in YANGI_ROLLAR if frappe.db.exists("Role", r)]
    if not rollar:
        return

    # 1) Hisobot ruxsat ro'yxati — Custom Role (bo'lmasa Report rollaridan boshlanadi)
    custom_role_name = frappe.db.get_value("Custom Role", {"report": REPORT}, "name")
    if custom_role_name:
        custom_role = frappe.get_doc("Custom Role", custom_role_name)
    else:
        custom_role = frappe.new_doc("Custom Role")
        custom_role.report = REPORT
        custom_role.ref_doctype = frappe.db.get_value("Report", REPORT, "ref_doctype")
        # Report json'ida saytda mavjud bo'lmagan rol uchrashi mumkin
        # (masalan siryo-sklad) — faqat mavjudlari ko'chiriladi
        for row in frappe.get_doc("Report", REPORT).roles:
            if frappe.db.exists("Role", row.role):
                custom_role.append("roles", {"role": row.role})

    mavjud = {row.role for row in custom_role.roles}
    for rol in rollar:
        if rol not in mavjud:
            custom_role.append("roles", {"role": rol})
    custom_role.save(ignore_permissions=True)

    # 2) Stock Ledger Entry: read + report ruxsati
    for rol in rollar:
        if not frappe.db.exists(
            "Custom DocPerm", {"parent": "Stock Ledger Entry", "role": rol}
        ):
            add_permission("Stock Ledger Entry", rol)
        update_permission_property("Stock Ledger Entry", rol, 0, "report", 1)

    frappe.clear_cache()
