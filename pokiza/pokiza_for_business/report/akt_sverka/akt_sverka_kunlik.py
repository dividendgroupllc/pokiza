"""Akt Sverka — kunlik (kalendar) ko'rinish: ma'lumot qatlami.

Hisobotning ikkita ko'rinishi bor, ikkalasi ham bitta «Akt Sverka» hisoboti
ichida, yuqoridagi «Кўриниш» filtri bilan almashtiriladi:

  * «Подробный»  — hujjat-hujjat lenta, akt_sverka.py da (eski ko'rinish)
  * «Ежедневный» — shu modul: kunlik kalendar lenta

«Excel юклаш» tugmasi esa qaysi ko'rinish tanlanganidan qat'i nazar doim
shu kunlik shaklni bo'yalgan .xlsx qilib beradi — mijozga beriladigan shakl:

    Дата | Отгрузка | Оплачено | Возврат | Перечисления | Бонус | Сальдо

Har bir kalendar kuni bitta qator (harakat bo'lmasa ham), sarlavhada
davr jami «Отгрузка», kontragent nomi va yopilish «Сальдо» turadi.

Asosiy qoidalar:
  * Сальдо = oldingi сальдо + Отгрузка − Оплачено − Возврат − Перечисления − Бонус
  * Оплачено    — kassa (naqd) to'lovlari
    Перечисления — bank / Р/С orqali o'tkazmalar
  * Бонус oyning oxirgi kuniga (yoki davr oxirgi kuniga) yig'ib qo'yiladi —
    bonus oylik yakun bo'yicha hisoblashiladi.
  * Klassifikatsiyalanmagan harakatlar «Прочее» ustuniga tushadi; bu ustun
    faqat nolga teng bo'lmaganda qo'shiladi (pul yo'qolib qolmasligi uchun).
"""

import base64
import io
import json
from collections import defaultdict

import frappe
from frappe.utils import add_days, flt, get_last_day, getdate

# Bank / o'tkazma hisoblarini aniqlash uchun nomlardagi kalit so'zlar.
# (Pokiza'da «Р/С» hisobining account_type xato — «Cash», shuning uchun
#  nom bo'yicha ham tekshiramiz.)
PERECHISLENIYA_PATTERNS = ("р/с", "р\\с", "перечисл", "банк", "bank", "transfer")

BONUS_ACCOUNT_NAME = "Бонус"

MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}

AMOUNT_FIELDS = ("otgruzka", "oplachano", "vozvrat", "perechisleniya", "bonus", "boshqa")

# Kunlik lenta cheksiz uzun bo'lib ketmasligi uchun chegara
MAX_DAYS = 1100

NUM_FORMAT = '#,##0;-#,##0;"-"'


# ──────────────────────────────────────────────────────────────────────────
#  Tashqi nuqta
# ──────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def generate_akt_sverka_excel(filters):
    if isinstance(filters, str):
        filters = json.loads(filters)

    if not filters or not filters.get("party"):
        frappe.throw("Контрагентни танланг")

    report = build_report(filters)
    return base64.b64encode(build_excel(report)).decode("utf-8")


# ──────────────────────────────────────────────────────────────────────────
#  Ma'lumot
# ──────────────────────────────────────────────────────────────────────────

