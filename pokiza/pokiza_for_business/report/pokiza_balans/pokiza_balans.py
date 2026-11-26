# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Pokiza Balans — oy oxiri holatiga boshqaruv balansi (egasi Excel formati, 2026-11).

Bitta hisobot, «Ko'rinish» filtri bilan 4 sahifa (Excel'dagi 4 varaq tartibida):
    Balans | Debitorlar | Kreditorlar | Zaxiralar

Manba — GL Entry (buxgalteriya), zaxira guruhlari — Stock Ledger Entry.
Har ustun = bitta oyning OXIRGI KUNI holatiga qoldiq; oxirgi oy yopilmagan
bo'lsa (to_date oy o'rtasida) — o'sha sanaga, sarlavhada * bilan.

Qoidalar (Excel bilan tiyin-tiyin tekshirilgan, 2026-06..10):
  * Debitor/kreditor — RAZVERNUTOE saldo: har (kontragent, hisob) bo'yicha
    qoldiq musbat bo'lsa aktivda, manfiy bo'lsa passivda. Mijoz minusda =
    «Mijozlardan olingan avans», yetkazib beruvchi plusda = «YB'ga avans».
  * Xodimlar ham Creditors UZS da yuradi (party_type=Employee).
  * Zaxira: GL (Склад сырьё + Склад ГП) — jami; guruhlarga bo'lish SLE
    stock_value dan: Сырё / Упаковка / Фарш / Сотув махсулотлари (daraxti bilan)
    / Асосий восита; GL−SLE farqi alohida qatorda.
  * Taqsimlanmagan foyda GL'dan: Income−Expense yig'ma harakati (Period
    Closing yo'q, Retained Earnings hisobi bo'sh — tekshirilgan).
  * Dividendlar — «Dividends Paid-*» equity hisoblarining oy ichidagi harakati.

Balans tengligi KONSTRUKTIV: barcha leaf hisoblar qoldig'i biror qatorga
tushadi (tasniflanmagani «Boshqa»ga), shuning uchun Check = 0 bo'lishi shart.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, get_last_day, add_months, add_days

EPS = 0.005

OY_NOMLARI = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr",
]

# zaxira guruhlari: Item Group -> balans qatori (tartibi ham shu)
ZAXIRA_GURUHLAR = [
    ("Xom ashyo (Сырё)", {"Сырё"}),
    ("Qadoq materiallari (Упаковка)", {"Упаковка"}),
    ("Farsh / yarim tayyor", {"Фарш"}),
    ("Tayyor mahsulot (ГП)", None),   # None -> «Сотув махсулотлари» daraxti (dinamik)
    ("Boshqa (asosiy vosita sifatidagi tovarlar)", "QOLGANLARI"),
]
GP_ILDIZ = "Сотув махсулотлари"

TURI_UZ = {"Customer": "Mijoz", "Supplier": "Yetkazib beruvchi", "Employee": "Xodim"}
TURI_TARTIB = {"Mijoz": 0, "Yetkazib beruvchi": 1, "Xodim": 2}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not (filters.get("from_date") and filters.get("to_date")):
        frappe.throw(_("Davr (dan/gacha) tanlanishi shart"))

    oylar = _oy_ustunlari(getdate(filters.from_date), getdate(filters.to_date))
    if not oylar:
        frappe.throw(_("Davr noto'g'ri: «dan» «gacha»dan keyin"))
    if len(oylar) > 13:
        frappe.throw(_("Ko'pi bilan 13 oy tanlang (hozir {0} oy)").format(len(oylar)))

    korinish = filters.get("korinish") or "Balans"
    if korinish == "Balans":
        return _balans_korinishi(oylar)
    if korinish in ("Debitorlar", "Kreditorlar"):
        return _kontragent_korinishi(oylar, debitor=(korinish == "Debitorlar"))
    return _zaxira_korinishi(oylar)


# --------------------------------------------------------------------------- oylar

def _oy_ustunlari(from_date, to_date):
    """[{label, start, cutoff, partial}] — har oy uchun oy oxiri (oxirgisi to_date gacha)."""
    oylar = []
    d = getdate(f"{from_date.year}-{from_date.month:02d}-01")
    while d <= to_date:
        oxiri = get_last_day(d)
        partial = oxiri > to_date
        cutoff = to_date if partial else oxiri
        label = f"{OY_NOMLARI[d.month - 1]} {d.year}" + ("*" if partial else "")
        oylar.append(frappe._dict(start=d, cutoff=cutoff, label=label, partial=partial))
        d = add_months(d, 1)
    return oylar


