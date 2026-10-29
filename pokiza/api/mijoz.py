"""Mijozning odatiy (doim sotib oladigan) itemlari.

Schyotda mijoz tanlanganda items jadvaliga default tushadigan ro'yxat:
so'nggi 90 kundagi tasdiqlangan schyotlardan (2026-09-05, egasi talabi).
Client tomonda soni 0 bilan tushadi, narxni ERPNext o'zi oladi — bu yerdagi
qty/rate faqat ma'lumot uchun (2026-09-07).
"""

import frappe
from frappe.utils import flt

KUNLAR = 90
NARX_GURUHI = "Сотув махсулотлари"

# Schyotga oldindan tushadigan qator chegarasi (egasi qarori 2026-10-29).
# «ЧП Хаёт»da 72 Aktiv SKU bor, sotuvchi esa odatda 5-10 tasini sotadi.
# 72 qator jadvalni og'irlashtiradi va har son tahririda ERPNext butun
# hujjatni serverga yuboradi (~58 KB) — shuning uchun eng ko'p sotiladigan
# CHEK tasi tushadi, qolganini sotuvchi «Add Row» bilan qo'shadi
# (qo'lda qo'shilgan qatorga narx mijoz kesimidagi Item Price'dan keladi,
# ya'ni baribir kartochka narxi — qarang pokiza.api.narx).
CHEK = 10


@frappe.whitelist()
def odatiy_itemlar(customer):
    """Schyotga default tushadigan itemlar.

    Mijozning kartochkasi bo'lsa (2026-09-22) — undagi AKTIV qatorlar
    kartochka narxi bilan (Disabled qatorlar tushmaydi); kartochkasiz
    mijozga eski usul: so'nggi KUNLAR tarixidan oxirgi soni/narxi.
    """
    if not customer or not frappe.has_permission("Sales Invoice", "read"):
        return []

    from pokiza.api.kartochka import aktiv_map

    karta = aktiv_map(customer)
    if karta:
        return sorted(
            (
                {
                    "item_code": r.sku,
                    "item_name": r.sku_nomi or r.sku,
                    "qty": 0,
                    "rate": r.sotuv_narxi,
                    "kartochkadan": 1,
                }
                for r in karta.values()
            ),
            key=lambda q: (q["item_name"] or "").lower(),
        )

    # Tarix so'rovi kartochka moduli bilan BIR XIL bo'lsin (2026-10-29):
    # avval shu yerda va kartochka.py'da deyarli bir xil ikki SQL turardi
    # — biri tuzatilsa ikkinchisi eskirib qolardi. Endi manba bitta.
    from pokiza.api.kartochka import _mijoz_qatorlari

    oxirgi = _mijoz_qatorlari(customer)
    return sorted(oxirgi.values(), key=lambda q: (q.item_name or q.item_code).lower())


def _eng_kop_sotiladigan(customer, asos, chek):
    """Ro'yxatni mijozning HAQIQIY xaridiga qarab tartiblab, `chek` tasini oladi.

    Tartib: shu mijoz so'nggi KUNLAR ichida necha MARTA olgani (eng
    ishonchli belgi — doimiy assortiment), keyin oxirgi xarid sanasi,
    keyin og'irligi. Tarixda uchramagan SKU'lar oxirida, alifbo bo'yicha.
    """
    if len(asos) <= chek:
        return asos

    tarix = {
        r.item_code: r
        for r in frappe.db.sql(
            """
            SELECT sii.item_code, COUNT(*) AS marta,
                   MAX(si.posting_date) AS oxirgi, SUM(sii.stock_qty) AS kg
            FROM `tabSales Invoice` si
            JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.customer = %(customer)s
              AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(kunlar)s DAY)
              AND sii.qty > 0
            GROUP BY sii.item_code
            """,
            {"customer": customer, "kunlar": KUNLAR},
            as_dict=True,
        )
    }

    bugun = frappe.utils.getdate()

    def kalit(q):
        """Kichik kalit = oldinda. Tarixsiz SKU oxirida, alifbo bo'yicha."""
        t = tarix.get(q["item_code"])
        nom = (q.get("item_name") or q["item_code"]).lower()
        if not t:
            return (1, 0, 0, 0.0, nom)
        kun_oldin = (bugun - frappe.utils.getdate(t.oxirgi)).days if t.oxirgi else 10 ** 6
        return (0, -int(t.marta), kun_oldin, -flt(t.kg), nom)

    return sorted(asos, key=kalit)[:chek]


