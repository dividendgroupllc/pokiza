"""
Bir martalik: ESKI qoralama schyotlarni zakaz/fakt bilan sinxronlash
(2026-09-30 «schyotda zakaz+fakt» o'zgarishidan OLDIN yaratilgan qoralamalar).

Nimani tuzatadi (faqat docstatus=0, zakazga bog'liq qatorlari borlar):
  * tarozichi fakt yozgan bo'lsa — qator soni faktga tenglashadi
    (summalar qayta hisoblanadi),
  * custom_zakaz_kg (zakazda so'ralgan kg) to'ldiriladi.
Mexanizm: schyot oddiy save qilinadi — before_validate hook o'zi
sinxronlaydi (kelajakdagi oqim bilan bir xil yo'l). Tasdiqlangan
schyotlarga TEGILMAYDI (tarix o'zgarmasligi kerak).

Ishga tushirish:
    # avval ko'rish (hech narsa o'zgarmaydi):
    bench --site pokiza.local execute pokiza.scripts.eski_si_fakt_backfill.dry_run
    # qo'llash:
    bench --site pokiza.local execute pokiza.scripts.eski_si_fakt_backfill.apply
"""

import frappe
from frappe.utils import flt, getdate, today


def _kandidatlar():
    """Tuzatish kerak bo'lgan qoralama schyotlar ro'yxati."""
    rows = frappe.db.sql(
        """
        SELECT sii.parent AS si, sii.item_code,
               sii.qty AS si_qty, soi.qty AS zakaz_kg,
               IFNULL(soi.custom_fakt_kg, 0) AS fakt_kg,
               IFNULL(sii.custom_zakaz_kg, 0) AS joriy_zakaz_kg
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 0
        JOIN `tabSales Order Item` soi ON soi.name = sii.so_detail
            AND soi.docstatus = 1
        WHERE (IFNULL(soi.custom_fakt_kg, 0) > 0
               AND ABS(sii.qty - soi.custom_fakt_kg) > 0.0005)
           OR IFNULL(sii.custom_zakaz_kg, 0) = 0
        ORDER BY sii.parent
        """,
        as_dict=True,
    )
    schyotlar = {}
    for r in rows:
        schyotlar.setdefault(r.si, []).append(r)
    return schyotlar


def dry_run():
    schyotlar = _kandidatlar()
    if not schyotlar:
        print("Tuzatiladigan qoralama schyot yo'q.")
        return
    print(f"{len(schyotlar)} ta qoralama schyot yangilanadi:")
    for si, rows in schyotlar.items():
        print(f"\n  {si}:")
        for r in rows:
            if r.fakt_kg and abs(flt(r.si_qty) - flt(r.fakt_kg)) > 0.0005:
                print(f"    {r.item_code}: soni {flt(r.si_qty, 1)} -> "
                      f"FAKT {flt(r.fakt_kg, 1)} (zakaz {flt(r.zakaz_kg, 1)})")
            else:
                print(f"    {r.item_code}: faqat zakaz kg to'ldiriladi "
                      f"({flt(r.zakaz_kg, 1)})")


def apply():
    schyotlar = _kandidatlar()
    if not schyotlar:
        print("Tuzatiladigan qoralama schyot yo'q.")
        return
    ok, xato = 0, 0
    for si_name in schyotlar:
        try:
            si = frappe.get_doc("Sales Invoice", si_name)
            si.flags.ignore_permissions = True
            # _si_fakt_yangila bilan bir xil: eski qoralamada due_date /
            # payment_schedule sanalari orqada qolgan bo'lsa validatsiya
            # yiqilmasligi uchun bugunga suriladi
            if si.due_date and getdate(si.due_date) < getdate(today()):
                si.due_date = today()
            for ps in si.get("payment_schedule") or []:
                if ps.due_date and getdate(ps.due_date) < getdate(today()):
                    ps.due_date = today()
            si.save()
            ok += 1
            print(f"  ✓ {si_name}")
        except Exception as e:
            xato += 1
            frappe.log_error(
                frappe.get_traceback(),
                f"Pokiza backfill: {si_name} yangilanmadi",
            )
            print(f"  ✗ {si_name}: {e}")
    frappe.db.commit()
    print(f"\nYangilandi: {ok} ta, xato: {xato} ta"
          + (" (Error Log'da batafsil)" if xato else ""))
