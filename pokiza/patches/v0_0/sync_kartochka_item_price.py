# Kartochka narxini mijoz kesimidagi Item Price'ga ko'chirish (2026-10-29).
#
# Nimaga: shu paytgacha shartnoma narxi schyot qatoriga faqat brauzer
# orqali qo'yilardi, sotuvchi songa qo'l tekkizganda esa ERPNext'ning
# `apply_price_list`i uni umumiy prays-list narxiga almashtirib yuborardi
# (sinab ko'rilgan: П/к. "Burxanov" To'yona — 35 070 → 33 400; 799 Aktiv
# qatordan 743 tasida kartochka narxi umumiy narxdan farq qiladi).
# Mijoz kesimidagi Item Price'dan keyin ERPNext kartochka narxini o'zi
# ustun qo'yadi — qarang pokiza/api/narx.py.
#
# Patch idempotent: sinxronla() faqat farqni yozadi, mavjud to'g'ri
# yozuvlarga tegmaydi.
import frappe


def execute():
    from pokiza.api.narx import sinxronla_hammasi

    natija = sinxronla_hammasi()
    frappe.logger().info("sync_kartochka_item_price: %s" % natija)
    for xato in natija.get("xatolar") or []:
        frappe.logger().warning("sync_kartochka_item_price: %s" % xato)