@frappe.whitelist()
def schyot_qatorlari(customer, company=None, price_list=None, set_warehouse=None,
                     posting_date=None):
    """Mijoz tanlanganda schyot jadvaliga TAYYOR qatorlar — BITTA so'rovda.

    NIMA UCHUN KERAK (2026-10-29, sotuvchi shikoyati: «schyot uzoq yuklanadi»):
    avval brauzer har SKU uchun alohida `frappe.model.set_value("item_code")`
    qilardi, bu esa ERPNext'ning `get_item_details` server chaqiruvini
    QATOR BOSHIGA bir marta ishga tushirardi — va har chaqiruvga butun
    schyot hujjati yuk sifatida biriktirilardi. «ЧП Хаёт» kartochkasida
    72 Aktiv SKU bor: 72 ketma-ket HTTP so'rov (faqat server tomonidagi
    SQL 1 498 so'rov / 1.8 s), har biri o'sib borayotgan hujjat bilan —
    ya'ni traffik qatorlar soniga KVADRAT bog'liq. Natijada sotuvchi
    mijozni tanlagandan keyin o'n sekundlarcha kutib turardi.

    Bu yerda o'sha ma'lumot 5 ta bulk so'rovda yig'iladi va brauzer
    qatorlarni handler ishga tushirmasdan (frm.add_child) joylaydi.

    NIMA UCHUN XAVFSIZ: pokizada soliq jadvali yo'q (0 qator), Pricing
    Rule yo'q, bitta kompaniya, bitta valyuta (UZS, kurs 1), bitta sotuv
    prays-listi (Standard Selling), hech bir sotuv SKU'sida sales_uom
    va partiya (has_batch_no) yo'q. Ya'ni get_item_details ning
    universal mashinasi bu yerda faqat bo'sh ish qiladi. Hisob
    (income_account, cost_center va h.k.) baribir SAQLASHDA ERPNext'ning
    o'zi `set_missing_values` bilan to'ldiradi — biz uni oldinga
    ko'chirmaymiz, shunchaki ekranga chiqarish uchun kerakli maydonlarni
    beramiz.
    """
    if not customer or not frappe.has_permission("Sales Invoice", "create"):
        return {"qatorlar": [], "tel": None}

    # Mijoz telefoni ham SHU javobda ketadi (2026-10-29): avval brauzer
    # mijoz tanlanganda alohida `frappe.db.get_value("Customer", ...)`
    # so'rovi yuborardi. Bitta maydon uchun alohida tarmoq borib-kelishi
    # — mijoz tanlashdagi kechikishning yana bir bo'lagi.
    tel = frappe.db.get_value(
        "Customer", customer, ["contact_number", "mobile_no"], as_dict=True) or {}
    tel = tel.get("contact_number") or tel.get("mobile_no")

    asos = odatiy_itemlar(customer)
    if not asos:
        return {"qatorlar": [], "tel": tel}

    jami_mavjud = len(asos)
    asos = _eng_kop_sotiladigan(customer, asos, CHEK)

    skular = [r["item_code"] for r in asos]
    company = company or frappe.defaults.get_user_default("Company")
    price_list = price_list or frappe.db.get_single_value(
        "Selling Settings", "selling_price_list") or "Standard Selling"
    sana = posting_date or frappe.utils.nowdate()

    # 1) Item ustunlari
    itemlar = {
        r.name: r
        for r in frappe.db.sql(
            """
            SELECT name, item_name, description, stock_uom, item_group,
                   is_stock_item, has_batch_no, IFNULL(sales_uom, stock_uom) AS sotuv_uom
            FROM `tabItem` WHERE name IN %(skular)s
            """,
            {"skular": tuple(skular)},
            as_dict=True,
        )
    }

    # 2) Item Default (ombor) — kompaniya kesimida
    omborlar = dict(frappe.db.sql(
        """
        SELECT parent, default_warehouse FROM `tabItem Default`
        WHERE company = %(company)s AND parent IN %(skular)s
          AND IFNULL(default_warehouse, '') <> ''
        """,
        {"company": company, "skular": tuple(skular)},
    ))

    # 3) Prays-list narxi — kartochkasiz mijozga (kartochkalisiga narx
    #    kartochkadan keladi). Har SKU uchun amal qiladigan ENG YANGI
    #    qator: ORDER BY tufayli birinchi uchragani kerakligi.
    praysdan = {}
    for r in frappe.db.sql(
        """
        SELECT item_code, uom, price_list_rate
        FROM `tabItem Price`
        WHERE price_list = %(price_list)s AND item_code IN %(skular)s
          AND IFNULL(customer, '') = ''
          AND (valid_from IS NULL OR valid_from <= %(sana)s)
          AND (valid_upto IS NULL OR valid_upto >= %(sana)s)
        ORDER BY valid_from DESC, modified DESC
        """,
        {"price_list": price_list, "skular": tuple(skular), "sana": sana},
        as_dict=True,
    ):
        praysdan.setdefault((r.item_code, r.uom or ""), flt(r.price_list_rate))

    # 4) UOM konversiyasi — sotuv birligi stock birligidan farq qilsa
    konversiya = {}
    for r in frappe.db.sql(
        """
        SELECT parent, uom, conversion_factor FROM `tabUOM Conversion Detail`
        WHERE parent IN %(skular)s
        """,
        {"skular": tuple(skular)},
        as_dict=True,
    ):
        konversiya[(r.parent, r.uom)] = flt(r.conversion_factor) or 1.0

    qatorlar = []
    for a in asos:
        it = itemlar.get(a["item_code"])
        if not it:
            continue
        uom = it.sotuv_uom or it.stock_uom
        cf = 1.0 if uom == it.stock_uom else konversiya.get((it.name, uom), 1.0)
        narx = flt(a.get("rate")) if a.get("kartochkadan") else 0.0
        prays = praysdan.get((it.name, uom)) or praysdan.get((it.name, ""), 0.0)
        if not narx:
            narx = prays

        qatorlar.append({
            "item_code": it.name,
            "item_name": it.item_name or it.name,
            "description": it.description or it.item_name or it.name,
            "item_group": it.item_group,
            "uom": uom,
            "stock_uom": it.stock_uom,
            "conversion_factor": cf,
            "qty": 0,
            "stock_qty": 0,
            "rate": narx,
            "price_list_rate": prays,
            "amount": 0,
            "base_rate": narx,
            "base_amount": 0,
            "warehouse": set_warehouse or omborlar.get(it.name),
            # `is_stock_item` SI Item maydoni EMAS — yubormaymiz.
            "use_serial_batch_fields": 1 if it.has_batch_no else 0,
            "kartochkadan": a.get("kartochkadan") or 0,
        })

    return {"qatorlar": qatorlar, "tel": tel, "jami_mavjud": jami_mavjud}
