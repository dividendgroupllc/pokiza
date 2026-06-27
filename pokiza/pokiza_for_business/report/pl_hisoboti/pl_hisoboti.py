# Copyright (c) 2026, abdulloh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate
from datetime import date, timedelta


# ─── Account mapping ─────────────────────────────────────────────────────────

PRODUCTION_ROWS = [
    ("Зарплата (пр-во)",      "5211"),
    ("Налоги с зарплаты",     "5207"),
    ("Электроэнергия",        "5217"),
    ("Газ / Бензин",          "5202"),
    ("Питание",               "5201"),
    ("Хозяйственные расходы", "5203"),
    ("Цех / Обще-пр-во",      "5206"),
    ("Транспорт",             "5222"),
]
PRODUCTION_NUMBERS = {r[1] for r in PRODUCTION_ROWS}

OPEX_SALES_NUM   = {"5208"}
OPEX_ADMIN_NUM   = {"5209", "5204"}
OPEX_OTHER_NUM   = {"5210", "5213", "5214", "5218", "5224", "5225"}
OPEX_OTHER_NAMES = {"Бонус"}
OPEX_FIN_NUM     = {"5212"}
OPEX_FIN_NAMES   = {"Exchange Gain/Loss"}
OPEX_TAX_NUM     = {"5205"}

CARD_COLORS = ["#2563EB", "#059669", "#7C3AED", "#DC2626", "#0891B2", "#D97706", "#BE185D"]


# ─── Entry point ─────────────────────────────────────────────────────────────

def execute(filters=None):
    filters  = frappe._dict(filters or {})
    company  = filters.get("company") or "Pokiza"

    period_list = build_period_list(filters)
    if not period_list:
        return [], []

    from_date = str(period_list[0]["from_date"])
    to_date   = str(period_list[-1]["to_date"])

    gl_rows       = fetch_gl(company, from_date, to_date)
    vol_rows      = fetch_volume(company, from_date, to_date)
    prod_accounts = fetch_production_accounts(company)
    pdata         = aggregate(period_list, gl_rows, vol_rows)

    columns      = get_columns(period_list)
    data         = build_rows(period_list, pdata, prod_accounts)
    summary_html = get_summary_html(company, filters, period_list, pdata)

    return columns, data, summary_html


# ─── Period list ─────────────────────────────────────────────────────────────

def build_period_list(filters):
    today       = date.today()
    from_date   = getdate(filters.get("from_date") or date(today.year, 1, 1))
    to_date     = getdate(filters.get("to_date")   or today)
    periodicity = filters.get("periodicity") or "Yearly"

    periods  = []
    current  = from_date

    while current <= to_date:
        y, m = current.year, current.month

        if periodicity == "Monthly":
            p_start  = date(y, m, 1)
            nm       = m + 1
            p_end    = (date(y, nm, 1) - timedelta(days=1)) if nm <= 12 else date(y, 12, 31)
            label    = p_start.strftime("%b %Y")
            next_cur = date(y, nm, 1) if nm <= 12 else date(y + 1, 1, 1)

        elif periodicity == "Quarterly":
            q        = (m - 1) // 3
            qs, qe   = q * 3 + 1, q * 3 + 3
            p_start  = date(y, qs, 1)
            p_end    = (date(y, qe + 1, 1) - timedelta(days=1)) if qe < 12 else date(y, 12, 31)
            label    = f"Q{q + 1} {y}"
            nqs      = qe + 1
            next_cur = date(y, nqs, 1) if nqs <= 12 else date(y + 1, 1, 1)

        elif periodicity == "Half-Yearly":
            if m <= 6:
                p_start, p_end, label = date(y, 1, 1), date(y, 6, 30),  f"H1 {y}"
                next_cur = date(y, 7, 1)
            else:
                p_start, p_end, label = date(y, 7, 1), date(y, 12, 31), f"H2 {y}"
                next_cur = date(y + 1, 1, 1)

        else:  # Yearly
            p_start, p_end, label = date(y, 1, 1), date(y, 12, 31), str(y)
            next_cur = date(y + 1, 1, 1)

        actual_start = max(p_start, from_date)
        actual_end   = min(p_end,   to_date)
        if actual_start <= actual_end:
            periods.append({
                "key":       label,
                "label":     label,
                "from_date": actual_start,
                "to_date":   actual_end,
            })
        current = next_cur

    return periods


# ─── Data fetching ────────────────────────────────────────────────────────────

