"""Sales Invoice doc_events: narxsiz sotuvni bloklash.

Schyot qatoridagi tovar "Сотув махсулотлари" guruhidan bo'lsa va shu
qatordagi narxi (rate) 0 bo'lsa, schyot submit bo'lmaydi. Schyotning
o'zida narx qo'yilsa — bemalol o'tadi.
"""

import frappe
from frappe import _
from frappe.utils import flt

NARX_GURUHI = "Сотув махсулотлари"


def before_submit(doc, method=None) -> None:
    """'Сотув махсулотлари' guruhidagi tovar narxi 0 bo'lsa submit'ni to'xtatish."""
    narxsiz = []
    for row in doc.get("items") or []:
        if not row.item_code or flt(row.rate):
            continue
        item_group = frappe.get_cached_value("Item", row.item_code, "item_group")
        if item_group == NARX_GURUHI:
            narxsiz.append(row.item_code)

    if narxsiz:
        royxat = "".join(f"<li><b>{frappe.utils.escape_html(i)}</b></li>"
                         for i in sorted(set(narxsiz)))
        frappe.throw(
            _("Quyidagi tovarlarning narxi 0 — schyotni tasdiqlab bo'lmaydi. "
              "Avval qatordagi narxni kiriting:")
            + f"<ul>{royxat}</ul>",
            title=_("Narx kiritilmagan"),
        )


BONUS_REMARK = "Avto bonus"


def on_submit(doc, method=None) -> None:
    """Schyot tasdiqlanganda mijoz bonusini Journal Entry qilib avto yozish.

    Summa = Customer.custom_bonus_foiz × schyot umumiy summasi.
    Dt «Бонус» (rasxod) / Kt Debtors (mijoz, schyotga bog'langan) —
    mijoz qarzi bonus summasiga kamayadi. Manfiy foiz = ustama (teskari
    yozuv, qarz oshadi). JE avto submit bo'ladi.
    """
    bonus = flt(frappe.get_cached_value("Customer", doc.customer, "custom_bonus_foiz"))
    summa = flt(doc.base_grand_total * bonus / 100, 2)
    if not summa:
        return

    bonus_account = frappe.db.get_value(
        "Account", {"account_name": "Бонус", "company": doc.company, "is_group": 0}
    )
    if not bonus_account:
        frappe.throw(
            _("«Бонус» nomli rasxod accounti topilmadi ({0}). "
              "Avval Chart of Accounts'da yarating.").format(doc.company),
            title=_("Bonus accounti yo'q"),
        )

    debtors_qator = {
        "account": doc.debit_to,
        "party_type": "Customer",
        "party": doc.customer,
    }
    if summa > 0:
        # Bonus: mijoz qarzi kamayadi, schyotga to'lov sifatida bog'lanadi
        debtors_qator.update({
            "credit_in_account_currency": summa,
            "reference_type": "Sales Invoice",
            "reference_name": doc.name,
        })
        bonus_qator = {"account": bonus_account, "debit_in_account_currency": summa}
    else:
        # Ustama (manfiy foiz): mijoz qarzi oshadi.
        # ERPNext debit qatorni Sales Invoice'ga bog'lashga ruxsat bermaydi —
        # bog'liqlik cheque_no (Reference No) orqali saqlanadi.
        debtors_qator["debit_in_account_currency"] = -summa
        bonus_qator = {"account": bonus_account, "credit_in_account_currency": -summa}

    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Journal Entry",
        "company": doc.company,
        "posting_date": doc.posting_date,
        "cheque_no": doc.name,
        "cheque_date": doc.posting_date,
        "user_remark": f"{BONUS_REMARK} {bonus}% — {doc.name}, {doc.customer_name or doc.customer}",
        "accounts": [debtors_qator, bonus_qator],
    })
    je.flags.ignore_permissions = True
    je.insert()
    je.submit()
    frappe.msgprint(
        _("Bonus {0}% — {1} avto yozildi: {2}").format(
            bonus, frappe.format_value(abs(summa), {"fieldtype": "Currency"}),
            frappe.utils.get_link_to_form("Journal Entry", je.name),
        ),
        alert=True, indicator="green",
    )


def before_cancel(doc, method=None) -> None:
    """Schyot bekor qilinsa, unga avto yozilgan bonus JE ham bekor bo'ladi."""
    je_lar = frappe.get_all(
        "Journal Entry",
        filters={
            "cheque_no": doc.name,
            "docstatus": 1,
            "user_remark": ["like", f"{BONUS_REMARK}%"],
        },
        pluck="name",
    )
    for nomi in je_lar:
        je = frappe.get_doc("Journal Entry", nomi)
        je.flags.ignore_permissions = True
        je.cancel()
