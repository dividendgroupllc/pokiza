"""Ishlab chiqarish analitikasi: fakt, xomashyo sarfi, talab tarixi/prognoz va "agar … qilsam" ssenariysi.

Ma'lumot modeli (2026-11 holati):
- Production Entry (PE, docstatus=1) — NORMA ishlab chiqarish: `item_to_manufacture` ('Готовый продукт'),
  `qty_to_manufacture` = fakt kg, `reja_kg` = reja (bo'lsa), `brak_kg`. Submit'da Manufacture Stock Entry
  (`custom_production_entry`) yaratadi: xomashyo chiqadi, norma 'Склад сырьё'ga kiradi. Valuatsiya =
  xomashyo summasi, ya'ni norma tannarxi faqat xomashyo (ish haqi/ustama kirmaydi).
- Sotuv SKU ('Сотув махсулотлари') alohida Manufacture SE'da (PE'siz) norma + upakovkadan yig'iladi.
- Sotuv qatorida `custom_norma` — SKU qaysi normadan qilingani. `custom_tannarx_kg` ishonchsiz — ishlatilmaydi.
Hamma hisob-kitob shu yerda (SQL), AI faqat natijani tahlil qiladi.
"""
import math

import frappe
from frappe.utils import add_days, add_months, date_diff, flt, get_first_day, get_last_day, getdate, nowdate

from pokiza.ai.tools import ToolError, parse_json_arg, tool

# production_entry.py: 2026-iyul/avgust boshigacha PE sarflari 1 birlik uchun saqlangan — ishonchsiz
PE_RELIABLE_FROM = "2026-08-01"
KG_UOMS = ("кг", "Kg", "kg")


def _settings():
    s = frappe.get_cached_doc("Ishlab Chiqarish Sozlamalari")
    return frappe._dict(
        quvvat=flt(s.kunlik_quvvat_kg) or 6900,
        zames=flt(s.zames_kg) or 95,
        yakshanba=bool(s.yakshanba_ishlaydi),
    )


def _work_days(d1, d2, yakshanba=False):
    d1, d2 = getdate(d1), getdate(d2)
    if d2 < d1:
        return 0
    return sum(1 for i in range(date_diff(d2, d1) + 1) if yakshanba or add_days(d1, i).weekday() != 6)


def _period(from_date, to_date, months=3):
    """Berilmasa: oxirgi `months` to'liq oy."""
    if from_date and to_date:
        f, t = getdate(from_date), getdate(to_date)
    else:
        t = get_last_day(add_months(getdate(nowdate()), -1))
        f = get_first_day(add_months(t, -(months - 1)))
    if f > t:
        raise ToolError("from_date to_date'dan keyin")
    return f, t


def _notes(f, t, brak_total=0):
    notes = []
    if f < getdate(PE_RELIABLE_FROM):
        notes.append(
            f"{PE_RELIABLE_FROM} gacha bo'lgan PE xomashyo sarflari tizim xatosi tufayli ishonchsiz "
            "(1 birlik uchun saqlangan) — sarf/tannarx tahlilini avgustdan boshlab qil."
        )
    if not brak_total and not frappe.db.count("Brak Vozvrat"):
        notes.append("Brak ma'lumoti tizimga kiritilmagan (PE brak_kg = 0, Brak Vozvrat bo'sh) — brak foizini aytib bo'lmaydi.")
    return notes


GROUP_KEYS = {
    "month": "DATE_FORMAT(p.posting_date, '%%Y-%%m')",
    "week": "DATE_FORMAT(p.posting_date, '%%x-H%%v')",
    "day": "p.posting_date",
    "norma": "p.item_to_manufacture",
}


