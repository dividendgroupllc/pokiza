"""Mijoz Kartochkasi API — tannarx hisoblash va qoralama to'ldirish.

Tannarx modeli (arxitektura 2026-09-21, egasi tasdiqlagan):
  tannarx so'm/kg = norma farsh narxi (aktiv BOM retsepti boyicha)
                  + SKU upakovka narxi (Product Bundle'ning ГП bo'lmagan
                    qatorlari: qty * item narxi, 1 kg uchun).

MUHIM (2026-09-22): farsh BOM'ning saqlangan total_cost'idan OLINMAYDI —
u BOM oxirgi saqlangan kundagi narx bo'lib qolgan bo'ladi (avto-yangilash
o'chiq, masalan Нитрит BOM'da 103 879 vs skladda 62 936). Buning o'rniga
BOM'dan faqat retsept miqdorlari olinib, har xom ashyo HOZIRGI sklad
narxida qayta hisoblanadi. Item narxi manbai (ikkala qism uchun bir xil):
ombor valuation_rate → Item.valuation_rate → Standard Buying Item Price →
(farshda) BOM qatoridagi rate.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, nowdate

SOTUV_GURUH = "Сотув махсулотлари"
NORMA_GURUH = "Готовый продукт"
KUNLAR = 90  # qoralama uchun sotuv tarixi oynasi


def _norma_farsh_narxi(norma):
    """1 kg farsh tannarxi: BOM retsepti × HOZIRGI sklad narxlari."""
    if not norma:
        return 0.0
    bom = frappe.db.get_value(
        "BOM",
        {"item": norma, "is_active": 1, "is_default": 1, "docstatus": 1},
        ["name", "quantity", "operating_cost"],
        as_dict=True,
    ) or frappe.db.get_value(
        "BOM",
        {"item": norma, "is_active": 1, "docstatus": 1},
        ["name", "quantity", "operating_cost"],
        as_dict=True,
    )
    if not bom or not flt(bom.quantity):
        return 0.0

    qatorlar = frappe.get_all(
        "BOM Item", filters={"parent": bom.name}, fields=["item_code", "qty", "rate"]
    )
    jami = 0.0
    for q in qatorlar:
        narx = _item_narxi(q.item_code) or flt(q.rate)
        jami += flt(q.qty) * narx
    return (jami + flt(bom.operating_cost)) / flt(bom.quantity)


def _item_narxi(item_code):
    """Upakovka/syryo itemining 1 birlik narxi (valuation → Item → Buying)."""
    narx = frappe.db.get_value(
        "Bin", {"item_code": item_code, "valuation_rate": [">", 0]}, "valuation_rate"
    )
    if not narx:
        narx = frappe.db.get_value("Item", item_code, "valuation_rate")
    if not narx:
        narx = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": "Standard Buying"},
            "price_list_rate",
        )
    return flt(narx)


def _upakovka_narxi(sku):
    """SKU bundle'idagi ГП bo'lmagan qatorlar — 1 kg uchun upakovka narxi."""
    qatorlar = frappe.db.sql(
        """
        SELECT pbi.item_code, pbi.qty, i.item_group
        FROM `tabProduct Bundle` pb
        JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
        JOIN `tabItem` i ON i.name = pbi.item_code
        WHERE pb.new_item_code = %s AND IFNULL(pb.disabled, 0) = 0
        """,
        sku,
        as_dict=True,
    )
    jami = 0.0
    for q in qatorlar:
        if q.item_group == NORMA_GURUH:
            continue
        jami += flt(q.qty) * _item_narxi(q.item_code)
    return jami


def bundle_normasi(sku):
    """SKU bundle'idagi norma (ГП) — default norma sifatida.

    Bitta bo'lsa (143 tadan 137 tasi shunday) o'shani qaytaradi,
    aksiya-to'plamlarda (2-3 norma) None: normani odam tanlaydi.
    """
    normalar = frappe.db.sql(
        """
        SELECT pbi.item_code
        FROM `tabProduct Bundle` pb
        JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
        JOIN `tabItem` i ON i.name = pbi.item_code
        WHERE pb.new_item_code = %s AND IFNULL(pb.disabled, 0) = 0
          AND i.item_group = %s
        """,
        (sku, NORMA_GURUH),
    )
    return normalar[0][0] if len(normalar) == 1 else None


@frappe.whitelist()
def tannarx_hisobla(sku, norma=None):
    """1 kg tannarx = farsh (norma BOM) + upakovka (bundle). Izoh bilan."""
    if not frappe.has_permission("Item", "read"):
        frappe.throw(_("Huquq yo'q"))

    farsh = _norma_farsh_narxi(norma)
    upakovka = _upakovka_narxi(sku) if sku else 0.0
    izoh_qism = []
    if norma:
        izoh_qism.append("farsh %s" % fmt_money(farsh, 0))
        if not farsh:
            izoh_qism.append("⚠ normada aktiv BOM yo'q")
    else:
        izoh_qism.append("⚠ norma tanlanmagan")
    izoh_qism.append("upakovka %s" % fmt_money(upakovka, 0))

    return {
        "tannarx": farsh + upakovka,
        "farsh": farsh,
        "upakovka": upakovka,
        "izoh": ", ".join(izoh_qism),
    }


@frappe.whitelist()
def sku_malumot(sku, mijoz=None):
    """Forma uchun: SKU tanlanganda default norma, oxirgi narx, mijoz bonusi."""
    if not frappe.has_permission("Mijoz Kartochkasi", "write"):
        frappe.throw(_("Huquq yo'q"))

    oxirgi_narx = None
    if mijoz:
        oxirgi_narx = frappe.db.sql(
            """
            SELECT sii.rate
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.customer = %s AND sii.item_code = %s
            ORDER BY si.posting_date DESC, si.creation DESC
            LIMIT 1
            """,
            (mijoz, sku),
        )
        oxirgi_narx = flt(oxirgi_narx[0][0]) if oxirgi_narx else None

    bonus = None
    if mijoz:
        bonus = flt(frappe.db.get_value("Customer", mijoz, "custom_bonus_foiz"))

    return {
        "norma": bundle_normasi(sku),
        "oxirgi_narx": oxirgi_narx,
        "bonus_foiz": bonus,
    }


def aktiv_map(mijoz):
    """Mijoz kartochkasidagi Aktiv qatorlar: {sku: {narx, bonus, norma}}.

    Bo'sh dict = kartochka yo'q yoki Aktiv qatori yo'q — chaqiruvchi eski
    xatti-harakatga qaytadi (kartochkasiz mijozlar ishlashda davom etadi).
    """
    rows = frappe.db.sql(
        """
        SELECT q.sku, q.sku_nomi, q.norma, q.sotuv_narxi, q.bonus_foiz
        FROM `tabMijoz Kartochka Qatori` q
        JOIN `tabMijoz Kartochkasi` k ON k.name = q.parent
        WHERE k.mijoz = %s AND q.status = 'Aktiv'
        """,
        mijoz,
        as_dict=True,
    )
    return {r.sku: r for r in rows}


def norma_map(mijoz):
    """{sku: norma} — mijoz kartochkasining Aktiv, normasi kiritilgan
    qatorlari. Ishlab chiqarish rejasi shu normaga yoziladi (Faza 2)."""
    return {s: r.norma for s, r in aktiv_map(mijoz).items() if r.norma}


@frappe.whitelist()
def aktiv_itemlar(mijoz):
    """Zakaz/schyot formalari uchun: mijozning Aktiv kartochka SKU'lari."""
    if not frappe.has_permission("Mijoz Kartochkasi", "read"):
        frappe.throw(_("Huquq yo'q"))
    return sorted(
        aktiv_map(mijoz).values(),
        key=lambda r: (r.sku_nomi or r.sku or "").lower(),
    )


