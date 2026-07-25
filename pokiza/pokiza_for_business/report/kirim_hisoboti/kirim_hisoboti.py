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
        {"label": "Бирлик", "fieldname": "uom", "fieldtype": "Data", "width": 80},
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
            pii.uom,
            pii.rate,
            pii.amount
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE {where_clause}
        ORDER BY pi.posting_date DESC, pi.supplier, pii.item_name
    """, values, as_dict=True)

    data = []
    # Har bir валюта бўйича жами сумма
    currency_totals = {}

    for row in rows:
        data.append(row)
        cur = row.get("currency") or ""
        currency_totals[cur] = currency_totals.get(cur, 0) + flt(row.get("amount"))

    # Жами қаторлар (ҳар бир валюта учун алоҳида)
    for cur, total_amount in sorted(currency_totals.items()):
        data.append({
            "posting_date": None,
            "supplier": "",
            "item_name": "ЖАМИ",
            "qty": None,
            "uom": "",
            "rate": None,
            "amount": total_amount,
            "currency": cur,
            "invoice": "",
            "is_total_row": True,
        })

    return data
