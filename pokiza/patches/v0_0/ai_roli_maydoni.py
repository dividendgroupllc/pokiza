"""AI ruxsati — yagona manba User.ai_roli (web chat, Telegram bot, rahbar paneli).

Ilgari web chat rolni ERP rollaridan taxmin qilardi (bir nechta mos kelsa to'liq ruxsatlisi tanlanardi —
"AI Foydalanuvchi" roli Investor'ga bog'langani uchun sotuv rahbari hammasini ko'rardi), System Manager esa
umuman cheklanmasdi. Endi: maydon bo'sh — AI ma'lumot bermaydi; System Manager ham o'z rolini oladi.

Mavjud qiymatlar faqat BO'SH maydonga yoziladi: Telegram a'zosining roli (TG Azo), keyin Nazorat rahbari.
Qolganlarini administrator User sahifasida qo'lda tanlaydi (taxmin qilinmaydi).
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

KORSATMALAR = {
    "Sotuv": "«Aylanma», «oborot», «tushum» deganda savdo summasini (sotuv fakturalari, qaytarishlar ayirilgan) "
             "tushun. Savdo, mijozlar, mijozlar qarzi va mahsulot savdosi haqida javob ber. Kassa, foyda, "
             "dividend, xarajat, postavshik va ishlab chiqarish raqamlari bu rolga kirmaydi.",
    "Buxgalteriya": "«Aylanma» deganda kassa va hisob-kitob harakatini tushun. Kassa, bank, mijoz va "
                    "postavshik qarzlari haqida javob ber. Foyda va dividend bu rolga kirmaydi.",
    "Ishlab chiqarish": "Ishlab chiqarish hajmi, xomashyo sarfi, navbat, brak va tarozi haqida javob ber. "
                        "Pul, savdo summasi, qarzlar, kassa va foyda bu rolga kirmaydi.",
    "Ombor": "Ombor qoldig'i, xomashyo va ishlab chiqarish harakati haqida javob ber. Pul, savdo summasi, "
             "qarzlar, kassa va foyda bu rolga kirmaydi.",
}
KORSATMALAR["Savdo bolimi boshligi"] = KORSATMALAR["Sotuv"]


def execute():
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_roli")
    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_bot_sozlamalari")
    create_custom_fields({"User": [{
        "fieldname": "ai_roli", "fieldtype": "Link", "options": "Nazorat Roli", "label": "AI roli (Nazorat)",
        "insert_after": "role_profile_name", "in_standard_filter": 1,
        "description": "Pokiza AI (web chat va Telegram bot) shu foydalanuvchiga faqat shu rol doirasidagi "
                       "ma'lumotni beradi. Bo'sh — AI ma'lumot bermaydi. System Manager ham shu rol bilan cheklanadi.",
    }]}, update=True)

    from pokiza.nazorat.scope import rol_tgdan

    for a in frappe.get_all("TG Azo", fields=["name", "rol", "bolim"]):
        nom = rol_tgdan(a.rol, a.bolim)
        if nom and frappe.db.exists("Nazorat Roli", nom) and not frappe.db.get_value("User", a.name, "ai_roli"):
            frappe.db.set_value("User", a.name, "ai_roli", nom, update_modified=False)

    rahbar = frappe.db.get_single_value("Nazorat Bot Sozlamalari", "rahbar")
    if rahbar and frappe.db.exists("Nazorat Roli", "Rahbar") and not frappe.db.get_value("User", rahbar, "ai_roli"):
        frappe.db.set_value("User", rahbar, "ai_roli", "Rahbar", update_modified=False)

    for nom, matn in KORSATMALAR.items():
        if frappe.db.exists("Nazorat Roli", nom) and not frappe.db.get_value("Nazorat Roli", nom, "ai_korsatma"):
            frappe.db.set_value("Nazorat Roli", nom, "ai_korsatma", matn, update_modified=False)

    if frappe.db.get_single_value("Nazorat Bot Sozlamalari", "himoya_kop_rad") in (None, ""):
        frappe.db.set_single_value("Nazorat Bot Sozlamalari", "himoya_kop_rad", 3)
