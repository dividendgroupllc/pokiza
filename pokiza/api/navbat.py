# -*- coding: utf-8 -*-
# ============================================================================
#  ISHLAB CHIQARISH NAVBATI — kunlik reja (artifact spec, 2026-08-18)
#  Joylashuv: pokiza/pokiza/api/navbat.py
#
#  MODEL:
#   - Har zakaz (Sales Order) SUBMIT bo'lganda tizim unga "ishlab chiqarish
#     kuni"ni tayinlaydi: kesim vaqtigacha kelgan bo'lsa bugundan boshlab,
#     keyin kelgan bo'lsa ertadan boshlab — birinchi SIG'ADIGAN kunga.
#   - Yakshanba dam (sozlamada yoqilmagan bo'lsa) — reja sakrab o'tadi.
#   - Zakaz kunga SIG'MASA — kun sig'imi TO'LDIRILADI, qolgani keyingi ish
#     kun(lar)iga bo'linadi (egasi talabi 2026-08-19). Taqsimot SO ichidagi
#     "Kunlarga taqsimot" child jadvalida saqlanadi;
#     custom_ishlab_chiqarish_kuni = reja bo'yicha OXIRGI (bitish) kun.
#   - Qo'lda surish (surish API) — zakaz BUTUNLIGICHA tanlangan kunga o'tadi
#     (majburiy), har surish jurnalga yoziladi.
#   - SO bekor qilinsa — unga bog'liq QORALAMA schyot avtomatik o'chiriladi
#     (egasi talabi 2026-08-19); tasdiqlangan schyot bo'lsa bekor bloklanadi.
#   - Og'irlik (kg) manbalari, ustuvorlik bilan:
#       1) qator kg'da sotilsa -> stock_qty ning o'zi
#       2) to'plam (Product Bundle) ichidagi "Готовый продукт" qatorlari
#          (egasi tasdig'i 2026-08-18: Nos deb yozilganlari ham aslida kg,
#           shuning uchun 1:1 kg deb olinadi)
#       3) item'ning o'z UOM konversiyasi (1 dona = ? kg)
#       4) topilmasa 0 kg + zakazda ogohlantirish ro'yxati
# ============================================================================

import json
import math

import frappe
from frappe import _
from frappe.utils import (
    add_days, cint, flt, get_datetime, get_time, getdate, nowdate, today,
)

EPS = 0.0001
KG_UOMS = ("кг", "Kg", "kg")
GP_GROUP = "Готовый продукт"
SLOT_TARTIB = {
    "Ertalab": 0,
    "Tushlik / abed atrofi": 1,
    "Kechki salqin": 2,
    "Boshqa vaqt": 3,
}


def _sozlamalar():
    s = frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari")
    return frappe._dict(
        quvvat=flt(s.kunlik_quvvat_kg) or 6900.0,
        kesim=s.kesim_vaqti or "13:00:00",
        zames=flt(s.zames_kg) or 95.0,
        yakshanba=cint(s.yakshanba_ishlaydi),
        gorizont=cint(s.gorizont_kun) or 7,
    )


# ---------------------------------------------------------------------------
#  KG HISOBLASH
# ---------------------------------------------------------------------------
def _bundle_gp_map(item_codes):
    """Sotuv itemi -> to'plamidagi 'Готовый продукт' qatorlari.
    {sotuv_item: [{"gp": item, "kg_per_unit": qty}, ...]}
    Egasi tasdig'i: ГП qatori Nos'da yozilgan bo'lsa ham qiymati kg."""
    if not item_codes:
        return {}
    rows = frappe.db.sql(
        """
        SELECT pb.new_item_code AS sotuv_item,
               pbi.item_code AS gp,
               pbi.qty AS kg_per_unit
        FROM `tabProduct Bundle` pb
        JOIN `tabProduct Bundle Item` pbi ON pbi.parent = pb.name
        JOIN `tabItem` ci ON ci.name = pbi.item_code
        WHERE pb.disabled = 0
          AND ci.item_group = %(gp_group)s
          AND pb.new_item_code IN %(items)s
        """,
        {"gp_group": GP_GROUP, "items": tuple(item_codes)},
        as_dict=True,
    )
    out = {}
    for r in rows:
        out.setdefault(r.sotuv_item, []).append(
            {"gp": r.gp, "kg_per_unit": flt(r.kg_per_unit)}
        )
    return out


def _uom_kg_factor(item_code):
    """Item'ning o'z konversiyasidan 1 stock birlik = ? kg.
    UOM Conversion Detail: 1 <uom> = factor x stock_uom."""
    f = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "uom": ("in", KG_UOMS)},
        "conversion_factor",
    )
    f = flt(f)
    return (1.0 / f) if f > EPS else 0.0


def hisobla_qator_kg(row, gp_map):
    """Bitta zakaz qatori uchun (jami_kg, gp_royxat, nomalum).
    gp_royxat: [{"gp": nom, "kg": qiymat}] — mahsulot kesimi/zames uchun."""
    stock_uom = row.get("stock_uom") or frappe.get_cached_value(
        "Item", row["item_code"], "stock_uom"
    )
    stock_qty = flt(row.get("stock_qty")) or flt(row.get("qty"))
    qty = flt(row.get("qty"))

    # 1) kg'da sotiladi — miqdorning o'zi og'irlik
    if stock_uom in KG_UOMS:
        gp_rows = gp_map.get(row["item_code"]) or []
        if gp_rows:
            gps = [
                {"gp": g["gp"], "kg": flt(g["kg_per_unit"]) * stock_qty}
                for g in gp_rows
            ]
        else:
            # to'plami yo'q — retsept noma'lum, lekin og'irlik aniq
            gps = [{"gp": None, "kg": stock_qty}]
        return stock_qty, gps, False

    # 2) to'plam orqali (dona mahsulot, ichida ГП kg bilan)
    gp_rows = gp_map.get(row["item_code"]) or []
    kg_per_unit = sum(flt(g["kg_per_unit"]) for g in gp_rows)
    if kg_per_unit > EPS:
        gps = [
            {"gp": g["gp"], "kg": flt(g["kg_per_unit"]) * qty} for g in gp_rows
        ]
        return kg_per_unit * qty, gps, False

    # 3) item'ning o'z "1 dona = ? kg" konversiyasi
    factor = _uom_kg_factor(row["item_code"])
    if factor > EPS:
        kg = stock_qty * factor
        return kg, [{"gp": None, "kg": kg}], False

    # 4) aniqlanmadi
    return 0.0, [], True


def hisobla_zakaz_kg(doc):
    """Sales Order hujjati uchun jami kg + kg aniqlanmagan qatorlar."""
    items = [d for d in doc.get("items") or []]
    gp_map = _bundle_gp_map(list({d.item_code for d in items}))
    jami = 0.0
    nomalum = []
    for d in items:
        row = {
            "item_code": d.item_code,
            "qty": d.qty,
            "stock_qty": d.get("stock_qty"),
            "stock_uom": d.get("stock_uom"),
        }
        kg, _gps, yoq = hisobla_qator_kg(row, gp_map)
        jami += kg
        if yoq:
            nomalum.append(f"{d.item_code} — {flt(d.qty)} {d.uom or ''}".strip())
    return flt(jami, 2), nomalum


# ---------------------------------------------------------------------------
#  KUN TAYINLASH
# ---------------------------------------------------------------------------
def _yakshanbami(sana):
    return getdate(sana).weekday() == 6


