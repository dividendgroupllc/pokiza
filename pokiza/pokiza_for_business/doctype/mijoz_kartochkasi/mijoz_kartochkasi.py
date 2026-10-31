# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Mijoz Kartochkasi — mijoz + SKU + norma + narx/bonus shartlari.

ERP uchun qoida (PDF spec, 2026-09-21): mijoz+SKU tanlanganda norma va sotuv
shartlari shu kartochkadan olinadi; tannarx normadan (BOM) va SKU upakovka
normasidan avtomatik tortiladi; bonusdan keyingi narx, marja so'm/kg va
marja % server tomonda hisoblanadi (brauzerdan kelgan qiymatga ishonilmaydi).

Muzlatish qoidasi: kartochka o'zgarishi O'TGAN davrga ta'sir qilmaydi —
sotuv paytida qiymatlar schyot qatoriga ko'chiriladi (Faza 3), kartochkadagi
har o'zgarish esa Kartochka Ozgarish Jurnaliga yoziladi va o'chirilmaydi.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

SOTUV_GURUH = "Сотув махсулотлари"
NORMA_GURUH = "Готовый продукт"

# Jurnalga yoziladigan qator maydonlari — faqat odam kiritadiganlar
# (tannarx/marja hisoblanadi, ularning o'zgarishi BOM/ombordan kelib chiqadi)
KUZATILADIGAN = ("norma", "sotuv_narxi", "bonus_foiz", "amal_sana", "status")


