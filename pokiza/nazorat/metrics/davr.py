"""Davr (oy / hafta / kun / oraliq) — matndan o'qish, oldingi davr, ish kunlari."""
import re
from datetime import date, timedelta

from frappe.utils import add_days, add_months, date_diff, get_first_day, get_last_day, getdate, nowdate

TURLAR = ("oy", "hafta", "kun", "oraliq")
OY_NOMI = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


class DavrXato(ValueError):
    pass


def ish_kunlari(f, t, yakshanba=False):
    f, t = getdate(f), getdate(t)
    if t < f:
        return 0
    return sum(1 for i in range(date_diff(t, f) + 1) if yakshanba or add_days(f, i).weekday() != 6)


class Davr:
    """turi + [f, t]. `qisman` — davr hali tugamagan (bugun ichida): oldingi davr ham shuncha kun bilan olinadi."""

    def __init__(self, turi, f, t, tabiiy_t=None):
        self.turi, self.f, self.t = turi, getdate(f), getdate(t)
        self.tabiiy_t = getdate(tabiiy_t) if tabiiy_t else self.t
        if self.f > self.t:
            raise DavrXato("Davr boshi oxiridan keyin")

    @property
    def qisman(self):
        return self.t < self.tabiiy_t

    @property
    def kunlar(self):
        return date_diff(self.t, self.f) + 1

    # ---------- yaratish ----------
    @classmethod
    def oy(cls, yil, oy, bugun=None):
        f = date(int(yil), int(oy), 1)
        return cls._kesilgan("oy", f, get_last_day(f), bugun)

    @classmethod
    def hafta(cls, dushanba, bugun=None):
        f = getdate(dushanba)
        f = f - timedelta(days=f.weekday())
        return cls._kesilgan("hafta", f, f + timedelta(days=6), bugun)

    @classmethod
    def kun(cls, sana):
        d = getdate(sana)
        return cls("kun", d, d)

    @classmethod
    def _kesilgan(cls, turi, f, t, bugun=None):
        bugun = getdate(bugun or nowdate())
        if f > bugun:
            raise DavrXato("Kelajakdagi davr uchun fakt yo'q")
        return cls(turi, f, min(t, bugun), tabiiy_t=t)

    @classmethod
    def parse(cls, matn=None, turi=None, bugun=None):
        """None -> oxirgi TO'LIQ davr (oy: o'tgan oy, hafta: o'tgan hafta, kun: kecha).

        Qabul qiladi: 2026-10 | 2026-W44 | 2026-10-15 | 2026-10-01:2026-10-15 |
        joriy_oy, otgan_oy, joriy_hafta, otgan_hafta, bugun, kecha.
        """
        bugun = getdate(bugun or nowdate())
        s = (matn or "").strip().lower().replace("'", "").replace("‘", "").replace("’", "")
        if not s:
            s = {"oy": "otgan_oy", "hafta": "otgan_hafta", "kun": "kecha"}.get(turi or "oy", "otgan_oy")
        if s == "joriy_oy":
            return cls.oy(bugun.year, bugun.month, bugun)
        if s == "otgan_oy":
            p = add_months(bugun, -1)
            return cls.oy(p.year, p.month, bugun)
        if s == "joriy_hafta":
            return cls.hafta(bugun, bugun)
        if s == "otgan_hafta":
            return cls.hafta(bugun - timedelta(days=7), bugun)
        if s == "bugun":
            return cls.kun(bugun)
        if s == "kecha":
            return cls.kun(bugun - timedelta(days=1))
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})", s):
            if not 1 <= int(m[2]) <= 12:
                raise DavrXato(f"Oy noto'g'ri: {matn}")
            return cls.oy(m[1], m[2], bugun)
        if m := re.fullmatch(r"(\d{4})-w(\d{1,2})", s):
            try:
                return cls.hafta(date.fromisocalendar(int(m[1]), int(m[2]), 1), bugun)
            except ValueError:
                raise DavrXato(f"Hafta noto'g'ri: {matn}")
        if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})", s):
            f, t = getdate(m[1]), getdate(m[2])
            if (t - f).days > 400:
                raise DavrXato("Oraliq 400 kundan oshmasin")
            return cls("oraliq", f, min(t, bugun), tabiiy_t=t)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return cls.kun(s)
        raise DavrXato(
            f"Davr tushunarsiz: '{matn}'. Misollar: 2026-10, 2026-W44, 2026-10-15, "
            "2026-10-01:2026-10-15, joriy_oy, otgan_oy, joriy_hafta, otgan_hafta, bugun, kecha"
        )

    # ---------- navigatsiya ----------
    def oldingi(self):
        """Oldingi davr. Qisman davr bo'lsa — oldingi davrning shuncha kunlik bo'lagi (adolatli solishtirish)."""
        if self.turi == "oy":
            pf = get_first_day(add_months(self.f, -1))
            pt = get_last_day(pf)
            if self.qisman:
                pt = min(pt, add_days(pf, self.kunlar - 1))
            return Davr("oy", pf, pt, tabiiy_t=get_last_day(pf))
        if self.turi == "hafta":
            return Davr("hafta", self.f - timedelta(days=7), self.t - timedelta(days=7), self.tabiiy_t - timedelta(days=7))
        if self.turi == "kun":
            return Davr.kun(self.f - timedelta(days=1))
        n = self.kunlar
        return Davr("oraliq", self.f - timedelta(days=n), self.f - timedelta(days=1))

    def orqaga(self, n):
        """Trend uchun: shu davr va undan oldingi n-1 ta TO'LIQ davr (eskidan yangiga)."""
        out, d = [], self
        for _ in range(n):
            out.append(d)
            d = d._toliq_oldingi()
        return list(reversed(out))

    def _toliq_oldingi(self):
        if self.turi == "oy":
            pf = get_first_day(add_months(self.f, -1))
            return Davr("oy", pf, get_last_day(pf))
        if self.turi == "hafta":
            f = self.f - timedelta(days=7)
            return Davr("hafta", f, f + timedelta(days=6))
        return self.oldingi()

    # ---------- ko'rinish ----------
    @property
    def nom(self):
        if self.turi == "oy":
            s = f"{OY_NOMI[self.f.month]} {self.f.year}"
            return s + (f" (1–{self.t.day})" if self.qisman else "")
        if self.turi == "hafta":
            return f"{self.f:%d.%m}–{self.t:%d.%m.%Y}" + (" (davom etmoqda)" if self.qisman else "")
        if self.turi == "kun":
            return f"{self.f:%d.%m.%Y}"
        return f"{self.f:%d.%m.%Y}–{self.t:%d.%m.%Y}"

    @property
    def kalit(self):
        if self.turi == "oy":
            return f"{self.f:%Y-%m}"
        if self.turi == "hafta":
            y, w, _ = self.f.isocalendar()
            return f"{y}-W{w:02d}"
        if self.turi == "kun":
            return f"{self.f:%Y-%m-%d}"
        return f"{self.f:%Y-%m-%d}:{self.t:%Y-%m-%d}"

    def as_dict(self):
        return {"turi": self.turi, "kalit": self.kalit, "nom": self.nom, "from": str(self.f), "to": str(self.t),
                "qisman": self.qisman}

    def __repr__(self):
        return f"Davr({self.kalit}, {self.f}..{self.t})"
