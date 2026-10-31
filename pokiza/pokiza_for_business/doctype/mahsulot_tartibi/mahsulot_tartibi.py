# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Накладная dagi mahsulot ketma-ketligi — YAGONA manba.

NEGA KERAK (egasi talabi 2026-10-31): chop etiladigan накладная da
mahsulotlar doim bir xil ketma-ketlikda turadi, ombor va haydovchi
tovarni shu tartibda sanaydi. Shuning uchun mijoz kartochkasi,
Sales Order va Sales Invoice jadvali ham aynan shu tartibda bo'lishi
kerak.

ISHLASHI: qatorlar shu yerda tortib tartiblanadi (Frappe bola jadvali
bunga o'zi ruxsat beradi), tartib = qator `idx`. Mijoz kartochkasi
saqlanganda qatorlari shu ro'yxatga qarab joylashadi; Sales Order va
Sales Invoice avto to'ldirishi kartochkadan o'qiydi. Ro'yxatda yo'q
mahsulot doim OXIRIDA, nom bo'yicha turadi — yo'qolmaydi.
"""

import frappe
from frappe import _
from frappe.model.document import Document

OXIRIGA = 10 ** 6


class MahsulotTartibi(Document):
    def validate(self):
        self.takrorni_tekshir()
        for i, q in enumerate(self.qatorlar, start=1):
            q.idx = i

    def takrorni_tekshir(self):
        korilgan = {}
        for q in self.qatorlar:
            if not q.mahsulot:
                continue
            if q.mahsulot in korilgan:
                frappe.throw(_("«{0}» ro'yxatda ikki marta: {1}- va {2}-qator").format(
                    q.mahsulot_nomi or q.mahsulot, korilgan[q.mahsulot], q.idx))
            korilgan[q.mahsulot] = q.idx

    def on_update(self):
        keshni_tozala()


def keshni_tozala():
    frappe.cache().delete_value("pokiza_mahsulot_tartibi")
    frappe.local.pokiza_mahsulot_tartibi = None
    frappe.local.pokiza_aktiv_karta_keshi = {}


def tartib_map():
    """{item_code: o'rin} — tartiblashning yagona o'qish nuqtasi.

    Ikki qatlamda keshlanadi: so'rov doirasi va Redis. Ro'yxat 144
    qatorli bola jadval, mijoz tanlanganda va har kartochka saqlanganda
    kerak bo'ladi — har safar o'qish ortiqcha.
    """
    kesh = getattr(frappe.local, "pokiza_mahsulot_tartibi", None)
    if kesh is not None:
        return kesh

    kesh = frappe.cache().get_value("pokiza_mahsulot_tartibi")
    if kesh is None:
        kesh = {
            r.mahsulot: r.idx
            for r in frappe.get_all(
                "Mahsulot Tartibi Qatori",
                filters={"parenttype": "Mahsulot Tartibi"},
                fields=["mahsulot", "idx"],
            )
            if r.mahsulot
        }
        frappe.cache().set_value("pokiza_mahsulot_tartibi", kesh)

    frappe.local.pokiza_mahsulot_tartibi = kesh
    return kesh


def kalit(item_code, nom=None):
    """Bitta mahsulotning saralash kaliti (ro'yxatda yo'q bo'lsa — oxiriga)."""
    return (tartib_map().get(item_code) or OXIRIGA, (nom or item_code or "").lower())


@frappe.whitelist()
def royxatni_joylash(matn, guruh_ustuni=1):
    """Excel'dan ko'chirilgan ro'yxatni qatorlarga aylantiradi.

    Har satrda bitta mahsulot nomi. Mahsulot `name` yoki `item_name`
    bo'yicha topiladi, registrga bog'liq emas (Excel'da «П/к. Сетка 45»,
    Item'da «П/К. Сетка 45» — kirill к/К).

    GURUH SARLAVHASI faqat BUTUNLAY BOSH HARFLI satr (Excel'dagi
    «ВАРЕНЫЕ КОЛБАСЫ», «СОСИСКИ» kabi). Qolgan topilmagan satr
    `topilmadi` ga yoziladi va ekranda ko'rsatiladi — avval bunday satr
    jim «guruh» deb qabul qilinardi, ya'ni xato yozilgan mahsulot nomi
    sezdirmasdan yo'qolib ketardi.

    Mavjud ro'yxat butunlay ALMASHTIRILADI.
    """
    if not frappe.has_permission("Mahsulot Tartibi", "write"):
        frappe.throw(_("Huquq yo'q"))

    satrlar = [s.strip() for s in (matn or "").splitlines()]
    satrlar = [s for s in satrlar if s]
    if not satrlar:
        frappe.throw(_("Ro'yxat bo'sh"))

    # Nom bo'yicha Item topish — registrga bog'liq emas (Excel'da
    # «П/к. Сетка 45», Item'da «П/К. Сетка 45» bo'lishi mumkin)
    itemlar = {}
    for r in frappe.db.sql("SELECT name, item_name FROM `tabItem`", as_dict=True):
        itemlar.setdefault((r.name or "").strip().lower(), r.name)
        itemlar.setdefault((r.item_name or "").strip().lower(), r.name)

    doc = frappe.get_single("Mahsulot Tartibi")
    doc.set("qatorlar", [])

    guruh = None
    qoshildi, takror, guruhlar, topilmadi = 0, [], [], []
    korilgan = set()
    for s in satrlar:
        item = itemlar.get(s.lower())
        if not item:
            if s == s.upper() and any(c.isalpha() for c in s):
                guruh = s           # «СОСИСКИ» kabi guruh sarlavhasi
                guruhlar.append(s)
            else:
                topilmadi.append(s)  # ehtimol nom xato yozilgan
            continue
        if item in korilgan:
            takror.append(s)
            continue
        korilgan.add(item)
        doc.append("qatorlar", {"mahsulot": item, "guruh": guruh})
        qoshildi += 1

    doc.flags.ignore_permissions = True
    doc.save()

    return {
        "qoshildi": qoshildi,
        "guruhlar": guruhlar,
        "takror": takror,
        "topilmadi": topilmadi,
        "tartibsiz": tartibsizlar(),
    }


@frappe.whitelist()
def tartibsizlar():
    """Ro'yxatda yo'q AKTIV sotuv mahsulotlari (ular oxirida turadi)."""
    tartibli = tuple(tartib_map()) or ("",)
    return frappe.db.sql(
        """
        SELECT name, item_name FROM `tabItem`
        WHERE item_group = 'Сотув махсулотлари' AND disabled = 0
          AND name NOT IN %(t)s
        ORDER BY item_name
        """,
        {"t": tartibli},
        as_dict=True,
    )


@frappe.whitelist()
def kartochkalarga_qolla(sinov=1):
    """Barcha mijoz kartochkalari qatorlarini shu ro'yxatga qarab joylashtiradi.

    Kartochka o'zi saqlanganda ham tartibga keladi, lekin ro'yxat
    o'zgargach 58 kartochkani qo'lda qayta saqlash real emas — shu
    tugma hammasini birdan qiladi.

    `sinov=1` — hech narsa saqlanmaydi, faqat nima o'zgarishini aytadi.
    Har kartochka alohida savepoint ichida: bitta buzuq kartochka
    (masalan `mijoz` o'chirilgan Customer'ga ishora qiladi) qolganini
    to'xtatmaydi.
    """
    from frappe.utils import cint

    if not frappe.has_permission("Mijoz Kartochkasi", "write"):
        frappe.throw(_("Huquq yo'q"))

    sinov = cint(sinov)
    natija = {"kartochka": 0, "ozgardi": 0, "tegilmadi": 0,
              "xatolar": [], "sinov": bool(sinov)}

    for nom in frappe.get_all("Mijoz Kartochkasi", pluck="name"):
        doc = frappe.get_doc("Mijoz Kartochkasi", nom)
        natija["kartochka"] += 1
        eski = [q.name for q in doc.qatorlar]
        yangi = saralangan(doc.qatorlar)

        if [q.name for q in yangi] == eski:
            natija["tegilmadi"] += 1
            continue

        natija["ozgardi"] += 1
        if sinov:
            continue

        doc.qatorlar = yangi
        sp = "tartib_%s" % abs(hash(nom))
        frappe.db.savepoint(sp)
        try:
            doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            natija["ozgardi"] -= 1
            natija["xatolar"].append("%s: %s" % (doc.mijoz, str(e)[:160]))

    return natija


def saralangan(qatorlar):
    """Kartochka qatorlarini ro'yxat tartibida qaytaradi (idx ham yoziladi)."""
    yangi = sorted(
        qatorlar,
        key=lambda q: kalit(q.get("sku"), q.get("sku_nomi") or q.get("sku")),
    )
    for i, q in enumerate(yangi, start=1):
        q.idx = i
    return yangi
