"""Vazifalar: D1 oylik bajarilish (xodim bo'yicha), H6 haftalik holat."""
import frappe
from frappe.utils import getdate, nowdate

from pokiza.nazorat.metrics.base import QIZIL, SARIQ, YASHIL, Ctx, foiz, metric, rang_chegara

YOPIQ_YOMON = ("Rad etildi", "Muddati o'tdi")


def _bajarilmagan(r, t):
    return r.holat in YOPIQ_YOMON or (r.holat in ("Yangi", "Qabul qilindi") and getdate(r.muddat) < t)


@metric("D1", "Vazifalar bajarilishi", "%", "oy", "rahbar", additive=False)
def vazifalar(ctx: Ctx):
    """Muddati shu davrga tushgan vazifalar: bajarilgan / (bajarilgan + bajarilmagan) × 100.
    Bajarilmagan = rad etilgan, muddati o'tgan yoki muddat o'tib hali ochiq. Rang: 90%+ / 70–90% / <70%.
    Ro'yxat xodim bo'yicha: jami — bajarilgan — bajarilmagan."""
    t = min(ctx.t, getdate(nowdate()))
    # oy tugamagan bo'lsa ham shu oy muddatli vazifalar (muddati kelmagan ochiqlari "ochiq" bo'lib turadi)
    rows = frappe.get_all("Vazifa", filters={"muddat": ["between", [ctx.f, ctx.d.tabiiy_t]], "holat": ["!=", "Bekor qilindi"]},
                          fields=["masul", "holat", "muddat", "sarlavha"])
    by = {}
    for r in rows:
        b = by.setdefault(r.masul, {"jami": 0, "bajarilgan": 0, "bajarilmagan": 0, "ochiq": 0})
        b["jami"] += 1
        if r.holat == "Bajarildi":
            b["bajarilgan"] += 1
        elif _bajarilmagan(r, t):
            b["bajarilmagan"] += 1
        else:
            b["ochiq"] += 1
    baj = sum(b["bajarilgan"] for b in by.values())
    yom = sum(b["bajarilmagan"] for b in by.values())
    fakt = foiz(baj, baj + yom)
    out = {"fakt": fakt, "rang": rang_chegara(fakt, 90, 70), "manba": "Vazifa (muddati davr ichida)"}
    if not rows:
        out["izoh"] = ["Bu davrda muddatli vazifa yo'q."]
    if ctx.full:
        tafsilot = []
        for u, b in by.items():
            f = foiz(b["bajarilgan"], b["bajarilgan"] + b["bajarilmagan"])
            tafsilot.append({"xodim": frappe.db.get_value("User", u, "full_name") or u, **b, "bajarilish_%": f,
                             "rang": YASHIL if not b["bajarilmagan"] else QIZIL})
        out["tafsilot"] = sorted(tafsilot, key=lambda r: -r["bajarilmagan"])
        out["qism"] = {"jami": len(rows), "bajarilgan": baj, "bajarilmagan": yom}
    return out


@metric("H6", "Vazifalar (haftalik)", "vazifa", "hafta", "rahbar", additive=False)
def vazifalar_hafta(ctx: Ctx):
    """Hafta: berilgan, qabul qilingan, rad etilgan, bajarilgan; fakt = hozir muddati o'tgan ochiq vazifalar soni.
    Rad etilganlar — individual gaplashish kerak (TZ H6)."""
    berilgan = frappe.get_all("Vazifa", filters={"creation": ["between", [f"{ctx.f} 00:00:00", f"{ctx.t} 23:59:59"]]},
                              fields=["name", "holat"])
    kechikkan = frappe.get_all("Vazifa", filters={"holat": "Muddati o'tdi"},
                               fields=["name", "sarlavha", "masul", "muddat"], order_by="muddat asc")
    rad = frappe.get_all("Vazifa", filters={"holat": "Rad etildi", "modified": [">=", f"{ctx.f} 00:00:00"]},
                         fields=["name", "sarlavha", "masul", "rad_sababi"])
    out = {"fakt": len(kechikkan), "rang": YASHIL if not kechikkan else QIZIL,
           "manba": "Vazifa"}
    if ctx.full:
        out["qism"] = {"berilgan": len(berilgan),
                       "bajarilgan": frappe.db.count("Vazifa", {"bajarilgan_vaqt": ["between", [f"{ctx.f} 00:00:00", f"{ctx.t} 23:59:59"]]}),
                       "rad_etilgan": len(rad), "muddati_otgan": len(kechikkan)}
        nom = lambda u: frappe.db.get_value("User", u, "full_name") or u  # noqa: E731
        out["tafsilot"] = ([{"vazifa": r.sarlavha, "xodim": nom(r.masul), "holat": "rad", "sabab": r.rad_sababi} for r in rad]
                           + [{"vazifa": r.sarlavha, "xodim": nom(r.masul), "holat": "muddati o'tgan",
                               "muddat": str(r.muddat)} for r in kechikkan])
    return out
