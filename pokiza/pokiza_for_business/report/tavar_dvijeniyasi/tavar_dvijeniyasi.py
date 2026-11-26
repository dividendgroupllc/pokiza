# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Tavar dvijeniyasi — davr ichidagi kirim/chiqim lentasi (1C «Движение товара» uslubi).

Har bir qator = bitta Stock Ledger Entry (hujjat x tavar x sklad):
Sana | Tavar | Kirim dona/tannarx | Chiqim dona/tannarx | Hujjat turi | Hujjat (link) | Sklad | Izoh

Tepada summary: Boshlang'ich qoldiq, Jami kirim, Jami chiqim, So'ngi qoldiq.

MUHIM gotcha: Stock Reconciliation yozuvlarida actual_qty = 0 (ERPNext qty_after_transaction
ni to'g'ridan-to'g'ri qo'yadi). Shuning uchun harakat miqdori shunday hisoblanadi:
har (tavar, sklad) oqimi bo'yicha yurib, movement = qty_after_transaction - oldingi balans.
Shunda Boshlang'ich + Kirim - Chiqim = So'ngi qoldiq doim bajariladi.

Tannarx = stock_value_difference (SLE dagi haqiqiy baholash o'zgarishi) — kirimda musbat,
chiqimda manfiy bo'ladi, mos ustunga absolyut qiymati yoziladi.

Diqqat: tavar filtrisiz (guruh/sklad bo'yicha) dona yig'indilari ARALASH birlikda
chiqishi mumkin (кг + шт) — summary shuni hisobga olib o'qilsin.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of

EPS = 0.0005

HUJJAT_TURI_UZ = {
    "Purchase Invoice": "Zakup (kirim schyoti)",
    "Sales Invoice": "Sotuv (schyot)",
    "Stock Reconciliation": "Inventarizatsiya",
}

STOCK_ENTRY_TURI_UZ = {
    "Material Receipt": "Kirim (qabul)",
    "Material Issue": "Spisaniye",
    "Material Transfer": "Ko'chirish",
    "Material Transfer for Manufacture": "Ishlab chiqarishga uzatish",
    "Manufacture": "Ishlab chiqarish",
    "Repack": "Qayta qadoqlash",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not (filters.get("from_date") and filters.get("to_date")):
        frappe.throw(_("Davr (dan/gacha) tanlanishi shart"))

    shart = ["sle.is_cancelled = 0"]
    params = {"from_date": filters.from_date, "to_date": filters.to_date}

    if filters.get("warehouse"):
        shart.append("sle.warehouse = %(warehouse)s")
        params["warehouse"] = filters.warehouse
    if filters.get("item_code"):
        shart.append("sle.item_code = %(item_code)s")
        params["item_code"] = filters.item_code
    if filters.get("item_group"):
        # guruh daraxti: tanlangan guruh + barcha bolalari
        guruhlar = get_descendants_of("Item Group", filters.item_group) or []
        guruhlar.append(filters.item_group)
        shart.append("i.item_group IN %(guruhlar)s")
        params["guruhlar"] = tuple(guruhlar)

    shart_sql = " AND ".join(shart)

    # ---- boshlang'ich qoldiq: har (tavar, sklad) bo'yicha davrdan OLDINGI oxirgi balans
    opening_rows = frappe.db.sql(
        f"""
        SELECT item_code, warehouse, qty_after_transaction
        FROM (
            SELECT sle.item_code, sle.warehouse, sle.qty_after_transaction,
                   ROW_NUMBER() OVER (
                       PARTITION BY sle.item_code, sle.warehouse
                       ORDER BY sle.posting_datetime DESC, sle.creation DESC
                   ) AS rn
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE {shart_sql} AND sle.posting_date < %(from_date)s
        ) t
        WHERE rn = 1
        """,
        params,
        as_dict=True,
    )
    balans = {(r.item_code, r.warehouse): flt(r.qty_after_transaction) for r in opening_rows}
    boshlangich = sum(balans.values())

    # ---- davr ichidagi yozuvlar, oqim bo'yicha tartiblangan (balansni yurgizish uchun)
    rows = frappe.db.sql(
        f"""
        SELECT sle.posting_date, sle.posting_datetime, sle.creation,
               sle.item_code, COALESCE(NULLIF(i.item_name, ''), i.name) AS item_name,
               i.stock_uom,
               sle.warehouse, sle.voucher_type, sle.voucher_no,
               sle.actual_qty, sle.qty_after_transaction, sle.stock_value_difference
        FROM `tabStock Ledger Entry` sle
        JOIN `tabItem` i ON i.name = sle.item_code
        WHERE {shart_sql}
          AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY sle.item_code, sle.warehouse, sle.posting_datetime, sle.creation
        """,
        params,
        as_dict=True,
    )

    izohlar = _izohlarni_olish(rows)

    data = []
    jami_kirim = jami_chiqim = 0.0
    for r in rows:
        kalit = (r.item_code, r.warehouse)
        oldingi = balans.get(kalit, 0.0)

        # Inventarizatsiyada actual_qty=0 — harakat balans farqidan olinadi
        movement = flt(r.actual_qty) or (flt(r.qty_after_transaction) - oldingi)
        balans[kalit] = flt(r.qty_after_transaction)

        svd = flt(r.stock_value_difference)
        if abs(movement) < EPS and abs(svd) < 0.01:
            continue  # hech nima o'zgarmagan (masalan, farqsiz inventarizatsiya qatori)

        kirim_dona = movement if movement > EPS else None
        chiqim_dona = -movement if movement < -EPS else None
        # tannarx harakat yo'nalishiga emas, qiymat o'zgarishi belgisiga qarab yotqiziladi
        # (qayta baholashda dona 0 bo'lsa ham qiymat o'zgaradi)
        kirim_tannarx = svd if svd > 0 else None
        chiqim_tannarx = -svd if svd < 0 else None

        if kirim_dona:
            jami_kirim += kirim_dona
        if chiqim_dona:
            jami_chiqim += chiqim_dona

        data.append({
            "sana": r.posting_date,
            "tavar": r.item_name,
            "item_code": r.item_code,
            "kirim_dona": kirim_dona,
            "kirim_tannarx": kirim_tannarx,
            "chiqim_dona": chiqim_dona,
            "chiqim_tannarx": chiqim_tannarx,
            "birlik": r.stock_uom,
            "hujjat_turi": _hujjat_turi(r, izohlar),
            "voucher_type": r.voucher_type,
            "hujjat": r.voucher_no,
            "sklad": r.warehouse,
            "izoh": izohlar.get((r.voucher_type, r.voucher_no), {}).get("izoh") or "",
            "_tartib": (r.posting_datetime, r.creation),
        })

    songgi = sum(balans.values())

    # foydalanuvchiga xronologik lenta qulay
    data.sort(key=lambda d: d.pop("_tartib"))

    columns = [
        {"fieldname": "sana", "label": _("Sana"), "fieldtype": "Date", "width": 95},
        {"fieldname": "tavar", "label": _("Tavar"), "fieldtype": "Data", "width": 220},
        {"fieldname": "kirim_dona", "label": _("Kirim (dona)"), "fieldtype": "Float", "width": 110},
        {"fieldname": "kirim_tannarx", "label": _("Kirim tannarxi"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "chiqim_dona", "label": _("Chiqim (dona)"), "fieldtype": "Float", "width": 110},
        {"fieldname": "chiqim_tannarx", "label": _("Chiqim tannarxi"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "birlik", "label": _("Birlik"), "fieldtype": "Data", "width": 70},
        {"fieldname": "hujjat_turi", "label": _("Hujjat turi"), "fieldtype": "Data", "width": 170},
        {"fieldname": "hujjat", "label": _("Hujjat"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
        {"fieldname": "sklad", "label": _("Sklad"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
        {"fieldname": "izoh", "label": _("Izoh"), "fieldtype": "Data", "width": 280},
        {"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 100, "hidden": 1},
    ]

    report_summary = [
        {"value": flt(boshlangich, 3), "label": _("Boshlang'ich qoldiq"), "datatype": "Float", "indicator": "Blue"},
        {"value": flt(jami_kirim, 3), "label": _("Jami kirim (dona)"), "datatype": "Float", "indicator": "Green"},
        {"value": flt(jami_chiqim, 3), "label": _("Jami chiqim (dona)"), "datatype": "Float", "indicator": "Red"},
        {"value": flt(songgi, 3), "label": _("So'nggi qoldiq"), "datatype": "Float", "indicator": "Blue"},
    ]

    return columns, data, None, None, report_summary


def _hujjat_turi(r, izohlar):
    """Hujjat turining tushunarli nomi; Stock Entry uchun aniq maqsadi ko'rsatiladi."""
    if r.voucher_type == "Stock Entry":
        purpose = izohlar.get((r.voucher_type, r.voucher_no), {}).get("purpose") or ""
        return STOCK_ENTRY_TURI_UZ.get(purpose, purpose or "Stock Entry")
    return HUJJAT_TURI_UZ.get(r.voucher_type, r.voucher_type)


def _izohlarni_olish(rows):
    """Hujjatlardan izoh/kontragentni TUR BO'YICHA bitta so'rovda yig'ish.

    Natija: {(voucher_type, voucher_no): {"izoh": ..., "purpose": ...}}
    """
    nomlar = {}
    for r in rows:
        nomlar.setdefault(r.voucher_type, set()).add(r.voucher_no)

    izohlar = {}

    def _tozala(remarks):
        remarks = (remarks or "").strip()
        return "" if remarks in ("No Remarks", "Нет комментариев") else remarks

    if nomlar.get("Stock Entry"):
        for d in frappe.get_all(
            "Stock Entry",
            filters={"name": ("in", list(nomlar["Stock Entry"]))},
            fields=["name", "purpose", "remarks"],
        ):
            izohlar[("Stock Entry", d.name)] = {
                "izoh": _tozala(d.remarks),
                "purpose": d.purpose,
            }

    for dt, kontragent_maydon in (
        ("Purchase Invoice", "supplier_name"),
        ("Sales Invoice", "customer_name"),
    ):
        if not nomlar.get(dt):
            continue
        for d in frappe.get_all(
            dt,
            filters={"name": ("in", list(nomlar[dt]))},
            fields=["name", kontragent_maydon, "remarks"],
        ):
            qismlar = [d.get(kontragent_maydon) or "", _tozala(d.remarks)]
            izohlar[(dt, d.name)] = {"izoh": " — ".join(p for p in qismlar if p)}

    return izohlar
