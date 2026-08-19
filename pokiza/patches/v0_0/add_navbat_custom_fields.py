"""Sales Order'ga ishlab chiqarish navbati uchun custom fieldlar.

Yangi bo'lim "Ishlab chiqarish rejasi":
  - custom_kelgan_vaqt        : zakaz qachon kelgani (kesim vaqti bilan solishtiriladi)
  - custom_mashina_vaqti      : yuk mashinasi qachon keladi (navbat tartibi shu bo'yicha)
  - custom_mashina_izoh       : aniq vaqt izohi (masalan "09:30")
  - custom_jami_kg            : tizim hisoblagan jami og'irlik (read-only)
  - custom_ishlab_chiqarish_kuni : tizim tayinlagan reja kuni (read-only,
                                   qo'lda surish faqat navbat sahifasi orqali — jurnal bilan)
  - custom_kg_nomalum         : kg aniqlanmagan qatorlar ro'yxati (read-only, ogohlantirish)
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
    "Sales Order": [
        {
            "fieldname": "custom_reja_section",
            "fieldtype": "Section Break",
            "label": "Ishlab chiqarish rejasi",
            "insert_after": "skip_delivery_note",
            "collapsible": 0,
        },
        {
            "fieldname": "custom_kelgan_vaqt",
            "fieldtype": "Datetime",
            "label": "Zakaz kelgan vaqt",
            "default": "Now",
            "insert_after": "custom_reja_section",
        },
        {
            "fieldname": "custom_mashina_vaqti",
            "fieldtype": "Select",
            "label": "Mashina vaqti",
            "options": "Ertalab\nTushlik / abed atrofi\nKechki salqin\nBoshqa vaqt",
            "default": "Ertalab",
            "insert_after": "custom_kelgan_vaqt",
        },
        {
            "fieldname": "custom_mashina_izoh",
            "fieldtype": "Data",
            "label": "Mashina aniq vaqti (ixtiyoriy)",
            "insert_after": "custom_mashina_vaqti",
        },
        {
            "fieldname": "custom_reja_col",
            "fieldtype": "Column Break",
            "insert_after": "custom_mashina_izoh",
        },
        {
            "fieldname": "custom_jami_kg",
            "fieldtype": "Float",
            "label": "Jami og'irlik (kg)",
            "read_only": 1,
            "insert_after": "custom_reja_col",
        },
        {
            "fieldname": "custom_ishlab_chiqarish_kuni",
            "fieldtype": "Date",
            "label": "Ishlab chiqarish kuni",
            "read_only": 1,
            "in_list_view": 0,
            "in_standard_filter": 1,
            "insert_after": "custom_jami_kg",
        },
        {
            "fieldname": "custom_kg_nomalum",
            "fieldtype": "Small Text",
            "label": "Kg aniqlanmagan qatorlar",
            "read_only": 1,
            "insert_after": "custom_ishlab_chiqarish_kuni",
        },
    ]
}


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