class MijozKartochkasi(Document):
    def validate(self):
        self.bonus_defaultla()
        self.validate_guruhlar()
        self.validate_takror()
        self.tartibga_keltir()
        self.hisobla()
        self.jurnalga_yoz()

    def tartibga_keltir(self):
        """Qatorlarni «Mahsulot Tartibi» ro'yxatiga qarab joylashtiradi.

        Накладная ketma-ketligi butun tizimda bitta joyda yuritiladi
        (egasi qarori 2026-10-31); kartochka esa undan o'qiydi, shuning
        uchun qatorlar qanday kiritilganidan qat'i nazar doim bir xil
        tartibda turadi. Ro'yxatda yo'q mahsulot oxirida, nom bo'yicha.
        """
        from pokiza.pokiza_for_business.doctype.mahsulot_tartibi.mahsulot_tartibi import saralangan

        self.qatorlar = saralangan(self.qatorlar)

    def on_update(self):
        # aktiv_map() so'rov doirasida keshlanadi — kartochka shu so'rov
        # ichida o'zgarsa (masalan qoralama_toldir), kesh eskiradi
        frappe.local.pokiza_aktiv_karta_keshi = {}

    def bonus_defaultla(self):
        """YANGI kartochkada bonus Customer'dagi foizdan default tushadi
        (egasi talabi 2026-09-24). Faqat birinchi saqlashda va faqat bo'sh
        joylarga — keyin istalgancha o'zgartirsa bo'ladi."""
        if not self.is_new() or not self.mijoz:
            return
        if not flt(self.bonus_foiz):
            self.bonus_foiz = flt(frappe.get_cached_value(
                "Customer", self.mijoz, "custom_bonus_foiz"))
        if flt(self.bonus_foiz):
            for q in self.qatorlar:
                if not flt(q.bonus_foiz):
                    q.bonus_foiz = self.bonus_foiz

    def validate_guruhlar(self):
        """SKU faqat sotuv guruhidan, norma faqat ГП guruhidan bo'lsin.

        TEZLIK (2026-10-29): guruhlar BITTA so'rovda olinadi. Avval har
        qator uchun frappe.get_cached_value("Item", ...) chaqirilardi —
        kesh bo'sh bo'lsa u butun Item hujjatini (barcha bola jadvallari
        bilan) yuklaydi: 13 qatorli kartochkada 203 SQL / 0.16 s. Endi
        1 SQL / 0.001 s.
        """
        itemlar = {q.sku for q in self.qatorlar if q.sku}
        itemlar |= {q.norma for q in self.qatorlar if q.norma}
        if not itemlar:
            return

        guruh = dict(frappe.db.sql(
            """
            SELECT name, item_group FROM `tabItem` WHERE name IN %(itemlar)s
            """,
            {"itemlar": tuple(itemlar)},
        ))

        for q in self.qatorlar:
            if q.sku and guruh.get(q.sku) != SOTUV_GURUH:
                frappe.throw(_("{0}-qator: {1} «{2}» guruhidan emas").format(
                    q.idx, q.sku, SOTUV_GURUH))
            if q.norma and guruh.get(q.norma) != NORMA_GURUH:
                frappe.throw(_("{0}-qator: {1} norma («{2}») guruhidan emas").format(
                    q.idx, q.norma, NORMA_GURUH))

    def validate_takror(self):
        """Bitta SKU uchun bittadan ortiq Aktiv qator bo'lmasin."""
        aktiv = set()
        for q in self.qatorlar:
            if q.status != "Aktiv" or not q.sku:
                continue
            if q.sku in aktiv:
                frappe.throw(_("{0}-qator: «{1}» uchun ikkinchi Aktiv qator. "
                               "Eskisini Disabled qiling.").format(q.idx, q.sku_nomi or q.sku))
            aktiv.add(q.sku)

    def hisobla(self):
        """Tannarx MUZLATILGAN DAVRDAN o'qiladi, bu yerda hisoblanMAYDI.

        Avval har saqlashda tannarx_hisobla() qayta chaqirilar va natija
        shu kartochkaga yozilardi. Shuning uchun bitta SKU 58 kartochkada
        58 xil vaqtda hisoblanib, bir vaqtda bir nechta xil tannarx bilan
        turardi (126 SKU'dan 66 tasi, «Рулет Burxanov»da farq 117%).
        Endi manba bitta: pokiza.api.tannarx (Tannarx Davri).
        """
        from pokiza.api.tannarx import davr_map, joriy_tannarx

        karta = davr_map()
        for q in self.qatorlar:
            if q.sku:
                t = karta.get(q.sku) or joriy_tannarx(q.sku, norma=q.norma)
                q.tannarx = t["tannarx"]
                q.tannarx_tafsilot = "%s — %s" % (
                    t.get("manba") or "?", t.get("izoh") or "")
            q.bonus_keyin_narx = flt(q.sotuv_narxi) * (1 - flt(q.bonus_foiz) / 100)
            q.marja_som = flt(q.bonus_keyin_narx) - flt(q.tannarx)
            q.marja_foiz = (
                q.marja_som / q.bonus_keyin_narx * 100 if flt(q.bonus_keyin_narx) else 0
            )

    def jurnalga_yoz(self):
        """Har bir qator maydoni o'zgarishini jurnalga yozadi (o'chirilmas iz).

        QATOR BIRLIGI — `name` (2026-10-29). Avval qatorlar SKU bo'yicha
        dict'ga yig'ilardi; bitta SKU ikki qatorda bo'lishi esa QONUNIY
        (eski qator Disabled + yangisi Aktiv — validate_takror faqat
        ikkinchi AKTIV qatorni taqiqlaydi). Dict bunday juftlikdan bittasini
        yo'qotib, o'zgarishni noto'g'ri qator bilan solishtirardi:
        «Disabled qildim» o'rniga «narx o'zgardi» yoki hech narsa yozilmasdi.
        Bola qatorining `name`i o'zgarmaydi — identifikator shu.
        """
        if self.is_new():
            return

        eski = {
            q.name: q
            for q in frappe.get_all(
                "Mijoz Kartochka Qatori",
                filters={"parent": self.name, "parenttype": "Mijoz Kartochkasi"},
                fields=["name", "sku"] + list(KUZATILADIGAN),
            )
        }

        yozuvlar = []
        for q in self.qatorlar:
            e = eski.pop(q.name, None)
            if e is None:
                yozuvlar.append((q.sku, "qator", "", "qo'shildi"))
                continue
            for maydon in KUZATILADIGAN:
                old_v, new_v = e.get(maydon), q.get(maydon)
                if maydon in ("sotuv_narxi", "bonus_foiz"):
                    if flt(old_v, 2) == flt(new_v, 2):
                        continue
                elif str(old_v or "") == str(new_v or ""):
                    continue
                yozuvlar.append((q.sku, maydon, old_v, new_v))

        # pop'dan keyin qolganlar — o'chirilgan qatorlar
        for e in eski.values():
            yozuvlar.append((e.sku, "qator", "bor edi", "o'chirildi"))

        self._jurnal_koptrib(yozuvlar)

    def _jurnal_koptrib(self, yozuvlar):
        """Jurnal qatorlarini BITTA INSERT'da yozadi.

        Avval har o'zgarish uchun frappe.get_doc(...).insert() chaqirilardi:
        har biri alohida nomlash + INSERT + hook zanjiri. Bonus foizini
        tepadan o'zgartirsa 40 qatorga 40×KUZATILADIGAN yozuv tushadi —
        bitta saqlash yuzlab so'rovga aylanardi. Jurnal faqat yoziladigan
        (in_create) jadval, hook'lari yo'q — to'g'ridan-to'g'ri bulk insert
        xavfsiz va tartib (idx/creation) saqlanadi.
        """
        if not yozuvlar:
            return

        from frappe.utils import now

        # NOMLASH: autoname «format:KJL-{#####}» → frappe `{#####}` ni
        # getseries("", 5) bilan oladi, ya'ni hisoblagich tabSeries'dagi
        # BO'SH kalitda turadi (frappe'ning o'z xususiyati). Shuning uchun
        # nomni o'zimiz MAX(name)+1 qilib o'ylab chiqarmaymiz — hisoblagichni
        # bir marta N ga oshirib, aynan shu oraliqni band qilamiz, aks holda
        # keyingi get_doc().insert() nom to'qnashuvini beradi.
        n = len(yozuvlar)
        frappe.db.sql(
            """
            INSERT INTO `tabSeries` (`name`, `current`) VALUES ('', %(n)s)
            ON DUPLICATE KEY UPDATE `current` = `current` + %(n)s
            """,
            {"n": n},
        )
        boshi = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = ''")[0][0] - n
        vaqt, kim = now(), frappe.session.user

        frappe.db.bulk_insert(
            "Kartochka Ozgarish Jurnali",
            fields=[
                "name", "creation", "modified", "owner", "modified_by",
                "mijoz", "sku", "maydon", "eski_qiymat", "yangi_qiymat", "kim",
            ],
            values=[
                (
                    "KJL-%05d" % (boshi + i),
                    vaqt, vaqt, kim, kim,
                    self.mijoz, sku, maydon,
                    "" if eski is None else str(eski),
                    "" if yangi is None else str(yangi),
                    kim,
                )
                for i, (sku, maydon, eski, yangi) in enumerate(yozuvlar, start=1)
            ],
        )
