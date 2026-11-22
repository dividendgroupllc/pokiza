"""Darhol signallar: rahbar pul (dividend) olganda yoki bekor qilinganda (TZ C5/K4)."""
import frappe
from frappe.utils import flt, get_first_day

from pokiza.nazorat.tg import config


def kassa_on_submit(doc, method=None):
    _navbat(doc, "submit")


def kassa_on_cancel(doc, method=None):
    _navbat(doc, "cancel")


def _navbat(doc, amal):
    from pokiza.pokiza_for_business.doctype.kassa.kassa import is_dividend_party_type

    if not is_dividend_party_type(doc.party_type) or not config.faol():
        return
    frappe.enqueue("pokiza.nazorat.events.dividend_xabar", queue="short", enqueue_after_commit=True,
                   kassa=doc.name, amal=amal)


def dividend_xabar(kassa, amal="submit"):
    from pokiza.nazorat.metrics import compute
    from pokiza.nazorat.tg.format import esc, son, summa

    k = frappe.db.get_value("Kassa", kassa, ["name", "date", "party_type", "party_name", "amount",
                                             "cash_account_currency", "transaction_type", "remarks"], as_dict=True)
    if not k:
        return
    s = frappe.get_cached_doc("Nazorat Sozlamalari")
    egasi = {"Дивиденд 1": s.dividend_1_egasi, "Дивиденд 2": s.dividend_2_egasi,
             "Дивиденд 3": s.dividend_3_egasi}.get(k.party_type) or k.party_type
    oy = compute("C5", f"{get_first_day(k.date)}:{k.date}", full=False)["fakt"]
    belgi = "💸" if amal == "submit" else "↩️"
    sarlavha = "Rahbar pul oldi" if amal == "submit" else "Dividend hujjati BEKOR qilindi"
    if k.transaction_type == "Приход":
        sarlavha = "Dividend qaytarildi (kassaga kirim)" if amal == "submit" else "Dividend qaytarish bekor qilindi"
    matn = (f"{belgi} <b>{sarlavha}</b>\n"
            f"{esc(egasi)}: <b>{son(flt(k.amount))} {esc(k.cash_account_currency or '')}</b>\n"
            f"Sana: {k.date:%d.%m.%Y} · {esc(k.name)}\n"
            + (f"Izoh: {esc((k.remarks or '')[:200])}\n" if k.remarks else "")
            + f"Oy boshidan jami dividend: {summa(oy)} so'm")
    _tarqat(f"dividend:{amal}:{kassa}", matn)


def _tarqat(kalit, matn):
    """Dividendni ko'ra oladiganlarning (C5 ruxsati) shaxsiy chatiga, har biriga bir marta."""
    from pokiza.nazorat.jadval import yubor_bir
    from pokiza.nazorat.scope import azo_bolimi, ruxsat_kodlar

    # 08:00 hisobot belgisiga bog'liq emas: dividendni ko'ra oladigan har bir faol a'zoga
    for a in frappe.get_all("TG Azo", filters={"faol": 1, "telegram_id": ["is", "set"]},
                            fields=["name", "user", "telegram_id", "faol"]):
        if "C5" in ruxsat_kodlar(azo_bolimi(a)):
            yubor_bir(f"{kalit}:{a.telegram_id}", "dividend", a.telegram_id, matn)


# ---------- Journal Entry orqali to'g'ridan-to'g'ri kiritilgan dividend (Kassa'siz) ----------
HISOB_EGASI = {"3200": "Дивиденд 1", "3201": "Дивиденд 2", "3202": "Дивиденд 3"}


def _dividend_qatorlar(doc):
    out = []
    for a in doc.get("accounts") or []:
        num = frappe.get_cached_value("Account", a.account, "account_number")
        if num in HISOB_EGASI:
            out.append((num, flt(a.debit) - flt(a.credit)))
    return out


def je_on_submit(doc, method=None):
    _je_navbat(doc, "submit")


def je_on_cancel(doc, method=None):
    _je_navbat(doc, "cancel")


def _je_navbat(doc, amal):
    if not config.faol():
        return
    if doc.get("cheque_no") and frappe.db.exists("Kassa", doc.cheque_no):
        return  # Kassa'dan yaratilgan — xabar Kassa orqali ketadi
    if not _dividend_qatorlar(doc):
        return
    frappe.enqueue("pokiza.nazorat.events.dividend_je_xabar", queue="short", enqueue_after_commit=True,
                   je=doc.name, amal=amal)


def dividend_je_xabar(je, amal="submit"):
    from pokiza.nazorat.metrics import compute
    from pokiza.nazorat.tg.format import esc, summa

    doc = frappe.get_doc("Journal Entry", je)
    s = frappe.get_cached_doc("Nazorat Sozlamalari")
    egalar = {"Дивиденд 1": s.dividend_1_egasi, "Дивиденд 2": s.dividend_2_egasi, "Дивиденд 3": s.dividend_3_egasi}
    jamlar = {}
    for num, summa_ in _dividend_qatorlar(doc):
        jamlar[num] = jamlar.get(num, 0) + summa_
    oy = compute("C5", f"{get_first_day(doc.posting_date)}:{doc.posting_date}", full=False)["fakt"]
    belgi, sarlavha = ("💸", "Rahbar pul oldi (Journal Entry)") if amal == "submit" else ("↩️", "Dividend provodkasi BEKOR qilindi")
    qatorlar = []
    for num, v in jamlar.items():
        pt = HISOB_EGASI[num]
        qatorlar.append(f"{esc(egalar.get(pt) or pt)}: <b>{summa(abs(v))} so'm</b>" + (" (qaytarildi)" if v < 0 else ""))
    matn = (f"{belgi} <b>{sarlavha}</b>\n" + "\n".join(qatorlar)
            + f"\nSana: {doc.posting_date:%d.%m.%Y} · {esc(doc.name)}\n"
            + (f"Izoh: {esc((doc.user_remark or '')[:200])}\n" if doc.user_remark else "")
            + f"Oy boshidan jami dividend: {summa(oy)} so'm")
    _tarqat(f"dividend_je:{amal}:{je}", matn)