def _oy_ustun_deflari(oylar, birinchi):
    cols = list(birinchi)
    for i, o in enumerate(oylar):
        cols.append({
            "fieldname": f"oy_{i}", "label": o.label,
            "fieldtype": "Currency", "width": 140,
        })
    return cols


# --------------------------------------------------------------------------- GL meta

def _hisob_meta():
    accs = frappe.get_all(
        "Account",
        filters={"is_group": 0},
        fields=["name", "root_type", "account_type", "account_currency"],
    )
    m = frappe._dict(
        kassa=set(), bank=set(), ar_ap=set(), usd_ap=set(), stock=set(),
        fixed=set(), ustav=set(), dividend=[], retained=set(), ie=set(),
        boshqa_aktiv=set(), boshqa_passiv=set(),
    )
    for a in accs:
        t = a.account_type or ""
        if t in ("Cash", "Bank"):
            # Р/С hisoblari ham Cash turida — nomidan ajratiladi (hisob rejasi shunaqa)
            (m.bank if (t == "Bank" or a.name.startswith("Р/С")) else m.kassa).add(a.name)
        elif t in ("Receivable", "Payable"):
            m.ar_ap.add(a.name)
            if a.account_currency and a.account_currency != "UZS":
                m.usd_ap.add(a.name)
        elif t == "Stock":
            m.stock.add(a.name)
        elif t in ("Fixed Asset", "Accumulated Depreciation", "Capital Work in Progress"):
            m.fixed.add(a.name)
        elif a.root_type == "Equity":
            if a.name.startswith("Dividends Paid"):
                m.dividend.append(a.name)
            elif a.name.startswith("Retained Earnings"):
                m.retained.add(a.name)
            else:
                m.ustav.add(a.name)
        elif a.root_type in ("Income", "Expense"):
            m.ie.add(a.name)
        elif a.root_type == "Asset":
            m.boshqa_aktiv.add(a.name)
        else:
            m.boshqa_passiv.add(a.name)
    m.dividend.sort()
    return m


def _gl_qoldiqlar(cutoff):
    """Hisob -> yig'ma qoldiq (debit − kredit) cutoff kuni oxirigacha."""
    return {
        r[0]: flt(r[1])
        for r in frappe.db.sql(
            """SELECT account, SUM(debit) - SUM(credit) FROM `tabGL Entry`
               WHERE is_cancelled = 0 AND posting_date <= %s GROUP BY account""",
            cutoff,
        )
    }


def _party_qoldiqlar(cutoff, ar_ap):
    return frappe.db.sql(
        """SELECT account, party_type, party, SUM(debit) - SUM(credit) AS bal
           FROM `tabGL Entry`
           WHERE is_cancelled = 0 AND posting_date <= %s
             AND account IN %s AND IFNULL(party, '') != ''
           GROUP BY account, party_type, party""",
        (cutoff, tuple(ar_ap)),
        as_dict=True,
    )


def _sle_qoldiqlar(cutoff):
    """Item -> SLE bo'yicha qoldiq qiymati (barcha skladlar yig'indisi) cutoff holatiga."""
    rows = frappe.db.sql(
        """SELECT item_code, stock_value FROM (
               SELECT sle.item_code, sle.stock_value,
                      ROW_NUMBER() OVER (
                          PARTITION BY sle.item_code, sle.warehouse
                          ORDER BY sle.posting_datetime DESC, sle.creation DESC
                      ) AS rn
               FROM `tabStock Ledger Entry` sle
               WHERE sle.is_cancelled = 0 AND sle.posting_date <= %s
           ) t WHERE rn = 1""",
        cutoff,
        as_dict=True,
    )
    natija = {}
    for r in rows:
        natija[r.item_code] = natija.get(r.item_code, 0.0) + flt(r.stock_value)
    return natija


def _zaxira_guruh_xaritasi():
    """Item Group -> balans guruh yorlig'i (GP daraxti dinamik)."""
    from frappe.utils.nestedset import get_descendants_of

    gp = set(get_descendants_of("Item Group", GP_ILDIZ) or []) | {GP_ILDIZ} \
        if frappe.db.exists("Item Group", GP_ILDIZ) else set()
    xarita = {}
    for label, guruhlar in ZAXIRA_GURUHLAR:
        if guruhlar is None:
            for g in gp:
                xarita[g] = label
        elif guruhlar != "QOLGANLARI":
            for g in guruhlar:
                xarita[g] = label
    return xarita  # topilmagani -> «Boshqa» (oxirgi label)


