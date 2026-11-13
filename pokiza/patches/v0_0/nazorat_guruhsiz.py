"""Bot faqat shaxsiy chatda ishlaydi: umumiy nazorat guruhi olib tashlandi.

- "Nazorat guruhi" Nazorat Roli o'chiriladi (shu rolda xodim bo'lsa — roli bo'shatiladi);
- TG Chat yozuvlari faol emas qilinadi (tarix uchun qoladi);
- sozlamadagi ulangan guruh maydonlari (endi doctype'da yo'q) tozalanadi.
Bot keyingi safar guruhdan xabar olsa, o'zi chiqib ketadi (pokiza.nazorat.tg.router._guruhdan_chiq).
"""
import frappe

ROL = "Nazorat guruhi"
DT = "Nazorat Bot Sozlamalari"


def execute():
    if frappe.db.exists("Nazorat Roli", ROL):
        frappe.db.sql("UPDATE `tabTG Azo` SET bolim = NULL WHERE bolim = %s", ROL)
        frappe.db.sql("UPDATE `tabAI Suhbat` SET bolim = NULL WHERE bolim = %s", ROL)
        frappe.delete_doc("Nazorat Roli", ROL, ignore_permissions=True, force=True)
    frappe.db.sql("UPDATE `tabTG Chat` SET faol = 0")
    frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field IN "
                  "('guruh_chat', 'guruh_nomi', 'rad_sababi_guruhda', 'ai_guruh_soatlik')", DT)
    frappe.clear_document_cache(DT, DT)
