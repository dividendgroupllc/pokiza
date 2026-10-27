# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Tannarx: NORMA vs FAKT — texnolog uchun chetlanishlar ro'yxati.

Ikki tannarxni yonma-yon qo'yadi:

Ikkala raqam ham SKU ning O'Z o'lchov birligida (odatda kg, ayrim
SKU'larda дона): normativ SKU BOM'ining `quantity` siga bo'linadi, fakt esa
sotilgan songa — shuning uchun дона bilan yuritiladigan SKU'da ham
solishtirish o'rinli.

  NORMATIV (karta)  — SKU BOM retsepti × hozirgi xomashyo narxlari
                      (pokiza.api.kartochka.tannarx_hisobla — mahsulot
                      kartochkasidagi «Tannarx» ustuni aynan shu).
  FAKT (ombor)      — sotuv paytida ombordan haqiqatda chiqqan qiymat
                      (Stock Ledger Entry.stock_value_difference). Bu
                      dashboarddagi «Себестоимость» bilan bir manba.

Farq = fakt − normativ. Ya'ni MUSBAT farq «zavod retseptdan ko'proq
sarflagan yoki qimmatroq xomashyo ketgan», MANFIY farq «retsept haqiqiy
sarfdan qimmat yozilgan — norma qayta ko'rilishi kerak».

QAYTARISH: ikkala tomonda ham ayiriladi — qaytgan tovar sotilmagan
hisoblanadi, uning tannarxi ham omborga qaytgan. Shuning uchun kg ham,
fakt tannarx ham qaytarishdan toza (dashboard bilan bir xil qoida).

Farq manbalari (texnolog shu tartibda qaraydi):
  1. ishlab chiqarishda normadan chetga chiqish (pererasxod/ekonomiya);
  2. SKU BOM'i ishlab chiqarish amalda ishlatayotgan retseptga mos emas;
  3. ombordagi qoldiq eski/arzon partiyadan — moving average lagi;
  4. xomashyo narxi karta oxirgi saqlangandan keyin o'zgargan.
"""

import frappe
from frappe import _
from frappe.utils import flt

SOTUV_GURUH = "Сотув махсулотлари"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not frappe.has_permission("Item", "read"):
        frappe.throw(_("Huquq yo'q"))

    kg_map = _sotuv_kg(filters)
    if not kg_map:
        return _ustunlar(), []

    fakt_map = _fakt_tannarx(filters)
    data = []
    min_farq = flt(filters.get("min_farq"))

    for sku, s in kg_map.items():
        kg = flt(s.kg)
        # qaytarishdan keyin sof kg nolga tushgan/manfiy SKU — bo'lish
        # ma'nosiz, chetlanish hisoblanmaydi
        if kg <= 0.005:
            continue

        normativ = _normativ(sku, filters.get("to_date"))
        fakt_kg = flt(fakt_map.get(sku)) / kg if sku in fakt_map else None

        farq = farq_foiz = None
        if fakt_kg is not None and normativ["tannarx"]:
            farq = fakt_kg - normativ["tannarx"]
            farq_foiz = farq / normativ["tannarx"] * 100

        # Qaytarish sof sotuvdan ko'p bo'lsa (masalan o'tgan oyning tovari
        # qaytgan) birlik tannarxi ma'nosiz raqam beradi — foiz chiqarilmaydi,
        # sabab izohda qoladi.
        if flt(s.qaytgan_kg) > kg:
            farq = farq_foiz = None

        if min_farq and (farq_foiz is None or abs(farq_foiz) < min_farq):
            continue

        data.append({
            "sku": sku,
            "norma": normativ["norma"],
            "uom": s.uom,
            "kg": kg,
            "qaytgan_kg": flt(s.qaytgan_kg),
            "fakt_kg": fakt_kg,
            "normativ_kg": normativ["tannarx"] or None,
            "farq": farq,
            "farq_foiz": farq_foiz,
            "farsh": normativ["farsh"] or None,
            "upakovka": normativ["upakovka"] or None,
            "bom": normativ["bom"],
            "izoh": _izoh(s, normativ, fakt_kg),
        })

    data.sort(key=lambda r: (
        (r["izoh"] or "").startswith("\u26a0"),      # ⚠ ishonchsizlar pastga
        -abs(flt(r["farq_foiz"])),
    ))
    return _ustunlar(), data


def _shartlar(filters):
    shart = ["si.docstatus = 1"]
    qiymat = {}
    if filters.get("from_date"):
        shart.append("si.posting_date >= %(from_date)s")
        qiymat["from_date"] = filters.from_date
    if filters.get("to_date"):
        shart.append("si.posting_date <= %(to_date)s")
        qiymat["to_date"] = filters.to_date
    if filters.get("mijoz"):
        shart.append("si.customer = %(mijoz)s")
        qiymat["mijoz"] = filters.mijoz
    return " AND ".join(shart), qiymat


def _sotuv_kg(filters):
    """{sku: kg (qaytarishdan toza), qaytgan_kg, uom}"""
    shart, qiymat = _shartlar(filters)
    rows = frappe.db.sql(
        f"""
        SELECT
            sii.item_code AS sku,
            SUM(COALESCE(sii.stock_qty, sii.qty, 0)) AS kg,
            SUM(CASE WHEN IFNULL(si.is_return, 0) = 1
                     THEN ABS(COALESCE(sii.stock_qty, sii.qty, 0)) ELSE 0 END) AS qaytgan_kg,
            it.stock_uom AS uom
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE {shart} AND it.item_group = %(guruh)s
        GROUP BY sii.item_code, it.stock_uom
        """,
        dict(qiymat, guruh=SOTUV_GURUH),
        as_dict=True,
    )
    return {r.sku: r for r in rows}


def _fakt_tannarx(filters):
    """{sku: ombordan chiqqan jami qiymat (qaytarishdan toza)}.

    SLE'ni ALOHIDA yig'amiz: bitta schyot qatoriga bir nechta SLE to'g'ri
    keladi (bundle sotuvida farsh + har upakovka alohida qator), shuning
    uchun SLE'ni sii.stock_qty bilan bitta SUM'da birlashtirish kg'ni
    ko'paytirib yuboradi.

    stock_value_difference sotuvda manfiy (tovar chiqdi), qaytarishda
    musbat — shuning uchun minus bilan olinadi va qaytarish o'z-o'zidan
    ayiriladi.
    """
    shart, qiymat = _shartlar(filters)
    rows = frappe.db.sql(
        f"""
        SELECT sii.item_code AS sku, -SUM(sle.stock_value_difference) AS fakt
        FROM `tabStock Ledger Entry` sle
        JOIN `tabSales Invoice Item` sii ON sii.name = sle.voucher_detail_no
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sle.is_cancelled = 0
          AND sle.voucher_type = 'Sales Invoice'
          AND {shart}
        GROUP BY sii.item_code
        """,
        qiymat,
        as_dict=True,
    )
    return {r.sku: flt(r.fakt) for r in rows}


def _normativ(sku, sana=None):
    """Kartochkadagi tannarx bilan AYNAN bir xil raqam.

    Yagona manbadan (Tannarx Davri) o'qiladi — hisobot kartochkadan
    boshqa raqam ko'rsatmasligi uchun. Davr yo'q bo'lsa api o'zi jonli
    hisobga tushadi va buni `manba`da aytadi.
    """
    from pokiza.api.partiya import sku_bom
    from pokiza.api.tannarx import joriy_tannarx

    t = joriy_tannarx(sku, sana)
    b = sku_bom(sku)
    return {
        "norma": t.get("norma"),
        "tannarx": flt(t.get("tannarx")),
        "farsh": flt(t.get("farsh")),
        "upakovka": flt(t.get("upakovka")),
        "bom": b.name if b else None,
        "manba": t.get("manba"),
    }


def _izoh(s, normativ, fakt_kg):
    if fakt_kg is None:
        return _("⚠ ombor harakati yo'q (schyotda «Update Stock» belgilanmagan?)")
    if not normativ["tannarx"]:
        return _("⚠ normativ hisoblanmadi — SKU BOM'i yoki aktiv norma BOM'i yo'q")
    if not normativ["bom"]:
        return _("⚠ SKU BOM'i yo'q — normativ eski usulda (norma BOM + bundle)")
    # Normadan emas, OMBOR HISOBIDAN kelgan buzilish: fakt normativdan
    # ikki barobar arzon chiqsa, bu retsept chetlanishi emas — ko'pincha
    # Stock Reconciliation tannarxni 1 so'mga tushirgan yoki qoldiq manfiyga
    # ketib moving average buzilgan. Texnolog normani qidirib vaqt
    # sarflamasligi uchun ajratib ko'rsatiladi.
    if normativ["tannarx"] and fakt_kg < normativ["tannarx"] * 0.5:
        return _("⚠ ombor bahosi buzilgan ko'rinadi (Stock Reconciliation / manfiy "
                 "qoldiq) — normaga aloqasi yo'q, ombor hisobini tekshirish kerak")
    if flt(s.qaytgan_kg) > flt(s.kg) * 0.2:
        return _("qaytarish ulushi yuqori ({0} {1}) — fakt shunga sezgir").format(
            flt(s.qaytgan_kg, 1), s.uom)
    return ""


def _ustunlar():
    return [
        {"fieldname": "sku", "label": _("SKU"), "fieldtype": "Link", "options": "Item", "width": 240},
        {"fieldname": "norma", "label": _("Norma (farsh)"), "fieldtype": "Link", "options": "Item", "width": 190},
        {"fieldname": "uom", "label": _("Birlik"), "fieldtype": "Data", "width": 70},
        {"fieldname": "kg", "label": _("Sof soni"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "qaytgan_kg", "label": _("Qaytgan"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "normativ_kg", "label": _("Normativ (karta) so'm/birlik"), "fieldtype": "Currency", "width": 160},
        {"fieldname": "fakt_kg", "label": _("Fakt (ombor) so'm/birlik"), "fieldtype": "Currency", "width": 160},
        {"fieldname": "farq", "label": _("Farq so'm/birlik"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "farq_foiz", "label": _("Farq %"), "fieldtype": "Percent", "precision": 1, "width": 90},
        {"fieldname": "farsh", "label": _("shundan farsh"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "upakovka", "label": _("shundan upakovka"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "bom", "label": _("SKU BOM"), "fieldtype": "Link", "options": "BOM", "width": 180},
        {"fieldname": "izoh", "label": _("Izoh"), "fieldtype": "Data", "width": 320},
    ]
