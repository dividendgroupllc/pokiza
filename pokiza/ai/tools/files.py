"""AI so'ragan Excel/PDF hisobot fayllari.

Aniqlik uchun jadval ma'lumoti AI orqali ko'chirilmaydi: har jadval manbasi (SQL yoki report)
server tomonda to'g'ridan-to'g'ri bazadan olinadi. `rows` manbasi faqat kichik, AI o'zi tuzgan
jadvallar uchun (masalan, bir nechta tool natijasidan yig'ilgan qisqa xulosa).
"""
import datetime
import io
import json
import re
from decimal import Decimal

import frappe
from frappe.utils import escape_html, format_datetime, get_fullname, md_to_html, now_datetime, strip_html

from pokiza.ai.tools import ToolError, parse_json_arg, tool

MAX_TABLES = 10
XLSX_MAX_ROWS = 20_000
PDF_MAX_ROWS = 3_000
ROWS_SOURCE_MAX = 500
NUMERIC_FIELDTYPES = {"Currency", "Float", "Percent", "Int"}


def context():
    ctx = getattr(frappe.local, "pokiza_ai", None)
    if not ctx:
        raise ToolError("Fayl faqat chat suhbati ichida yaratiladi")
    return ctx


# ---------- jadval ma'lumotini yig'ish ----------


def _clean(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, str) and "<" in v:
        return strip_html(v).strip()
    return v


def _load_table(t, max_rows):
    """{title, columns: [{label, fieldtype}], rows: [[...]], note, source_label}"""
    source = t.get("source")
    title = (t.get("title") or "Jadval").strip()[:120]

    if source == "sql":
        from pokiza.ai import sql_guard

        from pokiza.ai.client import get_settings

        if not get_settings().sql_enabled:
            raise ToolError("SQL o'chirilgan: report yoki rows manbasini ishlat")
        cols, rows, truncated = sql_guard.run_select(t.get("sql") or "", max_rows=max_rows)
        columns = [{"label": c, "fieldtype": None} for c in cols]
        data = [[_clean(r[c]) for c in cols] for r in rows]
        label = "SQL so'rov"
    elif source == "report":
        from pokiza.ai.tools.reports import execute_report

        cols, rows, filters, _msg = execute_report(t.get("report"), t.get("filters_json"))
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        columns = [{"label": c["label"], "fieldtype": c.get("fieldtype")} for c in cols]
        data = [[_clean(r.get(c["fieldname"])) for c in cols] for r in rows]
        period = " — ".join(str(filters[k]) for k in ("from_date", "to_date") if filters.get(k))
        label = f"Report: {t.get('report')}" + (f" ({period})" if period else "")
    elif source == "rows":
        cols = t.get("columns") or []
        rows = parse_json_arg(t.get("rows_json"), [], "rows_json")
        if not cols or not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
            raise ToolError(f"'{title}': rows manbasi uchun columns va rows_json (massivlar massivi) kerak")
        if len(rows) > ROWS_SOURCE_MAX:
            raise ToolError(f"'{title}': rows_json juda katta — katta jadval uchun sql yoki report manbasini ishlat")
        truncated = False
        columns = [{"label": str(c), "fieldtype": None} for c in cols]
        data = [[_clean(v) for v in (r + [None] * len(cols))[: len(cols)]] for r in rows]
        label = "AI hisob-kitobi (tool natijalaridan)"
    else:
        raise ToolError("source: sql, report yoki rows bo'lishi kerak")

    total_cols = [c for c in (t.get("total_columns") or []) if c in [x["label"] for x in columns]]
    return {
        "title": title,
        "columns": columns,
        "rows": data,
        "truncated": truncated,
        "source_label": label,
        "total_columns": total_cols,
    }


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _col_kind(col, values):
    ft = col.get("fieldtype")
    if ft in ("Int",):
        return "int"
    if ft in NUMERIC_FIELDTYPES:
        return "float"
    if ft in ("Date",):
        return "date"
    vals = [v for v in values if v not in (None, "")]
    if vals and all(_is_number(v) for v in vals):
        return "int" if all(float(v).is_integer() for v in vals) else "float"
    if vals and all(isinstance(v, (datetime.date, datetime.datetime)) for v in vals):
        return "date"
    return "text"


