"""Kontrol Marj hisoboti uchun maydonlar:
- Item.custom_kategoriya opsiyalariga "Tushonka" qo'shiladi (avval тушенка "Boshqa"ga tushardi);
- Item.custom_subkategoriya (brend: Burxanov / Pokiza / Nejnaya / ...) — hisobotning 2-darajasi.
Qiymatlar bu yerda to'ldirilmaydi — pokiza.nazorat.setup.taklif/qollash orqali tasdiqlab qo'yiladi.
"""
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

KATEGORIYALAR = "\nSosiska\nKopchyonniy\nVaryonniy\nDelikates\nTushonka\nBoshqa"

FIELDS = {
    "Item": [
        {
            "fieldname": "custom_kategoriya", "fieldtype": "Select", "label": "Kategoriya (nazorat)",
            "options": KATEGORIYALAR, "insert_after": "item_group", "in_standard_filter": 1,
            "depends_on": "eval:doc.item_group=='Сотув махсулотлари'",
            "description": "Rahbar hisobotidagi mahsulot mix (TZ B4) va Kontrol Marj 1-darajasi",
        },
        {
            "fieldname": "custom_subkategoriya", "fieldtype": "Data", "label": "Sub-kategoriya (brend)",
            "insert_after": "custom_kategoriya", "in_standard_filter": 1,
            "depends_on": "eval:doc.item_group=='Сотув махсулотлари'",
            "description": "Kontrol Marj 2-darajasi: Burxanov / Pokiza / Nejnaya / ...",
        },
    ],
}


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
