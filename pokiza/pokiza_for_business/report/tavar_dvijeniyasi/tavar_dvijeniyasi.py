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

Tannarx ustunlarida 1 BIRLIK NARXI (so'm/dona yoki so'm/kg): SLE dagi haqiqiy
baholash o'zgarishi (stock_value_difference) harakat miqdoriga bo'linadi.
Jami summalar qator ostida emas, tepadagi summary kartochkalarida — aks holda
total-qator birlik narxlarini qo'shib ma'nosiz son chiqarar edi (shu sababli
add_total_row ham o'chirilgan). Harakatsiz qayta baholash qatorida (dona 0,
qiymat o'zgargan) narx chiqmaydi, lekin summasi jami kartochkaga qo'shiladi.

Diqqat: tavar filtrisiz (guruh/sklad bo'yicha) dona yig'indilari ARALASH birlikda
chiqishi mumkin (кг + шт) — summary shuni hisobga olib o'qilsin.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of

EPS = 0.0005

# Hujjat turi TARJIMA QILINMAYDI — tizimda qanday bo'lsa shundayligicha
# chiqadi (foydalanuvchi talabi, 2026-11-28): Stock Entry'da hujjatdagi
# stock_entry_type (Material Receipt, Manufacture, Repack...), qolganlarida
# voucher_type (Purchase Invoice, Sales Invoice, Stock Reconciliation).


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
    jami_kirim_summa = jami_chiqim_summa = 0.0
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
        # 1 birlik narxi: qiymat o'zgarishi / harakat miqdori. Harakatsiz
        # qayta baholashda (dona 0, qiymat bor) narx chiqarilmaydi.
        narx = abs(svd) / abs(movement) if abs(movement) >= EPS else None
        kirim_narx = narx if kirim_dona else None
        chiqim_narx = narx if chiqim_dona else None

        if kirim_dona:
            jami_kirim += kirim_dona
        if chiqim_dona:
            jami_chiqim += chiqim_dona
        # jami summalar (summary kartochkalari uchun) — belgisi bo'yicha
        if svd > 0:
            jami_kirim_summa += svd
        elif svd < 0:
            jami_chiqim_summa += -svd

        data.append({
            "sana": r.posting_date,
            "tavar": r.item_name,
            "item_code": r.item_code,
            "kirim_dona": kirim_dona,
            "kirim_tannarx": kirim_narx,
            "chiqim_dona": chiqim_dona,
            "chiqim_tannarx": chiqim_narx,
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
        {"fieldname": "kirim_tannarx", "label": _("Kirim narxi (1 birlik)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "chiqim_dona", "label": _("Chiqim (dona)"), "fieldtype": "Float", "width": 110},
        {"fieldname": "chiqim_tannarx", "label": _("Chiqim narxi (1 birlik)"), "fieldtype": "Currency", "width": 130},
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
        {"value": flt(jami_kirim_summa), "label": _("Jami kirim tannarxi (summa)"), "datatype": "Currency",
         "currency": "UZS", "indicator": "Green"},
        {"value": flt(jami_chiqim, 3), "label": _("Jami chiqim (dona)"), "datatype": "Float", "indicator": "Red"},
        {"value": flt(jami_chiqim_summa), "label": _("Jami chiqim tannarxi (summa)"), "datatype": "Currency",
         "currency": "UZS", "indicator": "Red"},
        {"value": flt(songgi, 3), "label": _("So'nggi qoldiq"), "datatype": "Float", "indicator": "Blue"},
    ]

    return columns, data, None, None, report_summary


def _hujjat_turi(r, izohlar):
    """Hujjat turi tizimdagidek: Stock Entry'da hujjatning o'z turi
    (stock_entry_type), qolganlarida voucher_type."""
    if r.voucher_type == "Stock Entry":
        return izohlar.get((r.voucher_type, r.voucher_no), {}).get("turi") or "Stock Entry"
    return r.voucher_type


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
            fields=["name", "stock_entry_type", "purpose", "remarks"],
        ):
            izohlar[("Stock Entry", d.name)] = {
                "izoh": _tozala(d.remarks),
                "turi": d.stock_entry_type or d.purpose,
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
