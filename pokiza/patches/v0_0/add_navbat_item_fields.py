"""Sales Order Item'ga ishlab chiqarish holati maydonlari.

Har zakaz qatori 3 bosqichdan o'tadi (navbat sahifasidan boshqariladi):
  Kutilmoqda -> Chiqarildi (fakt kg bilan, ishlab chiqarish tasdiqlaydi)
             -> Jonatildi (sotuv jo'natadi / schyot tasdiqlanganda avtomatik)
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
    "Sales Order Item": [
        {
            "fieldname": "custom_holat",
            "fieldtype": "Select",
            "label": "Ishlab chiqarish holati",
            "options": "Kutilmoqda\nChiqarildi\nJonatildi",
            "default": "Kutilmoqda",
            "read_only": 1,
            "insert_after": "delivered_qty",
            "print_hide": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_fakt_kg",
            "fieldtype": "Float",
            "label": "Fakt chiqqan (kg)",
            "read_only": 1,
            "insert_after": "custom_holat",
            "print_hide": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_chiqarilgan_vaqt",
            "fieldtype": "Datetime",
            "label": "Chiqarilgan vaqt",
            "read_only": 1,
            "insert_after": "custom_fakt_kg",
            "print_hide": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_chiqargan",
            "fieldtype": "Data",
            "label": "Kim tasdiqladi",
            "read_only": 1,
            "insert_after": "custom_chiqarilgan_vaqt",
            "print_hide": 1,
            "allow_on_submit": 1,
        },
    ]
}


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
