# BOM sarf jami maydonlari — syryo jadvalidan avto hisoblash
import frappe
from frappe.utils import flt


def validate(doc, method=None):
    doc.custom_sarf_jami_soni = sum(flt(d.qty) for d in (doc.items or []))
    doc.custom_sarf_jami_summa = sum(flt(d.amount) for d in (doc.items or []))
