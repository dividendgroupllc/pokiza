"""Faza 3 — partiya (Batch) rejimi: SKU ombor itemi, partiya = norma.

Model (arxitektura 2026-09-21, egasi tasdiqlagan «Batch yo'li»):
  - Har (SKU, norma) juftligiga BITTA DOIMIY partiya ochiladi (kunlik lot
    emas) — «Jorj [N420]» va «Jorj [N340]» omborda alohida yuritiladi.
  - Partiya batchwise valuation bilan — har juftlikning o'z tannarxi.
  - Rejimga o'tgan SKU'da Product Bundle o'chiriladi (ERPNext ombor
    itemiga bundle taqiqlaydi), upakovka retsepti SKU Pasportiga ko'chadi.
  - Xodim «partiya» so'zini ko'rmaydi: hamma narsa kod ichida.

O'tish har SKU bo'yicha alohida (has_batch_no = yoqilgan/yoqilmagan —
tizimning o'zi shu belgiga qarab yangi/eski rejimda ishlaydi), shuning
uchun pilotdan to'liq o'tishgacha bosqichma-bosqich borish mumkin.
"""

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import flt, nowdate

SOTUV_GURUH = "Сотув махсулотлари"
NORMA_GURUH = "Готовый продукт"


def asosiy_ombor():
    return frappe.db.get_value(
        "Warehouse", {"is_group": 0, "disabled": 0}, "name"
    )


def partiya_rejimda(item_code):
    """SKU partiya rejimiga o'tganmi (has_batch_no — rejim belgisi)."""
    return bool(frappe.get_cached_value("Item", item_code, "has_batch_no"))


def partiya_ol(sku, norma):
    """(SKU, norma) juftligining doimiy partiyasi — bo'lmasa ochiladi."""
    nomi = frappe.db.get_value("Batch", {"item": sku, "custom_norma": norma})
    if nomi:
        return nomi
    batch = frappe.get_doc({
        "doctype": "Batch",
        "batch_id": make_autoname("PB-.#####"),
        "item": sku,
        "custom_norma": norma,
        "use_batchwise_valuation": 1,
        "description": "%s / %s" % (sku, norma),
    })
    batch.flags.ignore_permissions = True
    batch.insert()
    return batch.name


def partiya_qoldiq(sku, norma, warehouse=None):
    """(SKU, norma) partiyasining ombordagi qoldig'i (kg)."""
    nomi = frappe.db.get_value("Batch", {"item": sku, "custom_norma": norma})
    if not nomi:
        return 0.0, None
    from erpnext.stock.doctype.batch.batch import get_batch_qty
    qty = get_batch_qty(batch_no=nomi, warehouse=warehouse or asosiy_ombor(),
                        item_code=sku)
    return flt(qty), nomi


def norma_qoldiqlar(sku, warehouse=None):
    """SKU'ning barcha partiyalari norma kesimida: {norma: kg} (kg>0).

    v15'da batch qoldig'i SLE.batch_no'da emas, Serial and Batch Bundle
    ledgerida — shuning uchun har partiya get_batch_qty bilan o'qiladi
    (partiya soni = norma soni, ko'pi bilan bir nechta).
    """
    from erpnext.stock.doctype.batch.batch import get_batch_qty
    wh = warehouse or asosiy_ombor()
    out = {}
    for b in frappe.get_all("Batch", filters={"item": sku},
                            fields=["name", "custom_norma"]):
        qty = flt(get_batch_qty(batch_no=b.name, warehouse=wh, item_code=sku))
        if qty > 0.0005 and b.custom_norma:
            out[b.custom_norma] = out.get(b.custom_norma, 0.0) + qty
    return out


def pasport_qatorlari(sku):
    """SKU pasportidagi materiallar: [{item, qty}] (1 kg uchun)."""
    nomi = frappe.db.get_value("SKU Pasporti", {"sku": sku})
    if not nomi:
        return []
    return frappe.get_all(
        "SKU Pasport Qatori",
        filters={"parent": nomi, "parenttype": "SKU Pasporti"},
        fields=["item", "qty"],
        order_by="idx",
    )


