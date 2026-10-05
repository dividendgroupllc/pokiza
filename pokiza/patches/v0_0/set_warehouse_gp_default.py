"""Sales Invoice.set_warehouse defaulti сырьё emas, ГП sklad bo'lsin.

Customize Form orqali qo'yilgan eski Property Setter (default =
«Склад сырьё - P») har yangi schyotni xom-ashyo skladi bilan ochardi.
Sotuv DOIM tayyor mahsulot (ГП) skladidan — default shunga o'zgartiriladi.
Operator formada qo'lda boshqa skladni tanlashi mumkinligicha qoladi.
"""

import frappe


def execute():
    gp = frappe.db.get_value(
        "Warehouse", {"is_group": 0, "disabled": 0, "name": ("like", "%ГП%")}, "name"
    )
    if not gp:
        # ГП sklad hali ochilmagan sayt — eski defaultni olib tashlash bilan
        # cheklanamiz (JS fallback ГП topilganda o'zi qo'yadi)
        frappe.db.delete(
            "Property Setter",
            {"doc_type": "Sales Invoice", "field_name": "set_warehouse", "property": "default"},
        )
        return

    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    make_property_setter(
        "Sales Invoice",
        "set_warehouse",
        "default",
        gp,
        "Data",
        validate_fields_for_doctype=False,
    )
    frappe.clear_cache(doctype="Sales Invoice")