def production_report(from_date=None, to_date=None, group_by=None, norma=None):
    """Norma ishlab chiqarish fakti, sig'im yuklamasi, tannarx (xomashyo) — davr bo'yicha."""
    f, t = _period(from_date, to_date)
    key = GROUP_KEYS.get(group_by or "month")
    if not key:
        raise ToolError("group_by: month, week, day yoki norma")
    cond = "AND p.item_to_manufacture = %(norma)s" if norma else ""
    sql = f"""
        SELECT {key} AS guruh,
            COUNT(*) AS pe_soni,
            COUNT(DISTINCT p.posting_date) AS ish_kunlari,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN p.qty_to_manufacture ELSE 0 END) AS kg,
            SUM(CASE WHEN i.stock_uom NOT IN %(kg)s THEN p.qty_to_manufacture ELSE 0 END) AS boshqa_birlik,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN fg.amount ELSE 0 END) AS xomashyo_summa_kg_mahsulot,
            SUM(fg.amount) AS xomashyo_summa_jami,
            SUM(CASE WHEN p.reja_kg > 0 THEN p.reja_kg END) AS reja_kg,
            SUM(CASE WHEN p.reja_kg > 0 THEN p.qty_to_manufacture + p.brak_kg END) AS reja_bor_fakt_kg,
            SUM(p.brak_kg) AS brak_kg
        FROM `tabProduction Entry` p
        JOIN `tabItem` i ON i.name = p.item_to_manufacture
        LEFT JOIN (
            SELECT s.custom_production_entry AS pe, SUM(d.amount) AS amount
            FROM `tabStock Entry` s JOIN `tabStock Entry Detail` d ON d.parent = s.name AND d.is_finished_item = 1
            WHERE s.docstatus = 1 AND s.custom_production_entry IS NOT NULL
            GROUP BY s.custom_production_entry
        ) fg ON fg.pe = p.name
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s {cond}
        GROUP BY guruh ORDER BY {"kg DESC" if group_by == "norma" else "guruh"}
        LIMIT 200
    """
    rows = frappe.db.sql(sql, {"f": f, "t": t, "kg": KG_UOMS, "norma": norma}, as_dict=True)
    st = _settings()
    out_rows = []
    for r in rows:
        kg = flt(r.kg)
        row = {
            "guruh": str(r.guruh),
            "kg": round(kg, 1),
            "pe_soni": r.pe_soni,
            "ish_kunlari": r.ish_kunlari,
            "xomashyo_tannarx_kg": round(flt(r.xomashyo_summa_kg_mahsulot) / kg) if kg else None,
            "xomashyo_summa": round(flt(r.xomashyo_summa_jami)),
        }
        if flt(r.boshqa_birlik):
            row["boshqa_birlikda (dona)"] = round(flt(r.boshqa_birlik), 1)
        if group_by in (None, "month", "week", "day") and r.ish_kunlari:
            row["kunlik_ortacha_kg"] = round(kg / r.ish_kunlari)
            row["sigim_yuklamasi_%"] = round(kg / r.ish_kunlari / st.quvvat * 100, 1)
        if flt(r.reja_kg):
            row["reja_kg (reja kiritilgan PE'lar)"] = round(flt(r.reja_kg), 1)
            row["chiqish_%"] = round(flt(r.reja_bor_fakt_kg) / flt(r.reja_kg) * 100, 1)
        if flt(r.brak_kg):
            row["brak_kg"] = round(flt(r.brak_kg), 1)
        out_rows.append(row)

    total_kg = sum(flt(r.kg) for r in rows)
    days = frappe.db.sql(
        f"""SELECT COUNT(DISTINCT p.posting_date) FROM `tabProduction Entry` p
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s {cond}""",
        {"f": f, "t": t, "norma": norma},
    )[0][0]
    kalendar_ish_kuni = _work_days(f, min(t, getdate(nowdate())), st.yakshanba)
    total = {
        "kg": round(total_kg, 1),
        "ishlab_chiqarilgan_kunlar": days,
        "kalendar_ish_kunlari": kalendar_ish_kuni,
        "kunlik_sigim_kg": st.quvvat,
        "zames_kg": st.zames,
    }
    if days and not norma:
        total["kunlik_ortacha_kg"] = round(total_kg / days)
        total["sigim_yuklamasi_% (ishlagan kunlar)"] = round(total_kg / days / st.quvvat * 100, 1)
        total["sigim_yuklamasi_% (kalendar ish kunlari)"] = round(total_kg / max(kalendar_ish_kuni, 1) / st.quvvat * 100, 1)
    brak = sum(flt(r.brak_kg) for r in rows)
    return {
        "davr": f"{f} — {t}",
        "manba": "Production Entry (docstatus=1) + bog'langan Manufacture Stock Entry valuatsiyasi",
        "izoh": "kg — faqat kg'dagi normalar; xomashyo_tannarx_kg ish haqi/ustamasiz (faqat xomashyo).",
        "jami": total,
        "rows": out_rows,
        "ogohlantirish": _notes(f, t, brak),
    }


