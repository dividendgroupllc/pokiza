"""SODDA REJIMGA O'TISH — Maintain Stock flip, PARTIYASIZ (2026-10-02).

Egasi tasdiqlagan model: Maintain Stock + SKU BOM + mijoz kartasi +
tannarx. Partiya/norma qatlami YOQILMAYDI (has_batch_no=0 qoladi).

ERPNext `Item.cant_change` Maintain Stock'ni tasdiqlangan SO/Bundle/BOM
borligi uchun bloklaydi — lekin asl himoya predmeti SLE (ombor harakati),
u bu itemlarda NOL. Shuning uchun flip `db_set` bilan nazoratli chetlab
o'tiladi; HECH QANDAY eski hujjat cancel qilinmaydi.

Har SKU uchun shartlar: guruh sotuv, disabled emas, SLE=0, stock_uom kg.
Flip: bundle disable → is_stock_item=1 → default sklad = ГП → reserved
qayta hisob. Norma/retsept topilmasa flip BARIBIR bo'ladi (sotuvga
to'siq emas), faqat ogohlantiriladi (ishlab chiqarish uchun BOM kerak).
"""

import frappe
from frappe import _
from frappe.utils import flt

from pokiza.api.partiya import (
    NORMA_GURUH, SOTUV_GURUH, asosiy_ombor, bom_yagona_gp, sku_bom,
)

KG_UOMS = ("кг", "Kg", "kg", "KG", "Кг")


def _sku_audit(sku):
    a = {"sku": sku, "tayyor": True, "sabablar": [], "ogohlar": []}
    it = frappe.db.get_value(
        "Item", sku,
        ["item_group", "disabled", "is_stock_item", "has_batch_no", "stock_uom"],
        as_dict=True,
    )
    if not it:
        a["tayyor"] = False
        a["sabablar"].append("item topilmadi")
        return a
    if it.item_group != SOTUV_GURUH:
        a["tayyor"] = False
        a["sabablar"].append("guruh noto'g'ri")
    if it.disabled:
        a["tayyor"] = False
        a["sabablar"].append("item disabled")
    if it.is_stock_item:
        a["allaqachon"] = True
        a["tayyor"] = False
        a["sabablar"].append("allaqachon stock item")
        if it.has_batch_no:
            a["ogohlar"].append("DIQQAT: has_batch_no=1 — sodda rejimda bo'lmasligi kerak")
        return a

    sle = frappe.db.count("Stock Ledger Entry", {"item_code": sku, "is_cancelled": 0})
    if sle:
        a["tayyor"] = False
        a["sabablar"].append("SLE bor (%d) — flip TAQIQLANADI" % sle)

    if it.stock_uom not in KG_UOMS:
        a["tayyor"] = False
        a["sabablar"].append("stock_uom='%s' — kg emas, alohida qaror" % it.stock_uom)

    # retsept manbai (faqat ogohlantirish — sotuvga to'siq emas)
    if not sku_bom(sku):
        bundle_gp = frappe.db.sql(
            """
            SELECT COUNT(DISTINCT pbi.item_code)
            FROM `tabProduct Bundle` pb
            JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
            JOIN `tabItem` i ON i.name = pbi.item_code
            WHERE pb.new_item_code = %s AND i.item_group = %s
            """,
            (sku, NORMA_GURUH),
        )[0][0]
        if not bundle_gp:
            a["ogohlar"].append("BOM ham, bundle normasi ham yo'q — ishlab chiqarib bo'lmaydi, BOM to'ldirilsin")
        else:
            a["ogohlar"].append("SKU BOM hali yo'q — retsept bundle'dan olinadi, BOM to'ldirilsin")
    return a


def _default_ombor_qoy(sku):
    """Item default sklad = ГП (sotuv/zakaz qatorlariga avto tushadi)."""
    wh = asosiy_ombor()
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    it = frappe.get_doc("Item", sku)
    qator = next((d for d in it.item_defaults if d.company == company), None)
    if qator:
        if qator.default_warehouse == wh:
            return
        qator.default_warehouse = wh
    else:
        it.append("item_defaults", {"company": company, "default_warehouse": wh})
    it.flags.ignore_permissions = True
    it.save()


