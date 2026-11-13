"""0-bosqich: kategoriya va xarajat turini TAKLIF qilish va tasdiqdan keyin qo'llash.

    # 1) Taklifni ko'rish (Excel, hech narsa yozilmaydi):
    bench --site pokiza.local execute pokiza.nazorat.setup.taklif --kwargs "{'fayl': '/tmp/nazorat_taklif.xlsx'}"
    # 2) Excel'ni tekshirib, kerak bo'lsa "taklif" ustunini tuzatib, qo'llash (faqat bo'sh maydonlar):
    bench --site pokiza.local execute pokiza.nazorat.setup.qollash --kwargs "{'fayl': '/tmp/nazorat_taklif.xlsx'}"
"""
import re

import frappe

# (regex, kategoriya, ishonch) — tartib muhim: birinchi mos kelgani olinadi
KATEGORIYA_QOIDALARI = [
    (r"^\s*(ак\.|бонус|услуга)", "Boshqa", "yuqori"),
    (r"тушен|консерв|welmar", "Boshqa", "o'rta"),
    (r"сосиск|^\s*с-с|сардел", "Sosiska", "yuqori"),
    (r"^\s*п/к", "Kopchyonniy", "yuqori"),
    (r"коп-вар|рулет|yangilik", "Delikates", "past"),
    (r"кази|шедев", "Delikates", "o'rta"),
    (r"доктор|завтрак|любим|любител|деликатесн|сталичн|столичн|дорожн", "Varyonniy", "o'rta"),
]

OZGARUVCHI = r"бонус|брак|transport|газ|бензин|электро|commission|freight|реализ|упаков"
DOIMIY = r"зарп|аренда|rent|офис|office|it|dastur|банк|ремонт|хозяйств|питание|маркетинг|marketing|налог|ндс|цех|salary|depreciation|telephone|utility"


def _kategoriya(nom):
    for rx, kat, ish in KATEGORIYA_QOIDALARI:
        if re.search(rx, nom or "", re.I):
            return kat, ish
    return "", "topilmadi"


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
    ws.append(["item_code", "nomi", "hozirgi", "taklif", "ishonch", "oxirgi 3 oy savdo (so'm)"])
    savdo = dict(frappe.db.sql(
        """SELECT sii.item_code, SUM(sii.base_net_amount) FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) GROUP BY sii.item_code"""))
    items = frappe.get_all("Item", filters={"item_group": "Сотув махсулотлари", "disabled": 0},
                           fields=["name", "item_name", "custom_kategoriya"])
    items.sort(key=lambda r: -(savdo.get(r.name) or 0))
    for it in items:
        kat, ish = _kategoriya(it.item_name)
        ws.append([it.name, it.item_name, it.custom_kategoriya or "", kat, ish, round(savdo.get(it.name) or 0)])

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
        for col, width in zip("ABCDEF", (16, 45, 14, 14, 12, 20)):
            w.column_dimensions[col].width = width
    wb.save(fayl)
    print(f"Saqlandi: {fayl} — {len(items)} mahsulot, {ws2.max_row - 1} xarajat hisobi")
    return fayl


def qollash(fayl="/tmp/nazorat_taklif.xlsx", ustiga_yoz=False):
    """Excel'dagi 'taklif' ustunini yozadi. Standart: faqat bo'sh maydonlar (ustiga_yoz=False)."""
    from openpyxl import load_workbook

    wb = load_workbook(fayl, read_only=True)
    n = {"Item": 0, "Account": 0}
    for sheet, dt, field, ruxsat in (
        ("Kategoriya", "Item", "custom_kategoriya", {"Sosiska", "Kopchyonniy", "Varyonniy", "Delikates", "Boshqa"}),
        ("Xarajat turi", "Account", "custom_xarajat_turi", {"Doimiy", "O'zgaruvchi"}),
    ):
        for row in list(wb[sheet].iter_rows(values_only=True))[1:]:
            name, taklif_v = row[0], (row[3] if dt == "Item" else row[4])
            if not name or taklif_v not in ruxsat or not frappe.db.exists(dt, name):
                continue
            if not ustiga_yoz and frappe.db.get_value(dt, name, field):
                continue
            frappe.db.set_value(dt, name, field, taklif_v, update_modified=False)
            n[dt] += 1
    frappe.db.commit()
    print(f"Yozildi: {n['Item']} mahsulot kategoriyasi, {n['Account']} xarajat turi")
    return n