@frappe.whitelist()
def pasport_kochir(sku=None):
    """Product Bundle'dagi upakovka qatorlarini SKU Pasportiga ko'chiradi.

    sku berilsa — bitta, berilmasa hamma bundle'li SKU. Mavjud pasportga
    TEGMAYDI (qo'lda tahrirlangan bo'lishi mumkin). Bundle o'chirilmaydi —
    uni batch_rejimga() o'chiradi.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))

    filtr = {"new_item_code": sku} if sku else {}
    natija = {"yaratildi": 0, "otkazildi": 0}
    for pb in frappe.get_all("Product Bundle", filters=filtr,
                             fields=["name", "new_item_code"]):
        if frappe.db.exists("SKU Pasporti", {"sku": pb.new_item_code}):
            natija["otkazildi"] += 1
            continue
        qatorlar = frappe.db.sql(
            """
            SELECT pbi.item_code, pbi.qty
            FROM `tabProduct Bundle Item` pbi
            JOIN `tabItem` i ON i.name = pbi.item_code
            WHERE pbi.parent = %s AND i.item_group != %s
            ORDER BY pbi.idx
            """,
            (pb.name, NORMA_GURUH),
            as_dict=True,
        )
        doc = frappe.get_doc({
            "doctype": "SKU Pasporti",
            "sku": pb.new_item_code,
            "manba": "Bundle: %s (%s)" % (pb.name, nowdate()),
        })
        for q in qatorlar:
            doc.append("qatorlar", {"item": q.item_code, "qty": q.qty})
        doc.flags.ignore_permissions = True
        doc.insert()
        natija["yaratildi"] += 1
    return natija


@frappe.whitelist()
def batch_rejimga(sku):
    """Bitta SKU'ni partiya rejimiga o'tkazadi (QAYTMAS QADAM — avval
    sinov saytda!):
      1) pasporti borligini tekshiradi (bo'lmasa bundle'dan ko'chiradi);
      2) Item: is_stock_item=1, has_batch_no=1;
      3) Product Bundle o'chiriladi (ma'lumot pasportda saqlangan).
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))

    item = frappe.get_doc("Item", sku)
    if item.item_group != SOTUV_GURUH:
        frappe.throw(_("{0} «{1}» guruhidan emas").format(sku, SOTUV_GURUH))
    if item.has_batch_no and item.is_stock_item:
        return {"holat": "allaqachon partiya rejimida"}

    # Item hech qachon omborda turmagan bo'lishi shart — aks holda rejim
    # almashtirib bo'lmaydi (qoldiq tarixi buziladi)
    if frappe.db.exists("Stock Ledger Entry", {"item_code": sku, "is_cancelled": 0}):
        frappe.throw(_("{0} bo'yicha ombor harakati bor — rejim almashtirilmaydi").format(sku))

    if not frappe.db.exists("SKU Pasporti", {"sku": sku}):
        pasport_kochir(sku)
    if not pasport_qatorlari(sku):
        frappe.throw(_("{0} — pasporti bo'sh (bundle ham yo'q). "
                       "Avval SKU Pasportini to'ldiring.").format(sku))

    # 1) bundle DISABLED qilinadi (o'chirib bo'lmaydi — minglab eski schyot
    #    bog'langan; disabled bundle'ni ERPNext packed-item mexanizmi
    #    butunlay e'tiborsiz qoldiradi: packed_item.py is_product_bundle/
    #    get_product_bundle_items ikkalasi disabled=0 filtri bilan ishlaydi)
    ochirildi = []
    for pb in frappe.get_all("Product Bundle",
                             filters={"new_item_code": sku, "disabled": 0},
                             pluck="name"):
        frappe.db.set_value("Product Bundle", pb, "disabled", 1)
        ochirildi.append(pb)

    # 2) Rejim maydonlari DB orqali (Item.cant_change ATAYIN chetlab
    #    o'tiladi: u tasdiqlangan SO/SI tarixi borligi uchun bloklaydi,
    #    lekin bu item OMBORDA HECH QACHON TURMAGAN (SLE yo'q — yuqorida
    #    tekshirildi), shuning uchun qoldiq/valyuatsiya tarixiga xavf yo'q.
    #    Yon ta'siri: eski ochiq zakazlarning band (reserved) miqdori —
    #    quyida qayta hisoblanadi.
    frappe.db.set_value("Item", sku, {
        "is_stock_item": 1,
        "has_batch_no": 1,
        "create_new_batch": 0,
        "is_sales_item": 1,
    }, update_modified=True)
    frappe.clear_cache(doctype="Item")
    frappe.get_cached_doc("Item", sku)  # keshni yangi qiymat bilan isitish

    # 3) ochiq zakazlardan band miqdorni qayta hisoblash (best-effort)
    try:
        from erpnext.stock.stock_balance import get_reserved_qty, update_bin_qty
        wh = asosiy_ombor()
        update_bin_qty(sku, wh, {"reserved_qty": get_reserved_qty(sku, wh)})
    except Exception:
        frappe.log_error(title="partiya: reserved_qty qayta hisoblash",
                         message=frappe.get_traceback())

    return {"holat": "partiya rejimida", "bundle_ochirildi": ochirildi}


@frappe.whitelist()
def boshlangich_partiya(sku, norma, kg, kg_narx, submit=0):
    """Inventarizatsiya kirimi: (SKU, norma) partiyasiga boshlang'ich qoldiq.

    Material Receipt Stock Entry QORALAMA yaratadi (submit=1 berilsa
    tasdiqlaydi — faqat sinovda). kg_narx — 1 kg tannarxi (inventarizatsiya
    bahosi), partiya valuation shu bilan boshlanadi.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Huquq yo'q"))
    if not partiya_rejimda(sku):
        frappe.throw(_("{0} hali partiya rejimida emas").format(sku))

    batch = partiya_ol(sku, norma)
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": frappe.db.get_single_value("Global Defaults", "default_company"),
        "items": [{
            "item_code": sku,
            "qty": flt(kg),
            "t_warehouse": asosiy_ombor(),
            "basic_rate": flt(kg_narx),
            "allow_zero_valuation_rate": 0 if flt(kg_narx) else 1,
            "use_serial_batch_fields": 1,
            "batch_no": batch,
        }],
        "remarks": "Boshlang'ich partiya qoldig'i (inventarizatsiya): %s / %s"
                   % (sku, norma),
    })
    se.flags.ignore_permissions = True
    se.insert()
    if int(submit):
        se.submit()
    return {"stock_entry": se.name, "batch": batch, "docstatus": se.docstatus}
