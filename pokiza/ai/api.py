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


def _web_kontekst():
    """Web chat doirasi: faqat Administrator — cheklovsiz. Qolgan hamma (System Manager ham) — User.ai_roli
    bo'yicha (Telegram bilan bir xil manba). Chatga kirish "AI Foydalanuvchi" ERP roli bilan (_check)."""
    u = frappe.session.user
    if u == "Administrator":
        return None
    from pokiza.nazorat.scope import ai_tools, foydalanuvchi_roli

    bolim = foydalanuvchi_roli(u)
    if not bolim:
        frappe.throw("Sizga AI roli biriktirilmagan — AI ma'lumot bera olmaydi. Administrator foydalanuvchi "
                     "sahifasida «AI roli» maydonini to'ldirsin.", frappe.PermissionError)
    return {"kanal": "web", "bolim": bolim, "tools": ai_tools(bolim)}


def _suhbat_roli(suhbat, kontekst):
    """Mavjud suhbat boshqa rol bilan ochilgan bo'lsa davom ettirilmaydi: tarixida avvalgi rol ma'lumoti bor."""
    if not suhbat or kontekst is None:
        return
    if (frappe.db.get_value("AI Suhbat", suhbat, "bolim") or None) != kontekst["bolim"]:
        frappe.throw("Rolingiz o'zgargan (yoki bu suhbat rollar joriy etilishidan oldin ochilgan) — bu suhbatni "
                     "davom ettirib bo'lmaydi. Yangi suhbat oching.", frappe.PermissionError)


def _own(suhbat):
    owner = frappe.db.get_value("AI Suhbat", suhbat, "user")
    if not owner:
        frappe.throw("Suhbat topilmadi", frappe.DoesNotExistError)
    if owner != frappe.session.user:
        frappe.throw("Bu suhbat sizniki emas", frappe.PermissionError)


def _adminmi(user=None):
    """Boshqalarning suhbatini ko'ra oladi: Administrator yoki to'liq ruxsatli AI rolidagi System Manager.
    (Cheklangan roldagi System Manager boshqa suhbatlar orqali o'z rolidan ortiq ma'lumot ko'rmasin.)"""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    from pokiza.nazorat.scope import foydalanuvchi_roli, toliqmi

    return "System Manager" in frappe.get_roles(user) and toliqmi(foydalanuvchi_roli(user))


def _ulashilganmi(suhbat, user):
    return bool(frappe.db.exists("DocShare", {"share_doctype": "AI Suhbat", "share_name": suhbat, "user": user, "read": 1}))


