# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint


class NazoratSozlamalari(Document):
    def validate(self):
        if flt(self.oylik_quvvat_t) <= 0:
            frappe.throw(_("Oylik quvvat 0 dan katta bo'lishi kerak"))
        if not 1 <= cint(self.postavshik_tolov_kuni) <= 28:
            frappe.throw(_("Postavshik to'lov kuni 1..28 oralig'ida bo'lishi kerak"))
        pairs = (("quvvat_yashil", "quvvat_sariq"), ("savdo_yashil", "savdo_sariq"),
                 ("daromad_yashil_usd", "daromad_sariq_usd"), ("marja_qizil_pp", "marja_sariq_pp"))
        for hi, lo in pairs:
            if flt(self.get(hi)) < flt(self.get(lo)):
                frappe.throw(_("{0} {1} dan kichik bo'lmasligi kerak").format(
                    self.meta.get_label(hi), self.meta.get_label(lo)))
