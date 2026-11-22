# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt
"""Vazifa (TZ D1/H6): rahbar beradi, xodim Telegram'da qabul/rad qiladi, muddat nazorati."""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate

OCHIQ = ("Yangi", "Qabul qilindi")
OTISH = {
    "Yangi": {"Qabul qilindi", "Rad etildi", "Bekor qilindi", "Muddati o'tdi"},
    "Qabul qilindi": {"Bajarildi", "Bekor qilindi", "Muddati o'tdi"},
    "Muddati o'tdi": {"Bajarildi", "Bekor qilindi", "Qabul qilindi"},
    "Rad etildi": {"Yangi", "Bekor qilindi"},
    "Bajarildi": {"Qabul qilindi"},
    "Bekor qilindi": {"Yangi"},
}


# tarix kodi (Telegram kartochkasida shu tartibda ko'rinadi)
TARIX_KOD = {"Qabul qilindi": "q", "Rad etildi": "r", "Bajarildi": "b", "Muddati o'tdi": "mo",
             "Bekor qilindi": "bk", "Yangi": "y"}


class Vazifa(Document):
    def tarix_qosh(self, kod, matn=""):
        """Telegram guruh kartochkasi uchun voqealar: 'dd.mm HH:MM|kod|matn'."""
        qator = f"{now_datetime():%d.%m %H:%M}|{kod}|{(matn or '').replace(chr(10), ' ')[:300]}"
        self.tarix = ((self.tarix or "") + "\n" + qator).strip()

    def before_insert(self):
        if not self.berdi:
            self.berdi = frappe.session.user
        if getdate(self.muddat) < getdate(nowdate()):
            frappe.throw(_("Muddat o'tgan sana bo'lmasin"))

    def validate(self):
        eski = self.get_doc_before_save()
        user = frappe.session.user
        from pokiza.nazorat.scope import rahbarmi

        boshliq = bool(eski) and (user == eski.berdi or rahbarmi(user))
        if eski and not boshliq:
            for f in ("sarlavha", "masul", "muddat", "bolim", "tavsif", "berdi", "tasdiqlandi", "tasdiq_vaqti",
                      "qabul_vaqti", "bajarilgan_vaqt", "tarix", "eslatma_yuborildi"):
                if str(eski.get(f) or "") != str(self.get(f) or ""):
                    frappe.throw(_("Mas'ul faqat holat, rad sababi va izohni o'zgartira oladi"))
        if eski and eski.holat != self.holat:
            if self.holat not in OTISH.get(eski.holat, set()):
                frappe.throw(_("Holatni {0} dan {1} ga o'tkazib bo'lmaydi").format(eski.holat, self.holat))
            if self.holat == "Bekor qilindi" and not boshliq:
                frappe.throw(_("Vazifani faqat beruvchi yoki rahbar bekor qila oladi"))
            if self.holat == "Qabul qilindi":
                self.qabul_vaqti = now_datetime()
            if self.holat == "Bajarildi":
                self.bajarilgan_vaqt = now_datetime()
            if eski.holat == "Bajarildi" and self.holat == "Qabul qilindi":
                if not boshliq:
                    frappe.throw(_("Bajarilgan vazifani faqat beruvchi qaytara oladi"))
                self.tasdiqlandi, self.tasdiq_vaqti = 0, None
                self.tarix_qosh("qt", self.flags.get("qaytarish_sababi"))
            else:
                self.tarix_qosh(TARIX_KOD.get(self.holat, "?"), self.rad_sababi if self.holat == "Rad etildi" else "")
        if eski and self.tasdiqlandi and not eski.tasdiqlandi:
            if self.holat != "Bajarildi":
                frappe.throw(_("Faqat bajarilgan vazifani tasdiqlash mumkin"))
            self.tasdiq_vaqti = now_datetime()
            self.tarix_qosh("ok")
        if self.holat == "Rad etildi" and not (self.rad_sababi or "").strip():
            frappe.throw(_("Rad etish sababini yozing"))
        if eski and (eski.masul != self.masul or eski.muddat != self.muddat) and self.holat in ("Rad etildi", "Muddati o'tdi"):
            self.holat = "Yangi"  # boshqa xodimga yoki yangi muddatga qayta berildi
        if eski and eski.muddat != self.muddat:
            self.eslatma_yuborildi = 0

    def after_insert(self):
        frappe.enqueue("pokiza.nazorat.vazifa.yangi_xabar", queue="short", enqueue_after_commit=True, vazifa=self.name)

    def on_update(self):
        eski = self.get_doc_before_save()
        if not eski or self.flags.nz_jim:  # nz_jim — xabarni chaqiruvchi o'zi yuboradi (kunlik tekshiruv)
            return
        if eski.masul != self.masul and self.holat == "Yangi":
            frappe.enqueue("pokiza.nazorat.vazifa.yangi_xabar", queue="short", enqueue_after_commit=True, vazifa=self.name)
        elif eski.holat != self.holat or (self.tasdiqlandi and not eski.tasdiqlandi):
            frappe.enqueue("pokiza.nazorat.vazifa.holat_xabar", queue="short", enqueue_after_commit=True,
                           vazifa=self.name, eski=eski.holat)


def get_permission_query_conditions(user=None):
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    u = frappe.db.escape(user)
    return f"(`tabVazifa`.masul = {u} or `tabVazifa`.berdi = {u})"


def has_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return True
    return user in (doc.masul, doc.berdi)
