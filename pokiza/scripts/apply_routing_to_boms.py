"""
Tayyor mahsulot BOM'lariga 3 etaplik routing ("Kolbasa ishlab chiqarish")
tarqatish: with_operations=1 + routing + transfer_material_against=Job Card,
va har BOM Item'ni etapga biriktirish (Farsh/Shpris/Qadoqlash).

Ishga tushirish:
    # avval ko'rish (hech narsa o'zgarmaydi):
    bench --site pokiza.local2 execute pokiza.scripts.apply_routing_to_boms.dry_run
    # tarqatish:
    bench --site pokiza.local2 execute pokiza.scripts.apply_routing_to_boms.apply

Boshqa mahsulotlar uchun: --kwargs '{"products": ["Mahsulot nomi", ...]}'
"""

import frappe

ROUTING = "Kolbasa ishlab chiqarish"

# Operatsiya -> Sex (Workstation). Routing'da workstation bo'sh bo'lsa shundan olinadi.
OP_WORKSTATION = {
    "Farsh tayyorlash": "Farsh sexi",
    "Shpris": "Shpris sexi",
    "Qadoqlash": "Qadoqlash sexi",
}

DEFAULT_PRODUCTS = [
    "Б СЕРВЛАТ № 44",
    "СЕРВ.ПОКИЗА НИЯТ.Жавохир № 66",
    "Сетка 45 Лого № 79",
]

# Etap aniqlash qoidasi (nom bo'yicha). Qolgani -> Farsh.
SHPRIS_KW = ["азиапак", "шкура", "оболоч", "полоск", "клипс", "гофра", "целлоф",
             "фиброуз", "белкозин", "кутизин", "айцел", "нитк", "шпагат", "сетка"]
QAD_KW = ["этикет", "короб", "скотч", "пакет", "ярлык", "стикер", "наклей",
          "лоток", "термоусад", "вакуум", "упаков", "бирка"]


def classify(item_code):
    low = (item_code or "").lower()
    if any(k in low for k in QAD_KW):
        return "Qadoqlash"
    if any(k in low for k in SHPRIS_KW):
        return "Shpris"
    return "Farsh tayyorlash"


def _target_bom(product):
    return frappe.db.get_value(
        "BOM",
        {"item": product, "is_default": 1, "is_active": 1, "docstatus": 1},
        "name",
    )


def dry_run(products=None):
    """Hech narsa o'zgartirmasdan, har BOM item'ining etap-taqsimotini ko'rsatadi."""
    products = products or DEFAULT_PRODUCTS
    for prod in products:
        bom = _target_bom(prod)
        if not bom:
            print(f"[XATO] {prod}: default faol BOM topilmadi")
            continue
        doc = frappe.get_doc("BOM", bom)
        counts = {"Farsh tayyorlash": [], "Shpris": [], "Qadoqlash": []}
        for it in doc.items:
            counts[classify(it.item_code)].append(it.item_code)
        print(f"\n=== {prod}  ({bom})  with_operations={doc.with_operations} ===")
        for stage, items in counts.items():
            print(f"   {stage}: {len(items)} ta  ->  {items[:4]}")
    print("\nDRY_RUN tugadi — hech narsa o'zgartirilmadi.")


def apply(products=None):
    """3 etaplik routingni BOM'larga tarqatadi (in-place)."""
    products = products or DEFAULT_PRODUCTS

    # Routing operatsiyalariga workstation to'ldirish (bo'sh bo'lsa)
    routing = frappe.get_doc("Routing", ROUTING)
    for rop in routing.operations:
        if not rop.workstation and rop.operation in OP_WORKSTATION:
            rop.workstation = OP_WORKSTATION[rop.operation]
    routing.save(ignore_permissions=True)

    done = []
    for prod in products:
        bom = _target_bom(prod)
        if not bom:
            print(f"[XATO] {prod}: default faol BOM topilmadi")
            continue

        # 1) BOM sarlavha maydonlari
        frappe.db.set_value("BOM", bom, {
            "with_operations": 1,
            "routing": ROUTING,
            "transfer_material_against": "Job Card",
        }, update_modified=False)

        # 2) Operatsiyalarni routing'dan qayta yozish
        frappe.db.delete("BOM Operation", {"parent": bom})
        for idx, rop in enumerate(routing.operations, start=1):
            frappe.get_doc({
                "doctype": "BOM Operation",
                "parent": bom, "parenttype": "BOM", "parentfield": "operations",
                "idx": idx,
                "operation": rop.operation,
                "workstation": rop.workstation or OP_WORKSTATION.get(rop.operation),
                "time_in_mins": rop.time_in_mins or 1,
                "hour_rate": getattr(rop, "hour_rate", 0) or 0,
            }).insert(ignore_permissions=True)

        # 3) Har BOM Item'ni etapga biriktirish
        for it in frappe.get_all("BOM Item", filters={"parent": bom}, fields=["name", "item_code"]):
            frappe.db.set_value("BOM Item", it.name, "operation",
                                classify(it.item_code), update_modified=False)

        done.append((prod, bom))
        print(f"[OK] {prod}: {bom} -> routing tarqatildi")

    frappe.db.commit()
    frappe.clear_cache()
    print(f"\nJami {len(done)} ta BOM yangilandi.")
    return done