def build_report(filters):
    """Kunlik lentani hisoblaydi.

    Qaytadi: {rows, totals, opening, closing, currency, party, party_type,
              from_date, to_date, show_boshqa, company}
    """
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    party_type = filters.get("party_type")
    party = filters.get("party")

    if to_date < from_date:
        from_date, to_date = to_date, from_date

    from_date = clamp_from_date(party_type, party, from_date, to_date)

    currency = get_party_currency(party_type, party)
    # Customer uchun сальдо = debitorka (debit − credit),
    # Supplier/Employee uchun = kreditorka (credit − debit).
    sign = 1 if party_type == "Customer" else -1

    opening = get_opening_balance(party_type, party, currency, from_date, sign)
    entries = get_entries(party_type, party, currency, from_date, to_date)

    per_day = defaultdict(lambda: defaultdict(float))
    bonus_per_month = defaultdict(float)

    for entry in entries:
        bucket, amount = classify(entry, sign)
        if not amount:
            continue

        if bucket == "bonus":
            key = (entry["posting_date"].year, entry["posting_date"].month)
            bonus_per_month[key] += amount
        else:
            per_day[entry["posting_date"]][bucket] += amount

    # Employee uchun Salary Slip (GL'da party bilan yotmasligi mumkin)
    for slip in get_salary_slips(party_type, party, from_date, to_date):
        per_day[slip["posting_date"]]["otgruzka"] += flt(slip["amount"])

    # Bonusni oy oxiriga (yoki davr oxiriga) joylash
    for (year, month), amount in bonus_per_month.items():
        month_end = getdate(get_last_day(f"{year}-{month:02d}-01"))
        if month_end > to_date:
            month_end = to_date
        per_day[month_end]["bonus"] += amount

    rows = []
    totals = {f: 0.0 for f in AMOUNT_FIELDS}
    saldo = opening
    day = from_date

    while day <= to_date:
        values = per_day.get(day, {})
        row = {
            "posting_date": day,
            "date_label": fmt_date_label(day),
            "currency": currency,
        }
        for field in AMOUNT_FIELDS:
            amount = flt(values.get(field, 0), 2)
            row[field] = amount
            totals[field] += amount

        saldo += row["otgruzka"] - (
            row["oplachano"] + row["vozvrat"] + row["perechisleniya"]
            + row["bonus"] + row["boshqa"]
        )
        row["saldo"] = flt(saldo, 2)
        rows.append(row)
        day = getdate(add_days(day, 1))

    return {
        "rows": rows,
        "totals": {k: flt(v, 2) for k, v in totals.items()},
        "opening": flt(opening, 2),
        "closing": flt(saldo, 2),
        "currency": currency,
        "party": party,
        "party_type": party_type,
        "from_date": from_date,
        "to_date": to_date,
        "show_boshqa": bool(flt(totals["boshqa"], 2)),
        "company": get_company(),
    }


def fmt_date_label(d):
    d = getdate(d)
    return f"{d.day}-{MONTHS_RU[d.month]}-{d.year}"


def clamp_from_date(party_type, party, from_date, to_date):
    """Boshlanish sanasini kontragentning birinchi yozuvigacha qisqartirish.

    Telegram «butun davr» uchun 2000-01-01 yuboradi — birinchi yozuvgacha
    bo'sh kunlarni chizishning ma'nosi yo'q.
    """
    first = frappe.db.sql(
        """
        SELECT MIN(posting_date)
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND is_cancelled = 0
        """,
        (party_type, party),
    )[0][0]

    if first and getdate(first) > from_date:
        from_date = getdate(first)

    if (to_date - from_date).days > MAX_DAYS:
        from_date = getdate(add_days(to_date, -MAX_DAYS))

    return min(from_date, to_date)


def get_company():
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )


def get_party_currency(party_type, party):
    row = frappe.db.sql(
        """
        SELECT account_currency
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND is_cancelled = 0
        ORDER BY posting_date ASC, creation ASC
        LIMIT 1
        """,
        (party_type, party),
    )
    return row[0][0] if row else "UZS"


def get_opening_balance(party_type, party, currency, from_date, sign):
    balance = frappe.db.sql(
        """
        SELECT IFNULL(SUM(debit_in_account_currency - credit_in_account_currency), 0)
        FROM `tabGL Entry`
        WHERE posting_date < %s
          AND party_type = %s
          AND party = %s
          AND account_currency = %s
          AND is_cancelled = 0
        """,
        (from_date, party_type, party, currency),
    )[0][0]

    opening = sign * flt(balance)

    if party_type == "Employee":
        salary = frappe.db.sql(
            """
            SELECT IFNULL(SUM(gross_pay), 0)
            FROM `tabSalary Slip`
            WHERE posting_date < %s AND employee = %s AND docstatus = 1
            """,
            (from_date, party),
        )[0][0]
        opening += flt(salary)

    return opening


