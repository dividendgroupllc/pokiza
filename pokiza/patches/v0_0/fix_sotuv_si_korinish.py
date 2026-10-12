"""
Sotuvchiga Sales Invoice ro'yxati TO'LIQ ko'rinsin (2026-10-08).

Muammo (prodda): «Sotuv» roli bilan kirilganda faqat o'zi yaratgan
hujjatlar — draft/bekor qilingan/to'lanmagan — ko'rinardi, 1800 dan ortiq
Overdue schyot ko'rinmasdi.

Sabablari ikkita bo'lishi mumkin va ikkalasi ham KOD EMAS, baza sozlamasi
(shuning uchun oddiy kod yuborish yordam bermaydi):
  1) rol ruxsatida «Only If Creator» (if_owner) yoqilgan;
  2) foydalanuvchining ro'yxatida saqlanib qolgan filtr (__UserSettings).

Shu patch ikkalasini ham tuzatadi. Idempotent — qayta yurgizilsa zarar
bermaydi. User Permission topilsa O'CHIRILMAYDI, faqat ogohlantiradi
(u ataylab qo'yilgan bo'lishi mumkin).
"""

import frappe

ROL = "Sotuv"
DT = "Sales Invoice"


def execute():
    if not frappe.db.exists("Role", ROL):
        return

    # 1) «Only If Creator» ni o'chirish
    tuzatildi = 0
    for src in ("Custom DocPerm", "DocPerm"):
        for nomi in frappe.get_all(
            src,
            filters={"parent": DT, "role": ROL, "if_owner": 1},
            pluck="name",
        ):
            frappe.db.set_value(src, nomi, "if_owner", 0)
            tuzatildi += 1
    if tuzatildi:
        print(f"  ✅ {DT} / {ROL}: «Only If Creator» o'chirildi ({tuzatildi} ta qator)")

    # 2) shu roldagi foydalanuvchilarning ro'yxatida qotib qolgan filtrlar
    # DIQQAT: `Has Role` bola jadvali — frappe.get_all unda jim BO'SH
    # qaytaradi, shuning uchun to'g'ridan-to'g'ri SQL
    userlar = [
        r[0] for r in frappe.db.sql(
            "SELECT DISTINCT parent FROM `tabHas Role` "
            "WHERE role = %s AND parenttype = 'User'",
            ROL,
        )
    ]
    # DIQQAT: `__UserSettings` «tab» prefiksisiz jadval —
    # frappe.db.table_exists() uni TOPOLMAYDI (tab__UserSettings qidiradi)
    tozalandi = 0
    if userlar:
        for u in set(userlar):
            try:
                ta = frappe.db.sql(
                    "SELECT COUNT(*) FROM `__UserSettings` "
                    "WHERE `user`=%s AND `doctype`=%s",
                    (u, DT),
                )[0][0]
                if not ta:
                    continue
                frappe.db.sql(
                    "DELETE FROM `__UserSettings` WHERE `user`=%s AND `doctype`=%s",
                    (u, DT),
                )
                frappe.cache().hdel("_user_settings", f"{DT}::{u}")
                tozalandi += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(),
                                 "Pokiza: list filtrini tozalab bo'lmadi")
    if tozalandi:
        print(f"  ✅ {tozalandi} ta foydalanuvchining «{DT}» ro'yxat filtri tozalandi")

    # 3) User Permission — faqat ogohlantirish (o'chirilmaydi)
    for u in set(userlar):
        ups = frappe.db.count("User Permission", {"user": u})
        if ups:
            print(f"  ⚠ {u}: {ups} ta User Permission bor — ro'yxatni cheklayotgan "
                  f"bo'lishi mumkin (ataylab qo'yilgan bo'lsa tegilmaydi)")

    if tuzatildi or tozalandi:
        frappe.clear_cache()
