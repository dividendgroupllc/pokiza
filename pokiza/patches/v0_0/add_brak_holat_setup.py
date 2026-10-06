"""Tarozi ketma-ketligi + brak rasxodi sozlashlari (egasi talabi 2026-10-06).

1) SO/MR qator holatiga yangi oraliq qiymat «Ishlab chiqarildi» —
   ishlab chiqarish sahifasi endi fakt kiritmaydi, faqat «chiqardik» deb
   belgilaydi; tarozi faqat shu holatdagi qatorni torta oladi.
2) «Брак» rasxod hisobi (Производственные расходы guruhida) — brak endi
   skladga qaytmaydi, mahsulot tannarxi butunligicha shu hisobga chiqadi.
"""

import frappe


def execute():
    # 1) holat variantlari
    for dt, opts in (
        ("Sales Order Item",
         "Kutilmoqda\nIshlab chiqarildi\nChiqarildi\nJonatildi"),
        ("Material Request Item",
         "Kutilmoqda\nIshlab chiqarildi\nChiqarildi"),
    ):
        cf = frappe.db.get_value(
            "Custom Field", {"dt": dt, "fieldname": "custom_holat"}
        )
        if cf:
            frappe.db.set_value("Custom Field", cf, "options", opts,
                                update_modified=False)
        frappe.clear_cache(doctype=dt)

    # 2) «Брак» hisobi
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        return
    if frappe.db.exists("Account", {"account_name": "Брак", "company": company}):
        return
    guruh = frappe.db.get_value(
        "Account",
        {"account_name": ("like", "%Производственные расходы%"),
         "is_group": 1, "company": company},
    )
    if not guruh:
        # bunday guruh yo'q sayt — umumiy xarajat ildiziga
        guruh = frappe.db.get_value(
            "Account", {"root_type": "Expense", "is_group": 1,
                        "company": company},
        )
    frappe.get_doc({
        "doctype": "Account",
        "account_name": "Брак",
        "parent_account": guruh,
        "company": company,
        "root_type": "Expense",
        "is_group": 0,
    }).insert(ignore_permissions=True)
