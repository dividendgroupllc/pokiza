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
        # Kartochkadagi qator tartibi saqlanadi (2026-10-31): avval bu
        # yerda alifbo bo'yicha saralanardi, shuning uchun kartochkada
        # tortib qo'yilgan tartib schyotga yetib bormasdi.
        return [
            {
                "item_code": r.sku,
                "item_name": r.sku_nomi or r.sku,
                "qty": 0,
                "rate": r.sotuv_narxi,
                "kartochkadan": 1,
            }
            for r in karta.values()
        ]

    # Tarix so'rovining manbasi bitta bo'lsin: avval shu yerda va
    # kartochka.py'da deyarli bir xil ikki SQL turardi.
    from pokiza.api.kartochka import _mijoz_qatorlari

    # Kartochkasiz mijoz: tartib manbasi yo'q, nom bo'yicha
    return sorted(_mijoz_qatorlari(customer).values(),
                  key=lambda q: (q.item_name or q.item_code).lower())


@frappe.whitelist()
def schyot_qatorlari(customer, company=None, price_list=None, set_warehouse=None,
                     posting_date=None):
    """Mijoz tanlanganda schyot jadvaliga TAYYOR qatorlar — bitta so'rovda.

    Kartochkadagi BARCHA Aktiv qator tushadi (egasi qarori 2026-10-31:
    avvalgi 10 qator chegarasi olib tashlandi) va aynan kartochkadagi
    tartibda — kartochka jadvalida qatorlar tortib tartiblanadi.

    Avval brauzer har SKU uchun `frappe.model.set_value("item_code", ...)`
    qilardi, bu esa ERPNext'ning `get_item_details` server chaqiruvini QATOR
    BOSHIGA bir marta uchirardi — 72 SKU = 72 ketma-ket so'rov, har biriga
    butun hujjat yuk sifatida biriktirilgan. Bu yerda o'sha ma'lumot bir
    necha bulk so'rovda yig'iladi, brauzer esa qatorlarni handler
    uchirmasdan joylaydi (`frm.add_child`).

    Xavfsizlik sharti: pokizada soliq jadvali, Pricing Rule va sales_uom
    yo'q, bitta kompaniya va bitta valyuta (UZS, kurs 1), bitta sotuv
    prays-listi — ya'ni get_item_details'ning universal mantig'i bu yerda
    qo'shimcha hech narsa bermaydi. Natija 72 SKU'da ERPNext bilan
    taqqoslangan: uom, stock_uom, conversion_factor va price_list_rate
    aynan bir xil.

    MAJBURIY MAYDONLAR: Frappe ularni brauzerda, serverga yubormasdan
    oldin tekshiradi — shuning uchun hammasi shu javobda bo'lishi kerak:
    item_name, uom, conversion_factor, rate, amount, base_rate,
    base_amount, income_account, cost_center.
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

    # 2) Item Default — ombor VA hisoblar, kompaniya kesimida
    #
    # HISOBLAR (2026-10-30). `income_account` — `reqd = 1` va defaulti YO'Q,
    # shuning uchun u to'ldirilmasa forma brauzerda «обязательное поле ...
    # счет доходов» deb saqlanmaydi (server tomonida ERPNext uni
    # `set_missing_values`da o'zi to'ldiradi, lekin gap u yergacha
    # yetib bormaydi). `cost_center` ham `reqd = 1`, lekin uning
    # `default = ":Company"` qiymati bor va `frm.add_child` uni o'zi
    # qo'yadi — bloklamaydi; shunga qaramay beramiz, chunki `:Company`
    # har doim kompaniya markazini qo'yadi, ERPNext esa avval
    # `Item Default.selling_cost_center`ga qaraydi — ikki yo'l bir xil
    # natija bersin. Navbat get_item_details.py dagidek; Item Group /
    # Brand darajasi pokizada ishlatilmaydi.
    defaultlar = {
        r.parent: r
        for r in frappe.db.sql(
            """
            SELECT parent, default_warehouse, income_account, selling_cost_center
            FROM `tabItem Default`
            WHERE company = %(company)s AND parent IN %(skular)s
            """,
            {"company": company, "skular": tuple(skular)},
            as_dict=True,
        )
    }
    kompaniya_hisob = frappe.db.get_value(
        "Company", company, ["default_income_account", "cost_center"], as_dict=True
    ) or frappe._dict()

    # 3) Prays-list narxi. Navbat ERPNext'ning `get_price_list_rate_for`
    #    dagidek: avval MIJOZ kesimidagi Item Price, bo'lmasa umumiy.
    #    (Kartochka narxlari mijoz kesimidagi Item Price'ga ko'chiriladi —
    #    qarang pokiza.api.narx.) Har SKU uchun amal qiladigan eng yangi
    #    qator kerak: ORDER BY tufayli birinchi uchragani o'sha.
    praysdan = {}
    for r in frappe.db.sql(
        """
        SELECT item_code, uom, price_list_rate, IFNULL(customer, '') <> '' AS mijozniki
        FROM `tabItem Price`
        WHERE price_list = %(price_list)s AND item_code IN %(skular)s
          AND IFNULL(customer, '') IN ('', %(customer)s)
          AND (valid_from IS NULL OR valid_from <= %(sana)s)
          AND (valid_upto IS NULL OR valid_upto >= %(sana)s)
        ORDER BY mijozniki DESC, valid_from DESC, modified DESC
        """,
        {"price_list": price_list, "skular": tuple(skular),
         "customer": customer, "sana": sana},
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
        d = defaultlar.get(it.name)
        uom = it.sotuv_uom or it.stock_uom
        cf = 1.0 if uom == it.stock_uom else konversiya.get((it.name, uom), 1.0)
        prays = praysdan.get((it.name, uom)) or praysdan.get((it.name, ""), 0.0)
        narx = flt(a.get("rate")) if a.get("kartochkadan") else 0.0
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
            # price_list_rate = rate (2026-10-30). Avval bu yerda UMUMIY
            # prays-list narxi turardi, `rate` esa kartochkadan kelardi —
            # ERPNext ikkisining farqini soxta `discount_amount` (yoki
            # teskarisida `margin_type=Amount`) qilib yozib qo'yardi
            # (8 SKU'dan 7 tasida: prays 44 730 vs kartochka 40 530 ->
            # 4 200 "chegirma"). Mijoz uchun amal qiladigan narx —
            # kartochka narxi, demak uning prays-list narxi ham o'shanikidir
            # (narx.py uni mijoz kesimidagi Item Price'ga ham yozadi).
            "price_list_rate": narx,
            "base_price_list_rate": narx,
            "amount": 0,
            "base_rate": narx,
            "base_amount": 0,
            "warehouse": set_warehouse or (d.default_warehouse if d else None),
            "income_account": (d.income_account if d else None)
            or kompaniya_hisob.get("default_income_account"),
            "cost_center": (d.selling_cost_center if d else None)
            or kompaniya_hisob.get("cost_center"),
            # `is_stock_item` SI Item maydoni EMAS — yubormaymiz.
            "use_serial_batch_fields": 1 if it.has_batch_no else 0,
            "kartochkadan": a.get("kartochkadan") or 0,
        })

    _majburiy_qoriqchi(qatorlar)
    return {"qatorlar": qatorlar, "tel": tel, "jami_mavjud": jami_mavjud}


def _majburiy_qoriqchi(qatorlar):
    """Majburiy maydon bo'sh qolsa Error Log'ga yozadi (formani to'xtatmaydi).

    2026-10-30 da aynan shu jim sindirdi: `income_account` to'ldirilmagan
    edi va forma faqat BRAUZERDA saqlanmasdi — server tomonidagi sinovlar
    o'tib ketardi. Kelgusida SI Item'ga yangi majburiy maydon qo'shilsa,
    shu yerda darhol ko'rinadi.
    """
    if not qatorlar:
        return
    try:
        majburiy = [f.fieldname for f in frappe.get_meta("Sales Invoice Item").fields if f.reqd]
        kam = sorted({f for r in qatorlar for f in majburiy if r.get(f) in (None, "")})
        if kam:
            frappe.log_error(
                "Sales Invoice Item majburiy maydonlari to'ldirilmagan "
                "(forma saqlanmaydi): %s" % ", ".join(kam),
                "pokiza.api.mijoz.schyot_qatorlari",
            )
    except Exception:
        pass
