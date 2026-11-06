import frappe
from frappe.utils import add_days, add_months, getdate, today

from pokiza.telegram.messages import AKT_SVERKA_EMPTY, AKT_SVERKA_ERROR, AKT_SVERKA_GENERATING, PERIOD_LABELS
from pokiza.telegram.sender import answer_callback_query, send_document, send_message


def _date_range(period_code: str) -> tuple[str, str]:
    t = getdate(today())
    if period_code == "2w":
        return str(add_days(t, -14)), str(t)
    elif period_code == "1m":
        return str(add_months(t, -1)), str(t)
    elif period_code == "3m":
        return str(add_months(t, -3)), str(t)
    else:
        return "2000-01-01", str(t)


def generate_akt_sverka_pdf(
    party_type: str,
    party_name: str,
    from_date: str,
    to_date: str,
) -> bytes | None:
    """Akt Sverka PDF bytes qaytaradi. Ma'lumot bo'lmasa None.

    Deskdagi «PDF юклаш» tugmasi bilan AYNAN bir xil kontekstni ishlatadi —
    shablon `rows` va `summary` kutadi. (Ilgari bu yerda `data` va tekis
    `opening_credit`/`kassa_*` kalitlari yuborilar, natijada PDF jadvali
    bo'sh chiqardi.)
    """
    from weasyprint import HTML as WeasyHTML
    from pokiza.pokiza_for_business.report.akt_sverka.akt_sverka import (
        _build_pdf_summary,
        _render_pdf_html,
        get_data,
    )

    filters = {
        "party_type": party_type,
        "party": party_name,
        "from_date": from_date,
        "to_date": to_date,
    }

    data = get_data(filters)

    # Faqat boshlang'ich qoldiq qatori bo'lsa — yuboradigan narsa yo'q
    if not data or len(data) <= 1:
        return None

    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )

    html = _render_pdf_html(data, filters, company, _build_pdf_summary(data))

    return WeasyHTML(string=html).write_pdf()


def handle_akt_sverka(
    chat_id: int,
    callback_query_id: str,
    period_code: str,
    party_type: str,
    party_name: str,
    display_name: str,
) -> None:
    """Background task: Akt Sverka PDF generatsiya va Telegram ga yuborish."""
    answer_callback_query(callback_query_id, "Hisobot tayyorlanmoqda...")
    send_message(chat_id, AKT_SVERKA_GENERATING)

    try:
        from_date, to_date = _date_range(period_code)
        pdf_bytes = generate_akt_sverka_pdf(party_type, party_name, from_date, to_date)

        if not pdf_bytes or len(pdf_bytes) < 1000:
            send_message(chat_id, AKT_SVERKA_EMPTY)
            return

        period_label = PERIOD_LABELS.get(period_code, period_code)
        caption = (
            f"📊 <b>Akt Sverka</b>\n"
            f"👤 {display_name}\n"
            f"📅 {from_date} — {to_date}\n"
            f"⏱ Davr: {period_label}"
        )
        filename = f"Akt_Sverka_{party_name}_{from_date}_{to_date}.pdf"
        send_document(chat_id, pdf_bytes, filename, caption)

    except Exception as e:
        frappe.log_error(str(e), "Pokiza Akt Sverka PDF xatosi")
        send_message(chat_id, AKT_SVERKA_ERROR)
