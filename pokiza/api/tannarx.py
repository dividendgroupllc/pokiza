# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Normativ tannarxning YAGONA o'qish nuqtasi.

Qoida (2026-10-28): normativ tannarxni hech kim o'zi hisoblamaydi —
hamma shu moduldan o'qiydi. Manba «Tannarx Davri» doctype'i: bitta
davr → bitta SKU → bitta raqam.

Kim ishlatadi:
  * Mijoz Kartochkasi (validate) — qatorlarga tannarx shundan tushadi;
  * Sales Invoice (before_submit) — sotuv paytidagi muzlatish shundan;
  * Tannarx Norma Fakt hisoboti — normativ ustuni shundan.

DAVR TANLASH: sanani O'Z ICHIGA OLGAN tasdiqlangan davr. Bo'lmasa —
sanadan oldingi eng yangi tasdiqlangan davr (oy boshida hali yangi davr
yaratilmagan bo'lsa ish to'xtamaydi). Umuman tasdiqlangan davr bo'lmasa
jonli hisobga tushadi, lekin `manba` maydonida buni aytib turadi —
jim qolib noto'g'ri raqam bermaydi.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

JONLI = "jonli (tasdiqlangan davr yo'q)"


def _davr_nomi(sana=None):
    """Berilgan sanaga tegishli tasdiqlangan davr nomi (yoki None)."""
    sana = getdate(sana or nowdate())
    nomi = frappe.db.sql(
        """
        SELECT name FROM `tabTannarx Davri`
        WHERE holat = 'Tasdiqlangan' AND davr_boshi <= %(sana)s
        ORDER BY davr_boshi DESC LIMIT 1
        """,
        {"sana": sana},
    )
    return nomi[0][0] if nomi else None


def davr_map(sana=None):
    """{sku: {tannarx, farsh, upakovka, norma, davr}} — bitta so'rovda.

    Kartochka saqlashda 30-40 qator bo'ladi, har biriga alohida so'rov
    yubormaslik uchun shu funksiya ishlatiladi.

    SO'ROV ICHIDA KESHLANADI (2026-10-29): joriy_tannarx() davrda yo'q
    har SKU uchun davr_map()ni QAYTA chaqirardi — schyotda 20 ta yangi
    SKU bo'lsa 20 marta butun Tannarx Davri Qatori o'qilardi. Davr
    «muzlatilgan» (Tasdiqlangan) ma'lumot, bitta so'rov ichida
    o'zgarmaydi — shuning uchun sana bo'yicha keshlash xavfsiz.
    Qayta hisoblashdan keyin kesh davr_keshni_tozala() bilan tozalanadi.
    """
    kesh = getattr(frappe.local, "pokiza_davr_keshi", None)
    if kesh is None:
        kesh = frappe.local.pokiza_davr_keshi = {}
    kalit = str(getdate(sana or nowdate()))
    if kalit in kesh:
        return kesh[kalit]

    nomi = _davr_nomi(sana)
    if not nomi:
        kesh[kalit] = {}
        return kesh[kalit]
    rows = frappe.get_all(
        "Tannarx Davri Qatori",
        filters={"parent": nomi, "parenttype": "Tannarx Davri"},
        fields=["sku", "norma", "tannarx", "farsh", "upakovka"],
    )
    kesh[kalit] = {
        r.sku: {
            "tannarx": flt(r.tannarx),
            "farsh": flt(r.farsh),
            "upakovka": flt(r.upakovka),
            "norma": r.norma,
            "davr": nomi,
            "manba": nomi,
        }
        for r in rows
    }
    return kesh[kalit]


def davr_keshni_tozala():
    """Davrni o'zgartirgan kod (qayta_hisobla / tasdiqlash) chaqiradi."""
    frappe.local.pokiza_davr_keshi = {}


@frappe.whitelist()
def joriy_tannarx(sku, sana=None, norma=None):
    """Bitta SKU ning normativ tannarxi.

    Davrda yo'q SKU (yangi mahsulot — davr hisoblangandan keyin
    qo'shilgan) jonli hisoblanadi: nol qaytarish sotuvni bloklab
    qo'yishdan yaxshiroq, lekin `manba` buni ko'rsatib turadi.
    """
    karta = davr_map(sana)
    if sku in karta:
        return karta[sku]

    from pokiza.api.kartochka import bundle_normasi, tannarx_hisobla
    try:
        t = tannarx_hisobla(sku, norma or bundle_normasi(sku))
    except Exception:
        t = {"tannarx": 0, "farsh": 0, "upakovka": 0}
    return {
        "tannarx": flt(t.get("tannarx")),
        "farsh": flt(t.get("farsh")),
        "upakovka": flt(t.get("upakovka")),
        "norma": norma or bundle_normasi(sku),
        "davr": None,
        "manba": JONLI,
    }


@frappe.whitelist()
def davr_yarat(davr_boshi=None):
    """Berilgan oyga Tannarx Davri yaratadi va darhol hisoblaydi.

    Mavjud davrga TEGMAYDI — tasdiqlangan davrni tasodifan qayta
    yozib yuborish xavfli, buni faqat formadagi «Qayta hisoblash»
    tugmasi qiladi.
    """
    from frappe.utils import get_first_day

    if not frappe.has_permission("Tannarx Davri", "create"):
        frappe.throw(frappe._("Huquq yo'q"))

    boshi = get_first_day(getdate(davr_boshi or nowdate()))
    nomi = boshi.strftime("%Y-%m")
    if frappe.db.exists("Tannarx Davri", nomi):
        return {"davr": nomi, "yaratildi": False}

    doc = frappe.get_doc({
        "doctype": "Tannarx Davri",
        "davr_boshi": boshi,
        "holat": "Qoralama",
        "izoh": "Avto-yaratilgan",
    })
    doc.insert()
    doc.qayta_hisobla()
    return {"davr": nomi, "yaratildi": True}
