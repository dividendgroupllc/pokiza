"""Tayyor Frappe/ERPNext va Pokiza report'larini ishga tushirish."""
import frappe

from pokiza.ai.tools import ToolError, parse_json_arg, rows_payload, tool

# report nomi -> filtrlar tavsifi (AI uchun)
REPORTS = {
    # Pokiza
    "PL Hisoboti": "Foyda-zarar (Pokiza formati). company, from_date, to_date, periodicity (Monthly/Quarterly/Yearly)",
    "DDS": "Pul oqimi (ДДС). from_date, to_date, [mode_of_payment, party_type, party, category]",
    "Akt Sverka": "Kontragent bilan solishtirma dalolatnoma. from_date, to_date, party_type, party",
    "Kontragent Otchet": "Kontragentlar bo'yicha qoldiq/aylanma. from_date, to_date, [party_type, party, currency]",
    "Mijoz Marja": "Mijozlar bo'yicha marja (qaytarishlarsiz!). from_date, to_date, [mijoz]",
    "Tannarx Norma Fakt": "Tannarx norma va fakt farqi. from_date, to_date, [mijoz, min_farq]",
    "Ombor Qoldigi Fakt": "Ombor qoldig'i. [warehouse, item_group, nol_korsat]",
    "Kirim Hisoboti": "Xarid (kirim) hisoboti. from_date, to_date, [supplier]",
    # ERPNext
    "General Ledger": "Bosh kitob. company, from_date, to_date, [account (list), party_type, party (list), group_by]",
    "Accounts Receivable": "Debitorlik (mijozlar qarzi) yoshlari bilan. company, report_date, [party_type='Customer', party (list)]",
    "Accounts Payable": "Kreditorlik (yetkazib beruvchilarga qarz). company, report_date, [party_type='Supplier']",
    "Customer Ledger Summary": "Mijozlar bo'yicha boshlang'ich/aylanma/yakuniy qoldiq. company, from_date, to_date",
    "Supplier Ledger Summary": "Yetkazib beruvchilar bo'yicha qoldiq. company, from_date, to_date",
    "Stock Balance": "Ombor qoldig'i va harakati. company, from_date, to_date, [warehouse, item_code]",
    "Gross Profit": "Yalpi foyda. company, from_date, to_date, group_by ('Invoice','Item Code','Customer','Item Group')",
    "Profit and Loss Statement": "ERPNext P&L. company, period_start_date, period_end_date, periodicity, filter_based_on='Date Range'",
    "Balance Sheet": "Balans. company, period_start_date, period_end_date, periodicity, filter_based_on='Date Range'",
    "Sales Analytics": "Sotuv dinamikasi. company, from_date, to_date, tree_type ('Customer','Item'), value_quantity ('Value','Quantity'), range ('Monthly'), doc_type ('Sales Invoice' yoki 'Sales Order'). Quantity — har xil birliklar (kg va dona) aralash qo'shiladi",
}


def _columns(cols):
    out = []
    for c in cols or []:
        if isinstance(c, dict):
            out.append({"fieldname": c.get("fieldname"), "label": c.get("label"), "fieldtype": c.get("fieldtype")})
        else:
            # "Label:Type/Options:width" formati
            parts = str(c).split(":")
            label = parts[0]
            fieldtype = parts[1].split("/")[0] if len(parts) > 1 else None
            out.append({"fieldname": frappe.scrub(label), "label": label, "fieldtype": fieldtype})
    return out


def execute_report(report, filters_json=None):
    """(columns, rows, filters, message): to'liq natija, qatorlar dict (fieldname -> qiymat)."""
    if report not in REPORTS:
        raise ToolError(f"Report ruxsat ro'yxatida yo'q. Mavjud: {', '.join(REPORTS)}")
    filters = parse_json_arg(filters_json, {}, "filters_json")
    if not isinstance(filters, dict):
        raise ToolError("filters_json obyekt bo'lishi kerak")
    filters.setdefault("company", frappe.defaults.get_user_default("Company"))
    if report == "Sales Analytics":
        filters.setdefault("doc_type", "Sales Invoice")  # bo'lmasa report ichida AttributeError

    from frappe.desk.query_report import run

    res = run(report, filters=filters, ignore_prepared_report=True, are_default_filters=False)
    columns = _columns(res.get("columns"))
    keys = [c["fieldname"] for c in columns]
    rows = []
    for r in res.get("result") or []:
        if isinstance(r, dict):
            rows.append({k: r.get(k) for k in keys if r.get(k) not in (None, "")})
        elif isinstance(r, (list, tuple)):
            rows.append({k: v for k, v in zip(keys, r) if v not in (None, "")})
    rows = [r for r in rows if r]
    message = str(res["message"])[:500] if res.get("message") else None
    return columns, rows, filters, message


def run_report(report, filters_json=None):
    columns, rows, filters, message = execute_report(report, filters_json)
    out = rows_payload(rows, columns=[c["label"] for c in columns])
    out["filters"] = filters
    if message:
        out["message"] = message
    return out


TOOLS = [
    (
        {
            **tool(
                "run_report",
                "Tayyor report'ni ishga tushiradi. Mavjud report'lar va filtrlari:\n"
                + "\n".join(f"- {k}: {v}" for k, v in REPORTS.items())
                + "\nSanalar YYYY-MM-DD formatida. company berilmasa standart kompaniya olinadi.",
                {
                    "report": {"type": "string", "enum": list(REPORTS)},
                    "filters_json": {"type": "string", "description": 'JSON obyekt: {"from_date": "2026-10-01", "to_date": "2026-10-31"}'},
                },
                ["report"],
            )
        },
        run_report,
    ),
]
