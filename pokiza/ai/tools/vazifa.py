"""Vazifalar AI tool'lari.

- vazifa_taklif: AI vazifa TAKLIF qiladi (bazaga yozmaydi): taklif keshga tushadi, rahbar Telegram'da '✅ Yaratish'
  tugmasini bosgandagina Vazifa yaratiladi (pokiza.nazorat.vazifa.ai_taklif_callback). Faqat Telegram, faqat rahbar.
- vazifalar_holati: kim nimani bajardi / nima qoldi.
- ish_signallari: nima kiritilmagan / tasdiqlanmagan (raqamsiz).
"""
import secrets

import frappe
from frappe.utils import getdate, nowdate

from pokiza.ai.tools import ToolError, tool

TTL = 86400


def _topish(masul):
    """Xodimni topish: avval Telegram'ga ulanganlar (ism, @username, email), topilmasa — ERP foydalanuvchilari."""
    q = (masul or "").strip()
    if not q:
        raise ToolError("masul bo'sh")
    p = {"q": q, "u": q.lstrip("@"), "l": f"%{q.lstrip('@')}%"}
    rows = frappe.db.sql(
        """SELECT a.user, u.full_name FROM `tabTG Azo` a JOIN `tabUser` u ON u.name = a.user
        WHERE a.faol = 1 AND (a.user = %(q)s OR a.username = %(u)s OR u.full_name LIKE %(l)s OR u.first_name LIKE %(l)s
            OR a.ism LIKE %(l)s)""", p, as_dict=True)
    if not rows:
        rows = frappe.db.sql(
            """SELECT u.name AS user, u.full_name FROM `tabUser` u
            WHERE u.enabled = 1 AND u.user_type = 'System User' AND u.name NOT IN ('Administrator', 'Guest')
              AND (u.name = %(q)s OR u.full_name LIKE %(l)s OR u.first_name LIKE %(l)s)""", p, as_dict=True)
    if not rows:
        raise ToolError(f"'{masul}' xodimlar orasida topilmadi")
    if len(rows) > 1:
        raise ToolError("Bir nechta mos xodim: " + ", ".join(f"{r.full_name} ({r.user})" for r in rows[:8])
                        + ". Aniqroq ism yoki email bilan qayta chaqir.")
    return rows[0]


def vazifa_taklif(masul, sarlavha, muddat, tavsif=None):
    ctx = getattr(frappe.local, "pokiza_ai", None) or {}
    if ctx.get("kanal") != "telegram" or not ctx.get("vazifa_berish"):
        raise ToolError("Vazifani faqat rahbar beradi (Telegram)")
    u = _topish(masul)
    try:
        d = getdate(muddat)
    except Exception:
        raise ToolError("muddat formati YYYY-MM-DD")
    if d < getdate(nowdate()):
        raise ToolError("Muddat o'tgan sana")
    tid = secrets.token_urlsafe(6)
    t = {"masul": u.user, "sarlavha": sarlavha.strip()[:140], "muddat": str(d), "tavsif": (tavsif or "")[:1000],
         "berdi": frappe.session.user}
    frappe.cache.set_value(f"nz_vz_taklif:{tid}", t, expires_in_sec=TTL)
    if ctx.get("on_vazifa"):
        ctx["on_vazifa"](tid, {**t, "masul_nomi": u.full_name})
    return {"holat": "taklif tayyor — rahbar '✅ Yaratish' tugmasini bosishi kerak (hali yaratilmadi)",
            "masul": u.full_name, "sarlavha": t["sarlavha"], "muddat": t["muddat"]}


def xabar_yubor(kimga, matn):
    """Rahbar topshirig'i bilan xodimning SHAXSIY chatiga xabar TAKLIFI. Darhol yuborilmaydi: rahbar
    '✅ Yuborish' tugmasini bosgandagina ketadi (pokiza.nazorat.vazifa.xabar_taklif_callback)."""
    ctx = getattr(frappe.local, "pokiza_ai", None) or {}
    if ctx.get("kanal") != "telegram" or not ctx.get("vazifa_berish"):
        raise ToolError("Xodimga xabarni faqat rahbar yuboradi (Telegram)")
    u = _topish(kimga)
    if not frappe.db.get_value("TG Azo", {"user": u.user, "faol": 1}, "telegram_id"):
        raise ToolError(f"{u.full_name} Telegram botga ulanmagan — shaxsiy xabar yuborib bo'lmaydi")
    matn = (matn or "").strip()[:1500]
    if not matn:
        raise ToolError("matn bo'sh")
    tid = secrets.token_urlsafe(6)
    t = {"kimga": u.user, "matn": matn, "berdi": frappe.session.user}
    frappe.cache.set_value(f"nz_xb_taklif:{tid}", t, expires_in_sec=TTL)
    if ctx.get("on_xabar"):
        ctx["on_xabar"](tid, {**t, "kimga_nomi": u.full_name})
    return {"holat": "xabar tayyor — rahbar '✅ Yuborish' tugmasini bosishi kerak (hali yuborilmadi)",
            "kimga": u.full_name, "matn": matn}


def _rahbar():
    from pokiza.nazorat.scope import rahbarmi

    return rahbarmi(frappe.session.user)


