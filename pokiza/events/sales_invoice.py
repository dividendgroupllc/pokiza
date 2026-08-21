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
