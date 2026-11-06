"""Chat ichidagi dashboard: KPI kartalari va grafiklar.

Aniqlik uchun KPI va grafik ma'lumoti server tomonda SQL/report'dan olinadi (files.py dagi
`_load_table` bilan bir xil manbalar). AI'ga esa qisqa xulosa qaytariladi — shu raqamlar asosida
u tahlil va tavsiya yozadi.
"""
import datetime

import frappe

from pokiza.ai.tools import ToolError, tool
from pokiza.ai.tools.files import TABLE_SCHEMA, _is_number, _load_table, context

MAX_KPIS = 6
MAX_CHARTS = 4
MAX_SERIES = 4
MAX_POINTS = 60
PART_SLICES = 7  # undan ko'pi "Boshqa"ga yig'iladi


def _sql_value(sql):
    from pokiza.ai import sql_guard
    from pokiza.ai.client import get_settings

    if not get_settings().sql_enabled:
        raise ToolError("SQL o'chirilgan: KPI uchun value ber (tool natijasidan)")
    cols, rows, _ = sql_guard.run_select(sql, max_rows=1)
    if not rows or not cols:
        return None
    v = rows[0][cols[0]]
    return float(v) if v is not None else None


def _kpi(k):
    label = (k.get("label") or "").strip()[:60]
    if not label:
        raise ToolError("KPI uchun label kerak")
    value = _sql_value(k["sql"]) if k.get("sql") else k.get("value")
    if value is not None and not _is_number(value):
        raise ToolError(f"KPI '{label}': value raqam bo'lishi kerak")
    prev = _sql_value(k["compare_sql"]) if k.get("compare_sql") else k.get("compare_value")
    delta = None
    if _is_number(value) and _is_number(prev) and prev:
        delta = round((value - prev) / abs(prev) * 100, 1)
    return {
        "label": label,
        "value": value,
        "unit": (k.get("unit") or "").strip()[:12],
        "compare_label": (k.get("compare_label") or "").strip()[:40] or None,
        "prev": prev,
        "delta_pct": delta,
        "good_when": k.get("good_when") or "up",
        "verified": bool(k.get("sql")),
    }