def material_usage(from_date=None, to_date=None, norma=None, top=None, by_month=None):
    """Normalar uchun sarflangan xomashyo: miqdor, summa, 1 tonna normaga sarf, narx dinamikasi."""
    f, t = _period(from_date, to_date)
    top = min(int(top or 25), 100)
    cond = "AND p.item_to_manufacture = %(norma)s" if norma else ""
    base = f"""
        FROM `tabProduction Entry` p
        JOIN `tabStock Entry` s ON s.custom_production_entry = p.name AND s.docstatus = 1
        JOIN `tabStock Entry Detail` d ON d.parent = s.name
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s {cond}
    """
    args = {"f": f, "t": t, "norma": norma}
    fg_kg = flt(frappe.db.sql(f"SELECT SUM(d.qty) {base} AND d.is_finished_item = 1 AND d.stock_uom IN %(kg)s", {**args, "kg": KG_UOMS})[0][0])
    rows = frappe.db.sql(
        f"""SELECT d.item_code, it.item_group, d.stock_uom AS birlik, SUM(d.qty) AS miqdor, SUM(d.amount) AS summa
        FROM `tabProduction Entry` p
        JOIN `tabStock Entry` s ON s.custom_production_entry = p.name AND s.docstatus = 1
        JOIN `tabStock Entry Detail` d ON d.parent = s.name AND d.s_warehouse IS NOT NULL AND d.is_finished_item = 0
        JOIN `tabItem` it ON it.name = d.item_code
        WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s {cond}
        GROUP BY d.item_code, it.item_group, d.stock_uom ORDER BY summa DESC""",
        args,
        as_dict=True,
    )
    jami = sum(flt(r.summa) for r in rows)
    bins = _bin_rates([r.item_code for r in rows[:top]])
    out = []
    for r in rows[:top]:
        row = {
            "xomashyo": r.item_code,
            "guruh": r.item_group,
            "birlik": r.birlik,
            "miqdor": round(flt(r.miqdor), 2),
            "summa": round(flt(r.summa)),
            "ulush_%": round(flt(r.summa) / jami * 100, 1) if jami else None,
            "ortacha_narx": round(flt(r.summa) / flt(r.miqdor)) if flt(r.miqdor) else None,
            "1_tonna_normaga_sarf": round(flt(r.miqdor) / fg_kg * 1000, 2) if fg_kg else None,
        }
        b = bins.get(r.item_code)
        if b:
            row["joriy_narx (ombor)"] = round(b["rate"])
            row["joriy_qoldiq"] = round(b["qty"], 2)
        out.append(row)

    res = {
        "davr": f"{f} — {t}",
        "norma": norma or "barcha normalar",
        "ishlab_chiqarilgan_norma_kg": round(fg_kg, 1),
        "xomashyo_jami_summa": round(jami),
        "xomashyo_tannarx_kg": round(jami / fg_kg) if fg_kg else None,
        "xomashyo_turlari": len(rows),
        "rows": out,
        "ogohlantirish": _notes(f, t),
    }
    if by_month:
        items = [r.item_code for r in rows[:10]]
        trend = frappe.db.sql(
            f"""SELECT DATE_FORMAT(p.posting_date, '%%Y-%%m') AS oy, d.item_code, SUM(d.amount) / SUM(d.qty) AS narx
            FROM `tabProduction Entry` p
            JOIN `tabStock Entry` s ON s.custom_production_entry = p.name AND s.docstatus = 1
            JOIN `tabStock Entry Detail` d ON d.parent = s.name AND d.s_warehouse IS NOT NULL AND d.is_finished_item = 0
            WHERE p.docstatus = 1 AND p.posting_date BETWEEN %(f)s AND %(t)s AND d.item_code IN %(items)s {cond}
            GROUP BY oy, d.item_code ORDER BY oy""",
            {**args, "items": items or ["-"]},
            as_dict=True,
        )
        dyn = {}
        for r in trend:
            dyn.setdefault(r.item_code, {})[r.oy] = round(flt(r.narx))
        res["narx_dinamikasi (top 10, so'm/birlik)"] = dyn
    return res