def _kun_band_kg(sana, exclude_so=None):
    """Kunning band kg'i — submit bo'lgan zakazlarning shu kunga tushgan
    taqsimot qatorlari yig'indisi."""
    cond = "AND so.name != %(exclude)s" if exclude_so else ""
    r = frappe.db.sql(
        f"""
        SELECT IFNULL(SUM(kt.kg), 0)
        FROM `tabKun Taqsimot Qatori` kt
        JOIN `tabSales Order` so ON so.name = kt.parent
        WHERE kt.parenttype = 'Sales Order'
          AND so.docstatus = 1
          AND kt.sana = %(sana)s
          {cond}
        """,
        {"sana": sana, "exclude": exclude_so},
    )
    return flt(r[0][0]) if r else 0.0


# shundan kichik bo'sh joyga zakaz bo'lagi qo'yilmaydi (0.3 kg kabi mayda
# bo'laklar operatsion ma'nosiz) — qoldiq to'liq sig'sa baribir qo'yiladi
MIN_BOLAK_KG = 1.0


def kun_taqsimla(kelgan_vaqt, jami_kg, exclude_so=None, boshlanish_kun=None):
    """Zakaz kg'ini kunlarga taqsimlaydi: [{"sana": date, "kg": float}, ...].
    Kesim vaqtigacha kelgan -> bugundan, keyin -> ertadan boshlanadi.
    boshlanish_kun berilsa (oldindan zakaz) — reja o'sha kundan boshlanadi
    (lekin kesim qoidasidan ERTAROQ bo'lolmaydi).
    Har kunning bo'sh joyi TO'LDIRILADI, qolgani keyingi ish kuniga o'tadi
    (yakshanba sakrab o'tiladi). Kg noma'lum (0) zakaz birinchi to'lmagan
    ish kuniga bitta qator bilan tushadi."""
    s = _sozlamalar()
    kelgan = get_datetime(kelgan_vaqt or frappe.utils.now_datetime())

    kandidat = getdate(kelgan)
    if get_time(kelgan.time().strftime("%H:%M:%S")) > get_time(s.kesim):
        kandidat = getdate(add_days(kandidat, 1))
    # o'tmishga reja yozilmaydi (eski sana bilan kiritilgan zakaz)
    if kandidat < getdate(today()):
        kandidat = getdate(today())
    # oldindan zakaz: so'ralgan kundan boshlanadi
    if boshlanish_kun and getdate(boshlanish_kun) > kandidat:
        kandidat = getdate(boshlanish_kun)

    qoldi = flt(jami_kg)
    taqsimot = []
    for _i in range(730):
        if _yakshanbami(kandidat) and not s.yakshanba:
            kandidat = getdate(add_days(kandidat, 1))
            continue
        band = _kun_band_kg(kandidat, exclude_so=exclude_so)
        bosh = s.quvvat - band

        # kg noma'lum zakaz — joy hisobini o'zgartirmaydi, birinchi
        # to'lmagan ish kunga qo'yiladi
        if qoldi <= EPS:
            if bosh > EPS:
                return [{"sana": kandidat, "kg": 0.0}]
            kandidat = getdate(add_days(kandidat, 1))
            continue

        if bosh >= MIN_BOLAK_KG or (bosh > EPS and qoldi <= bosh + EPS):
            olish = min(bosh, qoldi)
            taqsimot.append({"sana": kandidat, "kg": flt(olish, 2)})
            qoldi -= olish
            if qoldi <= EPS:
                return taqsimot
        kandidat = getdate(add_days(kandidat, 1))

    frappe.throw(_("Reja kunini topib bo'lmadi (2 yil ichida bo'sh kun yo'q?)"))


def _taqsimot_yoz(so_name, taqsimot):
    """Submit bo'lgan zakazning taqsimot qatorlarini qayta yozadi (surish)."""
    frappe.db.delete(
        "Kun Taqsimot Qatori",
        {"parenttype": "Sales Order", "parent": so_name},
    )
    for i, t in enumerate(taqsimot, 1):
        frappe.get_doc({
            "doctype": "Kun Taqsimot Qatori",
            "parenttype": "Sales Order",
            "parent": so_name,
            "parentfield": "custom_kun_taqsimot",
            "idx": i,
            "sana": t["sana"],
            "kg": flt(t["kg"]),
        }).insert(ignore_permissions=True)


def _so_taqsimot(so_names):
    """{so_name: [{"sana": str, "kg": float}, ...]} — submit zakazlar uchun."""
    if not so_names:
        return {}
    rows = frappe.db.sql(
        """
        SELECT parent, sana, kg
        FROM `tabKun Taqsimot Qatori`
        WHERE parenttype = 'Sales Order' AND parent IN %(names)s
        ORDER BY sana
        """,
        {"names": tuple(so_names)},
        as_dict=True,
    )
    out = {}
    for r in rows:
        out.setdefault(r.parent, []).append(
            {"sana": str(r.sana), "kg": flt(r.kg, 1)}
        )
    return out


