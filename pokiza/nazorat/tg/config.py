"""Ichki (nazorat) bot sozlamalari. Mijozlar boti (pokiza/telegram) bilan aralashmaydi."""
import frappe

DOCTYPE = "Nazorat Bot Sozlamalari"


def _doc():
    return frappe.get_cached_doc(DOCTYPE)


def token():
    return _doc().get_password("bot_token", raise_exception=False) or None


def secret():
    return _doc().get_password("webhook_secret", raise_exception=False) or None


def faol():
    return bool(_doc().faol) and bool(token())


def username():
    return _doc().bot_username or ""


def rahbar_user():
    return _doc().rahbar


def sozlama(field, default=1):
    v = _doc().get(field)
    return default if v is None else v


def bir_marta(kalit, sekund=36 * 3600):
    """Rejali xabar ikki marta ketmasin (scheduler ikki marta ishlasa ham): True — shu chaqiruv egalladi."""
    return bool(frappe.cache.set(frappe.cache.make_key(f"nz_claim:{kalit}"), 1, ex=sekund, nx=True))


def bosh_qoy(kalit):
    """Yuborish muvaffaqiyatsiz bo'lsa — keyingi urinish uchun bo'shatish."""
    frappe.cache.delete(frappe.cache.make_key(f"nz_claim:{kalit}"))
