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


def _kesh(nom):
    """So'rov (request) doirasidagi kesh.

    Tannarx hisobi bir xil ma'lumotni qayta-qayta so'raydi: 171 SKU'ning
    hammasi 20-30 ta normaga tayanadi, bundle va BOM esa bitta so'rov
    ichida o'zgarmaydi. Kesh frappe.local'da — har HTTP so'rovi / fon
    ishi oxirida o'zi yo'qoladi, ya'ni eskirgan narx qotib qolmaydi.
    """
    kesh = getattr(frappe.local, nom, None)
    if kesh is None:
        kesh = {}
        setattr(frappe.local, nom, kesh)
    return kesh


def _norma_farsh_narxi(norma):
    """1 kg farsh tannarxi: BOM retsepti × HOZIRGI sklad narxlari."""
    if not norma:
        return 0.0
    kesh = _kesh("pokiza_farsh_narx_keshi")
    if norma in kesh:
        return kesh[norma]
    kesh[norma] = _norma_farsh_narxi_hisobla(norma)
    return kesh[norma]


def _norma_farsh_narxi_hisobla(norma):
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
    """Upakovka/syryo itemining 1 birlik narxi.

    MANBA NAVBATI (2026-10-27 tuzatish):
      1. QOLDIQ BOR omborlar bo'yicha og'irlangan o'rtacha:
         Σ stock_value / Σ actual_qty;
      2. qoldiq hech qayerda yo'q bo'lsa — OXIRGI XARID narxi
         (Purchase Invoice: base_net_amount / stock_qty);
      3. Item.valuation_rate;
      4. Standard Buying prays-listi.

    Avval shunchaki «valuation_rate > 0 bo'lgan birinchi Bin» olinardi.
    Ikki muammo bor edi: (a) ERPNext tovar tugaganda ham Bin'da oxirgi
    valuation_rate'ni saqlab qoladi, kod esa qoldiqqa qaramay o'sha
    qotib qolgan narxni olardi (186 xomashyodan 16 tasi shunday — ayrimlari
    2.5 oy oldingi narxda); (b) order_by yo'qligi sabab bir item ikki
    omborda bo'lsa narx tasodifiy tanlanardi. Og'irlangan o'rtacha ikkala
    muammoni ham yopadi va ombor hisobidagi qiymatga mos keladi.
    """
    kesh = getattr(frappe.local, "pokiza_item_narx_keshi", None)
    if kesh is None:
        kesh = frappe.local.pokiza_item_narx_keshi = {}
    if item_code in kesh:
        return kesh[item_code]

    # 1. qoldiq bor omborlar bo'yicha og'irlangan o'rtacha
    narx = frappe.db.sql(
        """
        SELECT SUM(stock_value) / SUM(actual_qty)
        FROM `tabBin`
        WHERE item_code = %s AND actual_qty > 0 AND stock_value > 0
        """,
        item_code,
    )
    narx = flt(narx[0][0]) if narx and narx[0][0] else 0

    # 2. qoldiq yo'q — oxirgi xarid narxi (Bin'dagi qotgan narx emas)
    if not narx:
        oxirgi = frappe.db.sql(
            """
            SELECT pii.base_net_amount / pii.stock_qty
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pii.item_code = %s AND pi.docstatus = 1
              AND IFNULL(pi.is_return, 0) = 0 AND pii.stock_qty > 0
            ORDER BY pi.posting_date DESC, pi.creation DESC
            LIMIT 1
            """,
            item_code,
        )
        narx = flt(oxirgi[0][0]) if oxirgi else 0

    if not narx:
        narx = frappe.db.get_value("Item", item_code, "valuation_rate")
    if not narx:
        narx = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": "Standard Buying"},
            "price_list_rate",
        )
    kesh[item_code] = flt(narx)
    return flt(narx)


