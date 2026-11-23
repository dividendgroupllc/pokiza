"""0-bosqich: kategoriya va xarajat turini TAKLIF qilish va tasdiqdan keyin qo'llash.

    # 1) Taklifni ko'rish (Excel, hech narsa yozilmaydi):
    bench --site pokiza.local execute pokiza.nazorat.setup.taklif --kwargs "{'fayl': '/tmp/nazorat_taklif.xlsx'}"
    # 2) Excel'ni tekshirib, kerak bo'lsa "taklif" ustunini tuzatib, qo'llash (faqat bo'sh maydonlar):
    bench --site pokiza.local execute pokiza.nazorat.setup.qollash --kwargs "{'fayl': '/tmp/nazorat_taklif.xlsx'}"
"""
import re

import frappe

from pokiza.guruhlar import sotuv_guruhlari

# (regex, kategoriya, ishonch) — tartib muhim: birinchi mos kelgani olinadi
KATEGORIYA_QOIDALARI = [
    (r"^\s*(ак\.|бонус|услуга)|скидка", "Boshqa", "yuqori"),
    (r"тушен|консерв", "Tushonka", "yuqori"),
    (r"welmar", "Tushonka", "o'rta"),
    (r"сосиск|^\s*с-с|сардел", "Sosiska", "yuqori"),
    (r"^\s*п/к", "Kopchyonniy", "yuqori"),
    (r"коп-вар|рулет|yangilik", "Delikates", "past"),
    (r"кази|шедев", "Delikates", "o'rta"),
    (r"доктор|завтрак|любим|любител|деликатесн|сталичн|столичн|дорожн|домашн", "Varyonniy", "o'rta"),
    (r"сервелат|чесночн|сетка|слитка|полтав|москов|украин|таллин", "Kopchyonniy", "o'rta"),
    (r"детск|молочн|экстра|себзор", "Varyonniy", "past"),
]

KATEGORIYA_RUXSAT = {"Sosiska", "Kopchyonniy", "Varyonniy", "Delikates", "Tushonka", "Boshqa"}

# (regex, brend) — Kontrol Marj hisobotining 2-darajasi. Mos kelmasa bo'sh
# qoladi (hisobotda «Boshqa» bo'lib ko'rinadi). «Рокiza» — kirill+lotin aralash.
SUBKATEGORIYA_QOIDALARI = [
    (r"burxanov|бурханов|бур[.,]|\bбур\b", "Burxanov"),
    (r"pokiza|покиза|рок[иi]za", "Pokiza"),
    (r"нежная", "Nejnaya"),
    (r"milaro", "Milaro"),
    (r"hosil|хосил", "Hosil"),
    (r"кукча", "Kukcha"),
    (r"welmar", "Welmar"),
    (r"abdazoff", "Abdazoff"),
    (r"м\.з", "M.Z"),
    (r"ишонч", "Ishonch"),
    (r"\bjiz\b", "JIZ"),
]

OZGARUVCHI = r"бонус|брак|transport|газ|бензин|электро|commission|freight|реализ|упаков"
DOIMIY = r"зарп|аренда|rent|офис|office|it|dastur|банк|ремонт|хозяйств|питание|маркетинг|marketing|налог|ндс|цех|salary|depreciation|telephone|utility"


def _kategoriya(nom):
    for rx, kat, ish in KATEGORIYA_QOIDALARI:
        if re.search(rx, nom or "", re.I):
            return kat, ish
    return "", "topilmadi"


def _subkategoriya(nom):
    for rx, sub in SUBKATEGORIYA_QOIDALARI:
        if re.search(rx, nom or "", re.I):
            return sub
    return ""


def _xarajat_turi(nom):
    if re.search(OZGARUVCHI, nom or "", re.I):
        return "O'zgaruvchi"
    if re.search(DOIMIY, nom or "", re.I):
        return "Doimiy"
    return ""


