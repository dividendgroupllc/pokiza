"""Nazorat rollari: avval kodda yozilgan bo'lim ruxsatlarini "Nazorat Roli" yozuvlariga ko'chirish.

Natija avvalgidek ishlaydi; endi o'zgartirish va yangi rol qo'shish ERP'dan (Nazorat Roli sahifasi).
Mavjud rol qayta yozilmaydi (qo'lda o'zgartirilgani saqlanadi).
"""
import frappe

ROLLAR = {
    "Rahbar": {"toliq_ruxsat": 1, "vazifa_berish": 1},
    "Sotuv": {"kpi": ("a2", "a4", "b2", "b3", "h1", "h2", "h4", "h5", "k1"),
              "ai": ("ai_qarz_mijoz", "ai_talab", "ai_fayl"), "erp": ("Sotuv", "Sales User", "Sales Manager")},
    "Ishlab chiqarish": {"kpi": ("a1", "c4", "h3", "k2"), "ai": ("ai_ishlab_chiqarish", "ai_talab", "ai_fayl"),
                         "erp": ("Ishlab chiqarish", "tarozi", "Manufacturing User")},
    "Buxgalteriya": {"kpi": ("c1", "c2", "c3", "k3"), "ai": ("ai_qarz_mijoz", "ai_qarz_postavshik", "ai_kassa", "ai_fayl"),
                     "erp": ("kassa", "Accounts User")},
    "Ombor": {"kpi": (), "ai": ("ai_ishlab_chiqarish", "ai_fayl"), "erp": ("Ombor", "Stock User")},
}


def execute():
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_roli_erp_roli")
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_roli")
    for nom, c in ROLLAR.items():
        if frappe.db.exists("Nazorat Roli", nom):
            continue
        doc = frappe.new_doc("Nazorat Roli")
        doc.rol_nomi = nom
        doc.toliq_ruxsat = c.get("toliq_ruxsat", 0)
        doc.vazifa_berish = c.get("vazifa_berish", 0)
        doc.izoh = c.get("izoh")
        for k in c.get("kpi", ()):
            doc.set(f"kpi_{k}", 1)
        for f in c.get("ai", ()):
            doc.set(f, 1)
        for r in c.get("erp", ()):
            if frappe.db.exists("Role", r):
                doc.append("erp_rollari", {"role": r})
        doc.insert(ignore_permissions=True)