# --------------------------------------------------------------------------- Balans

def _balans_korinishi(oylar):
    meta = _hisob_meta()
    guruh_xarita = _zaxira_guruh_xaritasi()
    boshqa_zaxira_label = ZAXIRA_GURUHLAR[-1][0]
    item_grp = dict(frappe.db.sql("SELECT name, item_group FROM `tabItem`"))

    # qo'shimcha 2 ta orqa snapshot: retained-prior va «o'tgan oy foydasi» uchun
    orqa2 = add_days(add_months(oylar[0].start, -1), -1)   # 2 oy avvalgi oy oxiri
    orqa1 = add_days(oylar[0].start, -1)                   # oldingi oy oxiri
    snapshotlar = [orqa2, orqa1] + [o.cutoff for o in oylar]
    bal = {d: _gl_qoldiqlar(d) for d in snapshotlar}

    def summa(d, hisoblar):
        b = bal[d]
        return sum(b.get(h, 0.0) for h in hisoblar)

    def cum_foyda(d):   # yig'ma sof foyda (Income−Expense)
        return -summa(d, meta.ie)

    def cum_div(d):
        return summa(d, meta.dividend)

    n = len(oylar)
    K = {}  # key -> [qiymat_per_oy]

    def qator(key):
        return K.setdefault(key, [0.0] * n)

    fa_hisoblar = sorted(meta.fixed)
    for i, o in enumerate(oylar):
        d = o.cutoff
        oldingi = snapshotlar[i + 1]  # shu oydan avvalgi oy oxiri

        qator("kassa")[i] = summa(d, meta.kassa)
        qator("bank")[i] = summa(d, meta.bank)

        # razvernutoe saldo
        party_jami = {}
        for p in _party_qoldiqlar(d, meta.ar_ap):
            party_jami[p.account] = party_jami.get(p.account, 0.0) + p.bal
            if abs(p.bal) < EPS:
                continue
            if p.party_type == "Customer":
                key = "mijoz_qarz" if p.bal > 0 else "mijoz_avans"
            elif p.party_type == "Supplier":
                if p.bal > 0:
                    key = "yb_avans"
                else:
                    key = "yb_usd" if p.account in meta.usd_ap else "yb_uzs"
            elif p.party_type == "Employee":
                key = "xodim_avans" if p.bal > 0 else "xodim_qarz"
            else:
                key = "boshqa_deb" if p.bal > 0 else "boshqa_kred"
            qator(key)[i] += abs(p.bal)
        # party'siz qoldiq (xatolik/texnik yozuvlar) — yo'qolmasin
        for h in meta.ar_ap:
            qoldiq = bal[d].get(h, 0.0) - party_jami.get(h, 0.0)
            if abs(qoldiq) >= EPS:
                qator("boshqa_deb" if qoldiq > 0 else "boshqa_kred")[i] += abs(qoldiq)

        qator("boshqa_deb")[i] += summa(d, meta.boshqa_aktiv)
        qator("boshqa_kred")[i] += -summa(d, meta.boshqa_passiv)

        # zaxiralar
        zax_gl = summa(d, meta.stock)
        qator("zax_gl")[i] = zax_gl
        sle = _sle_qoldiqlar(d)
        sle_jami = 0.0
        for item, v in sle.items():
            label = guruh_xarita.get(item_grp.get(item), boshqa_zaxira_label)
            qator("zax:" + label)[i] += v
            sle_jami += v
        qator("zax_farq")[i] = zax_gl - sle_jami

        for h in fa_hisoblar:
            qator("fa:" + h)[i] = bal[d].get(h, 0.0)

        # kapital
        qator("ustav")[i] = -summa(d, meta.ustav)
        retained_prior = (cum_foyda(oldingi) - cum_div(oldingi)) - summa(oldingi, meta.retained)
        qator("retained_prior")[i] = retained_prior
        foyda = cum_foyda(d) - cum_foyda(oldingi)
        qator("foyda")[i] = foyda
        div_oy = cum_div(d) - cum_div(oldingi)
        qator("div_oy")[i] = div_oy
        for h in meta.dividend:
            qator("div:" + h)[i] = bal[d].get(h, 0.0) - bal[oldingi].get(h, 0.0)
        qator("retained_jami")[i] = cum_foyda(d) - cum_div(d) - summa(d, meta.retained)

    # avvalgi oy foydasi (birinchi ustun uchun orqa2..orqa1 oralig'i)
    oldingi_foyda = [(-summa(orqa1, meta.ie)) - (-summa(orqa2, meta.ie))] + K["foyda"][:-1]

    def V(key):
        return K.get(key, [0.0] * n)

    pul = [a + b for a, b in zip(V("kassa"), V("bank"))]
    debitorlik = [sum(x) for x in zip(V("mijoz_qarz"), V("yb_avans"), V("xodim_avans"), V("boshqa_deb"))]
    zaxira = V("zax_gl")
    fa_jami = [sum(V("fa:" + h)[i] for h in fa_hisoblar) for i in range(n)]
    aktiv = [sum(x) for x in zip(pul, debitorlik, zaxira, fa_jami)]
    kreditorlik = [sum(x) for x in zip(V("yb_uzs"), V("yb_usd"), V("mijoz_avans"), V("xodim_qarz"), V("boshqa_kred"))]
    kapital = [u + rp + f - dv for u, rp, f, dv in zip(V("ustav"), V("retained_prior"), V("foyda"), V("div_oy"))]
    passiv = [k + c for k, c in zip(kreditorlik, kapital)]

    # ------ qatorlar (Excel tartibida)
    data = []

    def q(label, vals=None, indent=0, bold=0, fmt=None, bosh=0):
        row = {"korsatkich": label, "indent": indent, "bold": bold, "fmt": fmt, "bosh": bosh}
        for i in range(n):
            row[f"oy_{i}"] = None if vals is None else flt(vals[i], 2)
        data.append(row)

    q("AKTIV", bold=1, bosh=1)
    q("Pul qoldig'i", pul, bold=1)
    q("Asosiy kassa (naqd so'm)", V("kassa"), indent=1)
    q("Bank hisob raqami (Р/С)", V("bank"), indent=1)
    q("Debitorlik", debitorlik, bold=1)
    q("Mijozlar (bizga qarz)", V("mijoz_qarz"), indent=1)
    q("Yetkazib beruvchilarga avans", V("yb_avans"), indent=1)
    q("Xodimlar (avans)", V("xodim_avans"), indent=1)
    q("Boshqa oldi-berdi", V("boshqa_deb"), indent=1)
    q("Tovar-moddiy zaxiralar", zaxira, bold=1)
    for label, _g in ZAXIRA_GURUHLAR:
        if ("zax:" + label) in K:
            q(label, V("zax:" + label), indent=1)
    q("Ombor va buxgalteriya farqi", V("zax_farq"), indent=1)
    q("Asosiy vositalar", fa_jami, bold=1)
    for h in fa_hisoblar:
        if any(abs(x) >= EPS for x in V("fa:" + h)):
            q(h.rsplit(" - ", 1)[0], V("fa:" + h), indent=1)
    q("JAMI AKTIV", aktiv, bold=1)

    q("PASSIV", bold=1, bosh=1)
    q("Kreditorlik", kreditorlik, bold=1)
    q("Yetkazib beruvchilar (so'm)", V("yb_uzs"), indent=1)
    q("Yetkazib beruvchilar (USD, so'mda)", V("yb_usd"), indent=1)
    q("Mijozlardan olingan avans", V("mijoz_avans"), indent=1)
    q("Xodimlar (ish haqi qarzi)", V("xodim_qarz"), indent=1)
    if any(abs(x) >= EPS for x in V("boshqa_kred")):
        q("Boshqa majburiyatlar", V("boshqa_kred"), indent=1)
    q("Kapital", kapital, bold=1)
    q("Ustav fondi", V("ustav"), indent=1)
    q("Taqsimlanmagan foyda — oldingi oylar", V("retained_prior"), indent=1)
    q("Taqsimlanmagan foyda — joriy oy", V("foyda"), indent=1)
    q("Dividend — joriy oy", [-x for x in V("div_oy")], indent=1)
    q("JAMI PASSIV", passiv, bold=1)
    q("Check (Aktiv − Passiv)", [a - p for a, p in zip(aktiv, passiv)], bold=1)

    q("Foyda va dividend (oy davomida)", bold=1, bosh=1)
    q("Sof foyda", V("foyda"))
    q("O'tgan oyga nisbatan, so'm", [f - o for f, o in zip(V("foyda"), oldingi_foyda)], indent=1)
    q("O'tgan oyga nisbatan, %",
      [100.0 * (f - o) / abs(o) if abs(o) > EPS else 0 for f, o in zip(V("foyda"), oldingi_foyda)],
      indent=1, fmt="pct")
    q("Dividend jami", V("div_oy"))
    for h in meta.dividend:
        q(h.rsplit(" - ", 1)[0], V("div:" + h), indent=1)
    q("Dividend / sof foyda, %",
      [100.0 * d_ / f if abs(f) > EPS else 0 for d_, f in zip(V("div_oy"), V("foyda"))], fmt="pct")
    q("Biznesda qolgan foyda (foyda − dividend)", [f - d_ for f, d_ in zip(V("foyda"), V("div_oy"))])
    q("Taqsimlanmagan foyda (oy oxiri, jami)", V("retained_jami"))

    columns = _oy_ustun_deflari(
        oylar, [{"fieldname": "korsatkich", "label": _("Ko'rsatkich"), "fieldtype": "Data", "width": 330}]
    )

    oxirgi = len(oylar) - 1
    summary = [
        {"value": flt(aktiv[oxirgi], 0), "label": _("Jami aktiv ({0})").format(oylar[oxirgi].label), "datatype": "Currency", "indicator": "Blue"},
        {"value": flt(pul[oxirgi], 0), "label": _("Pul"), "datatype": "Currency", "indicator": "Green"},
        {"value": flt(debitorlik[oxirgi], 0), "label": _("Debitorlik"), "datatype": "Currency", "indicator": "Orange"},
        {"value": flt(kreditorlik[oxirgi], 0), "label": _("Kreditorlik"), "datatype": "Currency", "indicator": "Red"},
        {"value": flt(kapital[oxirgi], 0), "label": _("Kapital"), "datatype": "Currency", "indicator": "Blue"},
    ]
    xabar = None
    if oylar[oxirgi].partial:
        xabar = _("* {0} — {1} holatiga (oy yopilmagan: oylik va boshqa oylik xarajatlar hali to'liq emas).").format(
            oylar[oxirgi].label.rstrip("*"), frappe.utils.formatdate(oylar[oxirgi].cutoff)
        )
    return columns, data, xabar, None, summary


