"""Rejali yuborish (hooks.py scheduler_events.cron): 08:00 kunlik, dushanba haftalik, 1-sana oylik.

Har yuborish avval `Nazorat Yuborish` jurnaliga kalit bilan yoziladi (claim): kalit band bo'lsa — qayta
yuborilmaydi (scheduler ikki marta ishlasa ham). Xato bo'lsa holat=Xato; `qayta(turi)` qayta yuboradi.
"""
import frappe

from pokiza.nazorat.reports import davr_for, hisobot
from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.sender import TgXato, send_message



def qabul_qiluvchilar(turi=None):
    """[(chat_id, bolim)] — hisobotlar faqat SHAXSIY chatlarga: rahbar(lar) to'liq, xodimlar o'z bo'limi bo'yicha
    (TG Azo "08:00 hisobotlari" belgisi bilan)."""
    from pokiza.nazorat.scope import azo_bolimi

    out = []
    for a in frappe.get_all("TG Azo", filters={"faol": 1},
                            fields=["name", "telegram_id", "rol", "bolim", "faol", "hisobot_olsin"]):
        if a.rol != "Rahbar" and not a.hisobot_olsin:
            continue
        bolim = azo_bolimi(a)
        if a.telegram_id and bolim:
            out.append((a.telegram_id, bolim))
    return out


def _claim(kalit, turi, chat_id):
    if frappe.db.exists("Nazorat Yuborish", kalit):
        return False
    try:
        frappe.get_doc({"doctype": "Nazorat Yuborish", "kalit": kalit, "turi": turi, "chat_id": str(chat_id),
                        "holat": "Yuborilmoqda"}).insert(ignore_permissions=True)
        frappe.db.commit()
        return True
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        return False


def _belgila(kalit, holat, message_id=None, xato=None):
    frappe.db.set_value("Nazorat Yuborish", kalit, {"holat": holat, "message_id": message_id, "xato": xato})
    frappe.db.commit()


def yubor_bir(kalit, turi, chat_id, matn, reply_markup=None):
    """Claim -> yubor -> belgila. True — yuborildi."""
    if not _claim(kalit, turi, chat_id):
        return False
    try:
        mid = send_message(chat_id, matn, reply_markup=reply_markup)
        _belgila(kalit, "Yuborildi", message_id=mid)
        return True
    except TgXato as e:
        _belgila(kalit, "Xato", xato=str(e)[:500])
        return False
    except Exception as e:
        frappe.db.rollback()
        _belgila(kalit, "Xato", xato=f"{type(e).__name__}: {str(e)[:400]}")
        frappe.log_error(title="Nazorat: hisobot yuborilmadi")
        return False


def yubor(turi):
    if not config.faol():
        return
    d = davr_for(turi)
    natija = {}
    for chat_id, bolim in qabul_qiluvchilar(turi):
        try:
            matn, kb = hisobot(turi, bolim, d=d)
        except Exception:
            frappe.log_error(title=f"Nazorat {turi} hisobot")
            continue
        if not matn:
            continue
        ok = yubor_bir(f"{turi}:{d.kalit}:{chat_id}", turi, chat_id, matn, kb)
        natija[chat_id] = ok
    return natija


def kunlik():
    yubor("kunlik")


def haftalik():
    yubor("haftalik")


def oylik():
    yubor("oylik")


