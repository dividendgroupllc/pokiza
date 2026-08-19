# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RejaOzgarishJurnali(Document):
    """Reja qo'lda o'zgartirilganda avtomatik yoziladigan jurnal.
    in_create=1 — foydalanuvchi qo'lda yozolmaydi, faqat tizim yozadi;
    o'chirish/tahrirlash huquqi hech kimga berilmagan."""

    def before_insert(self):
        self.kim = frappe.session.user