def _notify():
    try:
        frappe.publish_realtime("navbat_update", after_commit=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  SALES ORDER HOOKLARI (hooks.py -> doc_events)
# ---------------------------------------------------------------------------
def so_validate(doc, method=None):
    """Har saqlashda jami kg qayta hisoblanadi (brauzerga ishonilmaydi)."""
    jami, nomalum = hisobla_zakaz_kg(doc)
    doc.custom_jami_kg = jami
    doc.custom_ombordan_jami = flt(
        sum(flt(d.get("custom_ombordan_kg")) for d in doc.get("items") or []), 2
    )
    doc.custom_kg_nomalum = "\n".join(nomalum) if nomalum else None
    if not doc.custom_kelgan_vaqt:
        doc.custom_kelgan_vaqt = frappe.utils.now_datetime()
    if nomalum and not doc.flags.in_insert:
        frappe.msgprint(
            _("Diqqat: {0} ta qatorning og'irligi (kg) aniqlanmadi — ular kunlik "
              "limitda hisobga olinmaydi:<br>{1}").format(
                len(nomalum), "<br>".join(nomalum)
            ),
            indicator="orange",
            alert=True,
        )


def so_before_submit(doc, method=None):
    """Submit paytida kunlarga taqsimlanadi — shu paytdan zakaz joy egallaydi.
    Ombordan band qilingan qism ISHLAB CHIQARILMAYDI — rejaga faqat
    qolgan (ishlab chiqariladigan) kg tushadi.
    Bitish kuni (oxirgi taqsimot kuni) custom_ishlab_chiqarish_kuni'da."""
    ishlab_kg = max(
        flt(doc.custom_jami_kg) - flt(doc.custom_ombordan_jami), 0.0
    )
    if flt(doc.custom_ombordan_jami) > EPS and ishlab_kg <= EPS:
        # to'liq ombordan qoplangan — ishlab chiqarish yo'q, joy olmaydi,
        # kutilgan kunning o'ziga tushadi (faqat jo'natish qoladi)
        taqsimot = [{
            "sana": _kutilgan_kun(doc.custom_kelgan_vaqt, doc.get("custom_kerak_kun")),
            "kg": 0.0,
        }]
    else:
        taqsimot = kun_taqsimla(
            doc.custom_kelgan_vaqt, ishlab_kg, exclude_so=doc.name,
            boshlanish_kun=doc.get("custom_kerak_kun"),
        )
    doc.set("custom_kun_taqsimot", [])
    for t in taqsimot:
        doc.append("custom_kun_taqsimot", {"sana": t["sana"], "kg": t["kg"]})
    doc.custom_ishlab_chiqarish_kuni = taqsimot[-1]["sana"]


def so_on_submit_notify(doc, method=None):
    taqsimot = doc.get("custom_kun_taqsimot") or []
    if len(taqsimot) > 1:
        qismlar = ", ".join(
            "{0} — {1} kg".format(
                frappe.utils.formatdate(t.sana, "dd.MM"), flt(t.kg, 1)
            )
            for t in taqsimot
        )
        frappe.msgprint(
            _("Zakaz {0} kunga bo'lib rejalashtirildi: {1}").format(
                len(taqsimot), qismlar
            ),
            indicator="green",
            alert=True,
        )
    elif doc.custom_ishlab_chiqarish_kuni:
        frappe.msgprint(
            _("Zakaz <b>{0}</b> kuni rejasiga tushdi ({1} kg)").format(
                frappe.utils.formatdate(
                    doc.custom_ishlab_chiqarish_kuni, "dd.MM.yyyy"
                ),
                flt(doc.custom_jami_kg, 1),
            ),
            indicator="green",
            alert=True,
        )
    _notify()


def so_before_cancel(doc, method=None):
    """Zakaz bekor qilinganda unga bog'liq QORALAMA schyot avtomatik
    o'chiriladi (egasi talabi). Tasdiqlangan schyot bo'lsa — bekor bloklanadi:
    buxgalteriya yozuvi bor hujjatni indamay o'chirish xavfli."""
    submitted = frappe.get_all(
        "Sales Invoice Item",
        filters={"sales_order": doc.name, "docstatus": 1},
        pluck="parent", distinct=True,
    )
    if submitted:
        frappe.throw(
            _("Bu zakazga TASDIQLANGAN schyot bor: {0}. Avval schyotni bekor "
              "qiling, keyin zakazni bekor qilasiz.").format(
                ", ".join(sorted(set(submitted)))
            )
        )

    drafts = frappe.get_all(
        "Sales Invoice Item",
        filters={"sales_order": doc.name, "docstatus": 0},
        pluck="parent", distinct=True,
    )
    for si_name in sorted(set(drafts)):
        # schyotda boshqa zakaz qatorlari ham bo'lsa — o'chirmaymiz
        boshqa = frappe.db.count(
            "Sales Invoice Item",
            {"parent": si_name, "sales_order": ("!=", doc.name)},
        )
        if boshqa:
            frappe.msgprint(
                _("Qoralama schyot {0} o'chirilmadi — unda boshqa zakaz "
                  "qatorlari ham bor, o'zingiz tekshiring.").format(si_name),
                indicator="orange",
            )
            continue
        frappe.delete_doc(
            "Sales Invoice", si_name,
            ignore_permissions=True, force=True,
        )
        frappe.msgprint(
            _("Qoralama schyot {0} avtomatik o'chirildi").format(si_name),
            indicator="blue",
            alert=True,
        )

    # avtomatik yaratilgan PE qoralamalari ham o'chiriladi; tasdiqlangani
    # (omborga kirgani) tegilmaydi — ishlab chiqarish haqiqatda bo'lgan
    for pe in frappe.get_all(
        "Production Entry",
        filters={"sales_order": doc.name},
        fields=["name", "docstatus"],
    ):
        if pe.docstatus == 0:
            frappe.delete_doc("Production Entry", pe.name,
                              ignore_permissions=True, force=True)
            frappe.msgprint(
                _("Ombor kirimi qoralamasi {0} avtomatik o'chirildi").format(pe.name),
                indicator="blue", alert=True,
            )
        elif pe.docstatus == 1:
            frappe.msgprint(
                _("Diqqat: {0} tasdiqlangan ombor kirimi shu zakazga bog'liq — "
                  "kerak bo'lsa o'zingiz bekor qiling").format(pe.name),
                indicator="orange",
            )


def so_on_cancel(doc, method=None):
    """Bekor qilinganda joy avtomatik bo'shaydi (so'rovlar docstatus=1 filtrlaydi);
    iz qolishi uchun jurnalga yozamiz."""
    if doc.custom_ishlab_chiqarish_kuni:
        _jurnal_yoz(
            doc,
            eski_kun=doc.custom_ishlab_chiqarish_kuni,
            yangi_kun=None,
            sabab=_("Zakaz bekor qilindi — joy bo'shadi"),
        )
    _notify()


def _jurnal_yoz(doc, eski_kun, yangi_kun, sabab):
    frappe.get_doc({
        "doctype": "Reja Ozgarish Jurnali",
        "sales_order": doc.name,
        "mijoz": doc.get("customer_name") or doc.get("customer") or "",
        "miqdor_kg": flt(doc.get("custom_jami_kg")),
        "eski_kun": eski_kun,
        "yangi_kun": yangi_kun,
        "sabab": sabab or "",
    }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
#  SAHIFA API
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_navbat(sana=None, gorizont_boshi=None):
    """Bitta kunning to'liq ko'rinishi: mijoz kartochkalari (mashina vaqti
    tartibida), sig'im, mahsulot kesimi (zames), gorizont chizig'i, tavsiyalar."""
    sana = getdate(sana or nowdate())
    s = _sozlamalar()

    # shu kunga taqsimot qatori tushgan zakazlar (+ shu kundagi ulushi)
    kun_ulush = {
        r.parent: flt(r.kg)
        for r in frappe.db.sql(
            """
            SELECT kt.parent, kt.kg
            FROM `tabKun Taqsimot Qatori` kt
            JOIN `tabSales Order` so ON so.name = kt.parent
            WHERE kt.parenttype = 'Sales Order'
              AND so.docstatus = 1
              AND kt.sana = %(sana)s
            """,
            {"sana": sana},
            as_dict=True,
        )
    }
    so_list = (
        frappe.get_all(
            "Sales Order",
            filters={"name": ("in", list(kun_ulush))},
            fields=[
                "name", "customer", "customer_name", "custom_jami_kg",
                "custom_ombordan_jami", "custom_kelgan_vaqt",
                "custom_mashina_vaqti", "custom_mashina_izoh", "custom_izoh",
                "custom_kg_nomalum", "delivery_date",
            ],
        )
        if kun_ulush
        else []
    )
    taqsimotlar = _so_taqsimot(list(kun_ulush))

    # zakaz qatorlari + kg taqsimoti + holatlar
    items_by_so = {}
    if so_list:
        rows = frappe.db.sql(
            """
            SELECT name, parent, item_code, item_name, qty, uom, stock_qty,
                   stock_uom, custom_holat, custom_fakt_kg,
                   custom_ombordan_kg, custom_chiqarilgan_vaqt, custom_chiqargan
            FROM `tabSales Order Item`
            WHERE parent IN %(names)s
            ORDER BY idx
            """,
            {"names": tuple(d.name for d in so_list)},
            as_dict=True,
        )
        gp_map = _bundle_gp_map(list({r.item_code for r in rows}))
        # qatorga bog'liq ombor kirimlari (PE) — sahifada havola ko'rinadi
        pe_map = {}
        for p in frappe.get_all(
            "Production Entry",
            filters={"so_item": ("in", [r.name for r in rows]),
                     "docstatus": ("<", 2)},
            fields=["name", "so_item", "docstatus"],
        ):
            pe_map.setdefault(p.so_item, []).append(
                {"name": p.name, "docstatus": p.docstatus}
            )
        for r in rows:
            kg, gps, yoq = hisobla_qator_kg(r, gp_map)
            items_by_so.setdefault(r.parent, []).append({
                "row": r.name,
                "item_code": r.item_code,
                "item_name": r.item_name or r.item_code,
                "qty": flt(r.qty),
                "uom": r.uom,
                "kg": flt(kg, 1),
                "kg_nomalum": yoq,
                "gps": gps,
                "holat": r.custom_holat or "Kutilmoqda",
                "fakt_kg": flt(r.custom_fakt_kg, 1),
                "ombordan_kg": flt(r.custom_ombordan_kg, 1),
                "pe": pe_map.get(r.name, []),
                "chiqargan": r.custom_chiqargan or "",
                "chiqarilgan_vaqt": str(r.custom_chiqarilgan_vaqt or ""),
            })

    # mijoz bo'yicha guruhlash (bitta mijozning bir kundagi zakazlari birga)
    guruhlar = {}
    for so in so_list:
        key = so.customer or so.name
        g = guruhlar.setdefault(key, {
            "mijoz": so.customer_name or so.customer or _("Noma'lum"),
            "slot": so.custom_mashina_vaqti or "Boshqa vaqt",
            "slot_izoh": so.custom_mashina_izoh or "",
            "kelgan": so.custom_kelgan_vaqt,
            "jami_kg": 0.0,
            "zakazlar": [],
        })
        kun_kg = flt(kun_ulush.get(so.name), 1)
        g["jami_kg"] += kun_kg
        if so.custom_kelgan_vaqt and (not g["kelgan"] or so.custom_kelgan_vaqt < g["kelgan"]):
            g["kelgan"] = so.custom_kelgan_vaqt
        so_items = items_by_so.get(so.name, [])
        taqsimot = taqsimotlar.get(so.name, [])
        g["zakazlar"].append({
            "name": so.name,
            "kg": flt(so.custom_jami_kg, 1),
            "ombordan": flt(so.custom_ombordan_jami, 1),
            "kun_kg": kun_kg,
            "bolingan": len(taqsimot) > 1,
            "taqsimot": taqsimot,
            "izoh": so.custom_izoh or "",
            "kg_nomalum": so.custom_kg_nomalum or "",
            "delivery_date": str(so.delivery_date or ""),
            "progress": _zakaz_progress(so_items),
            "items": so_items,
        })

    tartiblangan = sorted(
        guruhlar.values(),
        key=lambda g: (
            SLOT_TARTIB.get(g["slot"], 3),
            g["slot_izoh"] or "99:99",
            str(g["kelgan"] or ""),
        ),
    )
    jami = flt(sum(g["jami_kg"] for g in tartiblangan), 1)
    ortiqcha = flt(max(jami - s.quvvat, 0), 1)

    # tavsiya: sig'imga sig'dirish uchun qaysi zakaz(lar)ni ertaga surish
    tavsiyalar = []
    if ortiqcha > EPS:
        nomzodlar = sorted(
            [z for g in tartiblangan for z in g["zakazlar"]],
            key=lambda z: -z["kun_kg"],
        )
        qoldi = ortiqcha
        for z in nomzodlar:
            if qoldi <= EPS:
                break
            tavsiyalar.append({"so": z["name"], "kg": z["kun_kg"]})
            qoldi -= z["kun_kg"]

    # mahsulot (ГП) kesimi + zames — faqat ISHLAB CHIQARILADIGAN qism:
    # ombordan band qilingan kg zamesga kirmaydi; bo'lingan zakazda shu
    # kunga to'g'ri kelgan ULUSH proportsional olinadi.
    kesim = {}
    for g in tartiblangan:
        for z in g["zakazlar"]:
            ishlab_jami = z["kg"] - z["ombordan"]
            ulush = (
                (z["kun_kg"] / ishlab_jami)
                if (z["bolingan"] and ishlab_jami > EPS)
                else 1.0
            )
            for it in z["items"]:
                # qatorning ishlab chiqariladigan qismi (ombordan ayirilgan)
                it_factor = 1.0
                if flt(it["kg"]) > EPS and flt(it["ombordan_kg"]) > EPS:
                    it_factor = max(
                        (flt(it["kg"]) - flt(it["ombordan_kg"])) / flt(it["kg"]), 0.0
                    )
                for gp in it["gps"]:
                    nom = gp["gp"] or _("(retsepti aniqlanmagan)")
                    kesim[nom] = kesim.get(nom, 0.0) + flt(gp["kg"]) * it_factor * ulush
    kesim_rows = sorted(
        (
            {"gp": k, "kg": flt(v, 1), "zames": int(math.ceil(v / s.zames)) if v > EPS else 0}
            for k, v in kesim.items()
        ),
        key=lambda r: -r["kg"],
    )

    # gorizont: N kunlik lenta — boshlanish nuqtasi sahifadan keladi
    # (tanlangan kun lentadan chiqib ketmasligi uchun), berilmasa bugundan
    gorizont = []
    kun = getdate(gorizont_boshi or nowdate())
    for _i in range(s.gorizont):
        gorizont.append({
            "sana": str(kun),
            "band": flt(_kun_band_kg(kun), 1),
            "yakshanba": _yakshanbami(kun),
        })
        kun = getdate(add_days(kun, 1))

    # hali submit bo'lmagan (joy olmagan) qoralamalar soni — ma'lumot uchun
    qoralama = frappe.db.count("Sales Order", {"docstatus": 0})

    # TASDIQLANMAGAN hujjatlar (egasi talabi 2026-08-23): qoralama PE = mahsulot
    # omborga KIRMAGAN, qoralama schyot = pul yozilmagan + ombordan CHIQMAGAN.
    # Ikkalasi ham ko'rinmasa ombor va qarzdorlik yolg'on bo'lib qoladi.
    pe_qoralama = {
        "soni": frappe.db.count("Production Entry", {"docstatus": 0}),
        "kg": flt(frappe.db.sql(
            "SELECT IFNULL(SUM(qty_to_manufacture),0) "
            "FROM `tabProduction Entry` WHERE docstatus=0")[0][0], 1),
        "royxat": [
            {
                "name": p.name,
                "item": p.item_to_manufacture,
                "kg": flt(p.qty_to_manufacture, 1),
                "sana": str(p.posting_date or ""),
                "so": p.sales_order or "",
            }
            for p in frappe.get_all(
                "Production Entry", filters={"docstatus": 0},
                fields=["name", "item_to_manufacture", "qty_to_manufacture",
                        "posting_date", "sales_order"],
                order_by="posting_date desc, creation desc", limit=20,
            )
        ],
    }
    si_qoralama = {
        "soni": frappe.db.count("Sales Invoice", {"docstatus": 0}),
        "summa": flt(frappe.db.sql(
            "SELECT IFNULL(SUM(grand_total),0) "
            "FROM `tabSales Invoice` WHERE docstatus=0")[0][0], 0),
        "royxat": [
            {
                "name": s.name,
                "mijoz": s.customer_name or "",
                "summa": flt(s.grand_total, 0),
                "sana": str(s.posting_date or ""),
            }
            for s in frappe.get_all(
                "Sales Invoice", filters={"docstatus": 0},
                fields=["name", "customer_name", "grand_total", "posting_date"],
                order_by="posting_date desc, creation desc", limit=20,
            )
        ],
    }

    # kun bo'yicha uchyot: nechta zakaz qaysi holatda
    kun_uchyot = {"kutilmoqda": 0, "jarayonda": 0, "tayyor": 0, "jonatildi": 0}
    for g in tartiblangan:
        for z in g["zakazlar"]:
            kun_uchyot[z["progress"]] = kun_uchyot.get(z["progress"], 0) + 1

    return {
        "sana": str(sana),
        "quvvat": s.quvvat,
        "zames_kg": s.zames,
        "jami_kg": jami,
        "ortiqcha": ortiqcha,
        "tavsiyalar": tavsiyalar,
        "guruhlar": tartiblangan,
        "kesim": kesim_rows,
        "gorizont": gorizont,
        "qoralama": qoralama,
        "pe_qoralama": pe_qoralama,
        "si_qoralama": si_qoralama,
        "kun_uchyot": kun_uchyot,
        "umumiy": _umumiy_uchyot(),
        "yakshanba_dam": not s.yakshanba,
    }


def _zakaz_progress(items):
    """Zakaz darajasidagi holat — qatorlardan kelib chiqadi (saqlanmaydi):
    kutilmoqda -> jarayonda -> tayyor (hammasi chiqarilgan) -> jonatildi."""
    if not items:
        return "kutilmoqda"
    n = len(items)
    jonatildi = sum(1 for i in items if i["holat"] == "Jonatildi")
    chiqdi = sum(1 for i in items if i["holat"] in ("Chiqarildi", "Jonatildi"))
    if jonatildi == n:
        return "jonatildi"
    if chiqdi == n:
        return "tayyor"
    if chiqdi > 0:
        return "jarayonda"
    return "kutilmoqda"


def _umumiy_uchyot():
    """Butun tizim bo'yicha: hozir nechta aktiv zakaz bor, qaysi kunlarga,
    nechtasi kechikkan (reja kuni o'tgan, hali jo'natilmagan)."""
    rows = frappe.db.sql(
        """
        SELECT so.name, so.custom_ishlab_chiqarish_kuni AS kun,
               so.custom_jami_kg AS kg,
               SUM(CASE WHEN IFNULL(soi.custom_holat,'Kutilmoqda') != 'Jonatildi'
                        THEN 1 ELSE 0 END) AS ochiq_qatorlar
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        WHERE so.docstatus = 1
          AND so.custom_ishlab_chiqarish_kuni IS NOT NULL
        GROUP BY so.name
        HAVING ochiq_qatorlar > 0
        """,
        as_dict=True,
    )
    bugun = getdate(today())
    kechikkan = [r for r in rows if r.kun and getdate(r.kun) < bugun]
    return {
        "aktiv_soni": len(rows),
        "aktiv_kg": flt(sum(flt(r.kg) for r in rows), 1),
        "kechikkan_soni": len(kechikkan),
        "kechikkan": [
            {"so": r.name, "kun": str(r.kun), "kg": flt(r.kg, 1)}
            for r in sorted(kechikkan, key=lambda x: str(x.kun))[:20]
        ],
    }


# ---------------------------------------------------------------------------
#  HOLAT HARAKATLARI (sahifadan)
# ---------------------------------------------------------------------------
ISHLAB_CHIQARISH_ROLLARI = ("Manufacturing Manager", "Manufacturing User", "System Manager")
SOTUV_ROLLARI = ("Sales Manager", "Sales User", "System Manager")


def _rol_tekshir(rollar, xabar):
    if not set(rollar) & set(frappe.get_roles()):
        frappe.throw(xabar, frappe.PermissionError)


def _qator(row_name):
    r = frappe.db.get_value(
        "Sales Order Item", row_name,
        ["name", "parent", "item_code", "docstatus", "custom_holat"],
        as_dict=True,
    )
    if not r or r.docstatus != 1:
        frappe.throw(_("Zakaz qatori topilmadi yoki tasdiqlanmagan"))
    return r


@frappe.whitelist()
def chiqarildi(row_name, fakt_kg):
    """Ishlab chiqarish rahbari: mahsulot chiqqanini fakt kg bilan tasdiqlaydi.
    Shu bilan birga OMBOR uchun Production Entry QORALAMASI avtomatik
    tayyorlanadi (egasi talabi 2026-08-23) — xodim ochib tekshiradi va
    tasdiqlaydi, shunda tayyor mahsulot omborga kiradi."""
    _rol_tekshir(ISHLAB_CHIQARISH_ROLLARI,
                 _("Ishlab chiqarishni faqat ishlab chiqarish xodimi tasdiqlaydi"))
    r = _qator(row_name)
    if r.custom_holat == "Jonatildi":
        frappe.throw(_("Bu qator allaqachon jo'natilgan"))
    if flt(fakt_kg) <= 0:
        frappe.throw(_("Fakt kg 0 dan katta bo'lishi kerak"))
    frappe.db.set_value("Sales Order Item", row_name, {
        "custom_holat": "Chiqarildi",
        "custom_fakt_kg": flt(fakt_kg),
        "custom_chiqarilgan_vaqt": frappe.utils.now_datetime(),
        "custom_chiqargan": frappe.session.user,
    }, update_modified=False)
    pe_list, pe_xabar = _pe_qoralama_yarat(r, flt(fakt_kg))
    _notify()
    return {"ok": True, "pe": pe_list, "pe_xabar": pe_xabar}


def _pe_qoralama_yarat(qator, fakt_kg):
    """Zakaz qatori tasdiqlanganda ГП bo'yicha Production Entry qoralamasi.
    Eski qoralama bo'lsa yangisi bilan almashtiriladi (miqdor o'zgargan
    bo'lishi mumkin). Avtomat SUBMIT QILINMAYDI — xodim tekshiradi.
    Qaytaradi: ([pe_nomlari], ogohlantirish_matni yoki None)."""
    from pokiza.pokiza_for_business.doctype.production_entry.production_entry import (
        get_bom_for_item, get_bom_items,
    )

    # shu qator uchun eski qoralamalar — miqdor yangilangani uchun o'chiriladi
    for eski in frappe.get_all(
        "Production Entry",
        filters={"so_item": qator.name, "docstatus": 0},
        pluck="name",
    ):
        frappe.delete_doc("Production Entry", eski,
                          ignore_permissions=True, force=True)

    gps = _bundle_gp_map([qator.item_code]).get(qator.item_code) or []
    jami_u = sum(flt(g["kg_per_unit"]) for g in gps)
    if not gps or jami_u <= EPS:
        return [], _("{0} — retsepti (to'plamdagi tayyor mahsulot) topilmadi, "
                     "ombor kirimini qo'lda yozing").format(qator.item_code)

    wh = frappe.db.get_value(
        "Production Entry", {"docstatus": 1}, "target_warehouse",
        order_by="creation desc",
    ) or frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name")
    company = frappe.db.get_single_value("Global Defaults", "default_company")

    yaratildi, ogohlantirish = [], []
    for g in gps:
        gp_kg = flt(fakt_kg) * flt(g["kg_per_unit"]) / jami_u
        if gp_kg <= EPS:
            continue
        bom = get_bom_for_item(g["gp"])
        if not bom:
            ogohlantirish.append(
                _("{0} — aktiv BOM yo'q, ombor kirimini qo'lda yozing").format(g["gp"])
            )
            continue
        items = [
            i for i in get_bom_items(bom, gp_kg, source_warehouse=wh)
            if flt(i["required_qty"]) > EPS
        ]
        if not items:
            ogohlantirish.append(
                _("{0} — BOM bo'sh, ombor kirimini qo'lda yozing").format(g["gp"])
            )
            continue
        pe = frappe.get_doc({
            "doctype": "Production Entry",
            "naming_series": "PE-.YYYY.-",
            "posting_date": nowdate(),
            "posting_time": frappe.utils.nowtime(),
            "company": company,
            "item_to_manufacture": g["gp"],
            "bom_no": bom,
            "qty_to_manufacture": flt(gp_kg, 2),
            "target_warehouse": wh,
            "items": items,
            "sales_order": qator.parent,
            "so_item": qator.name,
            "remarks": _("Navbat sahifasidan avtomatik: {0} / {1}, fakt {2} kg").format(
                qator.parent, qator.item_code, flt(fakt_kg, 2)
            ),
        })
        pe.insert(ignore_permissions=True)
        yaratildi.append(pe.name)
    return yaratildi, ("; ".join(ogohlantirish) if ogohlantirish else None)


@frappe.whitelist()
def chiqarish_bekor(row_name):
    """Xato tasdiqlangan bo'lsa — qaytarish (faqat jo'natilmagan bo'lsa).
    Avtomatik yaratilgan PE qoralamasi ham o'chiriladi; PE allaqachon
    tasdiqlangan bo'lsa — tegilmaydi, ogohlantiriladi."""
    _rol_tekshir(ISHLAB_CHIQARISH_ROLLARI, _("Huquq yo'q"))
    r = _qator(row_name)
    if r.custom_holat == "Jonatildi":
        frappe.throw(_("Jo'natilgan qatorni qaytarib bo'lmaydi"))
    frappe.db.set_value("Sales Order Item", row_name, {
        "custom_holat": "Kutilmoqda",
        "custom_fakt_kg": 0,
        "custom_chiqarilgan_vaqt": None,
        "custom_chiqargan": None,
    }, update_modified=False)

    ogoh = None
    for pe in frappe.get_all(
        "Production Entry",
        filters={"so_item": row_name},
        fields=["name", "docstatus"],
    ):
        if pe.docstatus == 0:
            frappe.delete_doc("Production Entry", pe.name,
                              ignore_permissions=True, force=True)
        elif pe.docstatus == 1:
            ogoh = _("Diqqat: {0} allaqachon tasdiqlangan (omborga kirgan) — "
                     "kerak bo'lsa uni o'zingiz bekor qiling").format(pe.name)
    _notify()
    return {"ok": True, "pe_xabar": ogoh}


@frappe.whitelist()
def jonatildi(sales_order):
    """Sotuv: tayyor zakazni jo'natilgan deb belgilaydi.
    Zakazga bog'liq qoralama schyot bo'lsa, uni ham qaytaradi —
    sotuvchi ochib tekshirib tasdiqlashi uchun (schyot avtomat submit QILINMAYDI)."""
    _rol_tekshir(SOTUV_ROLLARI, _("Jo'natishni faqat sotuv xodimi belgilaydi"))
    doc = frappe.get_doc("Sales Order", sales_order)
    if doc.docstatus != 1:
        frappe.throw(_("Zakaz tasdiqlanmagan"))
    ochiq = [d for d in doc.items if (d.custom_holat or "Kutilmoqda") == "Kutilmoqda"]
    if ochiq:
        frappe.throw(_("Hali chiqarilmagan qatorlar bor ({0} ta) — avval ishlab "
                       "chiqarish tasdiqlashi kerak").format(len(ochiq)))
    for d in doc.items:
        if d.custom_holat != "Jonatildi":
            frappe.db.set_value("Sales Order Item", d.name,
                                "custom_holat", "Jonatildi", update_modified=False)
    _notify()

    draft_si = frappe.db.get_value(
        "Sales Invoice Item", {"sales_order": sales_order, "docstatus": 0}, "parent"
    )
    return {"ok": True, "draft_si": draft_si}


def si_on_submit(doc, method=None):
    """Schyot tasdiqlanganda unga bog'langan zakaz qatorlari avtomatik
    'Jonatildi' bo'ladi (sotuvchi schyot orqali ishlagan holat)."""
    so_names = {d.sales_order for d in doc.get("items") or [] if d.get("sales_order")}
    if not so_names:
        return
    frappe.db.sql(
        """
        UPDATE `tabSales Order Item`
        SET custom_holat = 'Jonatildi'
        WHERE parent IN %(names)s AND docstatus = 1
          AND IFNULL(custom_holat, '') != 'Jonatildi'
        """,
        {"names": tuple(so_names)},
    )
    _notify()


@frappe.whitelist()
def surish(sales_order, yangi_kun, sabab=None):
    """Zakazni boshqa kunga qo'lda surish. Faqat Sales Order'ga yozish huquqi
    borlar; har surish jurnalga yoziladi. Yakshanbaga surib bo'lmaydi
    (sozlamada yoqilmagan bo'lsa)."""
    doc = frappe.get_doc("Sales Order", sales_order)
    if doc.docstatus != 1:
        frappe.throw(_("Faqat tasdiqlangan zakazni surish mumkin"))
    if not doc.has_permission("write"):
        frappe.throw(_("Sizda bu zakazni o'zgartirish huquqi yo'q"), frappe.PermissionError)

    s = _sozlamalar()
    yangi = getdate(yangi_kun)
    if _yakshanbami(yangi) and not s.yakshanba:
        frappe.throw(_("Yakshanba — dam olish kuni. Boshqa kunni tanlang."))
    if yangi < getdate(today()):
        frappe.throw(_("O'tgan kunga surib bo'lmaydi"))

    eski = doc.custom_ishlab_chiqarish_kuni
    eski_taqsimot = _so_taqsimot([doc.name]).get(doc.name) or []
    if str(eski) == str(yangi) and len(eski_taqsimot) <= 1:
        return {"ok": True}

    # qo'lda surish = MAJBURIY: zakaz butunligicha tanlangan kunga
    # (bo'laklar yig'ilib bitta kunga o'tadi; kun to'lib ketsa ogohlantiriladi)
    _taqsimot_yoz(doc.name, [{"sana": yangi, "kg": flt(doc.custom_jami_kg)}])
    doc.db_set("custom_ishlab_chiqarish_kuni", yangi, update_modified=False)
    _jurnal_yoz(doc, eski_kun=eski, yangi_kun=yangi, sabab=sabab)
    _notify()

    band = _kun_band_kg(yangi)
    return {
        "ok": True,
        "yangi_kun": str(yangi),
        "yangi_kun_band": flt(band, 1),
        "quvvat": s.quvvat,
        "toldi": band > s.quvvat + EPS,
    }


# ---------------------------------------------------------------------------
#  OMBOR (tayyor mahsulot qoldig'i + band qilish hisobi)
#  Sotuv itemi omborda turmaydi — to'plami ichidagi "Готовый продукт" turadi.
#  Band = submit bo'lgan, hali jo'natilmagan zakazlarning ombordan olgan kg'i.
# ---------------------------------------------------------------------------
def _gp_qoldiq():
    """{gp_item: ombordagi qoldiq kg} — Bin (barcha omborlar yig'indisi)."""
    rows = frappe.db.sql(
        """
        SELECT b.item_code, SUM(b.actual_qty) AS qty
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE i.item_group = %(gp)s
        GROUP BY b.item_code
        """,
        {"gp": GP_GROUP},
        as_dict=True,
    )
    return {r.item_code: flt(r.qty) for r in rows}


def _ombor_band_gp(exclude_so=None):
    """{gp_item: band kg} — aktiv zakazlar ombordan band qilgan miqdor.
    Sotuv itemining band kg'i to'plamidagi ГП(lar)ga ulush bo'yicha yoziladi."""
    cond = "AND so.name != %(exclude)s" if exclude_so else ""
    rows = frappe.db.sql(
        f"""
        SELECT soi.item_code, SUM(soi.custom_ombordan_kg) AS kg
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
          AND IFNULL(soi.custom_ombordan_kg, 0) > 0
          AND IFNULL(soi.custom_holat, '') != 'Jonatildi'
          {cond}
        GROUP BY soi.item_code
        """,
        {"exclude": exclude_so},
        as_dict=True,
    )
    gp_map = _bundle_gp_map([r.item_code for r in rows])
    band = {}
    for r in rows:
        gps = gp_map.get(r.item_code) or []
        jami = sum(flt(g["kg_per_unit"]) for g in gps)
        if not gps or jami <= EPS:
            continue
        for g in gps:
            ulush = flt(g["kg_per_unit"]) / jami
            band[g["gp"]] = band.get(g["gp"], 0.0) + flt(r.kg) * ulush
    return band


def _item_ombor(item_codes, exclude_so=None):
    """Sotuv itemlari uchun ombordan olsa bo'ladigan BO'SH kg.
    {item: {"gp_nomlar": [...], "bosh": kg}} — to'plami (ГП) yo'q item uchun None
    (ombordan tekshirib bo'lmaydi)."""
    item_codes = list(set(item_codes))
    gp_map = _bundle_gp_map(item_codes)
    qoldiq = _gp_qoldiq()
    band = _ombor_band_gp(exclude_so=exclude_so)
    out = {}
    for item in item_codes:
        gps = gp_map.get(item)
        if not gps:
            out[item] = None
            continue
        jami = sum(flt(g["kg_per_unit"]) for g in gps)
        if jami <= EPS:
            out[item] = None
            continue
        # itemning 1 kg'i uchun har ГПdan qancha ketadi — eng tor joy chegaralaydi
        bosh = None
        for g in gps:
            ulush = flt(g["kg_per_unit"]) / jami
            gp_bosh = max(flt(qoldiq.get(g["gp"])) - flt(band.get(g["gp"])), 0.0)
            mumkin = gp_bosh / ulush if ulush > EPS else 0.0
            bosh = mumkin if bosh is None else min(bosh, mumkin)
        out[item] = {
            "gp_nomlar": [g["gp"] for g in gps],
            "bosh": flt(bosh or 0.0, 1),
        }
    return out


@frappe.whitelist()
def get_ombor():
    """Ombor tab: tayyor mahsulot qoldig'i, band qilingan va bo'sh kg."""
    qoldiq = _gp_qoldiq()
    band = _ombor_band_gp()
    nomlar = sorted(set(qoldiq) | set(band))
    rows = []
    for nom in nomlar:
        q = flt(qoldiq.get(nom), 1)
        b = flt(band.get(nom), 1)
        if abs(q) < 0.05 and b < 0.05:
            continue
        rows.append({"gp": nom, "qoldiq": q, "band": b, "bosh": flt(q - b, 1)})
    rows.sort(key=lambda r: -r["qoldiq"])
    return {
        "rows": rows,
        "jami_qoldiq": flt(sum(r["qoldiq"] for r in rows), 1),
        "jami_band": flt(sum(r["band"] for r in rows), 1),
    }


# ---------------------------------------------------------------------------
#  ZAKAZ URISH (sahifadan Sales Order yaratish)
# ---------------------------------------------------------------------------
def _kutilgan_kun(kelgan_vaqt=None, kerak_kun=None):
    """Kesim vaqti bo'yicha zakaz 'tushishi kutilgan' birinchi ish kuni.
    kerak_kun berilsa (oldindan zakaz) — o'sha kundan erta bo'lmaydi."""
    s = _sozlamalar()
    kelgan = get_datetime(kelgan_vaqt or frappe.utils.now_datetime())
    kandidat = getdate(kelgan)
    if get_time(kelgan.time().strftime("%H:%M:%S")) > get_time(s.kesim):
        kandidat = getdate(add_days(kandidat, 1))
    if kandidat < getdate(today()):
        kandidat = getdate(today())
    if kerak_kun and getdate(kerak_kun) > kandidat:
        kandidat = getdate(kerak_kun)
    while _yakshanbami(kandidat) and not s.yakshanba:
        kandidat = getdate(add_days(kandidat, 1))
    return kandidat


def _zakaz_items_tayyorla(items):
    """Kiruvchi qatorlar (json yoki list) -> tekshirilgan ro'yxat + kg hisobi."""
    if isinstance(items, str):
        items = json.loads(items)
    items = [i for i in (items or []) if i.get("item_code") and flt(i.get("qty")) > 0]
    if not items:
        frappe.throw(_("Kamida bitta mahsulot va miqdor kiriting"))
    gp_map = _bundle_gp_map([i["item_code"] for i in items])
    out = []
    for i in items:
        meta = frappe.db.get_value(
            "Item", i["item_code"],
            ["item_name", "stock_uom", "disabled", "item_group"], as_dict=True,
        )
        if not meta:
            frappe.throw(_("Mahsulot topilmadi: {0}").format(i["item_code"]))
        if cint(meta.disabled):
            frappe.throw(_("Mahsulot o'chirilgan: {0}").format(i["item_code"]))
        row = {
            "item_code": i["item_code"],
            "qty": flt(i["qty"]),
            "stock_qty": flt(i["qty"]),
            "stock_uom": meta.stock_uom,
        }
        kg, gps, nomalum = hisobla_qator_kg(row, gp_map)
        out.append({
            "item_code": i["item_code"],
            "item_name": meta.item_name or i["item_code"],
            "qty": flt(i["qty"]),
            "uom": meta.stock_uom,
            "kg": flt(kg, 2),
            "kg_nomalum": nomalum,
            "ombordan_kg": min(max(flt(i.get("ombordan_kg")), 0.0), flt(kg, 2)),
        })
    return out


@frappe.whitelist()
def item_ombor(item_code):
    """Zakaz urish formasi uchun: tanlangan itemning ombordagi holati —
    qoldiq/band/bo'sh (tayyor mahsuloti — ГП — bo'yicha)."""
    info = _item_ombor([item_code]).get(item_code)
    if not info:
        return None
    gp = info["gp_nomlar"][0] if info["gp_nomlar"] else None
    qoldiq = _gp_qoldiq()
    band = _ombor_band_gp()
    return {
        "bosh": info["bosh"],
        "gp": gp,
        "qoldiq": flt(sum(qoldiq.get(g, 0.0) for g in info["gp_nomlar"]), 1),
        "band": flt(sum(band.get(g, 0.0) for g in info["gp_nomlar"]), 1),
    }


@frappe.whitelist()
def zakaz_korish(items, kelgan_vaqt=None, kerak_kun=None):
    """Zakaz urishdan OLDIN ko'rik: kg, reja (qaysi kunlarga tushadi),
    kunlik limitga sig'maydigan qism va har item bo'yicha ombordagi bo'sh
    tayyor mahsulot. kerak_kun berilsa reja o'sha kundan boshlanadi
    (oldindan zakaz). Hech narsa yozilmaydi."""
    if kerak_kun and getdate(kerak_kun) < getdate(today()):
        frappe.throw(_("O'tgan kunga zakaz olib bo'lmaydi"))
    rows = _zakaz_items_tayyorla(items)
    ombor = _item_ombor([r["item_code"] for r in rows])

    jami = flt(sum(r["kg"] for r in rows), 2)
    ombordan = flt(sum(r["ombordan_kg"] for r in rows), 2)
    ishlab = max(jami - ombordan, 0.0)

    taqsimot = kun_taqsimla(kelgan_vaqt, ishlab, boshlanish_kun=kerak_kun)
    kutilgan = _kutilgan_kun(kelgan_vaqt, kerak_kun)
    birinchi_kun_kg = sum(
        t["kg"] for t in taqsimot if str(t["sana"]) == str(kutilgan)
    )
    yetmaydi = flt(max(ishlab - birinchi_kun_kg, 0.0), 1)

    s = _sozlamalar()
    for r in rows:
        r["ombor"] = ombor.get(r["item_code"])
    return {
        "items": rows,
        "jami_kg": jami,
        "ombordan_kg": ombordan,
        "ishlab_kg": flt(ishlab, 2),
        "taqsimot": [{"sana": str(t["sana"]), "kg": t["kg"]} for t in taqsimot],
        "kutilgan_kun": str(kutilgan),
        "yetmaydi": yetmaydi,
        "quvvat": s.quvvat,
        "kutilgan_band": flt(_kun_band_kg(kutilgan), 1),
    }


@frappe.whitelist()
def zakaz_yarat(mijoz, items, mashina_vaqti=None, mashina_izoh=None,
                izoh=None, kerak_kun=None):
    """Sahifadan zakaz urish: Sales Order yaratiladi va SUBMIT qilinadi —
    shu paytda mavjud hooklar ishlaydi (kg, kunlarga taqsimot, draft schyot).
    Ombordan so'ralgan kg server tomonda QAYTA tekshiriladi (brauzerga
    ishonilmaydi) va zakaz qatoriga band sifatida yoziladi."""
    _rol_tekshir(SOTUV_ROLLARI, _("Zakaz urishni faqat sotuv xodimi qiladi"))
    if not frappe.db.exists("Customer", mijoz):
        frappe.throw(_("Mijoz topilmadi: {0}").format(mijoz))
    if kerak_kun and getdate(kerak_kun) < getdate(today()):
        frappe.throw(_("O'tgan kunga zakaz olib bo'lmaydi"))

    rows = _zakaz_items_tayyorla(items)

    # --- ombor talabini ГП kesimida tekshirish (bir xil ГПга ikki qator
    #     qo'shilib qoldiqdan oshib ketmasin)
    ombor = _item_ombor([r["item_code"] for r in rows])
    gp_map = _bundle_gp_map([r["item_code"] for r in rows])
    talab_gp = {}
    for r in rows:
        if r["ombordan_kg"] <= EPS:
            continue
        if not ombor.get(r["item_code"]):
            frappe.throw(
                _("{0} — to'plami (retsepti) yo'q, ombordan olib bo'lmaydi")
                .format(r["item_name"])
            )
        gps = gp_map.get(r["item_code"]) or []
        jami_u = sum(flt(g["kg_per_unit"]) for g in gps)
        for g in gps:
            ulush = flt(g["kg_per_unit"]) / jami_u
            talab_gp[g["gp"]] = talab_gp.get(g["gp"], 0.0) + r["ombordan_kg"] * ulush
    if talab_gp:
        qoldiq = _gp_qoldiq()
        band = _ombor_band_gp()
        for gp, kg in talab_gp.items():
            bosh = max(flt(qoldiq.get(gp)) - flt(band.get(gp)), 0.0)
            if kg > bosh + 0.05:
                frappe.throw(
                    _("Omborda '{0}' yetarli emas: so'ralgan {1} kg, bo'sh {2} kg")
                    .format(gp, flt(kg, 1), flt(bosh, 1))
                )

    # yetkazish taxminan: reja boshlanadigan kundan bir kun keyin
    yetkazish = add_days(str(kerak_kun) if kerak_kun else nowdate(), 1)
    so = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": mijoz,
        "order_type": "Sales",
        "delivery_date": yetkazish,
        "custom_kelgan_vaqt": frappe.utils.now_datetime(),
        "custom_kerak_kun": kerak_kun or None,
        "custom_mashina_vaqti": mashina_vaqti or None,
        "custom_mashina_izoh": mashina_izoh or None,
        "custom_izoh": izoh or None,
    })
    for r in rows:
        rate = flt(frappe.db.get_value(
            "Item Price", {"item_code": r["item_code"], "selling": 1},
            "price_list_rate",
        ))
        so.append("items", {
            "item_code": r["item_code"],
            "qty": r["qty"],
            "uom": r["uom"],
            "rate": rate,
            "delivery_date": yetkazish,
            "custom_ombordan_kg": r["ombordan_kg"],
        })
    so.insert()
    so.submit()

    # to'liq ombordan qoplangan qator ishlab chiqarilmaydi — darhol
    # "Chiqarildi" (faqat jo'natish qoladi)
    for d in so.items:
        r = next((x for x in rows if x["item_code"] == d.item_code), None)
        if r and not r["kg_nomalum"] and r["kg"] > EPS \
                and r["ombordan_kg"] >= r["kg"] - 0.05:
            frappe.db.set_value("Sales Order Item", d.name, {
                "custom_holat": "Chiqarildi",
                "custom_chiqarilgan_vaqt": frappe.utils.now_datetime(),
                "custom_chiqargan": frappe.session.user,
            }, update_modified=False)

    taqsimot = _so_taqsimot([so.name]).get(so.name) or []
    return {
        "so": so.name,
        "jami_kg": flt(so.custom_jami_kg, 1),
        "ombordan_kg": flt(so.custom_ombordan_jami, 1),
        "taqsimot": taqsimot,
        "kun": str(taqsimot[0]["sana"]) if taqsimot else None,
    }


