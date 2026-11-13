"""Oylik mijoz hisoboti (PDF): tanlangan oy savdosi o'tgan oyga nisbatan.

Mijozga beriladi (sotuvchi ERP'dan yuklab oladi): hajm (kg) va summa o'zgarishi, savdosi kamaygan /
oshgan mahsulotlar, asosiy mahsulot tahlili, hajm ulushi va keyingi oy maqsadi (Mijoz Kartochkasi →
Oylik maqsadlar jadvali).

Hisob qoidalari (Nazorat ko'rsatkichlari bilan bir xil):
- faqat tasdiqlangan (docstatus=1) sotuv fakturalari, qaytarishlar ayirilgan holda;
- summa = base_net_amount (QQS'siz, chegirmadan keyin);
- hajm = kg'dagi mahsulotlar + donali mahsulotlar × Item.weight_per_unit; vazni yo'q donalilar
  kg'ga qo'shilmaydi, alohida "dona" bo'lib ko'rsatiladi.
"""
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

KG_UOMS = ("кг", "Kg", "kg")
OYLAR = ("", "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr",
         "Noyabr", "Dekabr")
TOP = 5


def _oy(oy):
    """'2026-09' -> date(2026, 9, 1)."""
    try:
        y, m = (int(x) for x in str(oy).split("-")[:2])
        return date(y, m, 1)
    except Exception:
        frappe.throw(_("Oy noto'g'ri: {0} (masalan 2026-09)").format(oy))


def _qatorlar(mijoz, f, t):
    rows = frappe.db.sql(
        """
        SELECT sii.item_code, MAX(sii.item_name) AS nom,
            SUM(CASE WHEN sii.stock_uom IN %(kg)s THEN sii.stock_qty
                     ELSE sii.stock_qty * IFNULL(i.weight_per_unit, 0) END) AS kg,
            SUM(CASE WHEN sii.stock_uom NOT IN %(kg)s AND IFNULL(i.weight_per_unit, 0) = 0
                     THEN sii.stock_qty ELSE 0 END) AS dona,
            SUM(sii.base_net_amount) AS summa
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1 AND si.customer = %(m)s AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY sii.item_code
        """,
        {"m": mijoz, "f": f, "t": t, "kg": KG_UOMS},
        as_dict=True,
    )
    return {r.item_code: r for r in rows}


def _foiz(a, b):
    return round((a - b) / b * 100, 1) if b else None


def _maqsad(mijoz, d):
    """Mijoz Kartochkasi → Oylik maqsadlar: d oyi uchun qator (bo'lmasa None)."""
    karta = frappe.db.get_value("Mijoz Kartochkasi", {"mijoz": mijoz}, "name", order_by="modified desc")
    if not karta:
        return None
    r = frappe.db.get_value("Mijoz Oylik Maqsad",
                            {"parent": karta, "parenttype": "Mijoz Kartochkasi", "yil": d.year, "oy": OYLAR[d.month]},
                            ["maqsad_kg", "maqsad_summa", "izoh"], as_dict=True)
    return r if r and (flt(r.maqsad_kg) or flt(r.maqsad_summa)) else None


def malumot(mijoz, oy):
    """Hisobot uchun barcha raqamlar (PDF shablon shu dict'dan chiziladi)."""
    d = _oy(oy)
    p = getdate(add_months(d, -1))
    k = getdate(add_months(d, 1))
    hozir = _qatorlar(mijoz, d, get_last_day(d))
    oldin = _qatorlar(mijoz, p, get_last_day(p))

    def jami(rows, key):
        return sum(flt(r[key]) for r in rows.values())

    kg1, kg0 = jami(hozir, "kg"), jami(oldin, "kg")
    s1, s0 = jami(hozir, "summa"), jami(oldin, "summa")

    mahsulotlar = []
    for code in set(hozir) | set(oldin):
        a, b = hozir.get(code), oldin.get(code)
        mahsulotlar.append(frappe._dict(
            code=code, nom=(a or b).nom, kg1=flt(a.kg) if a else 0, kg0=flt(b.kg) if b else 0,
            s1=flt(a.summa) if a else 0, s0=flt(b.summa) if b else 0))
    for m in mahsulotlar:
        m.farq = m.kg1 - m.kg0
    kamaygan = sorted([m for m in mahsulotlar if m.farq <= -0.5], key=lambda m: m.farq)[:TOP]
    oshgan = sorted([m for m in mahsulotlar if m.farq >= 0.5], key=lambda m: -m.farq)[:TOP]

    asosiy = max(mahsulotlar, key=lambda m: max(m.kg0, m.kg1), default=None)
    asosiy_d = None
    if asosiy and (asosiy.kg0 or asosiy.kg1):
        umumiy_farq = kg1 - kg0
        hissa = (round(asosiy.farq / umumiy_farq * 100) if umumiy_farq and asosiy.farq
                 and (asosiy.farq > 0) == (umumiy_farq > 0) else None)
        asosiy_d = frappe._dict(
            nom=asosiy.nom, kg0=asosiy.kg0, kg1=asosiy.kg1, farq=asosiy.farq, foiz=_foiz(asosiy.kg1, asosiy.kg0),
            hissa=hissa, ulush=round(asosiy.kg1 / kg1 * 100, 1) if kg1 else None,
            boshqa0=kg0 - asosiy.kg0, boshqa1=kg1 - asosiy.kg1,
            boshqa_foiz=_foiz(kg1 - asosiy.kg1, kg0 - asosiy.kg0))

    maqsad = _maqsad(mijoz, k)
    if maqsad:
        maqsad.kg_osish = _foiz(flt(maqsad.maqsad_kg), kg1) if maqsad.maqsad_kg else None
        maqsad.summa_osish = _foiz(flt(maqsad.maqsad_summa), s1) if maqsad.maqsad_summa else None

    return frappe._dict(
        mijoz=mijoz, mijoz_nomi=frappe.db.get_value("Customer", mijoz, "customer_name") or mijoz,
        oy=OYLAR[d.month], oy_yil=f"{OYLAR[d.month]} {d.year}", oldingi=OYLAR[p.month],
        oldingi_yil=f"{OYLAR[p.month]} {p.year}", keyingi=OYLAR[k.month], keyingi_yil=f"{OYLAR[k.month]} {k.year}",
        kg1=kg1, kg0=kg0, kg_farq=kg1 - kg0, kg_foiz=_foiz(kg1, kg0),
        s1=s1, s0=s0, s_farq=s1 - s0, s_foiz=_foiz(s1, s0),
        dona1=jami(hozir, "dona"), dona0=jami(oldin, "dona"),
        kamaygan=kamaygan, oshgan=oshgan, asosiy=asosiy_d, maqsad=maqsad,
        bosh=not hozir and not oldin,
        company=frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company"),
    )