# ---------- Excel ----------


def _sheet_name(title, used):
    name = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "Varaq"
    base, i = name, 2
    while name.lower() in used:
        suffix = f" ({i})"
        name = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(name.lower())
    return name


def _text_cell(cell):
    """Bazadagi '=...' matn Excel'da formula bo'lib ishlab ketmasin (formula injection)."""
    if cell.data_type == "f":
        cell.data_type = "s"
    return cell


def build_xlsx(title, summary, tables):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    head_fill = PatternFill("solid", fgColor="E6F0EF")
    thin = Side(style="thin", color="C9D3D2")
    stamp = f"Tayyorlandi: {format_datetime(now_datetime(), 'dd.MM.yyyy HH:mm')} · {get_fullname()}"

    if summary:
        ws = wb.create_sheet(_sheet_name("Izoh", used))
        ws["A1"] = title
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = stamp
        ws["A2"].font = Font(color="667085", size=9)
        for i, line in enumerate(summary.splitlines(), start=4):
            _text_cell(ws.cell(row=i, column=1, value=line.replace("**", "")))
        ws.column_dimensions["A"].width = 110

    for t in tables:
        ws = wb.create_sheet(_sheet_name(t["title"], used))
        ws["A1"] = t["title"]
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = f"{t['source_label']} · {stamp}"
        ws["A2"].font = Font(color="667085", size=9)
        if t["truncated"]:
            ws["A3"] = f"Diqqat: faqat birinchi {len(t['rows'])} qator"
            ws["A3"].font = Font(color="B42318", size=9)

        hr = 4
        kinds = [_col_kind(c, [r[i] for r in t["rows"]]) for i, c in enumerate(t["columns"])]
        for ci, c in enumerate(t["columns"], start=1):
            cell = ws.cell(row=hr, column=ci, value=c["label"])
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(vertical="center", wrap_text=True)

        fmt = {"int": "#,##0", "float": "#,##0.00", "date": "DD.MM.YYYY"}
        for ri, row in enumerate(t["rows"], start=hr + 1):
            for ci, v in enumerate(row, start=1):
                cell = _text_cell(ws.cell(row=ri, column=ci, value=v))
                if kinds[ci - 1] in fmt and v not in (None, ""):
                    cell.number_format = fmt[kinds[ci - 1]]

        last = hr + len(t["rows"])
        if t["total_columns"] and t["rows"]:
            tr = last + 1
            ws.cell(row=tr, column=1, value="Jami").font = Font(bold=True)
            for ci, c in enumerate(t["columns"], start=1):
                if c["label"] in t["total_columns"]:
                    L = get_column_letter(ci)
                    cell = ws.cell(row=tr, column=ci, value=f"=SUM({L}{hr + 1}:{L}{last})")
                    cell.font = Font(bold=True)
                    cell.number_format = fmt["int"] if kinds[ci - 1] == "int" else fmt["float"]
                    cell.border = Border(top=thin)

        for ci, c in enumerate(t["columns"], start=1):
            sample = [c["label"]] + [r[ci - 1] for r in t["rows"][:300]]
            width = max(len(f"{v:,.2f}" if _is_number(v) else str(v or "")) for v in sample)
            ws.column_dimensions[get_column_letter(ci)].width = min(max(width + 2, 8), 50)
        ws.freeze_panes = ws.cell(row=hr + 1, column=1)
        if t["rows"]:
            ws.auto_filter.ref = f"A{hr}:{get_column_letter(len(t['columns']))}{last}"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------- PDF ----------


def _fmt_num(v, kind):
    if kind == "int":
        return f"{v:,.0f}".replace(",", " ")
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return s


def _fmt_cell(v, kind):
    if v in (None, ""):
        return ""
    if _is_number(v) and kind in ("int", "float"):
        return _fmt_num(v, kind)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.strftime("%d.%m.%Y")
    return escape_html(str(v))


