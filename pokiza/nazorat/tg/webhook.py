"""Telegram webhook: https://<sayt>/api/method/pokiza.nazorat.tg.webhook.handle

Faqat X-Telegram-Bot-Api-Secret-Token to'g'ri bo'lsa qabul qilinadi; update darhol navbatga beriladi.
"""
import hmac
import json

import frappe

from pokiza.nazorat.tg import config


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle():
    secret = config.secret()
    got = frappe.get_request_header("X-Telegram-Bot-Api-Secret-Token") or ""
    if not secret or not hmac.compare_digest(got.encode(), secret.encode()):
        frappe.local.response["http_status_code"] = 403
        return "forbidden"
    if not config.faol():
        return "ok"
    try:
        update = json.loads(frappe.request.get_data(as_text=True) or "{}")
    except ValueError:
        return "ok"
    uid = update.get("update_id")
    if uid is None:
        return "ok"
    key = frappe.cache.make_key(f"nazorat_tg_upd2:{uid}")
    if not frappe.cache.set(key, 1, ex=86400, nx=True):
        return "ok"  # Telegram qayta yuborgan — takrorlamaymiz (atomar tekshiruv)
    try:
        frappe.enqueue("pokiza.nazorat.tg.router.process_update", queue="short", update=update,
                       job_id=f"nazorat_tg_{uid}", deduplicate=True)
    except Exception:
        frappe.cache.delete(key)  # navbatga tushmadi — Telegram qayta yuborganda qabul qilinsin
        raise
    return "ok"
