"""Nazorat tizimi 0-bosqich (docs/NAZORAT_TIZIMI_REJA.md):
- Item.custom_kategoriya (B4 kategoriya ulushi), Account.custom_xarajat_turi (C3 doimiy/o'zgaruvchi);
- Mijoz Kartochkasi: erkin matndagi "70/30 20-SANA" / "NAXT" / "10-SANA" -> tolov_foiz, tolov_kuni (faqat bo'sh bo'lsa);
- Nazorat Sozlamalari standart qiymatlari.
Kategoriya va xarajat turi qiymatlari bu yerda to'ldirilmaydi — pokiza.nazorat.setup orqali tasdiqlab qo'yiladi.
"""
import re

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

KATEGORIYALAR = "\nSosiska\nKopchyonniy\nVaryonniy\nDelikates\nBoshqa"

FIELDS = {
    "Item": [{
        "fieldname": "custom_kategoriya", "fieldtype": "Select", "label": "Kategoriya (nazorat)",
        "options": KATEGORIYALAR, "insert_after": "item_group", "in_standard_filter": 1,
        "depends_on": "eval:doc.item_group=='Сотув махсулотлари'",
        "description": "Rahbar hisobotidagi mahsulot mix (TZ B4)",
    }],
    "Account": [{
        "fieldname": "custom_xarajat_turi", "fieldtype": "Select", "label": "Xarajat turi (nazorat)",
        "options": "\nDoimiy\nO'zgaruvchi", "insert_after": "account_type",
        "depends_on": "eval:doc.root_type=='Expense' && !doc.is_group",
        "description": "Rahbar hisobotida doimiy/o'zgaruvchi xarajat (TZ C3)",
    }],
}


def parse_tolov_sharti(text):
    """'70/30 20-SANA' -> (70, 20); 'NAXT' -> (100, 0); '10-SANA' -> (100, 10); tushunarsiz -> None."""
    s = re.sub(r"\s+", " ", (text or "").upper()).strip()
    if not s:
        return None
    if s in ("NAXT", "НАХТ", "NAQD"):
        return 100, 0
    m = re.fullmatch(r"(?:(\d{1,3})\s*/\s*(\d{1,3})\s+)?(\d{1,2})\s*-?\s*SANA", s)
    if m:
        foiz = int(m[1]) if m[1] else 100
        if m[1] and int(m[1]) + int(m[2]) != 100:
            return None
        return foiz, int(m[3])
    return None


def execute():
    create_custom_fields(FIELDS, ignore_validate=True)
    frappe.reload_doc("pokiza_for_business", "doctype", "mijoz_kartochkasi")
    for r in frappe.get_all("Mijoz Kartochkasi", fields=["name", "tolov_sharti", "tolov_foiz", "tolov_kuni"]):
        if r.tolov_foiz or r.tolov_kuni:
            continue
        parsed = parse_tolov_sharti(r.tolov_sharti)
        if parsed:
            # set_value: on_update (narx sinxroni) ishga tushmasin
            frappe.db.set_value("Mijoz Kartochkasi", r.name, {"tolov_foiz": parsed[0], "tolov_kuni": parsed[1]},
                                update_modified=False)

    frappe.reload_doc("pokiza_for_business", "doctype", "nazorat_sozlamalari")
    s = frappe.get_single("Nazorat Sozlamalari")
    for df in s.meta.fields:
        if df.default and not s.get(df.fieldname):
            s.set(df.fieldname, df.default)
    s.save(ignore_permissions=True)
