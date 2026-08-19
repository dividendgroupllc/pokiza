# -*- coding: utf-8 -*-
# ============================================================================
#  SEX PLANSHETI — Professional shop-floor backend (PARTIYA / LOT modeli)
#  Odoo Shop Floor + Katana + SAP "operation overlapping" arxitekturasi
#  Joylashuv: pokiza/pokiza/api/sex_ekran.py
#  Whitelist yo'li: pokiza.api.sex_ekran.<funksiya>
# ============================================================================
#  MODEL (real hayot oqimi):
#   - Har Job Card (etap) bir necha PARTIYADA bajarilishi mumkin (Sex Batch).
#   - Oldingi etapdan kelgan miqdor "kutilayotgan" kartochkada YIG'ILIB boradi:
#       Farsh 3 berdi -> Shprisda karta "3"; Shpris hali BOSHLAMAGAN bo'lsa,
#       Farsh yana 2 bersa -> o'sha karta "5" bo'ladi (bitta karta).
#   - Operator "Boshlash" bosgan zahoti partiya MUZLAYDI (qty qotadi).
#       Shundan keyin kelgan miqdor uchun YANGI karta ochiladi —
#       "Avvalgi zakazning davomi" ogohlantirishi bilan.
#   - Keyingi etapga miqdor JAMLANIB oqadi: Shpris 3+2 qilib ishlagan bo'lsa
#       ham, Qadoqlash boshlamagan bo'lsa unda BITTA karta "5" turadi.
#  Funksiyalar:
#   - get_workstation_jobs : sex uchun kartochkalar (partiyalar + kutilayotgan)
#   - start_batch          : kutilayotgan miqdorni partiya qilib boshlash
#   - pause_batch / resume_batch : partiyani to'xtatish / davom ettirish
#   - complete_batch       : partiya natijasini yozish (avto-qisman)
#  Operator = login qilgan userga bog'langan Employee (PIN/tanlash yo'q,
#  kirish har sex sahifasining roli orqali boshqariladi).
# ============================================================================

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, flt, cint

EPS = 0.0001


def _current_employee():
    """Login qilgan Frappe userga bog'langan Employee (agar bor bo'lsa)."""
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _notify():
    """Barcha ochiq sex sahifalariga "yangilan" signali (socketio realtime).
    Yangi ish paydo bo'lganda yoki biror sex partiya boshlaganda/tugatganda
    ishchilar ekrani darrov o'zi yangilanadi."""
    try:
        frappe.publish_realtime("sex_ekran_update", after_commit=True)
    except Exception:
        pass


def notify_new_job(doc, method=None):
    """hooks.py -> Job Card yaratilganda (yangi Work Order submit bo'lganda)
    sex ekranlariga signal boradi."""
    _notify()


# ---------------------------------------------------------------------------
#  KARTOCHKALAR:  ochiq partiyalar  +  kutilayotgan (yig'iluvchi) miqdor
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_workstation_jobs(workstation):
    """Berilgan sex ekrani uchun kartochkalar ro'yxati.
    Har Job Card uchun:
      - har bir ochiq partiya (In Progress / On Hold) = alohida kartochka;
      - oldingi etapdan kelib, hali boshlanmagan miqdor = bitta "kutilayotgan"
        kartochka (yangi kelgan miqdor unga qo'shilib boraveradi)."""
    if not workstation:
        return []

    job_cards = frappe.get_all(
        "Job Card",
        filters={"workstation": workstation, "docstatus": 0},
        fields=[
            "name", "work_order", "operation", "production_item", "item_name",
            "for_quantity", "total_completed_qty", "sequence_id",
        ],
        order_by="expected_start_date asc, creation asc",
    )

    result = []
    for jc in job_cards:
        upstream = _upstream_qty(jc)          # shu etapga jami "yetib kelgan"
        batches = _get_batches(jc.name)       # shu etapning partiyalari
        allocated = sum(flt(b.qty) for b in batches)
        item_info = _item_info(jc)

        # 1) Ochiq partiyalar — har biri alohida kartochka
        # part_no: shu zakaz (Job Card) ichida nechanchi qism ekani (1, 2, 3...)
        for idx, b in enumerate(batches):
            if b.status == "Completed":
                continue
            result.append(dict(
                item_info,
                card_id=b.name,
                kind="batch",
                batch=b.name,
                remaining=max(flt(b.qty) - flt(b.produced_qty), 0.0),
                batch_qty=flt(b.qty),
                status=b.status,
                part_no=idx + 1,
                is_continuation=cint(b.is_continuation),
                employee_name=b.employee_name or "",
                pause_reason=b.pause_reason or "",
            ))

        # 2) Kutilayotgan (hali boshlanmagan) miqdor — yig'ilib boradigan karta
        pending = min(upstream, flt(jc.for_quantity)) - allocated
        if pending > EPS:
            result.append(dict(
                item_info,
                card_id=jc.name + "::pending",
                kind="pending",
                batch=None,
                remaining=pending,
                batch_qty=pending,
                status="Pending",
                part_no=len(batches) + 1,
                is_continuation=1 if batches else 0,
                employee_name="",
                pause_reason="",
            ))
    return result


