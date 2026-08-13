"""Telegram webhook — Pokiza uchun asosiy kirish nuqtasi.

Ro'yxatdan o'tish oqimi:
    1. User /start bosadi
    2. Bot telefon raqam so'raydi
    3. User raqam yuboradi
    4. Bot Customer / Supplier / Employee ni contact_number orqali qidiradi
    5. Topilsa — telegram_chat_id saqlanadi, keyingi bildirishnomalar shu userga boradi

Webhook URL:
    https://your-site.com/api/method/pokiza.api.telegram_webhook.handle
"""

import json
import re

import frappe

from pokiza.telegram.config import is_admin, is_bot_active
from pokiza.telegram.keyboards import (
    akt_sverka_keyboard,
    admin_menu_keyboard,
    main_menu_keyboard,
)
from pokiza.telegram.messages import (
    ADMIN_BOT_STATUS,
    ADMIN_NO_UNLINKED,
    ADMIN_UNLINKED_LIST,
    ADMIN_WELCOME,
    ALREADY_LINKED,
    ASK_PHONE,
    CHOOSE_PERIOD,
    NOT_LINKED,
    PHONE_INVALID,
    PHONE_NOT_FOUND,
    WELCOME_CUSTOMER,
    WELCOME_EMPLOYEE,
    WELCOME_SUPPLIER,
)
from pokiza.telegram.sender import answer_callback_query, get_me, send_message

_STATE_PREFIX = "pokiza_tg_state:"
_STATE_TTL = 300  # 5 daqiqa


# ─── Setup endpoint (bir marta ishlatiladi) ───────────────────────────────────

@frappe.whitelist(allow_guest=True)
def run_setup():
    """Custom fieldlarni yaratish — faqat bir marta chaqiriladi."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    fields = {
        "Customer": [
            {"fieldname": "contact_number", "label": "Telefon raqam", "fieldtype": "Data",
             "options": "Phone", "insert_after": "customer_name", "in_standard_filter": 1},
            {"fieldname": "telegram_chat_id", "label": "Telegram Chat ID", "fieldtype": "Data",
             "insert_after": "contact_number", "read_only": 1},
        ],
        "Supplier": [
            {"fieldname": "contact_number", "label": "Telefon raqam", "fieldtype": "Data",
             "options": "Phone", "insert_after": "supplier_name", "in_standard_filter": 1},
            {"fieldname": "telegram_chat_id", "label": "Telegram Chat ID", "fieldtype": "Data",
             "insert_after": "contact_number", "read_only": 1},
        ],
        "Employee": [
            {"fieldname": "telegram_chat_id", "label": "Telegram Chat ID", "fieldtype": "Data",
             "insert_after": "employee_name", "read_only": 1},
        ],
    }
    create_custom_fields(fields, ignore_validate=True, update=True)
    frappe.db.commit()
    return {"ok": True, "message": "Custom fields yaratildi"}


# ─── Webhook entry point ──────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def handle():
    """Telegram har bir update kelganda shu URL ni chaqiradi."""
    if not is_bot_active():
        return {"ok": True}

    raw = frappe.request.data
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        update = json.loads(raw)
    except Exception:
        return {"ok": True}

    process_update(update)
    return {"ok": True}


def process_update(update: dict) -> None:
    """Bitta Telegram update'ni qayta ishlash (webhook ham, polling ham shuni chaqiradi)."""
    from pokiza.pokiza_for_business.doctype.telegram_user.telegram_user import (
        upsert_from_telegram,
    )

    if "message" in update:
        tg_from = update["message"].get("from")
        if tg_from:
            upsert_from_telegram(tg_from)
        _on_message(update["message"])
    elif "callback_query" in update:
        tg_from = update["callback_query"].get("from")
        if tg_from:
            upsert_from_telegram(tg_from)
        _on_callback(update["callback_query"])


# ─── Xabar dispatcher ────────────────────────────────────────────────────────

