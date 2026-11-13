"""Kunlik / haftalik / oylik hisobot matni (TZ: K1-K4, H1-H6, A-D). Bo'lim doirasi bo'yicha filtrlanadi.

Bot buyruqlari ham, 08:00 rejali yuborish (3-bosqich) ham shu funksiyani ishlatadi.
"""
from datetime import timedelta

import frappe
from frappe.utils import getdate, nowdate

from pokiza.nazorat.metrics import BELGI, Davr, compute
from pokiza.nazorat.metrics.davr import ish_kunlari
from pokiza.nazorat.scope import ruxsat_kodlar
from pokiza.nazorat.tg import config
from pokiza.nazorat.tg.format import belgi, eslatmalar, esc, kpi_qator, qisqa, son, summa

HISOBOT = {
    "kunlik": ("📅 Kunlik hisobot", ["K1", "K2", "K3", "K4"]),
    "haftalik": ("🗓 Haftalik hisobot", ["H1", "H2", "H3", "H4", "H5", "H6"]),
    "oylik": ("📊 Oylik hisobot", ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4",
                                   "C1", "C2", "C3", "C4", "C5", "C6", "D1"]),
}


def oxirgi_ish_kuni(bugun=None):
    """Kecha; kecha dam olish kuni bo'lsa — undan oldingi ish kuni (dushanba 08:00 da shanba)."""
    s = frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari")
    d = getdate(bugun or nowdate()) - timedelta(days=1)
    for _ in range(7):
        if ish_kunlari(d, d, bool(s.yakshanba_ishlaydi)):
            return d
        d -= timedelta(days=1)
    return d


def davr_for(turi, bugun=None):
    if turi == "kunlik":
        return Davr.kun(oxirgi_ish_kuni(bugun))
    return Davr.parse(None, "hafta" if turi == "haftalik" else "oy", bugun)


GURUH = (("A", "🎯 Strategik fokus"), ("B", "👥 Mijozlar va sotish"), ("C", "💰 Moliya va to'lovlar"),
         ("D", "📌 Vazifalar"))
TURI = {"kunlik": "kun", "haftalik": "hafta", "oylik": "oy"}


def ruxsat_turlar(bolim):
    """Bo'limda kamida bitta ko'rsatkichi bor hisobot turlari (menyuda faqat shular chiqadi)."""
    r = ruxsat_kodlar(bolim)
    return [t for t, (_, kodlar) in HISOBOT.items() if r.intersection(kodlar)]


def davr_kalitdan(turi, kalit=None, bugun=None):
    return Davr.parse(kalit, TURI[turi], bugun) if kalit else davr_for(turi, bugun)


def keyingi(d, bugun=None):
    bugun = getdate(bugun or nowdate())
    s = d.tabiiy_t + timedelta(days=1)
    if s > bugun:
        return None
    if d.turi == "oy":
        return Davr.oy(s.year, s.month, bugun)
    if d.turi == "hafta":
        return Davr.hafta(s, bugun)
    return Davr.kun(s)


def _qisqa_davr(d):
    if d.turi == "oy":
        return d.nom.split(" (")[0]
    if d.turi == "hafta":
        return f"{d.f:%d.%m}–{d.tabiiy_t:%d.%m}"
    return f"{d.f:%d.%m}"


def _sub(m):
    """Ba'zi ko'rsatkichlar ostida bitta qisqa izoh qatori."""
    q, t, c = m.get("qism") or {}, m.get("tafsilot") or [], m["code"]
    if c == "K1" and q.get("oy_boshidan") is not None:
        s = f"oy boshidan {summa(q['oy_boshidan'])}"
        if q.get("oylik_bajarilish_%") is not None:
            s += f" · oylik rejaning {son(q['oylik_bajarilish_%'], 1)}%"
        return s
    if c in ("C5", "K4") and q.get("kim_boyicha"):
        return " · ".join(f"{esc(k.strip())} {summa(v)}" for k, v in q["kim_boyicha"].items())
    if c == "B2" and q:
        return f"↑{q.get('osgan', 0)} o'sgan · ↓{q.get('tushgan', 0)} tushgan · +{q.get('yangi', 0)} yangi"
    if c == "A1" and q.get("rejaga_%") is not None:
        return f"oylik reja {son(q['reja_t'], 0)} t — rejaning {son(q['rejaga_%'], 1)}%"
    if c == "C1" and q.get("jami_ostatka") is not None:
        return f"ostatka {summa(q['jami_ostatka'])}"
    if c == "C2" and q.get("buzilgan_summa"):
        return f"muddati buzilgan qarz {summa(q['buzilgan_summa'])}"
    if c == "C6" and q:
        boshqa = f" · boshqa {summa(q['boshqa_yonalishlar'])}" if q.get("boshqa_yonalishlar") else ""
        return f"dividend {summa(q.get('yechilgan'))}{boshqa} · oborotda {summa(q.get('oborotda_qolgan'))}"
    if c == "D1" and q:
        return f"{q.get('bajarilgan', 0)} / {q.get('jami', 0)} bajarildi"
    if c == "H6" and q:
        return f"{q.get('berilgan', 0)} berildi · {q.get('rad_etilgan', 0)} rad · {q.get('muddati_otgan', 0)} kechikdi"
    if c == "H4" and t:
        nomlar = ", ".join(esc(r["mijoz"]) for r in t[:3])
        return nomlar + (f" va yana {len(t) - 3}" if len(t) > 3 else "")
    return ""