def _item_info(jc):
    """Kartochkaning umumiy (zakaz darajasidagi) ma'lumotlari."""
    item = jc.get("production_item")
    image = frappe.db.get_value("Item", item, "image") if item else None
    uom = (frappe.db.get_value("Item", item, "stock_uom") if item else "") or ""
    sales_order, izoh = _so_info(jc.get("work_order"))
    return {
        "job_card": jc.get("name"),
        "work_order": jc.get("work_order"),
        "operation": jc.get("operation"),
        "item": item,
        "item_name": jc.get("item_name") or item or "",
        "order_qty": flt(jc.get("for_quantity")),
        "order_done": flt(jc.get("total_completed_qty")),
        "uom": uom,
        "image": image,
        "sales_order": sales_order,
        "izoh": izoh,
    }


def _get_batches(job_card):
    return frappe.get_all(
        "Sex Batch",
        filters={"job_card": job_card},
        fields=["name", "qty", "produced_qty", "status", "is_continuation",
                "employee", "employee_name", "pause_reason"],
        order_by="creation asc",
    )


def _prev_completed(work_order, my_seq):
    """Oldingi (eng yaqin) etap jami yakunlagan miqdor.
    Birinchi etap uchun None (yuqoridan cheklov yo'q)."""
    if not work_order:
        return None
    siblings = frappe.get_all(
        "Job Card",
        filters={"work_order": work_order},
        fields=["sequence_id", "total_completed_qty"],
    )
    prev_seq = None
    for s in siblings:
        sq = s.get("sequence_id") or 0
        if sq < my_seq and (prev_seq is None or sq > prev_seq):
            prev_seq = sq
    if prev_seq is None:
        return None
    return sum(
        flt(s.get("total_completed_qty"))
        for s in siblings
        if (s.get("sequence_id") or 0) == prev_seq
    )


def _upstream_qty(jc):
    """Shu etapga hozirgacha 'yetib kelgan' jami miqdor:
       birinchi etap -> reja (for_quantity), keyingilar -> oldingi etap bajargani."""
    prev = _prev_completed(jc.get("work_order"), jc.get("sequence_id") or 0)
    return flt(jc.get("for_quantity")) if prev is None else flt(prev)


def _so_info(work_order):
    """Work Order'ga bog'langan Sales Order nomi va undagi izoh
    (kartada zakaz qaysi Sales Order uchunligi ko'rsatiladi)."""
    if not work_order:
        return None, ""
    try:
        so = frappe.db.get_value("Work Order", work_order, "sales_order")
        if so:
            izoh = frappe.db.get_value("Sales Order", so, "custom_izoh") or ""
            return so, izoh
    except Exception:
        pass
    return None, ""


