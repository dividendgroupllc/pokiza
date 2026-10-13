"""Sales Order formasini soddalashtirish (egasi talabi 2026-10-13).

Keraksiz bo'limlar SERVER darajasida yashiriladi. MUHIM GOTCHA: faqat
Section Break'ni hidden qilish YETMAYDI — ichidagi maydonlar oldingi
ko'rinadigan bo'limga qo'shilib chiqaveradi; shuning uchun bo'lim bilan
birga HAR BIR maydon ham yashiriladi.

Yashiriladi: Customer's Purchase Order (po_no/po_date), Accounting
Dimensions, Currency and Price List, Taxes and Charges, Additional
Discount, hamda custom «So'ralgan kun» (o'rnini delivery_date bosadi —
navbat.so_before_submit fallback) va «Mashina aniq vaqti (ixtiyoriy)».
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import (
    make_property_setter,
)

YASHIRILADI = (
    # Customer's Purchase Order
    "po_no", "po_date", "column_break1",
    # Accounting Dimensions
    "accounting_dimensions_section", "cost_center", "dimension_col_break",
    "project",
    # Currency and Price List
    "currency_and_price_list", "currency", "conversion_rate",
    "column_break2", "selling_price_list", "price_list_currency",
    "plc_conversion_rate", "ignore_pricing_rule",
    # Taxes and Charges
    "taxes_section", "tax_category", "taxes_and_charges",
    "column_break_38", "shipping_rule", "column_break_49",
    "incoterm", "named_place", "section_break_40", "taxes",
    # Additional Discount
    "section_break_48", "apply_discount_on", "base_discount_amount",
    "coupon_code", "column_break_50", "additional_discount_percentage",
    "discount_amount",
)

CUSTOM_YASHIRILADI = ("custom_kerak_kun", "custom_mashina_izoh")


def execute():
    meta = frappe.get_meta("Sales Order")
    for f in YASHIRILADI:
        if not meta.get_field(f):
            continue  # ERPNext versiyasida bo'lmasa — o'tkazib yuboriladi
        make_property_setter(
            "Sales Order", f, "hidden", "1", "Check",
            validate_fields_for_doctype=False,
        )

    for f in CUSTOM_YASHIRILADI:
        cf = frappe.db.get_value("Custom Field",
                                 {"dt": "Sales Order", "fieldname": f})
        if cf:
            frappe.db.set_value("Custom Field", cf, "hidden", 1,
                                update_modified=False)

    frappe.clear_cache(doctype="Sales Order")
