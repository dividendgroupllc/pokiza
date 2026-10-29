# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Mijoz kartochkasi narxini ERPNext'ning O'Z narx mexanizmiga ko'chirish.

MUAMMO (2026-10-29 da aniqlandi va sinab ko'rildi): kartochkadagi
shartnoma narxi schyot qatoriga faqat BRAUZER orqali qo'yilardi. Sotuvchi
qatorga son kiritganda esa ERPNext'ning `qty` ishlovchisi serverga
`apply_price_list` so'rovini yuboradi, u umumiy prays-list narxini
qaytaradi va `_set_values_for_item_list` uni `rate` ustiga YOZADI:

    П/к. "Burxanov" To'yona — kartochka 35 070 → prays-list 33 400

799 Aktiv kartochka qatoridan 743 tasida kartochka narxi umumiy
prays-listdan farq qiladi, ya'ni deyarli har qator xatarda. Amalda
zarar kam ko'rindi (zakazdan ko'chirilgan qatorlarda ERPNext bu
almashtirishni o'tkazib yuboradi — `is_a_mapped_document`), lekin
QO'LDA kiritilgan schyot — ya'ni tezlashtirgan oqimimiz — to'liq
ochiq edi.

YECHIM: kartochkaning Aktiv qatorlari MIJOZ KESIMIDAGI `Item Price`
yozuvlariga ko'chiriladi. ERPNext `get_price_list_rate_for` da avval
mijoz narxini qidiradi (`get_item_price`, customer bo'yicha), umumiy
narxga esa faqat mijoz narxi topilmasa tushadi. Shundan keyin
kartochka narxi ERPNext uchun ham «o'z» narxi bo'ladi: uni
apply_price_list ham, get_item_details ham, zakaz ham, POS ham
bosib ketmaydi — biz hech narsani «ushlab turishimiz» kerak emas.

QOIDALAR:
  * manba — kartochka, nusxa — Item Price. Teskari yo'nalish YO'Q:
    Item Price qo'lda o'zgartirilsa keyingi sinxronda qaytariladi.
  * faqat Aktiv qatorlar; qator Disabled bo'lsa yoki o'chirilsa
    mijoz narxi ham o'chiriladi (eskirgan shartnoma narxi qolib
    ketmasin).
  * `valid_from` qo'yilmaydi: bu «hozirgi shartnoma narxi», tarixi
    esa Kartochka Ozgarish Jurnalida turadi. Kelasi sanali
    valid_from narxni jim o'chirib qo'yish xavfi bor.
  * narx 0 bo'lsa yozuv yaratilmaydi — 0 bilan sotishni bloklash
    before_submit'da allaqachon bor, uni prays-list bilan
    aylanib o'tib bo'lmasin.
"""

import frappe
from frappe.utils import flt

PRAYS_LIST = "Standard Selling"


def _kartochka_narxlari(mijoz):
    """{(sku, uom): narx} — mijozning Aktiv kartochka qatorlari.

    uom — Item'ning sotuv birligi (pokizada sales_uom hech qayerda
    to'ldirilmagan, demak stock_uom), chunki ERPNext Item Price'ni
    aynan qator uom'i bo'yicha qidiradi.
    """
    rows = frappe.db.sql(
        """
        SELECT q.sku, IFNULL(i.sales_uom, i.stock_uom) AS uom, q.sotuv_narxi
        FROM `tabMijoz Kartochka Qatori` q
        JOIN `tabMijoz Kartochkasi` k ON k.name = q.parent
        JOIN `tabItem` i ON i.name = q.sku
        WHERE k.mijoz = %s AND q.status = 'Aktiv' AND q.sotuv_narxi > 0
        """,
        mijoz,
        as_dict=True,
    )
    return {(r.sku, r.uom): flt(r.sotuv_narxi) for r in rows}


def _mavjud_narxlar(mijoz):
    """{(sku, uom): (name, narx)} — shu mijozga yozilgan Item Price'lar."""
    rows = frappe.db.sql(
        """
        SELECT name, item_code, uom, price_list_rate
        FROM `tabItem Price`
        WHERE price_list = %(prays)s AND customer = %(mijoz)s
        """,
        {"prays": PRAYS_LIST, "mijoz": mijoz},
        as_dict=True,
    )
    return {(r.item_code, r.uom): (r.name, flt(r.price_list_rate)) for r in rows}


def sinxronla(mijoz, valyuta=None):
    """Bitta mijozning kartochka narxlarini Item Price'ga tenglashtiradi.

    Faqat FARQNI yozadi: o'zgarmagan narxga tegmaydi, shuning uchun
    kartochka qayta saqlanganda ortiqcha yozuv va Version shovqini
    bo'lmaydi.
    """
    # Mijoz o'chirilgan/qayta nomlangan bo'lsa (bazada bitta shunday
    # yetim kartochka bor: «YaTT Mingishev Umid Qo'qon») Item Price Link
    # validatsiyasi yiqiladi va kartochkani umuman saqlab bo'lmay qoladi.
    # Narx sinxroni kartochkani bloklashi kerak emas — jim o'tkazamiz.
    if not frappe.db.exists("Customer", mijoz):
        return {"yaratildi": 0, "yangilandi": 0, "ochirildi": 0}

    kerak = _kartochka_narxlari(mijoz)
    bor = _mavjud_narxlar(mijoz)
    valyuta = valyuta or frappe.get_cached_value("Price List", PRAYS_LIST, "currency")

    natija = {"yaratildi": 0, "yangilandi": 0, "ochirildi": 0}

    for kalit, narx in kerak.items():
        sku, uom = kalit
        eski = bor.pop(kalit, None)
        if eski is None:
            frappe.get_doc({
                "doctype": "Item Price",
                "item_code": sku,
                "uom": uom,
                "price_list": PRAYS_LIST,
                "customer": mijoz,
                "selling": 1,
                "currency": valyuta,
                "price_list_rate": narx,
                "note": "Mijoz Kartochkasidan avto (pokiza.api.narx)",
            }).insert(ignore_permissions=True)
            natija["yaratildi"] += 1
        elif flt(eski[1], 2) != flt(narx, 2):
            doc = frappe.get_doc("Item Price", eski[0])
            doc.price_list_rate = narx
            doc.save(ignore_permissions=True)
            natija["yangilandi"] += 1

    # kartochkada qolmagan (Disabled / o'chirilgan / narxi 0 bo'lgan)
    # qatorlarning mijoz narxi ham turmasin
    for nom, _narx in bor.values():
        frappe.delete_doc("Item Price", nom, ignore_permissions=True, force=True)
        natija["ochirildi"] += 1

    return natija


@frappe.whitelist()
def sinxronla_hammasi():
    """Barcha kartochkalar uchun bir martalik (yoki tiklash uchun) sinxron."""
    if not frappe.has_permission("Item Price", "create"):
        frappe.throw(frappe._("Huquq yo'q"))

    valyuta = frappe.get_cached_value("Price List", PRAYS_LIST, "currency")
    jami = {"mijoz": 0, "yaratildi": 0, "yangilandi": 0, "ochirildi": 0, "xatolar": []}

    for mijoz in frappe.get_all("Mijoz Kartochkasi", pluck="mijoz"):
        # har mijoz YAKKA savepoint ichida — bittasi yiqilsa qolgani qoladi
        sp = "narx_%s" % abs(hash(mijoz))
        frappe.db.savepoint(sp)
        try:
            r = sinxronla(mijoz, valyuta)
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            jami["xatolar"].append("%s: %s" % (mijoz, str(e)[:200]))
            continue
        jami["mijoz"] += 1
        for k in ("yaratildi", "yangilandi", "ochirildi"):
            jami[k] += r[k]

    return jami


def kartochka_on_update(doc, method=None):
    """Mijoz Kartochkasi saqlanganda mijoz narxlarini yangilaydi."""
    sinxronla(doc.mijoz)