# --------------------------------------------------------------------------- Debitorlar / Kreditorlar

def _kontragent_korinishi(oylar, debitor):
    meta = _hisob_meta()
    n = len(oylar)

    qatorlar = {}  # (turi, party, hisob) -> [saldo_per_oy]
    for i, o in enumerate(oylar):
        for p in _party_qoldiqlar(o.cutoff, meta.ar_ap):
            turi = TURI_UZ.get(p.party_type, p.party_type)
            key = (turi, p.party, p.account)
            qatorlar.setdefault(key, [0.0] * n)[i] = p.bal

    # Xodim nomini o'qilishi uchun
    xodim_nomlar = dict(frappe.db.sql("SELECT name, employee_name FROM `tabEmployee`"))

    yon = 1 if debitor else -1
    data = []
    jami = [0.0] * n
    for turi in sorted({k[0] for k in qatorlar}, key=lambda t: TURI_TARTIB.get(t, 9)):
        guruh = []
        for (t, party, hisob), vals in qatorlar.items():
            if t != turi:
                continue
            korinadigan = [v * yon if v * yon > EPS else 0.0 for v in vals]
            if not any(korinadigan):
                continue
            nom = party
            if t == "Xodim" and xodim_nomlar.get(party):
                nom = f"{xodim_nomlar[party]} ({party})"
            guruh.append({"turi": t, "kontragent": nom, "hisob": hisob.rsplit(" - ", 1)[0],
                          "vals": korinadigan})
        if not guruh:
            continue
        guruh.sort(key=lambda r: -r["vals"][n - 1])
        g_jami = [0.0] * n
        for r in guruh:
            row = {"turi": r["turi"], "kontragent": r["kontragent"], "hisob": r["hisob"]}
            for i in range(n):
                row[f"oy_{i}"] = flt(r["vals"][i], 2) or None
                g_jami[i] += r["vals"][i]
                jami[i] += r["vals"][i]
            row["ozgarish"] = flt(r["vals"][n - 1] - (r["vals"][n - 2] if n > 1 else 0), 2)
            data.append(row)
        srow = {"turi": "", "kontragent": f"Jami — {turi}", "hisob": "", "bold": 1}
        for i in range(n):
            srow[f"oy_{i}"] = flt(g_jami[i], 2)
        srow["ozgarish"] = flt(g_jami[n - 1] - (g_jami[n - 2] if n > 1 else 0), 2)
        data.append(srow)

    jrow = {"turi": "", "kontragent": "JAMI", "hisob": "", "bold": 1}
    for i in range(n):
        jrow[f"oy_{i}"] = flt(jami[i], 2)
    jrow["ozgarish"] = flt(jami[n - 1] - (jami[n - 2] if n > 1 else 0), 2)
    data.append(jrow)

    columns = _oy_ustun_deflari(oylar, [
        {"fieldname": "turi", "label": _("Turi"), "fieldtype": "Data", "width": 125},
        {"fieldname": "kontragent", "label": _("Kontragent"), "fieldtype": "Data", "width": 260},
        {"fieldname": "hisob", "label": _("Hisob"), "fieldtype": "Data", "width": 110},
    ])
    columns.append({"fieldname": "ozgarish", "label": _("O'zgarish (oxirgi oy)"), "fieldtype": "Currency", "width": 140})

    nom = _("Jami debitorlik") if debitor else _("Jami kreditorlik")
    summary = [{"value": flt(jami[n - 1], 0), "label": f"{nom} ({oylar[n-1].label})",
                "datatype": "Currency", "indicator": "Orange" if debitor else "Red"}]
    return columns, data, None, None, summary


