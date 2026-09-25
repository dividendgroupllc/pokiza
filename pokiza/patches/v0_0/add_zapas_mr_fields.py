"""Zapas ishlab chiqarish = STANDART Material Request (turi Manufacture).

Egasi talabi (2026-09-25): zapas HECH QANDAY mijozga bog'lanmasin —
Material Request'da mijoz maydoni yo'q, sotuv/debitorka hisobotlariga
aralashmaydi. Bu ERPNext'ning make-to-stock standarti (Work Order /
Production Plan oilasi); bizning kun-quvvat/3 qog'oz/tarozi oqimi
Sales Order'dagidek custom maydonlar + hooklar bilan ulanadi.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "Material Request": [
            {
                "fieldname": "custom_jami_kg",
                "label": "Jami kg",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "schedule_date",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_ishlab_chiqarish_kuni",
                "label": "Ishlab chiqarish kuni (bitish)",
                "fieldtype": "Date",
                "read_only": 1,
                "insert_after": "custom_jami_kg",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_kun_taqsimot",
                "label": "Kunlarga taqsimot",
                "fieldtype": "Table",
                "options": "Kun Taqsimot Qatori",
                "read_only": 1,
                "insert_after": "custom_ishlab_chiqarish_kuni",
                "no_copy": 1,
            },
        ],
        "Material Request Item": [
            {
                "fieldname": "custom_holat",
                "label": "Holat",
                "fieldtype": "Select",
                "options": "Kutilmoqda\nChiqarildi",
                "default": "Kutilmoqda",
                "read_only": 1,
                "insert_after": "qty",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_fakt_kg",
                "label": "Fakt kg",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_holat",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_chiqargan",
                "label": "Kim chiqardi",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_fakt_kg",
                "no_copy": 1,
            },
            {
                "fieldname": "custom_chiqarilgan_vaqt",
                "label": "Chiqarilgan vaqt",
                "fieldtype": "Datetime",
                "read_only": 1,
                "insert_after": "custom_chiqargan",
                "no_copy": 1,
            },
        ],
    }, ignore_validate=True, update=True)
