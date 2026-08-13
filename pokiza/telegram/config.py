import frappe
from frappe.utils.password import get_decrypted_password


def get_bot_token() -> str | None:
    try:
        return get_decrypted_password("Telegram Bot Settings", "Telegram Bot Settings", "bot_token")
    except Exception:
        return frappe.db.get_single_value("Telegram Bot Settings", "bot_token")


def is_bot_active() -> bool:
    return bool(frappe.db.get_single_value("Telegram Bot Settings", "is_active"))


def get_admin_chat_ids() -> list[str]:
    admins = set()

    # Asosiy manba: Telegram User doctype'da "Admin" belgilanganlar
    admins.update(
        frappe.db.get_all("Telegram User", filters={"is_admin": 1}, pluck="chat_id")
    )

    # Eski usul (Telegram Bot Settings ichidagi jadval) ham ishlashda davom etadi
    rows = frappe.db.get_all(
        "Telegram Admin",
        filters={"parenttype": "Telegram Bot Settings"},
        fields=["chat_id"],
    )
    admins.update(r.chat_id for r in rows if r.chat_id)

    return [a for a in admins if a]


def is_admin(chat_id: int | str) -> bool:
    return str(chat_id) in get_admin_chat_ids()
