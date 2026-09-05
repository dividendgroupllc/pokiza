"""Mijozning odatiy (doim sotib oladigan) itemlari.

Schyotda mijoz tanlanganda items jadvaliga default tushadigan ro'yxat:
so'nggi 90 kundagi tasdiqlangan schyotlardan, har item bo'yicha eng
oxirgi olingan soni va narxi bilan (2026-09-05, egasi talabi).
"""

import frappe

KUNLAR = 90
NARX_GURUHI = "Сотув махсулотлари"


@frappe.whitelist()
def odatiy_itemlar(customer):
    """Mijoz so'nggi KUNLAR ichida olgan itemlar — oxirgi soni/narxi bilan."""
    if not customer or not frappe.has_permission("Sales Invoice", "read"):
        return []

    qatorlar = frappe.db.sql(
        """
        SELECT sii.item_code, sii.item_name, sii.qty, sii.rate, si.posting_date
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE si.docstatus = 1
          AND si.is_return = 0
          AND si.customer = %(customer)s
          AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(kunlar)s DAY)
          AND it.item_group = %(guruh)s
          AND it.disabled = 0
          AND sii.qty > 0
        ORDER BY si.posting_date DESC, si.creation DESC, sii.idx
        """,
        {"customer": customer, "kunlar": KUNLAR, "guruh": NARX_GURUHI},
        as_dict=True,
    )

    # Har item bo'yicha faqat eng oxirgi xarid (ro'yxat sana bo'yicha teskari)
    oxirgi = {}
    for q in qatorlar:
        if q.item_code not in oxirgi:
            oxirgi[q.item_code] = q

    return sorted(oxirgi.values(), key=lambda q: (q.item_name or q.item_code).lower())
