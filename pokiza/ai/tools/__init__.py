"""Tool registry: Claude'ga beriladigan tool'lar va ularni bajarish."""
import json
import time
from decimal import Decimal

import frappe

MAX_RESULT_CHARS = 40_000
MAX_ROWS = 200

# AI hech qachon ko'rmasligi kerak bo'lgan doctype'lar
DENY_DOCTYPES = {
    "User", "Has Role", "User Permission", "Sessions", "OAuth Client", "OAuth Bearer Token",
    "OAuth Authorization Code", "Social Login Key", "Email Account", "Access Log", "Activity Log",
    "Error Log", "Integration Request", "Webhook", "Webhook Request Log", "System Settings",
    "Pokiza AI Sozlamalari", "AI Suhbat", "AI Xabar", "Telegram Bot Settings", "Telegram User",
    "Telegram Admin", "Connected App", "Token Cache", "LDAP Settings", "Dropbox Settings",
    "S3 Backup Settings", "Google Settings", "SMS Settings", "Payment Gateway Account",
}


class ToolError(Exception):
    """AI'ga tushunarli xabar bilan qaytariladigan xato."""


# Claude API: barcha strict tool'lardagi ixtiyoriy parametrlar jami <= 24 bo'lishi kerak.
STRICT_OPTIONAL_LIMIT = 24


def tool(name, description, properties, required=(), strict=True):
    """strict=False — ichma-ich murakkab sxemalar uchun (kirish qiymati funksiya ichida tekshiriladi)."""
    return {
        "name": name,
        "description": description,
        "strict": strict,
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


def check_doctype(doctype):
    if not doctype or doctype in DENY_DOCTYPES or not frappe.db.exists("DocType", doctype):
        raise ToolError(f"DocType '{doctype}' mavjud emas yoki ruxsat etilmagan")


def parse_json_arg(value, default, name):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except ValueError as e:
        raise ToolError(f"'{name}' to'g'ri JSON emas: {e}")


def rows_payload(rows, columns=None):
    total = len(rows)
    out = {"row_count": total}
    if columns is not None:
        out["columns"] = columns
    out["rows"] = rows[:MAX_ROWS]
    if total > MAX_ROWS:
        out["note"] = f"Faqat birinchi {MAX_ROWS} ta qator ko'rsatildi (jami {total}). Agregatsiya yoki filtr ishlat."
    return out


def _registry():
    from pokiza.ai.tools import business, dashboard, docs, files, production, reports, sql

    funcs = {}
    for mod in (docs, reports, business, production, sql, files, dashboard):
        for spec, func in mod.TOOLS:
            funcs[spec["name"]] = (spec, func)
    return funcs


def _optional_count(schema):
    n = 0
    req = set(schema.get("required", []))
    for k, v in schema.get("properties", {}).items():
        n += (k not in req) + _optional_count(v)
    if "items" in schema:
        n += _optional_count(schema["items"])
    return n


def tool_specs(sql_enabled=True):
    specs = [spec for spec, _ in _registry().values()]
    if not sql_enabled:
        specs = [s for s in specs if s["name"] != "sql_query"]
    optional = sum(_optional_count(s["input_schema"]) for s in specs if s["strict"])
    if optional > STRICT_OPTIONAL_LIMIT:
        # API 400 qaytarmasligi uchun: chegaradan oshsa strict'ni o'chirib yuboramiz va log yozamiz
        frappe.log_error(title="Pokiza AI: strict optional parametrlar limiti", message=f"{optional} > {STRICT_OPTIONAL_LIMIT}")
        specs = [{**s, "strict": False} for s in specs]
    return specs


def _validate(spec, args):
    schema = spec["input_schema"]
    if not isinstance(args, dict):
        raise ToolError("Tool input obyekt bo'lishi kerak")
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        raise ToolError(f"Majburiy parametrlar yo'q: {', '.join(missing)}")
    extra = [k for k in args if k not in schema["properties"]]
    if extra:
        raise ToolError(f"Noma'lum parametrlar: {', '.join(extra)}")
    pytypes = {"string": str, "integer": int, "boolean": bool, "number": (int, float), "array": list, "object": dict}
    for k, v in args.items():
        t = schema["properties"][k].get("type")
        if v is None or t is None:
            continue
        if isinstance(t, list):
            t = next((x for x in t if x != "null"), None)
        if t in pytypes and not isinstance(v, pytypes[t]):
            raise ToolError(f"'{k}' turi {t} bo'lishi kerak")


def _json(v):
    return json.dumps(v, ensure_ascii=False, default=lambda o: float(o) if isinstance(o, Decimal) else str(o))


def _fit(result):
    """Natijani JSON'ni buzmasdan MAX_RESULT_CHARS ichiga sig'diradi (qatorlarni qisqartirib)."""
    content = _json(result)
    rows = result.get("rows") if isinstance(result, dict) else None
    while len(content) > MAX_RESULT_CHARS and rows and len(rows) > 1:
        rows = rows[: len(rows) // 2]
        result = {**result, "rows": rows, "note": f"Natija katta: faqat birinchi {len(rows)} qator ko'rsatildi "
                  f"(jami {result.get('row_count')}). Filtr yoki agregatsiya (sql_query) ishlat."}
        content = _json(result)
    if len(content) > MAX_RESULT_CHARS:
        content = json.dumps({"error": "Natija juda katta", "preview": content[:2000]}, ensure_ascii=False)
    return content


# Faqat o'zi yaratgan natija faylini (private File) saqlaydigan tool. Qolganlari READ ONLY tranzaksiyada.
OWN_OUTPUT_TOOLS = {"create_file"}


def run_tool(name, args):
    """(content_str, is_error, audit) qaytaradi.

    Tool READ ONLY tranzaksiyada ishlaydi: biznes ma'lumotiga har qanday INSERT/UPDATE/DELETE
    MariaDB darajasida rad etiladi (tool ichida commit bo'lsa ham — begin() flag'ga qaraydi).
    """
    started = time.monotonic()
    entry = _registry().get(name)
    read_only = name not in OWN_OUTPUT_TOOLS
    try:
        if not entry:
            raise ToolError(f"Noma'lum tool: {name}")
        spec, func = entry
        _validate(spec, args)
        if read_only:
            frappe.db.rollback()
            frappe.flags.read_only = True
            frappe.db.begin(read_only=True)
        result = func(**args)
        content = _fit(result)
        is_error = False
    except ToolError as e:
        content, is_error = str(e), True
    except frappe.InReadOnlyMode:
        frappe.log_error(title=f"Pokiza AI: tool bazaga yozmoqchi bo'ldi: {name}")
        content, is_error = "Bu amal bazaga yozishni talab qiladi — AI faqat o'qiy oladi", True
    except frappe.PermissionError:
        content, is_error = "Ruxsat yo'q", True
    except Exception as e:
        frappe.log_error(title=f"Pokiza AI tool xatosi: {name}")
        content, is_error = f"Tool ichki xatosi: {type(e).__name__}: {str(e)[:500]}", True
    finally:
        # tool ichida tasodifan yozish bo'lsa ham saqlanmasin; keyin oddiy tranzaksiyaga qaytamiz
        frappe.db.rollback()
        if read_only:
            frappe.flags.read_only = False
            frappe.db.begin()
    audit = {
        "name": name,
        "input": args,
        "is_error": is_error,
        "ms": int((time.monotonic() - started) * 1000),
        "preview": content[:300],
    }
    return content, is_error, audit