def vazifalar_holati(masul=None, holat=None, davr_kun=None):
    """Vazifalar: holat bo'yicha soni va ro'yxat (kim, nima, muddat, kechikish).
    Rahbar — hammasi; boshqa xodim — faqat o'ziga berilgan va o'zi bergan vazifalar."""
    from frappe.utils import add_days

    from pokiza.nazorat.vazifa import muddat_s

    filters = {}
    or_filters = None
    if not _rahbar():
        me = frappe.session.user
        or_filters = {"masul": me, "berdi": me}
    if masul:
        filters["masul"] = _topish(masul).user
    if holat == "ochiq":
        filters["holat"] = ["in", ["Yangi", "Qabul qilindi", "Muddati o'tdi"]]
    elif holat == "tekshiruvda":
        filters.update(holat="Bajarildi", tasdiqlandi=0)
    elif holat:
        filters["holat"] = holat
    if davr_kun:
        filters["modified"] = [">=", add_days(nowdate(), -int(davr_kun))]
    rows = frappe.get_all("Vazifa", filters=filters, or_filters=or_filters, order_by="muddat asc", limit=80,
                          fields=["sarlavha", "masul", "berdi", "holat", "muddat", "tasdiqlandi", "rad_sababi",
                                  "bajarilgan_vaqt", "modified"])
    ism = {}

    def n(u):
        if u not in ism:
            ism[u] = frappe.db.get_value("User", u, "full_name") or u
        return ism[u]

    sanoq = {}
    out = []
    for r in rows:
        sanoq[r.holat] = sanoq.get(r.holat, 0) + 1
        out.append({"vazifa": r.sarlavha, "masul": n(r.masul), "berdi": n(r.berdi), "holat": r.holat,
                    "muddat": muddat_s(r.muddat, r.holat), "beruvchi_tasdiqladi": bool(r.tasdiqlandi),
                    "rad_sababi": r.rad_sababi or None,
                    "bajarilgan": str(r.bajarilgan_vaqt)[:16] if r.bajarilgan_vaqt else None})
    return {"soni": len(out), "holat_boyicha": sanoq, "vazifalar": out,
            "eslatma": "Holatlar: Yangi (qabul qilinmagan), Qabul qilindi (ishlanmoqda), Bajarildi, Rad etildi, "
                       "Muddati o'tdi. Bajarildi + beruvchi_tasdiqladi=false — tekshiruv kutmoqda."}


def ish_signallari():
    """Oxirgi ish kuni bo'yicha nima kiritilmagan / tasdiqlanmagan (raqamsiz).
    Rahbar — hammasi mas'ullar nomi bilan; boshqa xodim — faqat o'ziga tegishlilari."""
    from pokiza.nazorat.signallar import masullar, signallar, signallar_royxati

    if _rahbar():
        d, rows = signallar_royxati()
    else:
        d, hammasi = signallar()
        rows = [matn for sig, matn in hammasi if frappe.session.user in masullar(sig)]
    return {"sana": str(d), "signallar": rows or ["Sizga tegishli kiritilmagan hujjat yo'q"]}


TOOLS = [
    (
        tool(
            "xabar_yubor",
            "Rahbar biror xodimga xabar/eslatma yuborishni so'rasa ('Odilga yoz, ishlarni tezroq qilsin', "
            "'Aliga ayt ertaga ertaroq kelsin'): xodimning SHAXSIY chatiga rahbar nomidan xabar TAKLIFINI tayyorlaydi; "
            "rahbar '✅ Yuborish' tugmasini bosgandagina ketadi. Mavjud ishlarni shoshiltirish uchun YANGI vazifa ochma.",
            {
                "kimga": {"type": "string", "description": "Xodim ismi yoki @username"},
                "matn": {"type": "string", "description": "Xabar matni — rahbar aytganini xushmuomala, aniq qilib yoz"},
            },
            ["kimga", "matn"],
            strict=False,
        ),
        xabar_yubor,
    ),
    (
        tool(
            "vazifalar_holati",
            "Vazifalar holati: kim nimani bajardi, nima qoldi, kimda kechikkan, nima tekshiruv kutmoqda. "
            "'Ishlar bajarildimi?', 'Alida nechta vazifa bor?', 'kim kechikyapti?' kabi savollarga AVVAL shuni ishlat.",
            {
                "masul": {"type": "string", "description": "Xodim ismi yoki @username (ixtiyoriy)"},
                "holat": {"type": "string", "description": "ochiq | tekshiruvda | Yangi | Qabul qilindi | Bajarildi | "
                                                          "Rad etildi | Muddati o'tdi (ixtiyoriy; bo'sh — hammasi)"},
                "davr_kun": {"type": "integer", "description": "Oxirgi N kunda o'zgarganlar (ixtiyoriy)"},
            },
            strict=False,
        ),
        vazifalar_holati,
    ),
    (
        tool(
            "ish_signallari",
            "Oxirgi ish kuni bo'yicha nima kiritilmagan yoki tasdiqlanmagan (sotuv/xarid fakturalari, kassa, ishlab "
            "chiqarish) va kim mas'ul. Raqamsiz. 'Hammasi kiritildimi?', 'nima qoldi?' kabi savollar uchun.",
            {},
            strict=False,
        ),
        ish_signallari,
    ),
    (
        tool(
            "vazifa_taklif",
            "Rahbar xodimga vazifa berishni so'rasa ('Aliga juma kunigacha ... vazifa ber'): vazifa TAKLIFINI tayyorlaydi. "
            "Vazifa darhol yaratilmaydi — rahbar tugmani bosib tasdiqlaydi. Javobda 'taklif tayyor, tasdiqlang' de.",
            {
                "masul": {"type": "string", "description": "Xodim ismi yoki email (Telegram'ga ulangan)"},
                "sarlavha": {"type": "string", "description": "Qisqa vazifa matni"},
                "muddat": {"type": "string", "description": "YYYY-MM-DD"},
                "tavsif": {"type": "string", "description": "Ixtiyoriy batafsil"},
            },
            ["masul", "sarlavha", "muddat"],
            strict=False,
        ),
        vazifa_taklif,
    ),
]
