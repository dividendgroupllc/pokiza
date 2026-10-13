"""Purchase Invoice defaultlari (egasi talabi 2026-10-13).

Xarid schyoti omborga kirim bilan birga yuritiladi: «Update Stock» default
YOQILGAN, ombor defaulti — xom ashyo (сырьё) skladi. Ikkalasi ham oddiy
default: operator formada o'zgartira oladi. ERPNext o'zi Purchase
Receipt'dan yasalgan schyotda update_stock'ka ruxsat bermaydi — default
yoqiq bo'lsa ham xavfsiz.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import (
    make_property_setter,
)


def execute():
    make_property_setter(
        "Purchase Invoice", "update_stock", "default", "1", "Text",
        validate_fields_for_doctype=False,
    )

    syryo = frappe.db.get_value(
        "Warehouse",
        {"is_group": 0, "disabled": 0, "name": ("like", "%сырь%")},
        "name",
    )
    if syryo:
        make_property_setter(
            "Purchase Invoice", "set_warehouse", "default", syryo, "Data",
            validate_fields_for_doctype=False,
        )

    frappe.clear_cache(doctype="Purchase Invoice")