def _bin_rates(items):
    if not items:
        return {}
    rows = frappe.db.sql(
        """SELECT item_code, SUM(actual_qty) AS qty, SUM(stock_value) AS val
        FROM `tabBin` WHERE item_code IN %(items)s GROUP BY item_code""",
        {"items": list(items)},
        as_dict=True,
    )
    return {r.item_code: {"qty": flt(r.qty), "rate": flt(r.val) / flt(r.qty) if flt(r.qty) > 0 else 0} for r in rows}


NORMA_COVERAGE_MIN = 0.7


def _norma_coverage(from_date, to_date=None):
    """Oy -> sotilgan kg'ning necha qismida custom_norma to'ldirilgan (2026-09 dan oldin deyarli yo'q)."""
    rows = frappe.db.sql(
        """SELECT DATE_FORMAT(s.posting_date, '%%Y-%%m') AS oy, SUM(i.stock_qty) AS kg,
            SUM(CASE WHEN IFNULL(i.custom_norma, '') != '' THEN i.stock_qty ELSE 0 END) AS norma_kg
        FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` s ON s.name = i.parent
        WHERE s.docstatus = 1 AND s.is_return = 0 AND i.stock_uom IN %(kg)s
            AND s.posting_date >= %(f)s AND s.posting_date <= %(t)s
        GROUP BY oy""",
        {"f": from_date, "t": to_date or getdate(nowdate()), "kg": KG_UOMS},
        as_dict=True,
    )
    return {r.oy: (flt(r.norma_kg) / flt(r.kg) if flt(r.kg) else 0) for r in rows}


def _forecast(series):
    """series: [(oy, qiymat)] to'liq oylar. Oddiy, tushuntirsa bo'ladigan usullar."""
    vals = [v for _, v in series]
    if len(vals) < 2:
        return {"izoh": "Prognoz uchun kamida 2 ta to'liq oy kerak"}
    last3 = vals[-3:]
    n = len(vals)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(vals) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / sxx if sxx else 0
    trend_next = my + slope * (n - mx)
    resid = [y - (my + slope * (x - mx)) for x, y in zip(xs, vals)]
    sd = math.sqrt(sum(e * e for e in resid) / max(n - 2, 1))
    growth = [(vals[i] / vals[i - 1] - 1) * 100 for i in range(1, n) if vals[i - 1]]
    return {
        "oxirgi_3_oy_ortacha": round(sum(last3) / len(last3)),
        "trend_boyicha_keyingi_oy": round(trend_next),
        "trend_oraligi_(±1 xato)": [round(trend_next - sd), round(trend_next + sd)],
        "oylik_osish_trendi": round(slope),
        "oxirgi_3_oy_min_max": [round(min(last3)), round(max(last3))],
        "oyma_oy_osish_%": [round(g, 1) for g in growth[-3:]],
        "usul": f"{n} ta to'liq oy; trend — chiziqli regressiya; oraliq — trenddan o'rtacha og'ish",
    }


