"""Ma'lumot himoyasi: xodim AI orqali ma'lumotni ko'p yig'ib olib chiqib ketmasin.

Hammasi ERP'dan sozlanadi — Nazorat Bot Sozlamalari → "Ma'lumot himoyasi":
- himoya_excel_xodim: xodimlar (to'liq ruxsatsiz rollar) AI'dan Excel/PDF fayl ola oladimi (standart — yo'q);
- himoya_forward / himoya_rahbarga: bot yuborgan xabar va fayllarni forward qilish/saqlash taqiqi (Telegram protect_content);
- himoya_kop_fayl / himoya_kop_savol: xodim bir kunda shuncha fayl / savoldan oshsa — rahbarga xabar (0 — o'chiq).
"""
import frappe
from frappe.utils import nowdate

from pokiza.nazorat.tg import config


def excel_xodimga():
    return bool(config.sozlama("himoya_excel_xodim", 0))


def forward_taqiq(chat_id):
    """Shu chatga ketadigan xabar himoyalansinmi (forward/saqlash yo'q)."""
    if not config.sozlama("himoya_forward", 1):
        return False
    rol = frappe.db.get_value("TG Azo", {"telegram_id": str(chat_id)}, "rol")
    if rol == "Rahbar":
        return bool(config.sozlama("himoya_rahbarga", 0))
    return True


def _cheklanganmi(user):
    """Rahbar va administratorlar kuzatilmaydi."""
    from pokiza.nazorat.scope import rahbarmi

    return not rahbarmi(user)


def qayd(tur, izoh=None, user=None):
    """Xodimning kunlik fayl / savol sonini hisoblaydi; chegaraga yetganda rahbarlarga bir marta xabar.
    tur: "fayl" | "savol". Xato bo'lsa jim (AI javobini to'xtatmasin)."""
    try:
        user = user or frappe.session.user
        if not user or user in ("Guest", "Administrator") or not _cheklanganmi(user):
            return
        chegara = int(config.sozlama("himoya_kop_fayl" if tur == "fayl" else "himoya_kop_savol", 0) or 0)
        if chegara <= 0:
            return
        k = frappe.cache.make_key(f"nz_himoya:{nowdate()}:{tur}:{user}")
        n = frappe.cache.incr(k)
        frappe.cache.expire(k, 2 * 86400)
        if n != chegara:
            return
        _rahbarga(user, tur, n, izoh)
    except Exception:
        frappe.log_error(title="Nazorat: ma'lumot himoyasi qaydi")


def _rahbarga(user, tur, n, izoh):
    from pokiza.nazorat.scope import rahbarlar
    from pokiza.nazorat.tg.format import esc
    from pokiza.nazorat.tg.sender import TgXato, send_message

    if not config.faol():
        return
    ism = frappe.db.get_value("User", user, "full_name") or user
    nima = f"AI'dan {n} ta fayl oldi" if tur == "fayl" else f"AI'ga {n} ta savol berdi"
    matn = (f"⚠️ <b>Diqqat</b>: {esc(ism)} bugun {nima}."
            + (f"\nOxirgisi: <i>{esc(izoh[:200])}</i>" if izoh else "")
            + "\n\nSuhbatlar ERP'da: AI Suhbat ro'yxati. Kerak bo'lsa botda 👥 Xodimlar orqali AI ruxsatini o'chiring.")
    for r in rahbarlar():
        tid = frappe.db.get_value("TG Azo", {"user": r, "faol": 1}, "telegram_id")
        if tid:
            try:
                send_message(tid, matn)
            except TgXato:
                pass