def fetch_gl(company, from_date, to_date):
    return frappe.db.sql("""
        SELECT
            gle.posting_date,
            TRIM(IFNULL(acc.account_number,        '')) AS account_number,
            TRIM(IFNULL(parent_acc.account_number, '')) AS parent_number,
            acc.account_name,
            acc.root_type,
            acc.account_type,
            SUM(gle.debit)  AS debit,
            SUM(gle.credit) AS credit
        FROM `tabGL Entry` gle
        JOIN  `tabAccount` acc        ON acc.name        = gle.account
        LEFT JOIN `tabAccount` parent_acc ON parent_acc.name = acc.parent_account
        WHERE gle.company = %s
          AND gle.is_cancelled = 0
          AND gle.posting_date BETWEEN %s AND %s
          AND acc.root_type IN ('Income', 'Expense')
        GROUP BY gle.posting_date, gle.account
        ORDER BY gle.posting_date
    """, (company, from_date, to_date), as_dict=True)


def fetch_volume(company, from_date, to_date):
    return frappe.db.sql("""
        SELECT si.posting_date, SUM(sii.stock_qty) AS qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.company = %s
          AND si.docstatus = 1
          AND si.posting_date BETWEEN %s AND %s
          AND LOWER(sii.uom) IN ('кг', 'kg')
        GROUP BY si.posting_date
    """, (company, from_date, to_date), as_dict=True)


def fetch_production_accounts(company):
    """
    Returns list of (account_name, prod_key) for production breakdown rows.
    Priority: children of 52001 parent (production env).
    Fallback: hardcoded PRODUCTION_ROWS (local env).
    """
    accounts = frappe.db.sql("""
        SELECT
            TRIM(IFNULL(account_number, '')) AS acc_num,
            account_name
        FROM `tabAccount`
        WHERE company = %s
          AND parent_account LIKE '52001%%'
          AND is_group = 0
        ORDER BY account_number, account_name
    """, (company,), as_dict=True)

    if accounts:
        return [(a.account_name, a.acc_num or a.account_name) for a in accounts]

    # Fallback: local structure — use actual DB names for accounts in PRODUCTION_NUMBERS
    db_accounts = frappe.db.sql("""
        SELECT
            TRIM(IFNULL(account_number, '')) AS acc_num,
            account_name
        FROM `tabAccount`
        WHERE company = %s
          AND TRIM(IFNULL(account_number, '')) IN %s
          AND is_group = 0
        ORDER BY account_number
    """, (company, tuple(PRODUCTION_NUMBERS)), as_dict=True)

    if db_accounts:
        return [(a.account_name, a.acc_num) for a in db_accounts]

    return PRODUCTION_ROWS


# ─── Aggregation ─────────────────────────────────────────────────────────────

def _period_key(posting_date, period_list):
    for p in period_list:
        if p["from_date"] <= posting_date <= p["to_date"]:
            return p["key"]
    return None


def _fk(period_key):
    return "v_" + period_key.replace(" ", "_").replace("-", "_")


def aggregate(period_list, gl_rows, vol_rows):
    def empty():
        return dict(revenue=0, cogs=0, prod={},
                    opex_sales=0, opex_admin=0, opex_other=0,
                    opex_fin=0, opex_tax=0, volume=0)

    pdata = {p["key"]: empty() for p in period_list}

    for r in gl_rows:
        pk = _period_key(r.posting_date, period_list)
        if not pk:
            continue
        d          = pdata[pk]
        net        = flt(r.debit) - flt(r.credit)
        num        = r.account_number or ""
        name       = r.account_name   or ""
        parent_num = r.parent_number  or ""

        if r.root_type == "Income":
            d["revenue"] += flt(r.credit) - flt(r.debit)

        elif r.account_type in ("Cost of Goods Sold", "Stock Adjustment"):
            d["cogs"] += net

        # ── Production approach: by parent account 52001 (production env) ──
        elif parent_num == "52001":
            key = num or name
            d["prod"][key] = d["prod"].get(key, 0) + net

        elif parent_num == "52002":
            d["opex_sales"] += net

        elif parent_num == "52003":
            d["opex_admin"] += net

        elif parent_num == "52004":
            d["opex_other"] += net

        elif parent_num == "52005":
            d["opex_fin"] += net

        elif parent_num == "52006":
            d["opex_tax"] += net

        # ── Fallback: by individual account number (local/old structure) ──
        elif num in PRODUCTION_NUMBERS:
            d["prod"][num] = d["prod"].get(num, 0) + net
        elif num in OPEX_SALES_NUM:
            d["opex_sales"] += net
        elif num in OPEX_ADMIN_NUM:
            d["opex_admin"] += net
        elif num in OPEX_OTHER_NUM or name in OPEX_OTHER_NAMES:
            d["opex_other"] += net
        elif num in OPEX_FIN_NUM or name in OPEX_FIN_NAMES:
            d["opex_fin"] += net
        elif num in OPEX_TAX_NUM:
            d["opex_tax"] += net

    for r in vol_rows:
        pk = _period_key(r.posting_date, period_list)
        if pk:
            pdata[pk]["volume"] += flt(r.qty)

    return pdata


