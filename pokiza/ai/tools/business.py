"""Pokiza'ga xos tez-tez so'raladigan ko'rsatkichlar uchun aniq tool'lar."""
import frappe
from frappe.utils import getdate, nowdate

from pokiza.ai.tools import MAX_ROWS, ToolError, rows_payload, tool


def _company(company=None):
    return company or frappe.defaults.get_user_default("Company")


def get_cash_balances(as_of_date=None, company=None):
    """Kassa va bank hisoblaridagi qoldiq (hisob valyutasida va UZS'da)."""
    rows = frappe.db.sql(
        """
        SELECT a.name AS account, a.account_type, a.account_currency,
            SUM(g.debit_in_account_currency - g.credit_in_account_currency) AS balance_account_currency,
            SUM(g.debit - g.credit) AS balance_company_currency
        FROM `tabAccount` a
        JOIN `tabGL Entry` g ON g.account = a.name AND g.is_cancelled = 0 AND g.posting_date <= %(d)s
        WHERE a.company = %(c)s AND a.is_group = 0 AND a.account_type IN ('Cash', 'Bank')
        GROUP BY a.name, a.account_type, a.account_currency
        HAVING ABS(balance_account_currency) > 0.005
        ORDER BY balance_company_currency DESC
        """,
        {"d": getdate(as_of_date or nowdate()), "c": _company(company)},
        as_dict=True,
    )
    return {"as_of_date": str(getdate(as_of_date or nowdate())), **rows_payload(rows)}


def get_party_balances(party_type, as_of_date=None, top=None, party=None, company=None):
    """Mijoz (debitorlik) yoki yetkazib beruvchi (kreditorlik) qoldiqlari GL bo'yicha."""
    if party_type not in ("Customer", "Supplier", "Employee", "Shareholder"):
        raise ToolError("party_type: Customer, Supplier, Employee yoki Shareholder")
    sign = "g.debit - g.credit" if party_type == "Customer" else "g.credit - g.debit"
    cond = "AND g.party = %(p)s" if party else ""
    rows = frappe.db.sql(
        f"""
        SELECT g.party, SUM({sign}) AS balance_uzs,
            MAX(g.posting_date) AS last_posting_date
        FROM `tabGL Entry` g
        WHERE g.party_type = %(pt)s AND g.company = %(c)s AND g.is_cancelled = 0
            AND g.posting_date <= %(d)s {cond}
        GROUP BY g.party
        HAVING ABS(balance_uzs) > 0.5
        ORDER BY balance_uzs DESC
        LIMIT %(lim)s
        """,
        {
            "pt": party_type,
            "c": _company(company),
            "d": getdate(as_of_date or nowdate()),
            "p": party,
            "lim": min(int(top or 50), MAX_ROWS),
        },
        as_dict=True,
    )
    total = frappe.db.sql(
        f"""SELECT SUM({sign}) FROM `tabGL Entry` g
        WHERE g.party_type = %(pt)s AND g.company = %(c)s AND g.is_cancelled = 0 AND g.posting_date <= %(d)s {cond}""",
        {"pt": party_type, "c": _company(company), "d": getdate(as_of_date or nowdate()), "p": party},
    )[0][0]
    return {
        "as_of_date": str(getdate(as_of_date or nowdate())),
        "sign_note": "musbat = ular bizga qarzdor" if party_type == "Customer" else "musbat = biz ularga qarzdormiz",
        "net_total_uzs": total,
        **rows_payload(rows),
    }


def get_production_queue(sana=None):
    """Berilgan kun uchun ishlab chiqarish navbati (Pokiza navbat moduli)."""
    from pokiza.api.navbat import get_navbat

    return get_navbat(sana=sana or nowdate())


def get_scale_list(sana=None):
    """Tarozi terminali ro'yxati: kun bo'yicha tortiladigan/tortilgan qatorlar."""
    from pokiza.api.navbat import tarozi_royxat

    return tarozi_royxat(sana=sana or nowdate())


def get_defect_list(sana=None):
    """Brak ro'yxati."""
    from pokiza.api.navbat import brak_royxat

    return brak_royxat(sana=sana or nowdate())


DATE = {"type": "string", "description": "YYYY-MM-DD, berilmasa bugun"}

TOOLS = [
    (
        tool(
            "get_cash_balances",
            "Kassa va bank hisoblaridagi pul qoldig'i (hisob valyutasida va UZS'da), sana holatiga.",
            {"as_of_date": DATE, "company": {"type": "string"}},
        ),
        get_cash_balances,
    ),
    (
        tool(
            "get_party_balances",
            "GL bo'yicha qarzdorlik: Customer — mijozlar bizga qarzi, Supplier — biz yetkazib beruvchilarga qarzimiz. "
            "Eng kattasidan tartiblangan, jami (net_total_uzs) bilan.",
            {
                "party_type": {"type": "string", "enum": ["Customer", "Supplier", "Employee", "Shareholder"]},
                "as_of_date": DATE,
                "top": {"type": "integer", "description": "Nechta qator (standart 50, max 200)"},
                "party": {"type": "string", "description": "Bitta kontragent nomi (ixtiyoriy)"},
                "company": {"type": "string"},
            },
            ["party_type"],
        ),
        get_party_balances,
    ),
    (
        tool(
            "get_production_queue",
            "Bitta kunning ishlab chiqarish navbati: zakazlar, mijozlar, kg, sig'im, mahsulot kesimi.",
            {"sana": DATE},
        ),
        get_production_queue,
    ),
    (
        tool("get_scale_list", "Tarozi ro'yxati: kun bo'yicha tortish holati (reja kg / fakt kg).", {"sana": DATE}),
        get_scale_list,
    ),
    (
        tool("get_defect_list", "Brak (yaroqsiz mahsulot) ro'yxati.", {"sana": DATE}),
        get_defect_list,
    ),
]
