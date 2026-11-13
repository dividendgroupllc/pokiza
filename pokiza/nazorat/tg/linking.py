"""Telegram akkauntni ERP foydalanuvchiga ulash: bir martalik kod (10 daqiqa), deep link t.me/<bot>?start=<kod>.

Telefon raqam bilan emas — kod faqat ERP'ga kirgan foydalanuvchining o'ziga beriladi.
"""
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime

from pokiza.nazorat.tg import config

KOD_TTL = 600
URINISH_LIMIT = 5  # soatiga noto'g'ri kod


def _key(kod):
    return f"nazorat_tg_kod:{kod}"


def _taxminiy_rol(user):
    """Xodimning ERP rollari bo'yicha Nazorat Roli taklifi (Nazorat Roli → "ERP rollari" jadvali)."""
    rollar = set(frappe.get_roles(user))
    for r in frappe.get_all("Nazorat Roli ERP Roli", filters={"parenttype": "Nazorat Roli"}, fields=["parent", "role"],
                            order_by="parent asc"):
        if r.role in rollar:
            return r.parent
    return None


def _boshqaruvchi():
    """Boshqa xodimlar uchun kod yarata oladiganlar: System Manager yoki nazorat rahbari."""
    u = frappe.session.user
    return u == "Administrator" or "System Manager" in frappe.get_roles(u) or config.rahbar_user() == u


def _admin(u=None):
    u = u or frappe.session.user
    return u == "Administrator" or "System Manager" in frappe.get_roles(u)


def _tizim_useri(user):
    return user not in ("Guest", "Administrator") and frappe.db.get_value(
        "User", user, ["user_type", "enabled"], as_dict=True) or None


@frappe.whitelist()
def tg_holat(user=None):
    """User sahifasi uchun: tugma ko'rsatilsinmi va ulanish holati. Ruxsat bo'lmasa None (xato chiqarmaydi)."""
    user = user or frappe.session.user
    u = _tizim_useri(user)
    if not u or u.user_type != "System User" or not u.enabled:
        return None
    oziniki = user == frappe.session.user
    if not oziniki and not _boshqaruvchi():
        return None
    azo = frappe.db.get_value("TG Azo", user, ["telegram_id", "ism", "username", "bolim", "rol", "faol", "ulangan"],
                              as_dict=True)
    from pokiza.nazorat.scope import rollar

    taxmin = None if (azo and azo.bolim) else _taxminiy_rol(user)
    return {"oziniki": oziniki, "admin": _boshqaruvchi(), "bot_faol": config.faol(), "bolimlar": rollar(),
            "azo": azo, "taxminiy_bolim": taxmin}


@frappe.whitelist()
def kod_yarat(user=None, bolim=None):
    """Bir martalik ulash kodi. user — boshqa xodim uchun (faqat admin/rahbar); bolim — o'sha xodimning bo'limi."""
    target = user or frappe.session.user
    if target != frappe.session.user and not _boshqaruvchi():
        frappe.throw(_("Boshqa foydalanuvchi uchun kod faqat administrator yoki rahbar yarata oladi"),
                     frappe.PermissionError)
    admin = _admin()
    if target != frappe.session.user and not admin:
        # rahbar (administrator emas): administratorlar va allaqachon ulangan akkauntlar uchun kod yaratolmaydi
        if _admin(target):
            frappe.throw(_("Administrator akkaunti uchun kodni faqat administrator yaratadi"), frappe.PermissionError)
        if frappe.db.get_value("TG Azo", target, "telegram_id"):
            frappe.throw(_("Bu xodim Telegram'ga ulangan. Qayta ulashni faqat administrator qiladi"),
                         frappe.PermissionError)
    u = _tizim_useri(target)
    if not u or u.user_type != "System User" or not u.enabled:
        frappe.throw(_("Faqat faol tizim foydalanuvchisi Telegram'ga ulana oladi"), frappe.PermissionError)
    if bolim and (not frappe.db.exists("Nazorat Roli", bolim) or not _boshqaruvchi()):
        frappe.throw(_("Bo'limni faqat administrator yoki rahbar belgilaydi"))
    if not config.faol():
        frappe.throw(_("Nazorat boti hali yoqilmagan (Nazorat Bot Sozlamalari)"))
    kod = secrets.token_urlsafe(9)
    frappe.cache.set_value(_key(kod), {"user": target, "bolim": bolim or None, "admin": admin,
                                       "oziniki": target == frappe.session.user}, expires_in_sec=KOD_TTL)
    bot = config.username()
    return {"kod": kod, "bot": bot, "link": f"https://t.me/{bot}?start={kod}" if bot else None,
            "daqiqa": KOD_TTL // 60, "user": target}


def ulash(kod, tg_user):
    """(ok, matn). tg_user — Telegram 'from' obyekti."""
    tid = str(tg_user["id"])
    fail_key = f"nazorat_tg_fail:{tid}"
    fails = int(frappe.cache.get_value(fail_key, expires=True) or 0)
    if fails >= URINISH_LIMIT:
        return False, "Juda ko'p noto'g'ri urinish. 1 soatdan keyin qayta urinib ko'ring."
    v = frappe.cache.get_value(_key(kod), expires=True) if kod else None
    user, bolim = (v.get("user"), v.get("bolim")) if isinstance(v, dict) else (v, None)
    if not user:
        frappe.cache.set_value(fail_key, fails + 1, expires_in_sec=3600)
        return False, ("Kod noto'g'ri yoki muddati o'tgan. ERP'da profilingizni oching → "
                       "<b>Telegram'ga ulash</b> tugmasini bosing va yangi havoladan kiring.")
    frappe.cache.delete_value(_key(kod))  # bir martalik

    band = frappe.db.get_value("TG Azo", {"telegram_id": tid}, "name")
    if band and band != user:
        return False, "Bu Telegram akkaunt boshqa ERP foydalanuvchiga ulangan. Administratorga murojaat qiling."
    eski = frappe.db.get_value("TG Azo", user, "telegram_id")
    if eski and eski != tid and not (isinstance(v, dict) and (v.get("admin") or v.get("oziniki"))):
        return False, "Bu ERP foydalanuvchi boshqa Telegram akkauntga ulangan. Qayta ulashni administrator qiladi."

    ism = " ".join(x for x in (tg_user.get("first_name"), tg_user.get("last_name")) if x)
    if frappe.db.exists("TG Azo", user):
        doc = frappe.get_doc("TG Azo", user)
    else:
        doc = frappe.new_doc("TG Azo")
        doc.user = user
        doc.rol = "Xodim"
    doc.telegram_id = tid
    doc.ism = ism[:140]
    doc.username = (tg_user.get("username") or "")[:140]
    doc.faol = 1
    doc.ulangan = now_datetime()
    if bolim:
        doc.bolim = bolim
    if config.rahbar_user() == user:
        doc.rol = "Rahbar"
    doc.save(ignore_permissions=True)
    return True, doc
