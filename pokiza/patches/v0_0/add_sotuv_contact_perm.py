"""Sotuv/kassa rollariga Kontakt (Contact) o'qish ruxsati.

Saytda Contact'ga Customize orqali «All» roliga if_owner=1 qo'yilgan —
har kim faqat O'ZI yaratgan kontaktni ko'radi. Standart Sales User'siz,
faqat maxsus rolli xodimlar (Sotuv, kassa) shu sabab schyot ochganda
«Не разрешено ... Контакты» xatosiga uchraydi (mijoz kontaktini boshqa
xodim yaratgan bo'lsa). Mijoz kontakti sotuv/kassa uchun ish ma'lumoti —
to'liq o'qish ruxsati beriladi (if_owner'siz)."""

import frappe
from frappe.permissions import add_permission


def execute():
    for rol in ("Sotuv", "kassa"):
        if not frappe.db.exists("Role", rol):
            continue
        if not frappe.db.exists(
            "Custom DocPerm", {"parent": "Contact", "role": rol}
        ):
            add_permission("Contact", rol)
    frappe.clear_cache()
