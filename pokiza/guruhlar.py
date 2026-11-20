"""Item guruh yordamchilari — bitta markaziy joy.

2026-11: egasi sotuv itemlarini tur bo'yicha bo'la boshladi — «Сотув
махсулотлари» endi guruh-tugun, ostida Сосиски / Полукопченые колбасы /
Вареные колбасы / Мясные деликатесы / Тушенки (va kelajakda yana).
Shuning uchun «sotuv mahsulotimi?» tekshiruvi qattiq nom bilan emas,
ildiz + barcha avlod guruhlari bo'yicha qilinadi — yangi bola guruh
qo'shilsa kod o'zgarmaydi. ГП itemlari esa «Фарш» guruhiga ko'chgan.
"""

import frappe

SOTUV_ILDIZ = "Сотув махсулотлари"
NORMA_GURUHLAR = ("Готовый продукт", "Фарш")


def sotuv_guruhlari():
    """SOTUV_ILDIZ va uning barcha avlod guruhlari (tuple).

    So'rov (request) doirasida keshlanadi — guruh daraxti so'rov ichida
    o'zgarmaydi; SQL `IN %s` paramga to'g'ridan-to'g'ri beriladi."""
    kesh = getattr(frappe.local, "pokiza_sotuv_guruhlari", None)
    if kesh is None:
        from frappe.utils.nestedset import get_descendants_of
        try:
            avlodlar = get_descendants_of(
                "Item Group", SOTUV_ILDIZ, ignore_permissions=True)
        except Exception:
            avlodlar = []
        kesh = frappe.local.pokiza_sotuv_guruhlari = tuple([SOTUV_ILDIZ, *avlodlar])
    return kesh


@frappe.whitelist()
def bom_item_guruhlari():
    """BOM item dropdowni uchun ruxsat etilgan guruhlar (public/js/bom.js)."""
    return list(NORMA_GURUHLAR) + list(sotuv_guruhlari())
