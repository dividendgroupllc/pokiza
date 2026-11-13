# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _
from frappe.model.document import Document


class NazoratBotSozlamalari(Document):
    def validate(self):
        if not self.get_password("webhook_secret", raise_exception=False):
            self.webhook_secret = secrets.token_urlsafe(32)
        if self.sayt_url and not self.sayt_url.startswith("https://"):
            frappe.throw(_("Sayt manzili https:// bilan boshlanishi kerak (Telegram faqat HTTPS'ga yuboradi)"))
        if self.faol and not self.get_password("bot_token", raise_exception=False):
            frappe.throw(_("Botni yoqish uchun token kiriting"))
