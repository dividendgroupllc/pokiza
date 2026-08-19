# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint


class IshlabChiqarishSozlamalari(Document):
    def validate(self):
        if flt(self.kunlik_quvvat_kg) <= 0:
            frappe.throw(_("Kunlik quvvat 0 dan katta bo'lishi kerak"))
        if flt(self.zames_kg) <= 0:
            frappe.throw(_("Zames og'irligi 0 dan katta bo'lishi kerak"))
        if cint(self.gorizont_kun) < 1:
            self.gorizont_kun = 7
