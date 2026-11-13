"""Rahbar paneli (/app/rahbar-paneli) API — Telegram hisobotlari bilan bir xil KPI dvigateli va bir xil doira."""
import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from pokiza.nazorat.charts import SONI
from pokiza.nazorat.metrics import REGISTRY, Davr, DavrXato, compute
from pokiza.nazorat.reports import HISOBOT, davr_for
from pokiza.nazorat.scope import ruxsat_kodlar

TURI = {"oylik": "oy", "haftalik": "hafta", "kunlik": "kun"}


def _bolim():
    user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return "Rahbar"
    if frappe.db.get_single_value("Nazorat Bot Sozlamalari", "rahbar") == user:
        return "Rahbar"
    azo = frappe.db.get_value("TG Azo", user, ["rol", "bolim", "faol"], as_dict=True)
    if azo and azo.faol:
        return "Rahbar" if azo.rol == "Rahbar" else azo.bolim
    frappe.throw(_("Sizga nazorat bo'limi biriktirilmagan (TG Azo)"), frappe.PermissionError)


def _davr(turi, davr, sana=None):
    """sana (ERP sana tanlagichidan) — shu sana tushgan oy / hafta / kun; davr — matn (joriy_oy, 2026-10 ...)."""
    if turi not in HISOBOT:
        frappe.throw(_("Noto'g'ri hisobot turi"))
    try:
        if sana:
            s = getdate(sana)
            if s > getdate(nowdate()):
                raise DavrXato("Kelajakdagi sana uchun fakt yo'q")
            if turi == "oylik":
                return Davr.oy(s.year, s.month)
            return Davr.hafta(s) if turi == "haftalik" else Davr.kun(s)
        return Davr.parse(davr, TURI[turi]) if davr else davr_for(turi)
    except DavrXato as e:
        frappe.throw(str(e))


@frappe.whitelist()
def get_panel(turi="oylik", davr=None, sana=None):
    bolim = _bolim()
    d = _davr(turi, davr, sana)
    ruxsat = ruxsat_kodlar(bolim)
    out = []
    for c in HISOBOT[turi][1]:
        if c not in ruxsat:
            continue
        try:
            m = compute(c, d if REGISTRY[c].davrlar and d.turi in REGISTRY[c].davrlar else None, full=False)
        except Exception as e:
            frappe.log_error(title=f"Rahbar paneli: {c}")
            m = {"code": c, "nom": REGISTRY[c].nom, "xato": str(e)[:200]}
        out.append(m)
    return {"bolim": bolim, "davr": d.as_dict(), "turi": turi, "korsatkichlar": out, "bugun": str(getdate(nowdate()))}


@frappe.whitelist()
def get_detail(code, turi="oylik", davr=None, sana=None):
    bolim = _bolim()
    code = (code or "").upper()
    if code not in ruxsat_kodlar(bolim):
        frappe.throw(_("Bu ko'rsatkich sizga yopiq"), frappe.PermissionError)
    d = _davr(turi, davr, sana)
    spec = REGISTRY[code]
    if d.turi not in spec.davrlar:
        d = Davr.parse(None, spec.turi)
    try:
        return compute(code, d, full=True, trend=SONI.get(d.turi, 12))
    except (DavrXato, ValueError) as e:
        frappe.throw(str(e))