def taklif(fayl="/tmp/nazorat_taklif.xlsx"):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Kategoriya"
    ws.append(["item_code", "nomi", "hozirgi kat", "taklif kat", "hozirgi subkat", "taklif subkat",
               "ishonch", "oxirgi 3 oy savdo (so'm)"])
    savdo = dict(frappe.db.sql(
        """SELECT sii.item_code, SUM(sii.base_net_amount) FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) GROUP BY sii.item_code"""))
    subkat_bor = frappe.db.has_column("Item", "custom_subkategoriya")
    items = frappe.get_all("Item", filters={"item_group": ["in", sotuv_guruhlari()], "disabled": 0},
                           fields=["name", "item_name", "custom_kategoriya"]
                                  + (["custom_subkategoriya"] if subkat_bor else []))
    items.sort(key=lambda r: -(savdo.get(r.name) or 0))
    for it in items:
        kat, ish = _kategoriya(it.item_name)
        ws.append([it.name, it.item_name, it.custom_kategoriya or "", kat,
                   it.get("custom_subkategoriya") or "", _subkategoriya(it.item_name),
                   ish, round(savdo.get(it.name) or 0)])

    ws2 = wb.create_sheet("Xarajat turi")
    ws2.append(["account", "nomi", "ota hisob", "hozirgi", "taklif", "oxirgi 3 oy (so'm)"])
    summa = dict(frappe.db.sql(
        """SELECT account, SUM(debit - credit) FROM `tabGL Entry` WHERE is_cancelled = 0
        AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) GROUP BY account"""))
    accs = frappe.get_all("Account", filters={"root_type": "Expense", "is_group": 0},
                          fields=["name", "account_name", "parent_account", "account_type", "custom_xarajat_turi"])
    for a in sorted(accs, key=lambda r: -(summa.get(r.name) or 0)):
        if a.account_type in ("Cost of Goods Sold", "Stock Adjustment", "Round Off") or "Exchange" in a.name:
            continue
        ws2.append([a.name, a.account_name, a.parent_account, a.custom_xarajat_turi or "",
                    _xarajat_turi(f"{a.account_name} {a.parent_account}"), round(summa.get(a.name) or 0)])
    for w in (ws, ws2):
        for c in w[1]:
            c.font = Font(bold=True)
        for col, width in zip("ABCDEFGH", (16, 45, 14, 14, 14, 14, 12, 20)):
            w.column_dimensions[col].width = width
    wb.save(fayl)
    print(f"Saqlandi: {fayl} — {len(items)} mahsulot, {ws2.max_row - 1} xarajat hisobi")
    return fayl


def qollash(fayl="/tmp/nazorat_taklif.xlsx", ustiga_yoz=False):
    """Excel'dagi 'taklif' ustunini yozadi. Standart: faqat bo'sh maydonlar (ustiga_yoz=False)."""
    from openpyxl import load_workbook

    wb = load_workbook(fayl, read_only=True)
    n = {"Item": 0, "Item_sub": 0, "Account": 0}

    def _yoz(dt, name, field, qiymat):
        if not qiymat or not frappe.db.exists(dt, name):
            return False
        if not ustiga_yoz and frappe.db.get_value(dt, name, field):
            return False
        frappe.db.set_value(dt, name, field, qiymat, update_modified=False)
        return True

    subkat_bor = frappe.db.has_column("Item", "custom_subkategoriya")
    for row in list(wb["Kategoriya"].iter_rows(values_only=True))[1:]:
        name = row[0]
        if not name:
            continue
        kat = row[3] if row[3] in KATEGORIYA_RUXSAT else None
        n["Item"] += _yoz("Item", name, "custom_kategoriya", kat)
        if subkat_bor and len(row) > 5:
            sub = (str(row[5]).strip() if row[5] else "")[:60]
            n["Item_sub"] += _yoz("Item", name, "custom_subkategoriya", sub)

    for row in list(wb["Xarajat turi"].iter_rows(values_only=True))[1:]:
        name, taklif_v = row[0], row[4]
        if name and taklif_v in {"Doimiy", "O'zgaruvchi"}:
            n["Account"] += _yoz("Account", name, "custom_xarajat_turi", taklif_v)
    frappe.db.commit()
    print(f"Yozildi: {n['Item']} mahsulot kategoriyasi, {n['Item_sub']} sub-kategoriyasi, "
          f"{n['Account']} xarajat turi")
    return n
