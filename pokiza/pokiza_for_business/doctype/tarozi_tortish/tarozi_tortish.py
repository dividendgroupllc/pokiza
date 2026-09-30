# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TaroziTortish(Document):
    """Tarozida bo'lib-bo'lib tortish jurnali (2026-09-30): har [+] bosish
    bitta yozuv. in_create=1 — qo'lda yozilmaydi, faqat terminal API yozadi.
    Xato yozuv o'chirilmaydi — holat='Ochirilgan' qilinadi (audit saqlanadi)."""

    def before_insert(self):
        self.kim = frappe.session.user