def _on_message(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if is_admin(chat_id):
        _admin_message(chat_id, text)
        return

    if text.startswith("/start"):
        _cmd_start(chat_id)
        return

    if text == "📊 Akt Sverka":
        if _is_linked(chat_id):
            send_message(chat_id, CHOOSE_PERIOD, reply_markup=akt_sverka_keyboard())
        else:
            send_message(chat_id, NOT_LINKED)
        return

    state = _get_state(chat_id)
    if state == "awaiting_phone":
        _handle_phone_input(chat_id, text)
        return

    if _is_linked(chat_id):
        send_message(
            chat_id,
            "📊 <b>Akt Sverka</b> tugmasini bosing.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        send_message(chat_id, NOT_LINKED)


# ─── Callback dispatcher ─────────────────────────────────────────────────────

def _on_callback(callback_query: dict) -> None:
    chat_id = callback_query["from"]["id"]
    data = callback_query.get("data", "")
    cq_id = callback_query["id"]

    if data.startswith("aks:"):
        period_code = data.split(":", 1)[1]
        party = _find_party_by_chat_id(str(chat_id))
        if not party:
            answer_callback_query(cq_id, "Siz tizimda topilmadingiz!")
            return
        frappe.enqueue(
            "pokiza.telegram.pdf_handler.handle_akt_sverka",
            chat_id=chat_id,
            callback_query_id=cq_id,
            period_code=period_code,
            party_type=party[0],
            party_name=party[1],
            display_name=party[2],
            queue="long",
            is_async=True,
        )
        return

    answer_callback_query(cq_id)


# ─── /start ──────────────────────────────────────────────────────────────────

def _cmd_start(chat_id: int) -> None:
    if _is_linked(chat_id):
        send_message(chat_id, ALREADY_LINKED, reply_markup=main_menu_keyboard())
        return
    _set_state(chat_id, "awaiting_phone")
    send_message(chat_id, ASK_PHONE)


# ─── Telefon orqali ro'yxatdan o'tish ────────────────────────────────────────

def _handle_phone_input(chat_id: int, text: str) -> None:
    phone = _normalize_phone(text)
    if not phone:
        send_message(chat_id, PHONE_INVALID)
        return

    result = _find_party_by_phone(phone)
    if not result:
        send_message(chat_id, PHONE_NOT_FOUND)
        return

    party_type, party_name, display_name = result

    frappe.db.set_value(party_type, party_name, "telegram_chat_id", str(chat_id))
    frappe.db.commit()

    from pokiza.pokiza_for_business.doctype.telegram_user.telegram_user import set_party
    set_party(chat_id, party_type, party_name, phone=phone)

    _clear_state(chat_id)

    if party_type == "Customer":
        msg = WELCOME_CUSTOMER.format(name=display_name)
    elif party_type == "Supplier":
        msg = WELCOME_SUPPLIER.format(name=display_name)
    else:
        msg = WELCOME_EMPLOYEE.format(name=display_name)

    send_message(chat_id, msg, reply_markup=main_menu_keyboard())


# ─── Telefon normalizatsiya ───────────────────────────────────────────────────

def _normalize_phone(raw: str) -> str:
    """Har xil formatdagi raqamni standart ko'rinimga keltiradi.

    +998 90 123 45 67  →  998901234567
    0901234567         →  998901234567
    901234567          →  998901234567
    """
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "998" + digits[1:]

    if len(digits) == 12 and digits.startswith("998"):
        return digits

    if len(digits) >= 7:
        return digits

    return ""


# ─── Party qidirish ───────────────────────────────────────────────────────────

def _find_party_by_phone(phone: str) -> tuple | None:
    """Customer, Supplier, Employee ni telefon orqali qidiradi."""
    last9 = phone[-9:] if len(phone) >= 9 else phone

    # Customer va Supplier — contact_number field orqali
    for doctype, name_field in [
        ("Customer", "customer_name"),
        ("Supplier", "supplier_name"),
    ]:
        # To'liq mos kelish
        row = frappe.db.get_value(
            doctype,
            {"contact_number": phone},
            ["name", name_field],
            as_dict=True,
        )
        if row:
            return doctype, row.name, row[name_field]

        # Oxirgi 9 raqam bilan qisman mos kelish
        rows = frappe.db.get_all(
            doctype,
            filters=[["contact_number", "like", f"%{last9}"]],
            fields=["name", name_field],
            limit=1,
        )
        if rows:
            return doctype, rows[0].name, rows[0][name_field]

    # Employee — cell_number orqali
    row = frappe.db.get_value(
        "Employee",
        {"cell_number": ["like", f"%{last9}"]},
        ["name", "employee_name"],
        as_dict=True,
    )
    if row:
        return "Employee", row.name, row.employee_name

    # ERPNext Contact Phone orqali ham qidirish (Customer/Supplier)
    for doctype in ["Customer", "Supplier"]:
        name_field = "customer_name" if doctype == "Customer" else "supplier_name"
        contact = frappe.db.sql("""
            SELECT dl.link_name
            FROM `tabContact Phone` cp
            JOIN `tabContact` c ON c.name = cp.parent
            JOIN `tabDynamic Link` dl ON dl.parent = c.name
            WHERE cp.phone LIKE %s
              AND dl.link_doctype = %s
              AND dl.parenttype = 'Contact'
            LIMIT 1
        """, (f"%{last9}%", doctype), as_dict=True)
        if contact:
            party_name = contact[0].link_name
            display = frappe.db.get_value(doctype, party_name, name_field) or party_name
            return doctype, party_name, display

    return None


def _find_party_by_chat_id(chat_id_str: str) -> tuple | None:
    """chat_id bo'yicha Customer, Supplier yoki Employee topish."""
    for doctype, name_field in [
        ("Customer", "customer_name"),
        ("Supplier", "supplier_name"),
    ]:
        row = frappe.db.get_value(
            doctype,
            {"telegram_chat_id": chat_id_str},
            ["name", name_field],
            as_dict=True,
        )
        if row:
            return doctype, row.name, row[name_field]

    row = frappe.db.get_value(
        "Employee",
        {"telegram_chat_id": chat_id_str},
        ["name", "employee_name"],
        as_dict=True,
    )
    if row:
        return "Employee", row.name, row.employee_name

    return None


def _is_linked(chat_id: int) -> bool:
    return _find_party_by_chat_id(str(chat_id)) is not None


# ─── Admin handlers ───────────────────────────────────────────────────────────

def _admin_message(chat_id: int, text: str) -> None:
    if text in ("/start", "/admin"):
        send_message(chat_id, ADMIN_WELCOME, reply_markup=admin_menu_keyboard())
        return

    if text == "👥 Telegram'siz kontragentlar":
        _admin_unlinked(chat_id)
        return

    if text == "ℹ️ Bot holati":
        _admin_status(chat_id)
        return

    send_message(chat_id, ADMIN_WELCOME, reply_markup=admin_menu_keyboard())


def _admin_unlinked(chat_id: int) -> None:
    lines = []

    customers = frappe.db.get_all(
        "Customer",
        filters=[["telegram_chat_id", "in", ["", None]]],
        fields=["customer_name", "contact_number"],
        limit=30,
    )
    for c in customers:
        phone = c.contact_number or "—"
        lines.append(f"👤 {c.customer_name}  <code>{phone}</code>")

    suppliers = frappe.db.get_all(
        "Supplier",
        filters=[["telegram_chat_id", "in", ["", None]]],
        fields=["supplier_name", "contact_number"],
        limit=30,
    )
    for s in suppliers:
        phone = s.contact_number or "—"
        lines.append(f"🏭 {s.supplier_name}  <code>{phone}</code>")

    if not lines:
        send_message(chat_id, ADMIN_NO_UNLINKED)
        return

    send_message(
        chat_id,
        ADMIN_UNLINKED_LIST.format(count=len(lines), list="\n".join(lines)),
    )


def _admin_status(chat_id: int) -> None:
    bot_info = get_me()
    customers = frappe.db.count(
        "Customer",
        filters=[["telegram_chat_id", "not in", ["", None]]],
    )
    suppliers = frappe.db.count(
        "Supplier",
        filters=[["telegram_chat_id", "not in", ["", None]]],
    )
    send_message(
        chat_id,
        ADMIN_BOT_STATUS.format(
            username=bot_info.get("username", "—"),
            bot_id=bot_info.get("id", "—"),
            customers=customers,
            suppliers=suppliers,
        ),
    )


# ─── Holat (state) boshqaruvi — Redis cache ───────────────────────────────────

def _set_state(chat_id: int, state: str) -> None:
    frappe.cache().set_value(f"{_STATE_PREFIX}{chat_id}", state, expires_in_sec=_STATE_TTL)


def _get_state(chat_id: int) -> str:
    return frappe.cache().get_value(f"{_STATE_PREFIX}{chat_id}") or ""


def _clear_state(chat_id: int) -> None:
    frappe.cache().delete_value(f"{_STATE_PREFIX}{chat_id}")
