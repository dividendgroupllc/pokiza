# Copyright (c) 2026, Sardorbek and contributors
# For license information, please see license.txt

"""Tannarx Davri — oyma-oy MUZLATILGAN normativ tannarx (SKU kesimida).

NIMA UCHUN KERAK (2026-10-28):
Avval normativ tannarx har mijoz kartochkasiga alohida nusxa bo'lib
yozilardi va kartochka har saqlanganda o'sha kundagi narxda qayta
hisoblanardi. Natijada 126 SKU'dan 66 tasida bir vaqtda bir nechta xil
tannarx turardi — bitta mahsulotga ikki sotuvchi ikki xil raqam ko'rardi
(«Рулет Burxanov»: 10 885 va 23 637, farq 117%).

Endi tannarx — SKU ning xossasi, mijozning emas: bitta davr → bitta SKU →
bitta raqam. Kartochka ham, sotuv paytidagi muzlatish ham shu jadvaldan
o'qiydi, o'zi hisoblamaydi.

Davr oy bo'yi o'zgarmaydi — narx kelishuvlari shuning uchun barqaror.
Xomashyo keskin qimmatlashsa «Qayta hisoblash» tugmasi bilan davr
yangilanadi (va kim/qachon qilgani yozilib qoladi).

FAKTIK tannarx bu jadvalda YO'Q — u ombor hisobida (Stock Ledger) va
dashboardda. Ikkisining farqi «Tannarx Norma Fakt» hisobotida ko'rinadi.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_first_day, get_last_day, getdate, now_datetime

SOTUV_GURUH = "Сотув махсулотлари"


class TannarxDavri(Document):
    def autoname(self):
        """Nom = davr nomi (YYYY-MM).

        Frappe nomlashni validate'dan OLDIN bajaradi, shuning uchun
        davr_nomi shu yerda to'ldiriladi — aks holda json'dagi
        «field:davr_nomi» bo'sh maydonga tushib «Davr is required»
        xatosini beradi.
        """
        self._davrni_tozala()
        self.name = self.davr_nomi

    def _davrni_tozala(self):
        """Davr har doim to'liq oy: boshi → oyning 1-kuni, oxiri → oy oxiri."""
        if not self.davr_boshi:
            frappe.throw(_("Davr boshi kiritilmagan"))
        boshi = get_first_day(getdate(self.davr_boshi))
        self.davr_boshi = boshi
        self.davr_oxiri = get_last_day(boshi)
        self.davr_nomi = boshi.strftime("%Y-%m")

    def validate(self):
        self._davrni_tozala()

        korilgan = set()
        for q in self.qatorlar:
            if q.sku in korilgan:
                frappe.throw(_("{0}-qator: «{1}» takrorlangan").format(q.idx, q.sku))
            korilgan.add(q.sku)

    @frappe.whitelist()
    def qayta_hisobla(self):
        """Barcha aktiv sotuv SKU'lari uchun normativ tannarxni qayta yozadi.

        Tasdiqlangan davrni qayta hisoblash — ataylab ruxsat etilgan
        (xomashyo keskin qimmatlashganda kerak bo'ladi), lekin kim va
        qachon qilgani yozilib qoladi va o'zgarish Version'da ko'rinadi.
        """
        from pokiza.api.kartochka import bundle_normasi, tannarx_hisobla
        from pokiza.api.partiya import sku_bom, sku_bom_oldindan

        if not frappe.has_permission(self.doctype, "write", self):
            frappe.throw(_("Huquq yo'q"))

        skular = frappe.get_all(
            "Item",
            filters={"item_group": SOTUV_GURUH, "disabled": 0},
            pluck="name",
            order_by="name",
        )

        # 171 SKU'ning BOM'ini bitta so'rovda keshga olib qo'yamiz —
        # quyidagi tsiklda sku_bom() va tannarx_hisobla() shu keshdan
        # o'qiydi (SKU boshiga 3-6 so'rov tejaladi)
        sku_bom_oldindan(skular)

        self.set("qatorlar", [])
        hisoblanmadi = 0
        for sku in skular:
            norma = bundle_normasi(sku)
            try:
                t = tannarx_hisobla(sku, norma)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Tannarx Davri: {sku}")
                t = None

            if not t or not flt(t.get("tannarx")):
                hisoblanmadi += 1
                izoh = _("⚠ hisoblanmadi — SKU BOM'i yoki aktiv norma BOM'i yo'q")
            else:
                izoh = t.get("izoh") or ""

            b = sku_bom(sku)
            self.append("qatorlar", {
                "sku": sku,
                "norma": norma,
                "tannarx": flt(t.get("tannarx")) if t else 0,
                "farsh": flt(t.get("farsh")) if t else 0,
                "upakovka": flt(t.get("upakovka")) if t else 0,
                "bom": b.name if b else None,
                "izoh": izoh,
            })

        self.hisoblangan = now_datetime()
        self.hisoblagan = frappe.session.user
        self.save()

        # davr o'zgardi — tannarx.davr_map() keshi endi eskirgan
        from pokiza.api.tannarx import davr_keshni_tozala
        davr_keshni_tozala()

        frappe.msgprint(
            _("{0} SKU hisoblandi ({1} tasida normativ chiqmadi).").format(
                len(skular), hisoblanmadi),
            indicator="green" if not hisoblanmadi else "orange",
            alert=True,
        )
        return {"jami": len(skular), "hisoblanmadi": hisoblanmadi}
