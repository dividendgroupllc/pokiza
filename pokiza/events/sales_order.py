"""Sales Order doc_events: submit bo'lganda draft Sales Invoice yaratish."""

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice


def _has_existing_invoice(sales_order: str) -> bool:
    """Shu Sales Order uchun bekor qilinmagan Sales Invoice bormi?"""
    return bool(frappe.db.exists(
        "Sales Invoice Item",
        {
            "sales_order": sales_order,
            "docstatus": ["<", 2],
        },
    ))


def on_submit(doc, method=None) -> None:
    """Sales Order submit bo'lganda o'sha ma'lumotlar bilan draft Sales Invoice yaratish."""
    # Ikki marta yaratilib ketmasligi uchun
    if _has_existing_invoice(doc.name):
        return

    try:
        si = make_sales_invoice(doc.name, ignore_permissions=True)
        if not si.get("items"):
            return

        # SANALAR MODELI (egasi 2026-10-15): schyot sanasi = Delivery Date
        # (zakaz sanasi esa ishlab chiqarish kuni). set_posting_time=1 —
        # keyingi saqlashlarda sana bugunga surilib ketmasin.
        if doc.get("delivery_date"):
            si.set_posting_time = 1
            si.posting_date = doc.delivery_date
            si.posting_time = "15:00:00"
            if not si.get("due_date") or getdate(si.due_date) < getdate(doc.delivery_date):
                si.due_date = doc.delivery_date

        si.flags.ignore_permissions = True
        si.insert(ignore_permissions=True)
    except Exception:
        # Sales Order submit bo'lishiga to'sqinlik qilmasin
        frappe.log_error(
            frappe.get_traceback(),
            f"Pokiza: {doc.name} uchun avtomatik Sales Invoice yaratilmadi",
        )
        frappe.msgprint(
            _("Avtomatik Sales Invoice yaratilmadi. Error Log'ni tekshiring."),
            indicator="orange",
            alert=True,
        )
        return

    frappe.msgprint(
        _("Draft Sales Invoice yaratildi: {0}").format(
            f'<a href="/app/sales-invoice/{si.name}"><b>{si.name}</b></a>'
        ),
        indicator="green",
        alert=True,
    )
