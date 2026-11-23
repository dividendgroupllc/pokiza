# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Kontrol Marja — marja nazorati uchun daraxt hisoboti:
Item Group -> Sub-kategoriya (brend) -> Tavar, ustunlar esa davrlar
(oyma-oy yoki kunma-kun), har katakda yalpi marja %.

Marja ERPNext'ning Gross Profit hisobotidagi gross_profit_percent bilan
bir xil hisoblanadi: (savdo − tannarx) / savdo × 100, bu yerda savdo =
schyot qatorining base_amount, tannarx esa Stock Ledger Entry'dagi
stock_value_difference (schyot qatoriga voucher_detail_no orqali
bog'langan) — nazorat B4 metrikasi bilan ham bir manba.

Vozvratlar (is_return) ham qo'shiladi: summalari manfiy bo'lgani uchun
davr natijasi sof (netto) chiqadi. Bu Gross Profit hisobotidan ataylab
farq qiladi: GP vozvratni asl schyot sanasiga qaytarib taqsimlaydi,
return_against'siz vozvratlarni esa umuman YO'QOTADI (2026-11-13 da
tekshirildi) — bu hisobotda vozvrat o'z sanasida minus bo'lib turadi.
Toza (vozvratsiz) kunda GP bilan tavar-tavar aynan mos (26/26, farq 0).

SLE yozuvi yo'q qatorlar (Услуга,
Бонус kabi omborga tegmaydiganlar) tannarxsiz, ya'ni marja 100% bo'lib
ko'rinadi — bu xato emas, ularning tannarxi haqiqatan yo'q.

