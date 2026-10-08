"""
Qaytarish (возврат) bloklanadigan mahsulotlarni aniqlash (2026-10-08).

Muammo: qaytgan tovar omborga KIRADI, ERPNext esa uning tannarxini bilishi
shart. Tannarx manbai — shu mahsulotning o'sha ombordagi oldingi harakati.
«Maintain Stock» yoqilgan, lekin omborda hech qachon harakat qilmagan
mahsulotni qaytarib bo'lmaydi (ERPNext «Valuation Rate Missing» / ruscha
«курс оценки» xatosini beradi).

Ishga tushirish (serverda):
    bench --site SAYT execute pokiza.scripts.qaytarish_tekshir.royxat
"""

import frappe
from frappe.utils import flt


def royxat():
    from pokiza.api.partiya import asosiy_ombor

    wh = asosiy_ombor()
    rows = frappe.db.sql(
        """
        SELECT i.name, i.item_name,
               (SELECT b.actual_qty FROM `tabBin` b
                 WHERE b.item_code = i.name AND b.warehouse = %(wh)s) AS qoldiq,
               (SELECT COUNT(*) FROM `tabSales Invoice Item` sii
                 JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE sii.item_code = i.name AND si.docstatus = 1) AS sotilgan
        FROM `tabItem` i
        WHERE i.item_group = 'Сотув махсулотлари'
          AND i.is_stock_item = 1 AND i.disabled = 0
          AND NOT EXISTS (
                SELECT 1 FROM `tabStock Ledger Entry` s
                 WHERE s.item_code = i.name AND s.warehouse = %(wh)s
                   AND s.is_cancelled = 0)
        ORDER BY sotilgan DESC, i.name
        """,
        {"wh": wh},
        as_dict=True,
    )

    jami = frappe.db.count(
        "Item",
        {"item_group": "Сотув махсулотлари", "is_stock_item": 1, "disabled": 0},
    )
    print(f"Ombor: {wh}")
    print(f"Ombor yurituvchi sotuv mahsulotlari: {jami} ta")
    print(f"Shundan QAYTARIB BO'LMAYDIGAN (omborda harakati yo'q): {len(rows)} ta\n")

    if not rows:
        print("✅ Hammasi joyida — har qanday mahsulotni qaytarsa bo'ladi.")
        return

    print(f"{'Mahsulot':50} {'Qoldiq':>10} {'Sotuvlar':>9}")
    print("-" * 72)
    for r in rows:
        print(f"{(r.item_name or r.name)[:48]:50} "
              f"{flt(r.qoldiq, 1) if r.qoldiq is not None else 0:>10} {r.sotilgan:>9}")

    print("\nNima qilish kerak (har biri uchun bittasi):")
    print("  1) Qaytarishni ASL SCHYOTDAN qiling (schyotni ochib «Return / "
          "Credit Note») — tannarx sotuvdan olinadi, hech narsa sozlash shart emas;")
    print("  2) Yoki qaytarishda «Update Stock» belgisini olib tashlang — "
          "faqat pul qaytadi;")
    print("  3) Yoki shu mahsulotga ombor kirimini yozing (ishlab chiqarish / "
          "boshlang'ich qoldiq) — keyin odatdagidek qaytariladi.")
