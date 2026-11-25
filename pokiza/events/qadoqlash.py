"""Sotuv (Sales Invoice) tasdiqlanganda — sotilgan har bir mahsulot uchun QORALAMA qadoqlash hujjati
(Stock Entry, Manufacture): default norma (BOM) bo'yicha farsh + upakovka -> sotuv mahsuloti, miqdori
fakturadagidek. Qoralama avtomatik tasdiqlanmaydi — mas'ul xodim tekshirib, o'zi Submit qiladi.

Faktura bekor qilinsa — uning hali tasdiqlanmagan qoralamalari o'chiriladi (tasdiqlanganiga tegilmaydi).
Qaytarish (vozvrat), ommaviy qayta kiritish (flags.asl_bonus / flags.qadoqlashsiz) — qoralama yaratilmaydi.
"""
from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe.utils import flt, get_datetime

BELGI = "Qadoqlash qoralamasi (sotuv {si})"


def _xom_ombor():
    return frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0, "name": ("like", "%сырь%")}, "name")


def _bom(item_code):
    from pokiza.pokiza_for_business.doctype.production_entry.production_entry import get_bom_for_item

    name = get_bom_for_item(item_code)
    return frappe.get_doc("BOM", name) if name else None


def qoralama_yarat(doc, method=None):
    """Sales Invoice on_submit."""
    if doc.is_return or not doc.update_stock or doc.flags.get("asl_bonus") is not None \
            or doc.flags.get("qadoqlashsiz"):
        return
    from pokiza.guruhlar import sotuv_guruhlari

    kerak = defaultdict(float)  # (sku, ombor) -> stock qty
    for r in doc.items:
        if r.item_code and r.warehouse and flt(r.stock_qty) > 0 \
                and frappe.get_cached_value("Item", r.item_code, "is_stock_item") \
                and frappe.get_cached_value("Item", r.item_code, "item_group") in sotuv_guruhlari():
            kerak[(r.item_code, r.warehouse)] += flt(r.stock_qty)
    if not kerak:
        return
    vaqt = get_datetime(f"{doc.posting_date} {doc.posting_time}") - timedelta(minutes=1)
    if vaqt.date() != get_datetime(doc.posting_date).date():
        vaqt = datetime.combine(vaqt.date() + timedelta(days=1), datetime.min.time())
    xom = _xom_ombor()
    yaratildi, normasiz = [], []
    for (sku, ombor), qty in kerak.items():
        try:
            bom = _bom(sku)
            if not bom:
                normasiz.append(sku)
                continue
            se = frappe.new_doc("Stock Entry")
            se.update({
                "stock_entry_type": "Manufacture", "company": doc.company, "posting_date": vaqt.date(),
                "posting_time": vaqt.strftime("%H:%M:%S"), "set_posting_time": 1,
                "from_bom": 1, "bom_no": bom.name, "fg_completed_qty": flt(qty, 3),
                "remarks": BELGI.format(si=doc.name) + f" — {doc.customer_name or doc.customer}, norma {bom.name}",
            })
            k = qty / flt(bom.quantity or 1)
            for b in bom.items:
                se.append("items", {"item_code": b.item_code, "qty": flt(flt(b.stock_qty or b.qty) * k, 6),
                                    "s_warehouse": b.get("source_warehouse") or xom,
                                    "uom": b.stock_uom, "stock_uom": b.stock_uom, "conversion_factor": 1})
            u = frappe.get_cached_value("Item", sku, "stock_uom")
            se.append("items", {"item_code": sku, "qty": flt(qty, 3), "t_warehouse": ombor, "is_finished_item": 1,
                                "uom": u, "stock_uom": u, "conversion_factor": 1})
            se.flags.ignore_permissions = True
            se.insert()
            yaratildi.append(se.name)
        except Exception:
            # qoralama yaratilmasa ham sotuv tasdiqlanaveradi
            frappe.log_error(title=f"Qadoqlash qoralamasi: {doc.name} / {sku}")
            normasiz.append(sku)
    if yaratildi:
        frappe.msgprint(f"Qadoqlash qoralamalari yaratildi ({len(yaratildi)} ta): " + ", ".join(yaratildi),
                        indicator="blue", alert=True)
    if normasiz:
        frappe.msgprint("Qadoqlash qoralamasi yaratilmadi (normasi yo'q yoki xato): " + ", ".join(normasiz),
                        indicator="orange")


def qoralamalarni_ochir(doc, method=None):
    """Sales Invoice on_cancel: shu fakturaning tasdiqlanmagan qadoqlash qoralamalari o'chiriladi."""
    for name in frappe.get_all("Stock Entry", filters={"docstatus": 0, "remarks": ("like", BELGI.format(si=doc.name) + "%")},
                               pluck="name"):
        frappe.delete_doc("Stock Entry", name, ignore_permissions=True)