def _label(v):
    if isinstance(v, datetime.datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    if isinstance(v, datetime.date):
        return v.strftime("%d.%m.%Y")
    return "" if v is None else str(v)


def _chart(c):
    ctype = c.get("type")
    if ctype not in ("line", "bar", "share"):
        raise ToolError("type: line, bar yoki share")
    t = _load_table(c["data"], MAX_POINTS * 10)
    labels = [col["label"] for col in t["columns"]]
    x = c.get("x_column") or labels[0]
    ys = c.get("y_columns") or [l for l in labels if l != x][:1]
    missing = [n for n in [x, *ys] if n not in labels]
    if missing:
        raise ToolError(f"Ustun topilmadi: {', '.join(missing)}. Mavjud: {', '.join(labels)}")
    if len(ys) > MAX_SERIES:
        raise ToolError(f"Bitta grafikda ko'pi bilan {MAX_SERIES} ta qator (series). Ko'p bo'lsa — alohida grafik qil")
    xi, yi = labels.index(x), [labels.index(y) for y in ys]

    def num(v):
        return float(v) if _is_number(v) else 0.0

    rows = t["rows"]
    if ctype == "share":
        if len(ys) != 1:
            raise ToolError("share grafigi uchun bitta y ustuni")
        pairs = sorted(((_label(r[xi]), num(r[yi[0]])) for r in rows), key=lambda p: -p[1])
        pairs = [p for p in pairs if p[1] > 0]
        if len(pairs) > PART_SLICES + 1:
            rest = sum(v for _, v in pairs[PART_SLICES:])
            pairs = pairs[:PART_SLICES] + [("Boshqa", rest)]
        x_labels = [p[0] for p in pairs]
        datasets = [{"name": ys[0], "values": [round(p[1], 2) for p in pairs]}]
        truncated = False
    else:
        truncated = len(rows) > MAX_POINTS
        rows = rows[:MAX_POINTS]
        x_labels = [_label(r[xi]) for r in rows]
        datasets = [{"name": y, "values": [round(num(r[i]), 2) for r in rows]} for y, i in zip(ys, yi)]

    return {
        "title": (c.get("title") or t["title"])[:120],
        "type": ctype,
        "unit": (c.get("unit") or "").strip()[:12],
        "labels": x_labels,
        "datasets": datasets,
        "source_label": t["source_label"],
        "truncated": truncated or t["truncated"],
    }


def _summary(chart):
    """AI tahlil qilishi uchun ixcham raqamlar."""
    out = {"title": chart["title"], "points": len(chart["labels"])}
    for ds in chart["datasets"]:
        vals = ds["values"]
        if not vals:
            continue
        i_max, i_min = vals.index(max(vals)), vals.index(min(vals))
        s = {
            "jami": round(sum(vals), 2),
            "max": [chart["labels"][i_max], vals[i_max]],
            "min": [chart["labels"][i_min], vals[i_min]],
            "birinchi": [chart["labels"][0], vals[0]],
            "oxirgi": [chart["labels"][-1], vals[-1]],
        }
        if len(vals) <= 24:
            s["qiymatlar"] = dict(zip(chart["labels"], vals))
        out[ds["name"]] = s
    if chart["truncated"]:
        out["note"] = f"Faqat birinchi {len(chart['labels'])} nuqta ko'rsatildi"
    return out


def show_dashboard(title, kpis=None, charts=None):
    ctx = context()
    kpis, charts = kpis or [], charts or []
    if not all(isinstance(x, dict) for x in [*kpis, *charts]) or not all(isinstance(c.get("data"), dict) for c in charts):
        raise ToolError("kpis va charts elementlari obyekt bo'lishi kerak (charts[].data ham obyekt)")
    if not kpis and not charts:
        raise ToolError("Kamida bitta KPI yoki grafik kerak")
    if len(kpis) > MAX_KPIS or len(charts) > MAX_CHARTS:
        raise ToolError(f"Ko'pi bilan {MAX_KPIS} KPI va {MAX_CHARTS} grafik")

    built_kpis = []
    for k in kpis:
        try:
            built_kpis.append(_kpi(k))
        except ToolError as e:
            raise ToolError(f"KPI '{k.get('label')}': {e}")
    built_charts = []
    for c in charts:
        try:
            built_charts.append(_chart(c))
        except ToolError as e:
            raise ToolError(f"Grafik '{c.get('title')}': {e}")

    dash = {"id": frappe.generate_hash(length=8), "title": (title or "Dashboard").strip()[:140], "kpis": built_kpis, "charts": built_charts}
    ctx["dashboards"].append(dash)
    if ctx.get("on_dashboard"):
        ctx["on_dashboard"](dash)

    return {
        "shown": True,
        "kpis": [{k: v for k, v in x.items() if k in ("label", "value", "unit", "prev", "delta_pct")} for x in built_kpis],
        "charts": [_summary(c) for c in built_charts],
        "note": "Dashboard foydalanuvchiga ko'rsatildi. Raqamlarni qayta jadval qilib yozma — "
        "qisqa tahlil (nima o'zgardi, nima sababdan) va so'ralgan bo'lsa tavsiyalar yoz.",
    }


KPI_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Masalan 'Sof sotuv'"},
        "sql": {"type": "string", "description": "Bitta qiymat qaytaradigan SELECT (afzal: server bazadan hisoblaydi)"},
        "value": {"type": "number", "description": "SQL bo'lmasa: tool natijasidagi aniq raqam"},
        "compare_sql": {"type": "string", "description": "Solishtirish davri qiymati uchun SELECT (masalan o'tgan oy)"},
        "compare_value": {"type": "number"},
        "compare_label": {"type": "string", "description": "Masalan 'sentyabrga nisbatan'"},
        "unit": {"type": "string", "description": "so'm, kg, %, ta"},
        "good_when": {"type": "string", "enum": ["up", "down"], "description": "O'sish yaxshimi (sotuv) yoki kamayish (xarajat, qarz)"},
    },
    "required": ["label"],
    "additionalProperties": False,
}

CHART_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["line", "bar", "share"],
            "description": "line — vaqt bo'yicha dinamika; bar — toifalarni solishtirish; share — butunning ulushlari (top 7 + Boshqa)",
        },
        "data": TABLE_SCHEMA,
        "x_column": {"type": "string", "description": "X o'qi ustuni (sana/oy yoki toifa). Berilmasa birinchi ustun"},
        "y_columns": {"type": "array", "items": {"type": "string"}, "description": "Qiymat ustunlari, ko'pi bilan 4 ta. Bitta grafikda faqat bir xil o'lchov birligi"},
        "unit": {"type": "string"},
    },
    "required": ["title", "type", "data"],
    "additionalProperties": False,
}

TOOLS = [
    (
        tool(
            "show_dashboard",
            "Chatda dashboard ko'rsatadi: KPI kartalari (o'tgan davr bilan solishtirish) va grafiklar. "
            "Foydalanuvchi dashboard, grafik, diagramma, analitika yoki dinamika so'rasa ishlat. "
            "Ma'lumotni o'zing ko'chirma: KPI uchun sql/compare_sql, grafik uchun data.source=sql yoki report ber — "
            "server bazadan oladi. Vaqt qatori uchun SQL'da oy/kun bo'yicha GROUP BY va ORDER BY qil. "
            "Har xil o'lchov birligidagi qiymatlarni (so'm va kg) bitta grafikka qo'yma — alohida grafik qil. "
            "Natijada qaytgan xulosa raqamlari asosida tahlil yoz.",
            {
                "title": {"type": "string"},
                "kpis": {"type": "array", "items": KPI_SCHEMA},
                "charts": {"type": "array", "items": CHART_SCHEMA},
            },
            ["title"],
            strict=False,
        ),
        show_dashboard,
    ),
]
