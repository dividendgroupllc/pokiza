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
        self.validate_guruhlar()
        self.validate_takror()
        self.hisobla()
        self.jurnalga_yoz()

    def validate_guruhlar(self):
        """SKU faqat sotuv guruhidan, norma faqat ГП guruhidan bo'lsin."""
        for q in self.qatorlar:
            if q.sku and frappe.get_cached_value("Item", q.sku, "item_group") != SOTUV_GURUH:
                frappe.throw(_("{0}-qator: {1} «{2}» guruhidan emas").format(
                    q.idx, q.sku, SOTUV_GURUH))
            if q.norma and frappe.get_cached_value("Item", q.norma, "item_group") != NORMA_GURUH:
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
                               "Eskisini Noaktiv qiling.").format(q.idx, q.sku_nomi or q.sku))
            aktiv.add(q.sku)

    def hisobla(self):
        from pokiza.api.kartochka import tannarx_hisobla

        for q in self.qatorlar:
            if q.sku:
                t = tannarx_hisobla(q.sku, q.norma)
                q.tannarx = t["tannarx"]
                q.tannarx_tafsilot = t["izoh"]
            q.bonus_keyin_narx = flt(q.sotuv_narxi) * (1 - flt(q.bonus_foiz) / 100)
            q.marja_som = flt(q.bonus_keyin_narx) - flt(q.tannarx)
            q.marja_foiz = (
                q.marja_som / q.bonus_keyin_narx * 100 if flt(q.bonus_keyin_narx) else 0
            )

    def jurnalga_yoz(self):
        """Har bir qator maydoni o'zgarishini jurnalga yozadi (o'chirilmas iz)."""
        if self.is_new():
            return

        eski_qatorlar = frappe.get_all(
            "Mijoz Kartochka Qatori",
            filters={"parent": self.name, "parenttype": "Mijoz Kartochkasi"},
            fields=["sku"] + list(KUZATILADIGAN),
        )
        eski = {q.sku: q for q in eski_qatorlar}
        yangi = {q.sku: q for q in self.qatorlar if q.sku}

        for sku, q in yangi.items():
            if sku not in eski:
                self._jurnal(sku, "qator", "", "qo'shildi")
                continue
            for maydon in KUZATILADIGAN:
                e, y = eski[sku].get(maydon), q.get(maydon)
                if maydon in ("sotuv_narxi", "bonus_foiz"):
                    if flt(e, 2) == flt(y, 2):
                        continue
                elif str(e or "") == str(y or ""):
                    continue
                self._jurnal(sku, maydon, e, y)

        for sku in eski:
            if sku not in yangi:
                self._jurnal(sku, "qator", "bor edi", "o'chirildi")

    def _jurnal(self, sku, maydon, eski, yangi):
        frappe.get_doc({
            "doctype": "Kartochka Ozgarish Jurnali",
            "mijoz": self.mijoz,
            "sku": sku,
            "maydon": maydon,
            "eski_qiymat": str(eski if eski is not None else ""),
            "yangi_qiymat": str(yangi if yangi is not None else ""),
            "kim": frappe.session.user,
        }).insert(ignore_permissions=True)