def _bundle_qatorlari(sku):
    """SKU bundle'ining BARCHA qatorlari — bitta so'rovda, keshlanadi.

    Avval bundle ikki marta o'qilardi: _upakovka_narxi() ГП bo'lmagan
    qatorlar uchun, bundle_normasi() esa ГП qatori uchun — ikkisi ham
    har SKU'da alohida SQL yuborardi. Endi bitta so'rov ikkisiga ham
    xizmat qiladi (171 SKU'da 342 so'rov → 171).

    DISABLED bundle ham manba: flip'da bundlelar ataylab o'chirilgan,
    tarixiy retsept ma'lumoti o'sha yerda qoladi.
    """
    kesh = _kesh("pokiza_bundle_keshi")
    if sku not in kesh:
        kesh[sku] = frappe.db.sql(
            """
            SELECT pbi.item_code, pbi.qty, i.item_group
            FROM `tabProduct Bundle` pb
            JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
            JOIN `tabItem` i ON i.name = pbi.item_code
            WHERE pb.new_item_code = %s
            """,
            sku,
            as_dict=True,
        )
    return kesh[sku]


def bundle_oldindan(skular):
    """Ko'p SKU bundle qatorlarini BITTA so'rovda keshga yig'adi."""
    kesh = _kesh("pokiza_bundle_keshi")
    yetishmagan = [s for s in skular if s and s not in kesh]
    if not yetishmagan:
        return kesh

    for r in frappe.db.sql(
        """
        SELECT pb.new_item_code AS sku, pbi.item_code, pbi.qty, i.item_group
        FROM `tabProduct Bundle` pb
        JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
        JOIN `tabItem` i ON i.name = pbi.item_code
        WHERE pb.new_item_code IN %(skular)s
        """,
        {"skular": tuple(yetishmagan)},
        as_dict=True,
    ):
        kesh.setdefault(r.sku, []).append(r)

    for s in yetishmagan:
        kesh.setdefault(s, [])
    return kesh


def _upakovka_narxi(sku):
    """SKU bundle'idagi ГП bo'lmagan qatorlar — 1 kg uchun upakovka narxi."""
    jami = 0.0
    for q in _bundle_qatorlari(sku):
        if q.item_group == NORMA_GURUH:
            continue
        jami += flt(q.qty) * _item_narxi(q.item_code)
    return jami


def bundle_normasi(sku):
    """SKU bundle'idagi norma (ГП) — default norma sifatida.

    Bitta bo'lsa (143 tadan 137 tasi shunday) o'shani qaytaradi,
    aksiya-to'plamlarda (2-3 norma) None: normani odam tanlaydi.
    """
    kesh = _kesh("pokiza_bundle_norma_keshi")
    if sku in kesh:
        return kesh[sku]

    normalar = {q.item_code for q in _bundle_qatorlari(sku)
                if q.item_group == NORMA_GURUH}
    if len(normalar) == 1:
        kesh[sku] = normalar.pop()
    else:
        # bundle'siz (yangi) mahsulot: SKU BOM'idagi yagona ГП qatori
        from pokiza.api.partiya import bom_yagona_gp
        kesh[sku] = bom_yagona_gp(sku)
    return kesh[sku]


