# BOM sarf jami maydonlari — syryo jadvalidan avto hisoblash
import frappe
from frappe.utils import flt


def validate(doc, method=None):
    doc.custom_sarf_jami_soni = sum(flt(d.qty) for d in (doc.items or []))
    doc.custom_sarf_jami_summa = sum(flt(d.amount) for d in (doc.items or []))
    # ro'yxatda rang/filtr uchun: sotuv mahsulotining BOMi belgilanadi
    doc.custom_sotuv_sku = 1 if frappe.get_cached_value(
        "Item", doc.item, "item_group") == "Сотув махсулотлари" else 0