def _rejim(suhbat):
    """Suhbatni ko'rish huquqi: egasi — to'liq; ulashilgan foydalanuvchi va administrator — faqat o'qish."""
    owner = frappe.db.get_value("AI Suhbat", suhbat, "user")
    if not owner:
        frappe.throw("Suhbat topilmadi", frappe.DoesNotExistError)
    u = frappe.session.user
    if owner == u:
        return "egasi"
    if _ulashilganmi(suhbat, u):
        return "ulashilgan"
    if _adminmi(u):
        return "admin"
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
    from pokiza.nazorat.himoya import qayd

    qayd("savol")  # xodim bir kunda chegaradan ko'p so'rasa — rahbarga xabar (Ma'lumot himoyasi)
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
def send_message(text=None, suhbat=None, files=None, loyiha=None):
    _check()
    s = get_settings()
    if not s.enabled:
        frappe.throw("Pokiza AI o'chirilgan")
    if s.monthly_limit_usd and month_spent_usd() >= s.monthly_limit_usd:
        frappe.throw(f"Oylik AI limiti (${s.monthly_limit_usd}) tugadi. Administratorga murojaat qiling.")

    kontekst = _web_kontekst()
    _suhbat_roli(suhbat, kontekst)
    if isinstance(files, str):
        files = json.loads(files or "[]")
    if loyiha and not suhbat:
        from pokiza.ai.loyiha import _own as loyiha_own

        loyiha_own(loyiha)
    yangi = not suhbat
    suhbat, user_xabar, xabar = _create_messages(text, suhbat, files)
    if yangi and loyiha:
        frappe.db.set_value("AI Suhbat", suhbat, "loyiha", loyiha)
    if yangi and kontekst is not None:
        frappe.db.set_value("AI Suhbat", suhbat, "bolim", kontekst["bolim"])
    frappe.enqueue(
        "pokiza.ai.agent.run",
        queue="long",
        timeout=900,
        enqueue_after_commit=True,
        suhbat=suhbat,
        xabar=xabar,
        kontekst=kontekst,
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
        fields=["name", "title", "status", "last_message_at", "modified", "loyiha"],
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
    rejim = _rejim(suhbat)
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
    doc = frappe.db.get_value("AI Suhbat", suhbat, ["name", "title", "status", "total_cost_usd", "loyiha", "user"], as_dict=True)
    doc["loyiha_nomi"] = frappe.db.get_value("AI Loyiha", doc.loyiha, "nomi") if doc.loyiha and rejim == "egasi" else None
    doc["rejim"] = rejim
    doc["egasi"] = get_fullname(doc.user)
    if rejim != "egasi":
        doc["loyiha"] = None
    return {"suhbat": doc, "messages": rows}


def _ulash_qatorlari(suhbat):
    return frappe.get_all("DocShare", filters={"share_doctype": "AI Suhbat", "share_name": suhbat, "read": 1},
                          pluck="user")


@frappe.whitelist()
def share_candidates(txt=None):
    """Ulashish uchun faol ERP foydalanuvchilari (o'zidan tashqari)."""
    _check()
    txt = f"%{(txt or '').strip()}%"
    return frappe.db.sql("""SELECT name, full_name FROM `tabUser`
        WHERE enabled = 1 AND user_type = 'System User' AND name NOT IN ('Administrator', 'Guest', %s)
          AND (name LIKE %s OR full_name LIKE %s)
        ORDER BY full_name LIMIT 30""", (frappe.session.user, txt, txt), as_dict=True)


@frappe.whitelist()
def get_shares(suhbat):
    _check()
    _own(suhbat)
    return [{"user": u, "full_name": get_fullname(u)} for u in _ulash_qatorlari(suhbat)]


@frappe.whitelist(methods=["POST"])
def share_conversation(suhbat, users=None):
    """Suhbatni tanlangan foydalanuvchilar bilan faqat o'qish uchun ulashish (ro'yxat to'liq almashtiriladi)."""
    _check()
    _own(suhbat)
    if isinstance(users, str):
        users = json.loads(users or "[]")
    users = {u for u in (users or []) if u and u != frappe.session.user}
    for u in users:
        if not frappe.db.get_value("User", {"name": u, "enabled": 1, "user_type": "System User"}):
            frappe.throw(f"Foydalanuvchi topilmadi yoki faol emas: {u}")
    from frappe.share import add_docshare, remove

    eski = set(_ulash_qatorlari(suhbat))
    for u in users - eski:
        add_docshare("AI Suhbat", suhbat, u, read=1, write=0, share=0, notify=1, flags={"ignore_share_permission": 1})
    for u in eski - users:
        remove("AI Suhbat", suhbat, u, flags={"ignore_share_permission": 1, "ignore_permissions": 1})
    return get_shares(suhbat)


@frappe.whitelist()
def list_shared_with_me():
    _check()
    names = frappe.get_all("DocShare", filters={"share_doctype": "AI Suhbat", "user": frappe.session.user, "read": 1},
                           pluck="share_name")
    if not names:
        return []
    rows = frappe.get_all("AI Suhbat", filters={"name": ["in", names]},
                          fields=["name", "title", "status", "last_message_at", "modified", "user"],
                          order_by="modified desc", limit_page_length=200)
    for r in rows:
        r["egasi"] = get_fullname(r.user)
    return rows


@frappe.whitelist()
def list_all_conversations():
    """Administrator uchun: boshqa foydalanuvchilarning suhbatlari (faqat o'qish)."""
    _check()
    if not _adminmi():
        frappe.throw("Faqat administrator uchun", frappe.PermissionError)
    rows = frappe.get_all("AI Suhbat", filters={"user": ["!=", frappe.session.user]},
                          fields=["name", "title", "status", "last_message_at", "modified", "user"],
                          order_by="modified desc", limit_page_length=500)
    for r in rows:
        r["egasi"] = get_fullname(r.user)
    return rows


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
    frappe.db.delete("DocShare", {"share_doctype": "AI Suhbat", "share_name": suhbat})
    for f in frappe.get_all("File", filters={"attached_to_doctype": "AI Suhbat", "attached_to_name": suhbat}, pluck="name"):
        frappe.delete_doc("File", f, ignore_permissions=True)
    frappe.delete_doc("AI Suhbat", suhbat, ignore_permissions=True)
    return True
