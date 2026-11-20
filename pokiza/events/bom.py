# BOM sarf jami maydonlari — syryo jadvalidan avto hisoblash
import frappe
from frappe import _
from frappe.utils import cint, flt


def validate(doc, method=None):
    # FAQAT qoralamada: submit'dan keyin (masalan Is Active'ni o'chirganda)
    # qayta hisoblash float dumi tufayli "Cannot Update After Submit"
    # xatosini beradi (2.37545 vs 2.3754500000000003)
    if doc.docstatus != 0:
        return
    doc.custom_sarf_jami_soni = flt(
        sum(flt(d.qty) for d in (doc.items or [])), 6)
    doc.custom_sarf_jami_summa = flt(
        sum(flt(d.amount) for d in (doc.items or [])), 2)
    # ro'yxatda rang/filtr uchun: sotuv mahsulotining BOMi belgilanadi
    doc.custom_sotuv_sku = 1 if frappe.get_cached_value(
        "Item", doc.item, "item_group") == "Сотув махсулотлари" else 0


def before_validate(doc, method=None):
    """Qoralama BOM qatorlaridagi ichki BOM havolasi doim DEFAULT versiyaga
    to'g'rilanadi (2026-11-20, egasi shikoyati).

    ERPNext'da BOM nusxalanganda (duplicate/amend) qatordagi bom_no eski
    versiyaligicha ko'chib qoladi — default faqat bo'sh katakka olinadi
    (bom.py get_bom_material_detail). Shu yerda, erpnext validate'dan
    OLDIN (eski havola deaktiv bo'lsa validate_bom_no throw qiladi),
    havola itemning joriy default BOM'iga almashtiriladi.
    """
    if doc.docstatus != 0:
        return
    qatorlar = [d for d in (doc.get("items") or []) if d.bom_no and d.item_code]
    if not qatorlar:
        return
    defaultlar = dict(frappe.db.sql(
        "SELECT name, default_bom FROM `tabItem` WHERE name IN %s",
        (tuple({d.item_code for d in qatorlar}),),
    ))
    almashdi = []
    for d in qatorlar:
        default = defaultlar.get(d.item_code)
        if default and d.bom_no != default:
            almashdi.append("%s: %s → %s" % (d.item_code, d.bom_no, default))
            d.bom_no = default
    if almashdi and not (frappe.flags.in_migrate or frappe.flags.in_patch):
        frappe.msgprint(
            _("Ichki BOM havolalari joriy default versiyaga almashtirildi:")
            + "<br>" + "<br>".join(almashdi),
            indicator="orange", alert=True,
        )


def on_submit(doc, method=None):
    eski_versiyalarni_almashtir(doc)


def on_update_after_submit(doc, method=None):
    # submit'dan keyin Is Default / Is Active belgilanganda ham ishlaydi
    eski_versiyalarni_almashtir(doc)


def eski_versiyalarni_almashtir(doc):
    """Yangi BOM default bo'lganda shu itemning ESKI versiyalariga ishora
    qilib turgan barcha tashqi BOM'larda havolani avto yangilaydi —
    ERPNext'ning standart BOM Update Tool (Replace BOM) mexanizmi orqali:
    har eski versiya uchun BOM Update Log ochiladi, fon jobda bom_no
    almashadi, exploded items va narxlar qayta hisoblanadi, jurnal qoladi.
    """
    if not (cint(doc.is_active) and cint(doc.is_default)):
        return
    eski_bomlar = frappe.db.sql_list(
        """
        SELECT DISTINCT bi.bom_no
        FROM `tabBOM Item` bi
        JOIN `tabBOM` b ON b.name = bi.bom_no
        WHERE b.item = %s AND bi.bom_no != %s
          AND bi.docstatus < 2 AND bi.parenttype = 'BOM'
        """,
        (doc.item, doc.name),
    )
    if not eski_bomlar:
        return
    from erpnext.manufacturing.doctype.bom_update_tool.bom_update_tool import (
        enqueue_replace_bom,
    )
    loglar = []
    for eski in eski_bomlar:
        log = enqueue_replace_bom(boms={"current_bom": eski, "new_bom": doc.name})
        loglar.append("%s → %s (%s)" % (
            eski, doc.name,
            frappe.utils.get_link_to_form("BOM Update Log", log.name)))
    frappe.msgprint(
        _("Eski versiyaga ishora qilgan tashqi BOM'lar avto yangilanmoqda (BOM Update Tool):")
        + "<br>" + "<br>".join(loglar),
        indicator="blue",
    )