# --------------------------------------------------------------------------- Zaxiralar

def _zaxira_korinishi(oylar):
    guruh_xarita = _zaxira_guruh_xaritasi()
    boshqa_label = ZAXIRA_GURUHLAR[-1][0]
    item_info = {
        r.name: r for r in frappe.get_all("Item", fields=["name", "item_name", "item_group"])
    }
    n = len(oylar)

    qatorlar = {}  # item -> [qiymat_per_oy]
    for i, o in enumerate(oylar):
        for item, v in _sle_qoldiqlar(o.cutoff).items():
            qatorlar.setdefault(item, [0.0] * n)[i] = v

    guruh_tartib = {label: i for i, (label, _g) in enumerate(ZAXIRA_GURUHLAR)}
    boylab = {}
    for item, vals in qatorlar.items():
        if not any(abs(v) >= EPS for v in vals):
            continue
        info = item_info.get(item)
        label = guruh_xarita.get(info.item_group if info else None, boshqa_label)
        boylab.setdefault(label, []).append((item, vals))

    data = []
    jami = [0.0] * n
    for label in sorted(boylab, key=lambda l: guruh_tartib.get(l, 9)):
        itemlar = sorted(boylab[label], key=lambda x: -x[1][n - 1])
        g_jami = [0.0] * n
        for item, vals in itemlar:
            info = item_info.get(item)
            row = {
                "guruh": label,
                "tovar": (info.item_name if info and info.item_name else item),
            }
            for i in range(n):
                row[f"oy_{i}"] = flt(vals[i], 2) or None
                g_jami[i] += vals[i]
                jami[i] += vals[i]
            row["ozgarish"] = flt(vals[n - 1] - (vals[n - 2] if n > 1 else 0), 2)
            data.append(row)
        srow = {"guruh": "", "tovar": f"Jami — {label}", "bold": 1}
        for i in range(n):
            srow[f"oy_{i}"] = flt(g_jami[i], 2)
        srow["ozgarish"] = flt(g_jami[n - 1] - (g_jami[n - 2] if n > 1 else 0), 2)
        data.append(srow)

    jrow = {"guruh": "", "tovar": "JAMI (SLE bo'yicha)", "bold": 1}
    for i in range(n):
        jrow[f"oy_{i}"] = flt(jami[i], 2)
    jrow["ozgarish"] = flt(jami[n - 1] - (jami[n - 2] if n > 1 else 0), 2)
    data.append(jrow)

    columns = _oy_ustun_deflari(oylar, [
        {"fieldname": "guruh", "label": _("Guruh"), "fieldtype": "Data", "width": 170},
        {"fieldname": "tovar", "label": _("Tovar"), "fieldtype": "Data", "width": 260},
    ])
    columns.append({"fieldname": "ozgarish", "label": _("O'zgarish (oxirgi oy)"), "fieldtype": "Currency", "width": 140})

    summary = [{"value": flt(jami[n - 1], 0), "label": _("Jami zaxira ({0})").format(oylar[n-1].label),
                "datatype": "Currency", "indicator": "Blue"}]
    return columns, data, None, None, summary
