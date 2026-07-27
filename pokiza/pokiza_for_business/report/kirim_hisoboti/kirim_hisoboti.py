import frappe
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        return [], []

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {"label": "Сана", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Таъминотчи", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"label": "Махсулот", "fieldname": "item_name", "fieldtype": "Data", "width": 260},
        {"label": "Миқдор", "fieldname": "qty", "fieldtype": "Float", "width": 110},
        {"label": "Нарх", "fieldname": "rate", "fieldtype": "Currency", "options": "currency", "width": 120},
        {"label": "Сумма", "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": "Валюта", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
        {"label": "Хужжат", "fieldname": "invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
    ]


def get_data(filters):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    supplier = filters.get("supplier")

    conditions = ["pi.docstatus = 1", "pi.posting_date >= %(from_date)s", "pi.posting_date <= %(to_date)s"]
    values = {"from_date": from_date, "to_date": to_date}

    if supplier:
        conditions.append("pi.supplier = %(supplier)s")
        values["supplier"] = supplier

    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            pi.posting_date,
            pi.supplier,
            pi.currency,
            pi.name AS invoice,
            pii.item_code,
            pii.item_name,
            pii.qty,
            pii.rate,
            pii.amount
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE {where_clause}
        ORDER BY pi.posting_date DESC, pi.supplier, pii.item_name
    """, values, as_dict=True)

    data = []
    # Har bir валюта бўйича жами миқдор ва сумма
    currency_totals = {}

    for row in rows:
        data.append(row)
        cur = row.get("currency") or ""
        if cur not in currency_totals:
            currency_totals[cur] = {"qty": 0, "amount": 0}
        currency_totals[cur]["qty"] += flt(row.get("qty"))
        currency_totals[cur]["amount"] += flt(row.get("amount"))

    # Жами қаторлар (ҳар бир валюта учун алоҳида)
    for cur, totals in sorted(currency_totals.items()):
        total_qty = totals["qty"]
        total_amount = totals["amount"]
        data.append({
            "posting_date": None,
            "supplier": "",
            "item_name": "ЖАМИ",
            "qty": total_qty,
            "rate": None,
            "amount": total_amount,
            "currency": cur,
            "invoice": "",
            "is_total_row": True,
        })

    return data
