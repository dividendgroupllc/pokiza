"""Nazorat Bot Sozlamalari → Ma'lumot himoyasi: yangi maydonlarning standart qiymatlari (Single'ga o'zi tushmaydi).
Faqat hali yozilmagan maydonlar to'ldiriladi."""
import frappe

DT = "Nazorat Bot Sozlamalari"
QIYMAT = {"himoya_excel_xodim": 0, "himoya_forward": 1, "himoya_rahbarga": 0, "himoya_web_ai_belgi": 1,
          "himoya_kop_fayl": 3, "himoya_kop_savol": 25}


def execute():
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_bot_sozlamalari")
    for field, v in QIYMAT.items():
        if not frappe.db.sql("SELECT 1 FROM `tabSingles` WHERE doctype = %s AND field = %s", (DT, field)):
            frappe.db.set_single_value(DT, field, v)
    frappe.clear_document_cache(DT, DT)
