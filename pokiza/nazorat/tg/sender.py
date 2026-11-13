"""Telegram Bot API (ichki bot). HTML parse_mode, 4096 belgidan uzun matnni bo'lish, 429 da qayta urinish."""
import json
import time

import frappe
import requests

from pokiza.nazorat.tg import config

API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 4000


class TgXato(Exception):
    pass


# bot o'chiq bo'lsa ham ishlaydigan (sozlash) metodlar; qolgan hammasi — xabar yuborish, bot o'chiq bo'lsa to'xtaydi
SOZLASH_METODLARI = {"getMe", "setWebhook", "deleteWebhook", "getWebhookInfo", "setMyCommands", "deleteMyCommands",
                     "getUpdates"}


def call(method, data=None, files=None, timeout=15, urinish=2):
    tok = config.token()
    if not tok:
        raise TgXato("Bot token kiritilmagan (Nazorat Bot Sozlamalari)")
    if method not in SOZLASH_METODLARI and not config.faol():
        raise TgXato("Nazorat boti o'chirilgan (Nazorat Bot Sozlamalari → Faol)")
    url = API.format(token=tok, method=method)
    for i in range(urinish + 1):
        try:
            if files:
                r = requests.post(url, data=data, files=files, timeout=max(timeout, 60))
            else:
                r = requests.post(url, json=data or {}, timeout=timeout)
        except requests.RequestException as e:
            if i < urinish:
                time.sleep(1 + i)
                continue
            raise TgXato(f"Tarmoq xatosi: {type(e).__name__}")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 429 and i < urinish:
            time.sleep(min(int((body.get("parameters") or {}).get("retry_after", 2)), 10))
            continue
        if not body.get("ok"):
            # token URL'da — log'ga faqat method va tavsif yoziladi
            raise TgXato(f"{method}: {body.get('description') or r.status_code}")
        return body.get("result")


def boluvchi(text, limit=LIMIT):
    """Matnni qator chegarasida bo'ladi (HTML teglar bitta qator ichida yopilgan bo'lishi kerak)."""
    parts, cur = [], ""
    for line in (text or "").split("\n"):
        while len(line) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts or [""]


def _himoya(chat_id):
    """Ma'lumot himoyasi: forward/saqlash taqiqi (Nazorat Bot Sozlamalari). Xato bo'lsa — himoyalangan."""
    try:
        from pokiza.nazorat.himoya import forward_taqiq

        return forward_taqiq(chat_id)
    except Exception:
        return True


def send_message(chat_id, text, reply_markup=None, reply_to=None, silent=False):
    """Bo'lib yuboradi; tugmalar oxirgi bo'lakka. Oxirgi xabar id'sini qaytaradi."""
    msg_id = None
    parts = boluvchi(text)
    himoya = _himoya(chat_id)
    for i, part in enumerate(parts):
        data = {"chat_id": chat_id, "text": part, "parse_mode": "HTML", "disable_web_page_preview": True,
                "disable_notification": silent, "protect_content": himoya}
        if reply_to and i == 0:
            data["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        if reply_markup and i == len(parts) - 1:
            data["reply_markup"] = reply_markup
        msg_id = (call("sendMessage", data) or {}).get("message_id")
    return msg_id


def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": boluvchi(text)[0], "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if reply_markup is not None:
        data["reply_markup"] = reply_markup
    try:
        return call("editMessageText", data)
    except TgXato as e:
        if "not modified" in str(e):
            return None
        raise


def send_photo(chat_id, png_bytes, caption="", reply_markup=None):
    data = {"chat_id": chat_id, "caption": boluvchi(caption, 1000)[0], "parse_mode": "HTML",
            "protect_content": "true" if _himoya(chat_id) else "false"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return call("sendPhoto", data, files={"photo": ("grafik.png", png_bytes, "image/png")})


def send_document(chat_id, file_bytes, filename, caption=""):
    return call("sendDocument", {"chat_id": chat_id, "caption": boluvchi(caption, 1000)[0], "parse_mode": "HTML",
                                 "protect_content": "true" if _himoya(chat_id) else "false"},
                files={"document": (filename, file_bytes)})


def answer_callback(callback_id, text="", alert=False):
    try:
        call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190], "show_alert": alert}, urinish=0)
    except TgXato:
        pass


def typing(chat_id):
    try:
        call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=5, urinish=0)
    except TgXato:
        pass


def xavfsiz_yubor(chat_id, text, **kw):
    """Hisobot/signal uchun: xato bo'lsa log yozadi, istisno ko'tarmaydi."""
    try:
        return send_message(chat_id, text, **kw)
    except TgXato as e:
        frappe.log_error(title="Nazorat bot: yuborib bo'lmadi", message=f"chat {chat_id}: {e}")
        return None