def demand_history(months=None, by=None, item=None, top=None):
    """Oylik sotuv (kg, summa, narx) va norma ishlab chiqarish + keyingi oy prognozi."""
    months = max(2, min(int(months or 6), 12))
    by = by or "total"
    if by not in ("total", "norma", "sku"):
        raise ToolError("by: total, norma yoki sku")
    top = min(int(top or 10), 100)
    today = getdate(nowdate())
    first_full = get_first_day(add_months(today, -months))
    cur_first = get_first_day(today)

    key = {"total": "'Jami'", "norma": "IFNULL(i.custom_norma, '(norma ko''rsatilmagan)')", "sku": "i.item_code"}[by]
    cond = ""
    if item:
        cond = " AND i.custom_norma = %(item)s" if by == "norma" else " AND i.item_code = %(item)s"
    rows = frappe.db.sql(
        f"""SELECT {key} AS k, DATE_FORMAT(s.posting_date, '%%Y-%%m') AS oy,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN i.stock_qty ELSE 0 END) AS kg,
            SUM(CASE WHEN i.stock_uom NOT IN %(kg)s THEN i.stock_qty ELSE 0 END) AS dona,
            SUM(i.base_net_amount) AS summa,
            SUM(CASE WHEN i.stock_uom IN %(kg)s THEN i.base_net_amount ELSE 0 END) AS kg_summa,
            COUNT(DISTINCT s.customer) AS mijozlar
        FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` s ON s.name = i.parent
        WHERE s.docstatus = 1 AND s.posting_date >= %(f)s {cond}
        GROUP BY k, oy ORDER BY k, oy""",
        {"f": first_full, "kg": KG_UOMS, "item": item},
        as_dict=True,
    )
    prod = {}
    if by in ("total", "norma"):
        pcond = " AND p.item_to_manufacture = %(item)s" if (item and by == "norma") else ""
        for r in frappe.db.sql(
            f"""SELECT {"'Jami'" if by == "total" else "p.item_to_manufacture"} AS k,
                DATE_FORMAT(p.posting_date, '%%Y-%%m') AS oy, SUM(p.qty_to_manufacture) AS kg
            FROM `tabProduction Entry` p JOIN `tabItem` it ON it.name = p.item_to_manufacture
            WHERE p.docstatus = 1 AND p.posting_date >= %(f)s AND it.stock_uom IN %(kg)s {pcond}
            GROUP BY k, oy""",
            {"f": max(first_full, getdate(PE_RELIABLE_FROM)), "kg": KG_UOMS, "item": item},
            as_dict=True,
        ):
            prod[(r.k, r.oy)] = flt(r.kg)

    series = {}
    for r in rows:
        series.setdefault(r.k, []).append(r)
    all_ranked = sorted(series, key=lambda k: -sum(flt(r.kg) for r in series[k]))
    ranked = all_ranked[:top]
    cur = cur_first.strftime("%Y-%m")
    elapsed = _work_days(cur_first, today)
    total_wd = _work_days(cur_first, get_last_day(today))

    coverage = _norma_coverage(first_full) if by == "norma" else {}
    out = []
    for k in ranked:
        oylar = []
        for r in series[k]:
            m = {
                "oy": r.oy + (" (joriy, to'liq emas)" if r.oy == cur else ""),
                "sotuv_kg": round(flt(r.kg), 1),
                "summa": round(flt(r.summa)),
                "ortacha_narx_kg": round(flt(r.kg_summa) / flt(r.kg)) if flt(r.kg) else None,
                "mijozlar": r.mijozlar,
            }
            if flt(r.dona):
                m["sotuv_dona"] = round(flt(r.dona), 1)
            if (k, r.oy) in prod:
                m["ishlab_chiqarilgan_norma_kg"] = round(prod[(k, r.oy)], 1)
            if by == "norma" and coverage.get(r.oy, 0) < NORMA_COVERAGE_MIN:
                m["ishonchsiz"] = f"bu oyda sotuvning faqat {coverage.get(r.oy, 0) * 100:.0f}% iga norma bog'langan"
            oylar.append(m)
        full = [
            (r.oy, flt(r.kg))
            for r in series[k]
            if r.oy != cur and (by != "norma" or coverage.get(r.oy, 0) >= NORMA_COVERAGE_MIN)
        ]
        entry = {"nom": k, "oylar": oylar, "prognoz_kg": _forecast(full)}
        cur_row = next((r for r in series[k] if r.oy == cur), None)
        if cur_row and elapsed >= 5:
            entry["joriy_oy_sur'atida_yakun_kg"] = round(flt(cur_row.kg) / elapsed * total_wd)
        out.append(entry)

    return {
        "manba": "Sales Invoice Item (docstatus=1, qaytarishlar ayirilgan) + Production Entry",
        "izoh": "sotuv_kg — faqat kg'dagi mahsulotlar; donadagilar sotuv_dona. "
        "Ishlab chiqarilgan norma kg avgustdan ishonchli. Prognoz — statistik taxmin, kafolat emas.",
        "joriy_oy": {"oy": cur, "otgan_ish_kunlari": elapsed, "jami_ish_kunlari": total_wd},
        **({"norma_boglanishi_%": {m: round(c * 100) for m, c in sorted(coverage.items())},
            "norma_izoh": f"norma bo'yicha prognoz faqat norma bog'lanishi >= {NORMA_COVERAGE_MIN:.0%} bo'lgan oylardan"}
           if by == "norma" else {}),
        **({"kesildi": f"Faqat eng katta {top} ta ko'rsatildi, yana {len(all_ranked) - top} ta bor — "
            "to'liq ro'yxat kerak bo'lsa top'ni oshir yoki SQL ishlat"} if len(all_ranked) > top else {}),
        "rows": out,
    }


def _default_bom(item):
    from pokiza.pokiza_for_business.doctype.production_entry.production_entry import get_bom_for_item

    return get_bom_for_item(item)