def get_entries(party_type, party, currency, from_date, to_date):
    bonus_accounts = get_bonus_accounts()
    bonus_condition = "0"
    params = {
        "from_date": from_date,
        "to_date": to_date,
        "party_type": party_type,
        "party": party,
        "currency": currency,
    }

    if bonus_accounts:
        bonus_condition = """EXISTS (
            SELECT 1 FROM `tabJournal Entry Account` jea
            WHERE jea.parent = gl.voucher_no
              AND jea.account IN %(bonus_accounts)s
        )"""
        params["bonus_accounts"] = tuple(bonus_accounts)

    return frappe.db.sql(
        f"""
        SELECT
            gl.posting_date,
            gl.voucher_type,
            gl.voucher_no,
            gl.debit_in_account_currency  AS debit,
            gl.credit_in_account_currency AS credit,
            pe.payment_type,
            pe.mode_of_payment,
            pe.paid_to,
            pe.paid_from,
            si.is_return AS si_return,
            pi.is_return AS pi_return,
            {bonus_condition} AS is_bonus
        FROM `tabGL Entry` gl
        LEFT JOIN `tabPayment Entry`    pe ON pe.name = gl.voucher_no AND gl.voucher_type = 'Payment Entry'
        LEFT JOIN `tabSales Invoice`    si ON si.name = gl.voucher_no AND gl.voucher_type = 'Sales Invoice'
        LEFT JOIN `tabPurchase Invoice` pi ON pi.name = gl.voucher_no AND gl.voucher_type = 'Purchase Invoice'
        WHERE gl.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gl.party_type = %(party_type)s
          AND gl.party = %(party)s
          AND gl.account_currency = %(currency)s
          AND gl.is_cancelled = 0
        ORDER BY gl.posting_date ASC, gl.creation ASC
        """,
        params,
        as_dict=True,
    )


def get_salary_slips(party_type, party, from_date, to_date):
    if party_type != "Employee":
        return []

    return frappe.db.sql(
        """
        SELECT posting_date, gross_pay AS amount
        FROM `tabSalary Slip`
        WHERE posting_date BETWEEN %s AND %s
          AND employee = %s
          AND docstatus = 1
        """,
        (from_date, to_date, party),
        as_dict=True,
    )


def get_bonus_accounts():
    return frappe.get_all(
        "Account",
        filters={"account_name": BONUS_ACCOUNT_NAME, "is_group": 0},
        pluck="name",
    )


def is_perechisleniya_account(account_name):
    if not account_name:
        return False
    low = account_name.lower()
    return any(p in low for p in PERECHISLENIYA_PATTERNS)


def classify(entry, sign):
    """GL yozuvini ustunga ajratadi.

    Qaytadi: (ustun nomi, summa). Summa doim «сальдо»ga ta'sir yo'nalishida
    musbat bo'ladi: Отгрузка oshiradi, qolganlari kamaytiradi.
    """
    voucher_type = entry.get("voucher_type")
    delta = sign * (flt(entry.get("debit")) - flt(entry.get("credit")))

    if voucher_type in ("Sales Invoice", "Purchase Invoice"):
        if entry.get("si_return") or entry.get("pi_return"):
            return "vozvrat", -delta
        return "otgruzka", delta

    if voucher_type == "Payment Entry":
        account = entry.get("paid_to") if entry.get("payment_type") == "Receive" else entry.get("paid_from")
        bucket = "perechisleniya" if (
            is_perechisleniya_account(account)
            or is_perechisleniya_account(entry.get("mode_of_payment"))
        ) else "oplachano"
        return bucket, -delta

    if voucher_type == "Journal Entry" and entry.get("is_bonus"):
        return "bonus", -delta

    return "boshqa", -delta


# ──────────────────────────────────────────────────────────────────────────
#  Ekrandagi ko'rinish (query report)
# ──────────────────────────────────────────────────────────────────────────

