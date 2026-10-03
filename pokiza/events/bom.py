# BOM sarf jami maydonlari — syryo jadvalidan avto hisoblash
import frappe
from frappe.utils import flt


def validate(doc, method=None):
    # FAQAT qoralamada: submit'dan keyin (masalan Is Active'ni o'chirganda)
    # qayta hisoblash float dumi tufayli "Cannot Update After Submit"
    # xatosini beradi (2.37545 vs 2.3754500000000003)
    if doc.docstatus != 0:
        return
    doc.custom_sarf_jami_soni = flt(
        sum(flt(d.qty) for d in (doc.items or [])), 6)
    doc.custom_sarf_jami_summa = flt(
        sum(flt(d.amount) for d in (doc.items or [])), 2)
    # ro'yxatda rang/filtr uchun: sotuv mahsulotining BOMi belgilanadi
    doc.custom_sotuv_sku = 1 if frappe.get_cached_value(
        "Item", doc.item, "item_group") == "Сотув махсулотлари" else 0
