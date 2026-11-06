"""Pokiza AI sahifasi uchun whitelisted API. Faqat AI Foydalanuvchi va System Manager."""
import json

import frappe
from frappe.utils import add_to_date, get_datetime, get_fullname, now_datetime

from pokiza.ai import attachments
from pokiza.ai.agent import stop_key
from pokiza.ai.client import ROLES, get_settings, month_spent_usd
from pokiza.ai.prompt import user_preamble

MAX_INPUT_CHARS = 8000


def _check():
    frappe.only_for(ROLES)


def _own(suhbat):
    owner = frappe.db.get_value("AI Suhbat", suhbat, "user")
    if not owner:
        frappe.throw("Suhbat topilmadi", frappe.DoesNotExistError)
    if owner != frappe.session.user:
        frappe.throw("Bu suhbat sizniki emas", frappe.PermissionError)


def _create_messages(text, suhbat=None, files=None):
    text = (text or "").strip()
    files = attachments.own_files(files or [])
    if not text and not files:
        frappe.throw("Savol bo'sh")
    if len(text) > MAX_INPUT_CHARS:
        frappe.throw(f"Savol juda uzun (max {MAX_INPUT_CHARS} belgi)")

    if suhbat:
        _own(suhbat)
        status, modified = frappe.db.get_value("AI Suhbat", suhbat, ["status", "modified"])
        # ishchi o'lib qolgan bo'lsa 15 daqiqadan keyin qulf ochiladi
        if status == "Ishlayapti" and get_datetime(modified) > add_to_date(now_datetime(), minutes=-15):
            frappe.throw("Oldingi savolga javob hali tayyorlanmoqda")
    else:
        doc = frappe.get_doc(
            {
                "doctype": "AI Suhbat",
                "title": text[:80]
                or ("Ovozli xabar" if attachments.kind_of(files[0].file_name) == "audio" else files[0].file_name[:80]),
                "user": frappe.session.user,
                "status": "Tayyor",
            }
        ).insert(ignore_permissions=True)
        suhbat = doc.name

    for f in files:
        frappe.db.set_value("File", f.name, {"attached_to_doctype": "AI Suhbat", "attached_to_name": suhbat})
    # fayllar matndan oldin: Claude avval faylni, keyin savolni ko'radi
    content = [
        {"type": "pokiza_audio" if attachments.kind_of(f.file_name) == "audio" else "pokiza_file", "file": f.name}
        for f in files
    ]
    if text:
        question = text
    elif all(attachments.kind_of(f.file_name) == "audio" for f in files):
        question = "(Savol yuqoridagi ovozli xabarda.)"
    else:
        question = "(Foydalanuvchi faqat fayl yubordi: faylni ko'rib chiq va qisqa xulosa ber.)"
    content.append({"type": "text", "text": user_preamble(now_datetime(), get_fullname()) + question})
    user_xabar = frappe.get_doc(
        {
            "doctype": "AI Xabar",
            "suhbat": suhbat,
            "role": "user",
            "text": text,
            "content_json": json.dumps(content, ensure_ascii=False),
            "files_json": json.dumps(
                [attachments.file_info(frappe.get_doc("File", f.name)) for f in files], ensure_ascii=False
            ),
        }
    ).insert(ignore_permissions=True)
    xabar = frappe.get_doc(
        {"doctype": "AI Xabar", "suhbat": suhbat, "role": "assistant", "status": "Ishlayapti"}
    ).insert(ignore_permissions=True)
    frappe.db.set_value("AI Suhbat", suhbat, {"status": "Ishlayapti", "last_message_at": now_datetime()})
    return suhbat, user_xabar.name, xabar.name


@frappe.whitelist(methods=["POST"])
def upload():
    """Chatga fayl biriktirish (rasm, PDF, Excel/CSV). Xabar yuborilganda suhbatga bog'lanadi."""
    _check()
    f = frappe.request.files.get("file")
    if not f:
        frappe.throw("Fayl topilmadi")
    return attachments.save_upload(f.filename, f.stream.read(), frappe.form_dict.get("duration"))


@frappe.whitelist(methods=["POST"])
def send_message(text=None, suhbat=None, files=None):
    _check()
    s = get_settings()
    if not s.enabled:
        frappe.throw("Pokiza AI o'chirilgan")
    if s.monthly_limit_usd and month_spent_usd() >= s.monthly_limit_usd:
        frappe.throw(f"Oylik AI limiti (${s.monthly_limit_usd}) tugadi. Administratorga murojaat qiling.")

    if isinstance(files, str):
        files = json.loads(files or "[]")
    suhbat, user_xabar, xabar = _create_messages(text, suhbat, files)
    frappe.enqueue(
        "pokiza.ai.agent.run",
        queue="long",
        timeout=900,
        enqueue_after_commit=True,
        suhbat=suhbat,
        xabar=xabar,
    )
    return {"suhbat": suhbat, "user_xabar": user_xabar, "xabar": xabar}


@frappe.whitelist(methods=["POST"])
def stop(xabar):
    _check()
    _own(frappe.db.get_value("AI Xabar", xabar, "suhbat"))
    frappe.cache.set_value(stop_key(xabar), 1, expires_in_sec=900)
    return True


@frappe.whitelist()
def list_conversations():
    _check()
    return frappe.get_all(
        "AI Suhbat",
        filters={"user": frappe.session.user},
        fields=["name", "title", "status", "last_message_at", "modified"],
        order_by="modified desc",
        limit_page_length=200,
    )


def _sources(tool_calls_json):
    out = []
    for a in json.loads(tool_calls_json or "[]"):
        inp = a.get("input") or {}
        out.append(
            {
                "name": a.get("name"),
                "is_error": a.get("is_error"),
                "ms": a.get("ms"),
                "report": inp.get("report"),
                "sql": inp.get("sql"),
                "purpose": inp.get("purpose"),
                "input": {k: v for k, v in inp.items() if k not in ("sql", "purpose")},
            }
        )
    return out


@frappe.whitelist()
def get_conversation(suhbat):
    _check()
    _own(suhbat)
    rows = frappe.get_all(
        "AI Xabar",
        filters={"suhbat": suhbat},
        fields=["name", "role", "text", "status", "error", "tool_calls_json", "files_json", "dashboards_json", "cost_usd", "creation"],
        order_by="creation asc",
    )
    for r in rows:
        r["sources"] = _sources(r.pop("tool_calls_json"))
        r["files"] = json.loads(r.pop("files_json") or "[]")
        r["dashboards"] = json.loads(r.pop("dashboards_json") or "[]")
    doc = frappe.db.get_value("AI Suhbat", suhbat, ["name", "title", "status", "total_cost_usd"], as_dict=True)
    return {"suhbat": doc, "messages": rows}


@frappe.whitelist(methods=["POST"])
def rename_conversation(suhbat, title):
    _check()
    _own(suhbat)
    frappe.db.set_value("AI Suhbat", suhbat, "title", (title or "").strip()[:140] or "Suhbat")
    return True


@frappe.whitelist(methods=["POST"])
def delete_conversation(suhbat):
    _check()
    _own(suhbat)
    frappe.db.delete("AI Xabar", {"suhbat": suhbat})
    for f in frappe.get_all("File", filters={"attached_to_doctype": "AI Suhbat", "attached_to_name": suhbat}, pluck="name"):
        frappe.delete_doc("File", f, ignore_permissions=True)
    frappe.delete_doc("AI Suhbat", suhbat, ignore_permissions=True)
    return True
