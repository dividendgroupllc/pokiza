# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint


class OylikReja(Document):
    def validate(self):
        if not 2020 <= cint(self.yil) <= 2100:
            frappe.throw(_("Yil noto'g'ri"))
        if flt(self.savdo_reja) <= 0:
            frappe.throw(_("Savdo rejasi 0 dan katta bo'lishi kerak"))
        for field in ("sof_marja_reja", "quvvat_reja_t", "sof_daromad_usd_reja"):
            if flt(self.get(field)) < 0:
                frappe.throw(_("{0} manfiy bo'lishi mumkin emas").format(self.meta.get_label(field)))
