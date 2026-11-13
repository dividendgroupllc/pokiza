# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt
"""Nazorat roli: Telegram bot, AI va rahbar panelida kim nimani ko'rishi — ERP'dan sozlanadi (koddan emas)."""
import frappe
from frappe import _
from frappe.model.document import Document

TIZIM_ROLLARI = ("Rahbar",)


class NazoratRoli(Document):
    def validate(self):
        if self.name == "Rahbar" and not self.toliq_ruxsat:
            frappe.throw(_("Rahbar roli to'liq ruxsatli bo'lishi kerak"))

    def on_trash(self):
        if self.name in TIZIM_ROLLARI:
            frappe.throw(_("{0} — tizim roli, o'chirib bo'lmaydi").format(self.name))