def production_scenario(plan, period_days=None, history_months=None):
    """"Agar shuncha ishlab chiqarsam" — xomashyo ehtiyoji, yetishmovchilik, sig'im, tannarx, talab va marja."""
    if isinstance(plan, str):
        plan = parse_json_arg(plan, [], "plan")
    if not isinstance(plan, list) or not plan or not all(isinstance(p, dict) and p.get("norma") and flt(p.get("kg")) > 0 for p in plan):
        raise ToolError('plan: [{"norma": "<Готовый продукт item>", "kg": 1000}, ...] — davr uchun jami kg')
    if len(plan) > 30:
        raise ToolError("Ko'pi bilan 30 ta norma")
    st = _settings()
    hm = max(1, min(int(history_months or 3), 6))
    h_to = get_last_day(add_months(getdate(nowdate()), -1))
    h_from = max(get_first_day(add_months(h_to, -(hm - 1))), getdate(PE_RELIABLE_FROM))
    month_count = max(1, (h_to.year - h_from.year) * 12 + h_to.month - h_from.month + 1)
    # sotuv/talab faqat norma bog'lanishi ishonchli oylardan (2026-09 gacha custom_norma deyarli bo'sh)
    coverage = _norma_coverage(get_first_day(add_months(h_to, -(hm - 1))), h_to)
    sale_months = sorted(m for m, c in coverage.items() if c >= NORMA_COVERAGE_MIN)

    need, normalar, xato = {}, [], []
    for p in plan:
        norma, kg = p["norma"], flt(p["kg"])
        if not frappe.db.exists("Item", norma):
            xato.append(f"'{norma}' item topilmadi")
            continue
        bom_no = _default_bom(norma)
        if not bom_no:
            xato.append(f"'{norma}' uchun aktiv BOM yo'q")
            continue
        bom = frappe.get_doc("BOM", bom_no)
        for bi in bom.items:
            q = flt(bi.stock_qty or bi.qty) * kg / flt(bom.quantity)
            n = need.setdefault(bi.item_code, {"qty": 0, "uom": bi.stock_uom, "bom_rate": flt(bi.rate), "normalar": set()})
            n["qty"] += q
            n["normalar"].add(norma)
        normalar.append({"norma": norma, "kg": kg, "bom": bom_no, "zames_soni": math.ceil(kg / st.zames), "_bom": bom})

    if not normalar:
        raise ToolError("; ".join(xato) or "Reja bo'sh")

    bins = _bin_rates(list(need))
    materials, total_cost = [], 0
    for code, n in need.items():
        b = bins.get(code, {"qty": 0, "rate": 0})
        rate = b["rate"] or n["bom_rate"]
        cost = n["qty"] * rate
        total_cost += cost
        materials.append(
            {
                "xomashyo": code,
                "birlik": n["uom"],
                "kerak": round(n["qty"], 2),
                "omborda": round(b["qty"], 2),
                "yetishmaydi": round(max(n["qty"] - b["qty"], 0), 2),
                "narx": round(rate),
                "summa": round(cost),
            }
        )
    materials.sort(key=lambda m: -m["summa"])

    for x in normalar:
        norma, kg, bom = x["norma"], x["kg"], x.pop("_bom")
        bins_n = {bi.item_code: bins.get(bi.item_code, {"rate": 0})["rate"] or flt(bi.rate) for bi in bom.items}
        x["xomashyo_tannarx_kg (joriy narxlar, BOM)"] = round(
            sum(flt(bi.stock_qty or bi.qty) * bins_n[bi.item_code] for bi in bom.items) / flt(bom.quantity)
        )
        fact = frappe.db.sql(
            """SELECT SUM(d.amount), SUM(d.qty) FROM `tabProduction Entry` p
            JOIN `tabStock Entry` s ON s.custom_production_entry = p.name AND s.docstatus = 1
            JOIN `tabStock Entry Detail` d ON d.parent = s.name AND d.is_finished_item = 1
            WHERE p.docstatus = 1 AND p.item_to_manufacture = %s AND p.posting_date BETWEEN %s AND %s""",
            (norma, h_from, h_to),
        )[0]
        if flt(fact[1]):
            x["xomashyo_tannarx_kg (fakt, tarix)"] = round(flt(fact[0]) / flt(fact[1]))
            x["tarixda_oylik_ortacha_ishlab_chiqarilgan_kg"] = round(flt(fact[1]) / month_count)
        sale = frappe.db.sql(
            """SELECT SUM(i.stock_qty), SUM(i.base_net_amount), COUNT(DISTINCT i.item_code)
            FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` s ON s.name = i.parent
            WHERE s.docstatus = 1 AND i.custom_norma = %s AND i.stock_uom IN %s
                AND DATE_FORMAT(s.posting_date, '%%Y-%%m') IN %s""",
            (norma, KG_UOMS, sale_months or ["-"]),
        )[0]
        pack = frappe.db.sql(
            """SELECT SUM(CASE WHEN it.item_group = 'Упаковка' THEN d.amount END), SUM(CASE WHEN d.is_finished_item = 1 THEN d.qty END)
            FROM `tabStock Entry` s JOIN `tabStock Entry Detail` d ON d.parent = s.name
            JOIN `tabItem` it ON it.name = d.item_code
            WHERE s.docstatus = 1 AND s.purpose = 'Manufacture' AND IFNULL(s.custom_production_entry, '') = ''
                AND s.posting_date BETWEEN %s AND %s
                AND s.name IN (SELECT parent FROM `tabStock Entry Detail` WHERE item_code = %s AND s_warehouse IS NOT NULL)""",
            (h_from, h_to, norma),
        )[0]
        upak = flt(pack[0]) / flt(pack[1]) if flt(pack[1]) else None
        if upak is not None:
            x["upakovka_tannarx_kg (tarix)"] = round(upak)
        stock = flt(frappe.db.sql("SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code = %s", norma)[0][0])
        x["norma_ombor_qoldigi_kg"] = round(stock, 1)
        if flt(sale[0]) > 0:
            oylik = flt(sale[0]) / len(sale_months)
            narx = flt(sale[1]) / flt(sale[0])
            x["tarixiy_oylik_sotuv_kg"] = round(oylik)
            x["ortacha_sotuv_narxi_kg"] = round(narx)
            x["sotuv_sku_soni"] = sale[2]
            tannarx = x["xomashyo_tannarx_kg (joriy narxlar, BOM)"] + (upak or 0)
            x["yalpi_marja_kg (narx - xomashyo - upakovka)"] = round(narx - tannarx)
            x["yalpi_marja_%"] = round((narx - tannarx) / narx * 100, 1) if narx else None
            x["kutilgan_tushum (shu narxda hammasi sotilsa)"] = round(kg * narx)
            if period_days:
                talab = oylik * flt(period_days) / 30
                x["davrdagi_kutilgan_talab_kg"] = round(talab)
                x["ortiqcha_(reja + qoldiq - talab)_kg"] = round(kg + stock - talab)
        else:
            x["sotuv"] = "Bu norma bo'yicha tarixda kg'dagi sotuv topilmadi (custom_norma bog'lanmagan bo'lishi mumkin)"

    total_kg = sum(x["kg"] for x in normalar)
    sigim = {"kunlik_sigim_kg": st.quvvat, "kerak_ish_kunlari (to'liq sig'imda)": round(total_kg / st.quvvat, 1)}
    if period_days:
        wd = _work_days(getdate(nowdate()), add_days(getdate(nowdate()), int(period_days) - 1), st.yakshanba)
        sigim.update(
            {
                "davr_kunlari": int(period_days),
                "davrdagi_ish_kunlari": wd,
                "kunlik_yuklama_kg": round(total_kg / wd) if wd else None,
                "sigim_yuklamasi_%": round(total_kg / wd / st.quvvat * 100, 1) if wd else None,
            }
        )
    yetishmaydi = [m for m in materials if m["yetishmaydi"] > 0]
    return {
        "reja_jami_kg": round(total_kg, 1),
        "sigim": sigim,
        "normalar": normalar,
        "xomashyo_jami_summa (joriy narxlar)": round(total_cost),
        "yetishmaydigan_xomashyo": yetishmaydi[:40],
        "xomashyo_ehtiyoji (top 25)": materials[:25],
        "xatolar": xato,
        "tarix_davri": f"{h_from} — {h_to}",
        "talab_va_narx_oylari": sale_months,
        "norma_boglanishi_%": {m: round(coverage[m] * 100) for m in sale_months},
        "talab_izoh": "Sotuvning bir qismida norma ko'rsatilmagan — normalar talabi biroz past baholangan bo'lishi mumkin "
        "(norma_boglanishi_% qancha past bo'lsa, shuncha ko'p).",
        "farazlar": [
            "Xomashyo miqdori — normaning aktiv default BOM'i bo'yicha (fakt sarf BOM'dan farq qilishi mumkin).",
            "Narx — ombordagi joriy o'rtacha valuatsiya (qoldiq bo'lmasa BOM narxi).",
            "Tannarxga ish haqi, elektr, ijara va boshqa ustama kirmaydi — bu yalpi marja, sof foyda emas.",
            "Sotuv narxi va talab — tarix davridagi o'rtacha; bozor o'zgarishi hisobga olinmagan.",
            "Ombordagi xomashyo boshqa ishlab chiqarishga ham ketishi mumkin (band qilinmagan).",
        ],
    }


