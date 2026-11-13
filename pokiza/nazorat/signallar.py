"""Ish signallari: oxirgi ish kuni bo'yicha nima kiritilmagan / tasdiqlanmagan (raqamsiz).

Har kuni 09:00 shaxsiy chatga: har mas'ul xodimga faqat o'ziga tegishli signallar, rahbarga hammasi.
Mas'ul — shu signalga tegishli ko'rsatkichni ko'radigan roldagi xodimlar (rol nomlari ERP'da o'zgarsa ham ishlaydi).
"""
import frappe
from frappe.utils import getdate, nowdate

from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.format import esc
from pokiza.nazorat.tg.sender import TgXato, send_message

# signal -> qaysi ko'rsatkichni ko'radigan rollar mas'ul
SIGNAL_KODLAR = {"sotuv": {"A2", "H1", "K1"}, "xarid": {"C1"}, "kassa": {"K3"}, "ishlab": {"A1", "H3", "K2"}}


def masullar(signal):
    """Shu signalga mas'ul xodimlar (TG Azo user'lari)."""
    from pokiza.nazorat.scope import kodni_koradigan_rollar

    rollar = kodni_koradigan_rollar(SIGNAL_KODLAR[signal])
    if not rollar:
        return []
    return frappe.get_all("TG Azo", filters={"faol": 1, "bolim": ["in", rollar], "rol": "Xodim"}, pluck="user")


def _qoralama(doctype, sana_field, gacha):
    return frappe.db.sql(f"SELECT COUNT(*), MIN(`{sana_field}`) FROM `tab{doctype}` WHERE docstatus = 0 AND `{sana_field}` <= %s",
                         (gacha,))[0]


def _bor(doctype, sana_field, sana):
    return frappe.db.sql(f"SELECT COUNT(*) FROM `tab{doctype}` WHERE docstatus = 1 AND `{sana_field}` = %s", (sana,))[0][0]


def signallar(bugun=None):
    """(sana, [(signal, matn)]) — oxirgi ish kuni bo'yicha nima kiritilmagan / tasdiqlanmagan."""
    from pokiza.nazorat.reports import oxirgi_ish_kuni

    d = oxirgi_ish_kuni(bugun)
    out = []
    n, eng = _qoralama("Sales Invoice", "posting_date", d)
    if n:
        out.append(("sotuv", f"🧾 {n} ta sotuv fakturasi tasdiqlanmagan (eng eskisi {getdate(eng):%d.%m})"))
    n, eng = _qoralama("Purchase Invoice", "posting_date", d)
    if n:
        out.append(("xarid", f"📥 {n} ta xarid fakturasi tasdiqlanmagan (eng eskisi {getdate(eng):%d.%m})"))
    n, eng = _qoralama("Kassa", "date", d)
    if n:
        out.append(("kassa", f"💵 {n} ta kassa hujjati tasdiqlanmagan (eng eskisi {getdate(eng):%d.%m})"))
    if not _bor("Production Entry", "posting_date", d):
        out.append(("ishlab", f"🏭 {d:%d.%m} uchun ishlab chiqarish kiritilmagan"))
    if not _bor("Kassa", "date", d):
        out.append(("kassa", f"💵 {d:%d.%m} uchun kassa yozuvi yo'q"))
    return d, out


def _ismlar(users):
    return ", ".join(frappe.db.get_value("User", u, "full_name") or u for u in users) or "mas'ul belgilanmagan"


def signallar_royxati(bugun=None):
    """AI uchun: (sana, [matn — mas'ullar])."""
    d, rows = signallar(bugun)
    return d, [f"{matn} — {_ismlar(masullar(sig))}" for sig, matn in rows]


def ish_signallari():
    """09:00 — shaxsiy chatga: mas'ulga o'z signallari, rahbarga hammasi (mas'ullar nomi bilan)."""
    if not config.faol() or not config.sozlama("guruh_signallari", 1):
        return
    from pokiza.nazorat.scope import rahbarlar

    d, rows = signallar()
    if not rows:
        return
    kimga = {}
    kesh = {}
    for sig, matn in rows:
        if sig not in kesh:
            kesh[sig] = masullar(sig)
        for u in kesh[sig]:
            kimga.setdefault(u, []).append(matn)
    for u in rahbarlar():
        kimga[u] = [f"{matn} — {esc(_ismlar(kesh[sig]))}" for sig, matn in rows]
    bugun = nowdate()
    for user, qatorlar in kimga.items():
        tid = frappe.db.get_value("TG Azo", {"user": user, "faol": 1}, "telegram_id")
        if not tid or not config.bir_marta(f"ish_signallari:{bugun}:{tid}"):
            continue
        try:
            send_message(tid, f"⚠️ <b>Kiritilishi kerak</b> ({d:%d.%m} holatiga)\n\n" + "\n".join(qatorlar))
        except TgXato as e:
            config.bosh_qoy(f"ish_signallari:{bugun}:{tid}")
            frappe.log_error(title="Nazorat: ish signallari", message=str(e))
