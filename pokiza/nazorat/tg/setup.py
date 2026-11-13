"""Nazorat Bot Sozlamalari tugmalari: token tekshirish, webhook va buyruqlar menyusini o'rnatish."""
import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.sender import TgXato, call

# Menyuda ko'rinadigan buyruqlar minimal: hammasi pastki tugmalarda. Eski /kunlik, /kpi A2 ... baribir ishlaydi.
BUYRUQLAR = [{"command": "start", "description": "Menyu"}]


def _holat(doc, matn):
    doc.db_set("webhook_holati", f"{now_datetime():%Y-%m-%d %H:%M} — {matn}")
    frappe.clear_document_cache(config.DOCTYPE, config.DOCTYPE)


@frappe.whitelist()
def ornatish():
    frappe.only_for("System Manager")
    doc = frappe.get_single(config.DOCTYPE)
    try:
        me = call("getMe")
        doc.db_set("bot_username", me.get("username"))
        frappe.clear_document_cache(config.DOCTYPE, config.DOCTYPE)
        call("setMyCommands", {"commands": BUYRUQLAR, "scope": {"type": "all_private_chats"}})
        call("deleteMyCommands", {"scope": {"type": "all_group_chats"}})  # bot guruhda ishlamaydi
        base = (doc.sayt_url or get_url()).rstrip("/")
        if not base.startswith("https://"):
            _holat(doc, f"@{me.get('username')} token to'g'ri. Webhook o'rnatilmadi: {base} HTTPS emas "
                        "(lokalda polling ishlating).")
            return _("Token to'g'ri: @{0}. Sayt HTTPS emas — lokalda: bench --site {1} execute pokiza.nazorat.tg.polling.run").format(
                me.get("username"), frappe.local.site)
        url = f"{base}/api/method/pokiza.nazorat.tg.webhook.handle"
        call("setWebhook", {"url": url, "secret_token": config.secret(),
                            "allowed_updates": ["message", "callback_query", "my_chat_member"], "max_connections": 10})
        _holat(doc, f"@{me.get('username')} webhook o'rnatildi: {url}")
        return _("Tayyor: @{0} webhook o'rnatildi").format(me.get("username"))
    except TgXato as e:
        _holat(doc, f"XATO: {e}")
        frappe.throw(_("Telegram xatosi: {0}").format(str(e)))


@frappe.whitelist()
def ochirish():
    frappe.only_for("System Manager")
    call("deleteWebhook")
    _holat(frappe.get_single(config.DOCTYPE), "webhook o'chirildi")
    return _("Webhook o'chirildi")
