"""Nazorat Bot Sozlamalari (Single): vazifa/signal belgilarining standart qiymati = 1.

Single doctype'ga qo'shilgan Check maydonning `default` qiymati mavjud yozuvga o'zi tushmaydi.
Faqat hali yozilmagan maydonlar to'ldiriladi (qo'lda o'chirilgani qayta yoqilmaydi).
"""
import frappe

DT = "Nazorat Bot Sozlamalari"


def execute():
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_bot_sozlamalari")
    for field in ("rahbar_tekshiruvi", "guruh_signallari"):
        if not frappe.db.sql("SELECT 1 FROM `tabSingles` WHERE doctype = %s AND field = %s", (DT, field)):
            frappe.db.set_single_value(DT, field, 1)
    frappe.clear_document_cache(DT, DT)