# ---------------------------------------------------------------------------
#  HOLAT MASHINASI:  START (partiya ochish) -> PAUSE/RESUME -> COMPLETE
# ---------------------------------------------------------------------------
@frappe.whitelist()
def start_batch(job_card, employee=None):
    """"Boshlash": kutilayotgan miqdorni PARTIYA qilib muzlatadi.
    Shu paytdan keyin oldingi etapdan kelgan yangi miqdor alohida
    (davomi) kartochka bo'lib ochiladi."""
    employee = employee or _current_employee()
    jc = frappe.db.get_value(
        "Job Card", job_card,
        ["name", "work_order", "for_quantity", "total_completed_qty",
         "sequence_id", "docstatus"],
        as_dict=True,
    )
    if not jc:
        return {"ok": False, "error": _("Job Card topilmadi")}
    if jc.docstatus == 1:
        return {"ok": False, "error": _("Bu ish allaqachon yakunlangan")}

    batches = _get_batches(job_card)
    allocated = sum(flt(b.qty) for b in batches)
    pending = min(_upstream_qty(jc), flt(jc.for_quantity)) - allocated
    if pending <= EPS:
        return {"ok": False, "error": _("Hozircha boshlashga miqdor yo'q")}

    emp_name = (frappe.db.get_value("Employee", employee, "employee_name")
                if employee else None)
    batch = frappe.get_doc({
        "doctype": "Sex Batch",
        "job_card": job_card,
        "workstation": frappe.db.get_value("Job Card", job_card, "workstation"),
        "qty": pending,
        "produced_qty": 0,
        "status": "In Progress",
        "is_continuation": 1 if batches else 0,
        "employee": employee,
        "employee_name": emp_name or "",
        "started_at": now_datetime(),
    })
    try:
        batch.insert(ignore_permissions=True)
    except Exception as e:
        frappe.db.rollback()
        return {"ok": False, "error": str(e)}
    _notify()
    return {"ok": True, "batch": batch.name, "qty": pending}


@frappe.whitelist()
def pause_batch(batch, reason, note=None):
    """Partiyani to'xtatadi (sabab bilan).
    Sabab/izoh Job Card'dagi "To'xtatishlar tarixi" maydoniga (Time Logs
    jadvalining tagida) vaqt va operator bilan QO'SHILIB boradi — o'chmaydi."""
    b = frappe.db.get_value("Sex Batch", batch,
                            ["job_card", "employee_name"], as_dict=True)
    if not b:
        return {"ok": False, "error": _("Partiya topilmadi")}
    txt = reason if not note else "{0}: {1}".format(reason, note)
    frappe.db.set_value("Sex Batch", batch,
                        {"status": "On Hold", "pause_reason": txt})

    # Job Card'dagi tarixga qator qo'shamiz: [vaqt] operator — sabab
    if frappe.get_meta("Job Card").has_field("custom_pause_reason"):
        stamp = now_datetime().strftime("%d.%m.%Y %H:%M")
        who = " ({0})".format(b.employee_name) if b.employee_name else ""
        line = "[{0}]{1} {2}".format(stamp, who, txt)
        old = frappe.db.get_value("Job Card", b.job_card, "custom_pause_reason") or ""
        new = (old + "\n" + line).strip() if old else line
        frappe.db.set_value("Job Card", b.job_card, "custom_pause_reason", new)

    # Job Card holati: boshqa partiya ishlamayotgan bo'lsa — ON HOLD
    others_running = [x for x in _get_batches(b.job_card)
                      if x.name != batch and x.status == "In Progress"]
    if not others_running:
        frappe.db.set_value("Job Card", b.job_card, "status", "On Hold",
                            update_modified=False)
    _notify()
    return {"ok": True}


@frappe.whitelist()
def resume_batch(batch, employee=None):
    """To'xtatilgan partiyani davom ettiradi."""
    if not frappe.db.exists("Sex Batch", batch):
        return {"ok": False, "error": _("Partiya topilmadi")}
    employee = employee or _current_employee()
    vals = {"status": "In Progress", "pause_reason": ""}
    if employee:
        vals["employee"] = employee
        vals["employee_name"] = frappe.db.get_value(
            "Employee", employee, "employee_name") or ""
    frappe.db.set_value("Sex Batch", batch, vals)
    # Job Card holatini ham ishga qaytaramiz
    jc = frappe.db.get_value("Sex Batch", batch, "job_card")
    if jc:
        frappe.db.set_value("Job Card", jc, "status", "Work In Progress",
                            update_modified=False)
    _notify()
    return {"ok": True}


