"""Foydalanuvchi yuborgan fayllar: rasm, PDF, Excel/CSV.

Fayl Frappe'da private File sifatida saqlanadi. Suhbat tarixida (content_json) faqat belgi turadi:
{"type": "pokiza_file", "file": "<File name>"} — Claude'ga yuborishdan oldin `expand_content` uni
haqiqiy blokka aylantiradi (rasm/PDF base64, jadval matn). Shu tufayli bazada base64 saqlanmaydi.
"""
import base64
import csv
import io
import os

import frappe

MAX_UPLOAD_MB = 20
MAX_FILES_PER_MESSAGE = 5
IMAGE_MAX_EDGE = 1568
SHEET_MAX_ROWS = 300
SHEET_MAX_COLS = 40
SHEET_MAX_CHARS = 60_000

MAX_AUDIO_MB = 14

AUDIO_MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",  # Telegram ovozli xabarlari: Ogg konteyneridagi Opus
    ".mp3": "audio/mp3",
    ".m4a": "audio/m4a",
    ".mp4": "audio/m4a",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}

KINDS = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".gif": "image",
    ".pdf": "pdf",
    ".xlsx": "sheet", ".xls": "sheet", ".csv": "sheet",
    **{ext: "audio" for ext in AUDIO_MIME},
}
IMAGE_MEDIA = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}


def kind_of(file_name):
    return KINDS.get(os.path.splitext(file_name or "")[1].lower())


def _duration_key(name):
    return f"pokiza_ai_audio_dur:{name}"


def file_info(doc):
    info = {
        "name": doc.name,
        "file_name": doc.file_name,
        "file_url": doc.file_url,
        "kind": kind_of(doc.file_name) or "file",
        "size": doc.file_size,
    }
    if info["kind"] == "audio":
        # brauzer yozgan webm'da davomiylik metadata'si bo'lmaydi — yuklashda kelgan qiymat
        info["duration"] = frappe.cache.get_value(_duration_key(doc.name))
    return info


def _shrink_image(content):
    """Rasmni Claude uchun qulay o'lchamga keltiradi (uzun tomoni <= 1568px)."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Exception:
        frappe.throw("Rasmni o'qib bo'lmadi. JPG, PNG yoki WEBP yuboring.")
    img = ImageOps.exif_transpose(img)
    if max(img.size) > IMAGE_MAX_EDGE:
        img.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE))
    out = io.BytesIO()
    has_alpha = img.mode in ("RGBA", "LA", "P")
    if has_alpha:
        img.save(out, "PNG", optimize=True)
        if out.tell() <= 3 * 1024 * 1024:
            return out.getvalue(), ".png"
        out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue(), ".jpg"


def save_upload(file_name, content, duration=None):
    kind = kind_of(file_name)
    if not kind:
        frappe.throw("Bu turdagi fayl qabul qilinmaydi. Rasm, PDF, Excel/CSV yoki ovozli xabar yuboring.")
    if kind == "audio" and len(content) > MAX_AUDIO_MB * 1024 * 1024:
        frappe.throw(f"Ovozli xabar juda katta (max {MAX_AUDIO_MB} MB)")
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw(f"Fayl juda katta (max {MAX_UPLOAD_MB} MB)")
    if not content:
        frappe.throw("Fayl bo'sh")

    if kind == "image":
        content, ext = _shrink_image(content)
        file_name = os.path.splitext(file_name)[0] + ext
    elif kind == "pdf" and not content.startswith(b"%PDF"):
        frappe.throw("Bu PDF fayl emas")

    doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "content": content,
            "is_private": 1,
            "folder": "Home/Attachments",
        }
    ).insert(ignore_permissions=True)
    if kind == "audio" and duration:
        try:
            frappe.cache.set_value(_duration_key(doc.name), round(min(float(duration), 3600), 1), expires_in_sec=30 * 86400)
        except ValueError:
            pass
    return file_info(doc)


def own_files(names):
    """Faqat joriy foydalanuvchi yuklagan, qo'llab-quvvatlanadigan fayllar."""
    if not names:
        return []
    if len(names) > MAX_FILES_PER_MESSAGE:
        frappe.throw(f"Bitta xabarga ko'pi bilan {MAX_FILES_PER_MESSAGE} ta fayl")
    docs = []
    for name in names:
        doc = frappe.db.get_value(
            "File", name, ["name", "file_name", "file_url", "file_size", "owner"], as_dict=True
        )
        if not doc or doc.owner != frappe.session.user or not kind_of(doc.file_name):
            frappe.throw("Fayl topilmadi yoki sizga tegishli emas")
        docs.append(doc)
    return docs


