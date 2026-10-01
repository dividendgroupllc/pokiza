# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BrakVozvrat(Document):
    """Kun oxirida tarozichi yig'ib qaytargan brak jurnali (2026-10-01):
    mahsulotdan N kg brak → farshi NORMA (ГП) bo'lib xom ashyo hisobiga
    qaytadi, upakovkasi rasxodga ketadi. in_create=1 — faqat terminal
    API yozadi."""

    def before_insert(self):
        self.kim = frappe.session.user