def get_columns(report):
    currency = report.get("currency") or "UZS"

    columns = [
        {"label": "Дата", "fieldname": "date_label", "fieldtype": "Data", "width": 120},
        {"label": "Отгрузка", "fieldname": "otgruzka", "fieldtype": "Currency",
         "options": "currency", "width": 130},
        {"label": "Оплачено", "fieldname": "oplachano", "fieldtype": "Currency",
         "options": "currency", "width": 130},
        {"label": "Возврат", "fieldname": "vozvrat", "fieldtype": "Currency",
         "options": "currency", "width": 120},
        {"label": "Перечисления", "fieldname": "perechisleniya", "fieldtype": "Currency",
         "options": "currency", "width": 140},
        {"label": "Бонус", "fieldname": "bonus", "fieldtype": "Currency",
         "options": "currency", "width": 130},
    ]

    if report.get("show_boshqa"):
        columns.append(
            {"label": "Прочее", "fieldname": "boshqa", "fieldtype": "Currency",
             "options": "currency", "width": 120}
        )

    columns.append(
        {"label": "Сальдо", "fieldname": "saldo", "fieldtype": "Currency",
         "options": "currency", "width": 150}
    )

    for col in columns:
        col["currency"] = currency

    return columns


def get_ui_rows(report):
    """Datatable uchun qatorlar.

    DIQQAT: bu yerda `indent` maydoni BO'LMASLIGI kerak. Frappe daraxt
    rejimini `this.data.some(d => "indent" in d)` bilan aniqlaydi — kunlik
    lentada daraxt kerak emas, oddiy jadval bo'lib chiqadi.
    """
    return list(report["rows"])


def _fmt_num(value):
    try:
        return "{:,.0f}".format(float(value or 0)).replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def get_summary_html(report):
    """Namunadagi сарлавҳа блоки: жами оборотлар + очилиш/ёпилиш сальдоси."""
    if not report.get("rows"):
        return ""

    totals = report["totals"]
    cells = [
        ("Отгрузка", totals["otgruzka"], "#1565c0"),
        ("Оплачено", totals["oplachano"], "#2e7d32"),
        ("Возврат", totals["vozvrat"], "#c62828"),
        ("Перечисления", totals["perechisleniya"], "#2e7d32"),
        ("Бонус", totals["bonus"], "#ef6c00"),
    ]
    if report.get("show_boshqa"):
        cells.append(("Прочее", totals["boshqa"], "#6a1b9a"))

    tds = "".join(
        f"""<td style="padding:8px 12px;border:1px solid #d0d0d0;text-align:center;">
                <div style="font-size:11px;color:#666;">{label}</div>
                <div style="font-weight:bold;color:{color};">{_fmt_num(value)}</div>
            </td>"""
        for label, value, color in cells
    )

    party = frappe.utils.escape_html(report.get("party") or "")

    return f"""
    <div style="margin-bottom:12px;overflow-x:auto;">
        <table style="border-collapse:collapse;background:#fff;">
            <tr>
                <td style="padding:8px 12px;border:1px solid #d0d0d0;background:#f3f3f3;">
                    <div style="font-size:11px;color:#666;">Контрагент</div>
                    <div style="font-weight:bold;">{party}</div>
                </td>
                <td style="padding:8px 12px;border:1px solid #d0d0d0;text-align:center;">
                    <div style="font-size:11px;color:#666;">Сальдо на начало</div>
                    <div style="font-weight:bold;">{_fmt_num(report['opening'])}</div>
                </td>
                {tds}
                <td style="padding:8px 12px;border:1px solid #d0d0d0;text-align:center;background:#00e676;">
                    <div style="font-size:11px;color:#1b5e20;">Сальдо на конец</div>
                    <div style="font-weight:bold;">{_fmt_num(report['closing'])}</div>
                </td>
            </tr>
        </table>
    </div>
    """


# ──────────────────────────────────────────────────────────────────────────
#  Excel
# ──────────────────────────────────────────────────────────────────────────