def hisobot(turi, bolim, bugun=None, d=None):
    """(matn, tugmalar) — faqat bo'limga ruxsat etilgan ko'rsatkichlar. Ruxsat bo'lmasa (None, None)."""
    sarlavha, kodlar = HISOBOT[turi]
    ruxsat = ruxsat_kodlar(bolim)
    kodlar = [c for c in kodlar if c in ruxsat]
    if not kodlar:
        return None, None
    d = d or davr_for(turi, bugun)
    natija, ogohlantirish = [], []
    for c in kodlar:
        try:
            m = compute(c, d if c not in ("C1", "C2") or d.turi == "oy" else None, full=True, bugun=bugun)
        except Exception:
            frappe.log_error(title=f"Nazorat hisobot: {c}")
            m = {"code": c, "mavjud": False, "sabab": "hisoblashda xato"}
        natija.append(m)
        ogohlantirish += m.get("izoh") or []

    sanoq = {r: sum(1 for m in natija if m.get("rang") == r) for r in ("yashil", "sariq", "qizil")}
    tally = "   ".join(f"{BELGI[r]} {n}" for r, n in sanoq.items() if n)
    lines = [f"<b>{sarlavha}</b>", f"<i>{esc(d.nom)}</i>" + (f"   {tally}" if tally else "")]

    guruhli = turi == "oylik" and len(natija) > 6  # faqat rahbarda — bo'lim xodimiga sarlavhalar ortiqcha
    for g, gnom in (GURUH if guruhli else (("", None),)):
        bloki = [m for m in natija if m["code"].startswith(g)]
        if not bloki:
            continue
        lines.append("")
        if gnom:
            lines.append(f"<b>{gnom}</b>")
        for m in bloki:
            lines.append(kpi_qator(m))
            sub = _sub(m) if m.get("mavjud") is not False else ""
            if sub:
                lines.append(f"      <i>{sub}</i>")

    if turi == "kunlik":
        ogohlantirish = _tasdiqlanmagan(bolim, bugun) + ogohlantirish
    b = getdate(bugun or nowdate())
    if turi == "oylik" and {"C1", "C2"} & set(kodlar) and b.day <= 10 and (d.tabiiy_t + timedelta(days=1)).replace(day=1) == b.replace(day=1):
        ogohlantirish.insert(0, "Postavshiklar va debitorlik bo'yicha to'lov muddati 10-sanagacha — yakuniy holat "
                                "11-sanada alohida keladi.")
    if ogohlantirish:
        lines += ["", eslatmalar(ogohlantirish)]
    return "\n".join(lines), klaviatura(turi, natija, d, bugun)


def _tasdiqlanmagan(bolim=None, bugun=None):
    """Kunlik signal: bugungacha bo'lgan, hali tasdiqlanmagan (qoralama) hujjatlar — faqat tegishli bo'limga."""
    out = []
    kor = ruxsat_kodlar(bolim)
    for dt, sana, nom, kodlar in (("Sales Invoice", "posting_date", "sotuv fakturasi", {"A2", "H1", "K1"}),
                                  ("Purchase Invoice", "posting_date", "xarid fakturasi", {"C1", "C3"}),
                                  ("Kassa", "date", "kassa hujjati", {"K3", "C5", "K4"})):
        if not kor & kodlar:
            continue
        n, s = frappe.db.sql(
            f"SELECT COUNT(*), MIN(`{sana}`) FROM `tab{dt}` WHERE docstatus = 0 AND `{sana}` < %s",
            (getdate(bugun or nowdate()),))[0]
        if n:
            out.append(f"Tasdiqlanmagan {nom}: {n} ta (eng eskisi {s}) — hisobotga kirmagan.")
    return out


def klaviatura(turi, natija, d, bugun=None):
    """Ko'rsatkich tugmalari (rang + qisqa nom), davr bo'ylab ◀ ▶, (https bo'lsa) rahbar paneli."""
    rows, row = [], []
    for m in natija:
        if m.get("mavjud") is False:
            continue
        row.append({"text": f"{belgi(m)} {qisqa(m['code'])}", "callback_data": f"k:{m['code']}:{d.kalit}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = [{"text": f"◀ {_qisqa_davr(d.oldingi())}", "callback_data": f"h:{turi}:{d.oldingi().kalit}"}]
    k = keyingi(d, bugun)
    if k:
        nav.append({"text": f"{_qisqa_davr(k)} ▶", "callback_data": f"h:{turi}:{k.kalit}"})
    rows.append(nav)
    url = (frappe.get_cached_doc(config.DOCTYPE).sayt_url or "").rstrip("/")
    if url.startswith("https://"):
        rows.append([{"text": "🌐 Rahbar paneli", "url": f"{url}/app/rahbar-paneli"}])
    return {"inline_keyboard": rows}