# ─── Columns ─────────────────────────────────────────────────────────────────

def get_columns(period_list):
    cols = [{"fieldname": "label", "label": _("Кўрсаткич"), "fieldtype": "Data", "width": 310}]
    for p in period_list:
        cols.append({
            "fieldname": _fk(p["key"]),
            "label":     p["label"],
            "fieldtype": "Currency",
            "options":   "currency",
            "width":     160,
        })
    return cols


# ─── Row builder ─────────────────────────────────────────────────────────────

def build_rows(period_list, pdata, prod_accounts=None):
    if prod_accounts is None:
        prod_accounts = PRODUCTION_ROWS

    def row(label, value_map, bold=False, indent=0):
        INDENT = {0: "", 1: "    ", 2: "        "}
        prefix = INDENT.get(indent, "            ")
        r = {"label": prefix + label, "bold": 1 if bold else 0}
        r.update(value_map)
        return r

    def spacer():
        r = {"label": "", "bold": 0}
        for p in period_list:
            r[_fk(p["key"])] = None
        return r

    def vmap(getter):
        return {_fk(p["key"]): getter(pdata[p["key"]]) for p in period_list}

    rows = []

    # ── Volume ──
    rows.append(row("Объём продажи (кг)", vmap(lambda d: d["volume"]), bold=True))
    rows.append(spacer())

    # ── Revenue ──
    rows.append(row("Выручка от реализации", vmap(lambda d: d["revenue"]), bold=True))
    avg = {_fk(p["key"]): (pdata[p["key"]]["revenue"] / pdata[p["key"]]["volume"])
           if pdata[p["key"]]["volume"] else 0
           for p in period_list}
    rows.append(row("средний цена за кг", avg, indent=1))
    rows.append(spacer())

    # ── Себестоимость ──
    cogs_total = {}
    prod_total = {}
    for p in period_list:
        d  = pdata[p["key"]]
        pt = sum(d["prod"].values())
        prod_total[_fk(p["key"])] = pt
        cogs_total[_fk(p["key"])] = d["cogs"] + pt

    rows.append(row("Себестоимость реализации", cogs_total, bold=True))
    rows.append(row("Производственные расходы", prod_total, indent=1))
    for acc_name, prod_key in prod_accounts:
        prow = {_fk(p["key"]): pdata[p["key"]]["prod"].get(prod_key, 0) for p in period_list}
        rows.append(row(acc_name, prow, indent=2))
    rows.append(spacer())

    # ── Gross Profit ──
    gp = {}
    for p in period_list:
        d  = pdata[p["key"]]
        pt = sum(d["prod"].values())
        gp[_fk(p["key"])] = d["revenue"] - d["cogs"] - pt

    rows.append(row("Прибыль валовая", gp, bold=True))
    margin = {_fk(p["key"]): (gp[_fk(p["key"])] / pdata[p["key"]]["revenue"] * 100)
              if pdata[p["key"]]["revenue"] else 0
              for p in period_list}
    rows.append(row("маржа %", margin, indent=1))
    rows.append(spacer())

    # ── OpEx ──
    opex_total = {}
    for p in period_list:
        d = pdata[p["key"]]
        opex_total[_fk(p["key"])] = (
            d["opex_sales"] + d["opex_admin"] + d["opex_other"] +
            d["opex_fin"]   + d["opex_tax"]
        )
    rows.append(row("Расходы с прибыли", opex_total, bold=True))

    for section_label, key in [
        ("52002 - Расходы по реализации",       "opex_sales"),
        ("52003 - Административные расходы",    "opex_admin"),
        ("52004 - Прочие операционные расходы", "opex_other"),
        ("52005 - Финансовые расходы",          "opex_fin"),
        ("52006 - налог с прибыли",             "opex_tax"),
    ]:
        svals = {_fk(p["key"]): pdata[p["key"]][key] for p in period_list}
        rows.append(row(section_label, svals, indent=1))
    rows.append(spacer())

    # ── Net Profit ──
    np_map = {}
    for p in period_list:
        d     = pdata[p["key"]]
        pt    = sum(d["prod"].values())
        gross = d["revenue"] - d["cogs"] - pt
        opex  = d["opex_sales"] + d["opex_admin"] + d["opex_other"] + d["opex_fin"] + d["opex_tax"]
        np_map[_fk(p["key"])] = gross - opex

    rows.append(row("Чистая прибыль", np_map, bold=True))
    net_margin = {_fk(p["key"]): (np_map[_fk(p["key"])] / pdata[p["key"]]["revenue"] * 100)
                  if pdata[p["key"]]["revenue"] else 0
                  for p in period_list}
    rows.append(row("рентабельность %", net_margin, indent=1))

    return rows


