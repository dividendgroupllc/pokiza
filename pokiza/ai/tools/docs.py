"""DocType sxemasi va yozuvlarni o'qish (Frappe permission bilan)."""
import json
import re

import frappe

from pokiza.ai.tools import DENY_DOCTYPES, MAX_ROWS, ToolError, check_doctype, parse_json_arg, rows_payload, tool

LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading", "Image"}
SECRET = {"Password"}


def search_doctypes(query):
    rows = frappe.db.sql(
        """SELECT name, module, istable, issingle FROM `tabDocType`
        WHERE name LIKE %(q)s ORDER BY istable, name LIMIT 50""",
        {"q": f"%{query}%"},
        as_dict=True,
    )
    return [r for r in rows if r.name not in DENY_DOCTYPES]


def describe_doctype(doctype):
    check_doctype(doctype)
    meta = frappe.get_meta(doctype)
    fields = []
    for df in meta.fields:
        if df.fieldtype in LAYOUT or df.fieldtype in SECRET:
            continue
        f = {"fieldname": df.fieldname, "type": df.fieldtype, "label": df.label}
        if df.fieldtype in ("Link", "Dynamic Link", "Table", "Table MultiSelect", "Select") and df.options:
            f["options"] = df.options[:200]
        fields.append(f)
    return {
        "doctype": doctype,
        "table": f"tab{doctype}",
        "is_child_table": meta.istable,
        "is_submittable": meta.is_submittable,
        "standard_columns": "name, owner, creation, modified, docstatus"
        + (", parent, parenttype, parentfield, idx" if meta.istable else ""),
        "fields": fields,
    }


def _clean(doctype, row):
    meta = frappe.get_meta(doctype)
    secret = {df.fieldname for df in meta.fields if df.fieldtype in SECRET}
    return {k: v for k, v in row.items() if k not in secret and v not in (None, "")}


def _no_foreign_tables(*parts):
    """fields/filters/order_by orqali yopiq jadvalga (`tabUser`.api_key kabi) murojaatni bloklaydi."""
    text = json.dumps(parts, ensure_ascii=False)
    for name in re.findall(r"tab([A-Za-z][\w ]*?)`", text) + re.findall(r"\[\s*\"([^\"]+)\"\s*,\s*\"[^\"]+\"\s*,", text):
        if name.strip() in DENY_DOCTYPES:
            raise ToolError(f"'{name}' ma'lumotiga ruxsat yo'q")
    if "__" in text.replace("__note", ""):
        raise ToolError("Tizim jadvallariga ruxsat yo'q")


def list_records(doctype, filters_json=None, fields=None, order_by=None, limit=None):
    check_doctype(doctype)
    filters = parse_json_arg(filters_json, {}, "filters_json")
    _no_foreign_tables(fields, filters, order_by)
    limit = min(int(limit or 50), MAX_ROWS)
    rows = frappe.get_list(
        doctype,
        filters=filters,
        fields=fields or ["name"],
        order_by=order_by or f"`tab{doctype}`.creation desc",
        limit_page_length=limit,
    )
    return rows_payload([_clean(doctype, r) for r in rows])


def get_record(doctype, name):
    check_doctype(doctype)
    if not frappe.db.exists(doctype, name):
        raise ToolError(f"{doctype} '{name}' topilmadi")
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    data = doc.as_dict(no_default_fields=False)
    out = {}
    meta = frappe.get_meta(doctype)
    for k, v in data.items():
        df = meta.get_field(k)
        if df and df.fieldtype in SECRET:
            continue
        if isinstance(v, list):
            child = df.options if df else None
            out[k] = [_clean(child, c) if child else c for c in v[:100]]
            if len(v) > 100:
                out[k + "__note"] = f"{len(v)} qatordan 100 tasi"
        elif v not in (None, ""):
            out[k] = v
    return out


TOOLS = [
    (
        tool(
            "search_doctypes",
            "DocType (jadval) nomini qidiradi. Qaysi jadvalda ma'lumot borligini bilmasang ishlat.",
            {"query": {"type": "string", "description": "Nomning bir qismi, masalan 'Invoice' yoki 'Kassa'"}},
            ["query"],
        ),
        search_doctypes,
    ),
    (
        tool(
            "describe_doctype",
            "DocType maydonlarini (fieldname, turi, label, link) qaytaradi. SQL yozishdan oldin ishlat.",
            {"doctype": {"type": "string", "description": "Masalan 'Sales Invoice'"}},
            ["doctype"],
        ),
        describe_doctype,
    ),
    (
        tool(
            "list_records",
            "Frappe get_list orqali yozuvlar ro'yxati (foydalanuvchi ruxsati bilan). Oddiy ro'yxat va "
            "filtrlash uchun. Agregatsiya (SUM, GROUP BY) uchun sql_query ishlat.",
            {
                "doctype": {"type": "string"},
                "filters_json": {
                    "type": "string",
                    "description": 'Frappe filtrlari JSON: {"customer": "X", "docstatus": 1} yoki '
                    '[["posting_date", ">=", "2026-10-01"]]',
                },
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Maydonlar ro'yxati"},
                "order_by": {"type": "string", "description": "Masalan 'posting_date desc'"},
                "limit": {"type": "integer", "description": "Max 200, standart 50"},
            },
            ["doctype"],
        ),
        list_records,
    ),
    (
        tool(
            "get_record",
            "Bitta hujjatni to'liq (child jadvallari bilan) qaytaradi.",
            {"doctype": {"type": "string"}, "name": {"type": "string"}},
            ["doctype", "name"],
        ),
        get_record,
    ),
]
