# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""SKU Pasporti — tayyor mahsulotning upakovka normasi (1 kg uchun sarf).

Product Bundle o'rnini bosadi: partiya rejimiga o'tgan SKU ombor itemi
bo'ladi va bundle unga taqiqlanadi (ERPNext qoidasi), upakovka retsepti
esa shu yerda yashaydi. Ishlab chiqarish (PE SKU rejimi) sarflarni shu
pasportdan oladi.
"""

import frappe
from frappe import _
from frappe.model.document import Document

SOTUV_GURUH = "Сотув махсулотлари"
# 2026-11: ГП itemlari «Фарш» guruhiga ko'chirildi — ikkala guruh ham norma
NORMA_GURUHLAR = ("Готовый продукт", "Фарш")


class SKUPasporti(Document):
    def validate(self):
        from pokiza.guruhlar import sotuv_guruhlari
        if self.sku and frappe.get_cached_value("Item", self.sku, "item_group") not in sotuv_guruhlari():
            frappe.throw(_("{0} «{1}» guruhidan emas").format(self.sku, SOTUV_GURUH))
        korilgan = set()
        for q in self.qatorlar:
            if not q.item:
                continue
            if frappe.get_cached_value("Item", q.item, "item_group") in NORMA_GURUHLAR:
                frappe.throw(
                    _("{0}-qator: {1} — norma (farsh) pasportga yozilmaydi, "
                      "u mijoz kartochkasidan olinadi").format(q.idx, q.item))
            if q.item in korilgan:
                frappe.throw(_("{0}-qator: {1} takrorlangan").format(q.idx, q.item))
            korilgan.add(q.item)
