"""
Sotuvchiga Sales Invoice ro'yxati to'liq ko'rinmasligini aniqlash
(2026-10-08: «faqat draft/cancelled/unpaid ko'rinyapti, overdue yo'q»).

Eng ko'p uchraydigan 3 sabab:
  1) Rol ruxsatida «if_owner» (faqat o'zi yaratgan hujjatlar) yoqilgan;
  2) Foydalanuvchiga User Permission qo'yilgan (masalan faqat bir nechta
     mijoz ko'rinadi);
  3) Ro'yxatda saqlanib qolgan filtr (status bo'yicha) — bu faqat
     brauzerdagi ko'rinish, ruxsatga aloqasi yo'q.

Ishga tushirish (serverda):
    bench --site SAYT execute pokiza.scripts.sotuv_ruxsat_tekshir.tekshir \
        --kwargs "{'user':'sotuvchi@gmail.com'}"
Filtrni tozalash (faqat ko'rinish, xavfsiz):
    bench --site SAYT execute pokiza.scripts.sotuv_ruxsat_tekshir.filtr_tozala \
        --kwargs "{'user':'sotuvchi@gmail.com'}"
"""

from collections import Counter

import frappe

DT = "Sales Invoice"


def tekshir(user="sotuvchi@gmail.com"):
    if not frappe.db.exists("User", user):
        print(f"❌ {user} foydalanuvchisi topilmadi")
        return

    rollar = sorted(frappe.get_roles(user))
    print(f"Foydalanuvchi: {user}")
    print(f"Rollari: {', '.join(rollar)}\n")

    # 1) ruxsatlar
    print("=== Sales Invoice ruxsatlari (shu foydalanuvchi rollari) ===")
    muammo_if_owner = []
    for dt in ("Custom DocPerm", "DocPerm"):
        for p in frappe.get_all(
            dt,
            filters={"parent": DT, "role": ["in", rollar], "permlevel": 0},
            fields=["role", "read", "if_owner"],
        ):
            belgi = "  ⚠ FAQAT O'ZINIKI" if p.if_owner else ""
            print(f"  [{dt.split()[0]:6}] {p.role:22} read={p.read} if_owner={p.if_owner}{belgi}")
            if p.if_owner and p.read:
                muammo_if_owner.append((dt, p.role))

    # 2) user permission
    ups = frappe.get_all(
        "User Permission",
        filters={"user": user},
        fields=["allow", "for_value", "applicable_for"],
    )
    print(f"\n=== User Permission: {len(ups)} ta ===")
    for up in ups[:15]:
        print(f"  {up.allow} = {up.for_value} (applicable_for={up.applicable_for or '-'})")

    # 3) real ko'rinish
    frappe.set_user(user)
    try:
        rows = frappe.get_list(DT, fields=["status"], limit_page_length=0)
    finally:
        frappe.set_user("Administrator")
    jami = frappe.db.count(DT)
    print(f"\n=== Ko'rinish: {len(rows)} / {jami} ta schyot ===")
    for s, c in Counter(r.status for r in rows).most_common():
        print(f"  {s or '-':14} {c}")

    # xulosa
    print("\n=== XULOSA ===")
    if len(rows) == jami:
        print("✅ Ruxsat to'liq — server hamma schyotni qaytaryapti.")
        print("   Demak sabab ro'yxatdagi SAQLANGAN FILTR (brauzerda):")
        print("   ro'yxat tepasidagi filtr belgilarini (×) olib tashlang yoki")
        print("   filtr_tozala() ni yurgizing.")
    else:
        if muammo_if_owner:
            print("❌ Sabab: ruxsatda «if_owner» yoqilgan — foydalanuvchi faqat")
            print("   O'ZI yaratgan schyotlarni ko'radi. Tuzatish: Role Permissions")
            print("   Manager'da Sales Invoice uchun shu roldagi «Only If Creator»")
            print("   belgisini olib tashlang:")
            for dt, rol in muammo_if_owner:
                print(f"     - {rol} ({dt})")
        if ups:
            print("❌ Sabab: User Permission cheklayapti (yuqoridagi ro'yxat).")
        if not muammo_if_owner and not ups:
            print("⚠ Ruxsat cheklangan, lekin sababi yuqoridagilarda emas —")
            print("  Permission Rules / Server Script'ni tekshiring.")


def filtr_tozala(user="sotuvchi@gmail.com"):
    """Ro'yxatda saqlanib qolgan filtrlarni tozalash (faqat ko'rinish)."""
    frappe.db.sql(
        "DELETE FROM `__UserSettings` WHERE `user` = %s AND `doctype` = %s",
        (user, DT),
    )
    frappe.cache().hdel("_user_settings", f"{DT}::{user}")
    frappe.db.commit()
    print(f"✅ {user} uchun «{DT}» ro'yxati filtrlari tozalandi. "
          "Brauzerni yangilang (Ctrl+Shift+R).")
