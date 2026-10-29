# Mijoz Kartochkasi moduli uchun indekslar (2026-10-29).
#
# Nimaga kerak (EXPLAIN bilan tekshirilgan, pokiza.local: 2 973 schyot,
# 11 675 schyot qatori, 58 kartochka, 1 546 jurnal yozuvi):
#
# 1. `tabMijoz Kartochka Qatori`.sku — bola jadvalda faqat `parent`
#    indeksi bor edi. «Bu SKU qaysi mijozlarda bor / qaysi narxda?»
#    kesimi (marja tahlili, narx taqqoslash, Tannarx Norma Fakt) 819
#    qatorni to'liq skan qilardi. Qatorlar soni mijoz×SKU bo'yicha
#    o'sadi, shuning uchun indeks hozirdan kerak.
#
# 2. `tabKartochka Ozgarish Jurnali` (mijoz, sku) — jurnal faqat
#    yoziladi, hech qachon tozalanmaydi (har saqlashda yangi qatorlar).
#    List view esa doim mijoz yoki SKU bo'yicha filtrlanadi, indeks esa
#    faqat `creation`/`modified`da bor edi → to'liq skan.
#
# 3. `tabSales Invoice` (customer, docstatus, posting_date) — kartochka
#    moduli mijozning 90 kunlik tarixini o'qiydi (odatiy_itemlar,
#    sku_malumot, qoralama_toldir). EXPLAIN'da `customer` indeksi
#    ishlatilib, keyin «Using filesort» chiqardi: sana filtri va
#    ORDER BY posting_date indeksdan foydalanmasdi. Kompozit indeks
#    uchala shartni bitta oraliq skan bilan yopadi.
import frappe


def execute():
    for doctype, fields, nomi in (
        ("Mijoz Kartochka Qatori", ["sku"], None),
        ("Kartochka Ozgarish Jurnali", ["mijoz", "sku"], "jurnal_mijoz_sku"),
        ("Sales Invoice", ["customer", "docstatus", "posting_date"],
         "pokiza_si_customer_docstatus_date"),
    ):
        try:
            frappe.db.add_index(doctype, fields, index_name=nomi)
        except Exception:
            # indeks allaqachon bor yoki jadval hali yo'q — migrate to'xtamasin
            frappe.log_error(frappe.get_traceback(), "add_kartochka_indexes: %s" % doctype)
