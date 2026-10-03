"""BOM'da sotuv mahsuloti belgisi (egasi 2026-10-03): ro'yxatda sotuv-SKU
BOM'larini rang bilan ajratish va filtrlash uchun avto-check maydon.
Mavjud BOM'lar backfill qilinadi; yangilari events/bom.py validate'da
avto belgilanadi."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "BOM": [
            {
                "fieldname": "custom_sotuv_sku",
                "label": "Sotuv mahsuloti BOMi",
                "fieldtype": "Check",
                "read_only": 1,
                "insert_after": "item_name",
                "in_standard_filter": 1,
                "no_copy": 0,
            },
        ],
    }, ignore_validate=True, update=True)

    frappe.db.sql(
        """
        UPDATE `tabBOM` b
        JOIN `tabItem` i ON i.name = b.item
        SET b.custom_sotuv_sku = 1
        WHERE i.item_group = 'Сотув махсулотлари'
        """
    )
