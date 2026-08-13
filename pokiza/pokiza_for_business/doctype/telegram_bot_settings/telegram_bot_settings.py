import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url
from frappe.utils.password import get_decrypted_password

WEBHOOK_PATH = "/api/method/pokiza.api.telegram_webhook.handle"


class TelegramBotSettings(Document):
    pass


def default_webhook_url() -> str:
    """Saytning o'z manzilidan webhook URL yasash."""
    return get_url().rstrip("/") + WEBHOOK_PATH


@frappe.whitelist()
def set_webhook(webhook_url=None):
    """Webhook o'rnatish. URL berilmasa — sayt manzilidan avtomatik yasaladi."""
    token = _get_token()
    if not token:
        frappe.throw(_("Avval Bot Token kiritib, hujjatni saqlang"))

    if not webhook_url:
        webhook_url = frappe.db.get_single_value("Telegram Bot Settings", "webhook_url")
    if not webhook_url:
        webhook_url = default_webhook_url()

    if not webhook_url.startswith("https://"):
        frappe.throw(
            _(
                "Webhook faqat <b>https://</b> bilan ishlaydi. Hozirgi manzil: {0}<br>"
                "Lokal test uchun webhook o'rniga <b>polling</b> ishlating:<br>"
                "<code>bench --site {1} execute pokiza.telegram.polling.run</code>"
            ).format(webhook_url, frappe.local.site)
        )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=10,
        )
        result = r.json()
    except requests.RequestException as e:
        frappe.throw(str(e))

    if result.get("ok"):
        # Ishlatilgan URL'ni sozlamada saqlab qo'yamiz
        frappe.db.set_value(
            "Telegram Bot Settings", "Telegram Bot Settings", "webhook_url", webhook_url
        )
        frappe.db.commit()
        frappe.msgprint(_("✅ Webhook o'rnatildi:<br><code>{0}</code>").format(webhook_url))
    else:
        frappe.throw(_("Xato: {0}").format(result.get("description")))
    return result


@frappe.whitelist()
def delete_webhook():
    token = _get_token()
    if not token:
        frappe.throw(_("Bot Token kiritilmagan"))
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            timeout=10,
        )
        result = r.json()
        if result.get("ok"):
            frappe.msgprint(_("Webhook o'chirildi"))
        return result
    except requests.RequestException as e:
        frappe.throw(str(e))


@frappe.whitelist()
def bot_status() -> dict:
    """Bot va webhook holati — UI'dagi 'Bot holati' tugmasi uchun."""
    token = _get_token()
    if not token:
        frappe.throw(_("Avval Bot Token kiritib, hujjatni saqlang"))

    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
        wh = requests.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10
        ).json()
    except requests.RequestException as e:
        frappe.throw(_("Telegram API'ga ulanib bo'lmadi: {0}").format(e))

    if not me.get("ok"):
        frappe.throw(
            _("Token noto'g'ri yoki bot o'chirilgan: {0}").format(me.get("description"))
        )

    return {
        "bot": me.get("result", {}),
        "webhook": wh.get("result", {}),
        "linked_users": frappe.db.count("Telegram User", {"party": ["is", "set"]}),
        "total_users": frappe.db.count("Telegram User"),
        "admins": frappe.db.count("Telegram User", {"is_admin": 1}),
    }


def _get_token():
    try:
        return get_decrypted_password("Telegram Bot Settings", "Telegram Bot Settings", "bot_token")
    except Exception:
        return frappe.db.get_single_value("Telegram Bot Settings", "bot_token")