@frappe.whitelist()
def complete_batch(batch, good_qty=0, scrap_qty=0, close_job=0, employee=None):
    """Partiya natijasini yozish ("record production"):
       - good_qty : shu partiyada chiqqan yaroqli miqdor
       - scrap_qty: brak (yaroqsiz)
       - close_job: 1 bo'lsa — butun ishni (Job Card) ataylab erta yopish
    AVTO-QISMANLIK: partiya to'liq chiqmasa ham yozilaveradi (karta qoladi);
    Job Card rejasi to'liq bajarilganda avtomatik submit bo'ladi."""
    b = frappe.db.get_value(
        "Sex Batch", batch,
        ["name", "job_card", "qty", "produced_qty", "status",
         "employee", "started_at"],
        as_dict=True,
    )
    if not b:
        return {"ok": False, "error": _("Partiya topilmadi")}
    if b.status == "Completed":
        return {"ok": False, "error": _("Bu partiya allaqachon yakunlangan")}

    doc = frappe.get_doc("Job Card", b.job_card)
    if doc.docstatus == 1:
        return {"ok": False, "error": _("Bu ish allaqachon yakunlangan")}

    good = flt(good_qty)
    scrap = flt(scrap_qty)
    close_job = cint(close_job)
    if good <= 0:
        return {"ok": False, "error": _("Chiqqan miqdor 0 dan katta bo'lishi kerak")}

    batch_left = flt(b.qty) - flt(b.produced_qty)
    if good > batch_left + EPS:
        return {"ok": False, "error": _(
            "Bu partiyada {0} qoldi — undan ko'p yozib bo'lmaydi"
        ).format(batch_left)}

    employee = employee or b.employee or _current_employee()
    now = now_datetime()

    # Ishlab chiqarish yozuvi (time log). Qisqa oyna — bir xodimning ketma-ket
    # yozuvlari ustma-ust tushib overlap xatosi bermasligi uchun.
    doc.append("time_logs", {
        "from_time": add_to_date(now, seconds=-5),
        "to_time": now,
        "completed_qty": good,
        "employee": employee,
    })
    # brakni jamlaymiz
    if doc.meta.has_field("custom_scrap_qty"):
        doc.custom_scrap_qty = flt(doc.get("custom_scrap_qty")) + scrap

    total_good = sum(flt(t.completed_qty) for t in doc.time_logs)
    order_left = flt(doc.for_quantity) - total_good

    try:
        if order_left > EPS and not close_job:
            doc.status = "Work In Progress"
            doc.save(ignore_permissions=True)
        else:
            # Reja to'liq bajarildi YOKI ataylab erta yopildi
            if total_good < flt(doc.for_quantity):
                doc.for_quantity = total_good
            doc.status = "Completed"
            doc.save(ignore_permissions=True)
            doc.submit()

        # partiya holatini yangilaymiz
        new_produced = flt(b.produced_qty) + good
        batch_vals = {"produced_qty": new_produced}
        if new_produced >= flt(b.qty) - EPS or close_job or order_left <= EPS:
            batch_vals["status"] = "Completed"
        frappe.db.set_value("Sex Batch", batch, batch_vals)
        if close_job or order_left <= EPS:
            # butun ish yopildi — barcha ochiq partiyalarni ham yopamiz
            for ob in _get_batches(b.job_card):
                if ob.status != "Completed":
                    frappe.db.set_value("Sex Batch", ob.name, "status", "Completed")

        batch_done = batch_vals.get("status") == "Completed"
        # boshqa sexlar (keyingi etap) darrov ko'rsin
        _notify()
        return {"ok": True, "batch": batch, "batch_done": batch_done,
                "order_done": order_left <= EPS or close_job,
                "done": total_good, "remaining": max(order_left, 0)}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "complete_batch xato")
        return {"ok": False, "error": str(e)}
