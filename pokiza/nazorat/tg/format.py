"""Telegram HTML formatlash: KPI qatorlari, raqamlar, Markdown -> Telegram HTML."""
import html
import re

from pokiza.nazorat.metrics import BELGI

def esc(s):
    """Telegram HTML uchun xavfsiz matn. Frappe Data/Small Text maydonlarini saqlashda o'zi HTML-escape qiladi
    ("<" -> "&lt;"), shuning uchun avval unescape — aks holda foydalanuvchi "&lt;" ni ko'radi (ikki marta escape)."""
    return html.escape(html.unescape(str(s if s is not None else "")), quote=False)


def son(v, kasr=0):
    """1234567.8 -> '1 234 568' (o'zbekcha: bo'shliq bilan, vergul kasr)."""
    if v is None:
        return "—"
    s = f"{v:,.{kasr}f}".replace(",", " ").replace(".", ",")
    return s


def summa(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9:
        return f"{son(v / 1e9, 2)} mlrd"
    if a >= 1e6:
        return f"{son(v / 1e6, 1)} mln"
    return son(v)


def qiymat(v, birlik):
    if v is None:
        return "—"
    if birlik == "so'm":
        return f"{summa(v)} so'm"
    if birlik == "$":
        return f"${son(v)}"
    if birlik == "%":
        return f"{son(v, 2 if 0 < abs(v) < 1 else 1)}%"
    if birlik == "tonna":
        return f"{son(v, 1)} t"
    if birlik == "so'm/kg":
        return f"{son(v)} so'm/kg"
    if birlik in ("mijoz", "mahsulot", "vazifa"):
        return f"{son(v)} ta"
    return f"{son(v, 2)} {birlik}"


QISQA = {
    "A1": "Quvvat", "A2": "Savdo", "A3": "Rentabellik", "A4": "O'rtacha chek", "A5": "Sof daromad",
    "B1": "Mijoz rentabelligi", "B2": "Mijoz dinamikasi", "B3": "Top mahsulotlar", "B4": "Kategoriyalar",
    "C1": "Postavshiklar", "C2": "Debitorlik", "C3": "Xarajatlar", "C4": "Brak", "C5": "Dividend",
    "C6": "Foyda taqsimoti", "D1": "Vazifalar",
    "H1": "Savdo", "H2": "O'rtacha chek", "H3": "Quvvat", "H4": "Jim mijozlar", "H5": "Nazoratdagi mijozlar",
    "H6": "Kechikkan vazifalar", "K1": "Savdo", "K2": "Ishlab chiqarish", "K3": "Kassa kirimi", "K4": "Dividend",
}
ASL = {"H1": "A2", "K1": "A2", "H2": "A4", "H3": "A1", "K2": "A1", "K4": "C5"}  # alias -> asosiy
NEYTRAL = "▫️"


def belgi(m):
    return BELGI.get(m.get("rang")) if m.get("rang") else NEYTRAL


def qisqa(code):
    return QISQA.get(code, code)


def bar(foiz, n=10):
    """▰▰▰▰▰▰▰▱▱▱ — reja bajarilishi (100% dan oshsa to'la)."""
    k = max(0, min(n, round((foiz or 0) / 100 * n)))
    return "▰" * k + "▱" * (n - k)


def foiz_s(v):
    return "—" if v is None else f"{son(v, 0 if abs(v) >= 10 else 1)}%"


def strelka(ozg):
    if ozg is None:
        return ""
    return f"↑{foiz_s(ozg)}" if ozg > 0 else f"↓{foiz_s(abs(ozg))}" if ozg < 0 else "→ 0%"


def ozgarish_s(m):
    """Oldingi davrga nisbatan: foizli ko'rsatkichda pp farq, boshqalarida % o'zgarish."""
    if m["birlik"] == "%":
        a, b = m.get("fakt"), (m.get("oldingi") or {}).get("fakt")
        if a is None or b is None:
            return ""
        d = round(a - b, 1)
        return f"↑{son(d, 1)} pp" if d > 0 else f"↓{son(abs(d), 1)} pp" if d < 0 else "→ 0 pp"
    return strelka(m.get("ozgarish_%"))


def reja_qator(m):
    """Fakt ostidagi qator: progress bar (yig'iladigan) yoki rejadan farq (foizli)."""
    b = m["birlik"]
    if m.get("reja") is None:
        return ""
    if m.get("bajarilish_%") is not None:
        return f"{bar(m['bajarilish_%'])} <b>{foiz_s(m['bajarilish_%'])}</b> · reja {qiymat(m['reja'], b)}"
    if b == "%" and m.get("fakt") is not None:
        d = round(m["fakt"] - m["reja"], 1)
        return f"reja {qiymat(m['reja'], b)} · rejadan {'+' if d >= 0 else '−'}{son(abs(d), 1)} pp"
    return f"reja {qiymat(m['reja'], b)}"


def kpi_qator(m, nom=None):
    """Hisobotdagi ixcham ko'rinish (1–2 qator)."""
    nom = nom or qisqa(m["code"])
    if m.get("mavjud") is False:
        return f"{NEYTRAL} <b>{esc(nom)}</b> — hali yo'q"
    if m.get("fakt") is None:
        return f"{NEYTRAL} <b>{esc(nom)}</b> — <i>ma'lumot yo'q</i>"
    v = qiymat(m.get("fakt"), m["birlik"])
    oz = ozgarish_s(m)
    rq = reja_qator(m)
    if rq:
        # foizli rejada (rentabellik) rejadan farq allaqachon pp — ikkinchi pp chalkashtiradi
        oz = "" if m.get("bajarilish_%") is None else oz
        return f"{belgi(m)} <b>{esc(nom)}</b> — {v}\n      {rq}" + (f" · {oz}" if oz else "")
    return f"{belgi(m)} <b>{esc(nom)}</b> — {v}" + (f"  {oz}" if oz else "")


# ---------- batafsil ----------
# tafsilot jadvalidan qaysi ustunlar qanday ko'rinadi: (sarlavha, nom kaliti, [(kalit, format)])
TAFSILOT = {
    "A1": ("Normalar", "norma", [("kg", "kg"), ("ulush_%", "%")]),
    "A2": ("Mijozlar", "mijoz", [("summa", "som"), ("ulush_%", "%")]),
    "A4": ("Mahsulotlar", "mahsulot", [("narx_kg", "somkg"), ("kg", "kg")]),
    "B1": ("Mijozlar", "mijoz", [("rentabellik_%", "%"), ("foyda", "som")]),
    "B2": ("Mijozlar", "mijoz", [("farq", "+som"), ("ozgarish_%", "+%")]),
    "B3": ("Mahsulotlar", "mahsulot", [("summa", "som"), ("ulush_%", "%")]),
    "B4": ("Kategoriyalar", "kategoriya", [("savdo_ulush_%", "ulush%"), ("savdo", "som"), ("yalpi_marja_%", "marja%")]),
    "C1": ("Postavshiklar", "postavshik", [("yopish_%", "%"), ("ostatka", "som")]),
    "C2": ("Qarzdorlar", "mijoz", [("qarz", "som"), ("muddat", "sana")]),
    "C3": ("Xarajat moddalari", "hisob", [("summa", "som"), ("savdoga_%", "%"), ("turi", "txt")]),
    "C4": ("Brak va vozvrat", "nomi", [("kg", "kg"), ("summa", "som")]),
    "C5": ("Yozuvlar", "kim", [("summa", "som"), ("sana", "sana")]),
    "C6": ("Kim bo'yicha", "kim", [("summa", "som"), ("foydadan_%", "%")]),
    "D1": ("Xodimlar", "xodim", [("bajarilgan", "n"), ("jami", "/n"), ("bajarilish_%", "%")]),
    "H4": ("Jim mijozlar", "mijoz", [("jim_kun", "kun")]),
    "H6": ("Vazifalar", "vazifa", [("xodim", "txt"), ("holat", "txt")]),
}
QISM = {
    "A1": [("kunlik_ortacha_kg", "O'rtacha kuniga", "kg"), ("ishlangan_kunlar", "Ishlangan kun", "n"),
           ("reja_t", "Oylik reja (t)", "n"), ("rejaga_%", "Rejaga nisbatan", "%")],
    "A3": [("savdo", "Savdo", "som"), ("tannarx", "Tannarx", "som"), ("xarajatlar", "Xarajatlar", "som"),
           ("sof_foyda", "Sof foyda", "som")],
    "A5": [("sof_foyda_som", "Sof foyda", "som"), ("kurs", "Kurs", "n")],
    "B2": [("osgan", "O'sgan", "n"), ("tushgan", "Tushgan", "n"), ("yangi", "Yangi", "n"), ("yoqolgan", "Yo'qolgan", "n")],
    "C1": [("olingan", "Olingan", "som"), ("yopilgan", "Yopilgan", "som"), ("jami_ostatka", "Ostatka", "som")],
    "C2": [("buzgan", "Muddatni buzgan", "n"), ("buzilgan_summa", "Buzilgan summa", "som")],
    "C3": [("jami_xarajat", "Jami xarajat", "som")],  # savdo summasi — faqat savdo ko'rsatkichlarida
    "C4": [("ishlab_chiqarilgan_kg", "Ishlab chiqarildi", "kg"), ("brak_kg", "Brak", "kg"),
           ("brak_summa", "Brak summasi", "som"), ("vozvrat_kg", "Vozvrat", "kg")],
    "C5": [("sof_foydadan_%", "Sof foydadan", "%")],
    "C6": [("sof_foyda", "Sof foyda", "som"), ("yechilgan", "Dividend", "som"),
           ("boshqa_yonalishlar", "Boshqa yo'nalishlar", "som"), ("oborotda_qolgan", "Oborotda", "som")],
    "D1": [("jami", "Jami", "n"), ("bajarilgan", "Bajarildi", "n"), ("bajarilmagan", "Bajarilmadi", "n")],
    "H4": [("faol_mijozlar_90_kun", "Faol mijozlar (90 kun)", "n")],
    "H6": [("berilgan", "Berildi", "n"), ("bajarilgan", "Bajarildi", "n"), ("rad_etilgan", "Rad etildi", "n"),
           ("muddati_otgan", "Kechikdi", "n")],
    "K1": [("oy_boshidan", "Oy boshidan", "som"), ("oylik_bajarilish_%", "Oylik reja", "%")],
    "K4": [("oy_boshidan", "Oy boshidan", "som")],
}


def _f(v, fmt):
    if v is None or v == "":
        return ""
    if fmt == "som":
        return summa(v)
    if fmt == "+som":
        return ("+" if v > 0 else "") + summa(v)
    if fmt == "%":
        return foiz_s(v)
    if fmt == "ulush%":
        return f"ulushi {foiz_s(v)}"
    if fmt == "marja%":
        return f"marja {foiz_s(v)}"
    if fmt == "+%":
        return ("+" if v > 0 else "") + foiz_s(v)
    if fmt == "kg":
        return f"{son(v, 1 if abs(v) < 100 and v != int(v) else 0)} kg"
    if fmt == "somkg":
        return f"{son(v)} so'm/kg"
    if fmt == "kun":
        return f"{son(v)} kun"
    if fmt == "n":
        return son(v)
    if fmt == "/n":
        return "/" + son(v)
    if fmt == "sana":
        s = str(v)[:10]
        return f"{s[8:10]}.{s[5:7]}" if len(s) == 10 and s[4] == "-" else esc(s)
    return esc(v)


def _qisqart(s, n=34):
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def tafsilot_qator(code, r, i):
    _, nom_k, ustun = TAFSILOT[ASL.get(code, code)]
    qism = []
    for k, fmt in ustun:
        v = _f(r.get(k), fmt)
        if not v:
            continue
        if fmt == "/n" and qism:
            qism[-1] += v
        else:
            qism.append(v)
    rang = r.get("rang")
    boshi = BELGI[rang] if rang in BELGI and rang else f"{i}."
    return f"{boshi} {esc(_qisqart(r.get(nom_k)))}" + (f" — {' · '.join(qism)}" if qism else "")


def kpi_batafsil(m, qatorlar=8):
    """Bitta ko'rsatkich kartasi: katta raqam, reja/bar, oldingi davr, asosiy tarkib, top ro'yxat, eslatmalar."""
    code = m["code"]
    if m.get("mavjud") is False:
        return f"{NEYTRAL} <b>{esc(qisqa(code))}</b>: hali yo'q — {esc(m.get('sabab'))}"
    b = m["birlik"]
    out = [f"{belgi(m)} <b>{esc(m['nom'])}</b>", f"<i>{esc(m['davr']['nom'])}</i>", "",
           f"<b>{qiymat(m.get('fakt'), b)}</b>"]
    rq = reja_qator(m)
    if rq:
        out.append(rq)
    old = m.get("oldingi") or {}
    if old.get("fakt") is not None:
        oz = ozgarish_s(m)
        out.append(f"{esc(old['davr'])}: {qiymat(old['fakt'], b)}" + (f" · {oz}" if oz else ""))
    if m.get("prognoz"):
        out.append(f"📈 Oy oxiriga taxmin: {summa(m['prognoz']['oy_oxiriga_taxmin'])} so'm")
    q = m.get("qism") or {}
    qs = [f"{nom}: <b>{_f(q.get(k), fmt)}</b>" for k, nom, fmt in QISM.get(code, QISM.get(ASL.get(code), []))
          if q.get(k) not in (None, "")]
    if code == "C3":
        qs += [f"{t}: <b>{summa(q[t]['summa'])}</b> ({foiz_s(q[t].get('savdoga_%'))} savdodan)"
               for t in ("Doimiy", "O'zgaruvchi") if isinstance(q.get(t), dict)]
    if code in ("C5", "K4") and q.get("kim_boyicha"):
        qs += [f"{esc(k)}: <b>{summa(v)}</b>" for k, v in q["kim_boyicha"].items()]
    if qs:
        out += [""] + qs
    t = m.get("tafsilot") or []
    spec = TAFSILOT.get(ASL.get(code, code))
    if t and spec:
        out += ["", f"<b>{spec[0]}</b>" + (f" <i>(top {qatorlar} / {len(t)})</i>" if len(t) > qatorlar else "")]
        out += [tafsilot_qator(code, r, i) for i, r in enumerate(t[:qatorlar], 1)]
    iz = m.get("izoh") or []
    if iz:
        out += ["", eslatmalar(iz)]
    return "\n".join(out)


def eslatmalar(items, n=8):
    """Yig'iladigan blok: yopiq holda qisqa ko'rinadi, bosilsa ochiladi."""
    items = list(dict.fromkeys(items))
    body = "\n".join(f"• {esc(x)}" for x in items[:n])
    more = f"\n… yana {len(items) - n} ta" if len(items) > n else ""
    return f"<blockquote expandable>⚠️ <b>{len(items)} ta eslatma</b>\n{body}{more}</blockquote>"


def md_to_html(text):
    """AI javobi (Markdown) -> Telegram HTML: **qalin**, *kursiv*, `kod`, ```blok```, sarlavha, jadval -> <pre>."""
    text = text or ""
    bloklar = []

    def _blok(m):
        bloklar.append(f"<pre>{esc(m.group(1).strip())}</pre>")
        return f"\x00{len(bloklar) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", _blok, text, flags=re.S)
    # Markdown jadval -> monospace blok
    lines, out, tbl = text.split("\n"), [], []
    for ln in lines + [""]:
        if re.match(r"^\s*\|.*\|\s*$", ln):
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", ln):
                tbl.append([c.strip() for c in ln.strip().strip("|").split("|")])
            continue
        if tbl:
            w = [max(len(r[i]) if i < len(r) else 0 for r in tbl) for i in range(max(map(len, tbl)))]
            rows = ["  ".join((r[i] if i < len(r) else "").ljust(w[i]) for i in range(len(w))).rstrip() for r in tbl]
            bloklar.append(f"<pre>{esc(chr(10).join(rows))}</pre>")
            out.append(f"\x00{len(bloklar) - 1}\x00")
            tbl = []
        out.append(ln)
    text = esc("\n".join(out[:-1] if out and out[-1] == "" else out))
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^(\s*)[-*]\s+", lambda m: m.group(1) + "• ", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: bloklar[int(m.group(1))], text)
