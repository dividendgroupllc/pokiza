"""Kim qaysi ko'rsatkichni ko'radi va AI'da qaysi vositalar ochiq — **Nazorat Roli** sahifasidan (ERP'da sozlanadi).

Telegram bot, hisobotlar, rahbar paneli va AI shu yerdan foydalanadi. Cheklov KOD darajasida qo'llanadi
(AI'ga yopiq vosita umuman berilmaydi), lekin nima ochiq ekanini rahbar/administrator ERP'da belgilaydi.
"""
import frappe

from pokiza.nazorat.metrics import REGISTRY

RAHBAR = "Rahbar"

# AI vositalari guruhlari (Nazorat Roli'dagi belgi -> tool nomlari)
AI_GURUHLAR = {
    "ai_qarz_mijoz": {"get_party_balances"},
    "ai_qarz_postavshik": {"get_party_balances"},
    "ai_kassa": {"get_cash_balances"},
    "ai_ishlab_chiqarish": {"production_report", "material_usage", "production_scenario", "get_production_queue",
                            "get_scale_list", "get_defect_list"},
    "ai_talab": {"demand_history"},
    "ai_fayl": {"create_file"},
    "ai_erkin": {"sql_query", "describe_doctype", "search_doctypes", "list_records", "get_record", "run_report"},
}
DOIM = {"get_kpi", "vazifalar_holati", "ish_signallari"}  # har rolda: o'z ko'rsatkichlari va vazifalar holati


def rol(nom):
    """Nazorat Roli hujjati (keshlangan) yoki None."""
    nom = (nom or "").strip()
    if not nom or not frappe.db.exists("Nazorat Roli", nom):
        return None
    return frappe.get_cached_doc("Nazorat Roli", nom)


def rollar():
    """Tanlash uchun rollar ro'yxati (Telegram'ga ulash dialogi va h.k.)."""
    return frappe.get_all("Nazorat Roli", pluck="name", order_by="toliq_ruxsat desc, name asc")


def ruxsat_kodlar(bolim):
    """Rol ko'ra oladigan KPI kodlari. To'liq ruxsat — hammasi; rolsiz — hech narsa."""
    r = rol(bolim)
    if not r:
        return set()
    if r.toliq_ruxsat:
        return set(REGISTRY)
    return {c for c in REGISTRY if r.get(f"kpi_{c.lower()}")}


def toliqmi(bolim):
    r = rol(bolim)
    return bool(r and r.toliq_ruxsat)


def vazifa_berish(bolim):
    r = rol(bolim)
    return bool(r and (r.toliq_ruxsat or r.vazifa_berish))


def rahbarmi(user):
    """Rahbar huquqi (vazifani tasdiqlash/qaytarish): administrator, Nazorat rahbari yoki TG Azo roli Rahbar."""
    if not user or user == "Guest":
        return False
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True
    from pokiza.nazorat.tg import config

    return config.rahbar_user() == user or frappe.db.get_value("TG Azo", user, "rol") == "Rahbar"


def rahbarlar():
    """Botga ulangan rahbarlar (user) — haftalik vazifa natijasi va ish signallari shularga."""
    return [u for u in frappe.get_all("TG Azo", filters={"faol": 1, "telegram_id": ["is", "set"]}, pluck="user")
            if rahbarmi(u)]


def vazifa_bera_oladimi(azo):
    """Vazifa bera oladimi: rahbar yoki Nazorat Roli'da "vazifa bera oladi" belgisi."""
    return bool(azo) and (rahbarmi(azo.user) or vazifa_berish(azo_bolimi(azo)))


def azo_bolimi(azo):
    """TG Azo -> samarali rol (TG Azo'da rol=Rahbar bo'lsa 'Rahbar')."""
    if not azo or not azo.faol:
        return None
    return RAHBAR if azo.rol == "Rahbar" else azo.bolim


def bolim_kaliti(bolim):
    return (bolim or "").strip().lower().replace(" ", "_")


def ai_tools(bolim):
    """None — cheklovsiz (to'liq ruxsat); set — ruxsat etilgan tool nomlari; bo'sh set — hech narsa."""
    r = rol(bolim)
    if not r:
        return set()
    if r.toliq_ruxsat:
        return None
    out = set(DOIM)
    for f, tools in AI_GURUHLAR.items():
        if r.get(f):
            out |= tools
    return out


def ai_arg_xato(bolim, tool_name, args):
    """Argument darajasidagi cheklov: qarzlarda faqat ruxsat etilgan tomon (mijoz / postavshik)."""
    r = rol(bolim)
    if not r or r.toliq_ruxsat or tool_name != "get_party_balances":
        return None
    pt = (args or {}).get("party_type")
    ruxsat = {t for t, f in (("Customer", "ai_qarz_mijoz"), ("Supplier", "ai_qarz_postavshik")) if r.get(f)}
    if pt not in ruxsat:
        return "Bu rolda qarzlar faqat: " + (", ".join(sorted(ruxsat)) or "yopiq")
    return None


def kodni_koradigan_rollar(kodlar):
    """Shu ko'rsatkichlardan birortasini ko'radigan (to'liq ruxsatsiz) rollar — ish signallari mas'ullari."""
    out = []
    for nom in rollar():
        r = rol(nom)
        if r and not r.toliq_ruxsat and any(r.get(f"kpi_{k.lower()}") for k in kodlar):
            out.append(nom)
    return out