def _flip(sku):
    for pb in frappe.get_all("Product Bundle",
                             filters={"new_item_code": sku, "disabled": 0},
                             pluck="name"):
        frappe.db.set_value("Product Bundle", pb, "disabled", 1)

    # cant_change ATAYIN chetlab o'tiladi — SLE=0 auditda tekshirilgan
    frappe.db.set_value("Item", sku, {
        "is_stock_item": 1,
        "has_batch_no": 0,
        "is_sales_item": 1,
    }, update_modified=True)
    frappe.clear_cache(doctype="Item")

    _default_ombor_qoy(sku)

    try:
        from erpnext.stock.stock_balance import get_reserved_qty, update_bin_qty
        wh = asosiy_ombor()
        update_bin_qty(sku, wh, {"reserved_qty": get_reserved_qty(sku, wh)})
    except Exception:
        frappe.log_error(title="otish: reserved_qty", message=frappe.get_traceback())


@frappe.whitelist()
def ommaviy_audit():
    """Quruq tekshiruv — hech narsa yozmaydi."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    natija = {"tayyor": [], "otkazilmaydi": [], "allaqachon": []}
    for sku in frappe.get_all("Item", filters={"item_group": SOTUV_GURUH},
                              order_by="name", pluck="name"):
        a = _sku_audit(sku)
        if a.get("allaqachon"):
            natija["allaqachon"].append({"sku": sku, "ogohlar": a["ogohlar"]})
        elif a["tayyor"]:
            natija["tayyor"].append({"sku": sku, "ogohlar": a["ogohlar"]})
        else:
            natija["otkazilmaydi"].append({"sku": sku, "sabablar": a["sabablar"]})
    natija["jami"] = {k: len(v) for k, v in natija.items() if isinstance(v, list)}
    return natija


@frappe.whitelist()
def ommaviy_otkaz(tasdiq=None):
    """Auditdan TAYYOR chiqqanlarni flip qiladi (har biri savepoint'da).
    tasdiq='OTKAZ' shart."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    if tasdiq != "OTKAZ":
        frappe.throw(_("tasdiq='OTKAZ' yuboring"))

    natija = {"otkazildi": [], "xato": [], "otkazilmaydi": 0, "allaqachon": 0}
    for sku in frappe.get_all("Item", filters={"item_group": SOTUV_GURUH},
                              order_by="name", pluck="name"):
        a = _sku_audit(sku)
        if a.get("allaqachon"):
            natija["allaqachon"] += 1
            continue
        if not a["tayyor"]:
            natija["otkazilmaydi"] += 1
            continue
        try:
            frappe.db.savepoint("flip_sku")
            _flip(sku)
            natija["otkazildi"].append(sku)
        except Exception:
            frappe.db.rollback(save_point="flip_sku")
            natija["xato"].append({"sku": sku, "xato": frappe.get_traceback()[-250:]})
    frappe.clear_cache(doctype="Item")
    natija["jami"] = {"otkazildi": len(natija["otkazildi"]),
                      "xato": len(natija["xato"]),
                      "otkazilmaydi": natija["otkazilmaydi"],
                      "allaqachon": natija["allaqachon"]}
    return natija


@frappe.whitelist()
def lokal_batch_tozalash(tasdiq=None):
    """FAQAT SINOV SAYTI uchun: avvalgi partiya-sinovlari izini tozalaydi —
    partiyaga tegishli SI/SE'lar bekor qilinadi, partiyalar o'chiriladi,
    has_batch_no=0 qilinadi. Jonlida ishlatilmaydi (u yerda partiya yo'q).
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    if tasdiq != "TOZALA":
        frappe.throw(_("tasdiq='TOZALA' yuboring"))

    natija = {"si_bekor": [], "se_bekor": [], "batch_ochirildi": 0,
              "has_batch_oчирildi": 0, "xato": []}

    # 1) partiyali SLE'ga ega hujjatlar — avval SI, keyin SE bekor
    hujjatlar = frappe.db.sql(
        """
        SELECT DISTINCT sle.voucher_type, sle.voucher_no
        FROM `tabStock Ledger Entry` sle
        JOIN `tabItem` i ON i.name = sle.item_code
        WHERE i.item_group = %s AND sle.is_cancelled = 0
        """,
        SOTUV_GURUH, as_dict=True,
    )
    for turi in ("Sales Invoice", "Stock Entry"):
        for h in [x for x in hujjatlar if x.voucher_type == turi]:
            try:
                d = frappe.get_doc(turi, h.voucher_no)
                if d.docstatus == 1:
                    # PE'ga bog'langan SE bo'lsa PE orqali bekor qilinadi
                    if turi == "Stock Entry" and d.get("custom_production_entry"):
                        pe = frappe.get_doc("Production Entry",
                                            d.custom_production_entry)
                        pe.cancel()
                    else:
                        d.cancel()
                    natija["se_bekor" if turi == "Stock Entry" else "si_bekor"]\
                        .append(h.voucher_no)
            except Exception:
                natija["xato"].append({"hujjat": h.voucher_no,
                                       "xato": frappe.get_traceback()[-200:]})

    # 2) partiyalarni o'chirish
    for b in frappe.get_all("Batch", pluck="name"):
        try:
            frappe.delete_doc("Batch", b, ignore_permissions=True, force=True)
            natija["batch_ochirildi"] += 1
        except Exception:
            natija["xato"].append({"hujjat": b,
                                   "xato": frappe.get_traceback()[-200:]})

    # 3) has_batch_no=0 (SLE'lar endi bekor — xavfsiz)
    skular = frappe.get_all("Item", filters={
        "item_group": SOTUV_GURUH, "has_batch_no": 1}, pluck="name")
    for sku in skular:
        frappe.db.set_value("Item", sku, {"has_batch_no": 0},
                            update_modified=False)
    natija["has_batch_oчирildi"] = len(skular)
    frappe.clear_cache(doctype="Item")
    return natija


@frappe.whitelist()
def bom_yarat_bundledan(tasdiq=None):
    """BOM'i YO'Q sotuv mahsulotlariga Product Bundle tarkibidan BOM
    yaratadi (egasi 2026-10-03: «BOM'ga qancha mahsulot ketishini
    bundle'dan olib to'g'irlaymiz»).

    Qoidalar:
      - qo'lda yaratilgan BOM bor SKU'larga TEGILMAYDI (istalgan submitted
        BOM bo'lsa — o'tkazib yuboriladi);
      - bundle qatorlari AYNAN ko'chiriladi (norma ГП + upakovka + syryo),
        disabled bundle ham manba (flip'da ataylab o'chirilgan edi);
      - BOM: 1 kg uchun, aktiv, default, narxlar Valuation Rate'dan;
      - faqat stock (flip bo'lgan) itemlarga; шт'larga keyin.
    tasdiq='YARAT' shart. Avval quruq ko'rish uchun tasdiq bermasdan
    chaqiring — nimalar yaratilishini sanab beradi.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    quruq = tasdiq != "YARAT"

    natija = {"yaratiladi": [], "bom_bor": 0, "bundlesiz": [],
              "xato": [], "quruq": quruq}
    for sku in frappe.get_all("Item", filters={
        "item_group": SOTUV_GURUH, "disabled": 0, "is_stock_item": 1,
    }, order_by="name", pluck="name"):
        if sku_bom(sku):
            natija["bom_bor"] += 1
            continue
        qatorlar = frappe.db.sql(
            """
            SELECT pbi.item_code, SUM(pbi.qty) qty
            FROM `tabProduct Bundle` pb
            JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
            WHERE pb.new_item_code = %s
            GROUP BY pbi.item_code
            """,
            sku, as_dict=True,
        )
        if not qatorlar:
            natija["bundlesiz"].append(sku)
            continue
        natija["yaratiladi"].append(
            {"sku": sku, "qatorlar": len(qatorlar)})
        if quruq:
            continue
        try:
            frappe.db.savepoint("bom_sku")
            bom = frappe.get_doc({
                "doctype": "BOM",
                "item": sku,
                "quantity": 1,
                "is_active": 1,
                "is_default": 1,
                "rm_cost_as_per": "Valuation Rate",
                "company": frappe.db.get_single_value(
                    "Global Defaults", "default_company"),
                "items": [
                    {"item_code": q.item_code, "qty": flt(q.qty)}
                    for q in qatorlar if flt(q.qty) > 0
                ],
            })
            bom.flags.ignore_permissions = True
            bom.insert()
            bom.submit()
        except Exception:
            frappe.db.rollback(save_point="bom_sku")
            natija["xato"].append({"sku": sku,
                                   "xato": frappe.get_traceback()[-250:]})
            natija["yaratiladi"].pop()
    natija["jami"] = {"yaratiladi": len(natija["yaratiladi"]),
                      "bom_bor": natija["bom_bor"],
                      "bundlesiz": len(natija["bundlesiz"]),
                      "xato": len(natija["xato"])}
    return natija


@frappe.whitelist()
def default_ombor_backfill():
    """Barcha stock sotuv itemlarga default sklad = ГП."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    n = 0
    for sku in frappe.get_all("Item", filters={
        "item_group": SOTUV_GURUH, "is_stock_item": 1}, pluck="name"):
        _default_ombor_qoy(sku)
        n += 1
    return {"yangilandi": n}


@frappe.whitelist()
def eski_bom_almashtir(tasdiq=None):
    """Eski QO'LDA yasalgan xomashyo-BOM'larni bundle'dan yangilash.

    Muammo (egasi 2026-10-03): ba'zi sotuv SKU'larda (asosan «Ак.»
    to'plamlar) eskidan to'liq xomashyo retsepti yozilgan BOM bor —
    ichida farsh (ГП) ham, upakovka ham yo'q. To'g'ri tarkib: bundle'dagi
    kabi farsh ГП qatorlari + upakovka. Tannarx ham sku_bom orqali shu
    eski BOM'dan noto'g'ri hisoblanadi.

    Qoidalar:
      - nomzod: aktiv submitted BOM'ida ГП qatori umuman yo'q, YOKI
        upakovka qatori yo'q (bundle'da esa bor) — ikkala holatda ham
        bundle'ida ГП bo'lishi shart;
      - eski BOM'lar CANCEL QILINMAYDI (tarixiy SE'lar bog'langan) —
        faqat is_active=0, is_default=0 qilinadi;
      - yangi BOM bundle qatorlaridan (1 birlik uchun), aktiv+default.
    tasdiq='ALMASHTIR' shart; tasdiqsiz quruq ro'yxat.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    quruq = tasdiq != "ALMASHTIR"

    nomzodlar = frappe.db.sql(
        """
        SELECT b.item sku, b.name bom
        FROM `tabBOM` b
        JOIN `tabItem` s ON s.name = b.item AND s.item_group = %s
        WHERE b.docstatus = 1 AND b.is_active = 1
          AND (
            -- ГП qatori umuman yo'q (sof xomashyo retsepti)
            NOT EXISTS (
              SELECT 1 FROM `tabBOM Item` bi
              JOIN `tabItem` i ON i.name = bi.item_code
              WHERE bi.parent = b.name AND i.item_group = %s)
            -- yoki upakovkasiz (bundle'da upakovka bor)
            OR (NOT EXISTS (
                  SELECT 1 FROM `tabBOM Item` bi
                  JOIN `tabItem` i ON i.name = bi.item_code
                  WHERE bi.parent = b.name AND i.item_group = 'Упаковка')
                AND EXISTS (
                  SELECT 1 FROM `tabProduct Bundle` pb
                  JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
                  JOIN `tabItem` i ON i.name = pbi.item_code
                  WHERE pb.new_item_code = b.item
                    AND i.item_group = 'Упаковка'))
          )
          AND EXISTS (
            SELECT 1 FROM `tabProduct Bundle` pb
            JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
            JOIN `tabItem` i ON i.name = pbi.item_code
            WHERE pb.new_item_code = b.item AND i.item_group = %s)
        ORDER BY b.item
        """,
        (SOTUV_GURUH, NORMA_GURUH, NORMA_GURUH), as_dict=True,
    )
    natija = {"almashdi": [], "xato": [], "quruq": quruq,
              "nomzodlar": [n.sku for n in nomzodlar]}
    if quruq:
        return natija

    for n in nomzodlar:
        try:
            frappe.db.savepoint("bom_almash")
            # SKU'ning BARCHA submitted BOM'lari noaktiv qilinadi
            for eski in frappe.get_all("BOM", filters={
                    "item": n.sku, "docstatus": 1}, pluck="name"):
                frappe.db.set_value(
                    "BOM", eski, {"is_active": 0, "is_default": 0},
                    update_modified=False)
            qatorlar = frappe.db.sql(
                """
                SELECT pbi.item_code, SUM(pbi.qty) qty
                FROM `tabProduct Bundle` pb
                JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
                WHERE pb.new_item_code = %s
                GROUP BY pbi.item_code
                """,
                n.sku, as_dict=True,
            )
            bom = frappe.get_doc({
                "doctype": "BOM",
                "item": n.sku,
                "quantity": 1,
                "is_active": 1,
                "is_default": 1,
                "rm_cost_as_per": "Valuation Rate",
                "company": frappe.db.get_single_value(
                    "Global Defaults", "default_company"),
                "items": [
                    {"item_code": q.item_code, "qty": flt(q.qty)}
                    for q in qatorlar if flt(q.qty) > 0
                ],
            })
            bom.flags.ignore_permissions = True
            bom.insert()
            bom.submit()
            natija["almashdi"].append({"sku": n.sku, "eski": n.bom,
                                       "yangi": bom.name})
        except Exception:
            frappe.db.rollback(save_point="bom_almash")
            natija["xato"].append({"sku": n.sku,
                                   "xato": frappe.get_traceback()[-250:]})
    natija["jami"] = {"almashdi": len(natija["almashdi"]),
                      "xato": len(natija["xato"])}
    return natija