DATE = {"type": "string", "description": "YYYY-MM-DD"}

TOOLS = [
    (
        tool(
            "production_report",
            "Ishlab chiqarish fakti (norma bo'yicha, Production Entry): kg, ishlagan kunlar, kunlik o'rtacha, "
            "sig'im yuklamasi %, xomashyo tannarxi/kg, reja vs fakt (chiqish %), brak. "
            "group_by: month/week/day/norma. Sana berilmasa — oxirgi 3 to'liq oy. Ishlab chiqarish hajmi, "
            "sig'im, tannarx savollarida AVVAL shuni ishlat.",
            {
                "from_date": DATE,
                "to_date": DATE,
                "group_by": {"type": "string", "enum": ["month", "week", "day", "norma"]},
                "norma": {"type": "string", "description": "Bitta norma (Готовый продукт item nomi)"},
            },
            strict=False,
        ),
        production_report,
    ),
    (
        tool(
            "material_usage",
            "Normalar uchun sarflangan xomashyo va upakovka: miqdor, summa, ulush, o'rtacha va joriy narx, "
            "1 tonna normaga sarf, joriy ombor qoldig'i; by_month=true — top-10 xomashyo narxi oyma-oy.",
            {
                "from_date": DATE,
                "to_date": DATE,
                "norma": {"type": "string"},
                "top": {"type": "integer", "description": "Nechta xomashyo (standart 25)"},
                "by_month": {"type": "boolean"},
            },
            strict=False,
        ),
        material_usage,
    ),
    (
        tool(
            "demand_history",
            "Oylik sotuv tarixi (kg, dona, summa, o'rtacha narx/kg, mijozlar soni) va shu oydagi norma ishlab "
            "chiqarish, hamda keyingi oy uchun statistik prognoz (o'rtacha, trend, oraliq) va joriy oy sur'ati. "
            "by: total / norma / sku. Talab, mavsumiylik, prognoz, 'keyingi oy qancha' savollari uchun.",
            {
                "months": {"type": "integer", "description": "Nechta to'liq oy (2-12, standart 6)"},
                "by": {"type": "string", "enum": ["total", "norma", "sku"]},
                "item": {"type": "string", "description": "Bitta norma yoki SKU nomi"},
                "top": {"type": "integer", "description": "Nechta norma/SKU (standart 10, max 100)"},
            },
            strict=False,
        ),
        demand_history,
    ),
    (
        tool(
            "production_scenario",
            "'Agar shuncha ishlab chiqarsam nima bo'ladi?' ssenariysi. Reja bo'yicha: xomashyo ehtiyoji va "
            "ombordagi yetishmovchilik, xomashyo summasi, sig'im (ish kunlari, yuklama %), zames soni, "
            "tannarx/kg (joriy narx va tarixiy fakt), upakovka, tarixiy sotuv narxi va talab, yalpi marja, "
            "ortiqcha qoladigan kg. Normalar nomini avval production_report(group_by=norma) yoki "
            "demand_history(by=norma) bilan aniqla.",
            {
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"norma": {"type": "string"}, "kg": {"type": "number"}},
                        "required": ["norma", "kg"],
                    },
                    "description": "Davr uchun jami kg: [{norma, kg}]",
                },
                "period_days": {"type": "integer", "description": "Reja necha kunga (masalan 30). Talab va kunlik yuklama uchun"},
                "history_months": {"type": "integer", "description": "Narx/talab uchun tarix (1-6 oy, standart 3)"},
            },
            ["plan"],
            strict=False,
        ),
        production_scenario,
    ),
]
