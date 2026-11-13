"""Pokiza AI Telegram kanali (5-bosqich): mavjud agent (pokiza/ai) qayta ishlatiladi, ikkinchi "miya" yo'q.

- Faqat shaxsiy chat: rahbar (to'liq) yoki AI ruxsati bor xodim (o'z roli doirasida). Guruh yo'q.
- Javob faqat savol kelgan chatga ketadi (chat_id AI'dan olinmaydi). AI baribir faqat o'qiydi (READ ONLY guard);
  "yozish" faqat TAKLIF ko'rinishida (vazifa / xodimga xabar) — rahbar tugma bilan tasdiqlaydi.
Patternlar: hamroh (MIT, github.com/Rustam-Z/hamroh) — input normalizer.
"""
import json
import re
import time
import unicodedata

import frappe
import requests
from frappe.utils import add_to_date, now_datetime

from pokiza.nazorat.scope import ai_tools, vazifa_berish as _vazifa_berish
from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.format import esc, md_to_html
from pokiza.nazorat.tg.sender import TgXato, call, send_document, send_message, typing

_YASHIRIN = re.compile("[​-‏‪-‮⁠-⁩﻿­]")
MAX_VOICE_MB = 20


def normalize(text):
    """Zero-width/bidi belgilarini olib tashlash, NFC, boshqaruv belgilarisiz (hamroh input_normalizer g'oyasi)."""
    text = _YASHIRIN.sub("", unicodedata.normalize("NFC", text or ""))
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C").strip()


def _xml_attr(v):
    return esc(str(v or "")).replace('"', "&quot;")


class TgPublisher:
    def __init__(self, chat_id, reply_to=None):
        self.chat_id, self.reply_to = chat_id, reply_to
        self.last_typing = 0.0
        self.takliflar = []
        self.xabarlar = []

    def text(self, chunk, kind="text"):
        pass

    def flush(self):
        pass

    def vazifa(self, tid, t):
        self.takliflar.append((tid, t))

    def xabar(self, tid, t):
        self.xabarlar.append((tid, t))

    def send(self, type_, **data):
        if type_ in ("status", "tool_start", "tool_run") and time.monotonic() - self.last_typing > 4:
            self.last_typing = time.monotonic()
            typing(self.chat_id)
        elif type_ == "file":
            f = data.get("file") or {}
            try:
                doc = frappe.get_doc("File", f.get("name"))
                send_document(self.chat_id, doc.get_content(), doc.file_name)
            except Exception:
                frappe.log_error(title="Nazorat AI: fayl yuborilmadi")
        elif type_ == "done":
            self._javob(data.get("text") or "", data.get("error"))

    def _javob(self, text, error):
        html = md_to_html(text) if text else ""
        if error:
            html += f"\n\n⚠️ <i>{esc(error)}</i>"
        if not html.strip():
            html = "Javob tayyorlab bo'lmadi."
        rows = [[{"text": f"✅ Yaratish: {t['sarlavha'][:28]} → {t['masul_nomi'][:16]}", "callback_data": f"vzt:{tid}"}]
                for tid, t in self.takliflar[:5]]
        for tid, t in self.xabarlar[:5]:
            html += f"\n\n<b>{esc(t['kimga_nomi'])}ga xabar:</b>\n<blockquote>{esc(t['matn'])}</blockquote>"
            rows.append([{"text": f"✅ Yuborish → {t['kimga_nomi'][:24]}", "callback_data": f"xbt:{tid}"}])
        kb = {"inline_keyboard": rows} if rows else None
        try:
            send_message(self.chat_id, html, reply_markup=kb, reply_to=self.reply_to)
        except TgXato as e:
            if "parse" in str(e).lower() or "entit" in str(e).lower():
                send_message(self.chat_id, esc(text or error or ""), reply_markup=kb, reply_to=self.reply_to)
            else:
                raise


def _limit_xato(azo):
    from pokiza.ai.client import get_settings, month_spent_usd

    s = get_settings()
    if not s.enabled:
        return "Pokiza AI o'chirilgan."
    if s.monthly_limit_usd and month_spent_usd() >= s.monthly_limit_usd:
        return "Oylik AI limiti tugadi. Administratorga murojaat qiling."
    b = frappe.get_cached_doc(config.DOCTYPE)
    kunlik = int(b.ai_kunlik_limit or 40)
    n = frappe.db.sql(
        """SELECT COUNT(*) FROM `tabAI Xabar` x JOIN `tabAI Suhbat` s ON s.name = x.suhbat
        WHERE s.kanal = 'Telegram' AND s.user = %s AND x.role = 'user' AND x.creation >= CURDATE()""", azo.user)[0][0]
    if n >= kunlik:
        return f"Bugungi savollar limiti ({kunlik}) tugadi."
    return None


def _ovoz(msg):
    """Ovozli xabar -> private File (joriy foydalanuvchi nomidan). [file_name] yoki []."""
    v = msg.get("voice") or msg.get("audio")
    if not v:
        return []
    if (v.get("file_size") or 0) > MAX_VOICE_MB * 1024 * 1024:
        raise frappe.ValidationError("Ovozli xabar juda katta")
    f = call("getFile", {"file_id": v["file_id"]})
    r = requests.get(f"https://api.telegram.org/file/bot{config.token()}/{f['file_path']}", timeout=60)
    r.raise_for_status()
    from pokiza.ai.attachments import save_upload

    ext = ".ogg" if msg.get("voice") else ("." + (f["file_path"].rsplit(".", 1)[-1] if "." in f["file_path"] else "mp3"))
    info = save_upload(f"telegram_ovoz{ext}", r.content, v.get("duration"))
    return [info["name"]]


