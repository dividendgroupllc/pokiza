"""Sales Order list view: davr bo'yicha batafsil hisobotni chop etish uchun HTML.

Foydalanuvchi list view'dagi tugmani bosib sana oralig'ini tanlaydi, natijada
o'sha davrda yaratilgan har bir Sales Order kim uchun, qaysi mahsulotdan
qancha va qanday narxda sotilgani bilan birga chiqadi.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, formatdate, getdate


def _fmt_qty(v) -> str:
    v = flt(v)
    txt = f"{v:,.3f}".rstrip("0").rstrip(".") if v % 1 else f"{v:,.0f}"
    return txt.replace(",", " ")


def _fmt_money(v) -> str:
    return f"{flt(v):,.2f}".replace(",", " ")


def _get_orders(from_date, to_date, include_draft: bool, include_cancelled: bool) -> list:
    docstatuses = [1]
    if include_draft:
        docstatuses.append(0)
    if include_cancelled:
        docstatuses.append(2)

    return frappe.get_all(
        "Sales Order",
        filters={
            "transaction_date": ["between", [from_date, to_date]],
            "docstatus": ["in", docstatuses],
        },
        fields=[
            "name", "transaction_date", "delivery_date", "customer", "customer_name",
            "currency", "conversion_rate", "total", "total_taxes_and_charges",
            "discount_amount", "grand_total", "status", "docstatus", "company",
        ],
        order_by="transaction_date asc, name asc",
    )


def _get_items(order_names: list) -> dict:
    if not order_names:
        return {}

    rows = frappe.get_all(
        "Sales Order Item",
        filters={"parent": ["in", order_names]},
        fields=["parent", "idx", "item_code", "item_name", "qty", "uom", "rate", "amount"],
        order_by="parent asc, idx asc",
    )

    grouped = {}
    for row in rows:
        grouped.setdefault(row.parent, []).append(row)
    return grouped


_STATUS_LABELS = {
    "Draft": "Qoralama",
    "On Hold": "To'xtatilgan",
    "To Deliver and Bill": "Yetkazish va hisob-faktura",
    "To Bill": "Hisob-faktura kutilmoqda",
    "To Deliver": "Yetkazish kutilmoqda",
    "Completed": "Yakunlangan",
    "Cancelled": "Bekor qilingan",
    "Closed": "Yopilgan",
}


def _order_block(order, items) -> str:
    status = _STATUS_LABELS.get(order.status, order.status or "")
    status_class = "st-draft" if order.docstatus == 0 else ("st-cancelled" if order.docstatus == 2 else "st-submitted")

    item_rows = []
    for it in items:
        item_label = escape_html(it.item_name or it.item_code or "")
        if it.item_code and it.item_name and it.item_code != it.item_name:
            item_label += f' <span class="code">({escape_html(it.item_code)})</span>'
        item_rows.append(
            "<tr>"
            f'<td class="num">{it.idx}</td>'
            f'<td class="item">{item_label}</td>'
            f'<td class="qty">{_fmt_qty(it.qty)}</td>'
            f'<td class="uom">{escape_html(it.uom or "")}</td>'
            f'<td class="money">{_fmt_money(it.rate)}</td>'
            f'<td class="money">{_fmt_money(it.amount)}</td>'
            "</tr>"
        )

    if not item_rows:
        item_rows.append('<tr><td colspan="6" class="empty">Mahsulot qatorlari yo\'q</td></tr>')

    totals = []
    if flt(order.total_taxes_and_charges):
        totals.append(f"Soliq/qo'shimcha: <b>{_fmt_money(order.total_taxes_and_charges)}</b>")
    if flt(order.discount_amount):
        totals.append(f"Chegirma: <b>{_fmt_money(order.discount_amount)}</b>")
    extra_totals = f'<div class="extra">{" · ".join(totals)}</div>' if totals else ""

    delivery = (
        f'<span class="meta-item">Yetkazish: <b>{formatdate(order.delivery_date)}</b></span>'
        if order.delivery_date else ""
    )

    return f"""
    <section class="order">
        <div class="order-head">
            <div class="order-id">
                <span class="doc">{escape_html(order.name)}</span>
                <span class="badge {status_class}">{escape_html(status)}</span>
            </div>
            <div class="order-meta">
                <span class="meta-item">Sana: <b>{formatdate(order.transaction_date)}</b></span>
                {delivery}
            </div>
        </div>
        <div class="customer">Mijoz: <b>{escape_html(order.customer_name or order.customer or "")}</b></div>
        <table class="items">
            <thead>
                <tr>
                    <th class="num">#</th>
                    <th class="item">Mahsulot</th>
                    <th class="qty">Miqdor</th>
                    <th class="uom">Birlik</th>
                    <th class="money">Narx</th>
                    <th class="money">Summa</th>
                </tr>
            </thead>
            <tbody>{"".join(item_rows)}</tbody>
            <tfoot>
                <tr>
                    <td colspan="5" class="total-label">Jami ({escape_html(order.currency or "")})</td>
                    <td class="money total-value">{_fmt_money(order.grand_total)}</td>
                </tr>
            </tfoot>
        </table>
        {extra_totals}
    </section>
    """


@frappe.whitelist()
def get_period_report_html(from_date, to_date, include_draft=0, include_cancelled=0):
    """Tanlangan davrdagi Sales Order'larning batafsil chop etish HTML'i."""
    frappe.has_permission("Sales Order", "read", throw=True)

    from_date, to_date = getdate(from_date), getdate(to_date)
    if from_date > to_date:
        frappe.throw(_("Boshlanish sanasi tugash sanasidan katta bo'lishi mumkin emas."))

    include_draft = frappe.utils.cint(include_draft)
    include_cancelled = frappe.utils.cint(include_cancelled)

    orders = _get_orders(from_date, to_date, include_draft, include_cancelled)
    items_by_order = _get_items([o.name for o in orders])

    # Valyuta bo'yicha yakuniy jamilar (bazada UZS va USD buyurtmalar aralash bo'lishi mumkin)
    totals_by_currency = {}
    qty_by_currency = {}
    for o in orders:
        if o.docstatus == 2:
            continue
        cur = o.currency or ""
        totals_by_currency[cur] = flt(totals_by_currency.get(cur)) + flt(o.grand_total)
        qty_by_currency[cur] = flt(qty_by_currency.get(cur)) + sum(
            flt(i.qty) for i in items_by_order.get(o.name, [])
        )

    body = "".join(_order_block(o, items_by_order.get(o.name, [])) for o in orders)
    if not orders:
        body = '<p class="empty-report">Tanlangan davrda Sales Order topilmadi.</p>'

    summary_rows = "".join(
        "<tr>"
        f"<td>{escape_html(cur)}</td>"
        f'<td class="qty">{_fmt_qty(qty_by_currency.get(cur))}</td>'
        f'<td class="money">{_fmt_money(total)}</td>'
        "</tr>"
        for cur, total in sorted(totals_by_currency.items())
    )
    summary = f"""
        <section class="summary">
            <h2>Yakuniy jami</h2>
            <table>
                <thead><tr><th>Valyuta</th><th class="qty">Umumiy miqdor</th><th class="money">Umumiy summa</th></tr></thead>
                <tbody>{summary_rows}</tbody>
            </table>
        </section>
    """ if summary_rows else ""

    company = orders[0].company if orders else (frappe.defaults.get_user_default("Company") or "")
    period = f"{formatdate(from_date)} — {formatdate(to_date)}"
    printed_on = formatdate(frappe.utils.nowdate())

    return {
        "count": len(orders),
        "html": f"""
        <div class="so-report">
            <header class="report-head">
                <div>
                    <div class="kicker">Sotuv buyurtmalari hisoboti</div>
                    <h1>{escape_html(company)}</h1>
                </div>
                <div class="head-right">
                    <div class="period">{period}</div>
                    <div class="muted">Buyurtmalar: <b>{len(orders)}</b></div>
                    <div class="muted">Chop etildi: {printed_on}</div>
                </div>
            </header>
            {body}
            {summary}
        </div>
        """,
    }
