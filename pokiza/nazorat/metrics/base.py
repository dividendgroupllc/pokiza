"""KPI dvigateli yadrosi: registry, kontekst (sozlama + reja), rang, hisoblash.

Har ko'rsatkich bitta funksiya: fn(ctx, full) -> dict(fakt=..., [reja, tafsilot, izoh, qism...]).
Telegram hisoboti, rahbar paneli va AI (`get_kpi`) shu yerdan oladi — raqamlar hamma joyda bir xil.
"""
from dataclasses import dataclass, field

import frappe
from frappe.utils import flt

from pokiza.nazorat.metrics.davr import Davr, ish_kunlari

YASHIL, SARIQ, QIZIL = "yashil", "sariq", "qizil"
BELGI = {YASHIL: "🟢", SARIQ: "🟡", QIZIL: "🔴", None: "⚪"}
KG_UOMS = ("кг", "Kg", "kg")


@dataclass
class Spec:
    code: str
    nom: str
    fn: object
    birlik: str
    turi: str  # standart davr turi: oy / hafta / kun
    bolim: str  # sotuv / ishlab_chiqarish / buxgalteriya / ombor / rahbar
    additive: bool = True  # yig'iladigan (savdo, tonna) — qisman davrda reja proporsional kesiladi
    rang_trend: bool = False  # rang reja bilan emas, oldingi davr bilan (o'sdi/tushdi)
    tavsif: str = ""
    davrlar: tuple = ("oy", "hafta", "kun", "oraliq")


REGISTRY: dict[str, Spec] = {}

# Hali qurilmagan ko'rsatkichlar — AI va hisobot halol "yo'q" deyishi uchun
REJADA: dict = {}


def metric(code, nom, birlik, turi, bolim, **kw):
    def deco(fn):
        REGISTRY[code] = Spec(code=code, nom=nom, fn=fn, birlik=birlik, turi=turi, bolim=bolim,
                              tavsif=(fn.__doc__ or "").strip(), **kw)
        return fn
    return deco


def alias(code, asl, nom, turi, **kw):
    """Bir funksiya, boshqa standart davr (masalan H1 = A2 haftalik)."""
    s = REGISTRY[asl]
    REGISTRY[code] = Spec(code=code, nom=nom, fn=s.fn, birlik=s.birlik, turi=turi, bolim=s.bolim,
                          additive=s.additive, rang_trend=s.rang_trend, tavsif=s.tavsif,
                          **{"davrlar": s.davrlar, **kw})


