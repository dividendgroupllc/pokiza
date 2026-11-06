"""Erkin savollar uchun faqat-o'qish SQL."""
from pokiza.ai import sql_guard
from pokiza.ai.tools import tool


def sql_query(sql, purpose=None):
    columns, rows, truncated = sql_guard.run_select(sql)
    out = {"columns": columns, "row_count": len(rows), "rows": [list(r.values()) for r in rows]}
    if truncated:
        out["note"] = f"Natija {sql_guard.MAX_ROWS} qatorda kesildi — agregatsiya yoki LIMIT ishlat."
    return out


TOOLS = [
    (
        tool(
            "sql_query",
            "MariaDB'da faqat-o'qish SELECT so'rovi (bitta statement, max 500 qator, 15 s). "
            "Jadvallar: `tabSales Invoice`, `tabSales Invoice Item`, `tabGL Entry`, `tabStock Ledger Entry`, "
            "`tabBin`, `tabSales Order`, `tabPayment Entry`, `tabKassa`, `tabProduction Entry` va h.k. "
            "Jadval nomini backtick bilan yoz. Noma'lum maydonlar uchun avval describe_doctype.",
            {
                "sql": {"type": "string", "description": "SELECT so'rov"},
                "purpose": {"type": "string", "description": "Bu so'rov nimani hisoblaydi (audit va UI uchun, qisqa)"},
            },
            ["sql"],
        ),
        sql_query,
    ),
]
