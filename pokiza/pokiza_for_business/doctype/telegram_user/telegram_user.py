import frappe
from frappe.model.document import Document


class TelegramUser(Document):
    pass


def upsert_from_telegram(tg_from: dict) -> None:
    """Telegram'dan kelgan har bir update'da foydalanuvchini ro'yxatga olish/yangilash.

    tg_from — Telegram update ichidagi "from" obyekti:
        {"id": 123, "first_name": "...", "last_name": "...", "username": "..."}
    """
    chat_id = str(tg_from.get("id") or "")
    if not chat_id:
        return

    first_name = " ".join(
        p for p in [tg_from.get("first_name"), tg_from.get("last_name")] if p
    )
    username = tg_from.get("username") or ""
    now = frappe.utils.now()

    if frappe.db.exists("Telegram User", chat_id):
        frappe.db.set_value(
            "Telegram User",
            chat_id,
            {"first_name": first_name, "username": username, "last_seen": now},
            update_modified=False,
        )
    else:
        frappe.get_doc(
            {
                "doctype": "Telegram User",
                "chat_id": chat_id,
                "first_name": first_name,
                "username": username,
                "status": "Active",
                "last_seen": now,
            }
        ).insert(ignore_permissions=True)
    frappe.db.commit()


def set_party(chat_id: int | str, party_type: str, party: str, phone: str = "") -> None:
    """Ro'yxatdan o'tganda Telegram User'ni kontragentga bog'lash."""
    chat_id = str(chat_id)
    if not frappe.db.exists("Telegram User", chat_id):
        return
    values = {"party_type": party_type, "party": party}
    if phone:
        values["phone"] = phone
    frappe.db.set_value("Telegram User", chat_id, values, update_modified=False)
    frappe.db.commit()
