"""Eski ichki BOM havolalarini default versiyaga ko'chirish (bir martalik).

Muammo (2026-11-20): BOM nusxalanganda ichki bom_no eski versiyaligicha
qolgan — bazada 83 ta aktiv BOM qatori eski (ko'pi deaktiv) ichki BOM'ga
ishora qiladi. Bu modul ERPNext'ning standart BOM Update Tool (Replace
BOM) mexanizmi bilan hammasini default versiyaga o'tkazadi.

Ishlatish (bench console):
    from pokiza.api.bom_versiya import eski_havolalar, tuzat
    eski_havolalar()                 # faqat ro'yxat (hech narsa o'zgarmaydi)
    tuzat(tasdiq="TUZAT")            # fon joblar bilan (prod: workerlar bor)
    tuzat(tasdiq="TUZAT", sync=1)    # darhol, shu jarayonda (lokal test)

Kelajak uchun himoya pokiza/events/bom.py da: yangi default BOM
submit bo'lganda eski havolalar avto almashadi, qoralamada esa
before_validate havolani defaultga to'g'rilaydi.
"""

import frappe
from frappe import _


def _juftliklar():
    """[(eski_bom, default_bom, item, nechta_qator)] — faqat default'i bor itemlar;
    defaultsizlar alohida ro'yxatda qaytadi."""
    rows = frappe.db.sql(
        """
        SELECT bi.bom_no AS eski, b.item, i.default_bom, COUNT(*) AS qatorlar
        FROM `tabBOM Item` bi
        JOIN `tabBOM` b ON b.name = bi.bom_no
        JOIN `tabItem` i ON i.name = b.item
        WHERE bi.docstatus < 2 AND bi.parenttype = 'BOM'
          AND i.default_bom IS NOT NULL AND i.default_bom != ''
          AND bi.bom_no != i.default_bom
        GROUP BY bi.bom_no, b.item, i.default_bom
        ORDER BY b.item
        """,
        as_dict=True,
    )
    defaultsiz = frappe.db.sql(
        """
        SELECT bi.bom_no AS eski, b.item, COUNT(*) AS qatorlar
        FROM `tabBOM Item` bi
        JOIN `tabBOM` b ON b.name = bi.bom_no
        JOIN `tabItem` i ON i.name = b.item
        WHERE bi.docstatus < 2 AND bi.parenttype = 'BOM'
          AND IFNULL(i.default_bom, '') = ''
        GROUP BY bi.bom_no, b.item
        """,
        as_dict=True,
    )
    return rows, defaultsiz


@frappe.whitelist()
def eski_havolalar():
    """Hisobot: qaysi eski ichki BOM'lar nechta tashqi BOM qatorida turibdi
    va qaysi default versiyaga almashadi. Hech narsani o'zgartirmaydi."""
    frappe.only_for("System Manager")
    rows, defaultsiz = _juftliklar()
    return {
        "almashadi": rows,
        "jami_qator": sum(r.qatorlar for r in rows),
        "defaultsiz": defaultsiz,  # itemda default BOM yo'q — qo'lda hal qilinadi
    }


@frappe.whitelist()
def tuzat(tasdiq=None, sync=0):
    """Har (eski → default) juftlik uchun BOM Update Log ochadi — ERPNext'ning
    o'zi tashqi BOM'lardagi havolani almashtiradi, narx/exploded items qayta
    hisoblanadi, hammasi BOM Update Log jurnalida qoladi.

    sync=1 — fon navbatsiz, shu jarayonda darhol bajariladi (lokal test /
    workersiz muhit uchun). Himoya: tasdiq="TUZAT" bo'lmasa faqat ro'yxat.
    """
    frappe.only_for("System Manager")
    rows, defaultsiz = _juftliklar()
    if tasdiq != "TUZAT":
        frappe.throw(_("Tasdiqlash uchun tasdiq='TUZAT' bering. Hozircha {0} juftlik topildi — ro'yxatni eski_havolalar() bilan ko'ring.").format(len(rows)))

    from erpnext.manufacturing.doctype.bom_update_log.bom_update_log import (
        run_replace_bom_job,
    )
    from erpnext.manufacturing.doctype.bom_update_tool.bom_update_tool import (
        enqueue_replace_bom,
    )

    natija = {"loglar": [], "xatolar": [], "defaultsiz": defaultsiz}
    for r in rows:
        boms = {"current_bom": r.eski, "new_bom": r.default_bom}
        try:
            log = enqueue_replace_bom(boms=boms)
            if int(sync or 0):
                # on_submit'dagi enqueue commit'dan keyin ham ketadi, lekin
                # job idempotent: sync bajarilgach almashadigan qator qolmaydi
                run_replace_bom_job(log, boms=boms)
                log.reload()
            natija["loglar"].append({
                "log": log.name, "status": log.status,
                "eski": r.eski, "yangi": r.default_bom, "qatorlar": r.qatorlar,
            })
        except Exception:
            frappe.db.rollback()
            natija["xatolar"].append({
                "eski": r.eski, "yangi": r.default_bom,
                "xato": frappe.get_traceback().splitlines()[-1],
            })
    return natija
