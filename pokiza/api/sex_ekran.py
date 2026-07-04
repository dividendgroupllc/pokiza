# Copyright (c) 2026, abdulloh and contributors
# For license information, please see license.txt
"""
Sex plansheti (kartochka ekrani) uchun backend.

Ekran har bir sex (Workstation) uchun "tayyor" Job Card'larni kartochka qilib
ko'rsatadi. Operator bossa Job Card yakunlanadi (submit) va keyingi etap ochiladi.
Ketma-ketlik: keyingi etap kartochkasi faqat oldingi etap tugagach paydo bo'ladi.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def get_sexlar():
    """Barcha sexlar (Workstation) ro'yxati."""
    return frappe.get_all("Workstation", pluck="name", order_by="name")


@frappe.whitelist()
def get_cards(workstation):
    """
    Shu sex uchun 'tayyor' (oldingi etap tugagan) ochiq Job Card'lar.
    Har kartochka: mahsulot nomi, rasm, miqdor (kg), izoh (Sales Order'dan).
    """
    if not workstation:
        return []

    job_cards = frappe.get_all(
        "Job Card",
        filters={
            "workstation": workstation,
            "docstatus": 0,
            "status": ["!=", "Completed"],
        },
        fields=[
            "name", "work_order", "operation", "production_item",
            "item_name", "for_quantity", "sequence_id", "creation",
        ],
        order_by="creation asc",
    )

    cards = []
    for jc in job_cards:
        # Ketma-ketlik: oldingi (kichik sequence_id) job card'lar tugamaган bo'lsa — ko'rsatilmaydi
        if jc.sequence_id:
            prev_pending = frappe.db.exists(
                "Job Card",
                {
                    "work_order": jc.work_order,
                    "sequence_id": ["<", jc.sequence_id],
                    "docstatus": ["!=", 1],
                },
            )
            if prev_pending:
                continue

        image, uom = frappe.db.get_value(
            "Item", jc.production_item, ["image", "stock_uom"]
        ) or (None, "")

        cards.append({
            "job_card":  jc.name,
            "work_order": jc.work_order,
            "operation": jc.operation,
            "item":      jc.production_item,
            "item_name": jc.item_name or jc.production_item,
            "qty":       jc.for_quantity,
            "uom":       uom or "",
            "image":     image,
            "izoh":      _get_izoh(jc.work_order),
        })

    return cards


def _get_izoh(work_order):
    """Izoh matni — bog'langan Sales Order'ning custom_izoh maydonidan."""
    sales_order = frappe.db.get_value("Work Order", work_order, "sales_order")
    if not sales_order:
        return ""
    if not frappe.get_meta("Sales Order").has_field("custom_izoh"):
        return ""
    return frappe.db.get_value("Sales Order", sales_order, "custom_izoh") or ""


@frappe.whitelist()
def complete_card(job_card):
    """
    Job Card'ni bir bosishda yakunlash:
    time log (completed_qty = for_quantity) qo'shib, submit qiladi.
    Sekvensiya ERPNext tomonidan tekshiriladi (oldingi etap tugamasa — xato).
    """
    doc = frappe.get_doc("Job Card", job_card)

    if doc.docstatus == 1 or doc.status == "Completed":
        return {"ok": True, "already": True}

    # Oldingi etaplar tugaganini tekshirish (aks holda frappe.throw beradi)
    doc.validate_sequence_id()

    now = now_datetime()
    doc.append("time_logs", {
        "from_time": now,
        "to_time": now,
        "completed_qty": doc.for_quantity,
    })
    doc.save(ignore_permissions=True)
    doc.submit()

    return {"ok": True, "job_card": doc.name}