@dataclass
class Ctx:
    d: Davr
    full: bool = True
    _cache: dict = field(default_factory=dict)

    @property
    def f(self):
        return self.d.f

    @property
    def t(self):
        return self.d.t

    @property
    def p(self):
        return {"f": self.d.f, "t": self.d.t, "kg": KG_UOMS}

    def sozlama(self):
        if "s" not in self._cache:
            s = frappe.get_cached_doc("Nazorat Sozlamalari")
            ich = frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari")
            self._cache["s"] = frappe._dict(
                oylik_quvvat_t=flt(s.oylik_quvvat_t) or 180,
                tolov_kuni=int(s.postavshik_tolov_kuni or 10), jimlik_kun=int(s.mijoz_jimlik_kun or 7),
                konsentratsiya=flt(s.konsentratsiya_foiz) or 25,
                quvvat_yashil=flt(s.quvvat_yashil) or 90, quvvat_sariq=flt(s.quvvat_sariq) or 70,
                savdo_yashil=flt(s.savdo_yashil) or 95, savdo_sariq=flt(s.savdo_sariq) or 85,
                marja_sariq_pp=flt(s.marja_sariq_pp) or 0.5, marja_qizil_pp=flt(s.marja_qizil_pp) or 1,
                daromad_yashil=flt(s.daromad_yashil_usd) or 50000, daromad_sariq=flt(s.daromad_sariq_usd) or 40000,
                chek_tol=flt(s.chek_ozgarmas_foiz) or 0.5,
                b1_yashil=flt(s.get("b1_yashil")) or 25, b1_sariq=flt(s.get("b1_sariq")) or 20,
                b4_yashil=flt(s.get("b4_yashil")) or 35, b4_sariq=flt(s.get("b4_sariq")) or 30,
                b2_yashil=flt(s.get("b2_yashil")) or 30, b2_sariq=flt(s.get("b2_sariq")) or 50,
                b3_yashil=int(s.get("b3_yashil") or 8), b3_sariq=int(s.get("b3_sariq") or 5),
                c3_yashil=flt(s.get("c3_yashil")) or 18, c3_sariq=flt(s.get("c3_sariq")) or 22,
                c4_yashil=flt(s.get("c4_yashil")) or 1, c4_sariq=flt(s.get("c4_sariq")) or 2,
                c5_sariq=flt(s.get("c5_sariq")) or 80, c6_min=flt(s.get("c6_min")) or 30,
                kunlik_quvvat_kg=flt(ich.kunlik_quvvat_kg) or 6900, yakshanba=bool(ich.yakshanba_ishlaydi),
                dividend_egasi={"Дивиденд 1": s.dividend_1_egasi, "Дивиденд 2": s.dividend_2_egasi,
                                "Дивиденд 3": s.dividend_3_egasi},
            )
        return self._cache["s"]

    def oylik_reja(self):
        """Davr tugagan oyning rejasi (Oylik Reja) yoki None."""
        if "r" not in self._cache:
            oy = self.reja_oyi()
            name = frappe.db.get_value("Oylik Reja", {"yil": oy.year, "oy": f"{oy.month:02d}"},
                                       ["savdo_reja", "sof_marja_reja", "quvvat_reja_t", "sof_daromad_usd_reja"],
                                       as_dict=True)
            self._cache["r"] = name
        return self._cache["r"]

    def reja_oyi(self):
        """Qaysi oyning rejasi: hafta — kunlarining ko'pi tushgan oy (payshanba), qolganlari — davr oxiri oyi."""
        from datetime import timedelta
        return self.d.f + timedelta(days=3) if self.d.turi == "hafta" else self.d.t

    def kurs(self):
        return self.kurs_info()["kurs"]

    def kurs_info(self):
        """USD->UZS faqat Currency Exchange'dan: davr oxirigacha bo'lgan eng so'nggi kurs (yo'q bo'lsa kurs=None)."""
        if "kurs" in self._cache:
            return self._cache["kurs"]
        row = frappe.db.sql(
            """SELECT exchange_rate, date FROM `tabCurrency Exchange`
            WHERE from_currency = 'USD' AND to_currency = 'UZS' AND date <= %s AND exchange_rate > 0
            ORDER BY date DESC, modified DESC LIMIT 1""", self.d.t)
        info = {"kurs": flt(row[0][0]), "sana": row[0][1]} if row else {"kurs": None, "sana": None}
        self._cache["kurs"] = info
        return info

    def ish_kunlari(self, f=None, t=None):
        return ish_kunlari(f or self.d.f, t or self.d.t, self.sozlama().yakshanba)

    def kesim(self, reja_toliq):
        """Davr rejasi -> (bugungacha kesilgan reja, to'liq reja yoki None). Davr tugagan bo'lsa kesilmaydi."""
        if reja_toliq is None or not self.d.qisman:
            return reja_toliq, None
        jami = self.ish_kunlari(self.d.f, self.d.tabiiy_t) or 1
        return reja_toliq * self.ish_kunlari() / jami, reja_toliq

    def davr_rejasi(self, oylik):
        """Oylik reja qiymatidan shu davrning (to'liq) rejasi: oy=1, hafta=1/4 (TZ H1), kun/oraliq=ish kunlari ulushi."""
        if oylik is None:
            return None
        if self.d.turi == "oy":
            return oylik
        return oylik * self.oy_ulushi()

    def oy_ulushi(self):
        """Davr oylik rejaning qancha qismi (ish kunlari bo'yicha). Hafta = 1/4 (TZ H1)."""
        if self.d.turi == "hafta":
            return 0.25
        from frappe.utils import get_first_day, get_last_day
        of, ot = get_first_day(self.reja_oyi()), get_last_day(self.reja_oyi())
        jami = self.ish_kunlari(of, ot) or 1
        return self.ish_kunlari(max(self.d.f, of), min(self.d.tabiiy_t, ot)) / jami