@frappe.whitelist()
def tannarx_hisobla(sku, norma=None):
    """1 kg tannarx.

    ASOSIY MANBA (egasi 2026-10-02): SKU'ning O'Z BOM'i — har qatori
    hozirgi sklad narxida: ГП (farsh) qatori o'z retsepti (BOM'i) orqali,
    qolganlari to'g'ridan-to'g'ri. SKU BOM'i bo'lmasa — eski usul:
    norma BOM (farsh) + bundle (upakovka)."""
    if not frappe.has_permission("Item", "read"):
        frappe.throw(_("Huquq yo'q"))

    from pokiza.api.partiya import sku_bom
    b = sku_bom(sku) if sku else None
    if b:
        q = flt(b.quantity) or 1.0
        farsh = upakovka = 0.0
        for r in frappe.db.sql(
            """
            SELECT bi.item_code, SUM(bi.qty) qty, i.item_group
            FROM `tabBOM Item` bi JOIN `tabItem` i ON i.name = bi.item_code
            WHERE bi.parent = %s GROUP BY bi.item_code
            """,
            b.name, as_dict=True,
        ):
            if r.item_group == NORMA_GURUH:
                narx = _norma_farsh_narxi(r.item_code) or _item_narxi(r.item_code)
                farsh += flt(r.qty) / q * narx
            else:
                upakovka += flt(r.qty) / q * _item_narxi(r.item_code)
        return {
            "tannarx": farsh + upakovka,
            "farsh": farsh,
            "upakovka": upakovka,
            "izoh": "SKU BOM: farsh %s, upakovka %s" % (
                fmt_money(farsh, 0), fmt_money(upakovka, 0)),
        }

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
    kesh = _kesh("pokiza_aktiv_karta_keshi")
    if mijoz in kesh:
        return kesh[mijoz]

    # ORDER BY q.idx — kartochkadagi QATOR TARTIBI (2026-10-31, egasi qarori).
    # Kartochka jadvalida qatorlarni sichqoncha bilan tortib tartiblash
    # mumkin; o'sha tartib накладная ketma-ketligi hisoblanadi va shu
    # yerdan Sales Order, Sales Invoice va PDF ga tarqaladi. Avval bu
    # ro'yxat chaqiruvchi tomonda ALIFBO bo'yicha saralanardi — shuning
    # uchun kartochkadagi tartib hech qayerda ko'rinmasdi.
    # Natija dict'i ham shu tartibni saqlaydi (Python dict insertion order).
    rows = frappe.db.sql(
        """
        SELECT q.sku, q.sku_nomi, q.norma, q.tannarx, q.sotuv_narxi,
               q.bonus_foiz, k.bonus_foiz AS umumiy_bonus
        FROM `tabMijoz Kartochka Qatori` q
        JOIN `tabMijoz Kartochkasi` k ON k.name = q.parent
        WHERE k.mijoz = %s AND q.status = 'Aktiv'
        ORDER BY q.idx
        """,
        mijoz,
        as_dict=True,
    )
    kesh[mijoz] = {r.sku: r for r in rows}
    return kesh[mijoz]


def norma_map(mijoz):
    """{sku: norma} — mijoz kartochkasining Aktiv, normasi kiritilgan
    qatorlari. Ishlab chiqarish rejasi shu normaga yoziladi (Faza 2)."""
    return {s: r.norma for s, r in aktiv_map(mijoz).items() if r.norma}


@frappe.whitelist()
def aktiv_itemlar(mijoz):
    """Zakaz/schyot formalari uchun: mijozning Aktiv kartochka SKU'lari.

    Huquq bo'lmasa XATO BERMAYDI (2026-10-08): bu forma qulayligi, har
    mijoz tanlanganda chaqiriladi — huquqsiz foydalanuvchiga «Huquq yo'q»
    oynasini qayta-qayta ko'rsatish o'rniga bo'sh ro'yxat qaytariladi
    (narxlar qo'lda kiritiladi).
    """
    if not frappe.has_permission("Mijoz Kartochkasi", "read"):
        return []
    # Saralamaymiz: kartochkadagi qator tartibi aynan saqlanadi
    return list(aktiv_map(mijoz).values())


def _tarix_qatorlari(mijozlar):
    """{mijoz: {sku: oxirgi narx qatori}} — BARCHA mijoz uchun bitta so'rov.

    Avval har mijozga alohida so'rov yuborilardi (58 mijoz = 58 so'rov,
    har biri `tabSales Invoice` × `Item` join'i bilan). SQL o'zi
    guruhlashi arzonroq: bitta indeksli skan, dedupe Python'da.
    """
    if not mijozlar:
        return {}

    tarix = frappe.db.sql(
        """
        SELECT si.customer, sii.item_code, sii.item_name, sii.qty, sii.rate,
               si.posting_date
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        JOIN `tabItem` it ON it.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.customer IN %(mijozlar)s
          AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(kunlar)s DAY)
          AND it.item_group = %(guruh)s AND it.disabled = 0
          AND sii.qty > 0
        ORDER BY si.posting_date DESC, si.creation DESC
        """,
        {"mijozlar": tuple(mijozlar), "kunlar": KUNLAR, "guruh": SOTUV_GURUH},
        as_dict=True,
    )

    natija = {}
    for t in tarix:
        # ORDER BY tufayli birinchi uchragani eng oxirgi xaridi
        natija.setdefault(t.customer, {}).setdefault(t.item_code, t)
    return natija