# ---------- formatlash ----------
def son(v, kasr=0):
    if v is None:
        return "—"
    return f"{v:,.{kasr}f}".replace(",", " ").replace(".", ",")


def ishorali(v, kasr=0):
    if v is None:
        return "—"
    return ("+" if v > 0 else "−" if v < 0 else "") + son(abs(v), kasr)


def summa(v, ishora=False):
    if v is None:
        return "—"
    a = abs(v)
    s = (f"{son(a / 1e9, 2)} mlrd" if a >= 1e9 else f"{son(a / 1e6, 1)} mln" if a >= 1e6 else son(a))
    if ishora:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


def _donut(foiz, rang, fon="rgba(255,255,255,.08)", r=54, w=14):
    """SVG halqa: foiz (0..100) qismi rangli."""
    import math

    foiz = max(0.0, min(100.0, flt(foiz)))
    c = r + w
    if foiz >= 99.95:
        arc = f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{rang}" stroke-width="{w}"/>'
    elif foiz <= 0.05:
        arc = ""
    else:
        a = foiz / 100 * 2 * math.pi
        x, y = c + r * math.sin(a), c - r * math.cos(a)
        katta = 1 if foiz > 50 else 0
        arc = (f'<path d="M {c} {c - r} A {r} {r} 0 {katta} 1 {x:.2f} {y:.2f}" fill="none" stroke="{rang}" '
               f'stroke-width="{w}" stroke-linecap="round"/>')
    return (f'<svg width="{2 * c}" height="{2 * c}" viewBox="0 0 {2 * c} {2 * c}">'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{fon}" stroke-width="{w}"/>{arc}</svg>')


def _font_css():
    base = frappe.get_app_path("frappe", "public", "css", "fonts", "inter")
    out = []
    for w, f in ((400, "Inter-Regular"), (500, "Inter-Medium"), (600, "Inter-SemiBold"), (700, "Inter-Bold"),
                 (800, "Inter-ExtraBold")):
        out.append(f"@font-face{{font-family:'Inter';font-weight:{w};src:url('file://{base}/{f}.woff2') format('woff2');}}")
    return "\n".join(out)


def html(mijoz, oy):
    m = malumot(mijoz, oy)
    return frappe.render_template("pokiza/templates/mijoz_hisobot.html", {
        "m": m, "son": son, "ishorali": ishorali, "summa": summa, "donut": _donut, "font_css": _font_css(),
    })


def pdf_bytes(mijoz, oy):
    from weasyprint import HTML

    return HTML(string=html(mijoz, oy), base_url=frappe.utils.get_url()).write_pdf()


@frappe.whitelist()
def yuklab_ol(mijoz, oy):
    """ERP tugmasi: /api/method/pokiza.api.mijoz_hisobot.yuklab_ol?mijoz=...&oy=2026-09"""
    if not frappe.db.exists("Customer", mijoz):
        frappe.throw(_("Mijoz topilmadi"))
    if not (frappe.has_permission("Customer", "read", doc=mijoz) and frappe.has_permission("Sales Invoice", "read")):
        frappe.throw(_("Bu mijoz savdosini ko'rishga ruxsatingiz yo'q"), frappe.PermissionError)
    d = _oy(oy)
    if d > get_first_day(getdate()):
        frappe.throw(_("Kelajakdagi oy uchun hisobot yo'q"))
    nom = frappe.db.get_value("Customer", mijoz, "customer_name") or mijoz
    xavfsiz = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in nom).strip().replace(" ", "_")
    frappe.local.response.filename = f"Savdo_tahlili_{xavfsiz}_{d:%Y-%m}.pdf"
    frappe.local.response.filecontent = pdf_bytes(mijoz, oy)
    frappe.local.response.type = "pdf"
