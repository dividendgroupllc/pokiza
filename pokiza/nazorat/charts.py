"""KPI trend grafigi (PNG, Telegram uchun): oy -> 12 oy, hafta -> 12 hafta, kun -> 30 kun.

Bitta seriya (legenda yo'q, sarlavha nomlaydi), reja — kulrang punktir, oxirgi qiymat yozuv bilan.
Ranglar: dataviz standart palitrasi (series-1 ko'k, matn tokenlari).
"""
import io

from frappe.utils import getdate

from pokiza.nazorat.metrics import REGISTRY, Davr, compute
from pokiza.nazorat.metrics.davr import OY_NOMI, ish_kunlari

SURFACE, INK, INK2, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"
SONI = {"oy": 12, "hafta": 12, "kun": 30}


def _qisqa(v, birlik):
    if v is None:
        return ""
    if birlik == "so'm":
        return f"{v / 1e6:,.0f} mln".replace(",", " ")
    if birlik == "%":
        return f"{v:.1f}%".replace(".", ",")
    if birlik == "$":
        return f"${v:,.0f}".replace(",", " ")
    if birlik == "tonna":
        return f"{v:.1f} t".replace(".", ",")
    return f"{v:,.0f}".replace(",", " ")


def trend_png(code, turi=None, davr=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    spec = REGISTRY[code]
    turi = turi or spec.turi
    if turi not in SONI or turi not in spec.davrlar:
        turi = spec.turi
    d = Davr.parse(davr, turi) if not isinstance(davr, Davr) else davr
    m = compute(code, d, full=False, trend=SONI[turi])
    tr = m["trend"]
    if turi == "kun":
        # dam olish kunlari (ishlanmagan, fakt 0) grafikni buzmasin
        import frappe

        yak = bool(frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari").yakshanba_ishlaydi)
        tr = [t for t in tr if t["fakt"] or ish_kunlari(t["davr"], t["davr"], yak)]
    labels = [f"{OY_NOMI[int(t['davr'][5:7])][:3]}" + (f" {t['davr'][2:4]}" if t["davr"][5:7] == "01" or i == 0 else "")
              if turi == "oy" else t["davr"][-3:] if turi == "hafta" else f"{getdate(t['davr']):%d.%m}"
              for i, t in enumerate(tr)]
    vals = [t["fakt"] for t in tr]
    yv = [v if v is not None else 0 for v in vals]

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    x = range(len(yv))
    if turi == "kun":
        ax.plot(x, yv, color=SERIES, linewidth=2, marker="o", markersize=3.5)
    else:
        ax.bar(x, yv, color=SERIES, width=0.72, edgecolor=SURFACE, linewidth=1)
    reja = m.get("reja_toliq") or m.get("reja")
    if reja and spec.additive and d.turi == turi:
        ax.axhline(reja, color=INK2, linestyle=(0, (4, 3)), linewidth=1.2)
        ax.text(len(yv) - 0.5, reja, f" reja {_qisqa(reja, spec.birlik)}", va="bottom", ha="right",
                color=INK2, fontsize=8)
    if vals and vals[-1] is not None:
        ax.annotate(_qisqa(vals[-1], spec.birlik), (len(yv) - 1, yv[-1]), textcoords="offset points",
                    xytext=(0, 5), ha="center", color=INK, fontsize=9, fontweight="bold")
    ax.set_xticks(list(x))
    step = 1 if len(labels) <= 13 else 3
    ax.set_xticklabels([lb if i % step == 0 or i == len(labels) - 1 else "" for i, lb in enumerate(labels)],
                       fontsize=8, color=INK2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: _qisqa(v, spec.birlik)))
    ax.tick_params(axis="y", labelsize=8, colors=INK2, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    nom = {"oy": "12 oy", "hafta": "12 hafta", "kun": "30 kun"}[turi]
    ax.set_title(f"{spec.nom} — {nom}", loc="left", fontsize=11, color=INK, pad=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue(), m