def build_excel(report):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    fields = ["otgruzka", "oplachano", "vozvrat", "perechisleniya", "bonus"]
    labels = ["Отгрузка", "Оплачено", "Возврат", "Перечисления", "Бонус"]
    if report["show_boshqa"]:
        fields.append("boshqa")
        labels.append("Прочее")

    saldo_col = 2 + len(fields)  # A = sana, keyin ustunlar, oxiri Сальдо

    wb = Workbook()
    ws = wb.active
    ws.title = "Акт сверки"

    grey = PatternFill("solid", fgColor="BFBFBF")
    green = PatternFill("solid", fgColor="00E676")
    orange = PatternFill("solid", fgColor="FFC000")
    light_green = PatternFill("solid", fgColor="92D050")

    dashed = Side(style="dashed", color="4472C4")
    thin = Side(style="thin", color="808080")
    data_border = Border(left=dashed, right=dashed, top=dashed, bottom=dashed)
    head_border = Border(left=thin, right=thin, top=thin, bottom=thin)

    center = Alignment(horizontal="center", vertical="center")
    right = Alignment(horizontal="right", vertical="center")

    # ── 1-qator: ustun nomlari ────────────────────────────────────────────
    ws.cell(row=1, column=1).fill = grey
    ws.cell(row=1, column=1).border = head_border
    for idx, label in enumerate(labels, start=2):
        cell = ws.cell(row=1, column=idx, value=label)
        cell.fill = grey
        cell.font = Font(bold=True, size=10)
        cell.alignment = center
        cell.border = head_border

    saldo_head = ws.cell(row=1, column=saldo_col, value="Сальдо")
    saldo_head.fill = grey
    saldo_head.font = Font(bold=True, size=10)
    saldo_head.alignment = center
    saldo_head.border = head_border

    # ── 2-qator: «Дата» + jami отгрузка + kontragent + yopilish сальдо ───
    date_head = ws.cell(row=2, column=1, value="Дата")
    date_head.font = Font(bold=True, size=10)
    date_head.alignment = center
    date_head.border = head_border

    otgruzka_total = ws.cell(row=2, column=2, value=report["totals"]["otgruzka"])
    otgruzka_total.font = Font(bold=True, size=11, color="1F4E99")
    otgruzka_total.alignment = center
    otgruzka_total.number_format = NUM_FORMAT
    otgruzka_total.border = head_border

    ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=saldo_col - 1)
    party_cell = ws.cell(row=2, column=3, value=report.get("party") or "")
    party_cell.font = Font(size=11)
    party_cell.alignment = center
    for col in range(3, saldo_col):
        ws.cell(row=2, column=col).border = head_border

    closing = ws.cell(row=2, column=saldo_col, value=report["closing"])
    closing.fill = green
    closing.font = Font(bold=True, size=11)
    closing.alignment = center
    closing.number_format = NUM_FORMAT
    closing.border = head_border

    # ── Ma'lumot qatorlari ────────────────────────────────────────────────
    rows = report["rows"]
    for i, row in enumerate(rows):
        excel_row = 3 + i

        date_cell = ws.cell(row=excel_row, column=1, value=row["date_label"])
        date_cell.border = data_border
        date_cell.alignment = Alignment(horizontal="left", vertical="center")
        if i == 0:
            date_cell.fill = orange
            date_cell.font = Font(bold=True)
        elif i == len(rows) - 1:
            date_cell.fill = light_green
            date_cell.font = Font(bold=True)

        for idx, field in enumerate(fields, start=2):
            cell = ws.cell(row=excel_row, column=idx, value=row[field])
            cell.number_format = NUM_FORMAT
            cell.alignment = right
            cell.border = data_border

        saldo_cell = ws.cell(row=excel_row, column=saldo_col, value=row["saldo"])
        saldo_cell.number_format = NUM_FORMAT
        saldo_cell.alignment = right
        saldo_cell.border = data_border

    # ── Ko'rinish ─────────────────────────────────────────────────────────
    ws.column_dimensions["A"].width = 14
    for col in range(2, saldo_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16
    ws.freeze_panes = "A3"
    ws.sheet_view.showGridLines = False

    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