def _mijoz_qatorlari(mijoz):
    """Bitta mijozning 90 kunlik tarixi (har SKU oxirgi narxi).

    `customer` ustuni faqat bulk so'rovni guruhlash uchun kerak —
    bitta mijoz kesimida uni qaytarmaymiz, chunki natija to'g'ridan-
    to'g'ri schyot formasiga (odatiy_itemlar) ketadi.
    """
    return {
        sku: frappe._dict({k: v for k, v in q.items() if k != "customer"})
        for sku, q in _tarix_qatorlari([mijoz]).get(mijoz, {}).items()
    }


@frappe.whitelist()
def qoralama_toldir(mijoz=None):
    """Kartochkalarni sotuv tarixidan qoralama qilib to'ldiradi.

    mijoz berilsa — faqat o'sha mijozga (mavjud kartochkaga yetishmagan
    SKU qatorlarini qo'shadi), berilmasa — 90 kunda xarid qilgan barcha
    mijozlarga kartochkasi yo'q bo'lsa yaratadi.

    TEZLIK (2026-10-29): avval har mijoz uchun alohida sotuv tarixi
    so'rovi + Customer bonusi + mavjud kartochka tekshiruvi ketardi va
    har SKU uchun bundle normasi qayta so'ralardi — 58 mijozda mingdan
    oshiq so'rov. Endi uch bulk so'rov tsikl boshida bir marta
    bajariladi, bundle normalar ham oldindan keshga yig'iladi.

    BARDOSHLILIK: bitta mijozning kartochkasi saqlanmasa (masalan
    ichidagi SKU boshqa guruhga ko'chirilgan bo'lsa) butun jarayon
    to'xtab qolmaydi — o'sha mijoz `xatolar`ga yoziladi, qolganlari
    to'ldiriladi.
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

    natija = {"yaratildi": 0, "qator_qoshildi": 0, "otkazildi": 0,
              "normasiz": [], "xatolar": []}
    if not mijozlar:
        return natija

    # --- uchta bulk so'rov: tarix, bonuslar, mavjud kartochkalar
    tarixlar = _tarix_qatorlari(mijozlar)
    if not tarixlar:
        natija["otkazildi"] = len(mijozlar)
        return natija

    bonuslar = dict(frappe.db.sql(
        """
        SELECT name, IFNULL(custom_bonus_foiz, 0) FROM `tabCustomer`
        WHERE name IN %(mijozlar)s
        """,
        {"mijozlar": tuple(mijozlar)},
    ))
    mavjudlar = dict(frappe.db.sql(
        """
        SELECT mijoz, name FROM `tabMijoz Kartochkasi` WHERE mijoz IN %(mijozlar)s
        """,
        {"mijozlar": tuple(mijozlar)},
    ))

    # tsiklda bundle normasi so'ralmasin — barcha SKU bir marta keshga
    bundle_oldindan({sku for t in tarixlar.values() for sku in t})

    for m in mijozlar:
        tarix = tarixlar.get(m)
        if not tarix:
            natija["otkazildi"] += 1
            continue

        bonus = flt(bonuslar.get(m))
        mavjud_nom = mavjudlar.get(m)

        if mavjud_nom:
            doc = frappe.get_doc("Mijoz Kartochkasi", mavjud_nom)
            bor_skular = {q.sku for q in doc.qatorlar}
            if not flt(doc.bonus_foiz) and bonus:
                doc.bonus_foiz = bonus
        else:
            doc = frappe.get_doc({
                "doctype": "Mijoz Kartochkasi",
                "mijoz": m,
                "holat": "Qoralama",
                "bonus_foiz": bonus,
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

        # SAVEPOINT: xato bo'lgan mijozni YAKKA o'zini qaytaradi.
        # Oddiy frappe.db.rollback() butun tranzaksiyani — ya'ni shu
        # tsiklda allaqachon muvaffaqiyatli saqlangan kartochkalarni ham —
        # bekor qilib yuborardi.
        sp = "qoralama_%d" % id(doc)
        frappe.db.savepoint(sp)
        try:
            doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            natija["xatolar"].append("%s: %s" % (m, str(e)[:200]))
            continue

        if mavjud_nom:
            natija["qator_qoshildi"] += qoshildi
        else:
            natija["yaratildi"] += 1

    return natija
