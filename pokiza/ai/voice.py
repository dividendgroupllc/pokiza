"""Ovozli xabar: audio -> matn (Google Gemini Interactions API), keyin Claude javob beradi.

Claude audio qabul qilmaydi. Shuning uchun agent ishga tushishidan oldin foydalanuvchi xabaridagi
{"type": "pokiza_audio", "file": ...} belgisi Gemini orqali matnga o'giriladi va content_json'da
oddiy matn blokiga almashtiriladi (bir marta, keyin tarix o'zgarmaydi).
"""
import base64
import json
import os
import time

import frappe
import requests

from pokiza.ai.attachments import AUDIO_MIME, MAX_AUDIO_MB, kind_of, read_bytes
from pokiza.ai.client import get_secret, get_settings

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
TIMEOUT_SEC = 90
RETRY_STATUS = {429, 500, 502, 503, 504}

# Sozlamadagi model band bo'lsa (503/429) — shu tartibda keyingisiga o'tiladi.
# 2026-11 da tekshirilgan: o'zbekcha nutqni aniq yozadi, nutqsiz audio'da so'z to'qimaydi.
FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash")
NO_SPEECH = "[NUTQ_YOQ]"

# Eslatma: oddiy "nutqni yoz" deyilsa, model jimlik/shovqindan o'zbekcha gap to'qib chiqargan —
# shuning uchun "nutq yo'q" uchun aniq belgi talab qilinadi.
PROMPT = (
    "Vazifa: audio'dagi inson nutqini so'zma-so'z matnga o'girish (transkripsiya).\n"
    f"MUHIM: agar audio'da aniq eshitiladigan inson nutqi bo'lmasa (jimlik, shovqin, signal/ton, musiqa) — "
    f"faqat {NO_SPEECH} deb yoz. Hech qachon so'z o'ylab topma va eshitilmagan narsani yozma.\n"
    "Nutq bo'lsa: til o'zbekcha, ruscha yoki aralash bo'lishi mumkin; o'zbekcha qismlarni lotin yozuvida, "
    "ruscha qismlarni kirill yozuvida yoz. Raqamlar, sanalar va summalarni raqam bilan yoz. "
    "Kompaniya, mijoz va mahsulot nomlarini eshitilganidek yoz. "
    "Faqat transkripsiyani qaytar: izoh, tarjima yoki qo'shtirnoqsiz."
)


class VoiceError(Exception):
    pass


def transcribe(content, mime):
    api_key = get_secret("gemini_api_key")
    if not api_key:
        raise VoiceError("Ovozli xabar uchun Gemini API key kiritilmagan (Pokiza AI Sozlamalari)")
    if len(content) > MAX_AUDIO_MB * 1024 * 1024:  # base64 bilan so'rov 20 MB dan oshmasligi uchun
        raise VoiceError(f"Ovozli xabar juda uzun (max {MAX_AUDIO_MB} MB)")

    models = list(dict.fromkeys([get_settings().gemini_model, *FALLBACK_MODELS]))
    audio = {"type": "audio", "data": base64.b64encode(content).decode(), "mime_type": mime}
    r = None
    # band (429/5xx) yoki topilmagan model (404) — darhol keyingi modelga; hammasi band bo'lsa kutib yana bir aylana
    for round_wait in (0, 4):
        time.sleep(round_wait)
        for model in models:
            try:
                r = requests.post(
                    API_URL,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json", "Api-Revision": API_REVISION},
                    data=json.dumps({"model": model, "input": [{"type": "text", "text": PROMPT}, audio]}),
                    timeout=TIMEOUT_SEC,
                )
            except requests.RequestException:
                r = None
                continue
            if r.status_code not in RETRY_STATUS and r.status_code != 404:
                break
        else:
            continue
        break
    if r is None:
        raise VoiceError("Gemini'ga ulanib bo'lmadi (internet yoki proxy)")
    if r.status_code in RETRY_STATUS or r.status_code == 404:
        raise VoiceError("Ovozni matnga o'giruvchi servis (Gemini) hozir band. Bir daqiqadan keyin \"Qayta urinish\"ni bosing.")
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text
        if r.status_code in (401, 403):
            raise VoiceError("Gemini API key noto'g'ri yoki ruxsat yo'q")
        raise VoiceError(f"Gemini xatosi {r.status_code}: {msg[:300]}")

    data = r.json()
    texts = [
        block.get("text", "")
        for step in data.get("steps") or []
        if step.get("type") == "model_output"
        for block in step.get("content") or []
        if block.get("type") == "text"
    ]
    text = "\n".join(t for t in texts if t).strip()
    return "" if NO_SPEECH in text or text.strip("[]. ") == "" else text


def _user_message_before(suhbat, xabar):
    creation = frappe.db.get_value("AI Xabar", xabar, "creation")
    rows = frappe.get_all(
        "AI Xabar",
        filters={"suhbat": suhbat, "role": "user", "creation": ["<=", creation]},
        fields=["name", "content_json", "files_json", "text"],
        order_by="creation desc",
        limit=1,
    )
    return rows[0] if rows else None


def prepare_voice(suhbat, xabar, publish):
    """Joriy savoldagi ovozli xabarlarni matnga o'giradi. Xato bo'lsa VoiceError."""
    row = _user_message_before(suhbat, xabar)
    if not row:
        return
    content = json.loads(row.content_json or "[]")
    if not any(b.get("type") == "pokiza_audio" for b in content):
        return

    files = json.loads(row.files_json or "[]")
    new_content, transcripts = [], []
    for b in content:
        if b.get("type") != "pokiza_audio":
            new_content.append(b)
            continue
        publish("status", text="Ovozli xabar tinglanmoqda…")
        doc = frappe.get_doc("File", b["file"])
        if kind_of(doc.file_name) != "audio":
            raise VoiceError("Audio fayl emas")
        mime = AUDIO_MIME.get(os.path.splitext(doc.file_name)[1].lower(), "audio/webm")
        text = transcribe(read_bytes(doc), mime)
        if not text:
            raise VoiceError("Ovozli xabarda nutq eshitilmadi. Qaytadan, aniqroq gapirib ko'ring.")
        transcripts.append(text)
        for f in files:
            if f.get("name") == doc.name:
                f["transcript"] = text
        publish("transcript", file=doc.name, text=text)
        new_content.append(
            {
                "type": "text",
                "text": "[Ovozli xabar — avtomatik matnga o'girilgan, so'z/raqamlarda xato bo'lishi mumkin]\n" + text,
            }
        )

    frappe.db.set_value(
        "AI Xabar",
        row.name,
        {"content_json": json.dumps(new_content, ensure_ascii=False), "files_json": json.dumps(files, ensure_ascii=False)},
        update_modified=False,
    )
    # sarlavha audio fayl nomidan olingan bo'lsa — ovozli xabar matni bilan almashtiramiz
    title = frappe.db.get_value("AI Suhbat", suhbat, "title")
    if transcripts and title in ["Ovozli xabar", *[f.get("file_name", "")[:80] for f in files]]:
        frappe.db.set_value("AI Suhbat", suhbat, "title", transcripts[0][:80])
    frappe.db.commit()