def _mijoz_qatorlari(mijoz):
    """Mijozning 90 kunlik tarixidan kartochka qatorlari (har SKU oxirgi narxi)."""
    tarix = frappe.db.sql(
        """
        SELECT sii.item_code, sii.rate, si.posting_date
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.customer = %(mijoz)s
          AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(kunlar)s DAY)
          AND it.item_group = %(guruh)s AND it.disabled = 0
          AND sii.qty > 0
        ORDER BY si.posting_date DESC, si.creation DESC
        """,
        {"mijoz": mijoz, "kunlar": KUNLAR, "guruh": SOTUV_GURUH},
        as_dict=True,
    )
    oxirgi = {}
    for t in tarix:
        if t.item_code not in oxirgi:
            oxirgi[t.item_code] = t
    return oxirgi


@frappe.whitelist()
def qoralama_toldir(mijoz=None):
    """Kartochkalarni sotuv tarixidan qoralama qilib to'ldiradi.

    mijoz berilsa — faqat o'sha mijozga (mavjud kartochkaga yetishmagan
    SKU qatorlarini qo'shadi), berilmasa — 90 kunda xarid qilgan barcha
    mijozlarga kartochkasi yo'q bo'lsa yaratadi.
    """
    rollar = set(frappe.get_roles())
    if not rollar & {"System Manager", "Sales Manager", "kassa", "investor"}:
        frappe.throw(_("Huquq yo'q"))

    if mijoz:
        mijozlar = [mijoz]
    else:
        mijozlar = [m[0] for m in frappe.db.sql(
            """
            SELECT DISTINCT customer FROM `tabSales Invoice`
            WHERE docstatus = 1 AND is_return = 0
              AND posting_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            """,
            KUNLAR,
        )]

    natija = {"yaratildi": 0, "qator_qoshildi": 0, "otkazildi": 0, "normasiz": []}

    for m in mijozlar:
        tarix = _mijoz_qatorlari(m)
        if not tarix:
            natija["otkazildi"] += 1
            continue

        bonus = flt(frappe.db.get_value("Customer", m, "custom_bonus_foiz"))
        mavjud_nom = frappe.db.get_value("Mijoz Kartochkasi", {"mijoz": m})

        if mavjud_nom:
            doc = frappe.get_doc("Mijoz Kartochkasi", mavjud_nom)
            bor_skular = {q.sku for q in doc.qatorlar}
        else:
            doc = frappe.get_doc({
                "doctype": "Mijoz Kartochkasi",
                "mijoz": m,
                "holat": "Qoralama",
                "kartochka_sana": nowdate(),
                "izoh": "Avto-qoralama: so'nggi %s kunlik sotuv tarixidan" % KUNLAR,
            })
            bor_skular = set()

        qoshildi = 0
        for sku, t in sorted(tarix.items()):
            if sku in bor_skular:
                continue
            norma = bundle_normasi(sku)
            if not norma:
                natija["normasiz"].append("%s / %s" % (m, sku))
            doc.append("qatorlar", {
                "sku": sku,
                "norma": norma,
                "sotuv_narxi": flt(t.rate),
                "bonus_foiz": bonus,
                "amal_sana": nowdate(),
                "status": "Aktiv",
            })
            qoshildi += 1

        if not qoshildi:
            natija["otkazildi"] += 1
            continue

        doc.save(ignore_permissions=True)
        if mavjud_nom:
            natija["qator_qoshildi"] += qoshildi
        else:
            natija["yaratildi"] += 1

    return natija