PDF_CSS = """
@page { size: A4 %(orientation)s; margin: 14mm 12mm 16mm;
  @bottom-left { content: "Pokiza AI · %(stamp)s"; font-family: %(font)s; font-size: 7.5pt; color: #8a9696; }
  @bottom-right { content: counter(page) " / " counter(pages); font-family: %(font)s; font-size: 7.5pt; color: #8a9696; } }
body { font-family: %(font)s; font-size: 9pt; color: #17201f; }
h1 { font-size: 16pt; margin: 0 0 2pt; color: #0b4f4a; }
.stamp { color: #667372; font-size: 8pt; margin-bottom: 12pt; }
.summary { margin-bottom: 10pt; line-height: 1.45; }
.summary p { margin: 0 0 5pt; }
h2 { font-size: 11pt; margin: 14pt 0 2pt; color: #17201f; }
.src { font-size: 7.5pt; color: #667372; margin-bottom: 5pt; }
.warn { color: #b42318; }
table { border-collapse: collapse; width: 100%%; }
th { background: #e6f0ef; text-align: left; font-weight: 600; padding: 4pt 5pt; border-bottom: 1pt solid #9fb6b3; }
td { padding: 3pt 5pt; border-bottom: 0.5pt solid #dde5e4; vertical-align: top; }
td.n, th.n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; border-top: 1pt solid #9fb6b3; border-bottom: 0; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
"""


def build_pdf(title, summary, tables):
    from weasyprint import HTML

    stamp = f"{format_datetime(now_datetime(), 'dd.MM.yyyy HH:mm')} · {get_fullname()}"
    wide = any(len(t["columns"]) > 6 for t in tables)
    parts = [
        f"<h1>{escape_html(title)}</h1>",
        f"<div class='stamp'>Tayyorlandi: {escape_html(stamp)}</div>",
    ]
    if summary:
        parts.append(f"<div class='summary'>{md_to_html(summary) or ''}</div>")
    for t in tables:
        kinds = [_col_kind(c, [r[i] for r in t["rows"]]) for i, c in enumerate(t["columns"])]
        num = ["n" if k in ("int", "float") else "" for k in kinds]
        parts.append(f"<h2>{escape_html(t['title'])}</h2>")
        warn = f" · <span class='warn'>faqat birinchi {len(t['rows'])} qator</span>" if t["truncated"] else ""
        parts.append(f"<div class='src'>{escape_html(t['source_label'])}{warn}</div>")
        head = "".join(f"<th class='{num[i]}'>{escape_html(c['label'])}</th>" for i, c in enumerate(t["columns"]))
        body = "".join(
            "<tr>" + "".join(f"<td class='{num[i]}'>{_fmt_cell(v, kinds[i])}</td>" for i, v in enumerate(r)) + "</tr>"
            for r in t["rows"]
        )
        if t["total_columns"] and t["rows"]:
            cells = []
            for i, c in enumerate(t["columns"]):
                if c["label"] in t["total_columns"]:
                    s = sum(v for v in (r[i] for r in t["rows"]) if _is_number(v))
                    cells.append(f"<td class='n'>{_fmt_num(s, kinds[i] if kinds[i] in ('int', 'float') else 'float')}</td>")
                else:
                    cells.append("<td>Jami</td>" if i == 0 else "<td></td>")
            body += "<tr class='total'>" + "".join(cells) + "</tr>"
        parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")

    css = PDF_CSS % {
        "orientation": "landscape" if wide else "portrait",
        "stamp": stamp.replace('"', "'"),
        "font": '"Noto Sans", "DejaVu Sans", "Liberation Sans", Arial, sans-serif',
    }
    html = f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(parts)}</body></html>"

    def no_fetch(url, *args, **kwargs):
        # AI yozgan matn orqali tashqi/lokal resurslarni o'qishga yo'l qo'ymaymiz
        raise ValueError("tashqi resurslar o'chirilgan")

    return HTML(string=html, url_fetcher=no_fetch).write_pdf()


# ---------- tool ----------


def _file_name(title, ext):
    slug = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip().replace(" ", "_")[:80] or "hisobot"
    return f"{slug}_{now_datetime():%Y%m%d_%H%M}.{ext}"


