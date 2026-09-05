"""Sales Invoice doc_events: narxsiz sotuvni bloklash.

Schyot qatoridagi tovar "Сотув махсулотлари" guruhidan bo'lsa va shu
qatordagi narxi (rate) 0 bo'lsa, schyot submit bo'lmaydi. Schyotning
o'zida narx qo'yilsa — bemalol o'tadi.
"""

import frappe
from frappe import _
from frappe.utils import flt

NARX_GURUHI = "Сотув махсулотлари"


def before_submit(doc, method=None) -> None:
    """'Сотув махсулотлари' guruhidagi tovar narxi 0 bo'lsa submit'ni to'xtatish."""
    narxsiz = []
    for row in doc.get("items") or []:
        if not row.item_code or flt(row.rate):
            continue
        item_group = frappe.get_cached_value("Item", row.item_code, "item_group")
        if item_group == NARX_GURUHI:
            narxsiz.append(row.item_code)

    if narxsiz:
        royxat = "".join(f"<li><b>{frappe.utils.escape_html(i)}</b></li>"
                         for i in sorted(set(narxsiz)))
        frappe.throw(
            _("Quyidagi tovarlarning narxi 0 — schyotni tasdiqlab bo'lmaydi. "
              "Avval qatordagi narxni kiriting:")
            + f"<ul>{royxat}</ul>",
            title=_("Narx kiritilmagan"),
        )


def validate(doc, method=None) -> None:
    """Yangi schyotga mijozning doimiy bonus foizini avtomatik qo'llash.

    Bonus Customer.custom_bonus_foiz maydonidan olinadi va umumiy summadan
    (Grand Total) chegirma sifatida ayiriladi — qarzdorlik sof summada yoziladi.
    Faqat birinchi saqlashda va chegirma qo'lda kiritilmagan bo'lsa ishlaydi —
    keyin sotuvchi qiymatni shu schyot uchun erkin o'zgartira oladi.
    """
    if not doc.is_new() or not doc.customer:
        return
    if flt(doc.additional_discount_percentage) or flt(doc.discount_amount):
        return  # qo'lda kiritilgan chegirma ustuvor
    bonus = flt(frappe.get_cached_value("Customer", doc.customer, "custom_bonus_foiz"))
    if not bonus:
        return
    doc.apply_discount_on = "Grand Total"
    doc.additional_discount_percentage = bonus
    # validate hook standart hisob-kitobdan KEYIN chaqiriladi — qayta hisoblaymiz
    doc.calculate_taxes_and_totals()