# ---------- Claude bloklari ----------


def read_bytes(doc):
    """Fayl baytlari. File.get_content() matnga o'xshagan faylni str qilib qaytaradi — bizga doim bytes kerak."""
    doc.validate_file_path()
    with open(doc.get_full_path(), "rb") as f:
        return f.read()


def _read(name):
    doc = frappe.get_doc("File", name)
    return doc, read_bytes(doc)


def _image_block(content):
    from PIL import Image

    fmt = Image.open(io.BytesIO(content)).format
    media = IMAGE_MEDIA.get(fmt, "image/jpeg")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(content).decode()}}


def _pdf_block(content, title):
    return {
        "type": "document",
        "title": title,
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(content).decode()},
    }


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _sheets(file_name, content):
    """[(sheet_name, rows)] — har qator list."""
    ext = os.path.splitext(file_name)[1].lower()
    if ext == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        return [("CSV", list(csv.reader(io.StringIO(text))))]
    if ext == ".xls":
        import xlrd

        book = xlrd.open_workbook(file_contents=content)
        return [(s.name, [s.row_values(i) for i in range(min(s.nrows, SHEET_MAX_ROWS + 1))]) for s in book.sheets()]

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > SHEET_MAX_ROWS:
                break
            rows.append(list(row))
        out.append((ws.title, rows))
    wb.close()
    return out


def _sheet_block(file_name, content):
    parts = [f"Foydalanuvchi yuborgan jadval fayli: {file_name}"]
    for sheet, rows in _sheets(file_name, content):
        rows = [r[:SHEET_MAX_COLS] for r in rows if any(c not in (None, "") for c in r)]
        buf = io.StringIO()
        csv.writer(buf).writerows([[_cell(c) for c in r] for r in rows[:SHEET_MAX_ROWS]])
        note = f" (faqat birinchi {SHEET_MAX_ROWS} qator)" if len(rows) > SHEET_MAX_ROWS else ""
        parts.append(f"\n### Varaq: {sheet}{note}\n```csv\n{buf.getvalue()}```")
    text = "\n".join(parts)
    if len(text) > SHEET_MAX_CHARS:
        text = text[:SHEET_MAX_CHARS] + "\n… (fayl katta, qolgani kesildi)"
    return {"type": "text", "text": text}


def to_block(name):
    try:
        doc, content = _read(name)
    except Exception:
        return {"type": "text", "text": "(Biriktirilgan fayl o'chirilgan yoki topilmadi)"}
    kind = kind_of(doc.file_name)
    try:
        if kind == "image":
            return _image_block(content)
        if kind == "pdf":
            return _pdf_block(content, doc.file_name)
        if kind == "sheet":
            return _sheet_block(doc.file_name, content)
    except Exception:
        frappe.log_error(title="Pokiza AI: faylni o'qib bo'lmadi")
        return {"type": "text", "text": f"({doc.file_name} faylini o'qib bo'lmadi)"}
    return {"type": "text", "text": f"({doc.file_name}: qo'llab-quvvatlanmaydigan fayl)"}


def expand_content(content):
    """content_json'dagi pokiza_file belgilarini Claude bloklariga aylantiradi."""
    out = []
    for b in content:
        if b.get("type") == "pokiza_file":
            out.append(to_block(b["file"]))
        elif b.get("type") == "pokiza_audio":
            # odatda voice.prepare_voice allaqachon matnga almashtirgan bo'ladi
            out.append({"type": "text", "text": "(Ovozli xabarni matnga o'girib bo'lmadi)"})
        else:
            out.append(b)
    return out
