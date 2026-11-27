"""Kontragent (Customer/Supplier) kartochkasida joriy balansni ko'rsatish.

Balans — GL Entry bo'yicha partiyaning debit − credit yig'indisi:
  Customer:  > 0 -> mijoz bizga qarzdor (debitorka), < 0 -> avans olingan;
  Supplier:  < 0 -> biz qarzdormiz (kreditorka),     > 0 -> avans berilgan.
JS tomoni: public/js/kontragent_balans.js (forma tepasida indikator).
"""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def balans(party_type, party):
    if party_type not in ("Customer", "Supplier"):
        frappe.throw("party_type faqat Customer yoki Supplier")
    frappe.has_permission(party_type, "read", party, throw=True)
    bal = frappe.db.sql(
        """SELECT SUM(debit) - SUM(credit) FROM `tabGL Entry`
        WHERE is_cancelled = 0 AND party_type = %s AND party = %s""",
        (party_type, party))[0][0]
    return flt(bal)
