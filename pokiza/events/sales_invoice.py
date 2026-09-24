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

    _kartochka_muzlat_va_stop(doc)


def _kartochka_muzlat_va_stop(doc) -> None:
    """Faza 3 (2026-09-24): submit oldidan har qatorga kartochka qiymatlarini
    MUZLATISH + partiya rejimidagi SKU'larda STOP tekshiruvi.

    Muzlatish (kartochkali mijozning har qatori): custom_norma,
    custom_tannarx_kg, custom_bonus_foiz_qator — keyin kartochka o'zgarsa
    ham tarixiy hisobot buzilmaydi.

    STOP (faqat partiya rejimidagi — has_batch_no yoqilgan SKU'lar):
    mijoz kartochkasidagi norma partiyasida yetarli qoldiq bo'lmasa schyot
    tasdiqlanMAYDI — omborda boshqa normadan tog' bo'lsa ham. Yetarli
    bo'lsa qatorga partiya avtomatik qo'yiladi (xodim partiya tanlamaydi,
    «ko'z aldansa ham dastur aldanmaydi»).
    """
    from pokiza.api.kartochka import aktiv_map
    from pokiza.api.partiya import (
        norma_qoldiqlar, partiya_ol, partiya_qoldiq, partiya_rejimda,
    )

    karta = aktiv_map(doc.customer)
    if not karta:
        return

    talab = {}      # batch -> jami so'ralgan kg (bir SKU 2 qatorda bo'lsa)
    xatolar = []

    for row in doc.get("items") or []:
        k = karta.get(row.item_code)
        if k:
            # --- muzlatish (partiya rejimidan qat'i nazar)
            row.custom_norma = k.norma
            row.custom_tannarx_kg = flt(k.tannarx)
            row.custom_bonus_foiz_qator = flt(
                k.bonus_foiz if flt(k.bonus_foiz) else k.umumiy_bonus
            )

        if not partiya_rejimda(row.item_code):
            continue

        # --- partiya rejimi: kartochka va norma majburiy
        if not k or not k.norma:
            xatolar.append(_(
                "<b>{0}</b> — {1} kartochkasida yo'q yoki normasi kiritilmagan. "
                "Partiya rejimidagi mahsulot kartochkasiz sotilmaydi."
            ).format(row.item_name or row.item_code, doc.customer_name or doc.customer))
            continue

        batch = partiya_ol(row.item_code, k.norma)
        row.use_serial_batch_fields = 1
        row.batch_no = batch
        if not doc.is_return:
            talab[(row.item_code, k.norma, batch)] = (
                talab.get((row.item_code, k.norma, batch), 0.0) + flt(row.stock_qty or row.qty)
            )

    for (item_code, norma, batch), kg in talab.items():
        qoldiq, _b = partiya_qoldiq(item_code, norma)
        if kg > qoldiq + 0.005:
            boshqa = norma_qoldiqlar(item_code)
            boshqa.pop(norma, None)
            boshqa_txt = (
                _("Omborda boshqa normadan bor: {0} — lekin bu mijozning normasi emas.")
                .format(", ".join(f"{n}: {flt(q, 1)} kg" for n, q in boshqa.items()))
                if boshqa else _("Omborda bu SKU'dan boshqa normada ham qoldiq yo'q.")
            )
            xatolar.append(_(
                "🔴 YETARLI QOLDIQ MAVJUD EMAS<br>"
                "<b>{0}</b> uchun <b>{1} / {2}</b> qoldig'i: <b>{3} kg</b>, "
                "so'ralgan: {4} kg.<br>{5}"
            ).format(
                doc.customer_name or doc.customer,
                frappe.utils.escape_html(item_code), frappe.utils.escape_html(norma),
                flt(qoldiq, 1), flt(kg, 1), boshqa_txt,
            ))

    if xatolar:
        frappe.throw(
            "<br><br>".join(xatolar),
            title=_("Pechat bloklandi — norma qoldig'i"),
        )


BONUS_REMARK = "Avto bonus"


def on_submit(doc, method=None) -> None:
    """Schyot tasdiqlanganda mijoz bonusini Journal Entry qilib avto yozish.

    Kartochkali mijoz (2026-09-24, Faza 3): summa = Σ(qator summasi ×
    qatorning MUZLATILGAN bonus foizi) — har SKU'ga o'z foizi.
    Kartochkasiz mijoz (eski usul): Customer.custom_bonus_foiz × schyot
    umumiy summasi.

    Dt «Бонус» (rasxod) / Kt Debtors (mijoz, schyotga bog'langan) —
    mijoz qarzi bonus summasiga kamayadi. Manfiy foiz = ustama (teskari
    yozuv, qarz oshadi). JE avto submit bo'ladi.
    """
    qatorlik = [
        r for r in (doc.get("items") or [])
        if r.get("custom_bonus_foiz_qator") is not None and flt(r.custom_bonus_foiz_qator)
    ]
    if qatorlik:
        summa = flt(sum(
            flt(r.base_amount) * flt(r.custom_bonus_foiz_qator) / 100
            for r in qatorlik
        ), 2)
        bonus = "qatorlik"
    else:
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
        "user_remark": (
            f"{BONUS_REMARK} (kartochka, SKU bo'yicha) — {doc.name}, {doc.customer_name or doc.customer}"
            if bonus == "qatorlik"
            else f"{BONUS_REMARK} {bonus}% — {doc.name}, {doc.customer_name or doc.customer}"
        ),
        "accounts": [debtors_qator, bonus_qator],
    })
    je.flags.ignore_permissions = True
    je.insert()
    je.submit()
    frappe.msgprint(
        _("Bonus {0} — {1} avto yozildi: {2}").format(
            _("(kartochka)") if bonus == "qatorlik" else f"{bonus}%",
            frappe.format_value(abs(summa), {"fieldtype": "Currency"}),
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