def create_file(format, title, tables, summary_markdown=None):
    ctx = context()
    if not tables and not summary_markdown:
        raise ToolError("Kamida bitta jadval yoki summary_markdown kerak")
    if len(tables) > MAX_TABLES:
        raise ToolError(f"Ko'pi bilan {MAX_TABLES} ta jadval")
    title = (title or "Hisobot").strip()[:140]
    max_rows = XLSX_MAX_ROWS if format == "xlsx" else PDF_MAX_ROWS

    loaded = []
    for t in tables:
        if not isinstance(t, dict):
            raise ToolError("tables elementi obyekt bo'lishi kerak")
        try:
            loaded.append(_load_table(t, max_rows))
        except ToolError as e:
            raise ToolError(f"'{t.get('title')}' jadvali: {e}")

    if format == "xlsx":
        content = build_xlsx(title, summary_markdown, loaded)
    elif format == "pdf":
        content = build_pdf(title, summary_markdown, loaded)
    else:
        raise ToolError("format: xlsx yoki pdf")

    doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": _file_name(title, format),
            "content": content,
            "is_private": 1,
            "attached_to_doctype": "AI Suhbat",
            "attached_to_name": ctx["suhbat"],
        }
    ).insert(ignore_permissions=True)
    # run_tool oxirida rollback qiladi — fayl yozuvi saqlanib qolishi uchun shu yerda commit
    frappe.db.commit()

    from pokiza.ai.attachments import file_info

    info = {**file_info(doc), "kind": format, "title": title}
    ctx["files"].append(info)
    if ctx.get("on_file"):
        ctx["on_file"](info)

    return {
        "file_name": doc.file_name,
        "format": format,
        "tables": [
            {"title": t["title"], "rows": len(t["rows"]), "columns": [c["label"] for c in t["columns"]], "truncated": t["truncated"]}
            for t in loaded
        ],
        "note": "Fayl tayyor va foydalanuvchiga yuklab olish tugmasi bilan ko'rsatildi. "
        "Javobda havola yozma; faylda nima borligini 1-2 jumlada ayt.",
    }


TABLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Jadval/varaq sarlavhasi"},
        "source": {
            "type": "string",
            "enum": ["sql", "report", "rows"],
            "description": "sql/report — ma'lumot server tomonda bazadan olinadi (afzal). rows — faqat kichik, o'zing tuzgan jadval",
        },
        "sql": {"type": "string", "description": "source=sql: SELECT so'rov (sql_query qoidalari bilan, LIMIT shart emas, max 20 000 qator)"},
        "report": {"type": "string", "description": "source=report: run_report'dagi report nomi"},
        "filters_json": {"type": "string", "description": "source=report: filtrlar JSON obyekti"},
        "columns": {"type": "array", "items": {"type": "string"}, "description": "source=rows: ustun nomlari"},
        "rows_json": {"type": "string", "description": "source=rows: JSON massivlar massivi, [[\"A\", 12.5], ...], max 500 qator"},
        "total_columns": {"type": "array", "items": {"type": "string"}, "description": "Jami qatorida yig'iladigan ustun nomlari"},
    },
    "required": ["title", "source"],
    "additionalProperties": False,
}

TOOLS = [
    (
        tool(
            "create_file",
            "Foydalanuvchi Excel yoki PDF hisobot so'rasa — yuklab olinadigan fayl yaratadi. "
            "Jadval ma'lumotini o'zing ko'chirib yozma: source=sql yoki source=report ber, server ma'lumotni "
            "bazadan to'g'ridan-to'g'ri oladi (raqamlar aniq bo'ladi). Avval sql_query/run_report bilan natijani "
            "tekshirib ol, keyin xuddi shu so'rovni shu yerga ber. SQL ustun nomlarini o'zbekcha qil "
            "(AS `Mijoz`). Pul ustunlari uchun total_columns ber.",
            {
                "format": {"type": "string", "enum": ["xlsx", "pdf"]},
                "title": {"type": "string", "description": "Hisobot sarlavhasi, masalan 'Oktyabr 2026 sotuvi mijozlar bo'yicha'"},
                "summary_markdown": {"type": "string", "description": "Fayl boshidagi qisqa izoh/xulosa (markdown). Raqamlar faqat tool natijasidan"},
                "tables": {"type": "array", "items": TABLE_SCHEMA},
            },
            ["format", "title", "tables"],
            strict=False,
        ),
        create_file,
    ),
]