# ─── Summary HTML (design panel) ─────────────────────────────────────────────

def _fmt(val):
    v = abs(flt(val))
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    elif v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    elif v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return f"{v:,.0f}"


def _bar(pct, color, bg):
    w = min(max(flt(pct), 0), 100)
    return f"""
        <div style="background:{bg};height:6px;border-radius:3px;overflow:hidden;margin-top:4px;">
          <div style="background:{color};height:100%;width:{w:.1f}%;border-radius:3px;"></div>
        </div>"""


def get_summary_html(company, filters, period_list, pdata):
    from_date   = filters.get("from_date", "")
    to_date     = filters.get("to_date",   "")
    periodicity = filters.get("periodicity", "Yearly")

    # ── Header ──────────────────────────────────────────────────────────────
    header = f"""
    <div style="background:linear-gradient(135deg,#0f2942 0%,#1e3a5f 60%,#1a4f72 100%);
                color:white;padding:20px 24px;border-radius:12px;margin-bottom:16px;
                display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
      <div>
        <div style="font-size:10px;letter-spacing:2.5px;text-transform:uppercase;
                    opacity:0.6;margin-bottom:4px;">ФОЙДА — ЗАРАР ҲИСОБОТИ</div>
        <div style="font-size:20px;font-weight:700;letter-spacing:-0.3px;">{company} &nbsp;·&nbsp; P&amp;L Report</div>
      </div>
      <div style="text-align:right;opacity:0.75;font-size:12px;line-height:1.6;">
        <div>{from_date} — {to_date}</div>
        <div style="font-size:10px;opacity:0.7;margin-top:2px;">{periodicity}</div>
      </div>
    </div>"""

    # ── Period cards ────────────────────────────────────────────────────────
    cards_html = ""
    for i, p in enumerate(period_list):
        d    = pdata[p["key"]]
        pt   = sum(d["prod"].values())
        gp   = d["revenue"] - d["cogs"] - pt
        opex = d["opex_sales"] + d["opex_admin"] + d["opex_other"] + d["opex_fin"] + d["opex_tax"]
        np   = gp - opex

        gm_pct  = (gp / d["revenue"] * 100) if d["revenue"] else 0
        nm_pct  = (np / d["revenue"] * 100) if d["revenue"] else 0
        color   = CARD_COLORS[i % len(CARD_COLORS)]

        # trend vs previous period
        if i > 0:
            prev_rev = pdata[period_list[i - 1]["key"]]["revenue"]
            delta    = d["revenue"] - prev_rev
            if prev_rev:
                trend_pct = delta / prev_rev * 100
                trend_ico = "▲" if delta >= 0 else "▼"
                trend_clr = "#10b981" if delta >= 0 else "#ef4444"
                trend_str = f'<span style="color:{trend_clr};font-size:10px;font-weight:600;">{trend_ico} {abs(trend_pct):.1f}%</span>'
            else:
                trend_str = ""
        else:
            trend_str = ""

        gm_bar  = _bar(gm_pct, "#10b981", "#ecfdf5")
        nm_bar  = _bar(nm_pct, color,     "#eff6ff")

        cards_html += f"""
        <div style="flex:1;min-width:180px;background:white;border-radius:10px;
                    box-shadow:0 1px 8px rgba(0,0,0,0.07);overflow:hidden;
                    border:1px solid #f0f0f0;">
          <div style="background:{color};padding:10px 14px;
                      display:flex;align-items:center;justify-content:space-between;">
            <span style="color:white;font-size:13px;font-weight:700;">{p['label']}</span>
            {trend_str}
          </div>
          <div style="padding:14px 16px;">
            <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #f5f5f5;">
              <div style="font-size:9px;color:#aaa;text-transform:uppercase;
                          letter-spacing:1px;margin-bottom:2px;">Выручка</div>
              <div style="font-size:22px;font-weight:800;color:#111;line-height:1.1;">
                {_fmt(d['revenue'])}
              </div>
              <div style="font-size:10px;color:#aaa;margin-top:1px;">UZS</div>
            </div>

            <div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:10px;color:#777;">Yalpi foyda</span>
                <span style="font-size:11px;font-weight:700;color:#10b981;">{gm_pct:.1f}%</span>
              </div>
              {gm_bar}
              <div style="font-size:9px;color:#bbb;margin-top:2px;">{_fmt(gp)} UZS</div>
            </div>

            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:10px;color:#777;">Sof foyda</span>
                <span style="font-size:11px;font-weight:700;color:{color};">{nm_pct:.1f}%</span>
              </div>
              {nm_bar}
              <div style="font-size:9px;color:#bbb;margin-top:2px;">{_fmt(np)} UZS</div>
            </div>
          </div>
        </div>"""

    cards_section = f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      {cards_html}
    </div>"""

    # ── Cost structure bar (stacked, for each period) ─────────────────────
    cost_bars = ""
    for i, p in enumerate(period_list):
        d     = pdata[p["key"]]
        rev   = d["revenue"]
        if not rev:
            continue
        pt    = sum(d["prod"].values())
        cogs_pct  = d["cogs"] / rev * 100
        prod_pct  = pt        / rev * 100
        sales_pct = d["opex_sales"] / rev * 100
        adm_pct   = d["opex_admin"] / rev * 100
        oth_pct   = (d["opex_other"] + d["opex_fin"] + d["opex_tax"]) / rev * 100
        profit_pct = 100 - cogs_pct - prod_pct - sales_pct - adm_pct - oth_pct
        profit_pct = max(profit_pct, 0)
        color = CARD_COLORS[i % len(CARD_COLORS)]

        cost_bars += f"""
        <div style="margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;
                      align-items:center;margin-bottom:5px;">
            <span style="font-size:11px;font-weight:600;color:#333;">{p['label']}</span>
            <span style="font-size:10px;color:#888;">{_fmt(rev)} UZS</span>
          </div>
          <div style="display:flex;height:18px;border-radius:6px;overflow:hidden;gap:1px;">
            <div style="flex:{cogs_pct:.1f};background:#ef4444;" title="COGS {cogs_pct:.1f}%"></div>
            <div style="flex:{prod_pct:.1f};background:#f97316;" title="Пр-во {prod_pct:.1f}%"></div>
            <div style="flex:{sales_pct:.1f};background:#eab308;" title="Реализ. {sales_pct:.1f}%"></div>
            <div style="flex:{adm_pct:.1f};background:#8b5cf6;"  title="Адм. {adm_pct:.1f}%"></div>
            <div style="flex:{oth_pct:.1f};background:#6b7280;"  title="Прочие {oth_pct:.1f}%"></div>
            <div style="flex:{profit_pct:.1f};background:#10b981;" title="Foyda {profit_pct:.1f}%"></div>
          </div>
          <div style="display:flex;gap:10px;margin-top:4px;flex-wrap:wrap;">
            <span style="font-size:9px;color:#ef4444;">■ COGS {cogs_pct:.0f}%</span>
            <span style="font-size:9px;color:#f97316;">■ Пр-во {prod_pct:.0f}%</span>
            <span style="font-size:9px;color:#eab308;">■ Реализ. {sales_pct:.0f}%</span>
            <span style="font-size:9px;color:#8b5cf6;">■ Адм. {adm_pct:.0f}%</span>
            <span style="font-size:9px;color:#6b7280;">■ Прочие {oth_pct:.0f}%</span>
            <span style="font-size:9px;color:#10b981;">■ Foyda {profit_pct:.0f}%</span>
          </div>
        </div>"""

    structure_section = ""
    if cost_bars:
        structure_section = f"""
        <div style="background:white;border-radius:10px;padding:16px 20px;
                    box-shadow:0 1px 8px rgba(0,0,0,0.07);border:1px solid #f0f0f0;">
          <div style="font-size:11px;font-weight:700;color:#333;
                      text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;">
            Даромаддан тузилиши
          </div>
          {cost_bars}
        </div>"""

    return f"""
    <div style="margin:20px 0;font-family:'Segoe UI',Arial,sans-serif;">
      {header}
      {cards_section}
      {structure_section}
    </div>"""