Daraja manbalari: 1-daraja Item.item_group, 2-daraja
Item.custom_subkategoriya (pokiza.nazorat.setup.taklif/qollash bilan
to'ldiriladi; bo'sh qiymat «Boshqa» bo'lib chiqadi). Item.custom_kategoriya
daraxtda ishlatilmaydi, lekin filtr sifatida qoladi.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate
from frappe.utils.nestedset import get_descendants_of

OYLAR = ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"]
KUNLIK_LIMIT = 92  # kunlik rejimda ustunlar soni chegarasi


def execute(filters=None):
    filters = frappe._dict(filters or {})
    davrlar = _davrlar(filters)  # [(key, label), ...]
    columns = _columns(davrlar)
    data = _data(filters, davrlar)
    return columns, data


# ---------------------------------------------------------------- davrlar

def _davrlar(filters):
    boshi, oxiri = getdate(filters.from_date), getdate(filters.to_date)
    if boshi > oxiri:
        frappe.throw(_("Boshlanish sanasi tugash sanasidan keyin bo'lishi mumkin emas"))
    davrlar = []
    if filters.get("davr") == "Kunlik":
        if (oxiri - boshi).days + 1 > KUNLIK_LIMIT:
            frappe.throw(_("Kunlik rejimda eng ko'pi {0} kun tanlang (hozir {1} kun)").format(
                KUNLIK_LIMIT, (oxiri - boshi).days + 1))
        kun = boshi
        while kun <= oxiri:
            davrlar.append((kun.strftime("%Y-%m-%d"), kun.strftime("%d.%m.%y")))
            kun = add_days(kun, 1)
    else:  # Oylik
        kun = get_first_day(boshi)
        while kun <= oxiri:
            davrlar.append((kun.strftime("%Y-%m"), f"{OYLAR[kun.month - 1]} {kun.year}"))
            kun = add_months(kun, 1)
    return davrlar


def _davr_fieldname(key):
    return "p_" + key.replace("-", "_")


def _columns(davrlar):
    columns = [{
        "fieldname": "tavar", "label": _("Guruh / Brend / Tavar"),
        "fieldtype": "Data", "width": 300,
    }]
    for key, label in davrlar:
        columns.append({
            "fieldname": _davr_fieldname(key), "label": label,
            "fieldtype": "Percent", "precision": 1, "width": 90,
        })
    columns += [
        {"fieldname": "jami_savdo", "label": _("Jami savdo"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "jami_foyda", "label": _("Jami yalpi foyda"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "jami_marja", "label": _("Jami marja %"), "fieldtype": "Percent",
         "precision": 1, "width": 100},
    ]
    return columns


# ---------------------------------------------------------------- ma'lumot

def _ichki_guruhlar(doctype, guruh):
    try:
        return [guruh, *get_descendants_of(doctype, guruh, ignore_permissions=True)]
    except Exception:
        return [guruh]


def _royxat(qiymat):
    """MultiSelectList qiymati — list yoki JSON matn bo'lib kelishi mumkin."""
    if not qiymat:
        return []
    if isinstance(qiymat, str):
        qiymat = frappe.parse_json(qiymat)
    return [v for v in qiymat if v]


def _sotuv_qatorlari(filters):
    shart = ["si.docstatus = 1"]
    qiymat = {"from_date": filters.from_date, "to_date": filters.to_date}
    shart.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")

    if filters.get("customer_group"):
        qiymat["customer_groups"] = _ichki_guruhlar("Customer Group", filters.customer_group)
        shart.append(
            "si.customer IN (SELECT name FROM `tabCustomer` WHERE customer_group IN %(customer_groups)s)")
    mijozlar = _royxat(filters.get("mijozlar"))
    if mijozlar:
        qiymat["mijozlar"] = mijozlar
        shart.append("si.customer IN %(mijozlar)s")
    if filters.get("item_group"):
        qiymat["item_groups"] = _ichki_guruhlar("Item Group", filters.item_group)
        shart.append("i.item_group IN %(item_groups)s")
    if filters.get("kategoriya"):
        qiymat["kategoriya"] = filters.kategoriya
        shart.append("COALESCE(NULLIF(i.custom_kategoriya, ''), 'Belgilanmagan') = %(kategoriya)s")

    subkatlar = _royxat(filters.get("subkategoriya"))
    if subkatlar:
        qiymat["subkatlar"] = subkatlar
        shart.append("COALESCE(NULLIF(i.custom_subkategoriya, ''), 'Boshqa') IN %(subkatlar)s")
    tavarlar = _royxat(filters.get("tavarlar"))
    if tavarlar:
        qiymat["tavarlar"] = tavarlar
        shart.append("sii.item_code IN %(tavarlar)s")

    davr_sql = ("DATE_FORMAT(si.posting_date, '%%Y-%%m-%%d')"
                if filters.get("davr") == "Kunlik"
                else "DATE_FORMAT(si.posting_date, '%%Y-%%m')")

    return frappe.db.sql(f"""
        SELECT
            i.item_group AS kat,
            COALESCE(NULLIF(i.custom_subkategoriya, ''), 'Boshqa') AS subkat,
            sii.item_code,
            {davr_sql} AS davr,
            SUM(sii.base_amount) AS savdo,
            SUM(-COALESCE(sle.v, 0)) AS tannarx
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem` i ON i.name = sii.item_code
        LEFT JOIN (
            SELECT voucher_detail_no, SUM(stock_value_difference) AS v
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0 AND voucher_type = 'Sales Invoice'
              AND posting_date BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY voucher_detail_no
        ) sle ON sle.voucher_detail_no = sii.name
        WHERE {" AND ".join(shart)}
        GROUP BY kat, subkat, sii.item_code, davr
    """, qiymat, as_dict=True)


def _marja(savdo, tannarx):
    if not savdo:
        return None
    return flt((savdo - tannarx) / abs(savdo) * 100)


def _data(filters, davrlar):
    rows = _sotuv_qatorlari(filters)

    # uch daraja uchun yig'ish: kalit -> {davr: [savdo, tannarx]}
    tugunlar = {}
    for r in rows:
        for kalit in ((r.kat,), (r.kat, r.subkat), (r.kat, r.subkat, r.item_code)):
            davr_map = tugunlar.setdefault(kalit, {})
            s = davr_map.setdefault(r.davr, [0.0, 0.0])
            s[0] += flt(r.savdo)
            s[1] += flt(r.tannarx)

    def jami_savdo(kalit):
        return sum(v[0] for v in tugunlar.get(kalit, {}).values())

    def qator(kalit, label, ota, indent):
        out = {"tavar": label, "ota": ota, "indent": indent,
               # tavar qatorini bosganda Item kartochkasiga o'tish uchun (JS formatter)
               "item_code": kalit[2] if len(kalit) == 3 else None}
        davr_map = tugunlar.get(kalit, {})
        t_savdo = t_tannarx = 0.0
        for key, _label in davrlar:
            s, t = davr_map.get(key, (0.0, 0.0))
            out[_davr_fieldname(key)] = _marja(s, t)
            t_savdo += s
            t_tannarx += t
        out["jami_savdo"] = t_savdo
        out["jami_foyda"] = t_savdo - t_tannarx
        out["jami_marja"] = _marja(t_savdo, t_tannarx)
        return out

    data = []
    katlar = sorted({k[0] for k in tugunlar if len(k) == 1}, key=lambda k: -jami_savdo((k,)))
    for kat in katlar:
        data.append(qator((kat,), kat, None, 0))
        subkatlar = sorted({k[1] for k in tugunlar if len(k) == 2 and k[0] == kat},
                           key=lambda s: -jami_savdo((kat, s)))
        for sub in subkatlar:
            data.append(qator((kat, sub), sub, kat, 1))
            itemlar = sorted({k[2] for k in tugunlar if len(k) == 3 and k[:2] == (kat, sub)},
                             key=lambda it: -jami_savdo((kat, sub, it)))
            for it in itemlar:
                data.append(qator((kat, sub, it), it, sub, 2))

    # umumiy JAMI qatori (davrlar bo'yicha barcha kategoriyalar yig'indisi)
    if data:
        jami = {"tavar": _("JAMI"), "ota": None, "indent": 0, "jami_savdo": 0.0}
        t_savdo = t_tannarx = 0.0
        for key, _label in davrlar:
            s = sum(tugunlar[(k,)].get(key, (0.0, 0.0))[0] for k in katlar)
            t = sum(tugunlar[(k,)].get(key, (0.0, 0.0))[1] for k in katlar)
            jami[_davr_fieldname(key)] = _marja(s, t)
            t_savdo += s
            t_tannarx += t
        jami["jami_savdo"] = t_savdo
        jami["jami_foyda"] = t_savdo - t_tannarx
        jami["jami_marja"] = _marja(t_savdo, t_tannarx)
        data.append(jami)
    return data


@frappe.whitelist()
def subkategoriyalar(txt=""):
    """Sub-kategoriya filtri uchun mavjud brendlar ro'yxati."""
    rows = frappe.db.sql(
        """SELECT DISTINCT custom_subkategoriya FROM `tabItem`
        WHERE IFNULL(custom_subkategoriya, '') != '' AND custom_subkategoriya LIKE %(txt)s
        ORDER BY custom_subkategoriya""",
        {"txt": f"%{txt or ''}%"})
    natija = [{"value": r[0], "description": ""} for r in rows]
    if "boshqa".startswith((txt or "").lower()):
        natija.append({"value": "Boshqa", "description": _("Brendi aniqlanmaganlar")})
    return natija