def savol(msg, azo, bolim, matn=None):
    """Shaxsiy chatdagi savolni navbatga qo'yadi (javob shu chatga)."""
    from pokiza.ai.api import _create_messages

    chat_id = msg["chat"]["id"]
    reply_to = None
    xato = _limit_xato(azo)
    if xato:
        return send_message(chat_id, xato, reply_to=reply_to)

    frappe.set_user(azo.user)
    matn = normalize(matn if matn is not None else (msg.get("text") or msg.get("caption") or ""))
    try:
        files = _ovoz(msg)
    except (TgXato, requests.RequestException, frappe.ValidationError) as e:
        return send_message(chat_id, f"Ovozni olib bo'lmadi: {esc(str(e))}", reply_to=reply_to)
    if not matn and not files:
        return send_message(chat_id, "Savolni yozing yoki ovozli xabar yuboring.", reply_to=reply_to)

    kontekst = [f'<kanal turi="telegram" doira="{_xml_attr(bolim)} bo\'limi"/>']
    rep = msg.get("reply_to_message")
    if rep and not (rep.get("from") or {}).get("is_bot") and (rep.get("text") or rep.get("caption")):
        kontekst.append(f'<reply_to from="{_xml_attr((rep.get("from") or {}).get("first_name"))}">'
                        f'{esc(normalize(rep.get("text") or rep.get("caption"))[:1500])}</reply_to>')
    savol_matni = "\n".join(kontekst) + "\n\n" + (matn or "")

    suhbat = frappe.get_all("AI Suhbat", filters={"user": azo.user, "kanal": "Telegram", "tg_chat": str(chat_id),
                                                  "bolim": bolim,  # rol o'zgarsa — yangi suhbat (eski doira qolmasin)
                                                  "last_message_at": [">", add_to_date(now_datetime(), hours=-3)]},
                            order_by="last_message_at desc", pluck="name", limit=1)
    if suhbat and _band(suhbat[0]):
        # oldingi javob tayyorlanmoqda — savol yo'qolmasin: navbatga, javobdan keyin o'zi ishlanadi
        if frappe.cache.llen(_nkey(suhbat[0])) >= 5:
            return send_message(chat_id, "Oldingi savollarga javob tayyorlanmoqda, biroz kuting.", reply_to=reply_to)
        frappe.cache.rpush(_nkey(suhbat[0]), json.dumps({"msg": msg, "matn": matn}, default=str))
        return send_message(chat_id, "Navbatga qo'ydim — oldingi javobdan keyin javob beraman.", reply_to=reply_to)
    try:
        suhbat, _ux, xabar = _create_messages(savol_matni, suhbat[0] if suhbat else None, files)
    except frappe.ValidationError as e:
        frappe.db.rollback()
        return send_message(chat_id, esc(str(e)), reply_to=reply_to)
    frappe.db.set_value("AI Suhbat", suhbat, {"kanal": "Telegram", "tg_chat": str(chat_id), "bolim": bolim})
    frappe.db.commit()
    typing(chat_id)
    frappe.enqueue("pokiza.nazorat.ai_channel.run_job", queue="long", timeout=900, enqueue_after_commit=True,
                   suhbat=suhbat, xabar=xabar, chat_id=chat_id, bolim=bolim, reply_to=reply_to, user=azo.user,
                   vazifa_berish=_vazifa_berish(bolim))


def _nkey(suhbat):
    return f"nz_ai_navbat:{suhbat}"  # RedisWrapper list metodlari kalitni o'zi make_key qiladi


def _band(suhbat):
    from frappe.utils import get_datetime

    status, modified = frappe.db.get_value("AI Suhbat", suhbat, ["status", "modified"])
    return status == "Ishlayapti" and get_datetime(modified) > add_to_date(now_datetime(), minutes=-15)


def run_job(suhbat, xabar, chat_id, bolim, reply_to, user, vazifa_berish=None, **_eski):
    from pokiza.ai.agent import run

    frappe.set_user(user)
    pub = TgPublisher(chat_id, reply_to)
    if vazifa_berish is None:
        vazifa_berish = _vazifa_berish(bolim)
    tools = ai_tools(bolim)
    if vazifa_berish and tools is not None:
        tools = set(tools) | {"vazifa_taklif", "xabar_yubor"}
    try:
        run(suhbat, xabar, publisher=pub,
            kontekst={"kanal": "telegram", "bolim": bolim, "tools": tools, "on_vazifa": pub.vazifa,
                      "on_xabar": pub.xabar, "vazifa_berish": bool(vazifa_berish)})
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Nazorat AI: javob tayyorlanmadi")
        frappe.db.set_value("AI Suhbat", suhbat, "status", "Tayyor")
        frappe.db.commit()
        try:
            send_message(chat_id, "Javob bera olmadim, savolni qayta yozing.", reply_to=reply_to)
        except TgXato:
            pass
    _navbatdagi(suhbat, user)


def _navbatdagi(suhbat, user):
    """Navbatda kutgan savol bo'lsa — endi ishlanadi."""
    raw = frappe.cache.lpop(_nkey(suhbat))
    if not raw:
        return
    d = json.loads(raw)
    azo = frappe.db.get_value("TG Azo", user, "name") and frappe.get_doc("TG Azo", user)
    if not azo or not azo.faol:
        return
    from pokiza.nazorat.scope import azo_bolimi

    if d.get("rejim") == "guruh":
        return  # eski (guruh) navbat yozuvi — endi ishlanmaydi
    savol(d["msg"], azo, azo_bolimi(azo), matn=d.get("matn"))

