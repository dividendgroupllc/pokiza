"""Sales Order: oldinga tortilgan zakazning ASL kuni (2026-10-13, egasi talabi).

Kun rejasi to'lmagan bo'lsa, keyingi kundagi zakazni bo'sh joyga tortib
kelish mumkin (navbat sahifasidagi taklif). Zakazning "o'z joyi" shu
maydonda saqlanadi: o'sha kunga birdan yangi zakaz kelsa, tizim avval
tortilgan zakazni shu kunga qaytaradi, keyin yangi zakazni yozadi.
Bo'sh (NULL) = zakaz hech qayerdan tortilmagan.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
    "Sales Order": [
        {
            "fieldname": "custom_tortilgan_asl_kun",
            "fieldtype": "Date",
            "label": "Oldinga tortilgan (asl kuni)",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "custom_ishlab_chiqarish_kuni",
            "description": "Bo'sh joyni to'ldirish uchun oldinga tortilgan "
                           "zakazning o'z kuni — yangi zakaz kelsa shu kunga qaytadi",
        },
    ]
}


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