# ---------------------------------------------------------------------------
#  SOZLAMALAR (sahifadan)
# ---------------------------------------------------------------------------
SOZLAMA_ROLLARI = ("System Manager", "Manufacturing Manager")


@frappe.whitelist()
def sozlamalar_get():
    s = frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari")
    return {
        "kunlik_quvvat_kg": flt(s.kunlik_quvvat_kg),
        "kesim_vaqti": str(s.kesim_vaqti or "13:00:00"),
        "zames_kg": flt(s.zames_kg),
        "yakshanba_ishlaydi": cint(s.yakshanba_ishlaydi),
        "gorizont_kun": cint(s.gorizont_kun) or 7,
        "tahrir_mumkin": bool(set(SOZLAMA_ROLLARI) & set(frappe.get_roles())),
    }


@frappe.whitelist()
def sozlamalar_saqla(kunlik_quvvat_kg, kesim_vaqti, zames_kg,
                     yakshanba_ishlaydi, gorizont_kun):
    _rol_tekshir(SOZLAMA_ROLLARI,
                 _("Sozlamalarni faqat rahbar o'zgartiradi"))
    if flt(kunlik_quvvat_kg) <= 0 or flt(zames_kg) <= 0:
        frappe.throw(_("Sig'im va zames kg 0 dan katta bo'lishi kerak"))
    if not (3 <= cint(gorizont_kun) <= 14):
        frappe.throw(_("Gorizont 3 dan 14 kungacha bo'lishi mumkin"))
    doc = frappe.get_doc("Ishlab Chiqarish Sozlamalari")
    doc.kunlik_quvvat_kg = flt(kunlik_quvvat_kg)
    doc.kesim_vaqti = kesim_vaqti
    doc.zames_kg = flt(zames_kg)
    doc.yakshanba_ishlaydi = cint(yakshanba_ishlaydi)
    doc.gorizont_kun = cint(gorizont_kun)
    doc.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Ishlab Chiqarish Sozlamalari")
    _notify()
    return {"ok": True}