def tolov_intizomi():
    """11-sana 09:00 — o'tgan oy postavshik va mijoz to'lovlari bo'yicha YAKUNIY holat (to'lov oynasi 10-sanada
    yopiladi; 1-sanadagi oylik hisobotda bu ikki ko'rsatkich hali to'liq emas)."""
    from datetime import timedelta

    from frappe.utils import getdate, nowdate

    from pokiza.nazorat.metrics import Davr, compute
    from pokiza.nazorat.reports import _sub
    from pokiza.nazorat.scope import ruxsat_kodlar
    from pokiza.nazorat.tg.format import belgi, eslatmalar, esc, kpi_qator, qisqa

    if not config.faol():
        return
    bugun = getdate(nowdate())
    p = bugun.replace(day=1) - timedelta(days=1)
    d = Davr.oy(p.year, p.month, bugun)
    natija_kesh = {}
    for chat_id, bolim in qabul_qiluvchilar():
        kodlar = [c for c in ("C1", "C2") if c in ruxsat_kodlar(bolim)]
        if not kodlar:
            continue
        lines = ["<b>💳 To'lov intizomi</b>", f"<i>{esc(d.nom)} — 10-sanagacha to'lovlar bilan yakuniy</i>", ""]
        izoh, tugma = [], []
        for c in kodlar:
            if c not in natija_kesh:
                try:
                    natija_kesh[c] = compute(c, d, full=True, bugun=bugun)
                except Exception:
                    frappe.log_error(title=f"Nazorat to'lov intizomi: {c}")
                    natija_kesh[c] = {"code": c, "mavjud": False, "sabab": "hisoblashda xato"}
            m = natija_kesh[c]
            lines.append(kpi_qator(m))
            sub = _sub(m) if m.get("mavjud") is not False else ""
            if sub:
                lines.append(f"      <i>{sub}</i>")
            izoh += m.get("izoh") or []
            if m.get("mavjud") is not False:
                tugma.append({"text": f"{belgi(m)} {qisqa(c)}", "callback_data": f"k:{c}:{d.kalit}"})
        if izoh:
            lines += ["", eslatmalar(izoh)]
        yubor_bir(f"tolov:{d.kalit}:{chat_id}", "oylik", chat_id, "\n".join(lines),
                  {"inline_keyboard": [tugma]} if tugma else None)


def jim_mijozlar_signal():
    """Har kuni 09:00 — bugun jim bo'lib qolgan mijozlar (oxirgi xariddan aynan N kun o'tgan; TZ: darhol aloqa).
    Jimlik ko'rsatkichini ko'radigan xodimlarning shaxsiy chatiga. Har mijoz faqat bir marta (jim bo'lgan kuni)."""
    from frappe.utils import add_days, getdate, nowdate

    from pokiza.nazorat.scope import azo_bolimi, ruxsat_kodlar
    from pokiza.nazorat.tg.format import esc

    if not config.faol():
        return
    s = frappe.get_cached_doc("Nazorat Sozlamalari")
    n = int(s.mijoz_jimlik_kun or 7)
    bugun = getdate(nowdate())
    rows = frappe.db.sql(
        """SELECT customer, MAX(customer_name) nom, MAX(posting_date) oxirgi FROM `tabSales Invoice`
        WHERE docstatus = 1 AND is_return = 0 AND posting_date BETWEEN %s AND %s
        GROUP BY customer HAVING MAX(posting_date) = %s ORDER BY nom""",
        (add_days(bugun, -90), bugun, add_days(bugun, -n)), as_dict=True)
    if not rows:
        return
    matn = [f"📵 <b>{len(rows)} ta mijoz {n} kundan beri buyurtma bermadi</b>",
            f"<i>Oxirgi xarid: {getdate(add_days(bugun, -n)):%d.%m} — bugun aloqaga chiqing</i>", ""]
    matn += [f"• {esc(r.nom or r.customer)}" for r in rows[:25]]
    if len(rows) > 25:
        matn.append(f"… va yana {len(rows) - 25} ta")
    for a in frappe.get_all("TG Azo", filters={"faol": 1}, fields=["name", "telegram_id", "rol", "bolim", "faol"]):
        if a.telegram_id and "H4" in ruxsat_kodlar(azo_bolimi(a)):
            yubor_bir(f"jim:{bugun}:{a.telegram_id}", "kunlik", a.telegram_id, "\n".join(matn))


def qayta(turi):
    """Xato bo'lganlarini (va 30 daqiqadan beri "Yuborilmoqda"da qotib qolganlarini) qayta yuborish:
    bench --site X execute pokiza.nazorat.jadval.qayta --args "['kunlik']" """
    from frappe.utils import add_to_date, now_datetime

    d = davr_for(turi)
    kalit = ["like", f"{turi}:{d.kalit}:%"]
    xato = frappe.get_all("Nazorat Yuborish", filters={"turi": turi, "holat": "Xato", "kalit": kalit}, pluck="name")
    qotgan = frappe.get_all("Nazorat Yuborish", filters={"turi": turi, "holat": "Yuborilmoqda", "kalit": kalit,
                                                          "creation": ["<", add_to_date(now_datetime(), minutes=-30)]},
                            pluck="name")
    for n in xato + qotgan:
        frappe.delete_doc("Nazorat Yuborish", n, ignore_permissions=True)
    frappe.db.commit()
    return yubor(turi)