def foiz(a, b):
    return round(flt(a) / flt(b) * 100, 1) if flt(b) else None


def ozgarish(yangi, eski):
    if yangi is None or eski is None or not flt(eski):
        return None
    return round((flt(yangi) - flt(eski)) / abs(flt(eski)) * 100, 1)


def rang_past(v, yashil, sariq):
    """Kam bo'lgani yaxshi: v <= yashil — yashil, v <= sariq — sariq, aks holda qizil. v None — rangsiz."""
    if v is None:
        return None
    return YASHIL if v <= yashil else SARIQ if v <= sariq else QIZIL


def rang_chegara(qiymat, yashil, sariq):
    if qiymat is None:
        return None
    return YASHIL if qiymat >= yashil else SARIQ if qiymat >= sariq else QIZIL


def rang_trend(ozg, tol):
    if ozg is None:
        return None
    return YASHIL if ozg > tol else QIZIL if ozg < -tol else SARIQ


def _round(v):
    if isinstance(v, float):
        return round(v, 2) if abs(v) < 1000 else round(v)
    return v


def compute(code, davr=None, full=True, trend=0, bugun=None):
    """Ko'rsatkichni hisoblaydi. davr: Davr yoki matn ('2026-10', 'kecha', ...). trend: nechta davr tarixi."""
    code = (code or "").upper().strip()
    if code in REJADA:
        return {"code": code, "mavjud": False, "sabab": REJADA[code]}
    spec = REGISTRY.get(code)
    if not spec:
        raise KeyError(f"Noma'lum ko'rsatkich: {code}")
    d = davr if isinstance(davr, Davr) else Davr.parse(davr, spec.turi, bugun)
    if d.turi not in spec.davrlar:
        raise ValueError(f"{code} uchun davr turi {', '.join(spec.davrlar)} bo'lishi kerak")

    ctx = Ctx(d, full=full)
    res = spec.fn(ctx)
    fakt = res.get("fakt")

    out = {"code": code, "nom": spec.nom, "birlik": spec.birlik, "bolim": spec.bolim, "davr": d.as_dict(),
           "fakt": _round(fakt)}

    prev = spec.fn(Ctx(d.oldingi(), full=False)).get("fakt")
    out["oldingi"] = {"davr": d.oldingi().nom, "fakt": _round(prev)}
    out["ozgarish_%"] = ozgarish(fakt, prev)

    reja = res.get("reja")
    if reja is not None:
        out["reja"] = _round(reja)
        if spec.additive:
            out["bajarilish_%"] = foiz(fakt, reja)
        if res.get("reja_toliq") is not None:
            out["reja_toliq"] = _round(res["reja_toliq"])
            out["izoh"] = ["Davr tugamagan: reja o'tgan ish kunlariga proporsional olindi; to'liq davr rejasi 'reja_toliq'da."]
    out["rang"] = res.get("rang") if "rang" in res else (
        rang_trend(out["ozgarish_%"], ctx.sozlama().chek_tol) if spec.rang_trend else None)
    out["belgi"] = BELGI.get(out["rang"])
    for k in ("qism", "tafsilot", "prognoz"):
        if res.get(k) is not None:
            out[k] = res[k]
    out["izoh"] = out.get("izoh", []) + res.get("izoh", [])
    out["manba"] = res.get("manba", "")
    if trend:
        out["trend"] = [{"davr": x.kalit, "nom": x.nom, "fakt": _round(spec.fn(Ctx(x, full=False)).get("fakt"))}
                        for x in d.orqaga(int(trend))]
    return out


def royxat(bolim=None):
    rows = [{"code": s.code, "nom": s.nom, "birlik": s.birlik, "standart_davr": s.turi, "bolim": s.bolim}
            for s in REGISTRY.values() if not bolim or s.bolim == bolim]
    rows += [{"code": c, "mavjud": False, "sabab": r} for c, r in REJADA.items()]
    return sorted(rows, key=lambda r: r["code"])
